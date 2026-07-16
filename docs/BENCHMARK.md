# AI detector benchmark gate

The canonical benchmark implementation now lives in [`benchmark/`](../benchmark/README.md). Real detector activation and product claims require a frozen, independent dataset rather than tuning and validating on the same texts.

- Public development fixtures exercise the code but are contamination-exposed and non-claimable.
- Private evaluation samples require permission, de-identification, process evidence, and separation from rewrite models.
- The sealed final set is one-use, threshold-independent, and inaccessible to providers until an approved retention-controlled evaluation window.
- Reports must include discrimination, calibration, human false positives, AI false negatives, sentence/range evidence, groups, confidence intervals, agreement, threshold sensitivity, and version drift.
- A detector score is a probabilistic risk signal, not an authorship label or disciplinary judgment.

Use `benchmark/DATA_DICTIONARY.md`, `benchmark/GOVERNANCE.md`, and `benchmark/collection-plan.csv` as the data and sampling contracts.
