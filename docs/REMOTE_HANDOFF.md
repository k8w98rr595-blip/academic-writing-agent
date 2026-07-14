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
- The Pages build/deploy workflow completed successfully for the DeepSeek integration commit `9e900be` (run `29252532296`).
- The credential-free production smoke workflow verifies Mock detector mode, DeepSeek rewrite mode, configured TOTP owner access, HTTP 401 for an unauthenticated document request, the Pages-to-API URL, and the exact GitHub Pages CORS origin.
- A production owner flow completed with non-sensitive generated text: login, document creation, DeepSeek rewrite session, V4 Pro patch generation, V4 Flash semantic validation, patch acceptance, document deletion, and logout. The returned metadata was `DeepSeek`, `deepseek-v4-pro`, `deepseek-v4-flash`, and `isMock=false`; the test document was deleted with HTTP 204.
- Local verification covers 29 backend tests, 2 frontend tests, 4 release-audit tests, type checking, the static Pages build, static secret scanning, dependency auditing, and the container entrypoint shell syntax.

## Production configuration

The API runs with production CORS, HTTPS-only owner access, TOTP, eager jobs, local volume-backed object storage, an explicitly labeled Mock detector, and server-only DeepSeek rewrite. `DATABASE_URL` and `REDIS_URL` reference the managed Railway services. No provider key is present in the frontend, Git repository, documentation, or knowledge vault.

The login material is only in the ignored local handoff file created for the owner. Do not copy the login password or TOTP URI into Git, GitHub variables, logs, or documentation.

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
