"""Utility LLM used for profile inference, query generation and entity extraction.

This is *not* one of the measured engines. It prefers Claude, then OpenAI, then
Gemini, and returns None when neither is configured (or in mock mode) so every
caller has a heuristic path and the product still works offline.
"""

import json
import logging
import re

import anthropic
import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


def available() -> bool:
    s = get_settings()
    return not s.geo_mock and bool(s.anthropic_api_key or s.openai_api_key or s.gemini_api_key)


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


async def complete_json(system: str, user: str, timeout: float = 60.0) -> dict | None:
    """Ask the utility model for a JSON object. Returns None on any failure."""
    s = get_settings()
    if s.geo_mock:
        return None
    try:
        if s.anthropic_api_key:
            return await _claude_json(s.anthropic_api_key, s.claude_utility_model, system, user, timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if s.openai_api_key:
                r = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {s.openai_api_key}"},
                    json={
                        "model": s.utility_model,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    },
                )
                r.raise_for_status()
                return _parse_json(r.json()["choices"][0]["message"]["content"] or "")
            if s.gemini_api_key:
                r = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{s.gemini_model}:generateContent",
                    headers={"x-goog-api-key": s.gemini_api_key},
                    json={
                        "systemInstruction": {"parts": [{"text": system}]},
                        "contents": [{"role": "user", "parts": [{"text": user}]}],
                        "generationConfig": {"responseMimeType": "application/json"},
                    },
                )
                r.raise_for_status()
                parts = r.json()["candidates"][0]["content"]["parts"]
                return _parse_json("".join(p.get("text", "") for p in parts))
    except Exception as e:  # noqa: BLE001 - utility calls are best-effort
        log.warning("utility LLM call failed: %s", e)
    return None


async def _claude_json(api_key: str, model: str, system: str, user: str, timeout: float) -> dict | None:
    async with anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout) as client:
        resp = await client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=system + "\n\nRespond with a single JSON object and nothing else.",
            messages=[{"role": "user", "content": user}],
            # Extraction and profile drafting are simple; low effort keeps them fast.
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    if resp.stop_reason == "refusal":
        log.warning("utility LLM call declined")
        return None
    return _parse_json("".join(b.text for b in resp.content if b.type == "text"))
