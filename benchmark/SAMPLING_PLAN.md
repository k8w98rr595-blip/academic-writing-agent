# Sampling plan from development v1 to a formal benchmark

## Development v1

`1.0.0-dev.1` has four active public fixtures: two historical human references and two specially generated AI texts. It verifies manifests, hashes, labels, sentence offsets, metrics, reports, and Mock-provider comparison. It deliberately does not simulate non-native students or human editing and is not representative or claim-eligible.

## Claim-eligible private evaluation set

Target at least 700 documents before threshold work:

- 280 independently human-written papers: 40 per discipline, balanced between native/non-native English where consented sampling permits.
- 140 fully AI-generated papers: 20 per discipline, spread across at least five unrelated model families and multiple sampling settings. Record the exact provider model identifier and date; never backfill a guessed version.
- 140 hybrids: 70 AI-draft/human-deep-edit and 70 human-draft/AI-polish, ten of each process per discipline, with revision histories and accepted-change spans.
- 70 translated academic texts: human and AI translation routes kept distinct, source language and translator/tool recorded.
- 35 template-heavy verified-human papers and 35 technical-feature papers containing formulas, citations, tables, abbreviations, and specialist terminology. These are intentional stress oversamples and may overlap discipline quotas only when weighting is reported.

Stratify length as short 800–1,499 words, medium 1,500–2,999, and long 3,000–5,000. Include lower- and upper-division undergraduates plus developing, typical, and advanced writing quality. Keep all versions from one author/assignment in the same split to prevent leakage.

## Final blind set

Commission or collect at least 350 additional documents after the evaluation schema and threshold policy are frozen. Use the same target distribution but new prompts, assignments, donors, and model invocations. An independent curator holds the mapping and body files. Development staff receive only the sealed manifest digest before the run.

The blind set is one-use against each provider version. If upload is necessary, confirm zero-retention or an approved deletion SLA, record the provider run ID, and retire the blind version after results are revealed. A new provider model needs a newly sealed or refreshed blind release; repeatedly querying the same final set turns it into a development set.

## Collection and labeling procedure

1. Obtain explicit benchmark permission or commissioning terms before receiving text.
2. Remove direct identifiers and document metadata before ingestion; keep consent evidence in a separate restricted system.
3. Collect a contemporaneous process declaration, source draft, final draft, prompts, exact model identifiers, and revision/accepted-change history.
4. Two curators independently assign process labels and AI character spans. Resolve disagreement without viewing detector results; quarantine unresolved samples.
5. Run schema, count, range, permission, duplicate, and near-duplicate checks. Cluster by author, prompt, assignment, and source before splitting.
6. Freeze canonical LF-normalized text, SHA-256, manifest, dataset version, seed, and preprocessing. Seal the manifest before running providers.
7. Weight formal reports back to the declared target population when stress cases are oversampled; always report unweighted subgroup counts alongside weighted estimates.

Threshold candidates minimize an explicitly chosen error cost, with the default development policy valuing one human false positive as five AI false negatives. This is a governance choice, not a statistical fact. Any candidate must name the applicable population and 95% confidence intervals and must be confirmed at the frozen threshold on the untouched blind set.
