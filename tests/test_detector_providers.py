from __future__ import annotations

import asyncio
from copy import deepcopy

import httpx
import pytest
from fastapi import HTTPException

from services.api.app.config import get_settings
from services.api.app.providers import detectors as detector_module
from services.api.app.providers.detectors import DetectorProviderError, _raise_for_provider_status, run_detection
from services.api.app.providers.http_client import post_json_with_retry


PARAGRAPHS = [
    {"id": "p1", "text": "Alpha evidence is carefully evaluated. Beta evidence remains uncertain."},
    {"id": "p2", "text": "A separate paragraph records the limitations."},
]


def _response(method: str, url: str, status_code: int, payload: dict, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code, json=payload, headers=headers, request=httpx.Request(method, url))


def _text() -> str:
    return "\n\n".join(row["text"] for row in PARAGRAPHS)


def _window(fragment: str, label: str, score: float, confidence: str = "High") -> dict:
    text = _text()
    start = text.index(fragment)
    return {
        "text": fragment,
        "label": label,
        "ai_assistance_score": score,
        "confidence": confidence,
        "start_index": start,
        "end_index": start + len(fragment),
    }


def _success_payload() -> dict:
    first = "Alpha evidence is carefully evaluated."
    second = "Beta evidence remains uncertain."
    third = PARAGRAPHS[1]["text"]
    return {
        "stage": "STAGE_SUCCESS",
        "text": _text(),
        "version": "3.0",
        "prediction_short": "Mixed",
        "fraction_ai": 0.5,
        "fraction_ai_assisted": 0.2,
        "fraction_human": 0.3,
        "windows": [
            _window(first, "AI-Generated", 0.91),
            _window(second, "Moderately AI-Assisted", 0.58, "Medium"),
            _window(third, "Human-Written", 0.04, "High"),
        ],
    }


def _real_mode(monkeypatch: pytest.MonkeyPatch, *, key: bool = True, acknowledged: bool = True) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DETECTOR_MODE", "pangram")
    monkeypatch.setenv("PANGRAM_API_URL", "https://text.external-api.pangram.com")
    monkeypatch.setenv("PANGRAM_API_KEY", "synthetic-contract-value" if key else "")
    monkeypatch.setenv("DETECTOR_DATA_PROCESSING_ACKNOWLEDGED", "1" if acknowledged else "0")
    get_settings.cache_clear()


def _install_success_transport(monkeypatch: pytest.MonkeyPatch, payload: dict, calls: list[tuple[str, str]] | None = None) -> None:
    async def fake_post(url: str, *, headers: dict, payload: dict, attempts: int, **_: object) -> httpx.Response:
        if calls is not None:
            calls.append(("POST", url))
        assert headers["x-api-key"]
        assert "Idempotency-Key" not in headers
        assert attempts == 1
        assert payload == {"text": _text(), "public_dashboard_link": False}
        return _response("POST", url, 202, {"task_id": "task-contract-1"})

    async def fake_get(url: str, **_: object) -> httpx.Response:
        if calls is not None:
            calls.append(("GET", url))
        return _response("GET", url, 200, payload)

    monkeypatch.setattr(detector_module, "post_json_with_retry", fake_post)
    monkeypatch.setattr(detector_module, "get_json_with_retry", fake_get)


@pytest.fixture(autouse=True)
def _clear_cached_settings():
    yield
    get_settings.cache_clear()


def test_pangram_current_async_contract_maps_three_classifications(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, str]] = []
    _real_mode(monkeypatch)
    _install_success_transport(monkeypatch, _success_payload(), calls)

    result = asyncio.run(
        run_detection(PARAGRAPHS, idempotency_key="analysis-contract", analyzed_version_id="version-1")
    )

    assert calls == [
        ("POST", "https://text.external-api.pangram.com/task"),
        ("GET", "https://text.external-api.pangram.com/task/task-contract-1"),
    ]
    assert result["provider"] == "Pangram"
    assert result["providerModelVersion"] == "3.0"
    assert result["requestId"] == "task-contract-1"
    assert result["prediction"] == "Mixed"
    assert result["aiGeneratedPercent"] == 50.0
    assert result["aiAssistedPercent"] == 20.0
    assert result["humanPercent"] == 30.0
    assert result["combinedRiskPercent"] == 70.0
    assert result["analyzedVersionId"] == "version-1"
    assert result["analyzedAt"]
    assert [span["classification"] for span in result["spans"]] == ["ai_generated", "ai_assisted"]
    assert result["spans"][0]["paragraphId"] == "p1"
    assert result["spans"][0]["start"] == 0
    assert result["spans"][1]["confidence"] == 0.7


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (401, "authentication_failed", False),
        (402, "insufficient_credits", False),
        (403, "authentication_failed", False),
        (429, "rate_limited", True),
        (500, "service_unavailable", True),
        (503, "service_unavailable", True),
    ],
)
def test_pangram_submit_errors_are_sanitized(
    monkeypatch: pytest.MonkeyPatch, status_code: int, expected_code: str, retryable: bool
):
    calls = 0

    async def fake_post(url: str, **_: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response("POST", url, status_code, {"secretDetail": "must not escape"})

    _real_mode(monkeypatch)
    monkeypatch.setattr(detector_module, "post_json_with_retry", fake_post)
    result = asyncio.run(run_detection(PARAGRAPHS, idempotency_key="status-contract"))
    assert calls == 1
    assert result["status"] == "failed"
    assert result["combinedRiskPercent"] is None
    assert result["spans"] == []
    assert result["error"]["code"] == expected_code
    assert result["error"]["retryable"] is retryable
    assert "secretDetail" not in str(result)


def test_pangram_ambiguous_submit_timeout_is_never_repeated(monkeypatch: pytest.MonkeyPatch):
    calls = 0

    async def fake_post(url: str, **_: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("synthetic timeout", request=httpx.Request("POST", url))

    _real_mode(monkeypatch)
    monkeypatch.setattr(detector_module, "post_json_with_retry", fake_post)
    result = asyncio.run(run_detection(PARAGRAPHS, idempotency_key="timeout-contract"))
    assert calls == 1
    assert result["error"] == {
        "code": "submission_outcome_unknown",
        "message": "Pangram submission timed out; it was not repeated automatically",
        "retryable": False,
    }


def test_pangram_invalid_json_fails_closed(monkeypatch: pytest.MonkeyPatch):
    async def fake_post(url: str, **_: object) -> httpx.Response:
        return _response("POST", url, 202, {"task_id": "task-json"})

    async def fake_get(url: str, **_: object) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", request=httpx.Request("GET", url))

    _real_mode(monkeypatch)
    monkeypatch.setattr(detector_module, "post_json_with_retry", fake_post)
    monkeypatch.setattr(detector_module, "get_json_with_retry", fake_get)
    result = asyncio.run(run_detection(PARAGRAPHS, idempotency_key="json-contract"))
    assert result["combinedRiskPercent"] is None
    assert result["error"]["code"] == "invalid_response"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda payload: payload.update(fraction_ai=1.2), "invalid_response"),
        (lambda payload: payload.update(fraction_human=0.8), "invalid_response"),
        (lambda payload: payload.update(text="different text"), "range_mismatch"),
        (lambda payload: payload["windows"][0].update(end_index=len(_text()) + 1), "range_mismatch"),
        (lambda payload: payload["windows"][0].update(text="mismatched window"), "range_mismatch"),
        (lambda payload: payload["windows"][0].update(confidence="Certain"), "invalid_response"),
        (lambda payload: payload["windows"][0].update(label="Unknown"), "invalid_response"),
        (lambda payload: payload.update(version="../unsafe"), "invalid_response"),
        (lambda payload: payload.update(prediction_short="Guaranteed AI"), "invalid_response"),
    ],
)
def test_pangram_critical_response_validation_fails_closed(
    monkeypatch: pytest.MonkeyPatch, mutation, expected_code: str
):
    payload = deepcopy(_success_payload())
    mutation(payload)
    _real_mode(monkeypatch)
    _install_success_transport(monkeypatch, payload)
    result = asyncio.run(run_detection(PARAGRAPHS, idempotency_key="invalid-contract"))
    assert result["combinedRiskPercent"] is None
    assert result["spans"] == []
    assert result["error"]["code"] == expected_code


def test_pangram_rejects_too_many_windows(monkeypatch: pytest.MonkeyPatch):
    payload = _success_payload()
    payload["windows"] = payload["windows"][:2]
    _real_mode(monkeypatch)
    monkeypatch.setattr(detector_module, "MAX_PROVIDER_WINDOWS", 1)
    _install_success_transport(monkeypatch, payload)
    result = asyncio.run(run_detection(PARAGRAPHS, idempotency_key="window-count-contract"))
    assert result["error"]["code"] == "invalid_response"
    assert result["spans"] == []


def test_pangram_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    _real_mode(monkeypatch, key=False)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(run_detection(PARAGRAPHS, idempotency_key="missing-key"))
    assert caught.value.status_code == 503
    assert "not configured" in str(caught.value.detail)


def test_pangram_requires_data_processing_acknowledgement(monkeypatch: pytest.MonkeyPatch):
    _real_mode(monkeypatch, acknowledged=False)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(run_detection(PARAGRAPHS, idempotency_key="missing-terms"))
    assert caught.value.status_code == 503
    assert "not been acknowledged" in str(caught.value.detail)


def test_pangram_rejects_untrusted_api_host_in_every_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DETECTOR_MODE", "pangram")
    monkeypatch.setenv("PANGRAM_API_URL", "https://attacker.invalid")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="official HTTPS API host"):
        get_settings()


def test_mock_pangram_is_deterministic_and_uses_single_provider_shape(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DETECTOR_MODE", "mock")
    get_settings.cache_clear()
    first = asyncio.run(run_detection(PARAGRAPHS, idempotency_key="same-analysis", analyzed_version_id="v1"))
    second = asyncio.run(run_detection(PARAGRAPHS, idempotency_key="same-analysis", analyzed_version_id="v1"))
    assert {key: value for key, value in first.items() if key != "analyzedAt"} == {
        key: value for key, value in second.items() if key != "analyzedAt"
    }
    assert first["provider"] == "Mock Pangram"
    assert first["isMock"] is True
    assert first["status"] == "success"
    assert set(first) >= {
        "aiGeneratedPercent", "aiAssistedPercent", "humanPercent", "combinedRiskPercent", "spans"
    }
    assert "providers" not in first
    assert "fusionStatus" not in first


def test_provider_status_helper_never_exposes_response_body():
    response = _response("POST", "https://provider.invalid", 401, {"secretDetail": "must not escape"})
    with pytest.raises(DetectorProviderError) as caught:
        _raise_for_provider_status("Provider", response)
    assert "secretDetail" not in caught.value.message


def test_retry_after_beyond_bound_returns_without_retry(monkeypatch: pytest.MonkeyPatch):
    attempts = 0

    class FakeClient:
        def __init__(self, **_: object) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def request(self, method: str, url: str, **_: object) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return _response(method, url, 429, {}, {"Retry-After": "300"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    response = asyncio.run(
        post_json_with_retry(
            "https://provider.invalid/test",
            headers={},
            payload={},
            timeout_seconds=1,
            attempts=2,
            max_retry_after_seconds=5,
        )
    )
    assert response.status_code == 429
    assert attempts == 1
