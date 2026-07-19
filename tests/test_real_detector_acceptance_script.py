from __future__ import annotations

import pytest

from scripts.acceptance_real_detectors import synthetic_paper, validate_provider
from services.api.app.text import word_count


def test_real_detector_acceptance_uses_only_synthetic_valid_length_text():
    paper = synthetic_paper()
    assert 800 <= word_count(paper) <= 5000
    assert "@" not in paper
    assert "http" not in paper.lower()


def test_real_detector_acceptance_rejects_mock_provider_result():
    provider = {
        "provider": "Pangram",
        "providerModelVersion": "3.0",
        "requestId": "synthetic-request",
        "prediction": "Mixed",
        "qualifyingWords": 900,
        "aiGeneratedPercent": 30.0,
        "aiAssistedPercent": 20.0,
        "humanPercent": 50.0,
        "combinedRiskPercent": 50.0,
        "spans": [],
        "warnings": [],
        "disclaimer": "probabilistic",
        "analyzedVersionId": "version-synthetic",
        "analyzedAt": "2026-07-19T00:00:00Z",
        "isMock": True,
        "latencyMs": 10,
        "status": "success",
        "error": None,
    }
    with pytest.raises(RuntimeError, match="mock/sandbox"):
        validate_provider(provider, "Pangram")
