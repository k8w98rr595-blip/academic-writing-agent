# Deployment

## GitHub Pages frontend

The web app uses a static Next.js export. The Pages workflow sets:

```text
NEXT_PUBLIC_BASE_PATH=/academic-writing-agent
NEXT_PUBLIC_API_BASE_URL=https://api-production-840c.up.railway.app
```

No provider secret is accepted by the frontend build. `scripts/check-static-secrets.mjs` fails the build if a key-like value appears in `apps/web/out`.

## Railway backend

For a new installation, create a service from the root Dockerfile, attach a persistent volume at `/data`, and set the variables from `.env.example`. The following is a safe initial configuration, not an instruction to reset the existing production variables:

- `APP_ENV=production`
- `DATABASE_URL`
- `ALLOWED_ORIGINS=https://k8w98rr595-blip.github.io`
- `OWNER_EMAIL`, `OWNER_PASSWORD_HASH`, `REQUIRE_TOTP=0`
- `COOKIE_SECURE=1`
- `DETECTOR_MODE=mock`
- `PANGRAM_API_BASE_URL=https://text.external-api.pangram.com`, `PANGRAM_MODEL=pangram-4`, `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=0`, and `PANGRAM_PAID_CALLS_ENABLED=0`
- `REWRITE_MODE=deepseek`, `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL=deepseek-v4-pro`, and `DEEPSEEK_VALIDATOR_MODEL=deepseek-v4-flash` for the owner-only production rewrite path
- `PAID_CALL_HOURLY_WARNING=10`, `PAID_CALL_HOURLY_HARD_LIMIT=20`, `PROVIDER_FAILURE_BREAKER_THRESHOLD=5`, `PROVIDER_BREAKER_SECONDS=900`, and `PROVIDER_USAGE_RETENTION_DAYS=30`

Do not deploy with a local bootstrap or handoff file. The owner-approved current stage keeps TOTP disabled; do not create, read, or alter TOTP material during routine deployment. Generate a replacement password verifier with `python scripts/hash_owner_password.py`, store the plaintext only in the owner's password manager, and put only the Argon2id verifier in Railway `OWNER_PASSWORD_HASH`.

Real Pangram 4 deployment additionally requires the server-only variables documented in [Provider setup](PROVIDER_SETUP.md). `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=1` and `PANGRAM_PAID_CALLS_ENABLED=1` are independent legal/operational gates, not technical defaults; keep both at `0` until the applicable data terms and one-call budget are confirmed. The official endpoint host and `pangram-4` selector are enforced, and the adapter verifies the selector with `GET /models` before creating a task. See [Pangram 4 deployment readiness](PANGRAM_4_DEPLOYMENT_READINESS.md). The existing owner deployment has passed a separately authorized synthetic activation and uses `DETECTOR_MODE=pangram`, `REWRITE_MODE=deepseek`, `BILLING_MODE=disabled` and `REQUIRE_TOTP=0`; preserve those settings during this reliability release without inspecting secret values.

## Managed services

The single-owner mock release can use Railway PostgreSQL and an attached `/data` volume with eager jobs. Before a student pilot, enable Redis/Celery, S3-compatible storage, database backups, shared rate limits, and provider data-processing agreements.

## Credential-free production check

After Pages and Railway are configured, verify the public release without supplying a GitHub or provider token:

```powershell
pnpm check:release --backend-url https://api-production-840c.up.railway.app --expected-detector-mode pangram --expected-rewrite-mode deepseek --expected-requires-totp false
```

The check requires a public repository, completed-success `pages.yml` and `production-smoke.yml` runs for the same main commit, HTTP 200 from Pages, the explicitly expected provider modes, the approved password-only owner state (`requiresTotp=false`), and HTTP 401 from the protected documents endpoint. Use `--expected-commit <full SHA>` to pin the release and `--json` for machine-readable evidence. A zero exit code is only anonymous public-boundary evidence, not an authenticated E2E result, proof of Railway's deployed commit, dependency readiness or public-launch approval.

The manual `Production smoke` workflow provides the same credential-free production boundary check from a GitHub-hosted runner and also verifies that Pages contains the Railway URL and the expected CORS origin.

## Document reliability release gate

Before publishing, rerun Python/frontend/release tests, TypeScript, the isolated Pages build and synthetic smoke, dependency audits, source/static secret scans and diff checks. Publish main only after they pass; preserve existing variables, data, billing-off and TOTP settings. No schema migration is required for this change. The local-staging files merged with the feature are development-only and do not enable staging on production.

Pages and Railway deploy asynchronously. Verify the new API's `POST /api/v1/rewrite-sessions/{session_id}/batch-decision` and `ExportRequest.expected_version_id` in the public OpenAPI schema before handing off the new UI. An unauthenticated dummy batch request must return 401; do not use a real document or bypass authentication. Confirm the Railway deployment's commit through its dashboard when an authorized session is available; schema/health checks alone do not prove an exact backend SHA.

Run signed-out desktop/mobile browser checks for page identity, assets, controls and console health. Owner login is required for production save/export/delete acceptance; it does not authorize a paid Pangram or DeepSeek task. Stop at login or a new cost approval and report that unverified portion. The previous release is `f42ec77`; if rollback is required, revert the release commits without resetting Git or clearing databases, and redeploy both frontend and API together. Do not automatically roll back the owner's deployment without reporting the failed gate and obtaining direction.
