"""Small text / URL helpers shared by the pipeline."""

import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlparse

_TWO_LEVEL_SUFFIXES = {"co.uk", "com.au", "co.nz", "co.in", "com.br", "co.za", "com.mx", "co.jp", "org.uk"}

# Words that carry no identity ("Acme LED Rentals LLC" == "Acme LED Rentals").
_STOPWORDS = {
    "the", "inc", "llc", "ltd", "co", "corp", "corporation", "company", "group",
    "and", "&", "of", "pllc", "lp", "llp",
}


def normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def host_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(normalize_url(url)).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def registrable_domain(url_or_host: str | None) -> str | None:
    """example.com for https://www.blog.example.com/x (good enough without a PSL)."""
    host = host_of(url_or_host) if url_or_host and ("/" in url_or_host or ":" in url_or_host) else url_or_host
    if not host:
        return None
    host = host.lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in _TWO_LEVEL_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def name_key(name: str) -> str:
    """Normalised identity for a business name, used to group mentions."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    tokens = [t for t in s.split() if t not in _STOPWORDS]
    return " ".join(tokens).strip()


def name_similarity(a: str, b: str) -> float:
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    # Treat "brightwave" vs "brightwave led rentals" as a strong match.
    if (ka in kb or kb in ka) and min(len(ka), len(kb)) >= 5:
        return 0.92
    return SequenceMatcher(None, ka, kb).ratio()


def domain_brand(domain: str | None) -> str:
    """'dallasledpros.com' -> 'dallasledpros' (for loose name/domain matching)."""
    if not domain:
        return ""
    return registrable_domain(domain).split(".")[0] if registrable_domain(domain) else ""


def squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def text_mentions_name(text: str, names: list[str]) -> bool:
    """Case/punctuation-insensitive substring check for any of the names."""
    low = text.lower()
    sq = squash(text)
    for n in names:
        n = n.strip()
        if len(n) < 3:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(n.lower()) + r"(?![a-z0-9])", low):
            return True
        nsq = squash(n)
        if len(nsq) >= 6 and nsq in sq:
            return True
    return False


def truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"
