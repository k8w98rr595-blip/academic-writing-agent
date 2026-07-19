from __future__ import annotations

import os
from pathlib import Path

import pytest


TEST_ROOT = Path(__file__).resolve().parent / ".runtime"
TEST_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": f"sqlite:///{(TEST_ROOT / 'paperlight-test.db').as_posix()}",
        "OBJECT_STORAGE_DIR": str(TEST_ROOT / "objects"),
        "OBJECT_STORAGE_MODE": "local",
        "OWNER_EMAIL": "owner@example.com",
        "REQUIRE_TOTP": "0",
        "DETECTOR_MODE": "mock",
        "DETECTOR_DATA_PROCESSING_ACKNOWLEDGED": "0",
        "PANGRAM_API_URL": "https://text.external-api.pangram.com",
        "REWRITE_MODE": "mock",
        "ALLOWED_ORIGINS": "http://testserver",
    }
)

from argon2 import PasswordHasher  # noqa: E402

os.environ["OWNER_PASSWORD_HASH"] = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash("correct horse battery staple")

from fastapi.testclient import TestClient  # noqa: E402
from services.api.app.database import Base, engine  # noqa: E402
from services.api.app.main import app  # noqa: E402
from services.api.app.security import login_limiter  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    with login_limiter._lock:
        login_limiter._events.clear()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery staple", "totp_code": ""},
    )
    assert response.status_code == 200, response.text
    return response.json()["session_token"]


@pytest.fixture()
def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def coursework_text() -> str:
    sentence = "It is important to note that ethical data reuse requires consent, purpose limitation, careful governance, and accountable review. "
    return "Introduction\n\n" + sentence * 75
