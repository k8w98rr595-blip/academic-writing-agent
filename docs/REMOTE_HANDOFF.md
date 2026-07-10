# Remote publish handoff

The reviewed source is pushed to `main` at commit `9058164`. No provider key is required for the owner-only Mock release.

## 1. Enable GitHub Pages

The repository is now **public**. GitHub Actions run `29110385649` passed dependency installation, 23 backend tests, frontend and release-audit tests, typecheck, static build, and secret scanning.

The run stops only because the repository does not yet have a Pages site. In repository **Settings > Pages**, under **Build and deployment > Source**, select **GitHub Actions**. This single setting is required because the official configure-pages action cannot create a Pages site with the default `GITHUB_TOKEN`; automatic enablement requires a separate administration-capable credential.

After selecting the source, re-run **Test and deploy GitHub Pages**. The committed workflow builds the `/academic-writing-agent` static export and deploys it.

## 2. Import backend into Railway

The Railway browser session could not be controlled reliably, so no Railway project was created. After the repository is available to Railway, create a project from it and deploy the root `Dockerfile`. Add PostgreSQL and Redis, plus a persistent volume mounted at `/data`. Configure:

```text
APP_ENV=production
ALLOWED_ORIGINS=https://k8w98rr595-blip.github.io
OBJECT_STORAGE_MODE=local
OBJECT_STORAGE_DIR=/data/objects
JOB_MODE=eager
DETECTOR_MODE=mock
REWRITE_MODE=mock
REQUIRE_TOTP=1
COOKIE_SECURE=1
```

Connect `DATABASE_URL` to the Railway PostgreSQL service. The single-owner Mock release does not require Redis at runtime while `JOB_MODE=eager`; Redis is already supported for the later Celery worker split.

Copy `OWNER_EMAIL`, `OWNER_PASSWORD_HASH`, and `OWNER_TOTP_SECRET` from the ignored `data/railway-owner.txt` created by `scripts/prepare_railway_secrets.py`. Never copy the login password or TOTP URI into Railway variables.

## 3. Connect Pages to Railway

After Railway produces an HTTPS domain:

1. Confirm `https://YOUR-DOMAIN/api/health` returns `ok: true` and both provider modes are `mock`.
2. Add the repository Actions variable `PAPERLIGHT_API_BASE_URL=https://YOUR-DOMAIN`.
3. Re-run the Pages workflow.
4. Verify unauthenticated API calls return `401`, then complete one non-sensitive Mock workflow before treating production as available.

Identity, CAPTCHA, MFA, provider purchases, API keys, and public-student rollout remain deliberate manual gates. As of this handoff, the intended Pages URL returns HTTP 404 because Pages is not enabled; do not treat production as deployed until both the Pages URL and Railway health check pass.

Once the Railway domain exists, run the credential-free release audit:

```powershell
pnpm check:release -- --backend-url https://YOUR-RAILWAY-SERVICE.up.railway.app
```

Exit code `0` is the deployment acceptance gate. The script never reads or prints GitHub credentials, owner secrets, or provider keys.
