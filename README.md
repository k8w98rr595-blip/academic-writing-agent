# Paperlight — Academic Writing Agent

Paperlight is an owner-only workspace for improving English undergraduate coursework while preserving citations, numbers, quotations, and author control. It provides a patch-based writing Agent, editable AI-like writing estimates, immutable versions, Word import/export, and seven-day deletion.

The default providers are deterministic mocks for product testing. Mock results are always labeled as demonstrations and are not Turnitin results or proof of authorship.

## Local development

Prerequisites: Node.js 22+, pnpm, and Python 3.12+.

```powershell
Copy-Item .env.example .env.local
python scripts/init_secrets.py --project-root .
python -m pip install -r services/api/requirements-dev.txt
pnpm install

python -m uvicorn services.api.app.main:app --host 127.0.0.1 --port 8000
pnpm dev
```

Open `http://127.0.0.1:3000` and sign in with the owner credentials written by the initializer to the local ignored file `data/bootstrap-owner.txt`.

The initializer never replaces an existing `.env.local` unless `--force` is supplied intentionally. `scripts/start-local.ps1` starts both services with the bundled local configuration.

## Provider configuration

Provider keys are server-only. Set `DETECTOR_MODE=dual` after configuring both Pangram and Copyleaks, or `REWRITE_MODE=deepseek` after configuring DeepSeek. The app refuses a real mode whose credentials are missing.

## Deployment

- Frontend: GitHub Pages from `.github/workflows/pages.yml`.
- Backend: Railway from the root `Dockerfile` and `railway.json`.
- Database/queue/object storage: local Docker Compose for development; managed PostgreSQL, Redis, and S3-compatible storage for public rollout.

See `docs/ARCHITECTURE.md`, `docs/BENCHMARK.md`, `docs/DEPLOYMENT.md`, `docs/SECURITY.md`, and `docs/PROVIDER_SETUP.md`.
