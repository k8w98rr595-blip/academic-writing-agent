# Security boundaries

| Operation | Identity | Ownership/state rule | Input controls | Audit event |
|---|---|---|---|---|
| Login | Configured owner | Owner email only | Generic errors, Argon2id, TOTP, rate limit | `auth.login` / `auth.failure` |
| Read/edit document | Active server session | `document.owner_email == session.owner_email` | UUID, version precondition, word limit | `document.read` / `document.version` |
| Run detection | Active owner | Current owned version only | Provider config, timeout, response schema | `analysis.complete` / `analysis.failure` |
| Propose patch | Active owner | Rewrite session and base version must match | Instruction/selection limits, protected tokens | `patch.proposed` |
| Accept patch | Active owner | Pending patch, current base version | Exact original match, protected-token equality | `patch.accepted` |
| Export | Active owner | Current owned version | Generated server-side filename | `document.exported` |
| Delete | Active owner | Owned document only | Cancels jobs and removes objects | `document.deleted` |

Residual deployment risks: GitHub Pages and Railway are cross-origin, so the frontend uses a bearer session kept in `sessionStorage`; CSP and XSS prevention remain critical. Next.js static export requires inline bootstrap scripts, so the Pages-compatible meta CSP permits inline scripts while still denying plugins, frames, arbitrary origins, and `eval` in production. A reverse-proxy deployment should replace the meta policy with nonce-based response headers. Provider and public-China compliance checks are external release gates.

CSRF note: the API does not authenticate with cookies; it requires an explicit `Authorization: Bearer` header and disables credentialed CORS. This removes the ambient-cookie condition required for conventional CSRF. The tradeoff is that frontend XSS protection and a short server-side session lifetime are critical.
