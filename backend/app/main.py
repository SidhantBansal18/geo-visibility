import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import worker
from app.config import get_settings
from app.db import get_db, init_db
from app.models import Business, Query, Recommendation, Response, Run
from app.pipeline import profile as profile_mod
from app.pipeline.engines import ENGINE_LABELS, get_engines
from app.schemas import BusinessIn, BusinessPatch, InferIn, QueryIn, RecommendationPatch, RunIn, SuggestQueriesIn
from app.util import host_of, normalize_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    await worker.start()
    yield
    await worker.stop()


app = FastAPI(title="GEO Visibility API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- serializers ----------

def _iso(dt):
    return dt.isoformat() + "Z" if dt else None  # stored as naive UTC


def ser_query(q: Query) -> dict:
    return {"id": q.id, "text": q.text, "kind": q.kind, "active": q.active}


def ser_run_brief(r: Run) -> dict:
    o = (r.summary or {}).get("overall", {})
    return {
        "id": r.id, "status": r.status, "stage": r.stage, "trigger": r.trigger, "engines": r.engines,
        "samples_per_query": r.samples_per_query, "progress_done": r.progress_done,
        "progress_total": r.progress_total, "error": r.error,
        "created_at": _iso(r.created_at), "finished_at": _iso(r.finished_at),
        "visibility": o.get("visibility"), "ci": o.get("ci"),
        "per_engine": {e: m.get("visibility") for e, m in ((r.summary or {}).get("per_engine") or {}).items()},
    }


def ser_business(b: Business, with_queries: bool = True) -> dict:
    latest = b.runs[-1] if b.runs else None
    latest_done = next((r for r in reversed(b.runs) if r.status == "done"), None)
    d = {
        "id": b.id, "url": b.url, "domain": b.domain, "name": b.name, "aliases": b.aliases or [],
        "category": b.category, "location": b.location, "description": b.description,
        "recheck_enabled": b.recheck_enabled, "recheck_days": b.recheck_days, "next_run_at": _iso(b.next_run_at),
        "created_at": _iso(b.created_at),
        "latest_run": ser_run_brief(latest) if latest else None,
        "latest_done_run": ser_run_brief(latest_done) if latest_done else None,
    }
    if with_queries:
        d["queries"] = [ser_query(q) for q in b.queries]
    return d


def _get_business(db: Session, bid: int) -> Business:
    b = db.get(Business, bid)
    if not b:
        raise HTTPException(404, "Business not found")
    return b


def _start_run(db: Session, b: Business, engines=None, samples=None, trigger="manual") -> Run:
    busy = db.scalar(select(Run.id).where(Run.business_id == b.id, Run.status.in_(("queued", "running"))))
    if busy:
        raise HTTPException(409, f"Run {busy} is already in progress for this business.")
    try:
        run = worker.create_run(db, b, trigger=trigger, engines=engines, samples=samples)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    worker.enqueue(run.id)
    return run


# ---------- meta ----------

@app.get("/api/health")
def health():
    s = get_settings()
    engines = get_engines()
    return {
        "ok": True,
        "mock": s.geo_mock,
        "engines": [{"id": e, "label": ENGINE_LABELS.get(e, e)} for e in engines],
        "samples_per_query": s.samples_per_query,
    }


# ---------- onboarding ----------

@app.post("/api/profile/infer")
async def infer(body: InferIn):
    return await profile_mod.infer_profile(body.url)


@app.post("/api/profile/queries")
async def suggest(body: SuggestQueriesIn):
    return {"queries": await profile_mod.suggest_queries(body.name, body.category, body.location, body.description)}


# ---------- businesses ----------

@app.get("/api/businesses")
def list_businesses(db: Session = Depends(get_db)):
    return [ser_business(b, with_queries=False) for b in db.scalars(select(Business).order_by(Business.id.desc()))]


@app.post("/api/businesses", status_code=201)
def create_business(body: BusinessIn, db: Session = Depends(get_db)):
    url = normalize_url(body.url)
    b = Business(
        url=url, domain=host_of(url) or url, name=body.name.strip(), category=body.category.strip(),
        location=body.location.strip(), description=body.description.strip(), aliases=body.aliases,
        recheck_enabled=body.recheck_enabled, recheck_days=body.recheck_days,
        queries=[Query(text=q.text.strip(), kind=q.kind, active=q.active) for q in body.queries],
    )
    db.add(b)
    db.commit()
    run_id = None
    if body.run_now:
        run_id = _start_run(db, b, body.engines, body.samples_per_query).id
    db.refresh(b)
    return {**ser_business(b), "run_id": run_id}


@app.get("/api/businesses/{bid}")
def get_business(bid: int, db: Session = Depends(get_db)):
    return ser_business(_get_business(db, bid))


@app.patch("/api/businesses/{bid}")
def patch_business(bid: int, body: BusinessPatch, db: Session = Depends(get_db)):
    b = _get_business(db, bid)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(b, k, v.strip() if isinstance(v, str) else v)
    if body.recheck_enabled is False:
        b.next_run_at = None
    db.commit()
    return ser_business(b)


@app.delete("/api/businesses/{bid}", status_code=204)
def delete_business(bid: int, db: Session = Depends(get_db)):
    db.delete(_get_business(db, bid))
    db.commit()


@app.put("/api/businesses/{bid}/queries")
def replace_queries(bid: int, body: list[QueryIn], db: Session = Depends(get_db)):
    if not body or len(body) > 30:
        raise HTTPException(422, "Provide between 1 and 30 queries.")
    b = _get_business(db, bid)
    existing = {q.id: q for q in b.queries}
    keep = []
    for qi in body:
        q = existing.get(qi.id) if qi.id else None
        if q is None:
            q = Query(business_id=b.id)
            db.add(q)
        q.text, q.kind, q.active = qi.text.strip(), qi.kind, qi.active
        keep.append(q)
    for qid, q in existing.items():
        if q not in keep:
            db.delete(q)
    db.commit()
    db.refresh(b)
    return [ser_query(q) for q in b.queries]


# ---------- runs ----------

@app.post("/api/businesses/{bid}/runs", status_code=202)
def start_run(bid: int, body: RunIn | None = None, db: Session = Depends(get_db)):
    b = _get_business(db, bid)
    body = body or RunIn()
    return ser_run_brief(_start_run(db, b, body.engines, body.samples_per_query))


@app.get("/api/businesses/{bid}/runs")
def list_runs(bid: int, db: Session = Depends(get_db)):
    _get_business(db, bid)
    runs = db.scalars(select(Run).where(Run.business_id == bid).order_by(Run.id)).all()
    return [ser_run_brief(r) for r in runs]


@app.get("/api/runs/{rid}")
def get_run(rid: int, db: Session = Depends(get_db)):
    r = db.get(Run, rid)
    if not r:
        raise HTTPException(404, "Run not found")
    return {
        **ser_run_brief(r),
        "business_id": r.business_id,
        "summary": r.summary,
        "competitors": r.competitors or [],
        "source_gaps": r.source_gaps or [],
        "site_audit": r.site_audit,
        "competitor_audits": r.competitor_audits or [],
        "recommendations": [{
            "id": x.id, "rank": x.rank, "priority": x.priority, "category": x.category, "title": x.title,
            "detail": x.detail, "technique_id": x.technique_id, "evidence": x.evidence, "done": x.done,
        } for x in r.recommendations],
    }


@app.get("/api/runs/{rid}/responses")
def get_responses(rid: int, query_id: int | None = None, engine: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Response).where(Response.run_id == rid)
    if query_id is not None:
        stmt = stmt.where(Response.query_id == query_id)
    if engine:
        stmt = stmt.where(Response.engine == engine)
    out = []
    for x in db.scalars(stmt.order_by(Response.query_id, Response.engine, Response.sample)):
        out.append({
            "id": x.id, "query_id": x.query_id, "query_text": x.query_text, "query_kind": x.query_kind,
            "engine": x.engine, "sample": x.sample, "text": x.text, "error": x.error, "latency_ms": x.latency_ms,
            "target_mentioned": x.target_mentioned, "target_position": x.target_position,
            "target_linked": x.target_linked,
            "mentions": [{"name": m.name, "domain": m.domain, "position": m.position, "is_target": m.is_target}
                         for m in x.mentions],
            "citations": [{"url": c.url, "domain": c.domain, "title": c.title} for c in x.citations],
        })
    return out


@app.patch("/api/recommendations/{rec_id}")
def patch_recommendation(rec_id: int, body: RecommendationPatch, db: Session = Depends(get_db)):
    rec = db.get(Recommendation, rec_id)
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    rec.done = body.done
    db.commit()
    return {"id": rec.id, "done": rec.done}
