# Production acceptance record — 2026-07-15

Target: Paperlight Academic Writing Agent owner-only production. All content used by this review is synthetic and contains no student or personal information. This record contains no passwords, tokens, API keys, TOTP values, session values, recovery codes, or document contents.

## Release identity and evidence

| Item | Observed result |
| --- | --- |
| Repository | Public GitHub repository; acceptance hardening revision `56f6e21` is on `main` |
| Frontend | GitHub Pages returned HTTP 200 at the `/academic-writing-agent/` subpath |
| API | Railway HTTPS endpoint returned a healthy Paperlight response |
| Production modes | Detector `mock`; rewrite `deepseek`; owner configured; TOTP deliberately disabled |
| Remote CI | Pages run `29361217184` and Production smoke run `29361298967` succeeded for revision `56f6e21` |
| Security review | Risk-ranked selected review: 12 of 120 ranked source-like files received full-file review; this is not an exhaustive repository audit |

Reproduce the credential-free release check with:

```powershell
node scripts/check-remote-release.mjs `
  --backend-url https://api-production-840c.up.railway.app `
  --expected-detector-mode mock `
  --expected-rewrite-mode deepseek `
  --expected-requires-totp false `
  --json
```

## Acceptance matrix

| Area | Result | Evidence or remaining action |
| --- | --- | --- |
| Pages document and static resources | Pass | Main document and nine same-origin assets loaded; production `config.js` points to the Railway API. |
| GitHub Pages subpath | Pass | Page and assets resolved under `/academic-writing-agent/` without root-path breakage. |
| Desktop layout | Pass | 1440 × 900 inspection showed no horizontal overflow and exposed the sign-in/workspace flow. |
| Mobile layout | Pass | 390 × 844 inspection showed no horizontal overflow and retained the core form and sign-in controls. |
| HTTPS | Pass | Both Pages and API use HTTPS; the API emits HSTS in production. |
| Health and provider modes | Pass | `/api/health` reports `ok`, Mock detection, and DeepSeek rewrite. |
| Exact production CORS | Pass | The Pages origin is allowed; credentialed CORS is disabled; an unauthenticated document request is not widened by CORS. |
| Unauthenticated business access | Pass | `GET /api/v1/documents` returned HTTP 401. |
| Auth status | Pass | Owner authentication is configured and `requiresTotp=false`, matching the temporary password-only decision. |
| Password login | Previously passed; final rerun pending | An existing authenticated production workspace was observed without reading a password. Revision `56f6e21` intentionally invalidates pre-hardening sessions, so the final rerun requires a fresh owner login. |
| Synthetic document create → Mock detection → rewrite → patch → stale result → recheck → DOCX export → delete → logout | Pending | Requires the owner's explicit confirmation for one small real DeepSeek call and production create/export/delete actions. A prior attempt reached document creation and Mock detection, then timed out waiting for DeepSeek; cleanup ran and the workspace subsequently showed no files. |
| Mock label | Source and release gate pass; final UI run pending | Production UI uses “演示检测，不代表真实服务”, “演示”, and “运行演示检测”; a live completed analysis must still be captured in the final browser run. |
| Residue check | Partial pass | The production workspace showed no recent files after the timed-out run. Final document, export, rewrite-session, and logout residue checks remain tied to the pending full flow. |
| Request-body limits | Deployed and locally verified | Headerless valid JSON and multipart streams return 413 before complete-body consumption in full-app ASGI tests. Production smoke confirms the deployed API is healthy, but intentionally oversized traffic was not sent to Railway. |

The production browser flow must not be marked complete until every pending row above is rerun against the final deployed commit.

## Credential custody audit

| Surface | Conclusion |
| --- | --- |
| Git history and current tracked source | No known token, API-key, private-key, TOTP URI, authenticated database URL, or owner-secret pattern was found by the review scanner. This is a pattern-based control, not proof that arbitrary secret formats never existed. |
| Static build and public Pages assets | No configured secret pattern was found. Only the public API base URL is injected into the Pages build. |
| GitHub Actions configuration | One public repository variable, `PAPERLIGHT_API_BASE_URL`; no repository or environment Actions secrets; workflows do not reference `${{ secrets.* }}`. |
| GitHub Actions logs | The authenticated production-smoke run and workflow were inspected. The workflow injects no secret; no leakage indicator was observed. Full historical free-text log searching was not treated as exhaustive. |
| Railway Variables | Sensitive values are server-side and masked. Twenty variable names were observed. Both `deepseek-api-key` and `DEEPSEEK_API_KEY` exist; the lowercase duplicate must be confirmed unused before owner-authorized removal. |
| Railway logs | A recent sampled window contained access/status lines and no paper content or secret indicator. This was a sampled operational check, not a lifetime log proof. |
| Local plaintext handoffs | `.env.local`, `data/bootstrap-owner.txt`, and `data/railway-owner.txt` remain ignored and untracked. Without reading them, their ACLs were changed to explicit FullControl for the current user, SYSTEM, and Administrators only. They remain plaintext and were not deleted. |
| Session rotation | Current code binds sessions to a one-way fingerprint of the owner password hash, so changing the hash invalidates older sessions after deployment. |
| Audit metadata | Current code uses a fixed metadata-key allowlist; paper text, rewrite text, arbitrary detail fields, credentials, and provider bodies are not accepted into audit details. |

Recommended single-owner custody is a password manager protected by MFA, with provider keys, owner password, TOTP seed/recovery material, and platform recovery records kept there. Store an offline recovery record in a physically secure location; test recovery twice per year. Rotate provider keys and review owner recovery material every 90 days and immediately after suspected exposure or device access loss.

TOTP remains disabled by design. Password compromise currently grants owner access, so this release is not suitable for student accounts. The exact restoration procedure is in [Cost alerts and credential custody runbook](COST_AND_CREDENTIALS_RUNBOOK.md); it must be performed with the owner present and is not authorized by this review.

## Cost and quota controls

| Provider | Current state | Daily | Weekly | Monthly soft / hard | Native or account action |
| --- | --- | ---:| ---:| ---:| --- |
| Railway | Limited Trial; 22 days or USD 4.53 remained when checked | USD 0.50 | USD 2 | USD 10 / USD 15 | No purchase, upgrade, payment change, or hard shutdown was applied. Owner must decide before the earlier of expiry or credit exhaustion. |
| DeepSeek | CNY 19.98 balance; CNY 0.01 cumulative spend; 15 requests / 5,755 tokens when checked | CNY 1 | CNY 5 | CNY 10 / CNY 20 | Native balance warning is off. Proposed low-balance warning: CNY 10, after explicit owner confirmation; no recharge. |
| Pangram | Disabled; no credential | 20 credits or USD 1 | 100 credits or USD 5 | 300 or USD 15 / 500 or USD 25 | Configure balance polling and keep auto-refill off before enabling. Pause new scans at 100 credits. |
| Copyleaks | Disabled; no credential | 80 credits | 400 credits | 800 / 1,200 credits | Configure check-credits and usage reconciliation; keep automatic replenish off. Pause new scans at 200 credits. |

Alert on paid-call volume above `max(10, 3 × trailing seven-day hourly median)` and open the circuit at `max(20, 5 × median)`, five consecutive transient failures, or a retry rate above 10% with at least ten calls in fifteen minutes. Treat more than one paid task for the same owner/document-version/provider/operation idempotency key in 24 hours as a duplicate. Retry only once, honor `Retry-After`, and never retry 400, 401, 402, 403, or 422. The circuit breaker must pause new paid work for fifteen minutes without blocking login, view, export, or immediate deletion.

Official control references: [Railway plans](https://docs.railway.com/pricing/plans), [Railway project usage](https://docs.railway.com/projects/project-usage), [Railway cost control](https://docs.railway.com/pricing/cost-control), [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing), [DeepSeek balance API](https://api-docs.deepseek.com/zh-cn/api/get-user-balance/), [Pangram API](https://www.pangram.com/solutions/api), [Copyleaks credit management](https://docs.copyleaks.com/concepts/management/manage-your-credits/), and [Copyleaks rate limits](https://docs.copyleaks.com/using-the-apis/rate-limits/).

## Failures and fixes

| Failure | Reproduction | Status |
| --- | --- | --- |
| Real rewrite acceptance timed out | Run the synthetic owner flow and wait for the DeepSeek rewrite/validator pair; the first automation attempt exceeded its read timeout after Mock detection. | Acceptance client timeout increased to 240 seconds; final production rerun pending. |
| Plaintext credential handoffs inherited broader ACLs | On the scanned revision, create only synthetic files under an inheriting Windows directory and inspect ACE inheritance. | Source fixed with atomic fail-closed secure writes; current existing file ACLs hardened; rotation/migration/deletion remain operational. |
| Password rotation did not revoke old sessions | Issue a session, replace the configured owner password hash, then re-use the old bearer. | Fixed and covered by regression test; production deployment will intentionally sign out existing sessions. |
| Headerless JSON crossed the 6 MiB policy | Stream a valid oversized login body without `Content-Length` through local full-app ASGI. | Fixed and deployed with an outer bounded pre-buffer/replay middleware and full-app regression coverage. |
| Headerless multipart parsed before 401 | Stream a valid oversized document multipart body without `Content-Length` through local full-app ASGI. | Fixed and deployed by the same boundary. |

## Remaining risks and owner actions

1. Confirm the final synthetic production create/export/delete flow and the small real DeepSeek charge.
2. Confirm whether to enable the DeepSeek native CNY 10 balance warning. This does not recharge or change payment details.
3. Before the Railway trial expires or consumes its remaining credit, decide personally whether to buy a plan. The review will not purchase, bind payment, recharge, or upgrade.
4. Move local handoff values into the password manager, rotate owner and provider credentials, validate, then explicitly authorize plaintext-file deletion if desired.
5. Confirm the lowercase Railway `deepseek-api-key` variable is unused before explicitly authorizing removal.
6. Restore TOTP before any student pilot and verify a fresh two-factor login plus old-session rejection.
7. Complete provider data-processing, retention, benchmark, and commercial checks before enabling Pangram or Copyleaks or making accuracy claims.
8. Treat the selected security review as partial. The deferred limiter-state candidate and Railway edge request limits need focused staging follow-up.

## Readiness conclusion

Current status: **not yet final-accepted**. Revision `56f6e21` is pushed; Pages deployment and Production smoke both pass. Credential-free release checks, static delivery, unauthenticated isolation, selected credential audit, deployed hardening, and local test coverage pass. Owner-ready status remains blocked on a fresh password login, the final authenticated production workflow, cleanup verification, and the owner decisions listed above. This status must be updated only after those checks are observed, not inferred.
