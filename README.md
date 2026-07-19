# Paperlight — Academic Writing Agent

Paperlight is an owner-only workspace focused on AI writing-risk detection and author-controlled revision of English undergraduate coursework while preserving citations, numbers, quotations, and author control. It provides a patch-based writing Agent, editable AI-risk evidence, immutable versions, Word import/export, and seven-day deletion. Plagiarism/similarity checking is intentionally outside the product scope.

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

Provider keys are server-only. Pangram and Copyleaks now have production adapters, normalized sentence evidence, conservative non-average fusion, and explicit partial/disagreement states. Keep `DETECTOR_MODE=mock` until both providers are configured and their data-processing terms are acknowledged; then follow `docs/PROVIDER_SETUP.md`. The DeepSeek path uses V4 Pro for the proposed edit and V4 Flash for semantic-safety validation; deterministic protected-token checks remain authoritative.

## Deployment

- Live owner-only frontend: <https://k8w98rr595-blip.github.io/academic-writing-agent/>.
- Live API: <https://api-production-840c.up.railway.app/api/health> (Mock detection and DeepSeek V4 rewrite).
- Frontend: GitHub Pages from `.github/workflows/pages.yml`; `.github/workflows/production-smoke.yml` verifies the production wiring without credentials.
- Backend: Railway from the root `Dockerfile` and `railway.json`, with managed PostgreSQL, Redis, and an attached `/data` volume.
- Database/queue/object storage: local Docker Compose for development; managed PostgreSQL, Redis, and S3-compatible storage for public rollout.

This deployment remains private to the configured owner. DeepSeek rewrite is enabled, while real detector providers, public registration, payments, and student rollout remain disabled until their separate evaluation and compliance gates are complete.

See `docs/ARCHITECTURE.md`, `benchmark/README.md`, `docs/DEPLOYMENT.md`, `docs/REMOTE_HANDOFF.md`, `docs/SECURITY.md`, and `docs/PROVIDER_SETUP.md`.
