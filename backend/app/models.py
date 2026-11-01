from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    # Naive UTC everywhere: SQLite does not store tz offsets, and mixing aware and
    # naive datetimes breaks comparisons in the scheduler.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    # owner_id is reserved for multi-tenancy; single-user mode leaves it null.
    owner_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    url: Mapped[str] = mapped_column(String(500))
    domain: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(255))
    location: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")

    recheck_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    recheck_days: Mapped[int] = mapped_column(Integer, default=7)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)

    queries: Mapped[list["Query"]] = relationship(
        back_populates="business", cascade="all, delete-orphan", order_by="Query.id"
    )
    runs: Mapped[list["Run"]] = relationship(
        back_populates="business", cascade="all, delete-orphan", order_by="Run.id"
    )


class Query(Base):
    __tablename__ = "queries"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    # unbranded | use_case | comparison | branded
    kind: Mapped[str] = mapped_column(String(32), default="unbranded")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)

    business: Mapped[Business] = relationship(back_populates="queries")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    # queued | running | done | failed
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual | scheduled
    engines: Mapped[list[str]] = mapped_column(JSON, default=list)
    samples_per_query: Mapped[int] = mapped_column(Integer, default=5)
    progress_done: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(64), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Computed results, stored denormalised so the dashboard is one read.
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    competitors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_gaps: Mapped[list | None] = mapped_column(JSON, nullable=True)
    site_audit: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    competitor_audits: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    business: Mapped[Business] = relationship(back_populates="runs")
    responses: Mapped[list["Response"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Response.id"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Recommendation.rank"
    )


class Response(Base):
    """One answer from one engine to one query (one sample)."""

    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    query_id: Mapped[int | None] = mapped_column(ForeignKey("queries.id", ondelete="SET NULL"), nullable=True)
    query_text: Mapped[str] = mapped_column(Text)  # snapshot: queries can be edited later
    query_kind: Mapped[str] = mapped_column(String(32))
    engine: Mapped[str] = mapped_column(String(32), index=True)
    sample: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Target-business outcome for this answer.
    target_mentioned: Mapped[bool] = mapped_column(Boolean, default=False)
    target_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_linked: Mapped[bool] = mapped_column(Boolean, default=False)

    run: Mapped[Run] = relationship(back_populates="responses")
    mentions: Mapped[list["Mention"]] = relationship(
        back_populates="response", cascade="all, delete-orphan", order_by="Mention.position"
    )
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="response", cascade="all, delete-orphan", order_by="Citation.position"
    )


class Mention(Base):
    """A business named in a response, in order of appearance."""

    __tablename__ = "mentions"

    id: Mapped[int] = mapped_column(primary_key=True)
    response_id: Mapped[int] = mapped_column(ForeignKey("responses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    key: Mapped[str] = mapped_column(String(255), index=True)  # normalised identity for grouping
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[int] = mapped_column(Integer)
    is_target: Mapped[bool] = mapped_column(Boolean, default=False)
    linked: Mapped[bool] = mapped_column(Boolean, default=False)

    response: Mapped[Response] = relationship(back_populates="mentions")


class Citation(Base):
    """A source URL the engine cited for a response."""

    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(primary_key=True)
    response_id: Mapped[int] = mapped_column(ForeignKey("responses.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer)

    response: Mapped[Response] = relationship(back_populates="citations")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    priority: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(32))  # source_gap | site | content
    title: Mapped[str] = mapped_column(Text)
    detail: Mapped[str] = mapped_column(Text)
    technique_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # [{"label": str, "url": str | None, "kind": "observed" | "reference"}]
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    done: Mapped[bool] = mapped_column(Boolean, default=False)

    run: Mapped[Run] = relationship(back_populates="recommendations")
