from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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


class ProviderUsageEvent(Base):
    """Content-free accounting for outbound provider calls.

    This table deliberately excludes paper text, prompts, provider response bodies,
    credentials, session tokens, and raw idempotency values.
    """

    __tablename__ = "provider_usage_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_email: Mapped[str] = mapped_column(String(320), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    operation: Mapped[str] = mapped_column(String(64), index=True)
    model_version: Mapped[str] = mapped_column(String(128), default="")
    idempotency_hash: Mapped[str] = mapped_column(String(64), index=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="reserved", index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    __table_args__ = (
        Index("ix_provider_usage_owner_provider_created", "owner_email", "provider", "created_at"),
    )


class BillingAccount(Base):
    """Provider-neutral billing identity and the currently materialized plan."""

    __tablename__ = "billing_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    plan_key: Mapped[str] = mapped_column(String(32), default="free", index=True)
    plan_source: Mapped[str] = mapped_column(String(32), default="default")
    subscription_status: Mapped[str] = mapped_column(String(32), default="none", index=True)
    provider: Mapped[str] = mapped_column(String(32), default="")
    provider_customer_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    provider_price_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    last_provider_event_created: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    last_provider_event_rank: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)


class BillingCheckoutAttempt(Base):
    """One durable, replay-safe Checkout slot per billing account."""

    __tablename__ = "billing_checkout_attempts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    billing_account_id: Mapped[str] = mapped_column(
        ForeignKey("billing_accounts.id", ondelete="CASCADE"), index=True
    )
    attempt_token: Mapped[str] = mapped_column(String(64), unique=True)
    price_id: Mapped[str] = mapped_column(String(128))
    provider_session_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="creating", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)


class ProductUsageReservation(Base):
    """Idempotent, content-free reservations for customer-visible quota meters."""

    __tablename__ = "product_usage_reservations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_email: Mapped[str] = mapped_column(String(320), index=True)
    meter: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_hash: Mapped[str] = mapped_column(String(64))
    period_start: Mapped[datetime] = mapped_column(DateTime(), index=True)
    status: Mapped[str] = mapped_column(String(24), default="reserved", index=True)
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    __table_args__ = (
        UniqueConstraint("owner_email", "meter", "idempotency_hash", name="uq_product_usage_idempotency"),
        Index("ix_product_usage_owner_meter_period", "owner_email", "meter", "period_start"),
    )


class DocumentQuotaRecord(Base):
    """Billable current-document bytes; immutable system history is excluded."""

    __tablename__ = "document_quota_records"

    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    owner_email: Mapped[str] = mapped_column(String(320), index=True)
    content_bytes: Mapped[int] = mapped_column(Integer, default=0)
    original_bytes: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)


class BillingWebhookEvent(Base):
    """Replay-safe Stripe event ledger without full payment payloads."""

    __tablename__ = "billing_webhook_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="processing", index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider_created_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)


class BillingProductEvent(Base):
    """Low-cardinality upgrade-funnel telemetry, never document content."""

    __tablename__ = "billing_product_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_email: Mapped[str] = mapped_column(String(320), index=True)
    event_name: Mapped[str] = mapped_column(String(64), index=True)
    trigger: Mapped[str] = mapped_column(String(80), default="")
    plan_key: Mapped[str] = mapped_column(String(32), default="free")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, index=True)

    __table_args__ = (Index("ix_billing_product_owner_event_created", "owner_email", "event_name", "created_at"),)
