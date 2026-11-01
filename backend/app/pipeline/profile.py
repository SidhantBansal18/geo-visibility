"""Step 1 of onboarding: infer who the business is, then propose queries."""

import logging
import re

from app.pipeline import llm
from app.pipeline.scrape import business_schema, fetch_page, schema_location
from app.util import domain_brand, host_of, normalize_url, truncate

log = logging.getLogger(__name__)

QUERY_KINDS = ("unbranded", "use_case", "comparison", "branded")

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
    "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}
CITY_STATE_RE = re.compile(r"\b([A-Z][a-zA-Z.]+(?:\s[A-Z][a-zA-Z.]+){0,2}),\s?([A-Z]{2})\b")


def _guess_name(page, schema: dict | None, domain: str) -> str:
    if schema and isinstance(schema.get("name"), str):
        return schema["name"].strip()
    if page.site_name:
        return page.site_name
    if page.title:
        # "Acme LED Rentals | LED Walls in Dallas" -> "Acme LED Rentals"
        first = re.split(r"\s[|\-–—:]\s", page.title)[0].strip()
        if 2 <= len(first) <= 60:
            return first
    return domain_brand(domain).replace("-", " ").title()


def _guess_location(page, schema: dict | None) -> str:
    loc = schema_location(schema)
    if loc:
        return loc
    for m in CITY_STATE_RE.finditer(page.title + " " + page.text[:20000]):
        if m.group(2) in US_STATES:
            return f"{m.group(1)}, {m.group(2)}"
    return ""


def _guess_category(page, name: str) -> str:
    # Use the title remainder or the first h1 that is not the name.
    candidates = re.split(r"\s[|\-–—:]\s", page.title)[1:] + page.h1
    for c in candidates:
        c = re.sub(r"\b(in|near|serving)\b.*$", "", c, flags=re.I).strip(" .,|-")
        if c and c.lower() != name.lower() and 3 <= len(c) <= 60:
            return c
    return ""


def template_queries(name: str, category: str, location: str) -> list[dict]:
    cat = category or "service"
    loc = location or "my area"
    return [
        {"kind": "unbranded", "text": f"What are the best {cat} companies in {loc}?"},
        {"kind": "unbranded", "text": f"Who is the most reliable {cat} provider in {loc}?"},
        {"kind": "unbranded", "text": f"Top rated {cat} in {loc} with good reviews"},
        {"kind": "unbranded", "text": f"Affordable {cat} options in {loc}"},
        {"kind": "unbranded", "text": f"Which {cat} business in {loc} do locals recommend?"},
        {"kind": "use_case", "text": f"I need {cat} in {loc} on short notice. Who should I call?"},
        {"kind": "use_case", "text": f"Recommend a {cat} company in {loc} for a business or corporate client"},
        {"kind": "use_case", "text": f"What should I look for when hiring a {cat} company in {loc}, and who are good options?"},
        {"kind": "comparison", "text": f"Compare the top {cat} companies in {loc}"},
        {"kind": "comparison", "text": f"{name} vs other {cat} companies in {loc}: which is better?"},
        {"kind": "branded", "text": f"Is {name} a good {cat} company?"},
        {"kind": "branded", "text": f"What do customers say about {name} in {loc}?"},
    ]


PROFILE_SYSTEM = (
    "You analyse a small business website and return JSON. Be concrete and short. "
    "category is the service a customer would search for, as a noun phrase usable in "
    "'best <category> companies in <location>' (e.g. 'LED wall rental', 'emergency plumbing'). "
    "location is the primary city and state/region served (e.g. 'Dallas, TX'); empty string if unknown."
)

QUERY_SYSTEM = (
    "You write the questions a real customer would type into ChatGPT, Gemini or Perplexity when "
    "looking for a business like this one. Return JSON {\"queries\": [{\"kind\", \"text\"}]}. "
    "Write 12 queries: 5 'unbranded' (best/top/recommended <category> in <location>, varied wording), "
    "3 'use_case' (specific situations this business serves, with location), "
    "2 'comparison' (comparing options; one may name the business), "
    "2 'branded' (questions about the business by name). Natural, conversational phrasing. "
    "Every non-branded query must include the location."
)


async def infer_profile(url: str) -> dict:
    """Returns a draft profile plus suggested queries. Never raises on scrape failure."""
    url = normalize_url(url)
    domain = host_of(url) or url
    draft = {
        "url": url,
        "domain": domain,
        "name": domain_brand(domain).replace("-", " ").title(),
        "category": "",
        "location": "",
        "description": "",
        "aliases": [],
        "scrape_ok": False,
        "needs_input": [],
    }
    page = None
    try:
        page = await fetch_page(url)
        draft["scrape_ok"] = page.status < 400
    except Exception as e:  # noqa: BLE001
        log.info("profile scrape failed for %s: %s", url, e)

    if page and draft["scrape_ok"]:
        schema = business_schema(page)
        draft["name"] = _guess_name(page, schema, domain)
        draft["location"] = _guess_location(page, schema)
        draft["category"] = _guess_category(page, draft["name"])
        draft["description"] = truncate(page.meta_description, 300)

        ai = await llm.complete_json(
            PROFILE_SYSTEM,
            "Return JSON with keys name, category, location, description (one sentence), "
            "aliases (other names/spellings the business goes by).\n\n"
            f"URL: {url}\nTitle: {page.title}\nMeta: {page.meta_description}\n"
            f"H1: {page.h1}\nHeadings: {page.headings[:20]}\n"
            f"Schema hints: name={draft['name']!r} location={draft['location']!r}\n"
            f"Page text: {truncate(page.text, 6000)}",
        )
        if ai:
            for k in ("name", "category", "location", "description"):
                if isinstance(ai.get(k), str) and ai[k].strip():
                    draft[k] = ai[k].strip()
            if isinstance(ai.get("aliases"), list):
                draft["aliases"] = [a for a in ai["aliases"] if isinstance(a, str) and a.strip()][:5]

    brand = domain_brand(domain)
    if brand and brand not in [a.lower() for a in draft["aliases"]]:
        draft["aliases"].append(brand)

    draft["needs_input"] = [k for k in ("name", "category", "location") if not draft[k]]
    draft["queries"] = await suggest_queries(draft["name"], draft["category"], draft["location"], draft["description"])
    return draft


async def suggest_queries(name: str, category: str, location: str, description: str = "") -> list[dict]:
    if category and location:
        ai = await llm.complete_json(
            QUERY_SYSTEM,
            f"Business: {name}\nCategory: {category}\nLocation: {location}\nDescription: {description}",
        )
        if ai and isinstance(ai.get("queries"), list):
            out = []
            for q in ai["queries"]:
                if isinstance(q, dict) and isinstance(q.get("text"), str) and q["text"].strip():
                    kind = q.get("kind") if q.get("kind") in QUERY_KINDS else "unbranded"
                    out.append({"kind": kind, "text": q["text"].strip()})
            if len(out) >= 6:
                return out[:15]
    return template_queries(name, category, location)
