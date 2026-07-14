# Production deployment handoff

The owner-only release is deployed from `main`. It uses DeepSeek V4 Pro for rewrite proposals and V4 Flash for semantic-safety validation; detection remains explicitly labeled Mock until the detector benchmark and provider gates are complete.

## Live services

- Frontend: <https://k8w98rr595-blip.github.io/academic-writing-agent/>
- Backend health: <https://api-production-840c.up.railway.app/api/health>
- GitHub repository: <https://github.com/k8w98rr595-blip/academic-writing-agent>
- Railway project: `academic-writing-agent`

GitHub Pages uses the `/academic-writing-agent` base path and the repository Actions variable `PAPERLIGHT_API_BASE_URL` to generate `config.js`. Railway contains the `api`, `Postgres`, and `Redis` services; the API has a persistent volume mounted at `/data`.

## Verified production state

The following checks have passed:

- Pages and its static assets return HTTP 200, and `config.js` contains the live Railway URL rather than the placeholder.
- The 2026-07-15 hardening revision `56f6e21` passed Pages run `29361217184` and credential-free Production smoke run `29361298967`.
- The credential-free production smoke workflow verifies Mock detector mode, DeepSeek rewrite mode, configured owner access, HTTP 401 for an unauthenticated document request, the Pages-to-API URL, and the exact GitHub Pages CORS origin.
- An earlier production owner flow completed with non-sensitive generated text: login, document creation, DeepSeek rewrite, semantic validation, patch acceptance, document deletion, and logout. The 2026-07-15 final acceptance flow is recorded separately and must be repeated after the hardening deployment before the current release is marked owner-ready.
- Current local verification covers 37 backend/security tests, 2 frontend tests, 4 release-audit tests, type checking, the static Pages build, and expanded static secret scanning.

## Production configuration

The API runs with production CORS, HTTPS-only owner access, eager jobs, local volume-backed object storage, an explicitly labeled Mock detector, and server-only DeepSeek rewrite. `DATABASE_URL` and `REDIS_URL` reference the managed Railway services. No provider key is present in the frontend, Git repository, documentation, or knowledge vault.

TOTP is temporarily disabled in production with `REQUIRE_TOTP=0` as of 2026-07-14. Password-only login and logout were verified against the production API. The existing TOTP secret remains configured so the second factor can be restored by setting `REQUIRE_TOTP=1` and redeploying; until then, owner access has reduced account protection.

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

Pangram and Copyleaks credentials remain unset. Real detector claims, a Turnitin comparison, public registration, payments, refunds, student uploads, provider data-processing agreements, retention guarantees, benchmark calibration, and China-facing compliance are not part of this owner-only release and must be completed before public rollout. DeepSeek production access must remain server-only and subject to the same data-processing and retention review before any student pilot.
