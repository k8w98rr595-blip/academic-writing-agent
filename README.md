# Paperlight — Academic Writing Agent

## Public local experience (2026-10-08)

Paperlight now targets Chinese and English student writing, not similarity checking or emulating Turnitin. The public homepage offers a free browser-local experience: basic rule-based writing review, explicit proposal acceptance/rejection, undo and UTF-8 text export. Writing stays in page memory; closing the page loses unexported work. These rules are **not AI detection or a model-powered rewrite**. No public paper uploads, registration or paid AI calls are enabled by this release.

The existing authenticated owner workspace remains available. It now accepts Chinese (500–12,000 CJK characters/ASCII words) and English (500–5,000 words), with plain-text DOCX import/export. Student account isolation, Argon2id passwords, one-time rotating recovery codes, account deletion and separate provider consent are implemented behind disabled launch gates. Accounts are pseudonymous; no name, university or student ID is required. Cloud student access is limited to adults in this first implementation.

Because the real operator/contact are not yet provided, keep `PUBLIC_REGISTRATION_ENABLED=0`, `PUBLIC_AI_ENABLED=0` and `PUBLIC_LAUNCH_ACKNOWLEDGED=0`. See [Chinese student launch gates](docs/PUBLIC_LAUNCH.md) for configuration, privacy/cost boundaries and the remaining cloud-launch work. Neither a healthy deployment nor passing tests means public cloud AI is approved.

Paperlight is an owner-only workspace focused on AI writing-risk detection and author-controlled revision of English undergraduate coursework while preserving citations, numbers, quotations, and author control. It provides a patch-based writing Agent, editable AI-risk evidence, immutable versions, Word import/export, seven-day deletion, and a provider-neutral Free/Pro entitlement and quota layer. Plagiarism/similarity checking is intentionally outside the product scope.

The writing Agent is a multi-turn, author-reviewed workflow. The owner selects a risky passage, states a writing-quality goal, reviews the proposed patch, and may ask the same rewrite session for another revision before accepting or rejecting it. Follow-up revisions keep the original passage as an immutable safety anchor. Context is derived by the server from the selected immutable document version; full-document context requires an explicit confirmation. The first-pass action also produces a persisted batch preview in both Mock and real modes: select paragraphs, explicitly accept once, then restore the previous immutable version if needed. No detection is automatically rerun. Frontend and API must be released together for the batch-decision and version-bound export contracts.

This is a plain-text workspace, not a Word layout editor. Import preserves paragraph/simple-table reading order and rejects unsupported academic structures such as equations, notes, drawings, tracked changes and complex tables; export rebuilds plain paragraphs. Keep the original formatted Word file. Export first saves the draft and binds the download to that version; failed/conflicting saves keep the draft on screen. New/open/logout/restore actions offer save/discard/cancel, and reload/close requests a browser warning while dirty. There is no durable browser draft backup or continuous autosave, so an OS/browser crash can still lose unsaved text.

Local development defaults to deterministic mocks for product testing. Mock results are always labeled as demonstrations and are not Turnitin results or proof of authorship. The owner-only production deployment currently uses real Pangram 4 detection after a controlled synthetic acceptance; its output remains a probabilistic internal risk signal.

The current production stage intentionally uses password-only owner authentication (`REQUIRE_TOTP=0`) and keeps customer charging off (`BILLING_MODE=disabled`). Paid provider work is guarded by a content-free usage ledger, while product billing has centralized Plan/Entitlement/Quota/Usage, a non-production fake Checkout, and an optional Stripe Checkout/Portal/Webhook adapter. Student quotas remain enforced even with billing disabled; owner-only disabled-plan privileges are not inherited by students. These controls do not by themselves approve public cloud launch; the browser-local experience is separately available without an account.

## Local development

For an isolated, credential-free product rehearsal, use [`docs/LOCAL_STAGING.md`](docs/LOCAL_STAGING.md): `scripts/start-staging.ps1 build`, then `smoke` or `serve`. It uses separate loopback ports, data and credentials, forces Mock providers and simulated billing, and never reads `.env.local`. This is local functional staging, not a production-equivalent cloud environment or Stripe payment acceptance.

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

Provider keys are server-only. Detection has one active adapter boundary: deterministic Mock Pangram or real Pangram 4. The current official Pangram REST contract discovers account selectors with `GET /models`, submits one async `POST /task` using `model: "pangram-4"`, and polls only `GET /task/{task_id}`; the older synchronous `/v3` URL is deprecated. Local and fresh deployments default to Mock until the separate credential, data, cost and acceptance gates are approved. The current owner-only production deployment has passed those controlled activation gates and runs Pangram 4; follow `docs/PROVIDER_SETUP.md`, `docs/PANGRAM_4_DEPLOYMENT_READINESS.md`, and the production acceptance record before changing modes. The DeepSeek path uses V4 Pro for the proposed edit and V4 Flash for semantic-safety validation; deterministic protected-token checks remain authoritative.

## Deployment

- Public local experience and authenticated workspace: <https://k8w98rr595-blip.github.io/academic-writing-agent/>.
- Live API: <https://api-production-840c.up.railway.app/api/health> (Pangram 4 detection and DeepSeek V4 rewrite).
- Frontend: GitHub Pages from `.github/workflows/pages.yml`; `.github/workflows/production-smoke.yml` verifies the production wiring without credentials.
- Backend: Railway from the root `Dockerfile` and `railway.json`, with managed PostgreSQL, Redis, and an attached `/data` volume.
- Database/queue/object storage: local Docker Compose for development; managed PostgreSQL, Redis, and S3-compatible storage for public rollout.

Cloud documents and real AI remain private to the configured owner. The public local experience does not use the configured provider keys. Public cloud registration, charging and student AI rollout remain disabled pending operator/contact, mainland service classification, cross-border data review, Chinese benchmarking, budget and rollback acceptance. Current owner TOTP status is not changed by this release.

Billing configuration, API/state semantics, Stripe setup and launch gates are documented in [`docs/BILLING.md`](docs/BILLING.md). The default does not create a Stripe request or charge.

Create a replacement owner-password verifier without displaying or storing plaintext with `python scripts/hash_owner_password.py`. The ignored output contains only an ACL-restricted Argon2id verifier for `OWNER_PASSWORD_HASH`; production password rotation still requires the owner to update Railway and verify a fresh login.

See `docs/ARCHITECTURE.md`, `benchmark/README.md`, `docs/DEPLOYMENT.md`, `docs/REMOTE_HANDOFF.md`, `docs/SECURITY.md`, and `docs/PROVIDER_SETUP.md`.
