# Dataset and run versioning

Dataset manifests are append-only and use semantic versions.

- Major: label ontology, canonicalization, split policy, or metric interpretation changes incompatibly.
- Minor: new samples or a materially expanded population are added without changing existing records.
- Patch: a documented correction quarantines or supersedes a record without silently rewriting prior results.
- `-dev.N`: non-claimable development releases.

Every manifest has a canonical SHA-256 lock generated with `python -m benchmark.cli seal`. A lock mismatch is a hard failure. Fixes require a new manifest version and changelog entry; old files and reports remain available for reproduction.

Prediction files are immutable runs keyed by dataset version, `runId`, provider, and provider model version. Never append results from a different model deployment to an existing run. The `drift` command compares matched sample/provider rows and alerts on model-version changes, mean absolute score movement of at least 0.10, or threshold classification flips of at least 10%.

Reports record dataset version, manifest digest, random seed, bootstrap iterations, decision threshold, provider versions, Mock status, and coverage. Blind releases add a separately held release ID and are retired after their approved one-use evaluation.
