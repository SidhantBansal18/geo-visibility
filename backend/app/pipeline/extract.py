"""Turn an engine answer into an ordered list of businesses, and decide whether
(and where) the target business appears."""

import re
from dataclasses import dataclass, field

from app.pipeline import llm
from app.util import name_key, name_similarity, registrable_domain, text_mentions_name

MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
BARE_URL = re.compile(r"https?://[^\s)\]>\"']+")
BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
LIST_ITEM = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\d{1,2}[.)]|[-*•])\s+(.*)$")
HEADING = re.compile(r"^\s*#{2,6}\s+(?:\d{1,2}[.)]\s*)?(.*)$")

GENERIC = {
    "tips", "considerations", "key considerations", "pricing", "reviews", "summary", "note", "notes",
    "conclusion", "overview", "factors", "what to look for", "bottom line", "recommendation",
    "recommendations", "pros", "cons", "cost", "services", "location", "why", "how to choose",
    "final thoughts", "sources", "quick picks", "best for", "highlights", "contact", "website",
}


@dataclass
class Extracted:
    mentions: list[dict] = field(default_factory=list)  # name, key, domain, position, is_target, linked
    target_mentioned: bool = False
    target_position: int | None = None  # 1-based position among businesses, None if not ranked
    target_linked: bool = False


def _clean_name(s: str) -> str:
    s = MD_LINK.sub(r"\1", s)
    s = re.sub(r"[*_`#]", "", s)
    s = BARE_URL.sub("", s)
    return s.strip(" \t:-–—.,;")


def _candidate_from_item(body: str) -> tuple[str, str | None] | None:
    link = MD_LINK.search(body)
    bold = BOLD.search(body)
    if bold:
        name = bold.group(1) or bold.group(2)
        inner = MD_LINK.search(name)
        url = inner.group(2) if inner else (link.group(2) if link and link.start() < bold.end() + 40 else None)
        name = _clean_name(name)
    elif link and link.start() < 5:
        name, url = _clean_name(link.group(1)), link.group(2)
    else:
        head = re.split(r"\s[-–—]\s|:\s|\s\(", MD_LINK.sub(r"\1", body), maxsplit=1)[0]
        name, url = _clean_name(head), (link.group(2) if link else None)
    return (name, url) if _looks_like_business(name) else None


def _looks_like_business(name: str) -> bool:
    if not name or len(name) > 70:
        return False
    words = name.split()
    if not (1 <= len(words) <= 8):
        return False
    if name.lower().strip(" :") in GENERIC or name.endswith("?"):
        return False
    if not any(w[:1].isupper() or w[:1].isdigit() for w in words):
        return False
    return True


def heuristic_businesses(text: str) -> list[tuple[str, str | None]]:
    """Businesses in order of appearance from list items, headings and bold runs."""
    found: list[tuple[str, str | None]] = []
    for line in text.splitlines():
        m = LIST_ITEM.match(line) or HEADING.match(line)
        if m:
            cand = _candidate_from_item(m.group(1))
            if cand:
                found.append(cand)
            continue
        # Bold names inside prose (common in Gemini/Perplexity answers).
        for b in BOLD.finditer(line):
            name = _clean_name(b.group(1) or b.group(2))
            if _looks_like_business(name) and len(name.split()) >= 2:
                found.append((name, None))
    # De-duplicate by identity, keep first occurrence.
    out, seen = [], set()
    for name, url in found:
        k = name_key(name)
        if k and k not in seen:
            seen.add(k)
            out.append((name, url))
    return out


EXTRACT_SYSTEM = (
    "Extract the specific businesses (companies, shops, providers) that an AI assistant's answer "
    "recommends or names, in order of first appearance. Exclude directories and publishers "
    "(Yelp, Google, Reddit, Thumbtack, BBB, Angi, magazines) unless the answer recommends them as a provider. "
    'Return JSON {"businesses": [{"name": str, "url": str|null}]}.'
)


async def llm_businesses(query: str, text: str) -> list[tuple[str, str | None]] | None:
    if not llm.available():
        return None
    data = await llm.complete_json(EXTRACT_SYSTEM, f"Question: {query}\n\nAnswer:\n{text[:12000]}")
    if not data or not isinstance(data.get("businesses"), list):
        return None
    out = []
    for b in data["businesses"]:
        if isinstance(b, dict) and isinstance(b.get("name"), str) and b["name"].strip():
            url = b.get("url") if isinstance(b.get("url"), str) else None
            out.append((b["name"].strip(), url))
    return out


def _is_target(name: str, domain: str | None, target_names: list[str], target_domain: str | None) -> bool:
    if target_domain and domain and domain == target_domain:
        return True
    return any(name_similarity(name, t) >= 0.85 for t in target_names)


def resolve(
    text: str,
    businesses: list[tuple[str, str | None]],
    citations: list[dict],
    target_names: list[str],
    target_url: str,
) -> Extracted:
    target_domain = registrable_domain(target_url)
    all_urls = [m.group(0) for m in BARE_URL.finditer(text)] + [c["url"] for c in citations]
    linked_domains = {registrable_domain(u) for u in all_urls}

    ex = Extracted()
    for i, (name, url) in enumerate(businesses, 1):
        dom = registrable_domain(url) if url else None
        is_t = _is_target(name, dom, target_names, target_domain)
        ex.mentions.append({
            "name": name,
            "key": name_key(name),
            "domain": dom,
            "position": i,
            "is_target": is_t,
            "linked": bool(dom and dom in linked_domains),
        })
        if is_t and ex.target_position is None:
            ex.target_position = i

    domain_in_text = bool(target_domain) and target_domain in text.lower()
    ex.target_mentioned = ex.target_position is not None or domain_in_text or text_mentions_name(text, target_names)
    ex.target_linked = bool(target_domain and target_domain in linked_domains)
    return ex


async def extract(query: str, text: str, citations: list[dict], target_names: list[str], target_url: str) -> Extracted:
    if not text.strip():
        return Extracted()
    businesses = await llm_businesses(query, text)
    if businesses is None:
        businesses = heuristic_businesses(text)
    return resolve(text, businesses, citations, target_names, target_url)
