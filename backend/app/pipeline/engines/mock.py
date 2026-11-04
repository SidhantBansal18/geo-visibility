"""Offline engine used when GEO_MOCK=1.

Produces realistic-looking, *non-deterministic* answers so the whole pipeline
(extraction, sampling variance, scoring, source gaps, trends) can be exercised
and demoed without API keys. Each engine has a different appetite for the target
business so the dashboard shows meaningful per-engine differences.
"""

import asyncio
import random
import zlib

import httpx

from app.pipeline.engines.base import AskContext, EngineAnswer
from app.util import squash

PREFIXES = ["Summit", "Lone Star", "BrightPath", "Apex", "Blue Ridge", "Northside", "Premier", "Elite", "Metro", "Golden Hour"]

# Base probability the target is mentioned for a non-branded query, per engine.
TARGET_RATE = {"chatgpt": 0.30, "claude": 0.25, "gemini": 0.55, "perplexity": 0.18}


def _tc(s: str) -> str:
    return " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in s.split())


def _city(ctx: AskContext) -> str:
    return ctx.city or (ctx.location.split(",")[0].strip() if ctx.location else "Springfield")


def competitor_pool(ctx: AskContext) -> list[dict]:
    rng = random.Random(zlib.crc32((ctx.business_domain or ctx.business_name or "x").encode()))
    cat = " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in (ctx.category or "service").split())
    city = _city(ctx)
    names = [f"{p} {cat}" for p in rng.sample(PREFIXES, 6)] + [f"{city} {cat} Co.", f"{cat} Pros of {city}"]
    pool = []
    for i, n in enumerate(names):
        pool.append({"name": n, "domain": squash(n)[:24] + ".com", "weight": 1.6 ** (len(names) - i)})
    return pool


def source_pool(ctx: AskContext) -> list[dict]:
    city = _city(ctx)
    cat = ctx.category or "service"
    slug = squash(city)
    cslug = "-".join(cat.lower().split())
    return [
        {"url": f"https://www.yelp.com/search?find_desc={cslug}&find_loc={slug}", "title": f"Top 10 Best {_tc(cat)} in {city} - Yelp", "w": 5},
        {"url": f"https://www.reddit.com/r/{slug}/comments/mock123/recommendations_for_{cslug.replace('-', '_')}/", "title": f"Recommendations for {cat}? : r/{slug}", "w": 4},
        {"url": f"https://www.expertise.com/{slug}/{cslug}", "title": f"Best {_tc(cat)} in {city} | Expertise.com", "w": 3},
        {"url": f"https://www.thumbtack.com/{slug}/{cslug}/", "title": f"The 10 Best {_tc(cat)} near {city} - Thumbtack", "w": 2},
        {"url": f"https://www.bbb.org/search?find_text={cslug}&find_loc={slug}", "title": f"{_tc(cat)} near {city} | BBB", "w": 1.5},
        {"url": f"https://{slug}magazine.com/best-of/{cslug}", "title": f"Best of {city}: {_tc(cat)}", "w": 2},
    ]


class MockEngine:
    def __init__(self, engine_id: str, label: str):
        self.id, self.label = engine_id, label

    async def ask(self, query: str, ctx: AskContext, client: httpx.AsyncClient) -> EngineAnswer:
        await asyncio.sleep(random.uniform(0.02, 0.12))
        rng = random.Random()
        pool = competitor_pool(ctx)
        branded = bool(ctx.business_name) and ctx.business_name.lower() in query.lower()

        k = rng.randint(3, 6)
        chosen: list[dict] = []
        candidates = pool[:]
        while candidates and len(chosen) < k:
            pick = rng.choices(candidates, weights=[c["weight"] for c in candidates])[0]
            candidates.remove(pick)
            chosen.append(pick)

        rate = 0.95 if branded else TARGET_RATE.get(self.id, 0.3)
        if rng.random() < rate:
            target = {"name": ctx.business_name, "domain": ctx.business_domain}
            pos = 0 if branded else min(len(chosen), rng.choice([0, 1, 2, 2, 3, 4, 5]))
            chosen.insert(pos, target)

        link = self.id != "gemini"  # Gemini answers rarely inline links
        lines = [f"Here are some well-regarded options for \"{query}\":", ""]
        for i, b in enumerate(chosen, 1):
            nm = f"[{b['name']}](https://{b['domain']})" if link and rng.random() < 0.7 else b["name"]
            lines.append(f"{i}. **{nm}** - known for {rng.choice(['fast turnaround', 'strong reviews', 'fair pricing', 'experienced staff', 'wide inventory'])}.")
        lines += ["", "Check recent reviews and request quotes from two or three of these before deciding."]

        sources = source_pool(ctx)
        n_src = rng.randint(2, 5) if self.id != "chatgpt" else rng.randint(1, 4)
        cites = []
        for s in rng.choices(sources, weights=[s["w"] for s in sources], k=n_src):
            if s["url"] not in [c["url"] for c in cites]:
                cites.append({"url": s["url"], "title": s["title"]})
        # Sometimes cite a competitor's own site.
        if rng.random() < 0.4 and chosen:
            b = rng.choice(chosen)
            if b.get("domain") and b["domain"] != ctx.business_domain:
                cites.append({"url": f"https://{b['domain']}/", "title": b["name"]})
        return EngineAnswer(text="\n".join(lines), citations=cites)


def mock_engines() -> dict:
    return {
        "chatgpt": MockEngine("chatgpt", "ChatGPT"),
        "claude": MockEngine("claude", "Claude"),
        "gemini": MockEngine("gemini", "Gemini"),
        "perplexity": MockEngine("perplexity", "Perplexity"),
    }


def mock_competitor_audit(name: str, domain: str) -> dict:
    rng = random.Random(zlib.crc32(domain.encode()))
    return {
        "url": f"https://{domain}/",
        "domain": domain,
        "name": name,
        "ok": True,
        "mock": True,
        "error": None,
        "checks": {
            "https": True,
            "title": f"{name} | Trusted Local Service",
            "meta_description": rng.random() < 0.9,
            "word_count": rng.randint(400, 2200),
            "jsonld_types": ["LocalBusiness"] if rng.random() < 0.7 else [],
            "local_business_schema": rng.random() < 0.7,
            "schema_has_address": rng.random() < 0.6,
            "aggregate_rating_schema": rng.random() < 0.4,
            "faq": rng.random() < 0.6,
            "reviews_on_site": rng.random() < 0.75,
            "phone_visible": True,
            "robots_found": True,
            "ai_bots_blocked": [],
            "search_bots_blocked": [],
            "sitemap": rng.random() < 0.8,
            "llms_txt": rng.random() < 0.15,
        },
    }


def mock_own_audit(url: str, domain: str) -> dict:
    """Used in mock mode when the real site can't be fetched (e.g. a made-up URL)."""
    a = mock_competitor_audit("", domain)
    a.update({"url": url, "name": None})
    a["checks"].update({"local_business_schema": False, "schema_has_address": False, "jsonld_types": [],
                        "faq": False, "word_count": 310, "aggregate_rating_schema": False})
    return a
