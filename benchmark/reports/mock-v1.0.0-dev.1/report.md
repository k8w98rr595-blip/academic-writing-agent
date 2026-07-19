# Paperlight AI Detector Benchmark Report

- **Dataset:** `1.0.0-dev.1`
- **Status:** development-only
- **Seed / bootstrap:** 20260716 / 500

> Detector scores are probabilistic risk signals. They are not authorship facts or academic-misconduct judgments.

## Technical summary

This run contains 4 active samples and 0 claim-eligible samples. Development-only or Mock results validate the evaluation pipeline, not detector performance.

## Provider comparison

| Provider | Version | Mock | n | AUROC (95% CI) | AUPRC (95% CI) | FPR @ threshold | FNR @ threshold | Brier | ECE |
|---|---|---:|---:|---|---|---:|---:|---:|---:|
| Mock Pangram | mock-pangram-v3 | yes | 4 | 0.375 [0.000, 1.000] | 0.500 [0.250, 1.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.315 [0.107, 0.522] | 0.197 [0.077, 0.753] |

## Threshold recommendation

Requires a claim-eligible private-evaluation slice with at least 200 verified human and 200 verified AI samples and real provider runs. Any candidate must then be frozen and confirmed on the untouched blind set.

## Group and span reporting

- **Mock Pangram**: sentence F1 0.372; range IoU 0.230. Groups with fewer than 10 samples are present as coverage counts but suppressed.
  - `discipline`: business_economics n=1 (suppressed), computer_engineering n=1 (suppressed), law_public_policy n=1 (suppressed), medicine_life_science n=1 (suppressed)
  - `level`: historical_reference n=2 (suppressed), synthetic_fixture n=2 (suppressed)
  - `writingAbility`: advanced n=2 (suppressed), unknown n=2 (suppressed)
  - `nativeEnglish`: not_applicable n=2 (suppressed), yes n=2 (suppressed)
  - `lengthBand`: short n=4 (suppressed)
  - `textType`: case_analysis n=1 (suppressed), historical_reference n=2 (suppressed), technical_report n=1 (suppressed)
  - `feature:formulas`: false n=2 (suppressed), true n=2 (suppressed)
  - `feature:citations`: false n=4 (suppressed)
  - `feature:tables`: false n=4 (suppressed)
  - `feature:abbreviations`: false n=2 (suppressed), true n=2 (suppressed)
  - `feature:specialistTerms`: true n=4 (suppressed)
  - `feature:templateDriven`: false n=3 (suppressed), true n=1 (suppressed)
  - `processLabel`: ai_generated n=2 (suppressed), human_independent n=2 (suppressed)

## Limitations

- Public development text may be present in provider training data and cannot establish contamination-free performance.
- The development corpus is too small and unrepresentative for product accuracy or threshold claims.
- Hybrid, translation, non-native-English, template-heavy, and all-discipline coverage must be populated with verified private/blind samples.
