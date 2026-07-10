# Remote publish handoff

The code is committed locally on `main`. No provider key is required for the private Mock release.

## 1. Create and push GitHub repository

Create an empty public repository named `academic-writing-agent` under `k8w98rr595-blip`. Do not initialize it with a README, license, or `.gitignore`, then run:

```powershell
git remote add origin git@github.com:k8w98rr595-blip/academic-writing-agent.git
git push -u origin main
```

In repository Settings → Pages, select **GitHub Actions** as the source. The committed workflow tests both applications, builds the `/academic-writing-agent` static export, scans it for secrets, and deploys Pages.

## 2. Import backend into Railway

Create a Railway project from the GitHub repository and deploy the root `Dockerfile`. Add PostgreSQL and Redis, plus a persistent volume mounted at `/data`. Configure:

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

Identity, CAPTCHA, MFA, provider purchases, API keys, and public-student rollout remain deliberate manual gates.
