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
| Mock Primary | mock-v2 | yes | 4 | 0.750 [0.000, 1.000] | 0.833 [0.333, 1.000] | 0.500 [0.000, 1.000] | 0.000 [0.000, 0.000] | 0.179 [0.034, 0.398] | 0.362 [0.182, 0.588] |
| Mock Review | mock-v2 | yes | 4 | 0.750 [0.000, 1.000] | 0.833 [0.333, 1.000] | 0.000 [0.000, 0.000] | 0.500 [0.000, 1.000] | 0.171 [0.051, 0.289] | 0.143 [0.055, 0.503] |

## Threshold recommendation

Requires a claim-eligible private-evaluation slice with at least 200 verified human and 200 verified AI samples and real provider runs. Any candidate must then be frozen and confirmed on the untouched blind set.

## Group and span reporting

- **Mock Primary**: sentence F1 0.969; range IoU 0.898. Groups with fewer than 10 samples are present as coverage counts but suppressed.
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
- **Mock Review**: sentence F1 0.681; range IoU 0.492. Groups with fewer than 10 samples are present as coverage counts but suppressed.
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
