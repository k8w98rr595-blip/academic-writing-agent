# Paperlight AI Detector Benchmark

This directory evaluates detector behavior on a declared sample distribution. It does not manufacture a universal “accuracy” claim.

## Trust tiers

- `public_dev`: checked-in development fixtures. They may be known to vendors and are never evidence for marketing.
- `private_eval`: consented or commissioned coursework used for model comparison and threshold development. Bodies and manifests are Git-ignored.
- `blind_final`: a sealed, one-use final set held by an independent curator. Rewrite models never receive it; provider upload requires approved retention terms.

## Reproduce the development report

```powershell
.\.venv\Scripts\python.exe -m benchmark.cli validate --manifest benchmark/manifests/v1.0.0-dev.1.jsonl
.\.venv\Scripts\python.exe -m benchmark.cli evaluate --manifest benchmark/manifests/v1.0.0-dev.1.jsonl --predictions benchmark/predictions/mock-v1.0.0-dev.1.jsonl --output benchmark/reports/mock-v1.0.0-dev.1 --seed 20260716 --bootstrap 500
```

The output contains JSON, Markdown, and standalone HTML. Mock reports are visibly non-claimable and never produce a production threshold recommendation.

After server-only keys, data-processing terms, retention, and cost approval are in place, collect real results without routing any text through the rewrite model:

```powershell
$env:DETECTOR_DATA_PROCESSING_ACKNOWLEDGED = "1"
.\.venv\Scripts\python.exe -m benchmark.run_providers --manifest benchmark/manifests/private/v1.0.0.jsonl --output benchmark/predictions/private/dual-v1.0.0.jsonl --run-id dual-v1.0.0-2026-07 --mode dual --confirm-provider-upload
```

The command reads credentials only through the backend environment, never prints them, refuses to overwrite a run by default, and blocks blind-set uploads unless the separate one-use blind flags are supplied.

## Formal-scale sampling target

The first claim-eligible release should include at least 700 private-evaluation samples and 350 one-use blind samples, balanced across the seven discipline families and oversampled for the hybrid, translation, non-native-English, template, and technical-feature cases in `collection-plan.csv`. Threshold claims require at least 200 verified human and 200 verified AI documents in the applicable slice; hybrid performance is reported separately.

Freeze provider versions, prompts, preprocessing, dataset version, seed, and threshold policy before opening the blind set. If a provider changes its model, create a new run and use `drift` rather than overwriting prior predictions.

```powershell
.\.venv\Scripts\python.exe -m benchmark.cli drift --manifest benchmark/manifests/v1.0.0-dev.1.jsonl --previous benchmark/predictions/previous.jsonl --current benchmark/predictions/current.jsonl --output benchmark/reports/drift.json --threshold 0.5
```

## What this benchmark can support

The checked-in development report supports only the statement that Paperlight has a reproducible, versioned framework reporting overall, grouped, calibration, span, agreement, threshold, confidence-interval, and drift metrics. It cannot support a claim that Pangram, Copyleaks, Paperlight, or any threshold is accurate for students. After a representative private evaluation and untouched blind run, every claim must name the population, dataset version, provider/model version, threshold, 95% confidence interval, and observed human false-positive rate.

See `DATA_DICTIONARY.md` for labels, `GOVERNANCE.md` for authorization/privacy, `SAMPLING_PLAN.md` for formal quotas, and `VERSIONING.md` plus `CHANGELOG.md` for immutable releases.
