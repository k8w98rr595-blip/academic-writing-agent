from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException

from services.api.app.config import get_settings
from services.api.app.database import session_scope
from services.api.app.models import ProviderUsageEvent, utcnow
from services.api.app.provider_usage import (
    ProviderCallSpec,
    cancel_unused_reservations,
    claim_provider_call,
    finalize_provider_call,
    provider_usage_summary,
    reserve_provider_calls,
)


OWNER = "owner@example.com"


def _spec(operation: str, key: str) -> ProviderCallSpec:
    return ProviderCallSpec(operation, "synthetic-model", key)


def test_usage_summary_is_owner_only_and_empty_by_default(client, headers):
    assert client.get("/api/v1/provider-usage/summary").status_code == 401
    response = client.get("/api/v1/provider-usage/summary", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["periods"]["hour"]["calls"] == 0
    assert payload["limits"]["hourlyHardLimit"] == 20
    assert "bill" in payload["disclaimer"].lower()


def test_usage_reservation_persists_only_hashed_idempotency_and_operational_metadata():
    raw_key = "synthetic-document-text-must-not-be-stored"
    reservation = reserve_provider_calls(OWNER, "DeepSeek", [_spec("rewrite", raw_key)])["rewrite"]
    finalize_provider_call(
        reservation,
        final_status="success",
        latency_ms=25,
        input_units=120,
        output_units=35,
    )
    with session_scope() as db:
        event = db.get(ProviderUsageEvent, reservation)
        assert event is not None
        assert event.idempotency_hash != raw_key
        assert raw_key not in repr(event.__dict__)
        assert event.input_units == 120
        assert event.output_units == 35
        assert not any(name in event.__table__.columns for name in ("text", "prompt", "response", "api_key"))


def test_duplicate_paid_call_is_rejected_but_cancelled_reservation_can_be_retried():
    first = reserve_provider_calls(OWNER, "DeepSeek", [_spec("rewrite", "same")])["rewrite"]
    with pytest.raises(HTTPException) as duplicate:
        reserve_provider_calls(OWNER, "DeepSeek", [_spec("rewrite", "same")])
    assert duplicate.value.status_code == 409
    cancel_unused_reservations([first])
    second = reserve_provider_calls(OWNER, "DeepSeek", [_spec("rewrite", "same")])["rewrite"]
    assert second != first


def test_worker_reservation_can_be_claimed_only_once_and_then_finalized():
    reservation = reserve_provider_calls(OWNER, "Pangram", [_spec("detection", "queued")])["detection"]
    assert claim_provider_call(reservation) is True
    assert claim_provider_call(reservation) is False
    finalize_provider_call(reservation, final_status="outcome_unknown", error_code="worker_interrupted")
    with session_scope() as db:
        event = db.get(ProviderUsageEvent, reservation)
        assert event is not None
        assert event.status == "outcome_unknown"


def test_pangram_concurrency_lock_allows_only_one_active_detection():
    active = reserve_provider_calls(OWNER, "Pangram", [_spec("detection", "content-one")])["detection"]
    with pytest.raises(HTTPException) as blocked:
        reserve_provider_calls(OWNER, "Pangram", [_spec("detection", "content-two")])
    assert blocked.value.status_code == 409
    finalize_provider_call(active, final_status="success")
    next_reservation = reserve_provider_calls(OWNER, "Pangram", [_spec("detection", "content-two")])
    assert next_reservation["detection"]


def test_pangram_same_content_is_blocked_for_24_hours():
    first = reserve_provider_calls(OWNER, "Pangram", [_spec("detection", "same-content-hash")])["detection"]
    finalize_provider_call(first, final_status="success")
    with pytest.raises(HTTPException) as duplicate:
        reserve_provider_calls(OWNER, "Pangram", [_spec("detection", "same-content-hash")])
    assert duplicate.value.status_code == 409
    assert "within 24 hours" in str(duplicate.value.detail)


def test_pangram_failed_local_validation_still_blocks_same_content_for_24_hours():
    first = reserve_provider_calls(OWNER, "Pangram", [_spec("detection", "failed-content-hash")])[
        "detection"
    ]
    finalize_provider_call(first, final_status="failed", error_code="range_mismatch")

    with pytest.raises(HTTPException) as duplicate:
        reserve_provider_calls(OWNER, "Pangram", [_spec("detection", "failed-content-hash")])

    assert duplicate.value.status_code == 409
    assert "within 24 hours" in str(duplicate.value.detail)


def test_pangram_daily_limit_counts_completed_calls(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PANGRAM_HOURLY_WARNING", "1")
    monkeypatch.setenv("PANGRAM_HOURLY_HARD_LIMIT", "2")
    monkeypatch.setenv("PANGRAM_DAILY_HARD_LIMIT", "2")
    get_settings.cache_clear()
    try:
        ids = []
        for index in range(2):
            reservation = reserve_provider_calls(
                OWNER, "Pangram", [_spec("detection", f"daily-{index}")]
            )["detection"]
            finalize_provider_call(reservation, final_status="success")
            ids.append(reservation)
        with session_scope() as db:
            for reservation in ids:
                event = db.get(ProviderUsageEvent, reservation)
                assert event is not None
                event.created_at = utcnow() - timedelta(hours=2)
        with pytest.raises(HTTPException) as blocked:
            reserve_provider_calls(OWNER, "Pangram", [_spec("detection", "daily-blocked")])
        assert blocked.value.status_code == 429
        assert "Daily Pangram" in str(blocked.value.detail)
    finally:
        monkeypatch.delenv("PANGRAM_HOURLY_WARNING", raising=False)
        monkeypatch.delenv("PANGRAM_HOURLY_HARD_LIMIT", raising=False)
        monkeypatch.delenv("PANGRAM_DAILY_HARD_LIMIT", raising=False)
        get_settings.cache_clear()


def test_hourly_warning_and_hard_limit_are_enforced(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PAID_CALL_HOURLY_WARNING", "1")
    monkeypatch.setenv("PAID_CALL_HOURLY_HARD_LIMIT", "2")
    get_settings.cache_clear()
    try:
        reservations = reserve_provider_calls(
            OWNER,
            "DeepSeek",
            [_spec("rewrite", "one"), _spec("validation", "two")],
        )
        for reservation in reservations.values():
            finalize_provider_call(reservation, final_status="success")
        with session_scope() as db:
            summary = provider_usage_summary(db, OWNER)
        assert summary["periods"]["hour"]["calls"] == 2
        assert summary["warnings"]
        with pytest.raises(HTTPException) as blocked:
            reserve_provider_calls(OWNER, "Pangram", [_spec("detection", "three")])
        assert blocked.value.status_code == 429
    finally:
        monkeypatch.delenv("PAID_CALL_HOURLY_WARNING", raising=False)
        monkeypatch.delenv("PAID_CALL_HOURLY_HARD_LIMIT", raising=False)
        get_settings.cache_clear()


def test_five_consecutive_failures_open_breaker_and_old_failures_recover():
    ids = []
    for index in range(5):
        reservation = reserve_provider_calls(OWNER, "DeepSeek", [_spec("rewrite", f"failure-{index}")])["rewrite"]
        finalize_provider_call(reservation, final_status="failed", error_code="synthetic_failure")
        ids.append(reservation)
    with pytest.raises(HTTPException) as blocked:
        reserve_provider_calls(OWNER, "DeepSeek", [_spec("rewrite", "blocked")])
    assert blocked.value.status_code == 503
    with session_scope() as db:
        old = utcnow() - timedelta(minutes=16)
        for reservation in ids:
            event = db.get(ProviderUsageEvent, reservation)
            assert event is not None
            event.completed_at = old
    recovered = reserve_provider_calls(OWNER, "DeepSeek", [_spec("rewrite", "recovered")])
    assert recovered["rewrite"]


def test_retention_cleanup_removes_old_operational_rows(monkeypatch: pytest.MonkeyPatch):
    old_id = reserve_provider_calls(OWNER, "DeepSeek", [_spec("rewrite", "old")])["rewrite"]
    finalize_provider_call(old_id, final_status="success")
    with session_scope() as db:
        event = db.get(ProviderUsageEvent, old_id)
        assert event is not None
        event.created_at = utcnow() - timedelta(days=31)
    reserve_provider_calls(OWNER, "Pangram", [_spec("detection", "new")])
    with session_scope() as db:
        assert db.get(ProviderUsageEvent, old_id) is None


def test_paid_call_limit_does_not_block_document_export_or_deletion(client, headers, coursework_text):
    for index in range(20):
        reservation = reserve_provider_calls(OWNER, "DeepSeek", [_spec("rewrite", f"limit-{index}")])["rewrite"]
        finalize_provider_call(reservation, final_status="success")
    with pytest.raises(HTTPException) as blocked:
        reserve_provider_calls(OWNER, "Pangram", [_spec("detection", "over-limit")])
    assert blocked.value.status_code == 429

    created = client.post(
        "/api/v1/documents",
        headers=headers,
        data={"title": "Synthetic quota boundary", "text": coursework_text},
    )
    assert created.status_code == 201
    document_id = created.json()["document"]["id"]
    exported = client.post(f"/api/v1/documents/{document_id}/exports", headers=headers)
    assert exported.status_code == 200
    assert exported.content.startswith(b"PK")
    assert client.delete(f"/api/v1/documents/{document_id}", headers=headers).status_code == 204
