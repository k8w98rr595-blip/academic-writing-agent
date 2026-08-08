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
PAID_CALL_HOURLY_WARNING=10
PAID_CALL_HOURLY_HARD_LIMIT=20
PROVIDER_FAILURE_BREAKER_THRESHOLD=5
PROVIDER_BREAKER_SECONDS=900
PROVIDER_USAGE_RETENTION_DAYS=30
```

`DEEPSEEK_API_KEY` belongs only in the Railway backend service. It must not be placed in GitHub Pages variables, any `NEXT_PUBLIC_*` value, source control, screenshots, or chat.

The application reserves two paid-call slots before each DeepSeek proposal—one for generation and one for semantic validation—and finalizes them with provider-reported token counts when available. Exact duplicate requests are blocked by hashed idempotency metadata; the raw instruction and passage are never stored in usage records.

## Pangram detection

On 2026-08-08 Pangram's official documentation identifies the current contract as:

1. Discover account entitlements with `GET https://text.external-api.pangram.com/models` and the server-only `x-api-key` header.
2. Require the returned catalog to contain `pangram-4`, then submit exactly one `POST https://text.external-api.pangram.com/task` with `{ "text": ..., "model": "pangram-4", "public_dashboard_link": false }`.
3. Poll only that task with `GET https://text.external-api.pangram.com/task/{task_id}` until `STAGE_SUCCESS` or `STAGE_FAILED`.
4. Require a returned `version` beginning with `4.` and validate all fractions, Pangram 4 window fields, text and offsets before saving any result.

Pangram's [deprecated endpoint page](https://docs.pangram.com/api-reference/deprecated-endpoints) lists synchronous `POST https://text.api.pangram.com/v3` as legacy. Model discovery is account-aware, so Paperlight does not assume `default` means Pangram 4. See [API overview](https://docs.pangram.com/api-reference/introduction), [Models](https://docs.pangram.com/api-reference/models), and [AI Detection](https://docs.pangram.com/api-reference/ai-detection).

```dotenv
DETECTOR_MODE=mock
DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=0
PANGRAM_PAID_CALLS_ENABLED=0
PANGRAM_API_BASE_URL=https://text.external-api.pangram.com
PANGRAM_API_KEY=<configure-in-Railway-api-service>
PANGRAM_MODEL=pangram-4
PANGRAM_POLL_INTERVAL_SECONDS=0.75
PANGRAM_MAX_POLL_SECONDS=45
PANGRAM_HOURLY_WARNING=1
PANGRAM_HOURLY_HARD_LIMIT=2
PANGRAM_DAILY_HARD_LIMIT=4
PANGRAM_MAX_CONCURRENT_CALLS=1
PANGRAM_RESERVATION_TTL_SECONDS=900
PROVIDER_TIMEOUT_SECONDS=45
```

### Railway activation order

1. In the Railway `api` service, add `PANGRAM_API_KEY` as a private backend Variable. Do not reveal or copy its value during verification.
2. Add the non-secret variables above, but keep `DETECTOR_MODE=mock`, `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=0`, and `PANGRAM_PAID_CALLS_ENABLED=0`.
3. Redeploy and confirm `/api/health` still reports `detector: mock`.
4. Confirm Pangram's current processing region, retention/deletion, no-training position, commercial terms, rate limits, and budget controls in writing.
5. Only after separate owner approval, set `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=1`, `PANGRAM_PAID_CALLS_ENABLED=1`, and `DETECTOR_MODE=pangram` in one planned deployment.
6. Run `python scripts/acceptance_real_detectors.py --confirm-cost` with owner credentials supplied only through local process environment variables. The script creates and deletes one synthetic paper and performs exactly one real Pangram submission.
7. If acceptance fails, restore `DETECTOR_MODE=mock`. Rotate the key only when exposure is suspected; do not print it while troubleshooting.

The task-creation POST is intentionally sent once. Paperlight does not automatically repeat an ambiguous or timed-out paid submission. Polling GET requests use bounded retries because they do not create a new task.

After activation, confirm the owner-only `/api/v1/provider-usage/summary` endpoint records one Pangram detection operation and shows no open breaker. This application summary is not a bill; reconcile it against Pangram's dashboard after the single approved synthetic run.
