# Remote publish handoff

The reviewed source is pushed to `main` at commit `3718af2`. No provider key is required for the owner-only Mock release.

## 1. Complete the GitHub Pages identity gate

The repository exists at `k8w98rr595-blip/academic-writing-agent`, but it was created as **private**. GitHub Pages is disabled on the current account while the repository is private. GitHub requires sudo-mode email verification before changing the visibility.

After completing that identity check, change the repository visibility to **public**. The source is already pushed, so do not recreate the repository or force-push it.

In repository **Settings > Pages**, select **GitHub Actions** as the source if it is not enabled automatically. Re-run **Test and deploy GitHub Pages**. The committed workflow tests both applications, builds the `/academic-writing-agent` static export, scans it for secrets, and deploys Pages.

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
