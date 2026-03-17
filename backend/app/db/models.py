"""SQLAlchemy models."""
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Case(Base):
    """Case-level header information for investigations."""

    __tablename__ = "cases"

    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    case_brief_text: Mapped[str] = mapped_column(Text, nullable=False)
    brief_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True
    )
    target_subject_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    crime_timestamp_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    crime_timestamp_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # For now, store coordinates in additional_metadata/evidence; ORM does not
    # model PostGIS geography directly here to avoid an extra dependency.
    # The column still exists in SQL for future geo queries.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")

    evidence_chunks: Mapped[list["EvidenceChunk"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    briefs: Mapped[list["CaseBrief"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class CaseBrief(Base):
    """A case summary/brief variant for a case. Cases can have multiple briefs."""

    __tablename__ = "case_briefs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("cases.case_id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, default="Case Summary")
    brief_text: Mapped[str] = mapped_column(Text, nullable=False)
    brief_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True
    )
    source_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    case: Mapped["Case"] = relationship(back_populates="briefs")


class EvidenceChunk(Base):
    """Evidence chunk for RAG retrieval."""

    __tablename__ = "evidence_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    reliability_score: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False
    )
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_document: Mapped[str | None] = mapped_column(nullable=True)
    additional_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    case_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("cases.case_id"), nullable=True
    )

    case: Mapped[Case | None] = relationship(back_populates="evidence_chunks")


class InvestigationLog(Base):
    """Persisted investigation run containing full pipeline results."""

    __tablename__ = "investigation_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("cases.case_id"), nullable=False
    )
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    effort_level: Mapped[str] = mapped_column(String(10), nullable=False, default="low")
    verdict: Mapped[str] = mapped_column(String(50), nullable=False)
    result_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    case: Mapped[Case] = relationship()

class InvestigationTrace(Base):
    """Persisted trace record capturing graph execution decisions."""

    __tablename__ = "investigation_traces"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("cases.case_id"), nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    trace_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    case: Mapped[Case] = relationship()
