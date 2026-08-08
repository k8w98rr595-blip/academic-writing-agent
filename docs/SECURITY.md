# Security boundaries

| Operation | Identity | Ownership/state rule | Input controls | Audit event |
|---|---|---|---|---|
| Login | Configured owner | Owner email only | Generic errors, Argon2id, password-hash-bound Session, rate limit; current stage is password-only | `auth.login` / `auth.failure` |
| Read/edit document | Active server session | `document.owner_email == session.owner_email` | UUID, version precondition, word limit | `document.read` / `document.version` |
| Run detection | Active owner | Current owned version only; content hash and owner quota reservation | Data-processing and paid-call gates, official-host/model allowlists, `/models` entitlement check, input/response limits, timeout, strict Pangram 4 schema/ranges, one task POST and bounded polling | `analysis.complete` / `analysis.failure` |
| Propose/refine patch | Active owner | Rewrite session, immutable base version, paragraph and prior pending patch must match | Instruction/selection limits, server-derived context, explicit full-document confirmation, protected tokens | `patch.proposed` |
| Accept patch | Active owner | Pending patch, current base version | Exact original match, protected-token equality | `patch.accepted` |
| Export | Active owner | Current owned version | Generated server-side filename | `document.exported` |
| Delete | Active owner | Owned document only | Cancels jobs and removes objects | `document.deleted` |
| View Provider usage | Active owner | Current owner aggregate only | Fixed time buckets; no caller-selected query or raw event access | `provider.usage_viewed`; usage rows contain no paper content or credentials |

Residual deployment risks: GitHub Pages and Railway are cross-origin, so the frontend uses a bearer session kept in `sessionStorage`; CSP and XSS prevention remain critical. Next.js static export requires inline bootstrap scripts, so the Pages-compatible meta CSP permits inline scripts while still denying plugins, frames, arbitrary origins, and `eval` in production. A reverse-proxy deployment should replace the meta policy with nonce-based response headers. Provider and public-China compliance checks are external release gates.

Detector trust boundary: Pangram responses are untrusted. Paperlight discovers the account model catalog before submission, requires `pangram-4`, validates response size, all three fractions and their sum, bounded windows, Pangram 4 labels/humanizer fields, returned `4.x` version, character bounds, returned text, and every window substring before saving evidence. Pangram-documented text normalization is accepted only when every non-whitespace character remains identical and ordered; a monotonic boundary map converts returned-text offsets to the submitted version, while any content change or ambiguous range fails closed. The raw task ID is used only for in-memory polling and is persisted as a SHA-256 reference. A failed call becomes a sanitized failure with no percentage or highlight; the provider response body is not exposed. Real detection stays disabled until both `DETECTOR_DATA_PROCESSING_ACKNOWLEDGED=1` and `PANGRAM_PAID_CALLS_ENABLED=1` are deliberately set.

Rewrite context boundary: browser-supplied document context is never trusted. The API derives selection, paragraph, section, or document context from the rewrite session's immutable base version and enforces an upper size bound. Full-document context additionally requires a per-request confirmation. A follow-up revision must reference the current pending patch from the same session and paragraph; after a safe successor is created, the previous proposal becomes read-only `superseded`. The original selected passage remains the protected-token and exact-application anchor across all revisions.

CSRF note: the API does not authenticate with cookies; it requires an explicit `Authorization: Bearer` header and disables credentialed CORS. This removes the ambient-cookie condition required for conventional CSRF. The tradeoff is that frontend XSS protection and a short server-side session lifetime are critical.

## Credential and session lifecycle

- Local bootstrap and Railway handoff files are written atomically. On Windows their ACL inheritance is removed before secret content is written, and access is limited to the current user, SYSTEM, and Administrators; POSIX files use mode `0600`.
- The files under `data/` remain one-time plaintext handoffs, not a password manager. Move their values into the owner's password manager, rotate the corresponding production credentials, and delete the handoff files only after explicit owner approval.
- Audit metadata uses a fixed allowlist. Paper text, rewrite text, credentials, sessions, provider response bodies, and arbitrary caller-supplied detail keys must never enter `AuditEvent.details`.
- A server session carries a one-way fingerprint of the current owner-password hash. Changing the hash invalidates previously issued sessions after deployment, so password rotation has an explicit revocation effect.
- Production deliberately remains password-only with `REQUIRE_TOTP=0` at the owner's direction. This is accepted only for the private owner stage; the service must not be opened to students under this authentication boundary.
- Paid Provider reservations and observations contain only provider/operation/model metadata, SHA-256 idempotency hashes, status, latency, and bounded provider-reported units. They never contain document text, Agent instructions, model responses, credentials, tokens, or raw idempotency keys.
- Paid work is denied before outbound traffic when a hard limit would be exceeded or a Provider breaker is open. Pangram is additionally limited to one concurrent task, two calls/hour and four/day; exact duplicate content is rejected for 24 hours. Provider controls do not block login, read, export, or immediate deletion.

Budget thresholds, provider-key ownership, password rotation, and the current password-only risk boundary are maintained in [Cost alerts and credential custody runbook](COST_AND_CREDENTIALS_RUNBOOK.md).
