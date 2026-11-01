"""Utility LLM used for profile inference, query generation and entity extraction.

This is *not* one of the measured engines. It prefers OpenAI, falls back to
Gemini, and returns None when neither is configured (or in mock mode) so every
caller has a heuristic path and the product still works offline.
"""

import json
import logging
import re

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


def available() -> bool:
    s = get_settings()
    return not s.geo_mock and bool(s.openai_api_key or s.gemini_api_key)


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
