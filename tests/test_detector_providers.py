from __future__ import annotations

import asyncio

import httpx
import pytest

from services.api.app.config import get_settings
from services.api.app.providers import detectors as detector_module
from services.api.app.providers.detectors import (
    DetectorProviderError,
    ProviderResult,
    ProviderSpan,
    _merge_results,
    _raise_for_provider_status,
    clear_copyleaks_token_cache,
    run_detection,
)
from services.api.app.providers.http_client import post_json_with_retry


def _response(method: str, url: str, status_code: int, payload: dict, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code, json=payload, headers=headers, request=httpx.Request(method, url))


def _set_real_mode(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    monkeypatch.setenv("DETECTOR_MODE", mode)
    monkeypatch.setenv("DETECTOR_DATA_PROCESSING_ACKNOWLEDGED", "1")
    get_settings.cache_clear()


def _restore_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DETECTOR_MODE", "mock")
    monkeypatch.setenv("DETECTOR_DATA_PROCESSING_ACKNOWLEDGED", "0")
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    clear_copyleaks_token_cache()


def test_pangram_async_contract_maps_official_v3_task_response(monkeypatch: pytest.MonkeyPatch):
    paragraphs = [
        {"id": "p1", "text": "Alpha evidence is carefully evaluated. Beta evidence remains uncertain."},
        {"id": "p2", "text": "A separate paragraph records the limitations."},
    ]
    submitted_text = "\n\n".join(row["text"] for row in paragraphs)
    first_sentence = paragraphs[0]["text"].split(". ")[0] + "."
    first_start = submitted_text.index(first_sentence)
    calls: list[tuple[str, str]] = []

    async def fake_post(url: str, *, headers: dict, payload: dict, **_: object) -> httpx.Response:
        calls.append(("POST", url))
        assert headers["x-api-key"]
        assert "Idempotency-Key" not in headers
        assert payload == {"text": submitted_text, "public_dashboard_link": False}
        return _response("POST", url, 202, {"task_id": "task-contract-1", "stage": "STAGE_QUEUED"})

    poll_payloads = [
        {"task_id": "task-contract-1", "stage": "STAGE_PREPROCESSING"},
        {
            "stage": "STAGE_SUCCESS",
            "text": submitted_text,
            "version": "3.3",
            "headline": "AI Detected",
            "prediction_short": "Mixed",
            "fraction_ai": 0.6,
            "fraction_ai_assisted": 0.1,
            "fraction_human": 0.3,
            "windows": [
                {
                    "text": first_sentence,
                    "label": "AI-Generated",
                    "ai_assistance_score": 0.88,
                    "confidence": "High",
                    "start_index": first_start,
                    "end_index": first_start + len(first_sentence),
                }
            ],
        },
    ]

    async def fake_get(url: str, **_: object) -> httpx.Response:
        calls.append(("GET", url))
        return _response("GET", url, 200, poll_payloads.pop(0))

    async def no_wait(_: float) -> None:
        return None

    monkeypatch.setenv("PANGRAM_API_KEY", "synthetic-pangram-contract-value")
    monkeypatch.setattr(detector_module, "post_json_with_retry", fake_post)
    monkeypatch.setattr(detector_module, "get_json_with_retry", fake_get)
    monkeypatch.setattr(detector_module.asyncio, "sleep", no_wait)
    _set_real_mode(monkeypatch, "pangram")

    result = asyncio.run(run_detection(paragraphs, idempotency_key="analysis-contract"))

    provider = result["providers"][0]
    assert calls == [
        ("POST", "https://text.external-api.pangram.com/task"),
        ("GET", "https://text.external-api.pangram.com/task/task-contract-1"),
        ("GET", "https://text.external-api.pangram.com/task/task-contract-1"),
    ]
    assert result["overallScore"] == 70.0
    assert provider["provider"] == "Pangram"
    assert provider["providerModelVersion"] == "3.3"
    assert provider["requestId"] == "task-contract-1"
    assert provider["isMock"] is False
    assert provider["sentenceSpans"][0]["paragraphId"] == "p1"
    assert provider["sentenceSpans"][0]["start"] == 0
    assert provider["sentenceSpans"][0]["end"] == len(first_sentence)
    _restore_mock(monkeypatch)


def test_copyleaks_sync_contract_logs_in_and_maps_character_sections(monkeypatch: pytest.MonkeyPatch):
    first_sentence = "Evidence should be interpreted cautiously because automated classifications remain probabilistic."
    text = " ".join([first_sentence] * 4)
    paragraphs = [{"id": "p1", "text": text}]
    calls: list[str] = []

    async def fake_post(url: str, *, headers: dict, payload: dict, **_: object) -> httpx.Response:
        calls.append(url)
        if url == "https://id.copyleaks.com/v3/account/login/api":
            assert set(payload) == {"email", "key"}
            assert "Authorization" not in headers
            return _response(
                "POST",
                url,
                200,
                {"access_token": "opaque-contract-value", ".expires": "2099-01-01T00:00:00Z"},
            )
        assert headers["Authorization"].startswith("Bearer ")
        assert payload["text"] == text
        assert payload["sandbox"] is False
        return _response(
            "POST",
            url,
            200,
            {
                "modelVersion": "v7.1",
                "results": [
                    {
                        "classification": 2,
                        "matches": [
                            {"text": {"chars": {"starts": [0], "lengths": [len(first_sentence)]}}}
                        ],
                    }
                ],
                "summary": {"human": 0.28, "ai": 0.72},
            },
        )

    clear_copyleaks_token_cache()
    monkeypatch.setenv("COPYLEAKS_EMAIL", "contract@example.invalid")
    monkeypatch.setenv("COPYLEAKS_API_KEY", "synthetic-copyleaks-contract-value")
    monkeypatch.setenv("COPYLEAKS_SANDBOX", "0")
    monkeypatch.setattr(detector_module, "post_json_with_retry", fake_post)
    _set_real_mode(monkeypatch, "copyleaks")

    result = asyncio.run(run_detection(paragraphs, idempotency_key="analysis-contract"))

    provider = result["providers"][0]
    assert len(calls) == 2
    assert calls[1].startswith("https://api.copyleaks.com/v2/writer-detector/pl-")
    assert result["overallScore"] == 72.0
    assert provider["providerModelVersion"] == "v7.1"
    assert provider["confidence"] == 0.72
    assert provider["sentenceSpans"][0]["start"] == 0
    assert provider["sentenceSpans"][0]["end"] == len(first_sentence)
    assert any("deprecated" in warning for warning in provider["warnings"])
    _restore_mock(monkeypatch)


def _provider(
    name: str,
    score: float | None,
    spans: list[ProviderSpan],
    *,
    failed: bool = False,
) -> ProviderResult:
    return ProviderResult(
        provider=name,
        provider_model_version="contract-v1" if not failed else None,
        overall_score=score,
        sentence_spans=spans,
        confidence=0.8 if not failed else None,
        request_id=f"request-{name.lower()}",
        warnings=[],
        is_mock=False,
        latency_ms=12,
        status="failed" if failed else "success",
        error={"code": "service_unavailable", "message": f"{name} is unavailable", "retryable": True}
        if failed
        else None,
    )


def test_dual_fusion_uses_consensus_floor_and_deep_blue_intersection():
    paragraphs = [{"id": "p1", "text": "A sentence contains evidence."}]
    pangram = _provider("Pangram", 71.0, [ProviderSpan("p1", 0, 29, 0.9)])
    copyleaks = _provider("Copyleaks", 63.0, [ProviderSpan("p1", 0, 29, 0.76)])

    result = _merge_results([pangram, copyleaks], paragraphs, requested_count=2)

    assert result["overallScore"] == 63.0
    assert result["fusionStatus"] == "provider-agreement"
    assert result["providers"][0]["overallScore"] == 71.0
    assert result["providers"][1]["overallScore"] == 63.0
    assert result["spans"] == [
        {
            "paragraphId": "p1",
            "start": 0,
            "end": 29,
            "score": 0.76,
            "evidence": "consensus",
            "providers": ["Copyleaks", "Pangram"],
        }
    ]


def test_dual_fusion_disagreement_has_no_fabricated_percentage():
    paragraphs = [{"id": "p1", "text": "A sentence contains evidence."}]
    result = _merge_results(
        [
            _provider("Pangram", 72.0, [ProviderSpan("p1", 0, 29, 0.9)]),
            _provider("Copyleaks", 34.0, [ProviderSpan("p1", 0, 29, 0.7)]),
        ],
        paragraphs,
        requested_count=2,
    )
    assert result["overallScore"] is None
    assert result["estimate"] is None
    assert result["disagreement"] is True
    assert result["fusionStatus"] == "disagreement"
    assert "no fused percentage" in result["warnings"][-1]


def test_dual_partial_failure_keeps_single_evidence_light_and_no_fused_score():
    paragraphs = [{"id": "p1", "text": "A sentence contains evidence."}]
    result = _merge_results(
        [
            _provider("Pangram", 72.0, [ProviderSpan("p1", 0, 29, 0.9)]),
            _provider("Copyleaks", None, [], failed=True),
        ],
        paragraphs,
        requested_count=2,
    )
    assert result["overallScore"] is None
    assert result["fusionStatus"] == "partial"
    assert result["spans"][0]["evidence"] == "single"
    assert result["providers"][1]["error"]["code"] == "service_unavailable"


def test_pangram_range_mismatch_fails_closed_without_score(monkeypatch: pytest.MonkeyPatch):
    paragraphs = [{"id": "p1", "text": "Evidence must be checked before a conclusion is accepted."}]
    submitted = paragraphs[0]["text"]

    async def fake_post(url: str, **_: object) -> httpx.Response:
        return _response("POST", url, 202, {"task_id": "task-range"})

    async def fake_get(url: str, **_: object) -> httpx.Response:
        return _response(
            "GET",
            url,
            200,
            {
                "stage": "STAGE_SUCCESS",
                "text": submitted,
                "version": "3.3",
                "fraction_ai": 0.8,
                "fraction_ai_assisted": 0,
                "fraction_human": 0.2,
                "windows": [
                    {
                        "text": "does not match",
                        "label": "AI-Generated",
                        "ai_assistance_score": 0.9,
                        "confidence": "High",
                        "start_index": 0,
                        "end_index": 14,
                    }
                ],
            },
        )

    monkeypatch.setenv("PANGRAM_API_KEY", "synthetic-pangram-contract-value")
    monkeypatch.setattr(detector_module, "post_json_with_retry", fake_post)
    monkeypatch.setattr(detector_module, "get_json_with_retry", fake_get)
    _set_real_mode(monkeypatch, "pangram")
    result = asyncio.run(run_detection(paragraphs, idempotency_key="range-contract"))
    assert result["overallScore"] is None
    assert result["providers"][0]["error"]["code"] == "range_mismatch"
    _restore_mock(monkeypatch)


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [(401, "authentication_failed", False), (402, "insufficient_credits", False), (429, "rate_limited", True), (503, "service_unavailable", True)],
)
def test_provider_http_errors_are_sanitized(status_code: int, expected_code: str, retryable: bool):
    response = _response("POST", "https://provider.invalid", status_code, {"secretDetail": "must not escape"})
    with pytest.raises(DetectorProviderError) as caught:
        _raise_for_provider_status("Provider", response)
    assert caught.value.code == expected_code
    assert caught.value.retryable is retryable
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


def test_production_detector_rejects_untrusted_api_host(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DETECTOR_MODE", "pangram")
    monkeypatch.setenv("PANGRAM_API_URL", "https://attacker.invalid")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="official HTTPS API host"):
        get_settings()
    monkeypatch.setenv("PANGRAM_API_URL", "https://text.external-api.pangram.com")
    _restore_mock(monkeypatch)
