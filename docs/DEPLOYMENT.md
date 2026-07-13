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
- `OWNER_EMAIL`, `OWNER_PASSWORD_HASH`, `OWNER_TOTP_SECRET`
- `COOKIE_SECURE=1`
- `DETECTOR_MODE=mock`, `REWRITE_MODE=mock` until provider contracts and keys are ready

Do not deploy with the local bootstrap password file. Generate production password and TOTP values separately and store only their hash/secret in Railway variables.

## Managed services

The single-owner mock release can use Railway PostgreSQL and an attached `/data` volume with eager jobs. Before a student pilot, enable Redis/Celery, S3-compatible storage, database backups, shared rate limits, and provider data-processing agreements.

## Credential-free production check

After Pages and Railway are configured, verify the public release without supplying a GitHub or provider token:

```powershell
pnpm check:release --backend-url https://api-production-840c.up.railway.app
```

The check requires a public repository, a successful latest Actions run, HTTP 200 from Pages, Mock provider mode, a configured TOTP owner, and HTTP 401 from the protected documents endpoint. It exits with code `0` only when the complete owner-only Mock release is ready. Use `--json` for machine-readable evidence.

The manual `Production smoke` workflow provides the same credential-free production boundary check from a GitHub-hosted runner and also verifies that Pages contains the Railway URL and the expected CORS origin.
