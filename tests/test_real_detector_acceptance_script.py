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
        "overallScore": 50.0,
        "sentenceSpans": [],
        "confidence": 0.8,
        "provider": "Pangram",
        "providerModelVersion": "3.3",
        "requestId": "synthetic-request",
        "warnings": [],
        "isMock": True,
        "latencyMs": 10,
        "status": "success",
        "error": None,
    }
    with pytest.raises(RuntimeError, match="mock/sandbox"):
        validate_provider(provider, "Pangram")
