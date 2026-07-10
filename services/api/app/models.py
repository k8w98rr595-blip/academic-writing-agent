from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    # Store naive UTC consistently across SQLite and PostgreSQL to avoid
    # driver-specific timezone coercion during expiry checks.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    owner_email: Mapped[str] = mapped_column(String(320), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_email: Mapped[str] = mapped_column(String(320), index=True)
    title: Mapped[str] = mapped_column(String(180))
    current_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(), index=True)


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    paragraphs: Mapped[list[dict]] = mapped_column(JSON)
    word_count: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    parent_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)

    __table_args__ = (Index("ix_versions_document_number", "document_id", "version_number", unique=True),)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    provider_mode: Mapped[str] = mapped_column(String(40))
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)


class RewriteSession(Base):
    __tablename__ = "rewrite_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)


class PatchRecord(Base):
    __tablename__ = "patches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rewrite_session_id: Mapped[str] = mapped_column(ForeignKey("rewrite_sessions.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    base_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    paragraph_id: Mapped[str] = mapped_column(String(64))
    original_text: Mapped[str] = mapped_column(Text)
    revised_text: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(500))
    protected_status: Mapped[str] = mapped_column(String(80), default="preserved")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)


class JobRecord(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_email: Mapped[str] = mapped_column(String(320), index=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    job_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    result_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor: Mapped[str] = mapped_column(String(320), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_id: Mapped[str] = mapped_column(String(64), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
