# Step 1 root-cause analysis

## Scope and evidence

This review used the exact ten members in `scripts/quality/frozen_reliability_cohort_10.json`, the isolated cohort result at `tmp/ten-full/frozen-reliability-9kx4zae9/cohort_result.json`, the retained Step 1 artifacts and candidate prompts beneath that run, and the live Step 2/reviewer ledgers referenced in `README.md`. The source manifest records the expected and observed SHA-256 values and physical page counts. No PDF, cache, raw model response, canonical claim, publication or WordPress write is committed in this package.

## Deterministic selector diagnosis

The current selector is `evidence_backed_shortlisting:5` in `src/generators/artifact_normalization.py`. Its existing regression coverage includes stable candidate identity retention, conservative semantic deduplication, provenance conflict handling, fallback theme coverage and cache invalidation. The first isolated ten-report run did not reproduce a selector-level defect: each report produced a retained candidate set with source evidence, protected metric fields and physical pages, and Step 2 received 59/59 retained claims.

The selection ledger preserves the raw candidate pool where the retained run recorded it, retained candidate IDs, final editorial wording, evidence IDs, evidence spans, metrics and pages. The artifact schema does not persist a selector rejection reason for every omitted candidate. The ledger therefore reports deterministic evidence-fidelity rejection only where the persisted `evidence_fidelity.json` proves it and labels other omissions as “not retained” rather than inventing a reason.

## First responsible stages observed

### Criteo candidate-generation drift

The live run contained a candidate whose wording stated “2023 plans” while its retained page-8 evidence did not establish that timeframe, and another candidate broadened “some new ad-supported streaming services” to “new ad-supported streaming services.” Evidence fidelity allowed the candidate package, but downstream public grounding rejected the unsupported form. This is an upstream candidate construction/metric-binding quality issue, not a demonstrated ranking or fallback defect. A selector-only patch would duplicate factual validation and could reject valid chart-supported findings, so no production selector change was justified.

### Reuters downstream validation

Reuters reached downstream validation with a `public_editorial_quality.metric_label_relationship` failure. The observed terminal failure is not evidence that the Step 1 selector incorrectly merged or discarded a proposition. It remains a generation/validation quality limitation and is recorded as such rather than being hidden in the selection score.

### Execution-path correction used for the live cohort

The exact cohort initially exposed a Windows deep-root path failure while persisting the resolved policy matrix. The targeted fix in `src/orchestrators/pipeline_preflight_orchestrator.py` retains the normal path for safe roots and uses a short deterministic `pf/<sha256(run_id)[:16]>.llm_policy_matrix.json` path only when the atomic-write path exceeds the existing service safety threshold. Regression coverage is in `tests/test_pipeline_preflight_orchestrator.py`. This is an execution-path fix required to run the cohort; it does not alter selector ranking, evidence validation or publication policy.

### Editorial review input correction

The fresh reviewer utility now accepts one explicit result/source-manifest pair and validates that roster as `explicit_ten`, instead of mixing the current ten claims with historical frozen/additional claim inventories. This keeps the independent reviewer coverage check aligned to the actual 59 claims. The change is covered by `tests/test_verified_claims_step2_editorial_review_integrity.py` and does not promote or mutate claims.

## Verification

Focused tests for the selector, evidence fidelity, Step 2 review integrity and preflight path behavior are run at the final commit. The production selector version and existing factual safeguards remain unchanged. The separate repeatability analysis records the invalid shared-batch attempt and the scope of the supplemental isolated rerun; it does not treat failed or reused-run artifacts as an independent clean evaluation.

## Remaining limitations

The acceptance requirement of two clean independent Step 1 evaluations per eligible report is not met by the available runs: the shared-batch repetition failed systemically and reused a run directory, while the clean supplemental isolated rerun covers only the five missing reports (KPMG, Reuters Institute, Algolia, Criteo and Deloitte). That rerun completed 5/5 terminal validation-pass records with 168 provider calls, estimated cost $0.431351, and 2,929.71 seconds. The claim-level editorial reviewer is not a source-recall oracle and is not P6 blind human acceptance. Step 1/E18 therefore remains PARTIAL, and Step 3/P6 remain open.

## Ten-report source-grounded audit follow-up — 2026-10-22

The independent physical-page audit in [`source-grounded-editorial-audit.md`](source-grounded-editorial-audit.md) inspected all 59 final-editorial rows rather than inferring quality from IDs. It found 33 HIGH, 22 MEDIUM, 4 LOW, and 0 INVALID source-grounded rows. The main high-value omissions were already present in the retained candidate inventory: Reuters AI-browser impact (p.41), KPMG execution tooling (p.24), Criteo US campaign-cost increase (p.7), Deloitte discovery-speed (p.6), Emplifi positive-resolution repeat buying (p.18), and StackAdapt first-party/contextual data (p.12). Each competed within an already-covered editorial theme; the retained artifact has no selector-level rejection reason, so the precise tie-break cannot be reconstructed safely.

This does not reproduce a deterministic selector, semantic-deduplication, fallback-fidelity, or cache defect. The observed quality trade-off is bounded candidate/final editorial selection, not unsupported evidence promotion. The final roster distinction is material: Step2 evaluates `insights_final`, while the Step1 ledger records `insights_candidates`; Emplifi has one source-supported final-stage replacement. The replay helper documentation now states this distinction explicitly. No keyword score, minimum-count change, fallback change, or ranking framework was introduced.

The audit retains three provisional recovered-page cases (KPMG p.35, Algolia p.26, Bain p.1), records the Algolia corrected-claim inherited evidence identity as a shadow-only lineage limitation, and confirms Criteo’s malformed verification response remains fail-closed. Step1/E18 remains PARTIAL; fresh source-recall and repeated-run evidence are still required.
