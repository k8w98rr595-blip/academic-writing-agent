# Cost alerts and credential custody runbook

Last implementation update: 2026-08-10 (Asia/Shanghai). Dashboard balances below are historical point-in-time observations and must be rechecked before any purchase decision. This document contains no passwords, tokens, API keys, TOTP seeds, session values, or recovery codes.

## Current account state

| System | Verified state | Immediate action |
|---|---|---|
| Railway | On 2026-08-08 the owner reported upgrading to Hobby after the trial expired. The project architecture then showed `api`, PostgreSQL, Redis, and their persistent volumes online. The exact billing balance was not read. | Keep a workspace usage alert enabled, review usage weekly, and verify the invoice/credit balance monthly. Do not enable a hard service-stopping limit without accepting the outage consequence. |
| DeepSeek | After production acceptance, the Usage page showed CNY 19.83 balance, CNY 0.16 cumulative spend, 26 requests, and 33,255 tokens. The native warning was reopened and verified enabled at CNY 10. | Keep the CNY 10 threshold enabled and review it monthly. No recharge or payment change was made. |
| Pangram | Real Pangram 4 is enabled for the owner-only production stage. Two real 851-word synthetic tasks are known: the first exposed a local whitespace-mapping defect and the authorized post-fix task passed. Actual billing was not read. | Reconcile the two tasks in the Pangram dashboard, keep auto-refill off, and do not expand access until account-specific retention terms and the independent benchmark are complete. |

The observed values are a point-in-time dashboard reading, not an accounting record. Re-check the provider dashboard before making a purchase decision.

## Budget matrix

| Provider | Daily warning | Weekly warning | Monthly soft limit | Monthly hard limit | Native control | Application control |
|---|---:|---:|---:|---:|---|---|
| Railway | USD 0.50 usage increase | USD 2 | USD 10 | USD 15 | Workspace Usage email threshold; a hard limit can stop services | Daily dashboard check while on trial; preserve login/view/export/delete if paid model calls are paused |
| DeepSeek | CNY 1 | CNY 5 | CNY 10 | CNY 20 | Low-balance warning at CNY 10; Usage/Billing history | Pause new rewrites at the hard limit or balance below CNY 2; keep Mock detection and document management available |
| Pangram 4 | 2 calls / at most USD 5 for two 5,000-word papers | 8 calls / at most USD 20 at the product length ceiling | 20 calls / at most USD 50 at the product length ceiling | 25 calls / at most USD 62.50 at the product length ceiling | Prepaid balance and optional auto-refill; auto-refill must remain off | App warns at 1/hour, blocks at 2/hour, 4/day and 1 concurrent call; monthly review is operational until a native alert is confirmed |

Railway cost controls and pricing are documented in [Plans](https://docs.railway.com/pricing/plans), [Project usage](https://docs.railway.com/projects/project-usage), and [Cost control](https://docs.railway.com/pricing/cost-control). DeepSeek exposes [pricing](https://api-docs.deepseek.com/quick_start/pricing), [balance](https://api-docs.deepseek.com/zh-cn/api/get-user-balance/), [rate limits](https://api-docs.deepseek.com/quick_start/rate_limit/), and [error codes](https://api-docs.deepseek.com/quick_start/error_codes). Pangram's current developer page lists Pangram 4 at USD 0.05 per 100 words and Pangram 3 at USD 0.05 per 1,000 words; a 1,500-word Pangram 4 realtime scan is therefore estimated at USD 0.75. The page is internally inconsistent about minimum funding (prose says USD 5–2,000 while the visible purchase card starts at USD 25), so the minimum must be confirmed in the authenticated account without purchasing. See [Pangram API pricing](https://www.pangram.com/solutions/api), [Models](https://docs.pangram.com/api-reference/models), and [Bulk API](https://docs.pangram.com/api-reference/bulk-api).

Hard limits are intentionally higher than soft limits. A Railway hard limit can create an outage, so it must not be enabled without the owner accepting that consequence. Provider auto-recharge is off by default and must never be enabled by automation.

## Abnormal-use alerts

- Global application warning: ten recorded paid calls in one hour; global hard limit: twenty. Pangram has a stricter warning at one detection/hour, hard limit at two/hour, four/day and one concurrent task. A DeepSeek proposal reserves two calls because generation and independent validation are separate provider requests.
- Circuit-breaker trigger: five consecutive failed or outcome-unknown calls for one Provider. The Provider reopens after fifteen minutes; a successful call resets the consecutive-failure sequence.
- Duplicate-work protection: a matching hashed `owner + provider + operation + idempotency key` in reserved, successful, or outcome-unknown state is rejected for 24 hours. Only the hash is persisted.
- Retry policy: initial attempt plus at most one retry, bounded exponential backoff, honor a short `Retry-After`, and never retry 400, 401, 402, 403, or 422. Pangram task creation is submitted only once because its official API does not document an idempotency header; only polling is retried.
- Breaker behavior: pause new paid tasks for fifteen minutes. Login, view, export, immediate deletion, and already-generated reports remain available.
- Review cadence: check Railway and provider dashboards weekly; reconcile request count and charges weekly; review monthly limits, invoices, balances, and keys on the first day of each month. Increase to daily review after an alert or unexplained usage spike.

The owner-only `GET /api/v1/provider-usage/summary` endpoint returns hour/day/week/month call counts, provider-reported input/output units, warnings, and breaker state. `provider_usage_events` retains operational metadata for 30 days and deliberately excludes paper text, prompts, responses, credentials, Session values, and raw idempotency keys. This is an operational safeguard, not a currency ledger; Railway, DeepSeek, and Pangram dashboards remain authoritative for charges and balances.

## Credential custody boundary

| Location | Allowed | Prohibited |
|---|---|---|
| Password manager with MFA | Owner password, TOTP seed/recovery material, provider keys, Railway/GitHub recovery information | Unencrypted exports, screenshots, chat messages |
| Railway `api` Variables | Password hash, TOTP secret, provider keys, managed database/Redis references | Plain owner login password and frontend configuration |
| GitHub Actions Variables | Public API base URL and non-sensitive expected modes | Passwords, tokens, provider keys, TOTP values |
| GitHub Actions Secrets | None are currently required by Pages | Provider keys copied merely for a static build |
| `.env.local` | Development-only credentials that differ from production | Long-term production recovery material |
| `data/*-owner.txt` | One-time bootstrap only | Long-term credential storage |

During acceptance, GitHub contained one repository variable (`PAPERLIGHT_API_BASE_URL`) and no repository or environment Actions secrets. Railway showed 20 masked service variables. The required production values were server-side, but both `deepseek-api-key` and `DEEPSEEK_API_KEY` names existed; verify the lowercase duplicate is unused, then remove it only with explicit owner confirmation.

For real detection, only Railway `api` Variables may contain `PANGRAM_API_KEY`. `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=1` may be set only after Pangram's applicable terms are reviewed; it contains no secret but records a release decision.

The existing `.env.local`, `data/bootstrap-owner.txt`, and `data/railway-owner.txt` files remain present. Their Windows ACLs were hardened without reading their contents: inheritance is disabled and only the current Windows user, SYSTEM, and Administrators have FullControl. They are still plaintext and should be migrated to the password manager. Deletion requires a separate owner confirmation.

Saved-password autofill exposed the owner-password field value to the browser automation accessibility channel during earlier acceptance and recurred during the 2026-08-10 post-logout verification. The values are not repeated in source, documentation, test output, or the knowledge vault, and the visible field was cleared immediately. Treat the latest event as a new credential exposure: rotate the owner password again, deploy only its replacement Argon2id hash, verify that old sessions fail, and disable password autofill for the production origin before any further browser-assisted login.

## Rotation and recovery

1. Store the new secret in the password manager before changing production.
2. Create a replacement provider key; do not revoke the old key yet.
3. Update only the Railway `api` variable and redeploy.
4. Verify health and one synthetic, non-sensitive operation.
5. Revoke the old provider key after successful verification.
6. For an owner-password rotation, deploy the new password hash. Sessions are tied to a password-hash version in the current code, so old sessions become invalid and the owner must sign in again.
7. Rotate provider keys every 90 days, immediately after suspected exposure, or when a collaborator/device loses authorization. Review owner password and recovery material every 90 days.
8. Keep an offline recovery record in a physically secure location. Test account recovery twice per year without revealing or copying the recovery values into project documentation.

## Current password-only authentication boundary

The owner explicitly excluded TOTP restoration from this implementation stage. Production remains `REQUIRE_TOTP=0`, the release checker expects `requiresTotp=false`, and routine work must not read, regenerate, or change TOTP material. Password compromise therefore grants owner access. Keep the service single-owner, rotate the exposed password before continued use, disable password autofill for the production origin, and do not open registration or student access. Stronger authentication is a separate future authorization decision, not an unfinished step in this stage.
