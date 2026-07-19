# Provider setup

Paperlight defaults to `DETECTOR_MODE=mock`. The only active detection modes are `mock` and `pangram`.

## DeepSeek V4 revision loop

Paperlight uses `deepseek-v4-pro` to prepare a reviewable patch and `deepseek-v4-flash` for an independent semantic-safety decision. Deterministic server checks still reject changes to citations, numbers, quotations, URLs, formulas, abbreviations, and protected terms. The model never writes directly into the document.

```dotenv
REWRITE_MODE=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=<configure-in-Railway-api-service>
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_VALIDATOR_MODEL=deepseek-v4-flash
```

`DEEPSEEK_API_KEY` belongs only in the Railway backend service. It must not be placed in GitHub Pages variables, any `NEXT_PUBLIC_*` value, source control, screenshots, or chat.

## Pangram detection

On 2026-07-19 Pangram's [official AI Detection documentation](https://docs.pangram.com/api-reference/ai-detection) identifies the current contract as:

1. `POST https://text.external-api.pangram.com/task` with the server-only `x-api-key` header and `{ "text": ..., "public_dashboard_link": false }`.
2. Poll `GET https://text.external-api.pangram.com/task/{task_id}` until `STAGE_SUCCESS` or `STAGE_FAILED`.
3. Read versioned `fraction_ai`, `fraction_ai_assisted`, `fraction_human`, `prediction_short`, and `windows` from a successful response.

Pangram's [deprecated endpoint page](https://docs.pangram.com/api-reference/deprecated-endpoints) now lists synchronous `POST https://text.api.pangram.com/v3` as legacy. Paperlight therefore uses the supported async API while preserving Pangram's V3/3.x model result fields.

```dotenv
DETECTOR_MODE=mock
DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=0
PANGRAM_API_URL=https://text.external-api.pangram.com
PANGRAM_API_KEY=<configure-in-Railway-api-service>
PANGRAM_POLL_INTERVAL_SECONDS=0.75
PANGRAM_MAX_POLL_SECONDS=45
PROVIDER_TIMEOUT_SECONDS=45
```

### Railway activation order

1. In the Railway `api` service, add `PANGRAM_API_KEY` as a private backend Variable. Do not reveal or copy its value during verification.
2. Add `PANGRAM_API_URL=https://text.external-api.pangram.com`, but keep `DETECTOR_MODE=mock` and `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=0`.
3. Redeploy and confirm `/api/health` still reports `detector: mock`.
4. Confirm Pangram's current processing region, retention/deletion, no-training position, commercial terms, rate limits, and budget controls in writing.
5. In one planned deployment, set `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=1` and `DETECTOR_MODE=pangram`.
6. Run `python scripts/acceptance_real_detectors.py --confirm-cost` with owner credentials supplied only through local process environment variables. The script creates and deletes one synthetic paper and performs exactly one real Pangram submission.
7. If acceptance fails, restore `DETECTOR_MODE=mock`. Rotate the key only when exposure is suspected; do not print it while troubleshooting.

The task-creation POST is intentionally sent once. Paperlight does not automatically repeat an ambiguous or timed-out paid submission. Polling GET requests use bounded retries because they do not create a new task.
