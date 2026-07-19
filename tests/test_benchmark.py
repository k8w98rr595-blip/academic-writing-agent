from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchmark.cli import BenchmarkError, canonical_digest, evaluate, load_manifest, load_predictions, write_report
from benchmark.metrics import auprc, auroc, drift_report, threshold_metrics
from benchmark.run_providers import paragraphs_for, prediction_rows


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmark" / "manifests" / "v1.0.0-dev.1.jsonl"
PREDICTIONS = ROOT / "benchmark" / "predictions" / "mock-v1.0.0-dev.1.jsonl"


def test_v1_manifest_is_locked_and_bodies_match() -> None:
    rows, texts = load_manifest(MANIFEST)
    expected = MANIFEST.with_suffix(".sha256").read_text(encoding="utf-8").split()[0]
    assert canonical_digest(rows) == expected
    assert set(texts) == {"ai_business_001", "ai_engineering_001", "human_darwin_001", "human_federalist_001"}
    assert all(not row["governance"]["claimEligible"] for row in rows)


def test_standard_document_metrics_and_threshold_confusion() -> None:
    labels = [0, 0, 1, 1]
    scores = [0.1, 0.4, 0.6, 0.9]
    assert auroc(labels, scores) == 1.0
    assert auprc(labels, scores) == 1.0
    result = threshold_metrics(labels, scores, 0.5)
    assert result["accuracy"] == 1.0
    assert result["fpr"] == 0.0
    assert result["fnr"] == 0.0
    assert auprc([0, 1], [0.5, 0.5]) == 0.5


def test_mock_evaluation_is_non_claimable_and_reproducible(tmp_path: Path) -> None:
    manifest, texts = load_manifest(MANIFEST)
    predictions = load_predictions(PREDICTIONS, dataset_version=manifest[0]["datasetVersion"], texts=texts)
    first = evaluate(manifest, texts, predictions, threshold=0.5, seed=17, bootstrap=100)
    second = evaluate(manifest, texts, predictions, threshold=0.5, seed=17, bootstrap=100)
    assert first == second
    assert first["claimStatus"] == "development-only"
    assert first["thresholdRecommendation"]["available"] is False
    assert first["providerAgreement"] == []
    assert all(group["suppressed"] for provider in first["providers"] for groups in provider["groups"].values() for group in groups)
    write_report(first, tmp_path)
    assert "NOT VALID FOR PRODUCT CLAIMS" in (tmp_path / "report.html").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["seed"] == 17


def test_failed_prediction_has_no_fabricated_score(tmp_path: Path) -> None:
    manifest, texts = load_manifest(MANIFEST)
    rows = [json.loads(line) for line in PREDICTIONS.read_text(encoding="utf-8").splitlines()]
    rows[0]["status"] = "failed"
    rows[0]["errorCode"] = "rate_limited"
    rows[0]["spans"] = []
    path = tmp_path / "predictions.jsonl"
    rows[0]["score"] = 0.7
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(BenchmarkError, match="failed prediction cannot contain a score"):
        load_predictions(path, dataset_version=manifest[0]["datasetVersion"], texts=texts)


def test_manifest_rejects_blind_rewrite_access(tmp_path: Path) -> None:
    rows = [json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines()]
    row = copy.deepcopy(rows[0])
    row["split"] = "blind_final"
    row["body"]["path"] = "corpus/blind/missing.txt"
    row["governance"]["visibility"] = "sealed"
    row["governance"]["rewriteModelAccess"] = "allowed"
    manifest_dir = tmp_path / "benchmark" / "manifests"
    manifest_dir.mkdir(parents=True)
    path = manifest_dir / "bad.jsonl"
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(BenchmarkError, match="must never reach rewrite models"):
        load_manifest(path, verify_lock=False)


def test_version_drift_detects_version_and_classification_changes() -> None:
    previous = [{"provider": "Detector", "providerVersion": "v1", "sampleId": "a", "status": "success", "score": 0.49}]
    current = [{"provider": "Detector", "providerVersion": "v2", "sampleId": "a", "status": "success", "score": 0.70}]
    report = drift_report(previous, current, 0.5)
    assert report["providers"][0]["versionChanged"] is True
    assert report["providers"][0]["classificationFlipRate"] == 1.0
    assert report["providers"][0]["alert"] is True


def test_provider_sentence_ranges_map_back_to_canonical_document() -> None:
    text = "First sentence.\n\nSecond sentence."
    paragraphs, offsets = paragraphs_for("sample1", text)
    result = {
        "provider": "Pangram", "providerModelVersion": "v1", "combinedRiskPercent": 60,
        "spans": [{"paragraphId": paragraphs[1]["id"], "start": 0, "end": 16, "score": 0.8}],
        "isMock": False, "latencyMs": 12, "status": "success", "error": None,
    }
    rows = prediction_rows(
        result, dataset_version="1.0.0", run_id="run", sample_id="sample1", offsets=offsets,
        created_at="2026-07-16T00:00:00Z",
    )
    assert rows[0]["score"] == 0.6
    assert text[rows[0]["spans"][0]["start"] : rows[0]["spans"][0]["end"]] == "Second sentence."
