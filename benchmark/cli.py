from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .metrics import (
    auprc,
    auroc,
    bootstrap_ci,
    brier,
    drift_report,
    ece,
    provider_agreement,
    span_metrics,
    threshold_metrics,
)


WORD_PATTERN = re.compile(r"\b[A-Za-z]+(?:['’-][A-Za-z]+)*\b")
GROUP_FIELDS = ("discipline", "level", "writingAbility", "nativeEnglish", "lengthBand", "textType")
FEATURE_FIELDS = ("formulas", "citations", "tables", "abbreviations", "specialistTerms", "templateDriven")
DEFAULT_THRESHOLDS = tuple(round(value / 10, 1) for value in range(1, 10))


class BenchmarkError(ValueError):
    pass


def canonical_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def canonical_digest(rows: list[dict[str, Any]]) -> str:
    payload = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in sorted(rows, key=lambda item: item["sampleId"])
    ) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise BenchmarkError(f"{path}:{line_number}: invalid JSON") from error
        if not isinstance(value, dict):
            raise BenchmarkError(f"{path}:{line_number}: row must be an object")
        rows.append(value)
    return rows


def _require(row: dict[str, Any], keys: set[str], label: str) -> None:
    missing = sorted(keys - set(row))
    if missing:
        raise BenchmarkError(f"{label}: missing {', '.join(missing)}")


def _safe_body_path(benchmark_root: Path, relative: str, split: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise BenchmarkError("body path must be relative and cannot contain parent traversal")
    expected = {"public_dev": "public_dev", "private_eval": "private", "blind_final": "blind"}[split]
    parts = relative_path.as_posix().split("/")
    if len(parts) < 3 or parts[0] != "corpus" or parts[1] != expected:
        raise BenchmarkError(f"{split} body must stay under corpus/{expected}")
    resolved = (benchmark_root / relative_path).resolve()
    if benchmark_root.resolve() not in resolved.parents:
        raise BenchmarkError("body path escapes benchmark root")
    return resolved


def load_manifest(path: Path, *, verify_lock: bool = True) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows = read_jsonl(path)
    if not rows:
        raise BenchmarkError("manifest is empty")
    benchmark_root = path.parent.parent
    seen: set[str] = set()
    versions: set[str] = set()
    texts: dict[str, str] = {}
    for row in rows:
        _require(row, {"sampleId", "datasetVersion", "status", "split", "body", "provenance", "profile", "features", "gold", "governance"}, "sample")
        sample_id = row["sampleId"]
        if not isinstance(sample_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{5,63}", sample_id):
            raise BenchmarkError("invalid sampleId")
        if sample_id in seen:
            raise BenchmarkError(f"duplicate sampleId: {sample_id}")
        seen.add(sample_id)
        versions.add(row["datasetVersion"])
        if row["status"] != "active":
            continue
        body, governance, gold = row["body"], row["governance"], row["gold"]
        _require(body, {"path", "sha256", "encoding", "wordCount", "characterCount"}, sample_id)
        _require(governance, {"visibility", "claimEligible", "providerAccess", "rewriteModelAccess", "piiReviewed"}, sample_id)
        _require(gold, {"documentClass", "aiFraction", "aiSpans"}, sample_id)
        if not governance["piiReviewed"]:
            raise BenchmarkError(f"{sample_id}: PII review is required")
        if row["split"] == "public_dev" and governance["claimEligible"]:
            raise BenchmarkError(f"{sample_id}: public development samples cannot be claim eligible")
        if row["split"] == "blind_final" and governance["rewriteModelAccess"] != "never":
            raise BenchmarkError(f"{sample_id}: blind samples must never reach rewrite models")
        if not isinstance(body["path"], str):
            raise BenchmarkError(f"{sample_id}: active sample requires a body path")
        body_path = _safe_body_path(benchmark_root, body["path"], row["split"])
        if not body_path.is_file():
            raise BenchmarkError(f"{sample_id}: body file is missing")
        text = canonical_text(body_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != body["sha256"]:
            raise BenchmarkError(f"{sample_id}: body SHA-256 mismatch")
        if len(text) != body["characterCount"] or len(WORD_PATTERN.findall(text)) != body["wordCount"]:
            raise BenchmarkError(f"{sample_id}: body counts do not match manifest")
        ai_fraction = gold["aiFraction"]
        if not isinstance(ai_fraction, (int, float)) or isinstance(ai_fraction, bool) or not 0 <= ai_fraction <= 1:
            raise BenchmarkError(f"{sample_id}: aiFraction must be between 0 and 1")
        for span in gold["aiSpans"]:
            if not isinstance(span, dict) or not isinstance(span.get("start"), int) or not isinstance(span.get("end"), int):
                raise BenchmarkError(f"{sample_id}: invalid gold span")
            if span["start"] < 0 or span["end"] <= span["start"] or span["end"] > len(text):
                raise BenchmarkError(f"{sample_id}: gold span is out of range")
        if gold["documentClass"] == "human" and (ai_fraction != 0 or gold["aiSpans"]):
            raise BenchmarkError(f"{sample_id}: human label conflicts with AI evidence")
        if gold["documentClass"] == "ai" and ai_fraction != 1:
            raise BenchmarkError(f"{sample_id}: fully AI label requires aiFraction=1")
        texts[sample_id] = text
    if len(versions) != 1:
        raise BenchmarkError("manifest must contain exactly one dataset version")
    digest = canonical_digest(rows)
    lock_path = path.with_suffix(".sha256")
    if verify_lock and lock_path.exists():
        expected = lock_path.read_text(encoding="utf-8").strip().split()[0]
        if expected != digest:
            raise BenchmarkError("manifest lock digest mismatch; issue a new dataset version instead of editing in place")
    return rows, texts


def load_predictions(path: Path, *, dataset_version: str, texts: dict[str, str]) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        _require(row, {"datasetVersion", "runId", "sampleId", "provider", "providerVersion", "status", "score", "spans", "isMock", "latencyMs", "createdAt"}, "prediction")
        if row["datasetVersion"] != dataset_version:
            raise BenchmarkError("prediction datasetVersion does not match manifest")
        if row["sampleId"] not in texts:
            raise BenchmarkError(f"prediction references unknown or inactive sample: {row['sampleId']}")
        key = (row["runId"], row["provider"], row["sampleId"])
        if key in seen:
            raise BenchmarkError(f"duplicate prediction: {key}")
        seen.add(key)
        if row["status"] == "success":
            if not isinstance(row["score"], (int, float)) or isinstance(row["score"], bool) or not 0 <= row["score"] <= 1:
                raise BenchmarkError("successful prediction requires score between 0 and 1")
        elif row["score"] is not None:
            raise BenchmarkError("failed prediction cannot contain a score")
        for span in row["spans"]:
            if not isinstance(span, dict) or not all(key in span for key in ("start", "end", "score")):
                raise BenchmarkError("prediction span is invalid")
            if span["start"] < 0 or span["end"] <= span["start"] or span["end"] > len(texts[row["sampleId"]]):
                raise BenchmarkError("prediction span is out of range")
            if not 0 <= span["score"] <= 1:
                raise BenchmarkError("prediction span score is outside 0 to 1")
    return rows


def _provider_rows(
    provider_predictions: list[dict[str, Any]], sample_map: dict[str, dict[str, Any]], texts: dict[str, str]
) -> list[dict[str, Any]]:
    output = []
    for prediction in provider_predictions:
        if prediction["status"] != "success" or prediction["score"] is None:
            continue
        sample = sample_map[prediction["sampleId"]]
        output.append({
            "sampleId": prediction["sampleId"], "score": float(prediction["score"]),
            "label": 1 if sample["gold"]["documentClass"] == "ai" else 0 if sample["gold"]["documentClass"] == "human" else None,
            "target": float(sample["gold"]["aiFraction"]), "profile": sample["profile"], "features": sample["features"],
            "processLabel": sample["provenance"]["processLabel"], "claimEligible": sample["governance"]["claimEligible"],
            "text": texts[prediction["sampleId"]], "goldSpans": sample["gold"]["aiSpans"],
            "predictedSpans": prediction["spans"],
        })
    return output


def _document_summary(rows: list[dict[str, Any]], threshold: float, seed: int, bootstrap: int) -> dict[str, Any]:
    binary = [row for row in rows if row["label"] is not None]
    labels = [row["label"] for row in binary]
    scores = [row["score"] for row in binary]
    targets = [row["target"] for row in rows]
    all_scores = [row["score"] for row in rows]
    tuple_rows = [(row["label"], row["score"]) for row in binary]
    calibration_rows = [(row["target"], row["score"]) for row in rows]
    threshold_cis = {
        metric: bootstrap_ci(
            tuple_rows,
            lambda values, metric=metric: threshold_metrics([v[0] for v in values], [v[1] for v in values], threshold)[metric],
            seed=seed + 10 + index,
            iterations=bootstrap,
        )
        for index, metric in enumerate(("accuracy", "precision", "recall", "f1", "fpr", "fnr"))
    }
    return {
        "n": len(rows), "binaryN": len(binary), "humanN": labels.count(0), "aiN": labels.count(1),
        "auroc": bootstrap_ci(tuple_rows, lambda values: auroc([v[0] for v in values], [v[1] for v in values]), seed=seed + 1, iterations=bootstrap),
        "auprc": bootstrap_ci(tuple_rows, lambda values: auprc([v[0] for v in values], [v[1] for v in values]), seed=seed + 2, iterations=bootstrap),
        "brier": bootstrap_ci(calibration_rows, lambda values: brier([v[0] for v in values], [v[1] for v in values]), seed=seed + 3, iterations=bootstrap),
        "ece": bootstrap_ci(calibration_rows, lambda values: ece([v[0] for v in values], [v[1] for v in values]), seed=seed + 4, iterations=bootstrap),
        "atThreshold": threshold_metrics(labels, scores, threshold),
        "atThreshold95CI": threshold_cis,
        "thresholdCurve": [threshold_metrics(labels, scores, item) for item in DEFAULT_THRESHOLDS],
        "softTargetN": len(targets), "calibrationScoreN": len(all_scores),
    }


def _group_results(
    rows: list[dict[str, Any]], threshold: float, *, seed: int, bootstrap: int
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    extractors = {
        **{field: lambda row, field=field: row["profile"][field] for field in GROUP_FIELDS},
        **{f"feature:{field}": lambda row, field=field: str(row["features"][field]).lower() for field in FEATURE_FIELDS},
        "processLabel": lambda row: row["processLabel"],
    }
    for field, extractor in extractors.items():
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(extractor(row))].append(row)
        output[field] = []
        for group_index, (value, members) in enumerate(sorted(groups.items())):
            group_seed = seed + int(hashlib.sha256(f"{field}:{value}:{group_index}".encode()).hexdigest()[:8], 16)
            output[field].append({
                "value": value, "n": len(members), "suppressed": len(members) < 10,
                "metrics": None if len(members) < 10 else _document_summary(
                    members, threshold, group_seed, bootstrap
                ),
            })
    return output


def evaluate(
    manifest: list[dict[str, Any]], texts: dict[str, str], predictions: list[dict[str, Any]], *, threshold: float, seed: int, bootstrap: int
) -> dict[str, Any]:
    active = [row for row in manifest if row["status"] == "active"]
    sample_map = {row["sampleId"]: row for row in active}
    dataset_version = next(iter({row["datasetVersion"] for row in manifest}))
    by_provider: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prediction in predictions:
        by_provider[prediction["provider"]].append(prediction)
    providers = []
    for provider_index, (provider, provider_predictions) in enumerate(sorted(by_provider.items())):
        rows = _provider_rows(provider_predictions, sample_map, texts)
        failures = Counter(row.get("errorCode") or "unknown" for row in provider_predictions if row["status"] == "failed")
        span_cis = {
            metric: bootstrap_ci(
                rows,
                lambda values, metric=metric: (
                    span_metrics(values, threshold)["sentence"][metric]
                    if metric in {"precision", "recall", "f1"}
                    else span_metrics(values, threshold)["rangeOverlap"][metric]
                ),
                seed=seed + provider_index * 100 + 70 + index,
                iterations=bootstrap,
            )
            for index, metric in enumerate(("precision", "recall", "f1", "iou", "dice"))
        }
        providers.append({
            "provider": provider,
            "providerVersions": sorted({row["providerVersion"] for row in provider_predictions}),
            "isMock": any(row["isMock"] for row in provider_predictions),
            "attempted": len(provider_predictions), "successful": len(rows), "failures": dict(sorted(failures.items())),
            "document": _document_summary(rows, threshold, seed + provider_index * 100, bootstrap),
            "spans": span_metrics(rows, threshold), "span95CI": span_cis,
            "groups": _group_results(rows, threshold, seed=seed + provider_index * 1000, bootstrap=bootstrap),
        })
    all_claim_eligible = bool(active) and all(row["governance"]["claimEligible"] for row in active)
    enough_claim_samples = sum(row["gold"]["documentClass"] == "human" for row in active) >= 200 and sum(row["gold"]["documentClass"] == "ai" for row in active) >= 200
    all_real = bool(predictions) and not any(row["isMock"] for row in predictions)
    candidate_allowed = all_claim_eligible and enough_claim_samples and all_real and set(row["split"] for row in active) == {"private_eval"}
    by_provider_recommendations: list[dict[str, Any]] = []
    if candidate_allowed:
        for provider_index, (provider, provider_predictions) in enumerate(sorted(by_provider.items())):
            rows = [row for row in _provider_rows(provider_predictions, sample_map, texts) if row["claimEligible"] and row["label"] is not None]
            labels = [row["label"] for row in rows]
            scores = [row["score"] for row in rows]
            candidates = [threshold_metrics(labels, scores, round(value / 100, 2)) for value in range(5, 100, 5)]
            selected = min(candidates, key=lambda row: ((5 * row["fp"] + row["fn"]) / len(rows), row["fpr"] or 0, -row["threshold"]))
            tuples = list(zip(labels, scores, strict=True))
            fpr_ci = bootstrap_ci(
                tuples,
                lambda values, t=selected["threshold"]: threshold_metrics([v[0] for v in values], [v[1] for v in values], t)["fpr"],
                seed=seed + 5000 + provider_index * 10,
                iterations=bootstrap,
            )
            fnr_ci = bootstrap_ci(
                tuples,
                lambda values, t=selected["threshold"]: threshold_metrics([v[0] for v in values], [v[1] for v in values], t)["fnr"],
                seed=seed + 5001 + provider_index * 10,
                iterations=bootstrap,
            )
            by_provider_recommendations.append({
                "provider": provider, "threshold": selected["threshold"], "applicableSampleCount": len(rows),
                "humanCount": labels.count(0), "aiCount": labels.count(1), "falsePositiveCostWeight": 5,
                "falseNegativeCostWeight": 1, "fpr95CI": fpr_ci, "fnr95CI": fnr_ci,
                "status": "private-evaluation candidate; freeze and confirm on the untouched blind set",
            })
    threshold_recommendation = {
        "available": candidate_allowed,
        "byProvider": by_provider_recommendations,
        "reason": (
            "Requires a claim-eligible private-evaluation slice with at least 200 verified human and 200 verified AI samples and real provider runs. Any candidate must then be frozen and confirmed on the untouched blind set."
            if not candidate_allowed else
            "Candidates minimize 5× false positives + 1× false negatives on the named private-evaluation slice; they are not production thresholds until blind confirmation."
        ),
        "falsePositiveCostWeight": 5, "falseNegativeCostWeight": 1,
    }
    coverage = {
        "activeSamples": len(active), "claimEligibleSamples": sum(row["governance"]["claimEligible"] for row in active),
        "splits": dict(sorted(Counter(row["split"] for row in active).items())),
        "classes": dict(sorted(Counter(row["gold"]["documentClass"] for row in active).items())),
        "processLabels": dict(sorted(Counter(row["provenance"]["processLabel"] for row in active).items())),
        "disciplines": dict(sorted(Counter(row["profile"]["discipline"] for row in active).items())),
    }
    return {
        "reportSchemaVersion": "1.0.0", "datasetVersion": dataset_version, "manifestDigest": canonical_digest(manifest),
        "seed": seed, "bootstrapIterations": bootstrap, "decisionThreshold": threshold,
        "claimStatus": "development-only" if not all_claim_eligible or not all_real else "eligible-pending-blind-review",
        "disclaimer": "Detector scores are probabilistic risk signals. They are not authorship facts or academic-misconduct judgments.",
        "coverage": coverage, "providers": providers,
        "providerAgreement": provider_agreement(predictions, threshold),
        "thresholdRecommendation": threshold_recommendation,
        "limitations": [
            "Public development text may be present in provider training data and cannot establish contamination-free performance.",
            "The development corpus is too small and unrepresentative for product accuracy or threshold claims.",
            "Hybrid, translation, non-native-English, template-heavy, and all-discipline coverage must be populated with verified private/blind samples.",
        ],
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paperlight AI Detector Benchmark Report", "",
        f"- **Dataset:** `{report['datasetVersion']}`",
        f"- **Status:** {report['claimStatus']}",
        f"- **Seed / bootstrap:** {report['seed']} / {report['bootstrapIterations']}", "",
        f"> {report['disclaimer']}", "",
        "## Technical summary", "",
        f"This run contains {report['coverage']['activeSamples']} active samples and {report['coverage']['claimEligibleSamples']} claim-eligible samples. "
        "Development-only or Mock results validate the evaluation pipeline, not detector performance.", "",
        "## Provider comparison", "",
        "| Provider | Version | Mock | n | AUROC (95% CI) | AUPRC (95% CI) | FPR @ threshold | FNR @ threshold | Brier | ECE |",
        "|---|---|---:|---:|---|---|---:|---:|---:|---:|",
    ]
    for provider in report["providers"]:
        document = provider["document"]
        auroc_row, auprc_row = document["auroc"], document["auprc"]
        auroc_text = f"{_fmt(auroc_row['estimate'])} [{_fmt(auroc_row['low'])}, {_fmt(auroc_row['high'])}]"
        auprc_text = f"{_fmt(auprc_row['estimate'])} [{_fmt(auprc_row['low'])}, {_fmt(auprc_row['high'])}]"
        at = document["atThreshold"]
        at_ci = document["atThreshold95CI"]
        lines.append(
            f"| {provider['provider']} | {', '.join(provider['providerVersions'])} | {'yes' if provider['isMock'] else 'no'} | {provider['successful']} | "
            f"{auroc_text} | {auprc_text} | {_fmt(at['fpr'])} [{_fmt(at_ci['fpr']['low'])}, {_fmt(at_ci['fpr']['high'])}] | "
            f"{_fmt(at['fnr'])} [{_fmt(at_ci['fnr']['low'])}, {_fmt(at_ci['fnr']['high'])}] | "
            f"{_fmt(document['brier']['estimate'])} [{_fmt(document['brier']['low'])}, {_fmt(document['brier']['high'])}] | "
            f"{_fmt(document['ece']['estimate'])} [{_fmt(document['ece']['low'])}, {_fmt(document['ece']['high'])}] |"
        )
    lines.extend(["", "## Threshold recommendation", "", report["thresholdRecommendation"]["reason"], "", "## Group and span reporting", ""])
    for provider in report["providers"]:
        span = provider["spans"]
        lines.append(
            f"- **{provider['provider']}**: sentence F1 {_fmt(span['sentence']['f1'])}; range IoU {_fmt(span['rangeOverlap']['iou'])}. "
            "Groups with fewer than 10 samples are present as coverage counts but suppressed."
        )
        for field, groups in provider["groups"].items():
            coverage = ", ".join(f"{group['value']} n={group['n']}{' (suppressed)' if group['suppressed'] else ''}" for group in groups)
            lines.append(f"  - `{field}`: {coverage}")
    lines.extend(["", "## Limitations", ""] + [f"- {item}" for item in report["limitations"]])
    return "\n".join(lines) + "\n"


def render_html(report: dict[str, Any], markdown: str) -> str:
    rows = []
    group_rows = []
    for provider in report["providers"]:
        doc, at = provider["document"], provider["document"]["atThreshold"]
        rows.append(
            "<tr>" + "".join(
                f"<td>{html.escape(str(value))}</td>" for value in (
                    provider["provider"], ", ".join(provider["providerVersions"]), "yes" if provider["isMock"] else "no",
                    provider["successful"],
                    f"{_fmt(doc['auroc']['estimate'])} [{_fmt(doc['auroc']['low'])}, {_fmt(doc['auroc']['high'])}]",
                    f"{_fmt(doc['auprc']['estimate'])} [{_fmt(doc['auprc']['low'])}, {_fmt(doc['auprc']['high'])}]",
                    f"{_fmt(at['fpr'])} [{_fmt(doc['atThreshold95CI']['fpr']['low'])}, {_fmt(doc['atThreshold95CI']['fpr']['high'])}]",
                    f"{_fmt(at['fnr'])} [{_fmt(doc['atThreshold95CI']['fnr']['low'])}, {_fmt(doc['atThreshold95CI']['fnr']['high'])}]",
                    f"{_fmt(doc['brier']['estimate'])} [{_fmt(doc['brier']['low'])}, {_fmt(doc['brier']['high'])}]",
                    f"{_fmt(doc['ece']['estimate'])} [{_fmt(doc['ece']['low'])}, {_fmt(doc['ece']['high'])}]",
                )
            ) + "</tr>"
        )
        for field, groups in provider["groups"].items():
            for group in groups:
                group_rows.append(
                    "<tr>" + "".join(
                        f"<td>{html.escape(str(value))}</td>" for value in (
                            provider["provider"], field, group["value"], group["n"],
                            "suppressed (n<10)" if group["suppressed"] else _fmt(group["metrics"]["auroc"]["estimate"]),
                            "suppressed (n<10)" if group["suppressed"] else _fmt(group["metrics"]["atThreshold"]["fpr"]),
                        )
                    ) + "</tr>"
                )
    limitations = "".join(f"<li>{html.escape(item)}</li>" for item in report["limitations"])
    mock_banner = "<div class='banner'>DEVELOPMENT / MOCK REPORT — NOT VALID FOR PRODUCT CLAIMS</div>" if report["claimStatus"] == "development-only" else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Paperlight AI Detector Benchmark Report</title><style>
body{{font:16px/1.55 system-ui,sans-serif;color:#182238;background:#f4f7fb;margin:0}}main{{max-width:1100px;margin:32px auto;background:white;padding:36px;border:1px solid #dce4ef}}h1,h2{{line-height:1.2}}.banner{{background:#fff3cd;border:1px solid #e1b847;padding:12px;font-weight:700}}.meta{{color:#53647e}}table{{width:100%;border-collapse:collapse;overflow:auto;display:block}}th,td{{border:1px solid #dce4ef;padding:8px;text-align:left;white-space:nowrap}}th{{background:#eef4ff}}code{{word-break:break-all}}@media(max-width:600px){{main{{margin:0;padding:20px;border:0}}}}
</style></head><body><main>{mock_banner}<h1>Paperlight AI Detector Benchmark Report</h1><p class="meta">Dataset {html.escape(report['datasetVersion'])} · seed {report['seed']} · {report['bootstrapIterations']} bootstrap replicates</p><p><strong>{html.escape(report['disclaimer'])}</strong></p><h2>Technical summary</h2><p>This run has {report['coverage']['activeSamples']} active samples and {report['coverage']['claimEligibleSamples']} claim-eligible samples. Mock results exercise the framework only.</p><h2>Provider comparison</h2><table><thead><tr><th>Provider</th><th>Version</th><th>Mock</th><th>n</th><th>AUROC</th><th>AUPRC</th><th>FPR</th><th>FNR</th><th>Brier</th><th>ECE</th></tr></thead><tbody>{''.join(rows)}</tbody></table><h2>Group coverage</h2><p>Small cells are shown as coverage counts but their metrics are suppressed to protect privacy and avoid unstable claims.</p><table><thead><tr><th>Provider</th><th>Dimension</th><th>Group</th><th>n</th><th>AUROC</th><th>FPR</th></tr></thead><tbody>{''.join(group_rows)}</tbody></table><h2>Threshold recommendation</h2><p>{html.escape(report['thresholdRecommendation']['reason'])}</p><h2>Limitations</h2><ul>{limitations}</ul><details><summary>Machine-readable narrative snapshot</summary><pre>{html.escape(markdown)}</pre></details></main></body></html>"""


def write_report(report: dict[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    (output / "report.json").write_text(json_text, encoding="utf-8", newline="\n")
    (output / "report.md").write_text(markdown, encoding="utf-8", newline="\n")
    (output / "report.html").write_text(render_html(report, markdown), encoding="utf-8", newline="\n")


def command_validate(args: argparse.Namespace) -> int:
    rows, texts = load_manifest(args.manifest)
    print(json.dumps({"valid": True, "datasetVersion": rows[0]["datasetVersion"], "samples": len(texts), "manifestDigest": canonical_digest(rows)}, indent=2))
    return 0


def command_seal(args: argparse.Namespace) -> int:
    rows, _ = load_manifest(args.manifest, verify_lock=False)
    digest = canonical_digest(rows)
    lock = args.manifest.with_suffix(".sha256")
    value = f"{digest}  {args.manifest.name}\n"
    if lock.exists() and lock.read_text(encoding="utf-8") != value and not args.force:
        raise BenchmarkError("lock exists with a different digest; issue a new version or pass --force only for an unsealed development manifest")
    lock.write_text(value, encoding="utf-8", newline="\n")
    print(str(lock))
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    manifest, texts = load_manifest(args.manifest)
    version = manifest[0]["datasetVersion"]
    predictions = load_predictions(args.predictions, dataset_version=version, texts=texts)
    report = evaluate(manifest, texts, predictions, threshold=args.threshold, seed=args.seed, bootstrap=args.bootstrap)
    write_report(report, args.output)
    print(json.dumps({"output": str(args.output), "claimStatus": report["claimStatus"], "providers": len(report["providers"])}, indent=2))
    return 0


def command_drift(args: argparse.Namespace) -> int:
    manifest, texts = load_manifest(args.manifest)
    version = manifest[0]["datasetVersion"]
    previous = load_predictions(args.previous, dataset_version=version, texts=texts)
    current = load_predictions(args.current, dataset_version=version, texts=texts)
    report = {"datasetVersion": version, **drift_report(previous, current, args.threshold)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(str(args.output))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Paperlight independent AI detector benchmark")
    commands = root.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--manifest", type=Path, required=True)
    validate.set_defaults(handler=command_validate)
    seal = commands.add_parser("seal")
    seal.add_argument("--manifest", type=Path, required=True)
    seal.add_argument("--force", action="store_true")
    seal.set_defaults(handler=command_seal)
    evaluate_command = commands.add_parser("evaluate")
    evaluate_command.add_argument("--manifest", type=Path, required=True)
    evaluate_command.add_argument("--predictions", type=Path, required=True)
    evaluate_command.add_argument("--output", type=Path, required=True)
    evaluate_command.add_argument("--threshold", type=float, default=0.5)
    evaluate_command.add_argument("--seed", type=int, default=20260716)
    evaluate_command.add_argument("--bootstrap", type=int, default=1000)
    evaluate_command.set_defaults(handler=command_evaluate)
    drift = commands.add_parser("drift")
    drift.add_argument("--manifest", type=Path, required=True)
    drift.add_argument("--previous", type=Path, required=True)
    drift.add_argument("--current", type=Path, required=True)
    drift.add_argument("--output", type=Path, required=True)
    drift.add_argument("--threshold", type=float, default=0.5)
    drift.set_defaults(handler=command_drift)
    return root


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        if hasattr(args, "threshold") and not 0 <= args.threshold <= 1:
            raise BenchmarkError("threshold must be between 0 and 1")
        if hasattr(args, "bootstrap") and not 0 <= args.bootstrap <= 100_000:
            raise BenchmarkError("bootstrap must be between 0 and 100000")
        return args.handler(args)
    except BenchmarkError as error:
        print(f"benchmark error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
