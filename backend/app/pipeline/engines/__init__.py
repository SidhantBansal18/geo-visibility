from app.config import get_settings
from app.pipeline.engines.base import AskContext, Engine, EngineAnswer
from app.pipeline.engines.live import configured_engines
from app.pipeline.engines.mock import mock_engines

ENGINE_LABELS = {"chatgpt": "ChatGPT", "gemini": "Gemini", "perplexity": "Perplexity"}


def get_engines() -> dict[str, Engine]:
    """Engines available right now: all mocks in GEO_MOCK mode, else those with keys."""
    if get_settings().geo_mock:
        return mock_engines()
    return configured_engines()


__all__ = ["AskContext", "Engine", "EngineAnswer", "ENGINE_LABELS", "get_engines"]
