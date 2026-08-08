# Production acceptance after Railway Hobby recovery — 2026-08-08

This record covers an owner-authorized production acceptance run against Paperlight after the owner reported upgrading Railway to Hobby. Only synthetic, non-sensitive text was used. No password, session, token, API key, TOTP material, or paper body is recorded here.

## Environment

- Frontend: `https://k8w98rr595-blip.github.io/academic-writing-agent/`
- API: `https://api-production-840c.up.railway.app`
- Source revision: `247ba3d`
- Detector: explicitly labeled `Mock Pangram` (`mock-pangram-v3`)
- Rewrite: DeepSeek `deepseek-v4-pro`
- Semantic validator: DeepSeek `deepseek-v4-flash`
- Authentication: owner password; TOTP remained disabled by owner decision
- Railway: owner reported Hobby upgrade; the `api`, PostgreSQL, Redis, and their persistent volumes were observed online

## Acceptance results

| Check | Result | Evidence |
|---|---|---|
| Railway recovery | Pass | Project architecture showed `api`, PostgreSQL, and Redis online with their persistent volumes after the Hobby upgrade. |
| Frontend and subpath | Pass | GitHub Pages loaded the production application from `/academic-writing-agent/`. |
| Owner login and logout | Pass | Password-only login opened the workspace; logout returned to the login screen. No credential field value was read. |
| Residual-data cleanup | Pass | The interrupted `Ethics of Data Reuse` synthetic document was found and immediately deleted with its versions, analyses, patches, tasks, exports, and files. |
| Fresh synthetic document | Pass | An 851-word safe demo document was created as `Paperlight Production Acceptance`. |
| Mock labeling | Pass | The report explicitly displayed demonstration-only labeling, `Mock Pangram`, and `mock-pangram-v3`. |
| Initial Mock result | Pass | The deterministic report showed 9.8% AI-generated risk, 7.9% AI-assisted risk, 82.4% human, 17.6% combined risk, and 11 marked spans. These are demonstration values, not performance evidence. |
| Detected-paragraph editor regression | Pass | A highlighted paragraph was edited without the prior React `removeChild` crash. The UI immediately displayed unsaved changes and stale detection; saving created immutable version 2. |
| Protected-content controls | Pass | The synthetic paragraph contained a year, percentage, quoted phrase, citation marker, URL, proper nouns, abbreviation, and formula. A DeepSeek proposal that attached punctuation to the URL was rejected fail-closed with no patch saved or applied. |
| Honest risk increase | Pass | After the author edit, re-analysis displayed `17.6% → 20.7%` and `+3.1` percentage points with the non-guarantee disclaimer. The increase was not hidden. |
| DeepSeek structured patch | Pass | A second request produced a reviewable `deepseek-v4-pro` patch for a different paragraph and displayed completed `deepseek-v4-flash` semantic-safety validation. |
| Explicit acceptance and stale analysis | Pass | The patch was not applied automatically. Explicit acceptance created immutable version 3 and immediately marked the prior analysis stale. |
| Protected content after acceptance | Pass | The protected synthetic paragraph remained text-identical after accepting the patch to another paragraph. |
| Re-analysis and risk comparison | Pass | Version 3 re-analysis displayed 6.9% AI-generated, 11.3% AI-assisted, 81.8% human, 18.2% combined risk, 12 marked spans, and `20.7% → 18.2%` without a guaranteed-reduction claim. |
| Desktop layout | Pass | At 1440×1024, document scroll width equaled viewport width. |
| Mobile layout | Pass | At 390×844, document scroll width did not exceed viewport width. |
| Browser console | Pass | No warning or error entries were captured during the run. |
| DOCX export request | Inconclusive | The export control was activated once. The in-app browser did not expose a completed download event before timeout, so the payload was not independently inspected. The request was not repeated; prior production acceptance and automated tests remain the current DOCX package evidence. |
| Immediate cleanup | Pass | The fresh synthetic document tree was deleted. The library then displayed no documents, covering the test versions, analyses, rewrite session, patch, task state, and export metadata. |
| API health and modes | Pass | `/api/health` returned HTTP 200 with detector `mock` and rewrite `deepseek`. |
| Unauthenticated business API | Pass | `/api/v1/documents` returned HTTP 401 after logout. |
| CORS and HTTPS | Pass | Preflight returned only the exact GitHub Pages origin; HSTS was present with a one-year max age and subdomain coverage. |

## Provider behavior

Two DeepSeek rewrite actions were submitted:

1. a protected paragraph request was rejected because the generated candidate changed URL punctuation;
2. a modest causal-clarity request produced a reviewable Pro proposal that passed Flash validation and was explicitly accepted.

No Pangram request was made. Production remains in Mock detector mode. This run does not claim a DeepSeek monetary charge because no provider billing dashboard was read.

## Remaining risks

1. Real Pangram remains disabled pending a server-side key, current data-processing and retention review, owner-approved cost controls, and a synthetic paid acceptance run.
2. TOTP remains disabled. Password-only access is acceptable only for the current single-owner stage and blocks public or student rollout.
3. The in-app browser could not independently capture and inspect the exported DOCX payload in this run.
4. Mock percentages are deterministic workflow fixtures, not evidence of detector accuracy or authorship.

## Post-publication verification

- GitHub Pages run `31241991415` completed successfully for documentation revision `9e13730`.
- Production smoke run `31242050187` completed successfully for the same revision.
- The final credential-free release checker reported the public repository, Pages, Mock detector, DeepSeek rewrite, password-only auth configuration, unauthenticated HTTP 401, frontend readiness, and production readiness all passing with no blockers.

## Owner-use conclusion

After Railway Hobby recovery, Paperlight is operational for owner-only use in its current Mock-detection plus real-DeepSeek configuration. The complete detection, author edit, fail-closed protection, reviewed patch, explicit acceptance, stale-result, re-analysis, cleanup, and logout loop passed. Real Pangram and public/student access remain disabled.
