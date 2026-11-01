"""Executes one analysis run end to end."""

import asyncio
import logging
import random
import time
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import Business, Citation, Mention, Recommendation, Response, Run, utcnow
from app.pipeline import extract as extract_mod
from app.pipeline.engines import AskContext, get_engines
from app.pipeline.engines.mock import mock_competitor_audit, mock_own_audit
from app.pipeline.recommend import build_recommendations
from app.pipeline.scoring import aggregate_competitors, compute_summary
from app.pipeline.scrape import audit_site
from app.pipeline.sources import analyze_sources, check_listings
from app.util import registrable_domain, truncate

log = logging.getLogger(__name__)


def target_names(b: Business) -> list[str]:
    return [b.name] + [a for a in (b.aliases or []) if a and a.lower() != b.name.lower()]


def ask_context(b: Business) -> AskContext:
    parts = [p.strip() for p in (b.location or "").split(",")]
    return AskContext(
        city=parts[0] if parts else "",
        region=parts[1] if len(parts) > 1 else "",
        business_name=b.name,
        business_domain=registrable_domain(b.url) or b.domain,
        category=b.category,
        location=b.location,
    )


async def _ask_with_retry(engine, query: str, ctx: AskContext, client: httpx.AsyncClient, attempts: int = 3):
    delay = 2.0
    for i in range(attempts):
        try:
            return await engine.ask(query, ctx, client)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code not in (429, 500, 502, 503, 504) or i == attempts - 1:
                raise RuntimeError(f"HTTP {code}: {truncate(e.response.text, 300)}") from e
        except (httpx.TransportError, httpx.TimeoutException):
            if i == attempts - 1:
                raise
        await asyncio.sleep(delay + random.random())
        delay *= 2


def _set(db: Session, run: Run, **kw) -> None:
    for k, v in kw.items():
        setattr(run, k, v)
    db.commit()


async def execute_run(run_id: int) -> None:
    s = get_settings()
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if run is None or run.status not in ("queued", "running"):
            return
        b = run.business
        queries = [q for q in b.queries if q.active]
        all_engines = get_engines()
        engines = {e: all_engines[e] for e in run.engines if e in all_engines}
        if not engines:
            raise RuntimeError("No engines available. Set API keys or GEO_MOCK=1.")
        if not queries:
            raise RuntimeError("No active queries for this business.")

        jobs = [(q, e, i) for q in queries for e in engines for i in range(run.samples_per_query)]
        _set(db, run, status="running", stage="asking engines", started_at=utcnow(),
             progress_total=len(jobs), progress_done=0, error=None)

        ctx = ask_context(b)
        names = target_names(b)
        audit_task = asyncio.create_task(audit_site(b.url))
        sem = asyncio.Semaphore(s.engine_concurrency)

        async with httpx.AsyncClient(timeout=s.request_timeout_s) as client:

            async def one(q, e, i):
                async with sem:
                    t0 = time.monotonic()
                    try:
                        ans = await _ask_with_retry(engines[e], q.text, ctx, client)
                        ex = await extract_mod.extract(q.text, ans.text, ans.citations, names, b.url)
                        return q, e, i, ans, ex, None, int(1000 * (time.monotonic() - t0))
                    except Exception as err:  # noqa: BLE001 - recorded per response
                        log.warning("engine %s failed on %r: %s", e, q.text, err)
                        return q, e, i, None, None, f"{err.__class__.__name__}: {err}", None

            for fut in asyncio.as_completed([one(*j) for j in jobs]):
                q, e, i, ans, ex, err, ms = await fut
                resp = Response(run_id=run.id, query_id=q.id, query_text=q.text, query_kind=q.kind,
                                engine=e, sample=i, text=ans.text if ans else "", error=err, latency_ms=ms)
                if ex:
                    resp.target_mentioned = ex.target_mentioned
                    resp.target_position = ex.target_position
                    resp.target_linked = ex.target_linked
                    resp.mentions = [Mention(**m) for m in ex.mentions]
                if ans:
                    resp.citations = [
                        Citation(url=c["url"], domain=registrable_domain(c["url"]) or c["url"],
                                 title=c.get("title"), position=k)
                        for k, c in enumerate(ans.citations)
                    ]
                db.add(resp)
                run.progress_done += 1
                db.commit()

        ok = [r for r in run.responses if r.error is None]
        if not ok:
            first = next((r.error for r in run.responses if r.error), "unknown error")
            raise RuntimeError(f"All engine calls failed. First error: {first}")

        _set(db, run, stage="analysing competitors and sources")
        rows = [{
            "query_id": r.query_id, "query_kind": r.query_kind, "engine": r.engine,
            "mentioned": r.target_mentioned, "position": r.target_position, "linked": r.target_linked,
            "n_businesses": len(r.mentions), "target_mentioned": r.target_mentioned,
            "mentions": [{"name": m.name, "key": m.key, "domain": m.domain, "position": m.position,
                          "is_target": m.is_target} for m in r.mentions],
            "citations": [{"url": c.url, "title": c.title} for c in r.citations],
        } for r in ok]

        summary = compute_summary(rows, list(engines), [{"id": q.id, "text": q.text, "kind": q.kind} for q in queries])
        summary["n_errors"] = len(run.responses) - len(ok)
        summary["mock"] = s.geo_mock
        competitors = aggregate_competitors(rows)
        comp_domains = {c["domain"] for c in competitors if c["domain"]}
        target_domain = registrable_domain(b.url)
        sources = analyze_sources(rows, target_domain, comp_domains)
        if not s.geo_mock:
            await check_listings(sources, names)

        _set(db, run, stage="auditing websites")
        audit = await audit_task
        if s.geo_mock and not audit.get("ok"):
            audit = mock_own_audit(b.url, target_domain or b.domain)
        top = [c for c in competitors if c["domain"]][:3]
        if s.geo_mock:
            comp_audits = [mock_competitor_audit(c["name"], c["domain"]) for c in top]
        else:
            comp_audits = await asyncio.gather(*(audit_site(c["domain"]) for c in top))
            for a, c in zip(comp_audits, top):
                a["name"] = c["name"]

        recs = build_recommendations(summary, rows, sources, audit, list(comp_audits))
        run.recommendations = [Recommendation(rank=k + 1, **r) for k, r in enumerate(recs)]
        _set(db, run, summary=summary, competitors=competitors, source_gaps=sources,
             site_audit=audit, competitor_audits=list(comp_audits),
             status="done", stage="done", finished_at=utcnow())
        if b.recheck_enabled:
            b.next_run_at = utcnow() + timedelta(days=b.recheck_days)
            db.commit()
    except Exception as e:  # noqa: BLE001
        log.exception("run %s failed", run_id)
        db.rollback()
        run = db.get(Run, run_id)
        if run:
            _set(db, run, status="failed", stage="failed", error=str(e), finished_at=utcnow())
            # Keep the schedule alive: retry a failed check the next day.
            if run.business.recheck_enabled and run.business.next_run_at is None:
                run.business.next_run_at = utcnow() + timedelta(days=1)
                db.commit()
    finally:
        db.close()
