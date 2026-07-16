# Authorization, privacy, and contamination controls

1. Accept only public-domain/open-license text with verified terms, explicit donation, commissioned work, or text specially generated for this benchmark. Never scrape or publish student submissions without consent.
2. Remove names, student numbers, schools, modules, instructors, dates that identify a class, document properties, comments, tracked-change author names, and embedded file metadata before assigning a sample ID.
3. Store consent or commissioning evidence outside Git. The manifest contains only a non-secret internal reference and the permitted uses.
4. Public development text may enter Git and may be sent to providers, but it is contamination-exposed and never claim-eligible. Restricted text and manifests are ignored by Git. Storage must be encrypted and access logged.
5. Private evaluation text may be sent to a provider only during an approved evaluation window after retention terms are confirmed. It must never be sent to the Paperlight rewrite model.
6. The final blind set is sealed, access is held by a curator who does not tune thresholds, and no provider or rewrite model sees it before the frozen final run. If provider evaluation necessarily uploads blind text, use a contractually approved zero-retention route, record the run, then retire that blind version from reuse.
7. Labels come from contemporaneous process evidence: drafts, revision history, accepted AI changes, prompts, model/version records, and curator adjudication. Detector output is forbidden as label evidence.
8. Dataset releases are append-only. Never edit a sealed manifest in place; quarantine errors and issue a new semantic version with a changelog and new hashes.
9. Report only aggregate groups with at least 10 samples. Suppress cells that could reveal a donor or a rare combination.
10. Delete raw identity/consent intake data on the approved schedule while retaining the minimum legal proof of permission in a separate access-controlled system.

The checked-in `v1.0.0-dev.1` corpus is intentionally non-claimable. Its two human references are public-domain historical prose, not student essays; its two AI samples are special fixtures from one model family. It validates code paths only.
