from __future__ import annotations

from dataclasses import replace
from contextlib import closing
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
import subprocess
import sqlite3
import sys
import threading
import uuid

import httpx
import pytest

from services.api.app.config import get_settings
from services.api.app.staging_guard import API_ORIGIN, BASE_PATH, STAGING_ROOT, WEB_ORIGIN, validate_local_staging
from scripts.local_staging import StagingFiles, api_environment, clean_environment, verify_empty_and_remove_smoke_db


def isolated_settings():
    return replace(get_settings(), app_env="local-staging", host="127.0.0.1", port=8100,
                   database_url=f"sqlite:///{(STAGING_ROOT / 'unit/paperlight.db').as_posix()}",
                   object_storage_dir=STAGING_ROOT / "unit/objects", object_storage_mode="local",
                   allowed_origins=(WEB_ORIGIN,), billing_app_url=WEB_ORIGIN + BASE_PATH,
                   job_mode="eager", redis_url="", detector_mode="mock", rewrite_mode="mock",
                   billing_mode="test", owner_email="owner@staging.paperlight.local", require_totp=False,
                   trust_proxy=False, owner_totp_secret="", pangram_api_key="", deepseek_api_key="",
                   stripe_secret_key="", stripe_webhook_secret="", stripe_pro_monthly_price_id="",
                   s3_access_key_id="", s3_secret_access_key="", s3_endpoint_url="",
                   pangram_paid_calls_enabled=False, detector_data_processing_acknowledged=False)


def test_staging_valid_local_configuration():
    validate_local_staging(isolated_settings())


@pytest.mark.parametrize("change", [
    {"host": "0.0.0.0"}, {"port": 8000}, {"allowed_origins": ("https://production.invalid",)},
    {"billing_app_url": "https://production.invalid"},
    {"database_url": "postgresql://production.invalid/db"},
    {"database_url": "sqlite:///./data/paperlight.db"},
    {"database_url": f"sqlite:///{(STAGING_ROOT / '../data/paperlight.db').as_posix()}"},
    {"object_storage_dir": Path("./data/objects")}, {"object_storage_mode": "s3"},
    {"job_mode": "celery"}, {"redis_url": "redis://localhost:6379/0"},
    {"detector_mode": "pangram"}, {"rewrite_mode": "deepseek"},
    {"pangram_paid_calls_enabled": True}, {"detector_data_processing_acknowledged": True},
    {"billing_mode": "stripe"}, {"pangram_api_key": "synthetic-forbidden-value"},
    {"deepseek_api_key": "synthetic-forbidden-value"}, {"stripe_secret_key": "sk_live_placeholder"},
    {"stripe_webhook_secret": "whsec_placeholder"}, {"s3_access_key_id": "synthetic-forbidden-value"},
    {"owner_email": "owner@example.com"}, {"owner_totp_secret": "synthetic-forbidden-value"},
    {"trust_proxy": True},
])
def test_staging_rejects_unsafe_configuration_without_values(change):
    with pytest.raises(RuntimeError) as error:
        validate_local_staging(replace(isolated_settings(), **change))
    assert "synthetic-forbidden-value" not in str(error.value)
    assert "production.invalid" not in str(error.value)
    assert "sk_live_placeholder" not in str(error.value)


def test_launcher_does_not_inherit_secrets_or_network_proxies():
    inherited = {"PATH": "synthetic-path", "SystemRoot": "synthetic-os-path", "DEEPSEEK_API_KEY": "synthetic",
                 "DATABASE_URL": "synthetic", "STRIPE_SECRET_KEY": "synthetic", "HTTP_PROXY": "synthetic",
                 "NODE_OPTIONS": "synthetic", "UNKNOWN_FUTURE_SECRET": "synthetic", "PYTHONPATH": "synthetic"}
    assert clean_environment(inherited) == {"PATH": "synthetic-path", "SystemRoot": "synthetic-os-path"}
    environment = api_environment(STAGING_ROOT / "unit", "synthetic-verifier")
    assert environment["APP_ENV"] == "local-staging"
    assert environment["DETECTOR_MODE"] == environment["REWRITE_MODE"] == "mock"
    assert "STRIPE_SECRET_KEY" not in environment and "DEEPSEEK_API_KEY" not in environment


def test_staging_config_import_never_calls_dotenv():
    environment = clean_environment()
    environment["APP_ENV"] = "local-staging"
    result = subprocess.run([sys.executable, "-c",
        "import dotenv; dotenv.load_dotenv=lambda *a, **k: (_ for _ in ()).throw(RuntimeError('dotenv was read')); "
        "import services.api.app.config; print('isolated')"],
        env=environment, capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.strip() == "isolated"


def test_cleanup_refuses_non_smoke_and_external_directories():
    for directory in (STAGING_ROOT / "local", STAGING_ROOT.parent / "data"):
        with pytest.raises(RuntimeError, match="Refusing cleanup"):
            verify_empty_and_remove_smoke_db(directory)


def test_staging_http_rejects_rebinding_and_foreign_origins(client, monkeypatch):
    from services.api.app import main
    monkeypatch.setattr(main, "settings", isolated_settings())
    assert client.get("/api/health").status_code == 403
    assert client.get("/api/health", headers={"Host": "127.0.0.1:8100", "Origin": "https://foreign.invalid"}).status_code == 403
    health = client.get("/api/health", headers={"Host": "127.0.0.1:8100", "Origin": WEB_ORIGIN})
    assert health.status_code == 200 and health.json()["environment"] == "local-staging"


def test_launcher_paths_cannot_escape_staging():
    with pytest.raises(RuntimeError):
        api_environment(STAGING_ROOT.parent / "data", "synthetic")


def test_static_server_limits_host_paths_and_connections(tmp_path):
    (tmp_path / "index.html").write_text("<h1>isolated</h1>", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(StagingFiles, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False) as client:
            assert client.get(BASE_PATH + "/").status_code == 403
            client.headers["Host"] = "127.0.0.1:3100"
            page = client.get(BASE_PATH + "/")
            assert page.status_code == 200 and "isolated" in page.text
            assert API_ORIGIN in page.headers["Content-Security-Policy"]
            assert "https:" not in page.headers["Content-Security-Policy"]
            assert client.get("/").headers["Location"] == BASE_PATH + "/"
            assert client.get("/config.js").status_code == 404
            assert client.get(BASE_PATH + "/%2e%2e/.env.local").status_code == 404
            assert client.head(BASE_PATH + "/").status_code == 405
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_synthetic_cleanup_closes_sqlite_before_unlinking():
    run_dir = STAGING_ROOT / ("smoke-unit-" + uuid.uuid4().hex)
    (run_dir / "objects").mkdir(parents=True)
    with closing(sqlite3.connect(run_dir / "paperlight.db")) as connection:
        for table in ("documents", "document_versions", "analysis_runs", "rewrite_sessions", "patches", "jobs", "sessions", "provider_usage_events"):
            connection.execute(f"CREATE TABLE {table} (id TEXT)")
        connection.commit()
    verify_empty_and_remove_smoke_db(run_dir)
    assert not run_dir.exists()
