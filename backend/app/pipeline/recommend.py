"""Turn run results into ranked, evidence-backed recommendations.

Rule: every recommendation carries at least one *observed* evidence item from
this run (a cited page, a competitor example, or the user's own audit result)
and, where one exists, a reference to the technique's primary source.
"""

from statistics import median

from app.pipeline.engines import ENGINE_LABELS
from app.pipeline.techniques import SOURCE_TYPE_TECHNIQUE, TECHNIQUES
from app.util import truncate

SOURCE_WEIGHT = {"reviews": 1.0, "maps": 1.0, "marketplace": 0.9, "editorial": 0.9, "forum": 0.8,
                 "social": 0.5, "reference": 0.4}


def obs(label: str, url: str | None = None) -> dict:
    return {"label": label, "url": url, "kind": "observed"}


def _rec(priority: float, category: str, technique: str, title: str, detail: str, evidence: list[dict]) -> dict:
    t = TECHNIQUES[technique]
    return {
        "priority": round(priority, 1),
        "category": category,
        "technique_id": technique,
        "title": title,
        "detail": detail or t["how"],
        "evidence": evidence + t["references"],
    }


def _engines_str(engines: dict) -> str:
    return ", ".join(ENGINE_LABELS.get(e, e) for e, _ in sorted(engines.items(), key=lambda x: -x[1]))


def source_gap_recs(sources: list[dict]) -> list[dict]:
    recs = []
    for s in sources:
        if s["type"] in {"own", "competitor"} or s["listed"] is True:
            continue
        if s["target_in_answers_rate"] >= 0.6:
            continue
        weight = SOURCE_WEIGHT.get(s["type"], 0.7)
        priority = 100 * s["citation_rate"] * weight * (1 - s["target_in_answers_rate"]) + 10 * weight
        technique = SOURCE_TYPE_TECHNIQUE.get(s["type"], "editorial_outreach")
        top = s["pages"][0] if s["pages"] else None
        if s["type"] == "editorial" and top and top.get("title"):
            title = f"Get included in “{truncate(top['title'], 80)}” ({s['domain']})"
        elif s["type"] == "forum":
            title = f"Get recommended in {s['domain']} threads"
        else:
            title = f"Get listed and reviewed on {s['domain']}"
        listed_note = (" We checked the page and your business isn't named on it."
                       if s["listed"] is False else "")
        detail = (f"{s['domain']} was cited {s['citations']} times across {s['n_queries']} of your questions "
                  f"({_engines_str(s['engines'])}). You were mentioned in only "
                  f"{round(100 * s['target_in_answers_rate'])}% of the answers that cited it.{listed_note} "
                  + TECHNIQUES[technique]["how"])
        ev = [obs(f"Cited {p['citations']}×: {truncate(p.get('title') or p['url'], 90)}", p["url"]) for p in s["pages"][:3]]
        if s["top_competitors"]:
            ev.append(obs("Recommended alongside it: " + ", ".join(s["top_competitors"])))
        recs.append(_rec(priority, "source_gap", technique, title, detail, ev))
    return recs


SITE_CHECKS = [
    # (check key, technique, base priority, label for competitor evidence)
    ("local_business_schema", "local_business_schema", 30, "has LocalBusiness structured data"),
    ("faq", "faq_content", 26, "has an FAQ / Q&A section"),
    ("reviews_on_site", "reviews_on_site", 20, "shows reviews on its site"),
    ("sitemap", "sitemap", 12, "publishes an XML sitemap"),
    ("meta_description", "meta_description", 10, "has a meta description"),
]


def site_recs(audit: dict | None, comp_audits: list[dict]) -> list[dict]:
    recs: list[dict] = []
    if not audit or not audit.get("ok"):
        if audit and audit.get("error"):
            recs.append(_rec(40, "site", "unblock_ai_crawlers", "Make sure your website is reachable",
                             f"We couldn't load your site ({audit['error']}). If crawlers can't read it, engines can't cite it.",
                             [obs(audit["error"], audit.get("url"))]))
        return recs
    c = audit["checks"]
    url = audit["url"]

    if c.get("search_bots_blocked"):
        bots = ", ".join(c["search_bots_blocked"])
        recs.append(_rec(100, "site", "unblock_ai_crawlers", "Unblock AI search crawlers in robots.txt",
                         f"Your robots.txt blocks {bots}. These crawlers fetch pages for live AI answers, so this "
                         f"directly hides your site. " + TECHNIQUES["unblock_ai_crawlers"]["how"],
                         [obs(f"robots.txt blocks {bots}", url.rstrip('/') + "/robots.txt")]))

    ok_comps = [a for a in comp_audits if a.get("ok")]
    for key, tech, base, label in SITE_CHECKS:
        if c.get(key):
            continue
        having = [a for a in ok_comps if a["checks"].get(key)]
        share = len(having) / len(ok_comps) if ok_comps else 0
        ev = [obs(f"Your site: not found ({url})", url)]
        for a in having[:2]:
            ev.append(obs(f"{a.get('name') or a['domain']} {label}", a["url"]))
        detail = TECHNIQUES[tech]["how"]
        if ok_comps and not having:
            detail += " None of the competitors we checked do this either, so treat this as lower-confidence."
        recs.append(_rec(base * (0.5 + share), "site", tech, TECHNIQUES[tech]["title"], detail, ev))

    comp_words = [a["checks"].get("word_count", 0) for a in ok_comps]
    if comp_words and c.get("word_count", 0) < 0.5 * median(comp_words):
        med = int(median(comp_words))
        biggest = max(ok_comps, key=lambda a: a["checks"].get("word_count", 0))
        recs.append(_rec(22, "content", "content_depth", TECHNIQUES["content_depth"]["title"],
                         f"Your homepage has about {c.get('word_count', 0)} words; the competitors we checked have a median of {med}. "
                         + TECHNIQUES["content_depth"]["how"],
                         [obs(f"Your homepage: ~{c.get('word_count', 0)} words", url),
                          obs(f"{biggest.get('name') or biggest['domain']}: ~{biggest['checks'].get('word_count')} words", biggest["url"])]))
    return recs


def query_gap_recs(summary: dict, responses: list[dict]) -> list[dict]:
    engines = summary["engines"]
    gaps = []
    for row in summary["matrix"]:
        if row["kind"] == "branded":
            continue
        rates = [v for v in row["rates"].values() if v is not None]
        if rates and max(rates) == 0:
            gaps.append(row)
    if not gaps:
        return []
    ev = []
    for row in gaps[:5]:
        names: dict[str, int] = {}
        for r in responses:
            if r["query_id"] == row["query_id"]:
                for m in r["mentions"]:
                    if not m["is_target"]:
                        names[m["name"]] = names.get(m["name"], 0) + 1
        top = max(names, key=names.get) if names else None
        ev.append(obs(f"“{row['text']}”: never mentioned" + (f"; {top} was" if top else "")))
    detail = (f"You weren't mentioned by any engine ({', '.join(ENGINE_LABELS.get(e, e) for e in engines)}) "
              f"for {len(gaps)} of your questions. " + TECHNIQUES["query_content"]["how"])
    return [_rec(20 + 3 * len(gaps), "content", "query_content", TECHNIQUES["query_content"]["title"], detail, ev)]


def engine_recs(summary: dict) -> list[dict]:
    per = {e: m for e, m in summary["per_engine"].items() if m.get("visibility") is not None}
    if len(per) < 2:
        return []
    best_e, best = max(per.items(), key=lambda kv: kv[1]["visibility"])
    recs = []
    for e, m in per.items():
        if e == best_e or best["visibility"] < 15 or m["visibility"] > 0.5 * best["visibility"]:
            continue
        ev = [obs(f"{ENGINE_LABELS.get(e, e)}: {m['visibility']:.0f}/100 vs {ENGINE_LABELS.get(best_e, best_e)}: {best['visibility']:.0f}/100")]
        if e == "chatgpt":
            recs.append(_rec(28, "site", "bing_index", "Close your ChatGPT gap: get indexed by Bing",
                             TECHNIQUES["bing_index"]["how"], ev))
        elif e == "gemini":
            recs.append(_rec(28, "source_gap", "maps_listings", "Close your Gemini gap: strengthen your Google presence",
                             TECHNIQUES["maps_listings"]["how"], ev))
        elif e == "perplexity":
            recs.append(_rec(24, "source_gap", "forum_presence", "Close your Perplexity gap: community and editorial sources",
                             "Perplexity leans heavily on forums and editorial lists. Check the source gaps below for the pages it cites, "
                             "and make sure PerplexityBot is not blocked.", ev))
    return recs


def build_recommendations(summary: dict, responses: list[dict], sources: list[dict],
                          audit: dict | None, comp_audits: list[dict], limit: int = 12) -> list[dict]:
    recs = (site_recs(audit, comp_audits) + source_gap_recs(sources)
            + query_gap_recs(summary, responses) + engine_recs(summary))
    # Every recommendation must carry observed evidence.
    recs = [r for r in recs if any(e["kind"] == "observed" for e in r["evidence"])]
    recs.sort(key=lambda r: -r["priority"])
    return recs[:limit]
