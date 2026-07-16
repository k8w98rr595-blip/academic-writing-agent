# Cost alerts and credential custody runbook

Last verified: 2026-07-15 (Asia/Shanghai). This document contains no passwords, tokens, API keys, TOTP seeds, session values, or recovery codes.

## Current account state

| System | Verified state | Immediate action |
|---|---|---|
| Railway | `academic-writing-agent` is on a Limited Trial. Dashboard showed 22 days or USD 4.53 remaining; `api`, PostgreSQL, and Redis were online. | Do not rely on the trial for uninterrupted production. Decide whether to purchase a plan before the earlier of credit exhaustion or trial expiry. No purchase or payment change was made during acceptance. |
| DeepSeek | After production acceptance, the Usage page showed CNY 19.83 balance, CNY 0.16 cumulative spend, 26 requests, and 33,255 tokens. The native warning was reopened and verified enabled at CNY 10. | Keep the CNY 10 threshold enabled and review it monthly. No recharge or payment change was made. |
| Pangram | Production adapter is implemented, but production remains in Mock mode and no credential has been supplied for this integration. | Keep disabled until the applicable DPA/retention terms and budget controls are confirmed. |
| Copyleaks | Production adapter and 48-hour token exchange are implemented, but production remains in Mock mode and no credential has been supplied for this integration. | Keep disabled until `/v2/writer-detector` retention/deletion terms and the account's API pricing are confirmed. |

The observed values are a point-in-time dashboard reading, not an accounting record. Re-check the provider dashboard before making a purchase decision.

## Budget matrix

| Provider | Daily warning | Weekly warning | Monthly soft limit | Monthly hard limit | Native control | Application control |
|---|---:|---:|---:|---:|---|---|
| Railway | USD 0.50 usage increase | USD 2 | USD 10 | USD 15 | Workspace Usage email threshold; a hard limit can stop services | Daily dashboard check while on trial; preserve login/view/export/delete if paid model calls are paused |
| DeepSeek | CNY 1 | CNY 5 | CNY 10 | CNY 20 | Low-balance warning at CNY 10; Usage/Billing history | Pause new rewrites at the hard limit or balance below CNY 2; keep Mock detection and document management available |
| Pangram | 20 credits / USD 1 | 100 credits / USD 5 | 300 credits / USD 15 | 500 credits / USD 25 | Credit balance and optional auto-refill; auto-refill must remain off initially | Refuse new scans at 100 credits remaining; preserve existing reports |
| Copyleaks | 80 credits | 400 credits | 800 credits | 1,200 credits | Credits balance, usage history, optional replenish budget | Refuse new scans at 200 credits remaining; reconcile synchronous scan usage against the analysis record |

Railway cost controls and pricing are documented in [Plans](https://docs.railway.com/pricing/plans), [Project usage](https://docs.railway.com/projects/project-usage), and [Cost control](https://docs.railway.com/pricing/cost-control). DeepSeek exposes [pricing](https://api-docs.deepseek.com/quick_start/pricing), [balance](https://api-docs.deepseek.com/zh-cn/api/get-user-balance/), [rate limits](https://api-docs.deepseek.com/quick_start/rate_limit/), and [error codes](https://api-docs.deepseek.com/quick_start/error_codes). Pangram publishes its [API credit model](https://www.pangram.com/solutions/api) and [bulk API](https://docs.pangram.com/api-reference/bulk-api). Copyleaks documents [credit management](https://docs.copyleaks.com/concepts/management/manage-your-credits/), [rate limits](https://docs.copyleaks.com/using-the-apis/rate-limits/), and [failure handling](https://docs.copyleaks.com/concepts/performance/handling-failures/).

Hard limits are intentionally higher than soft limits. A Railway hard limit can create an outage, so it must not be enabled without the owner accepting that consequence. Provider auto-recharge is off by default and must never be enabled by automation.

## Abnormal-use alerts

- Hourly call volume warning: more than `max(10, 3 × the trailing seven-day hourly median)` paid calls.
- Circuit-breaker trigger: more than `max(20, 5 × median)` paid calls in one hour, five consecutive transient provider failures, or a retry rate above 10% with at least ten calls in fifteen minutes.
- Duplicate-work alert: more than one paid task for the same `owner + document_version + provider + operation` idempotency key in 24 hours, or more than two distinct paid task ids for the same document version/provider in fifteen minutes.
- Retry policy: initial attempt plus at most one retry, bounded exponential backoff, honor a short `Retry-After`, and never retry 400, 401, 402, 403, or 422. Pangram task creation is submitted only once because its official API does not document an idempotency header; only polling is retried.
- Breaker behavior: pause new paid tasks for fifteen minutes. Login, view, export, immediate deletion, and already-generated reports remain available.
- Review cadence: check dashboards daily while on the Railway trial; reconcile request count and charges weekly; review monthly limits and keys on the first day of each month.

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

For real detectors, only Railway `api` Variables may contain `PANGRAM_API_KEY`, `COPYLEAKS_EMAIL`, and `COPYLEAKS_API_KEY`. Copyleaks access tokens are generated at runtime, cached only in process memory, and must not become a Railway variable. `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=1` may be set only after both suppliers' applicable terms are reviewed; it contains no secret but records a release decision.

The existing `.env.local`, `data/bootstrap-owner.txt`, and `data/railway-owner.txt` files remain present. Their Windows ACLs were hardened without reading their contents: inheritance is disabled and only the current Windows user, SYSTEM, and Administrators have FullControl. They are still plaintext and should be migrated to the password manager. Deletion requires a separate owner confirmation.

During the final post-logout check, saved-password autofill exposed the owner-password field value to the browser automation accessibility channel. The value is not repeated in source, documentation, test output, or the knowledge vault, and the visible field was cleared immediately. Treat this as a credential exposure: rotate the owner password, deploy only the replacement Argon2id hash, verify that old sessions fail, and disable password autofill for the production origin.

## Rotation and recovery

1. Store the new secret in the password manager before changing production.
2. Create a replacement provider key; do not revoke the old key yet.
3. Update only the Railway `api` variable and redeploy.
4. Verify health and one synthetic, non-sensitive operation.
5. Revoke the old provider key after successful verification.
6. For an owner-password rotation, deploy the new password hash. Sessions are tied to a password-hash version in the current code, so old sessions become invalid and the owner must sign in again.
7. Rotate provider keys every 90 days, immediately after suspected exposure, or when a collaborator/device loses authorization. Review owner password and recovery material every 90 days.
8. Keep an offline recovery record in a physically secure location. Test account recovery twice per year without revealing or copying the recovery values into project documentation.

## Restoring TOTP

TOTP remains deliberately disabled in production. Password compromise currently grants owner access, so the service must remain single-owner and should not be opened to students.

To restore it:

1. Confirm the saved TOTP seed is available in the password manager and the authenticator can generate a current code.
2. Set `REQUIRE_TOTP=1` on the Railway `api` service without revealing `OWNER_TOTP_SECRET`.
3. Redeploy the API.
4. Confirm `/api/v1/auth/status` reports `configured=true` and `requiresTotp=true`.
5. In a fresh browser session, sign in using the owner password and current code.
6. Confirm the old password-only session no longer authorizes document access.
7. Update `PAPERLIGHT_EXPECTED_REQUIRES_TOTP=true` if that repository variable is introduced, then run Production smoke.

Do not enable TOTP until the owner is present to complete step 5; do not reveal, copy, or regenerate the existing seed as part of routine deployment.
