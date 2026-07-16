from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark.cli import BenchmarkError, load_manifest


def paragraphs_for(sample_id: str, text: str) -> tuple[list[dict[str, str]], dict[str, int]]:
    paragraphs: list[dict[str, str]] = []
    offsets: dict[str, int] = {}
    cursor = 0
    for index, value in enumerate(text.split("\n\n")):
        paragraph_id = f"{sample_id}-p{index + 1:04d}"
        paragraphs.append({"id": paragraph_id, "text": value})
        offsets[paragraph_id] = cursor
        cursor += len(value) + 2
    return paragraphs, offsets


def prediction_rows(
    result: dict[str, Any], *, dataset_version: str, run_id: str, sample_id: str, offsets: dict[str, int], created_at: str
) -> list[dict[str, Any]]:
    rows = []
    for provider in result.get("providers", []):
        spans = []
        for span in provider.get("sentenceSpans", []):
            paragraph_id = span.get("paragraphId")
            if paragraph_id not in offsets:
                raise BenchmarkError("provider result referenced an unknown paragraph ID")
            spans.append({
                "start": offsets[paragraph_id] + int(span["start"]),
                "end": offsets[paragraph_id] + int(span["end"]),
                "score": float(span["score"]),
            })
        score = provider.get("overallScore")
        rows.append({
            "datasetVersion": dataset_version, "runId": run_id, "sampleId": sample_id,
            "provider": provider.get("provider") or provider.get("name"),
            "providerVersion": provider.get("providerModelVersion") or provider.get("modelVersion") or "unknown",
            "status": provider.get("status", "success"),
            "score": None if score is None else round(float(score) / 100, 6),
            "spans": spans, "isMock": bool(provider.get("isMock")),
            "latencyMs": int(provider.get("latencyMs") or 0), "createdAt": created_at,
            "errorCode": (provider.get("error") or {}).get("code"),
        })
    return rows


async def collect(args: argparse.Namespace) -> int:
    manifest, texts = load_manifest(args.manifest)
    active = [row for row in manifest if row["status"] == "active"]
    splits = {row["split"] for row in active}
    real = args.mode != "mock"
    if real and not args.confirm_provider_upload:
        raise BenchmarkError("real runs require --confirm-provider-upload after retention and cost approval")
    if "blind_final" in splits and not args.allow_blind_final:
        raise BenchmarkError("blind-final upload is blocked; use an approved one-use run and --allow-blind-final")
    if "blind_final" in splits and not args.blind_release_id:
        raise BenchmarkError("blind-final upload requires --blind-release-id for the evaluation audit record")
    if args.output.exists() and not args.force:
        raise BenchmarkError("prediction output already exists; use a new run ID/path or --force")
    os.environ["DETECTOR_MODE"] = args.mode
    from services.api.app.config import get_settings
    from services.api.app.providers.detectors import run_detection

    get_settings.cache_clear()
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    output: list[dict[str, Any]] = []
    for sample in sorted(active, key=lambda row: row["sampleId"]):
        if real and sample["governance"]["providerAccess"] == "never":
            raise BenchmarkError(f"{sample['sampleId']}: governance forbids provider access")
        paragraphs, offsets = paragraphs_for(sample["sampleId"], texts[sample["sampleId"]])
        result = await run_detection(paragraphs, idempotency_key=f"benchmark:{manifest[0]['datasetVersion']}:{args.run_id}:{sample['sampleId']}")
        output.extend(
            prediction_rows(
                result, dataset_version=manifest[0]["datasetVersion"], run_id=args.run_id,
                sample_id=sample["sampleId"], offsets=offsets, created_at=created_at,
            )
        )
    if real and any(row["isMock"] for row in output):
        raise BenchmarkError("real run returned Mock output; predictions were not written")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in output) + "\n"
    args.output.write_text(serialized, encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "rows": len(output), "mode": args.mode, "containsMock": any(row["isMock"] for row in output)}, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run Paperlight detector adapters against an approved benchmark manifest")
    result.add_argument("--manifest", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--run-id", required=True)
    result.add_argument("--mode", choices=("mock", "pangram", "copyleaks", "dual"), default="dual")
    result.add_argument("--confirm-provider-upload", action="store_true")
    result.add_argument("--allow-blind-final", action="store_true")
    result.add_argument("--blind-release-id")
    result.add_argument("--force", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(collect(parser().parse_args(argv)))
    except BenchmarkError as error:
        print(f"benchmark error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
