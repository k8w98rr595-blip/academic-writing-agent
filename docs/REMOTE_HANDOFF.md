# Production deployment handoff

The owner-only release is deployed from `main`. It is scoped to AI writing-risk detection and author-controlled revision; plagiarism/similarity checking is intentionally excluded. It uses real Pangram 4 for probabilistic risk detection, DeepSeek V4 Pro for rewrite proposals, and V4 Flash for semantic-safety validation. Public or student access remains closed.

The current writing flow is a multi-turn Agent patch review: select a passage, request a structured proposal, optionally refine that proposal in the same session, then explicitly accept or reject it. The original passage stays immutable across revisions; context is reconstructed server-side, full-document context requires explicit confirmation, and neither patch application nor re-detection is automatic.

## Live services

- Frontend: <https://k8w98rr595-blip.github.io/academic-writing-agent/>
- Backend health: <https://api-production-840c.up.railway.app/api/health>
- GitHub repository: <https://github.com/k8w98rr595-blip/academic-writing-agent>
- Railway project: `academic-writing-agent`

GitHub Pages uses the `/academic-writing-agent` base path and the repository Actions variable `PAPERLIGHT_API_BASE_URL` to generate `config.js`. Railway contains the `api`, `Postgres`, and `Redis` services; the API has a persistent volume mounted at `/data`.

## Verified production state

The following checks have passed:

- The owner-authorized 2026-08-10 Pangram 4 acceptance verified a real `pangram-4` / `4.0` result for an 851-word synthetic document, three-class probabilities, 28 mapped windows, an explicit probabilistic disclaimer, immediate stale status after version 2 was saved, zero old highlights on the edited version, no automatic third paid call, zero browser warnings/errors, and deletion leaving `尚无文稿`. The first real task had exposed Pangram whitespace normalization; revision `e75267c` fixed only provably equivalent whitespace mapping and the second authorized task passed. See [Production Pangram 4 acceptance — 2026-08-10](PRODUCTION_PANGRAM_4_ACCEPTANCE_2026-08-10.md).

- After the Railway trial expired and paused the deployment, the owner reported upgrading to Hobby on 2026-08-08. The `api`, PostgreSQL, Redis, and persistent volumes were observed online again. Post-recovery acceptance on revision `247ba3d` verified cleanup of the interrupted synthetic document, the detected-paragraph editor fix, deterministic Mock labeling, honest risk-increase display, fail-closed URL protection, a real Pro proposal with Flash validation, explicit patch acceptance, immediate stale evidence, re-analysis, desktop/mobile layout, empty-workspace cleanup, logout, API 200, unauthenticated 401, exact-origin CORS, HSTS, and zero browser warnings/errors. DOCX remained inconclusive because the in-app browser did not expose a completed download event. See [Production acceptance after Railway Hobby recovery — 2026-08-08](PRODUCTION_ACCEPTANCE_2026-08-08.md).
- Pages and its static assets return HTTP 200, and `config.js` contains the live Railway URL rather than the placeholder.
- The tested deployment includes hardening revision `56f6e21`; Pages run `29361860772` and credential-free Production smoke run `29361943400` passed for the pre-acceptance documentation revision `4660861`.
- The credential-free production smoke workflow verifies Mock detector mode, DeepSeek rewrite mode, configured owner access, HTTP 401 for an unauthenticated document request, the Pages-to-API URL, and the exact GitHub Pages CORS origin.
- The final 2026-07-15 owner flow completed against the hardened deployment with a 1,127-word synthetic paper: fresh login, labeled Mock analysis, fail-closed URL protection, real DeepSeek V4 patch, V4 Flash semantic validation, patch acceptance, stale-result transition, fresh reanalysis, valid DOCX export, immediate document-tree deletion, empty-workspace verification, and logout.
- The DeepSeek native low-balance warning is enabled at CNY 10. The post-test dashboard showed CNY 19.83 balance and CNY 0.16 cumulative spend; no recharge, purchase, payment change, or plan upgrade was made.
- Current local verification covers 75 backend/security/provider/workflow tests, 4 frontend unit tests, 4 release-audit tests, type checking, the static Pages build, expanded static secret scanning, and a browser-run desktop/mobile Mock closure check. The 2026-07-31 closure additionally verified two successive Agent proposals in one rewrite session, immutable-source protection, explicit full-document confirmation, patch acceptance, immediate stale evidence, re-analysis, before/after risk display, cleanup, and logout without any paid provider call.
- The 2026-08-01 production acceptance exercised the released multi-turn flow with real DeepSeek: fail-closed validation, a safe proposal version 1, a successive proposal version 2 anchored to the immutable original, explicit acceptance, stale Mock evidence, re-analysis, `17.6% → 15.9%` demonstration-risk display, desktop/mobile layout, deletion, empty-workspace verification, logout, zero browser warnings/errors, API health 200, unauthenticated 401, exact-origin CORS, and HSTS. The DOCX export control was activated, but the in-app browser did not expose a download event, so that item is recorded as inconclusive rather than passed. See [Production multi-turn Agent acceptance — 2026-08-01](PRODUCTION_ACCEPTANCE_2026-08-01.md).

## Production configuration

The API runs with production CORS, HTTPS-only owner access, eager jobs, local volume-backed object storage, real Pangram 4 detection, and server-only DeepSeek rewrite. `DATABASE_URL` and `REDIS_URL` reference the managed Railway services. Provider keys remain server-only and are not present in the frontend, Git repository, documentation, or knowledge vault.

The owner-approved current stage uses password-only authentication with `REQUIRE_TOTP=0`. Password-only login and logout were verified against the production API. TOTP restoration is intentionally out of scope for this stage; no deployment or verification step should read or alter TOTP material. Password compromise can grant owner access, so public registration and student access remain prohibited.

Credential follow-up: saved-password autofill exposed the owner-password field value to the automation accessibility channel during earlier acceptance and again during the 2026-08-10 post-logout check. No value is included in this repository. The field was cleared immediately, but the latest event is a new exposure: rotate the owner password again, deploy only its replacement hash, verify old-session rejection, and disable password autofill for the production origin before continued routine use.

Local handoff files are ignored and untracked. Their ACL inheritance is disabled and access is restricted to the current user, SYSTEM, and Administrators, but they remain plaintext. Move the values to the owner's password manager, rotate the related credentials, and delete the handoff files only after explicit owner confirmation. Do not copy login or TOTP material into Git, GitHub variables, logs, or documentation.

Operational custody, password rotation, the password-only risk boundary, and provider budget thresholds are defined in [Cost alerts and credential custody runbook](COST_AND_CREDENTIALS_RUNBOOK.md). Reproducible acceptance evidence is in [Production acceptance record — 2026-07-15](PRODUCTION_ACCEPTANCE_2026-07-15.md), [Production multi-turn Agent acceptance — 2026-08-01](PRODUCTION_ACCEPTANCE_2026-08-01.md), and [Production Pangram 4 acceptance — 2026-08-10](PRODUCTION_PANGRAM_4_ACCEPTANCE_2026-08-10.md).

The current backend adds a content-free paid-call ledger and the owner-only `GET /api/v1/provider-usage/summary` endpoint. Defaults are a warning at ten hourly calls, a hard stop before exceeding twenty, five consecutive failures opening a fifteen-minute Provider breaker, hashed duplicate-call protection, and 30-day operational retention. Login, reading, export, and deletion remain available while provider calls are paused. Provider dashboards remain authoritative for monetary charges.

## Operations

Every push to `main` runs tests, builds the static export, scans it for key-like values, and publishes Pages. Railway is connected to the same repository; an explicit deploy can also be started from the project root with:

```powershell
railway up --service api --detach
```

Run the credential-free audit with:

```powershell
pnpm check:release --backend-url https://api-production-840c.up.railway.app --expected-rewrite-mode deepseek --json
```

The manual `Production smoke` workflow is the remote acceptance check when the local network cannot route directly to the Railway edge.

## Deliberate future gates

Real Pangram is enabled only for the controlled owner stage. Accuracy claims, a Turnitin comparison, public registration, payments, refunds, student uploads, account-specific retention guarantees, benchmark calibration, and China-facing compliance are not part of this release and must be completed before public rollout. DeepSeek production access must remain server-only and subject to the same data-processing and retention review before any student pilot.

## Single-detector implementation handoff (2026-07-19)

The source contains one Pangram async-task adapter, strict response/range validation, bounded whitespace-only normalization mapping, no-repeat protection for ambiguous task submission, bounded safe polling retries, and deep-blue AI-generated/light-blue AI-assisted evidence rendering. Copyleaks, dual-provider fusion, consensus, and disagreement handling are not active product capabilities. Existing legacy analysis JSON remains readable as a non-highlighting historical record. Production currently runs `DETECTOR_MODE=pangram`; the real detector passed the controlled synthetic acceptance recorded above. Any future mode, model, credential or account-term change requires a new gated acceptance.
