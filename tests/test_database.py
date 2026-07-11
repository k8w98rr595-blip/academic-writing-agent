from services.api.app.database import _normalize_database_url


def test_normalize_railway_postgres_url_uses_psycopg_v3():
    assert _normalize_database_url("postgresql://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    assert _normalize_database_url("postgres://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"


def test_normalize_database_url_preserves_explicit_driver_and_sqlite():
    assert _normalize_database_url("postgresql+psycopg://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    assert _normalize_database_url("sqlite:///paperlight.db") == "sqlite:///paperlight.db"
