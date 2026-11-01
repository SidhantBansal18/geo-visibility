"""Visibility metrics with honest uncertainty.

Answers are non-deterministic, and samples of the same query are correlated, so
confidence intervals use a cluster bootstrap that resamples *queries* (with all
of their samples), not individual answers.
"""

import random
from collections import Counter, defaultdict
from statistics import mean

from app.util import name_similarity

SCORED_KINDS = {"unbranded", "use_case", "comparison"}
BOOTSTRAP_ITERS = 1000


def _cell_rates(rows: list[dict]) -> dict[tuple[int, str], float]:
    cells: dict[tuple[int, str], list[bool]] = defaultdict(list)
    for r in rows:
        cells[(r["query_id"], r["engine"])].append(r["mentioned"])
    return {k: sum(v) / len(v) for k, v in cells.items()}


def _visibility(rows: list[dict]) -> float | None:
    rates = _cell_rates(rows)
    return 100 * mean(rates.values()) if rates else None


def _bootstrap_ci(rows: list[dict], seed: int = 7) -> tuple[float, float] | None:
    by_q: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_q[r["query_id"]].append(r)
    qids = list(by_q)
    if len(qids) < 2:
        return None
    rng = random.Random(seed)
    stats = []
    for _ in range(BOOTSTRAP_ITERS):
        sample: list[dict] = []
        for j, q in enumerate(rng.choices(qids, k=len(qids))):
            # Re-key duplicates so they count as separate cells.
            sample.extend({**r, "query_id": (q, j)} for r in by_q[q])
        v = _visibility(sample)
        if v is not None:
            stats.append(v)
    stats.sort()
    lo = stats[int(0.025 * len(stats))]
    hi = stats[min(len(stats) - 1, int(0.975 * len(stats)))]
    return round(lo, 1), round(hi, 1)


def _metrics(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"visibility": None, "ci": None, "n": 0}
    ranked = [r["position"] for r in rows if r["position"] is not None]
    vis = _visibility(rows)
    return {
        "visibility": round(vis, 1) if vis is not None else None,
        "ci": _bootstrap_ci(rows),
        "mention_rate": round(sum(r["mentioned"] for r in rows) / n, 3),
        "top3_rate": round(sum(1 for r in rows if r["position"] is not None and r["position"] <= 3) / n, 3),
        "linked_rate": round(sum(r["linked"] for r in rows) / n, 3),
        "avg_position": round(mean(ranked), 2) if ranked else None,
        "n": n,
    }


def compute_summary(rows: list[dict], engines: list[str], queries: list[dict]) -> dict:
    """rows: one dict per successful response with query_id, query_kind, engine,
    mentioned, position, linked, n_businesses."""
    scored = [r for r in rows if r["query_kind"] in SCORED_KINDS]
    branded = [r for r in rows if r["query_kind"] == "branded"]

    overall = _metrics(scored)
    total_biz = sum(r["n_businesses"] for r in scored)
    target_biz = sum(1 for r in scored if r["position"] is not None)
    overall["share_of_voice"] = round(target_biz / total_biz, 3) if total_biz else None

    per_engine = {e: _metrics([r for r in scored if r["engine"] == e]) for e in engines}

    matrix = []
    rates = _cell_rates(rows)
    for q in queries:
        matrix.append({
            "query_id": q["id"],
            "text": q["text"],
            "kind": q["kind"],
            "rates": {e: (round(rates[(q["id"], e)], 3) if (q["id"], e) in rates else None) for e in engines},
        })

    return {
        "overall": overall,
        "per_engine": per_engine,
        "branded": _metrics(branded) if branded else None,
        "matrix": matrix,
        "engines": engines,
        "n_queries_scored": len({r["query_id"] for r in scored}),
    }


def aggregate_competitors(responses: list[dict], limit: int = 15) -> list[dict]:
    """responses: dicts with engine, query_id, query_kind, mentions (list of mention dicts)."""
    scored = [r for r in responses if r["query_kind"] in SCORED_KINDS]
    groups: list[dict] = []

    def find_group(m: dict) -> dict | None:
        for g in groups:
            if m["domain"] and m["domain"] in g["domains"]:
                return g
            if m["key"] == g["key"] or name_similarity(m["name"], g["display"]) >= 0.9:
                return g
        return None

    for r in scored:
        seen_here: set[int] = set()
        for m in r["mentions"]:
            if m["is_target"]:
                continue
            g = find_group(m)
            if g is None:
                g = {"key": m["key"], "display": m["name"], "names": Counter(), "domains": Counter(),
                     "positions": [], "responses": 0, "engines": Counter(), "queries": set()}
                groups.append(g)
            g["names"][m["name"]] += 1
            if m["domain"]:
                g["domains"][m["domain"]] += 1
            if id(g) not in seen_here:
                seen_here.add(id(g))
                g["responses"] += 1
                g["positions"].append(m["position"])
                g["engines"][r["engine"]] += 1
                g["queries"].add(r["query_id"])

    total = len(scored) or 1
    out = []
    for g in groups:
        out.append({
            "name": g["names"].most_common(1)[0][0],
            "domain": g["domains"].most_common(1)[0][0] if g["domains"] else None,
            "appearance_rate": round(g["responses"] / total, 3),
            "appearances": g["responses"],
            "avg_position": round(mean(g["positions"]), 2),
            "top3": sum(1 for p in g["positions"] if p <= 3),
            "engines": dict(g["engines"]),
            "n_queries": len(g["queries"]),
        })
    out.sort(key=lambda c: (-c["appearance_rate"], c["avg_position"]))
    return out[:limit]
