from typing import Literal

from pydantic import BaseModel, Field, field_validator

QueryKind = Literal["unbranded", "use_case", "comparison", "branded"]


class InferIn(BaseModel):
    url: str = Field(min_length=3, max_length=500)


class SuggestQueriesIn(BaseModel):
    name: str
    category: str
    location: str
    description: str = ""


class QueryIn(BaseModel):
    id: int | None = None
    text: str = Field(min_length=3, max_length=500)
    kind: QueryKind = "unbranded"
    active: bool = True


class BusinessIn(BaseModel):
    url: str = Field(min_length=3, max_length=500)
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=255)
    location: str = Field(min_length=1, max_length=255)
    description: str = ""
    aliases: list[str] = []
    queries: list[QueryIn] = Field(min_length=1, max_length=30)
    recheck_enabled: bool = True
    recheck_days: int = Field(default=7, ge=1, le=90)
    run_now: bool = True
    engines: list[str] | None = None
    samples_per_query: int | None = Field(default=None, ge=1, le=20)

    @field_validator("aliases")
    @classmethod
    def _clean_aliases(cls, v: list[str]) -> list[str]:
        return [a.strip() for a in v if a and a.strip()][:10]


class BusinessPatch(BaseModel):
    name: str | None = None
    category: str | None = None
    location: str | None = None
    description: str | None = None
    aliases: list[str] | None = None
    recheck_enabled: bool | None = None
    recheck_days: int | None = Field(default=None, ge=1, le=90)


class RunIn(BaseModel):
    engines: list[str] | None = None
    samples_per_query: int | None = Field(default=None, ge=1, le=20)


class RecommendationPatch(BaseModel):
    done: bool
