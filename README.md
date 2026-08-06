# Paperlight — Academic Writing Agent

Paperlight is an owner-only workspace focused on AI writing-risk detection and author-controlled revision of English undergraduate coursework while preserving citations, numbers, quotations, and author control. It provides a patch-based writing Agent, editable AI-risk evidence, immutable versions, Word import/export, and seven-day deletion. Plagiarism/similarity checking is intentionally outside the product scope.

The writing Agent is a multi-turn, author-reviewed workflow. The owner selects a risky passage, states a writing-quality goal, reviews the proposed patch, and may ask the same rewrite session for another revision before accepting or rejecting it. Follow-up revisions keep the original passage as an immutable safety anchor. Context is derived by the server from the selected immutable document version; full-document context requires an explicit confirmation. The Agent never auto-applies a patch, auto-runs detection, or optimizes against a detector score.

The default providers are deterministic mocks for product testing. Mock results are always labeled as demonstrations and are not Turnitin results or proof of authorship.

The current production stage intentionally uses password-only owner authentication (`REQUIRE_TOTP=0`). Paid provider work is guarded by a content-free usage ledger, an hourly warning/hard limit, duplicate-call protection, and a failure circuit breaker. These controls do not replace the billing dashboards and do not make the deployment suitable for public or student accounts.

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

Provider keys are server-only. Detection has one active adapter boundary: deterministic Mock Pangram or real Pangram. The current official Pangram REST contract creates an async task with `POST /task` and polls `GET /task/{task_id}`; the older synchronous `/v3` URL is deprecated. Keep `DETECTOR_MODE=mock` until Pangram credentials, cost controls, and data-processing terms are approved; then follow `docs/PROVIDER_SETUP.md`. The DeepSeek path uses V4 Pro for the proposed edit and V4 Flash for semantic-safety validation; deterministic protected-token checks remain authoritative.

## Deployment

- Live owner-only frontend: <https://k8w98rr595-blip.github.io/academic-writing-agent/>.
- Live API: <https://api-production-840c.up.railway.app/api/health> (Mock detection and DeepSeek V4 rewrite).
- Frontend: GitHub Pages from `.github/workflows/pages.yml`; `.github/workflows/production-smoke.yml` verifies the production wiring without credentials.
- Backend: Railway from the root `Dockerfile` and `railway.json`, with managed PostgreSQL, Redis, and an attached `/data` volume.
- Database/queue/object storage: local Docker Compose for development; managed PostgreSQL, Redis, and S3-compatible storage for public rollout.

This deployment remains private to the configured owner. DeepSeek rewrite is enabled, while real Pangram detection, public registration, payments, and student rollout remain disabled until their separate evaluation and compliance gates are complete.

Create a replacement owner-password verifier without displaying or storing plaintext with `python scripts/hash_owner_password.py`. The ignored output contains only an ACL-restricted Argon2id verifier for `OWNER_PASSWORD_HASH`; production password rotation still requires the owner to update Railway and verify a fresh login.

See `docs/ARCHITECTURE.md`, `benchmark/README.md`, `docs/DEPLOYMENT.md`, `docs/REMOTE_HANDOFF.md`, `docs/SECURITY.md`, and `docs/PROVIDER_SETUP.md`.
