"""Website fetching, parsing and the AI-readiness site audit."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.util import host_of, normalize_url

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 GEO-Visibility-Audit/0.1"
)
MAX_BYTES = 2_000_000

# Crawlers that feed AI answers. Blocking the *search* bots hides you from
# live answers; blocking training bots only affects future model knowledge.
AI_BOTS = {
    "OAI-SearchBot": "ChatGPT search",
    "ChatGPT-User": "ChatGPT browsing",
    "GPTBot": "OpenAI training",
    "PerplexityBot": "Perplexity",
    "Google-Extended": "Gemini training/grounding",
    "Bingbot": "Bing / Copilot / ChatGPT search index",
    "ClaudeBot": "Anthropic",
}
SEARCH_CRITICAL_BOTS = {"OAI-SearchBot", "PerplexityBot", "Bingbot", "ChatGPT-User"}

PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")


@dataclass
class Page:
    url: str
    final_url: str
    status: int
    html: str
    title: str = ""
    meta_description: str = ""
    site_name: str = ""
    h1: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    text: str = ""
    jsonld: list[dict] = field(default_factory=list)


async def fetch(url: str, client: httpx.AsyncClient | None = None, timeout: float = 20.0) -> tuple[int, str, str]:
    """Returns (status, final_url, body). Raises on network errors."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA})
    try:
        r = await client.get(url)
        body = r.content[:MAX_BYTES].decode(r.encoding or "utf-8", errors="replace")
        return r.status_code, str(r.url), body
    finally:
        if own:
            await client.aclose()


def _flatten_jsonld(obj) -> list[dict]:
    out: list[dict] = []
    if isinstance(obj, list):
        for o in obj:
            out.extend(_flatten_jsonld(o))
    elif isinstance(obj, dict):
        if "@graph" in obj:
            out.extend(_flatten_jsonld(obj["@graph"]))
        out.append(obj)
    return out


def parse(url: str, final_url: str, status: int, html: str) -> Page:
    soup = BeautifulSoup(html, "html.parser")
    jsonld: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            jsonld.extend(_flatten_jsonld(json.loads(tag.string or "")))
        except (json.JSONDecodeError, TypeError):
            continue

    def meta(**attrs) -> str:
        tag = soup.find("meta", attrs=attrs)
        return (tag.get("content") or "").strip() if tag else ""

    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    h1 = [h.get_text(" ", strip=True) for h in soup.find_all("h1")][:5]
    headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h2", "h3"])][:60]
    for t in soup(["script", "style", "noscript", "svg", "iframe"]):
        t.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return Page(
        url=url,
        final_url=final_url,
        status=status,
        html=html,
        title=title,
        meta_description=meta(name="description") or meta(property="og:description"),
        site_name=meta(property="og:site_name"),
        h1=h1,
        headings=headings,
        text=text,
        jsonld=jsonld,
    )


async def fetch_page(url: str, client: httpx.AsyncClient | None = None) -> Page:
    url = normalize_url(url)
    status, final_url, html = await fetch(url, client)
    return parse(url, final_url, status, html)


def _types(node: dict) -> list[str]:
    t = node.get("@type", [])
    return [t] if isinstance(t, str) else [x for x in t if isinstance(x, str)]


LOCAL_TYPES = {
    "LocalBusiness", "Organization", "Store", "ProfessionalService", "HomeAndConstructionBusiness",
    "Restaurant", "MedicalBusiness", "LegalService", "AutomotiveBusiness", "EntertainmentBusiness",
    "FinancialService", "HealthAndBeautyBusiness", "FoodEstablishment", "Dentist", "Plumber",
    "Electrician", "RealEstateAgent", "LodgingBusiness", "SportsActivityLocation", "EventVenue",
}


def business_schema(page: Page) -> dict | None:
    """The first LocalBusiness-ish JSON-LD node, if any."""
    best = None
    for node in page.jsonld:
        types = set(_types(node))
        if types & (LOCAL_TYPES - {"Organization"}):
            return node
        if "Organization" in types and best is None:
            best = node
    return best


def schema_location(node: dict | None) -> str | None:
    if not node:
        return None
    addr = node.get("address")
    if isinstance(addr, list):
        addr = addr[0] if addr else None
    if isinstance(addr, dict):
        city, region = addr.get("addressLocality"), addr.get("addressRegion")
        if city:
            return f"{city}, {region}" if region else city
    area = node.get("areaServed")
    if isinstance(area, str):
        return area
    if isinstance(area, dict) and area.get("name"):
        return area["name"]
    return None


def parse_robots(robots: str) -> dict[str, bool]:
    """Map bot -> blocked-from-root, honouring specific groups over '*'."""
    groups: list[tuple[list[str], list[str]]] = []
    agents: list[str] = []
    rules: list[str] = []
    last_was_agent = False
    for raw in robots.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if not last_was_agent and agents:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(v.lower())
            last_was_agent = True
        elif k == "disallow":
            if v == "/":
                rules.append("block")
            last_was_agent = False
        elif k == "allow":
            if v == "/":
                rules.append("allow")
            last_was_agent = False
    if agents:
        groups.append((agents, rules))

    def blocked_for(agent: str) -> bool | None:
        for ags, rs in groups:
            if agent in ags:
                return "block" in rs and "allow" not in rs
        return None

    star = blocked_for("*") or False
    out = {}
    for bot in AI_BOTS:
        specific = blocked_for(bot.lower())
        out[bot] = star if specific is None else specific
    return out


async def audit_site(url: str) -> dict:
    """AI-readiness checks for one website. Never raises; failures are recorded."""
    url = normalize_url(url)
    result: dict = {"url": url, "domain": host_of(url), "ok": False, "checks": {}, "error": None}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": UA}) as client:
        try:
            page = await fetch_page(url, client)
        except Exception as e:  # noqa: BLE001
            result["error"] = f"Could not fetch site: {e.__class__.__name__}"
            return result
        if page.status >= 400:
            result["error"] = f"Site returned HTTP {page.status}"
            return result
        result["ok"] = True
        base = page.final_url

        async def get_text(path: str) -> tuple[int, str]:
            try:
                st, _, body = await fetch(urljoin(base, path), client)
                return st, body
            except Exception:  # noqa: BLE001
                return 0, ""

        (r_st, robots), (s_st, sitemap), (l_st, _) = await asyncio.gather(
            get_text("/robots.txt"), get_text("/sitemap.xml"), get_text("/llms.txt")
        )

    blocked = parse_robots(robots) if r_st == 200 else {b: False for b in AI_BOTS}
    schema = business_schema(page)
    types = sorted({t for n in page.jsonld for t in _types(n)})
    words = len(page.text.split())
    faq = "FAQPage" in types or any(
        re.search(r"\b(faq|frequently asked)\b", h, re.I) for h in page.headings + page.h1
    ) or sum(1 for h in page.headings if h.endswith("?")) >= 3
    has_reviews = any("aggregateRating" in n or "review" in n for n in page.jsonld) or bool(
        re.search(r"\b(reviews?|testimonials?|★|stars?)\b", page.text[:20000], re.I)
    )

    result["checks"] = {
        "https": base.startswith("https://"),
        "title": page.title,
        "meta_description": bool(page.meta_description),
        "word_count": words,
        "jsonld_types": types,
        "local_business_schema": bool(schema and set(_types(schema)) & LOCAL_TYPES),
        "schema_has_address": bool(schema and schema.get("address")),
        "aggregate_rating_schema": any("aggregateRating" in n for n in page.jsonld),
        "faq": bool(faq),
        "reviews_on_site": bool(has_reviews),
        "phone_visible": bool(PHONE_RE.search(page.text)),
        "robots_found": r_st == 200,
        "ai_bots_blocked": [b for b, v in blocked.items() if v],
        "search_bots_blocked": [b for b, v in blocked.items() if v and b in SEARCH_CRITICAL_BOTS],
        "sitemap": s_st == 200 and ("<urlset" in sitemap or "<sitemapindex" in sitemap),
        "llms_txt": l_st == 200,
    }
    return result
