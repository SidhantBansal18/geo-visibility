from app.pipeline.engines.live import parse_gemini_response, parse_openai_response, parse_perplexity_response
from app.pipeline.extract import heuristic_businesses, resolve
from app.pipeline.recommend import build_recommendations
from app.pipeline.scoring import aggregate_competitors, compute_summary
from app.pipeline.scrape import parse_robots
from app.pipeline.sources import analyze_sources, classify
from app.util import name_similarity, registrable_domain, text_mentions_name

# ---------- util ----------

def test_registrable_domain():
    assert registrable_domain("https://www.blog.example.com/x") == "example.com"
    assert registrable_domain("shop.example.co.uk") == "example.co.uk"
    assert registrable_domain("example.com") == "example.com"


def test_name_similarity():
    assert name_similarity("Acme LED Rentals LLC", "acme led rentals") == 1.0
    assert name_similarity("BrightWave", "BrightWave LED Rentals") > 0.9
    assert name_similarity("Acme LED", "Summit Audio Visual") < 0.6


def test_text_mentions_name_word_boundaries():
    assert text_mentions_name("Try **Acme LED** for walls", ["Acme LED"])
    assert text_mentions_name("see dallasledpros.com", ["dallasledpros"])
    assert not text_mentions_name("Acmeled is different", ["Acme"])


# ---------- engine parsers ----------

def test_parse_openai_response():
    data = {"output": [
        {"type": "web_search_call", "id": "ws_1"},
        {"type": "message", "content": [{"type": "output_text", "text": "1. **Acme** - great",
                                         "annotations": [{"type": "url_citation", "url": "https://yelp.com/x", "title": "Yelp"},
                                                         {"type": "url_citation", "url": "https://yelp.com/x", "title": "Yelp"}]}]},
    ]}
    a = parse_openai_response(data)
    assert a.text.startswith("1. **Acme**")
    assert a.citations == [{"url": "https://yelp.com/x", "title": "Yelp"}]


def test_parse_gemini_response():
    data = {"candidates": [{"content": {"parts": [{"text": "Acme is good."}]},
                            "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://r/1", "title": "yelp.com"}}]}}]}
    a = parse_gemini_response(data)
    assert a.text == "Acme is good."
    assert a.citations[0]["title"] == "yelp.com"
    assert parse_gemini_response({"candidates": []}).text == ""


def test_parse_perplexity_response():
    base = {"choices": [{"message": {"content": "Acme [1]"}}]}
    assert parse_perplexity_response({**base, "citations": ["https://a.com"]}).citations[0]["url"] == "https://a.com"
    sr = parse_perplexity_response({**base, "search_results": [{"url": "https://b.com", "title": "B"}], "citations": ["x"]})
    assert sr.citations == [{"url": "https://b.com", "title": "B"}]


# ---------- extraction ----------

ANSWER = """Here are the top LED wall rental companies in Dallas:

1. **[Summit LED](https://summitled.com)** - fast setup and strong reviews.
2. **Acme LED Rentals** – great for corporate events.
3. Lone Star Screens: affordable packages ([site](https://lonestarscreens.com))

### Key Considerations
- **Pricing:** expect $1,500+ per day.

Also worth a look is **Blue Ridge Visuals**, a newer player.
"""


def test_heuristic_businesses_order_and_filtering():
    names = [n for n, _ in heuristic_businesses(ANSWER)]
    assert names[:3] == ["Summit LED", "Acme LED Rentals", "Lone Star Screens"]
    assert "Blue Ridge Visuals" in names
    assert "Pricing" not in names and "Key Considerations" not in names


def test_resolve_target_position_and_link():
    biz = heuristic_businesses(ANSWER)
    ex = resolve(ANSWER, biz, [{"url": "https://www.acmeled.com/about", "title": None}], ["Acme LED Rentals"], "acmeled.com")
    assert ex.target_mentioned and ex.target_position == 2 and ex.target_linked
    summit = ex.mentions[0]
    assert summit["domain"] == "summitled.com" and summit["linked"]


def test_resolve_mentioned_but_not_ranked():
    text = "Many people mention Acme LED Rentals in passing, but here are picks:\n1. **Summit LED** - good"
    ex = resolve(text, heuristic_businesses(text), [], ["Acme LED Rentals"], "acmeled.com")
    assert ex.target_mentioned and ex.target_position is None and not ex.target_linked


# ---------- robots ----------

def test_parse_robots_specific_overrides_star():
    robots = """
User-agent: *
Disallow: /admin

User-agent: GPTBot
User-agent: PerplexityBot
Disallow: /
"""
    b = parse_robots(robots)
    assert b["GPTBot"] and b["PerplexityBot"]
    assert not b["OAI-SearchBot"] and not b["Bingbot"]


def test_parse_robots_star_block():
    b = parse_robots("User-agent: *\nDisallow: /\n\nUser-agent: Bingbot\nAllow: /\n")
    assert b["OAI-SearchBot"] and not b["Bingbot"]


# ---------- scoring / sources / recs ----------

def _rows():
    rows = []
    # q1: chatgpt mentions target 2/2, gemini 0/2; q2: never; q3 branded always.
    for q, kind, eng, hits in [(1, "unbranded", "chatgpt", [True, True]), (1, "unbranded", "gemini", [False, False]),
                               (2, "unbranded", "chatgpt", [False, False]), (2, "unbranded", "gemini", [False, False]),
                               (3, "branded", "chatgpt", [True, True]), (3, "branded", "gemini", [True, True])]:
        for h in hits:
            mentions = [{"name": "Summit LED", "key": "summit led", "domain": "summitled.com", "position": 1, "is_target": False}]
            if h:
                mentions.append({"name": "Acme", "key": "acme", "domain": None, "position": 2, "is_target": True})
            rows.append({"query_id": q, "query_kind": kind, "engine": eng, "mentioned": h, "position": 2 if h else None,
                         "linked": False, "n_businesses": len(mentions), "target_mentioned": h, "mentions": mentions,
                         "citations": [{"url": "https://www.yelp.com/biz/x", "title": "Yelp"}]})
    return rows


QUERIES = [{"id": 1, "text": "best led dallas", "kind": "unbranded"}, {"id": 2, "text": "cheap led dallas", "kind": "unbranded"},
           {"id": 3, "text": "is acme good", "kind": "branded"}]


def test_summary_excludes_branded_and_averages_cells():
    s = compute_summary(_rows(), ["chatgpt", "gemini"], QUERIES)
    assert s["overall"]["visibility"] == 25.0  # cells: 1.0, 0, 0, 0
    assert s["per_engine"]["chatgpt"]["visibility"] == 50.0
    assert s["branded"]["mention_rate"] == 1.0
    lo, hi = s["overall"]["ci"]
    assert 0 <= lo <= 25.0 <= hi <= 100


def test_competitors_and_sources():
    rows = _rows()
    comps = aggregate_competitors(rows)
    assert comps[0]["name"] == "Summit LED" and comps[0]["appearance_rate"] == 1.0
    src = analyze_sources(rows, "acme.com", {"summitled.com"})
    assert src[0]["domain"] == "yelp.com" and src[0]["type"] == "reviews"
    assert src[0]["target_in_answers_rate"] == 0.25
    assert classify("summitled.com", "acme.com", {"summitled.com"}) == "competitor"


def test_every_recommendation_has_observed_evidence():
    rows = _rows()
    summary = compute_summary(rows, ["chatgpt", "gemini"], QUERIES)
    src = analyze_sources(rows, "acme.com", {"summitled.com"})
    audit = {"ok": True, "url": "https://acme.com", "checks": {"search_bots_blocked": ["OAI-SearchBot"], "word_count": 100}}
    comp = [{"ok": True, "url": "https://summitled.com", "domain": "summitled.com", "name": "Summit LED",
             "checks": {"local_business_schema": True, "faq": True, "word_count": 1500}}]
    recs = build_recommendations(summary, rows, src, audit, comp)
    assert recs[0]["technique_id"] == "unblock_ai_crawlers"
    assert any(r["technique_id"] == "review_site_presence" for r in recs)
    assert any(r["technique_id"] == "query_content" for r in recs)
    for r in recs:
        assert any(e["kind"] == "observed" for e in r["evidence"])
