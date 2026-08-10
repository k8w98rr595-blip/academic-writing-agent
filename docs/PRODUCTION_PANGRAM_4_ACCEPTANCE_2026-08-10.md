# Production Pangram 4 acceptance — 2026-08-10

This record covers the owner-authorized production acceptance of Paperlight's real Pangram 4 detector. The test document was synthetic, contained no student, personal, course, or institutional data, and was deleted after the check. No password, API key, cookie, session value, raw provider task ID, or paper body is recorded here.

## Tested deployment

- Frontend: <https://k8w98rr595-blip.github.io/academic-writing-agent/>
- API: <https://api-production-840c.up.railway.app>
- Detector mode: `pangram`
- Detector selector: `pangram-4`
- Rewrite mode: `deepseek`
- Remediation revision: `e75267c`
- Production-smoke alignment revision: `25eb005`
- GitHub Pages run: `31343354934` — passed
- Production Smoke run: `31343425538` — passed
- Credential-free recheck at `2026-08-10T01:02:56Z`: repository public, Pages 200, API health 200, detector `pangram`, rewrite `deepseek`, unauthenticated documents 401, and `productionReady=true` with no blockers

## Acceptance results

| Check | Result | Evidence |
|---|---|---|
| Owner-only production page | Pass | The authenticated workspace loaded the synthetic document; unauthenticated document access remains covered by Production Smoke as HTTP 401. |
| Real-provider identity | Pass | The result displayed `真实 Pangram`, provider `Pangram`, selector `pangram-4`, returned version `4.0`, and no Mock label. |
| Three-class result | Pass | Pangram returned AI-generated 100%, AI-assisted 0%, human 0%, and the UI transparently displayed combined risk 100%. These values are recorded as this sample's probabilistic risk signal, not an accuracy or authorship claim. |
| Evidence ranges | Pass | Twenty-eight provider windows mapped back to the immutable 851-word version and rendered as 28 marked fragments. The report disclosed that Pangram normalized whitespace and that ranges were mapped back to the original version. |
| Model and time auditability | Pass | The report displayed `pangram-4`, provider version `4.0`, prediction `AI`, and detection time `2026-08-10 08:08:44` local browser time. |
| Disclaimer | Pass | The UI stated that the output is a probabilistic internal AI-writing-risk signal and is not proof of authorship or academic misconduct. |
| Edit without automatic recheck | Pass | The owner appended one synthetic sentence and saved immutable version 2 (858 words). No new detection was launched. |
| Stale-result transition | Pass | The previous result changed to `已过期`; the UI stated that old ranges would not decorate the current version. The current version contained zero `<mark>` elements. |
| Explicit paid action | Pass | Re-detection remained an explicit button. Editing and saving did not trigger a hidden or automatic paid request. The button was not pressed again. |
| Browser health | Pass | No browser warning or error entries were returned after the successful result or stale transition. |
| Cleanup | Pass | After deletion, the production document library displayed `尚无文稿`; the synthetic document and its analysis workspace were no longer available. No DOCX was exported and no rewrite session was created in this Pangram-only run. |
| Logout | Pass | After the owner clicked `退出登录`, the production page returned to the owner login form and no workspace controls remained visible. No browser warnings or errors were reported. |

## Incident closure and call accounting

The first owner-authorized real submission for the same 851-word synthetic paper reached a provider result but failed local validation because Pangram normalized whitespace. Revision `e75267c` now accepts only provably equivalent whitespace normalization, constructs a monotonic offset map, and continues to fail closed for any non-whitespace content change or ambiguous range. The second owner-authorized submission passed end to end, so the normalized-text interoperability defect is closed.

Exactly two real Pangram task submissions are known in this acceptance sequence: the original locally rejected task and the successful post-fix task. No third submission was made. At the published Pangram 4 realtime price of USD 0.05 per started 100 words, each 851-word task is estimated at USD 0.45 and the two-task estimate is USD 0.90 if both were billed under that rule. The actual charge and whether the first locally rejected result was billed remain unknown until reconciled in the Pangram dashboard. Polling reused each existing task ID and did not create additional tasks.

## Security and product conclusion

- No provider key, session value or raw task ID was copied, logged, committed, or placed in the static frontend. During the post-logout verification, saved-password autofill exposed the owner password to the browser accessibility snapshot. The value was immediately cleared and is not repeated in this record, but the owner password must be rotated again and autofill disabled for this origin before continued routine use.
- Production remains owner-only and password-only because `REQUIRE_TOTP=0` is intentionally unchanged.
- Real Pangram 4 detection and real DeepSeek rewrite are functionally operational for controlled owner use; the newly exposed owner password is a security blocker for continued routine use until rotated.
- This run does not establish detector accuracy, calibration, student-population performance, authorship, misconduct, Turnitin equivalence, or guaranteed risk reduction.
- Public/student access remains blocked on stronger authentication, a consented independent benchmark, account-specific data-processing and retention confirmation, billing monitoring, and the remaining compliance gates.
