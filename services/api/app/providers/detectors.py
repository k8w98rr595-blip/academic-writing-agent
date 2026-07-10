from __future__ import annotations

import hashlib
import math
import secrets
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, status

from ..config import get_settings
from ..text import document_quality_checks, sentence_ranges, word_count
from .http_client import post_json_with_retry


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


@dataclass
class ProviderSpan:
    paragraph_id: str
    start: int
    end: int
    score: float


@dataclass
class ProviderResult:
    name: str
    model_version: str
    fraction: float
    spans: list[ProviderSpan]
    is_mock: bool


class DetectorConfigurationError(RuntimeError):
    pass


class MockDetector:
    def __init__(self, name: str, salt: str, threshold: int) -> None:
        self.name = name
        self.salt = salt
        self.threshold = threshold

    async def detect(self, paragraphs: list[dict]) -> ProviderResult:
        spans: list[ProviderSpan] = []
        flagged_words = 0
        total_words = sum(word_count(item["text"]) for item in paragraphs) or 1
        for paragraph in paragraphs:
            for start, end, sentence in sentence_ranges(paragraph["text"]):
                normalized = sentence.lower()
                digest = hashlib.sha256(f"{self.salt}:{sentence}".encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:2], "big") % 100
                formulaic = any(pattern in normalized for pattern in FORMULAIC)
                flagged = formulaic or bucket < self.threshold
                if flagged:
                    score = 0.86 if formulaic else 0.66 + (self.threshold - bucket) / 100
                    spans.append(ProviderSpan(paragraph["id"], start, end, min(score, 0.97)))
                    flagged_words += word_count(sentence)
        fraction = round(flagged_words / total_words * 100, 1)
        return ProviderResult(self.name, "mock-detector-v1", fraction, spans, True)


class PangramDetector:
    async def detect(self, paragraphs: list[dict]) -> ProviderResult:
        settings = get_settings()
        if not settings.pangram_api_key:
            raise DetectorConfigurationError("Pangram is not configured")
        text = "\n\n".join(item["text"] for item in paragraphs)
        response = await post_json_with_retry(
            settings.pangram_api_url,
            headers={
                "Authorization": f"Bearer {settings.pangram_api_key}",
                "Idempotency-Key": f"paperlight-{secrets.token_hex(16)}",
            },
            payload={"text": text, "public_dashboard_link": False},
            timeout_seconds=settings.provider_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Pangram response must be an object")
        fraction_value = payload.get("fraction_ai", payload.get("ai_fraction", payload.get("fraction", 0)))
        fraction = float(fraction_value)
        if 0 <= fraction <= 1:
            fraction *= 100
        if not math.isfinite(fraction) or not 0 <= fraction <= 100:
            raise ValueError("Pangram fraction is outside the accepted range")
        windows = payload.get("windows", [])
        if not isinstance(windows, list):
            raise ValueError("Pangram windows must be a list")
        spans = _global_windows_to_paragraphs(paragraphs, windows)
        return ProviderResult("Pangram", str(payload.get("model_version", "pangram-api")), round(fraction, 1), spans, False)


class CopyleaksDetector:
    async def detect(self, paragraphs: list[dict]) -> ProviderResult:
        settings = get_settings()
        if not settings.copyleaks_access_token:
            raise DetectorConfigurationError("Copyleaks is not configured")
        text = "\n\n".join(item["text"] for item in paragraphs)
        scan_id = f"paperlight-{secrets.token_hex(12)}"
        endpoint = f"{settings.copyleaks_api_url.rstrip('/')}/{scan_id}/check"
        response = await post_json_with_retry(
            endpoint,
            headers={
                "Authorization": f"Bearer {settings.copyleaks_access_token}",
                "Idempotency-Key": scan_id,
            },
            payload={"text": text, "sandbox": False, "explain": True, "sensitivity": 2},
            timeout_seconds=settings.provider_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Copyleaks response must be an object")
        fraction = float((payload.get("summary") or {}).get("ai", 0))
        if 0 <= fraction <= 1:
            fraction *= 100
        if not math.isfinite(fraction) or not 0 <= fraction <= 100:
            raise ValueError("Copyleaks fraction is outside the accepted range")
        windows: list[dict] = []
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise ValueError("Copyleaks results must be a list")
        for row in results:
            if not isinstance(row, dict):
                raise ValueError("Copyleaks result row must be an object")
            probability = float(row.get("probability", 0))
            for match in row.get("matches", []):
                chars = (match.get("text") or {}).get("chars") or {}
                for start, length in zip(chars.get("starts", []), chars.get("lengths", []), strict=False):
                    windows.append({"start": int(start), "end": int(start) + int(length), "score": probability})
        spans = _global_windows_to_paragraphs(paragraphs, windows)
        return ProviderResult("Copyleaks", str(payload.get("modelVersion", "copyleaks-api")), round(fraction, 1), spans, False)


def _global_windows_to_paragraphs(paragraphs: list[dict], windows: list[dict]) -> list[ProviderSpan]:
    offsets: list[tuple[dict, int, int]] = []
    cursor = 0
    for paragraph in paragraphs:
        start = cursor
        end = start + len(paragraph["text"])
        offsets.append((paragraph, start, end))
        cursor = end + 2
    spans: list[ProviderSpan] = []
    for row in windows:
        global_start = int(row.get("start", row.get("start_index", 0)))
        global_end = int(row.get("end", row.get("end_index", global_start)))
        score = float(row.get("score", row.get("probability", 0.5)))
        for paragraph, start, end in offsets:
            overlap_start = max(global_start, start)
            overlap_end = min(global_end, end)
            if overlap_end > overlap_start:
                spans.append(ProviderSpan(paragraph["id"], overlap_start - start, overlap_end - start, score))
    return spans


def _merge_results(results: list[ProviderResult], paragraphs: list[dict]) -> dict:
    paragraph_map = {item["id"]: item["text"] for item in paragraphs}
    grouped: dict[tuple[str, int, int], list[tuple[str, float]]] = {}
    for result in results:
        for span in result.spans:
            grouped.setdefault((span.paragraph_id, span.start, span.end), []).append((result.name, span.score))
    merged = []
    for (paragraph_id, start, end), rows in grouped.items():
        if paragraph_id not in paragraph_map or start < 0 or end > len(paragraph_map[paragraph_id]) or end <= start:
            continue
        merged.append(
            {
                "paragraphId": paragraph_id,
                "start": start,
                "end": end,
                "score": round(sum(row[1] for row in rows) / len(rows), 3),
                "evidence": "consensus" if len({row[0] for row in rows}) > 1 else "single",
                "providers": sorted({row[0] for row in rows}),
            }
        )
    fractions = [result.fraction for result in results]
    estimate = round(sum(fractions) / len(fractions), 1) if fractions else 0
    uncertainty_pad = 4 if len(results) > 1 else 8
    low = max(0, round(min(fractions) - uncertainty_pad, 1)) if fractions else 0
    high = min(100, round(max(fractions) + uncertainty_pad, 1)) if fractions else 0
    return {
        "estimate": estimate,
        "uncertainty": {"low": low, "high": high},
        "qualifyingWords": sum(word_count(item["text"]) for item in paragraphs),
        "isMock": all(result.is_mock for result in results),
        "label": "Low evidence" if estimate < 20 else "Estimated AI-like text",
        "spans": sorted(merged, key=lambda item: (item["paragraphId"], item["start"], item["end"])),
        "providers": [
            {
                "name": result.name,
                "modelVersion": result.model_version,
                "estimate": result.fraction,
                "isMock": result.is_mock,
            }
            for result in results
        ],
        "qualityChecks": document_quality_checks(paragraphs),
        "disclaimer": "This is a probabilistic writing-pattern estimate, not proof of authorship or misconduct.",
    }


async def run_detection(paragraphs: list[dict]) -> dict:
    settings = get_settings()
    if settings.detector_mode == "mock":
        detectors = [MockDetector("Mock Primary", "primary", 12), MockDetector("Mock Review", "review", 9)]
    elif settings.detector_mode == "dual":
        detectors = [PangramDetector(), CopyleaksDetector()]
    else:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Unsupported detector mode")
    try:
        results = [await detector.detect(paragraphs) for detector in detectors]
    except DetectorConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Detection provider unavailable") from error
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Detection provider returned an invalid response") from error
    return _merge_results(results, paragraphs)
