from __future__ import annotations

from sqlalchemy import create_engine, inspect

from services.api.app.migration_runner import downgrade_database, upgrade_database


def test_billing_migration_is_repeatable_and_reversible(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'migration.db').as_posix()}")
    upgrade_database(engine)
    upgrade_database(engine)
    tables = set(inspect(engine).get_table_names())
    assert {
        "alembic_version",
        "billing_accounts",
        "billing_checkout_attempts",
        "billing_webhook_events",
        "billing_product_events",
        "document_quota_records",
        "product_usage_reservations",
        "documents",
    } <= tables

    downgrade_database(engine)
    downgraded = set(inspect(engine).get_table_names())
    assert "documents" in downgraded
    assert "billing_accounts" not in downgraded
    assert "billing_checkout_attempts" not in downgraded
