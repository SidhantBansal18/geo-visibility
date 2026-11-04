"""Claude with Anthropic's server-side web search, the search-grounded mode
Claude users get when web search is on."""

import anthropic
import httpx

from app.pipeline.engines.base import AskContext, EngineAnswer

# A paused server-tool turn can be resumed; cap it so one question can't loop.
MAX_CONTINUATIONS = 3


class ClaudeSearch:
    id = "claude"
    label = "Claude"

    def __init__(self, api_key: str, model: str, timeout: float = 180.0):
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=4)

    async def ask(self, query: str, ctx: AskContext, client: httpx.AsyncClient) -> EngineAnswer:
        tool: dict = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}
        if ctx.city or ctx.region:
            tool["user_location"] = {
                "type": "approximate",
                "country": ctx.country or "US",
                **({"city": ctx.city} if ctx.city else {}),
                **({"region": ctx.region} if ctx.region else {}),
            }
        messages: list[dict] = [{"role": "user", "content": query}]
        content: list = []
        for _ in range(MAX_CONTINUATIONS + 1):
            resp = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                tools=[tool],
                messages=messages,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            if resp.stop_reason == "refusal":
                category = resp.stop_details.category if resp.stop_details else None
                raise RuntimeError(f"Claude declined to answer (category: {category})")
            content.extend(resp.content)
            if resp.stop_reason != "pause_turn":
                break
            messages = [messages[0], {"role": "assistant", "content": content}]
        return parse_claude_content(content)


def _get(obj, key: str):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def parse_claude_content(content: list) -> EngineAnswer:
    """Answer text plus the pages it cites, in citation order. Falls back to every
    search result when the answer carries no inline citations."""
    texts: list[str] = []
    cites: list[dict] = []
    results: list[dict] = []
    seen: set[str] = set()
    for block in content:
        kind = _get(block, "type")
        if kind == "text":
            texts.append(_get(block, "text") or "")
            for c in _get(block, "citations") or []:
                url = _get(c, "url")
                if url and url not in seen:
                    seen.add(url)
                    cites.append({"url": url, "title": _get(c, "title")})
        elif kind == "web_search_tool_result":
            found = _get(block, "content")
            # A list of results on success; a single error object otherwise.
            if isinstance(found, list):
                results.extend({"url": _get(r, "url"), "title": _get(r, "title")} for r in found if _get(r, "url"))
    if not cites:
        for r in results:
            if r["url"] not in seen:
                seen.add(r["url"])
                cites.append(r)
    return EngineAnswer(text="".join(texts).strip(), citations=cites)
