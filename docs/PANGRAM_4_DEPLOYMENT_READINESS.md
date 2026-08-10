# Pangram 4 deployment readiness

Verified against Pangram's public official material on 2026-08-08 (Asia/Shanghai). This record contains no API key, password, session, cookie, paper text, or raw Pangram task ID.

## Official contract record

| Topic | Verified statement | Source |
|---|---|---|
| Base URL and auth | AI detection uses `https://text.external-api.pangram.com`; every request uses `x-api-key`. | [API Overview](https://docs.pangram.com/api-reference/introduction) |
| Model choice | Call `GET /models`; pass one returned selector as `model`. The catalog is entitlement- and availability-aware. `pangram-4` is the documented selector. | [Models](https://docs.pangram.com/api-reference/models) |
| Realtime flow | `POST /task`, then `GET /task/{task_id}` until `STAGE_SUCCESS` or `STAGE_FAILED`. | [AI Detection](https://docs.pangram.com/api-reference/ai-detection) |
| Pangram 4 result | Example `version` is `4.0`; top-level fractions are AI-generated, AI-assisted and human. Windows use `AI-Generated`, `AI-Assisted`, `Human Written` and include offsets, confidence, `is_humanized` and `humanizer_score`. | [AI Detection](https://docs.pangram.com/api-reference/ai-detection) |
| Legacy V3 | Synchronous `POST https://text.api.pangram.com/v3` is deprecated in favor of async tasks. | [Deprecated Endpoints](https://docs.pangram.com/api-reference/deprecated-endpoints) |
| Errors | Official codes include 400, 401, 402, 403, 404, 413, 422, 429, 500 and 503. | [API Overview](https://docs.pangram.com/api-reference/introduction) |
| Public rate | Pangram advertises 5 QPS for realtime API checks. Paperlight imposes much lower owner-only limits. | [API solution](https://www.pangram.com/solutions/api) |
| Pricing | Pangram 4 is displayed at USD 0.05 per 100 words; Pangram 3 at USD 0.05 per 1,000 words; Bulk receives a 20% discount. | [API solution](https://www.pangram.com/solutions/api) |
| Languages | Pangram advertises detection in more than 20 languages. Paperlight v1 remains limited to English coursework. | [Multilingual detection](https://www.pangram.com/solutions/multilingual) |

The official API reference does not publish a numeric single-task hard minimum or maximum text length. Pangram marketing says it can work on text as short as 75 words, but this is not treated as the API validation contract. Paperlight continues to enforce 800–5,000 English words.

## Privacy and retention conclusion

Pangram's [Privacy Policy](https://www.pangram.com/privacy-policy) says submissions are not used to train or improve its models, registered-customer submissions and metadata are collected, queries can be deleted from history while a billing/analytics event remains, and registered-account content is deleted within 30 days after account closure or according to the customer agreement. It also says processing may occur in the United States. Pangram's API page describes zero-data-retention as an Enterprise option to discuss, not a default self-serve guarantee.

Therefore `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED` must remain `0` until the owner reviews the terms that actually apply to the account and decides whether ordinary registered-account handling is acceptable. Single realtime task/result retention, the exact delete mechanism for API tasks, and whether the account has zero-retention are still **待确认**.

## Billing gate for the first acceptance

- Published estimate for 1,500 English words on Pangram 4 realtime: 15 started 100-word units × USD 0.05 = **USD 0.75**.
- Published estimate for the planned 800–1,000-word synthetic acceptance: **USD 0.40–0.50**, assuming the public realtime unit rule applies.
- The public page does not explicitly assign a separate fee to `POST /task` versus polling `GET /task/{task_id}`. Paperlight treats only task creation as potentially billable and never creates a second task after an ambiguous timeout, but this billing detail remains **待确认** before the paid run.
- The public page conflicts on minimum funding: prose says USD 5–2,000 while the visible card starts at USD 25. Confirm in the authenticated dashboard; do not purchase or enable auto-refill during setup.
- The first production acceptance is limited to exactly one synthetic task. It requires a separate owner message: `允许进行一次 Pangram 真实付费验收`.

## Safe activation sequence

1. Store the Key only in Railway `api` Variables. Keep `DETECTOR_MODE=mock`, `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=0`, `PANGRAM_PAID_CALLS_ENABLED=0`.
2. Verify the redeployment preserves Mock detection and DeepSeek rewrite.
3. Review the applicable privacy, deletion and commercial terms. Record approval without copying private account content.
4. Before any real call, report the current price, expected call count, data type, retention conclusion and worst-case fee.
5. After explicit approval only, enable the two safety gates and `DETECTOR_MODE=pangram`, then run the one-call synthetic acceptance script.
6. Do not perform a second scan or reopen public registration without separate approval.

## Credential-free implementation verification

Before commit, the following completed without reading local or production secrets:

- 104 Python tests passed, including Pangram 4 contract failures, content/range validation, paid-call gates, duplicate protection, daily/concurrency limits, stale-version behavior and the one-call acceptance script.
- 5 frontend unit tests and 4 remote-release checker tests passed; TypeScript passed.
- Next.js 15.5.21 completed a Pages production export with the `/academic-writing-agent` subpath and production API URL; the static artifact secret scan passed.
- npm audit and Python runtime-requirements audit reported no known vulnerabilities after upgrading Next.js, Sharp, PostCSS and nanoid.
- Git working-tree and history scans found no token/private-key signature. No `.env.local` value was read; test/OpenAPI paths explicitly skip local dotenv loading.
- Docker CLI is not installed on the workstation, so a local Docker build could not be executed. The Railway build after push is the required container-build verification and must not be reported successful until its deployment is healthy.

No Pangram API request, model-catalog request, detection task, payment, recharge or auto-refill action was performed during this credential-free verification.

## Production acceptance outcome — 2026-08-10

The owner later completed the credential, data-processing acknowledgement, paid-call and two-call remediation gates. The first real 851-word synthetic task exposed a fail-closed whitespace-normalization mapping defect; revision `e75267c` repaired it without accepting content changes. A separately authorized second task returned Pangram 4 version `4.0`, produced valid three-class probabilities and 28 mapped windows, became stale after an explicit edit, removed every old highlight from version 2, and was followed by deletion of the synthetic document. No third task was created.

The two known task submissions are estimated at USD 0.90 total under the public USD 0.05 per started 100-word rule; actual billing remains a dashboard reconciliation item. See [Production Pangram 4 acceptance — 2026-08-10](PRODUCTION_PANGRAM_4_ACCEPTANCE_2026-08-10.md).
