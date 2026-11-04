from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings come from environment variables (or backend/.env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./geo.db"
    cors_origins: str = "http://localhost:3000"

    # Engine credentials. An engine is enabled when its key is present.
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    perplexity_api_key: str | None = None
    # Gemini grounding: "google" (Google Search grounding, needs grounding quota) or
    # "tavily" (Tavily web search fed to plain Gemini; works on free Gemini keys).
    gemini_grounding: str = "google"
    tavily_api_key: str | None = None

    # GEO_MOCK=1 replaces every engine and the utility LLM with offline fakes,
    # so the whole product can be run and demoed without API keys.
    geo_mock: bool = False

    # Models. These move fast; override via env rather than editing code.
    chatgpt_model: str = "gpt-5-mini"  # used with the web_search tool
    claude_model: str = "claude-opus-5"  # used with the web_search tool
    gemini_model: str = "gemini-2.5-flash"  # used with Google Search grounding
    perplexity_model: str = "sonar"
    utility_model: str = "gpt-5-mini"  # profile inference, query gen, extraction (OpenAI)
    claude_utility_model: str = "claude-opus-5"  # the same jobs when Claude is the utility model

    # Measurement defaults.
    samples_per_query: int = 5
    engine_concurrency: int = 4
    request_timeout_s: float = 90.0

    # Scheduler: how often the loop checks for businesses due a re-check.
    scheduler_enabled: bool = True
    scheduler_poll_s: int = 60
    default_recheck_days: int = 7

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
