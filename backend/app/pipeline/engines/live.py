"""Real engines, each called in its *search-grounded* mode so results reflect what
consumers see in the product, not the model's offline memory."""

import asyncio
import re

import httpx

from app.config import get_settings
from app.pipeline.engines.base import AskContext, EngineAnswer


class ChatGPTSearch:
    """OpenAI Responses API with the web_search tool (what ChatGPT search uses)."""

    id = "chatgpt"
    label = "ChatGPT"

    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model

    async def ask(self, query: str, ctx: AskContext, client: httpx.AsyncClient) -> EngineAnswer:
        tool: dict = {"type": "web_search"}
        if ctx.city or ctx.region:
            tool["user_location"] = {
                "type": "approximate",
                "country": ctx.country or "US",
                **({"city": ctx.city} if ctx.city else {}),
                **({"region": ctx.region} if ctx.region else {}),
            }
        r = await client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": query, "tools": [tool]},
        )
        r.raise_for_status()
        return parse_openai_response(r.json())


def parse_openai_response(data: dict) -> EngineAnswer:
    texts: list[str] = []
    cites: list[dict] = []
    seen: set[str] = set()
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for c in item.get("content", []):
            if c.get("type") != "output_text":
                continue
            texts.append(c.get("text", ""))
            for a in c.get("annotations", []) or []:
                url = a.get("url")
                if a.get("type") == "url_citation" and url and url not in seen:
                    seen.add(url)
                    cites.append({"url": url, "title": a.get("title")})
    return EngineAnswer(text="\n".join(texts).strip(), citations=cites)


class GeminiGrounded:
    """Gemini with Google Search grounding."""

    id = "gemini"
    label = "Gemini"

    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model

    async def ask(self, query: str, ctx: AskContext, client: httpx.AsyncClient) -> EngineAnswer:
        r = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            json={"contents": [{"role": "user", "parts": [{"text": query}]}], "tools": [{"google_search": {}}]},
        )
        r.raise_for_status()
        ans = parse_gemini_response(r.json())
        ans.citations = [await _resolve_redirect(c, client) for c in ans.citations]
        return ans


def parse_gemini_response(data: dict) -> EngineAnswer:
    cands = data.get("candidates") or []
    if not cands:
        return EngineAnswer(text="")
    cand = cands[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    cites, seen = [], set()
    for ch in (cand.get("groundingMetadata") or {}).get("groundingChunks", []) or []:
        web = ch.get("web") or {}
        uri = web.get("uri")
        if uri and uri not in seen:
            seen.add(uri)
            # Gemini returns a redirect URI; title is usually the source domain.
            cites.append({"url": uri, "title": web.get("title")})
    return EngineAnswer(text=text.strip(), citations=cites)


async def _resolve_redirect(c: dict, client: httpx.AsyncClient) -> dict:
    if "grounding-api-redirect" not in c["url"]:
        return c
    try:
        r = await client.get(c["url"], follow_redirects=False, timeout=10)
        loc = r.headers.get("location")
        if loc:
            return {"url": loc, "title": c.get("title")}
    except Exception:  # noqa: BLE001 - keep the redirect URL
        pass
    return c


TAVILY_PROMPT = """Answer the user's question as a helpful assistant would, using the web search
results below. When you name a business or rely on a fact, cite the result it came from as [n].
Do not invent businesses that the results do not support.

Search results:
{sources}

Question: {query}"""


class GeminiTavily:
    """Gemini grounded on Tavily web search instead of Google Search grounding,
    for keys without grounding quota (e.g. the free tier). Approximates, but is not,
    what Gemini users see: the search index and ranking differ."""

    id = "gemini"
    label = "Gemini (Tavily search)"

    def __init__(self, api_key: str, model: str, tavily_key: str):
        self.api_key, self.model, self.tavily_key = api_key, model, tavily_key
        # One search per question per process, shared across samples, to save search credits.
        self._searches: dict[str, asyncio.Task] = {}

    async def _search(self, query: str, client: httpx.AsyncClient) -> list[dict]:
        r = await client.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {self.tavily_key}"},
            json={"query": query, "max_results": 8, "search_depth": "basic", "country": "united states"},
        )
        r.raise_for_status()
        return [x for x in r.json().get("results", []) if x.get("url")]

    async def search(self, query: str, client: httpx.AsyncClient) -> list[dict]:
        task = self._searches.get(query)
        if task is None or (task.done() and task.exception()):
            task = self._searches[query] = asyncio.create_task(self._search(query, client))
        return await task

    async def ask(self, query: str, ctx: AskContext, client: httpx.AsyncClient) -> EngineAnswer:
        results = await self.search(query, client)
        sources = "\n\n".join(
            f"[{i}] {x.get('title') or ''}\n{x['url']}\n{(x.get('content') or '')[:1500]}"
            for i, x in enumerate(results, 1)
        )
        r = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            json={"contents": [{"role": "user", "parts": [{"text": TAVILY_PROMPT.format(sources=sources, query=query)}]}]},
        )
        r.raise_for_status()
        ans = parse_gemini_response(r.json())
        ans.citations = cited_results(ans.text, results)
        return ans


def cited_results(text: str, results: list[dict]) -> list[dict]:
    """Results the answer cites as [n], in citation order; all results if it cites none."""
    order: list[int] = []
    for m in re.finditer(r"\[(\d+(?:\s*,\s*\d+)*)\]", text):
        for n in m.group(1).split(","):
            k = int(n) - 1
            if 0 <= k < len(results) and k not in order:
                order.append(k)
    picked = [results[k] for k in order] if order else results
    return [{"url": x["url"], "title": x.get("title")} for x in picked]


class PerplexitySonar:
    id = "perplexity"
    label = "Perplexity"

    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model

    async def ask(self, query: str, ctx: AskContext, client: httpx.AsyncClient) -> EngineAnswer:
        r = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": [{"role": "user", "content": query}]},
        )
        r.raise_for_status()
        return parse_perplexity_response(r.json())


def parse_perplexity_response(data: dict) -> EngineAnswer:
    text = data["choices"][0]["message"]["content"]
    cites: list[dict] = []
    results = data.get("search_results") or []
    if results:
        cites = [{"url": s["url"], "title": s.get("title")} for s in results if s.get("url")]
    else:
        cites = [{"url": u, "title": None} for u in data.get("citations") or []]
    return EngineAnswer(text=text.strip(), citations=cites)


def configured_engines() -> dict:
    s = get_settings()
    out: dict = {}
    if s.openai_api_key:
        out["chatgpt"] = ChatGPTSearch(s.openai_api_key, s.chatgpt_model)
    if s.gemini_api_key and s.gemini_grounding == "tavily" and s.tavily_api_key:
        out["gemini"] = GeminiTavily(s.gemini_api_key, s.gemini_model, s.tavily_api_key)
    elif s.gemini_api_key:
        out["gemini"] = GeminiGrounded(s.gemini_api_key, s.gemini_model)
    if s.perplexity_api_key:
        out["perplexity"] = PerplexitySonar(s.perplexity_api_key, s.perplexity_model)
    return out
