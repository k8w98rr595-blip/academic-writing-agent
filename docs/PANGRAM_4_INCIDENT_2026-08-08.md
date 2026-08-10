# Pangram 4 normalized-text incident — 2026-08-08

## Scope

The owner explicitly initiated one real Pangram 4 detection for an 851-word synthetic, non-sensitive document. Paperlight displayed a sanitized `range_mismatch` failure: Pangram returned analyzed text that differed from the submitted string. No credential, raw provider response, raw task ID, session value, or test-paper body is recorded here.

## Root cause

The asynchronous task completed far enough to return analyzed text. Pangram's current official contract states that Pangram 4 may normalize submitted text before inference and that window offsets refer to the returned top-level `text`. Paperlight's adapter still required exact string equality before accepting any result. A safe provider normalization, such as collapsing paragraph-separator whitespace, was therefore rejected even though the result could have been mapped deterministically.

## Remediation

- Validate each provider window strictly against Pangram's returned text first.
- Accept only whitespace-only normalization: every non-whitespace Unicode code point must remain identical and in the same order.
- Build a monotonic boundary map from returned-text offsets to the submitted immutable document version.
- Revalidate every mapped range against the original text and stable paragraph boundaries.
- Continue to fail closed for content changes, out-of-range windows, overlaps, or any ambiguous mapping.
- Add an explicit warning when whitespace normalization was mapped successfully.
- Count a failed Pangram local-validation record as already submitted for the 24-hour same-content guard, preventing an accidental second charge after a completed provider task is rejected locally.

## Verification and operational status

- Provider contract tests cover successful whitespace normalization and unsafe content mutation.
- Existing exact-text, window, fraction, model-version, timeout, no-repeat, and sanitization checks remain active.
- No second real Pangram task was submitted during diagnosis or remediation.
- The original result cannot be recovered by Paperlight because only a SHA-256 task reference is persisted; this intentionally prevents later polling with a stored raw task ID.
- Whether the first provider task incurred a charge must be confirmed in Pangram's billing dashboard. Paperlight does not infer provider billing from a completed HTTP workflow.
- The production smoke workflow now validates an explicit expected detector mode. Its production default is `pangram` while the application runtime default remains `mock`; repository variable `PAPERLIGHT_EXPECTED_DETECTOR_MODE` can deliberately override the production expectation when modes change.

Official contract: [Pangram AI Detection](https://docs.pangram.com/api-reference/ai-detection).
