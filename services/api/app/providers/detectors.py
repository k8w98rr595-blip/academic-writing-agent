from __future__ import annotations

import asyncio
import hashlib
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from urllib.parse import quote

import httpx
from fastapi import HTTPException, status

from ..config import get_settings
from ..text import sentence_ranges, word_count
from .http_client import get_json_with_retry, post_json_with_retry


FORMULAIC = (
    "it is important to note",
    "it should be noted",
    "in conclusion",
    "moreover",
    "furthermore",
    "plays a crucial role",
    "cannot be overstated",
    "studies have shown",
    "this highlights the importance",
    "in today's rapidly evolving",
)

Classification = Literal["ai_generated", "ai_assisted", "human"]
CONFIDENCE_VALUES = {"high": 0.9, "medium": 0.7, "low": 0.5}
PANGRAM_4_PREDICTION_VALUES = {"ai", "human", "mixed"}
PANGRAM_4_LABELS: dict[str, Classification] = {
    "AI-Generated": "ai_generated",
    "AI-Assisted": "ai_assisted",
    "Human Written": "human",
}
MAX_PROVIDER_WINDOWS = 20_000
MAX_PROVIDER_MODELS = 64
MAX_PROVIDER_RESPONSE_BYTES = 16 * 1024 * 1024
FRACTION_SUM_TOLERANCE = 0.02
SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SAFE_LABEL = re.compile(r"^[A-Za-z][A-Za-z -]{0,63}$")
SAFE_MODEL_SELECTOR = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SAFE_STAGE = re.compile(r"^STAGE_[A-Z_]{1,40}$")
DISCLAIMER = (
    "This is a probabilistic AI writing risk signal for internal review, not proof of authorship "
    "or academic misconduct."
)


@dataclass(frozen=True)
class ProviderSpan:
    paragraph_id: str
    start: int
    end: int
    classification: Classification
    score: float
    confidence: float


@dataclass
class ProviderResult:
    provider: str
    provider_model: str | None
    provider_model_version: str | None
    prediction: str | None
    fraction_ai: float | None
    fraction_ai_assisted: float | None
    fraction_human: float | None
    qualifying_words: int
    spans: list[ProviderSpan]
    request_id: str | None
    warnings: list[str]
    is_mock: bool
    latency_ms: int
    status: str = "success"
    error: dict[str, Any] | None = None


class DetectorProvider(Protocol):
    name: str

    def validate_configuration(self) -> None: ...

    async def detect(self, paragraphs: list[dict], idempotency_key: str) -> ProviderResult: ...


class DetectorConfigurationError(RuntimeError):
    pass


class DetectorProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code
        self.request_id = request_id


class MockPangramDetectorProvider:
    name = "Mock Pangram"

    def validate_configuration(self) -> None:
        return None

    async def detect(self, paragraphs: list[dict], idempotency_key: str) -> ProviderResult:
        spans: list[ProviderSpan] = []
        word_totals: dict[Classification, int] = {"ai_generated": 0, "ai_assisted": 0, "human": 0}
        for paragraph in paragraphs:
            for start, end, sentence in sentence_ranges(paragraph["text"]):
                normalized = sentence.lower()
                bucket = int.from_bytes(hashlib.sha256(sentence.encode("utf-8")).digest()[:2], "big") % 100
                if any(pattern in normalized for pattern in FORMULAIC):
                    classification: Classification = "ai_generated"
                    score, confidence = 0.91, 0.9
                elif bucket < 28:
                    classification = "ai_assisted"
                    score, confidence = 0.58, 0.7
                else:
                    classification = "human"
                    score, confidence = 0.08, 0.7
                words = word_count(sentence)
                word_totals[classification] += words
                if classification != "human":
                    spans.append(
                        ProviderSpan(paragraph["id"], start, end, classification, score, confidence)
                    )

        total_words = sum(word_totals.values()) or 1
        fraction_ai = word_totals["ai_generated"] / total_words
        fraction_assisted = word_totals["ai_assisted"] / total_words
        fraction_human = 1.0 - fraction_ai - fraction_assisted
        prediction = _prediction_from_fractions(fraction_ai, fraction_assisted, fraction_human)
        request_id = "mock-" + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16]
        return ProviderResult(
            provider=self.name,
            provider_model="mock",
            provider_model_version="mock-pangram-4-shape-v1",
            prediction=prediction,
            fraction_ai=fraction_ai,
            fraction_ai_assisted=fraction_assisted,
            fraction_human=fraction_human,
            qualifying_words=total_words,
            spans=spans,
            request_id=request_id,
            warnings=["Demonstration result generated by deterministic local rules."],
            is_mock=True,
            latency_ms=0,
        )


class PangramDetectorProvider:
    name = "Pangram"

    def validate_configuration(self) -> None:
        settings = get_settings()
        if not settings.pangram_api_key:
            raise DetectorConfigurationError("Pangram is not configured")
        if not settings.detector_data_processing_acknowledged:
            raise DetectorConfigurationError("Real detector data processing terms have not been acknowledged")
        if not settings.pangram_paid_calls_enabled:
            raise DetectorConfigurationError("Real Pangram paid calls are not enabled")
        if settings.pangram_model != "pangram-4":
            raise DetectorConfigurationError("Paperlight requires the Pangram 4 model selector")

    async def detect(self, paragraphs: list[dict], idempotency_key: str) -> ProviderResult:
        self.validate_configuration()
        settings = get_settings()
        started = time.perf_counter()
        text = _document_text(paragraphs)
        base_url = settings.pangram_api_url.rstrip("/")
        headers = {"x-api-key": settings.pangram_api_key, "Content-Type": "application/json"}

        await _require_available_model(base_url, headers, settings.pangram_model)

        # Pangram documents no idempotency key for task creation. Never retry this
        # potentially billable POST after a timeout or an indeterminate response.
        try:
            response = await post_json_with_retry(
                f"{base_url}/task",
                headers=headers,
                payload={
                    "text": text,
                    "model": settings.pangram_model,
                    "public_dashboard_link": False,
                },
                timeout_seconds=settings.provider_timeout_seconds,
                attempts=1,
            )
        except httpx.TimeoutException as error:
            raise DetectorProviderError(
                "submission_outcome_unknown",
                "Pangram submission timed out; it was not repeated automatically",
                retryable=False,
            ) from error
        except httpx.HTTPError as error:
            raise DetectorProviderError(
                "submission_outcome_unknown",
                "Pangram submission could not be confirmed; it was not repeated automatically",
                retryable=False,
            ) from error
        _raise_for_provider_status("Pangram", response)
        submitted = _json_object("Pangram", response)
        task_id = submitted.get("task_id")
        if not isinstance(task_id, str) or not SAFE_TASK_ID.fullmatch(task_id):
            raise DetectorProviderError("invalid_response", "Pangram returned an invalid task ID", retryable=False)

        deadline = time.monotonic() + settings.pangram_max_poll_seconds
        completed: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            try:
                poll = await get_json_with_retry(
                    f"{base_url}/task/{quote(task_id, safe='')}",
                    headers={"x-api-key": settings.pangram_api_key},
                    timeout_seconds=settings.provider_timeout_seconds,
                    attempts=2,
                )
            except httpx.TimeoutException as error:
                raise DetectorProviderError(
                    "polling_timeout",
                    "Pangram result polling timed out; no new task was submitted",
                    retryable=False,
                    request_id=task_id,
                ) from error
            except httpx.HTTPError as error:
                raise DetectorProviderError(
                    "service_unavailable",
                    "Pangram result polling is unavailable; no new task was submitted",
                    retryable=False,
                    request_id=task_id,
                ) from error
            _raise_for_provider_status("Pangram", poll, request_id=task_id)
            current = _json_object("Pangram", poll)
            stage = current.get("stage")
            if not isinstance(stage, str) or not SAFE_STAGE.fullmatch(stage):
                raise DetectorProviderError(
                    "invalid_response", "Pangram returned an invalid task stage", retryable=False, request_id=task_id
                )
            if stage == "STAGE_SUCCESS":
                completed = current
                break
            if stage == "STAGE_FAILED":
                raise DetectorProviderError(
                    "provider_failed",
                    "Pangram could not analyze the submitted text",
                    retryable=False,
                    request_id=task_id,
                )
            await asyncio.sleep(settings.pangram_poll_interval_seconds)
        if completed is None:
            raise DetectorProviderError(
                "polling_timeout",
                "Pangram did not finish within the polling window; no new task was submitted",
                retryable=False,
                request_id=task_id,
            )

        fraction_ai = _fraction(completed.get("fraction_ai"), "Pangram fraction_ai", task_id)
        fraction_assisted = _fraction(
            completed.get("fraction_ai_assisted"), "Pangram fraction_ai_assisted", task_id
        )
        fraction_human = _fraction(completed.get("fraction_human"), "Pangram fraction_human", task_id)
        if abs((fraction_ai + fraction_assisted + fraction_human) - 1.0) > FRACTION_SUM_TOLERANCE:
            raise DetectorProviderError(
                "invalid_response", "Pangram authorship fractions do not sum to one", retryable=False,
                request_id=task_id,
            )
        returned_text = completed.get("text")
        if not isinstance(returned_text, str):
            raise DetectorProviderError(
                "range_mismatch", "Pangram returned an invalid analyzed text value", retryable=False,
                request_id=task_id,
            )
        boundary_map = _whitespace_normalization_boundary_map(text, returned_text, task_id)
        version = _validated_string(completed.get("version"), "Pangram version", SAFE_VERSION, task_id)
        if not version.startswith("4."):
            raise DetectorProviderError(
                "wrong_model_version",
                "Pangram returned a result that is not identified as Pangram 4",
                retryable=False,
                request_id=task_id,
            )
        prediction = _validated_prediction(completed.get("prediction_short"), task_id)
        windows = _validated_windows(returned_text, completed.get("windows"), task_id)
        windows = _remap_normalized_windows(text, returned_text, windows, boundary_map, task_id)
        spans = _map_windows_to_paragraphs(paragraphs, windows, task_id)
        combined = fraction_ai + fraction_assisted
        warnings = [
            "Combined risk is the transparent sum of Pangram AI-generated and AI-assisted fractions."
        ]
        if returned_text != text:
            warnings.append(
                "Pangram normalized whitespace before inference; marked ranges were mapped back to the original text."
            )
        if combined > 0 and not spans:
            warnings.append("Pangram reported document-level risk without a marked non-human segment.")
        return ProviderResult(
            provider=self.name,
            provider_model=settings.pangram_model,
            provider_model_version=version,
            prediction=prediction,
            fraction_ai=fraction_ai,
            fraction_ai_assisted=fraction_assisted,
            fraction_human=fraction_human,
            qualifying_words=word_count(text),
            spans=spans,
            request_id=_safe_task_reference(task_id),
            warnings=warnings,
            is_mock=False,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )


def _document_text(paragraphs: list[dict]) -> str:
    return "\n\n".join(str(item["text"]) for item in paragraphs)


def detection_content_fingerprint(paragraphs: list[dict], model: str) -> str:
    """Return a content-derived key without persisting or logging the paper text."""

    material = f"{model}\0{_document_text(paragraphs)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _safe_task_reference(task_id: str | None) -> str | None:
    if not task_id:
        return None
    return "sha256:" + hashlib.sha256(task_id.encode("utf-8")).hexdigest()


def _prediction_from_fractions(ai: float, assisted: float, human: float) -> str:
    if human >= 0.8:
        return "Human"
    if ai >= 0.6:
        return "AI"
    if assisted >= 0.4:
        return "AI-Assisted"
    return "Mixed"


def _fraction(value: Any, label: str, request_id: str | None = None) -> float:
    if isinstance(value, bool):
        raise DetectorProviderError(
            "invalid_response", f"{label} must be numeric", retryable=False, request_id=request_id
        )
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise DetectorProviderError(
            "invalid_response", f"{label} must be numeric", retryable=False, request_id=request_id
        ) from error
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise DetectorProviderError(
            "invalid_response", f"{label} is outside 0 to 1", retryable=False, request_id=request_id
        )
    return number


def _integer(value: Any, label: str, request_id: str | None = None) -> int:
    if isinstance(value, bool):
        raise DetectorProviderError(
            "invalid_response", f"{label} must be an integer", retryable=False, request_id=request_id
        )
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise DetectorProviderError(
            "invalid_response", f"{label} must be an integer", retryable=False, request_id=request_id
        ) from error
    if isinstance(value, float) and not value.is_integer():
        raise DetectorProviderError(
            "invalid_response", f"{label} must be an integer", retryable=False, request_id=request_id
        )
    return number


def _validated_string(
    value: Any, label: str, pattern: re.Pattern[str], request_id: str | None = None
) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise DetectorProviderError(
            "invalid_response", f"{label} has an invalid format", retryable=False, request_id=request_id
        )
    return value


def _validated_prediction(value: Any, request_id: str) -> str:
    if not isinstance(value, str) or len(value) > 32 or value.lower() not in PANGRAM_4_PREDICTION_VALUES:
        raise DetectorProviderError(
            "invalid_response", "Pangram prediction_short is invalid", retryable=False, request_id=request_id
        )
    return value


def _classification_from_label(value: Any, request_id: str) -> Classification:
    label = _validated_string(value, "Pangram window label", SAFE_LABEL, request_id)
    try:
        return PANGRAM_4_LABELS[label]
    except KeyError as error:
        raise DetectorProviderError(
            "invalid_response", "Pangram window label is unsupported", retryable=False, request_id=request_id
        ) from error


def _validated_windows(text: str, value: Any, request_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_PROVIDER_WINDOWS:
        raise DetectorProviderError(
            "invalid_response", "Pangram windows must be a bounded array", retryable=False, request_id=request_id
        )
    windows: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict):
            raise DetectorProviderError(
                "invalid_response", "Pangram window must be an object", retryable=False, request_id=request_id
            )
        start = _integer(row.get("start_index"), "Pangram start_index", request_id)
        end = _integer(row.get("end_index"), "Pangram end_index", request_id)
        _validate_provider_range(text, start, end, "Pangram", request_id)
        provider_text = row.get("text")
        if not isinstance(provider_text, str) or text[start:end] != provider_text:
            raise DetectorProviderError(
                "range_mismatch", "Pangram window text does not match its character range", retryable=False,
                request_id=request_id,
            )
        classification = _classification_from_label(row.get("label"), request_id)
        score = _fraction(row.get("ai_assistance_score"), "Pangram ai_assistance_score", request_id)
        confidence_label = row.get("confidence")
        if not isinstance(confidence_label, str) or confidence_label.lower() not in CONFIDENCE_VALUES:
            raise DetectorProviderError(
                "invalid_response", "Pangram window confidence is invalid", retryable=False, request_id=request_id
            )
        if not isinstance(row.get("is_humanized"), bool):
            raise DetectorProviderError(
                "invalid_response", "Pangram 4 window is_humanized is invalid", retryable=False,
                request_id=request_id,
            )
        _fraction(row.get("humanizer_score"), "Pangram humanizer_score", request_id)
        windows.append(
            {
                "start": start,
                "end": end,
                "classification": classification,
                "score": score,
                "confidence": CONFIDENCE_VALUES[confidence_label.lower()],
            }
        )
    windows.sort(key=lambda item: (item["start"], item["end"]))
    if any(current["start"] < previous["end"] for previous, current in zip(windows, windows[1:])):
        raise DetectorProviderError(
            "range_mismatch", "Pangram returned overlapping windows", retryable=False, request_id=request_id
        )
    return windows


def _whitespace_normalization_boundary_map(
    original: str, returned: str, request_id: str
) -> list[int]:
    """Map Pangram's normalized-text boundaries back to submitted text.

    Pangram 4 documents that it may normalize text before inference. We only
    accept normalization that changes whitespace. Every non-whitespace code
    point must remain identical and in the same order; any content change fails
    closed instead of guessing highlight positions.
    """

    if returned == original:
        return list(range(len(original) + 1))

    returned_content = [(index, char) for index, char in enumerate(returned) if not char.isspace()]
    original_content = [(index, char) for index, char in enumerate(original) if not char.isspace()]
    if not returned_content or [char for _, char in returned_content] != [
        char for _, char in original_content
    ]:
        raise DetectorProviderError(
            "range_mismatch",
            "Pangram normalized text cannot be mapped safely to the submission",
            retryable=False,
            request_id=request_id,
        )

    boundary_map: list[int | None] = [None] * (len(returned) + 1)

    def map_gap(returned_start: int, returned_end: int, original_start: int, original_end: int) -> None:
        returned_width = returned_end - returned_start
        original_width = original_end - original_start
        for boundary in range(returned_start, returned_end + 1):
            if returned_width == 0:
                mapped = original_end
            else:
                mapped = original_start + round(
                    ((boundary - returned_start) * original_width) / returned_width
                )
            boundary_map[boundary] = mapped

    returned_cursor = 0
    original_cursor = 0
    for (returned_index, _), (original_index, _) in zip(returned_content, original_content):
        map_gap(returned_cursor, returned_index, original_cursor, original_index)
        boundary_map[returned_index] = original_index
        boundary_map[returned_index + 1] = original_index + 1
        returned_cursor = returned_index + 1
        original_cursor = original_index + 1
    map_gap(returned_cursor, len(returned), original_cursor, len(original))

    if any(value is None for value in boundary_map):
        raise DetectorProviderError(
            "range_mismatch",
            "Pangram normalized text cannot be mapped safely to the submission",
            retryable=False,
            request_id=request_id,
        )
    return [int(value) for value in boundary_map]


def _remap_normalized_windows(
    original: str,
    returned: str,
    windows: list[dict[str, Any]],
    boundary_map: list[int],
    request_id: str,
) -> list[dict[str, Any]]:
    remapped: list[dict[str, Any]] = []
    for window in windows:
        start = boundary_map[window["start"]]
        end = boundary_map[window["end"]]
        _validate_provider_range(original, start, end, "Pangram", request_id)
        returned_fragment = returned[window["start"] : window["end"]]
        original_fragment = original[start:end]
        if "".join(returned_fragment.split()) != "".join(original_fragment.split()):
            raise DetectorProviderError(
                "range_mismatch",
                "Pangram normalized window cannot be mapped safely to the submission",
                retryable=False,
                request_id=request_id,
            )
        remapped.append({**window, "start": start, "end": end})
    remapped.sort(key=lambda item: (item["start"], item["end"]))
    if any(current["start"] < previous["end"] for previous, current in zip(remapped, remapped[1:])):
        raise DetectorProviderError(
            "range_mismatch", "Pangram normalized windows overlap after mapping", retryable=False,
            request_id=request_id,
        )
    return remapped


def _validate_provider_range(
    text: str, start: int, end: int, provider: str, request_id: str | None = None
) -> None:
    if start < 0 or end <= start or end > len(text):
        raise DetectorProviderError(
            "range_mismatch", f"{provider} returned an out-of-range character span", retryable=False,
            request_id=request_id,
        )


def _map_windows_to_paragraphs(
    paragraphs: list[dict], windows: list[dict[str, Any]], request_id: str
) -> list[ProviderSpan]:
    offsets: list[tuple[dict, int, int]] = []
    cursor = 0
    for paragraph in paragraphs:
        start = cursor
        end = start + len(paragraph["text"])
        offsets.append((paragraph, start, end))
        cursor = end + 2
    spans: list[ProviderSpan] = []
    for window in windows:
        if window["classification"] == "human":
            continue
        mapped = 0
        for paragraph, paragraph_start, paragraph_end in offsets:
            overlap_start = max(window["start"], paragraph_start)
            overlap_end = min(window["end"], paragraph_end)
            if overlap_end <= overlap_start:
                continue
            spans.append(
                ProviderSpan(
                    paragraph_id=paragraph["id"],
                    start=overlap_start - paragraph_start,
                    end=overlap_end - paragraph_start,
                    classification=window["classification"],
                    score=window["score"],
                    confidence=window["confidence"],
                )
            )
            mapped += overlap_end - overlap_start
        if mapped == 0:
            raise DetectorProviderError(
                "range_mismatch", "Pangram risk window could not be mapped to a paragraph", retryable=False,
                request_id=request_id,
            )
    return spans


def _json_object(provider: str, response: httpx.Response) -> dict[str, Any]:
    if len(response.content) > MAX_PROVIDER_RESPONSE_BYTES:
        raise DetectorProviderError(
            "invalid_response", f"{provider} response exceeded the allowed size", retryable=False
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise DetectorProviderError(
            "invalid_response", f"{provider} returned invalid JSON", retryable=False
        ) from error
    if not isinstance(payload, dict):
        raise DetectorProviderError(
            "invalid_response", f"{provider} response must be an object", retryable=False
        )
    return payload


async def _require_available_model(base_url: str, headers: dict[str, str], model: str) -> None:
    """Discover entitlement before any potentially billable detection submission."""

    if not SAFE_MODEL_SELECTOR.fullmatch(model):
        raise DetectorConfigurationError("Pangram model selector has an invalid format")
    try:
        response = await get_json_with_retry(
            f"{base_url}/models",
            headers={"x-api-key": headers["x-api-key"]},
            timeout_seconds=get_settings().provider_timeout_seconds,
            attempts=2,
        )
    except (httpx.TimeoutException, httpx.HTTPError) as error:
        raise DetectorProviderError(
            "model_discovery_unavailable",
            "Pangram model discovery is temporarily unavailable; no detection task was submitted",
            retryable=True,
        ) from error
    _raise_for_provider_status("Pangram", response)
    payload = _json_object("Pangram", response)
    models = payload.get("models")
    if not isinstance(models, list) or not 1 <= len(models) <= MAX_PROVIDER_MODELS:
        raise DetectorProviderError(
            "invalid_response", "Pangram returned an invalid model catalog", retryable=False
        )
    validated: list[str] = []
    for value in models:
        if not isinstance(value, str) or not SAFE_MODEL_SELECTOR.fullmatch(value):
            raise DetectorProviderError(
                "invalid_response", "Pangram returned an invalid model selector", retryable=False
            )
        validated.append(value)
    if model not in validated:
        raise DetectorProviderError(
            "model_not_available",
            "Pangram 4 is not enabled for this API key; no detection task was submitted",
            retryable=False,
        )


def _raise_for_provider_status(provider: str, response: httpx.Response, request_id: str | None = None) -> None:
    code = response.status_code
    if 200 <= code < 300:
        return
    if code in {401, 403}:
        raise DetectorProviderError(
            "authentication_failed", f"{provider} authentication or authorization failed", retryable=False,
            status_code=code, request_id=request_id,
        )
    if code == 402:
        raise DetectorProviderError(
            "insufficient_credits", f"{provider} has insufficient credits", retryable=False,
            status_code=code, request_id=request_id,
        )
    if code == 429:
        raise DetectorProviderError(
            "rate_limited", f"{provider} rate limit was reached", retryable=True,
            status_code=code, request_id=request_id,
        )
    if code in {400, 404, 409, 413, 422}:
        raise DetectorProviderError(
            "invalid_request", f"{provider} rejected the detection request", retryable=False,
            status_code=code, request_id=request_id,
        )
    if code in {408, 425, 500, 502, 503, 504}:
        raise DetectorProviderError(
            "service_unavailable", f"{provider} is temporarily unavailable", retryable=True,
            status_code=code, request_id=request_id,
        )
    raise DetectorProviderError(
        "provider_failed", f"{provider} request failed", retryable=False, status_code=code,
        request_id=request_id,
    )


async def _call_provider(
    detector: DetectorProvider, paragraphs: list[dict], idempotency_key: str
) -> ProviderResult:
    started = time.perf_counter()
    try:
        return await detector.detect(paragraphs, idempotency_key)
    except DetectorProviderError as error:
        return ProviderResult(
            provider=detector.name,
            provider_model=get_settings().pangram_model,
            provider_model_version=None,
            prediction=None,
            fraction_ai=None,
            fraction_ai_assisted=None,
            fraction_human=None,
            qualifying_words=sum(word_count(item["text"]) for item in paragraphs),
            spans=[],
            request_id=_safe_task_reference(error.request_id),
            warnings=[],
            is_mock=False,
            latency_ms=round((time.perf_counter() - started) * 1000),
            status="failed",
            error={"code": error.code, "message": error.message, "retryable": error.retryable},
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError, OverflowError):
        return _unexpected_provider_failure(detector.name, paragraphs, started)
    except Exception:
        return _unexpected_provider_failure(detector.name, paragraphs, started)


def _unexpected_provider_failure(
    provider: str, paragraphs: list[dict], started: float
) -> ProviderResult:
    return ProviderResult(
        provider=provider,
        provider_model=get_settings().pangram_model if provider == "Pangram" else None,
        provider_model_version=None,
        prediction=None,
        fraction_ai=None,
        fraction_ai_assisted=None,
        fraction_human=None,
        qualifying_words=sum(word_count(item["text"]) for item in paragraphs),
        spans=[],
        request_id=None,
        warnings=[],
        is_mock=False,
        latency_ms=round((time.perf_counter() - started) * 1000),
        status="failed",
        error={
            "code": "provider_failed",
            "message": "Detection provider failed unexpectedly",
            "retryable": False,
        },
    )


def _serialize_result(result: ProviderResult, analyzed_version_id: str) -> dict[str, Any]:
    successful = result.status == "success"
    ai_percent = round(result.fraction_ai * 100, 1) if result.fraction_ai is not None else None
    assisted_percent = (
        round(result.fraction_ai_assisted * 100, 1) if result.fraction_ai_assisted is not None else None
    )
    human_percent = round(result.fraction_human * 100, 1) if result.fraction_human is not None else None
    combined = (
        round((result.fraction_ai + result.fraction_ai_assisted) * 100, 1)
        if result.fraction_ai is not None and result.fraction_ai_assisted is not None
        else None
    )
    warnings = list(result.warnings)
    analyzed_at = datetime.now(timezone.utc).isoformat()
    if not successful:
        warnings.append("The detector was unavailable, so no risk percentage or highlight was saved.")
    return {
        "provider": result.provider,
        "providerModel": result.provider_model,
        "providerModelVersion": result.provider_model_version,
        "isMock": result.is_mock,
        "status": result.status,
        "error": result.error,
        "prediction": result.prediction,
        "qualifyingWords": result.qualifying_words,
        "aiGeneratedPercent": ai_percent,
        "aiAssistedPercent": assisted_percent,
        "humanPercent": human_percent,
        "combinedRiskPercent": combined,
        "spans": [
            {
                "paragraphId": span.paragraph_id,
                "start": span.start,
                "end": span.end,
                "classification": span.classification,
                "score": round(span.score, 3),
                "confidence": round(span.confidence, 3),
            }
            for span in result.spans
        ],
        "requestId": result.request_id,
        "taskReference": result.request_id,
        "warnings": warnings,
        "disclaimer": DISCLAIMER,
        "analyzedVersionId": analyzed_version_id,
        "analyzedAt": analyzed_at,
        "detectedAt": analyzed_at,
        "latencyMs": result.latency_ms,
    }


async def run_detection(
    paragraphs: list[dict], idempotency_key: str | None = None, analyzed_version_id: str = ""
) -> dict[str, Any]:
    settings = get_settings()
    if settings.detector_mode == "mock":
        detector: DetectorProvider = MockPangramDetectorProvider()
    elif settings.detector_mode == "pangram":
        detector = PangramDetectorProvider()
    else:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Unsupported detector mode")
    try:
        detector.validate_configuration()
    except DetectorConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    operation_key = idempotency_key or "analysis-" + hashlib.sha256(_document_text(paragraphs).encode()).hexdigest()
    result = await _call_provider(detector, paragraphs, operation_key)
    return _serialize_result(result, analyzed_version_id)
