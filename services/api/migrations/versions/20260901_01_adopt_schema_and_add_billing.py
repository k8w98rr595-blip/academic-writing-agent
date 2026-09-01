"""Adopt the existing schema and add the versioned billing foundation.

Revision ID: 20260901_01
Revises: None
Create Date: 2026-09-01
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

from services.api.app import models  # noqa: F401
from services.api.app.database import Base


revision = "20260901_01"
down_revision = None
branch_labels = None
depends_on = None

BILLING_TABLES = (
    "billing_checkout_attempts",
    "document_quota_records",
    "product_usage_reservations",
    "billing_product_events",
    "billing_webhook_events",
    "billing_accounts",
)


def upgrade() -> None:
    # Paperlight predates Alembic. create_all safely adopts existing core tables
    # and creates only missing tables; this revision then becomes the audited
    # baseline for explicit future schema changes.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in BILLING_TABLES:
        if inspect(bind).has_table(table_name):
            op.drop_table(table_name)
