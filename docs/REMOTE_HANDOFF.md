# Production deployment handoff

The owner-only release is deployed from `main`. It is scoped to AI writing-risk detection and author-controlled revision; plagiarism/similarity checking is intentionally excluded. It uses DeepSeek V4 Pro for rewrite proposals and V4 Flash for semantic-safety validation; detection remains explicitly labeled Mock until the detector benchmark and provider gates are complete.

## Live services

- Frontend: <https://k8w98rr595-blip.github.io/academic-writing-agent/>
- Backend health: <https://api-production-840c.up.railway.app/api/health>
- GitHub repository: <https://github.com/k8w98rr595-blip/academic-writing-agent>
- Railway project: `academic-writing-agent`

GitHub Pages uses the `/academic-writing-agent` base path and the repository Actions variable `PAPERLIGHT_API_BASE_URL` to generate `config.js`. Railway contains the `api`, `Postgres`, and `Redis` services; the API has a persistent volume mounted at `/data`.

## Verified production state

The following checks have passed:

- Pages and its static assets return HTTP 200, and `config.js` contains the live Railway URL rather than the placeholder.
- The tested deployment includes hardening revision `56f6e21`; Pages run `29361860772` and credential-free Production smoke run `29361943400` passed for the pre-acceptance documentation revision `4660861`.
- The credential-free production smoke workflow verifies Mock detector mode, DeepSeek rewrite mode, configured owner access, HTTP 401 for an unauthenticated document request, the Pages-to-API URL, and the exact GitHub Pages CORS origin.
- The final 2026-07-15 owner flow completed against the hardened deployment with a 1,127-word synthetic paper: fresh login, labeled Mock analysis, fail-closed URL protection, real DeepSeek V4 patch, V4 Flash semantic validation, patch acceptance, stale-result transition, fresh reanalysis, valid DOCX export, immediate document-tree deletion, empty-workspace verification, and logout.
- The DeepSeek native low-balance warning is enabled at CNY 10. The post-test dashboard showed CNY 19.83 balance and CNY 0.16 cumulative spend; no recharge, purchase, payment change, or plan upgrade was made.
- Current local verification covers 74 backend/security/provider/workflow tests, 2 frontend unit tests, 4 release-audit tests, type checking, the static Pages build, expanded static secret scanning, and a browser-run desktop/mobile Mock closure check.

## Production configuration

The API runs with production CORS, HTTPS-only owner access, eager jobs, local volume-backed object storage, an explicitly labeled Mock detector, and server-only DeepSeek rewrite. `DATABASE_URL` and `REDIS_URL` reference the managed Railway services. No provider key is present in the frontend, Git repository, documentation, or knowledge vault.

TOTP is temporarily disabled in production with `REQUIRE_TOTP=0` as of 2026-07-14. Password-only login and logout were verified against the production API. The existing TOTP secret remains configured so the second factor can be restored by setting `REQUIRE_TOTP=1` and redeploying; until then, owner access has reduced account protection.

Credential follow-up: the post-logout browser check exposed the saved owner-password field value to the automation accessibility channel. No value is included in this repository. Rotate the owner password, deploy only its replacement hash, verify old-session rejection, and disable password autofill for the production origin before continued routine use.

Local handoff files are ignored and untracked. Their ACL inheritance is disabled and access is restricted to the current user, SYSTEM, and Administrators, but they remain plaintext. Move the values to the owner's password manager, rotate the related credentials, and delete the handoff files only after explicit owner confirmation. Do not copy login or TOTP material into Git, GitHub variables, logs, or documentation.

Operational custody, rotation, TOTP restoration, and provider budget thresholds are defined in [Cost alerts and credential custody runbook](COST_AND_CREDENTIALS_RUNBOOK.md). The reproducible acceptance evidence and current blockers are in [Production acceptance record — 2026-07-15](PRODUCTION_ACCEPTANCE_2026-07-15.md).

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

Pangram credentials remain unset. Real detector claims, a Turnitin comparison, public registration, payments, refunds, student uploads, provider data-processing agreements, retention guarantees, benchmark calibration, and China-facing compliance are not part of this owner-only release and must be completed before public rollout. DeepSeek production access must remain server-only and subject to the same data-processing and retention review before any student pilot.

## Single-detector implementation handoff (2026-07-19)

The source now contains one current Pangram async-task adapter, strict response/range validation, no-repeat protection for ambiguous task submission, bounded safe polling retries, and deep-blue AI-generated/light-blue AI-assisted evidence rendering. Copyleaks, dual-provider fusion, consensus, and disagreement handling are no longer active product capabilities. Existing legacy analysis JSON remains readable as a non-highlighting historical record. Production remains on `DETECTOR_MODE=mock`; no Pangram key was added or used. Follow `docs/PROVIDER_SETUP.md` only after reviewing `docs/DETECTOR_PROVIDERS.md`, then run the cost-confirmed synthetic acceptance script before reporting real detection available.
