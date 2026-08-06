# Deployment

## GitHub Pages frontend

The web app uses a static Next.js export. The Pages workflow sets:

```text
NEXT_PUBLIC_BASE_PATH=/academic-writing-agent
NEXT_PUBLIC_API_BASE_URL=https://api-production-840c.up.railway.app
```

No provider secret is accepted by the frontend build. `scripts/check-static-secrets.mjs` fails the build if a key-like value appears in `apps/web/out`.

## Railway backend

Create a service from the root Dockerfile, attach a persistent volume at `/data`, and set the variables from `.env.example`. At minimum production requires:

- `APP_ENV=production`
- `DATABASE_URL`
- `ALLOWED_ORIGINS=https://k8w98rr595-blip.github.io`
- `OWNER_EMAIL`, `OWNER_PASSWORD_HASH`, `REQUIRE_TOTP=0`
- `COOKIE_SECURE=1`
- `DETECTOR_MODE=mock`
- `REWRITE_MODE=deepseek`, `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL=deepseek-v4-pro`, and `DEEPSEEK_VALIDATOR_MODEL=deepseek-v4-flash` for the owner-only production rewrite path
- `PAID_CALL_HOURLY_WARNING=10`, `PAID_CALL_HOURLY_HARD_LIMIT=20`, `PROVIDER_FAILURE_BREAKER_THRESHOLD=5`, `PROVIDER_BREAKER_SECONDS=900`, and `PROVIDER_USAGE_RETENTION_DAYS=30`

Do not deploy with a local bootstrap or handoff file. The owner-approved current stage keeps TOTP disabled; do not create, read, or alter TOTP material during routine deployment. Generate a replacement password verifier with `python scripts/hash_owner_password.py`, store the plaintext only in the owner's password manager, and put only the Argon2id verifier in Railway `OWNER_PASSWORD_HASH`.

Real Pangram deployment additionally requires the server-only variables documented in [Provider setup](PROVIDER_SETUP.md). `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=1` is a legal/operational gate, not a technical default; keep it at `0` until Pangram's applicable data terms are confirmed. The official endpoint host is enforced in every real-provider environment to prevent redirecting the key to an arbitrary server.

## Managed services

The single-owner mock release can use Railway PostgreSQL and an attached `/data` volume with eager jobs. Before a student pilot, enable Redis/Celery, S3-compatible storage, database backups, shared rate limits, and provider data-processing agreements.

## Credential-free production check

After Pages and Railway are configured, verify the public release without supplying a GitHub or provider token:

```powershell
pnpm check:release --backend-url https://api-production-840c.up.railway.app --expected-rewrite-mode deepseek
```

The check requires a public repository, a successful latest Actions run, HTTP 200 from Pages, Mock detector mode, DeepSeek rewrite mode, the approved password-only owner state (`requiresTotp=false`), and HTTP 401 from the protected documents endpoint. It exits with code `0` only when the owner-only release boundary is ready. Use `--json` for machine-readable evidence.

The manual `Production smoke` workflow provides the same credential-free production boundary check from a GitHub-hosted runner and also verifies that Pages contains the Railway URL and the expected CORS origin.
