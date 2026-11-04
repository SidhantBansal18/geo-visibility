from app.config import get_settings
from app.pipeline.engines.base import AskContext, Engine, EngineAnswer
from app.pipeline.engines.claude import ClaudeSearch
from app.pipeline.engines.live import configured_engines
from app.pipeline.engines.mock import mock_engines

ENGINE_LABELS = {"chatgpt": "ChatGPT", "claude": "Claude", "gemini": "Gemini", "perplexity": "Perplexity"}


def get_engines() -> dict[str, Engine]:
    """Engines available right now: all mocks in GEO_MOCK mode, else those with keys."""
    s = get_settings()
    if s.geo_mock:
        return mock_engines()
    engines = configured_engines()
    if s.anthropic_api_key:
        engines["claude"] = ClaudeSearch(s.anthropic_api_key, s.claude_model)
    return engines


__all__ = ["AskContext", "Engine", "EngineAnswer", "ENGINE_LABELS", "get_engines"]
