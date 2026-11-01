"""Source-gap analysis: which pages do the engines cite when they recommend your
competitors, and are you on them?"""

import asyncio
from collections import Counter, defaultdict

import httpx

from app.pipeline.scoring import SCORED_KINDS
from app.pipeline.scrape import UA, fetch
from app.util import registrable_domain, text_mentions_name

SOURCE_TYPES: dict[str, set[str]] = {
    "reviews": {"yelp.com", "tripadvisor.com", "trustpilot.com", "bbb.org", "angi.com", "angieslist.com",
                "homeadvisor.com", "houzz.com", "birdeye.com", "weddingwire.com", "theknot.com", "zocdoc.com",
                "healthgrades.com", "avvo.com", "g2.com", "capterra.com", "glassdoor.com"},
    "marketplace": {"thumbtack.com", "bark.com", "taskrabbit.com", "eventective.com", "gigsalad.com",
                    "peerspace.com", "upwork.com", "fiverr.com", "expertise.com", "threebestrated.com",
                    "porch.com", "networx.com", "clutch.co", "upcity.com"},
    "maps": {"google.com", "maps.apple.com", "bing.com", "mapquest.com", "apple.com"},
    "forum": {"reddit.com", "quora.com", "nextdoor.com", "stackexchange.com"},
    "social": {"facebook.com", "instagram.com", "linkedin.com", "youtube.com", "tiktok.com", "x.com", "twitter.com",
               "pinterest.com"},
    "reference": {"wikipedia.org", "wikidata.org"},
}

TYPE_LABELS = {
    "reviews": "Review site",
    "marketplace": "Directory / marketplace",
    "maps": "Maps listing",
    "forum": "Forum / community",
    "social": "Social",
    "reference": "Reference",
    "editorial": "Article / list",
    "competitor": "Competitor site",
    "own": "Your site",
}


def classify(domain: str, target_domain: str | None, competitor_domains: set[str]) -> str:
    if target_domain and domain == target_domain:
        return "own"
    if domain in competitor_domains:
        return "competitor"
    for t, doms in SOURCE_TYPES.items():
        if domain in doms:
            return t
    return "editorial"


def analyze_sources(
    responses: list[dict],
    target_domain: str | None,
    competitor_domains: set[str],
    limit: int = 15,
) -> list[dict]:
    """responses: engine, query_id, query_kind, target_mentioned, citations, mentions."""
    scored = [r for r in responses if r["query_kind"] in SCORED_KINDS]
    by_url: dict[str, dict] = {}
    for r in scored:
        comps = [m["name"] for m in r["mentions"] if not m["is_target"]]
        for c in r["citations"]:
            url = c["url"]
            dom = registrable_domain(url) or url
            s = by_url.setdefault(url, {
                "url": url, "domain": dom, "title": c.get("title"), "citations": 0, "engines": Counter(),
                "queries": set(), "with_target": 0, "competitors": Counter(),
            })
            s["citations"] += 1
            s["engines"][r["engine"]] += 1
            s["queries"].add(r["query_id"])
            s["with_target"] += int(r["target_mentioned"])
            s["competitors"].update(comps)
            if not s["title"] and c.get("title"):
                s["title"] = c["title"]

    # Roll up by domain so 6 different Yelp URLs read as one opportunity.
    by_domain: dict[str, dict] = defaultdict(lambda: {"urls": [], "citations": 0, "engines": Counter(),
                                                       "queries": set(), "with_target": 0, "competitors": Counter()})
    for s in by_url.values():
        d = by_domain[s["domain"]]
        d["urls"].append(s)
        d["citations"] += s["citations"]
        d["engines"].update(s["engines"])
        d["queries"] |= s["queries"]
        d["with_target"] += s["with_target"]
        d["competitors"].update(s["competitors"])

    total = len(scored) or 1
    out = []
    for dom, d in by_domain.items():
        stype = classify(dom, target_domain, competitor_domains)
        urls = sorted(d["urls"], key=lambda s: -s["citations"])
        out.append({
            "domain": dom,
            "type": stype,
            "type_label": TYPE_LABELS[stype],
            "citations": d["citations"],
            "citation_rate": round(d["citations"] / total, 3),
            "engines": dict(d["engines"]),
            "n_queries": len(d["queries"]),
            "target_in_answers_rate": round(d["with_target"] / d["citations"], 3) if d["citations"] else 0,
            "top_competitors": [n for n, _ in d["competitors"].most_common(3)],
            "pages": [{"url": s["url"], "title": s["title"], "citations": s["citations"], "listed": None}
                      for s in urls[:5]],
            "listed": None,  # filled by check_listings: True / False / None (unknown)
        })
    out.sort(key=lambda s: -s["citations"])
    return out[:limit]


async def check_listings(sources: list[dict], target_names: list[str], max_pages: int = 10) -> None:
    """Best-effort: fetch top third-party pages and check whether the target is named.
    Many sites block bots, so 'unknown' (None) is a normal outcome."""
    pages = [(s, p) for s in sources if s["type"] not in {"own", "competitor"} for p in s["pages"][:2]][:max_pages]
    if not pages:
        return
    sem = asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": UA}) as client:

        async def check(page: dict) -> None:
            async with sem:
                try:
                    status, _, body = await fetch(page["url"], client)
                except Exception:  # noqa: BLE001
                    return
                if status == 200 and len(body) > 2000:
                    page["listed"] = text_mentions_name(body, target_names)

        await asyncio.gather(*(check(p) for _, p in pages))
    for s in sources:
        vals = [p["listed"] for p in s["pages"] if p["listed"] is not None]
        s["listed"] = any(vals) if vals else None
