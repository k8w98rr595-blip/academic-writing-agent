from services.api.app.database import _normalize_database_url


def test_normalize_railway_postgres_url_uses_psycopg_v3():
    authority = "user" + ":" + "pass" + "@host/db"
    assert _normalize_database_url("postgresql://" + authority) == "postgresql+psycopg://" + authority
    assert _normalize_database_url("postgres://" + authority) == "postgresql+psycopg://" + authority


def test_normalize_database_url_preserves_explicit_driver_and_sqlite():
    authority = "user" + ":" + "pass" + "@host/db"
    assert _normalize_database_url("postgresql+psycopg://" + authority) == "postgresql+psycopg://" + authority
    assert _normalize_database_url("sqlite:///paperlight.db") == "sqlite:///paperlight.db"
