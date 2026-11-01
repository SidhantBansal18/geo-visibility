from dataclasses import dataclass, field
from typing import Protocol

import httpx


@dataclass
class AskContext:
    """What an engine may know about the simulated user (location) and, for the
    mock engine only, about the business being measured."""

    city: str = ""
    region: str = ""
    country: str = "US"
    # Mock-only fields:
    business_name: str = ""
    business_domain: str = ""
    category: str = ""
    location: str = ""


@dataclass
class EngineAnswer:
    text: str
    citations: list[dict] = field(default_factory=list)  # [{"url", "title"}]


class Engine(Protocol):
    id: str
    label: str

    async def ask(self, query: str, ctx: AskContext, client: httpx.AsyncClient) -> EngineAnswer: ...
