# Evidence, grounding, analytics, and validation

Canonical owner IDs: E6, E10, E12, E13, E14, E15, E16, E17, E18. This document contains **Active outcome specifications and their retained technical proposal slices**. Status belongs to [CONSOLIDATED_TODO.md](../../CONSOLIDATED_TODO.md), not to individual proposal sections. The complete source texts are preserved unchanged in the [historical backlog](archive/CONSOLIDATED_TODO-20261011-preconsolidation.md) and [historical proposal catalogue](archive/10improvements-20261011-preconsolidation.md).

Before implementing a slice, verify its historic diagnosis at current HEAD; use its **Luna implementation prompt** together with the full evidence and criteria immediately above it. Proposed thresholds are acceptance targets, not current results. Closed parent milestones are not reopened by a proposal's historical wording.

---
 
## E6. Retain a hash-pinned claim-embedding benchmark export

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `ANA-04`, `ANA-05`, `ANA-06`.

- **Baseline:** Claim embeddings and bounded live A/B tooling exist; the A/B output intentionally omits vectors. `semantic_evidence_preselection_benchmark.py` accepts supplied vector JSON offline but lacks governed model/dimension/corpus/content-hash validation and uses vector-norm ordering rather than production semantic selection. Approved retained export and zero-provider production-equivalent comparison remain open, not another embedding service/provider benchmark.
- **Target behaviour:** A bounded, retention-governed, hash-pinned benchmark export contains only approved vector identifiers/content hashes/vectors and enough model/dimension provenance to reproduce semantic ranking and compare against lexical fallback entirely offline.
- **What to implement, in order:**
  1. Define a versioned benchmark-export schema containing opaque claim/vector identity, content hash, embedding model/dimensions/version, vector, corpus identity and generation/hash provenance—no claim/source text.
  2. Add a controlled export path from the retained benchmark corpus that validates vector count/dimensions and writes an immutable manifest/hash.
  3. Load and validate the governed export in existing offline tooling before provider routing; reject/abstain on model/dimension/corpus/content-hash/version mismatch.
  4. Use the canonical production preselection/ranking boundary for zero-provider semantic-versus-lexical coverage, preserving corpus/export/model/dimension identity. Supplied-vector norm ordering or fake vectors cannot establish semantic retrieval closure.
  5. Document retention/update policy so a model/dimension/corpus change creates a new export rather than silently mutating the baseline.
- **Acceptance criteria:**
  - Export is hash-pinned, versioned, reproducible and contains no claim/report text or credentials.
  - CI can execute semantic ranking/coverage on the fixed corpus with **zero provider calls** and detect hash/dimension/model incompatibility.
  - Semantic versus lexical fallback metrics are retained with exact corpus/export identity and deterministic results.
  - A changed corpus/model/dimension cannot reuse an incompatible export silently.

### Luna implementation prompt — E6

```text
Work on E6 — Retain a hash-pinned claim-embedding benchmark export at the current MarketLense HEAD.
Owner specification: docs/backlog/E-evidence.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
### Linked technical implementation slices

Technical IDs below are **subtasks or investigations**, not additional canonical Active outcomes. Status notes are historical catalogue/reconciliation claims and require current-HEAD verification.
 
<a id="ana-04"></a>
#### ANA-04 — Retrieve evidence for the request, not the average retained claim

**Primary canonical owner:** [E6](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1; M–L, three slices; ANA-05 and ANA-06; coordinate ANA-09 budget allocation. **Owner/backlog:** semantic preselection generator/orchestration; extends the existing embedding foundation without reopening closed E1 or adding a vector-search product.

**Evidence and impact:** `src/generators/_cross_report_analysis_input/evidence_signals.py:202–313` computes one centroid of all fresh candidate claims and ranks proximity to that centroid; `_semantic_preselected_evidence()` receives neither topic nor selected-theme focus. Once any fresh embeddings exist, claims without fresh vectors disappear from the candidate set (`290–294`), whereas zero fresh embeddings retain deterministic fallback (`234–245`). **Confirmed behavior; hypothesis:** majority-topic claims crowd out relevant minority/counter-evidence, and partially embedded reports lose useful coverage. Measure this before selecting a new ranking policy.

**Luna implementation:** (1) Thread a bounded canonical request/theme focus into preselection; baseline deterministic topic/entity filters before considering a model call. (2) Compare existing-vector topical anchors or a reusable, hash-keyed query embedding through canonical LLM/budget boundaries; never call a provider from the pure generator. (3) Blend relevance with source/concept diversity and reserve bounded deterministic slots for eligible unembedded evidence and counter-signals. Return reasons and fallback coverage, not unsupported semantic-certainty labels. Keep retrieval decisions in idempotency material.

**Success criteria:** On ANA-06's fixed task corpus, labelled relevant-evidence recall@48 improves by at least 10 percentage points over centroid selection, with no precision regression greater than 2 points and no decrease in labelled counter-evidence coverage. Warm identical requests make zero new query-embedding calls; missing embeddings never silently remove a report's only relevant item. Insufficient quality evidence means retain the current policy.

**Validation:** `python -m pytest -q tests/test_cross_report_analysis_input_generator.py tests/test_cross_report_analysis_orchestrator.py tests/test_signal_candidate_orchestrator.py`. Fixtures include a dominant unrelated theme, a minority contradiction, only partial embeddings and query-cache invalidation. Run the same bounded canonical cross-report replay before/after with approved retained vectors and unchanged evidence budgets.

**Luna implementation prompt — ANA-04 (copy/paste)**

```text
Implement ANA-04 — Retrieve evidence for the request, not the average retained claim.
Objective: Deliver the verified behavior specified immediately above under canonical E6.
Source: docs/backlog/E-evidence.md, technical slice ANA-04.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E6 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ana-05"></a>
#### ANA-05 — Reject incompatible or numerically invalid retrieval vectors

**Primary canonical owner:** [E6](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P0; M, three slices; none. **Owner/backlog:** analytics embedding read/persist boundaries plus semantic preselection; corrective extension to closed E1, preserving its leases, retries and cost controls.

**Evidence and impact:** `_validate_embedding_record()` in `src/services/_analytics_store/claim_embeddings.py:244–273` checks length and required 1024 dimensions but not finite components or positive norm. `read_claim_embeddings():540–601` filters dimensions/status but not provider/model/version. `_embedding_by_entity()` and freshness selection (`evidence_signals.py:163–171,224–232`) choose records by entity and content hash without checking embedding-space identity; `_centroid()` checks only equal vector length (`151–160`). **Confirmed validation/compatibility gap:** equal-dimensional vectors from different spaces or NaN/Infinity can reach similarity ranking. Corrupt/mixed records in live data were not demonstrated.

**Luna implementation:** (1) Validate finite numeric non-boolean vector elements and positive finite norm at public persistence/read boundaries, with typed quarantine/failure. (2) Extend the read request with the active provider/model/dimensions/version identity resolved by existing configuration, and apply those filters before limits. (3) Make the generator require a homogeneous compatible embedding set and deterministic fallback for excluded records, recording counts/reasons. Existing content-hash freshness remains mandatory; do not reinterpret version mismatch as current just because lengths match.

**Success criteria:** Zero NaN/Infinity/zero-norm/mixed-space vectors participate in ranking on exhaustive invalid fixtures. Compatible valid records give unchanged similarities within 1e-12 and stable ordering. A current compatible vector wins over a newer incompatible attempt; fallback is explicit and performs zero regeneration/provider calls. Existing failed-record taxonomy and budgets are unchanged.

**Validation:** `python -m pytest -q tests/test_claim_embedding_persistence.py tests/test_claim_embedding_queue_remediation.py tests/test_cross_report_analysis_input_generator.py`. Add temporary-store readbacks containing two 1024-dimensional models, stale versions, NaN, Infinity, booleans, zero vectors and valid small-magnitude vectors; replay the canonical cross-report orchestrator with a boundary fake rather than patching private helpers.

**Luna implementation prompt — ANA-05 (copy/paste)**

```text
Implement ANA-05 — Reject incompatible or numerically invalid retrieval vectors.
Objective: Deliver the verified behavior specified immediately above under canonical E6.
Source: docs/backlog/E-evidence.md, technical slice ANA-05.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E6 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ana-06"></a>
#### ANA-06 — Close E6 with task-relevant offline semantic evaluation

**Primary canonical owner:** [E6](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P0; M–L, three slices; none; enables ANA-04/07/08/09 quality experiments. **Owner/backlog:** implement active E6, with a narrowly bounded task-quality extension; do not create a parallel benchmark ledger or silently alter approved models.

**Evidence and impact:** `CONSOLIDATED_TODO.md:426–440` explicitly retains E6's missing hash-pinned offline vector export. `scripts/quality/claim_embedding_ab_benchmark.py:1–5` deliberately retains neither text nor vectors. Its query text is exactly an indexed claim (`105–108`), and recall/MRR count recovery of that same UID (`130–144`). **Confirmed measurement limitation:** self-retrieval can verify vector identity and batching, but cannot establish usefulness for report questions, paraphrases, contradictions or Briefing selection. It is not proof the current embedding model is bad.

**Luna implementation:** (1) Implement E6's approved immutable vector export/manifest, retaining opaque IDs, hashes and model/dimension/version identity without claim/source text. (2) Add an explicitly governed task fixture with 30 independent analyst-labelled questions, relevant/supporting/counter-evidence IDs and distractors across at least ten retained reports; reuse separately approved corpus text rather than placing it in export/logs. (3) Evaluate canonical source/evidence selection against lexical fallback and centroid baseline with identical budgets; retain recall, precision, rank, source/counter-evidence coverage, prompt size and zero-call proof. Keep self-retrieval as a separately labelled transport diagnostic.

**Success criteria:** Three offline runs return identical metrics with zero provider calls; missing/hash-invalid/model-incompatible exports fail or explicitly abstain, never call live services. All 30 questions are distinct from the indexed claims. A candidate policy must meet each task's declared non-regression margin before promotion; an average win cannot conceal lost contradiction coverage.

**Validation:** `python -m pytest -q tests/test_claim_embedding_ab_benchmark.py tests/test_cross_report_analysis_input_generator.py tests/test_prompt_fixture_corpus_regression.py`. Add manifest-tampering, model-change, missing-vector and permission/retention fixtures; execute the canonical retrieval lane with provider boundaries that raise on any call. No live export creation is authorized by this documentation task.

**Luna implementation prompt — ANA-06 (copy/paste)**

```text
Implement ANA-06 — Close E6 with task-relevant offline semantic evaluation.
Objective: Deliver the verified behavior specified immediately above under canonical E6.
Source: docs/backlog/E-evidence.md, technical slice ANA-06.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E6 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
 
## E10. Attest active model-pricing rates before they become stale

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** none; outcome specification stands alone.

- **Baseline:** Enabled pricing governance blocks missing/invalid, explicitly held and explicitly expired configured rates before provider I/O, with cached-input/key/version attribution. Source/version/effective metadata exists, but proactive review/expiration attestation and reviewed cost-transition evidence remain absent. Approval, effective-date and mandatory review-age semantics are not enforced by the resolver; date labels do not prove rates stale or incorrect.
- **Target behaviour:** Operators get a bounded read-only freshness/coverage report for every active production-priced route and an explicit reviewed rate-card transition with before/after cost impact. No scraped/unreviewed rate becomes active automatically.
- **What to implement, in order:**
  1. Enumerate effective production model/provider pricing keys from the same reachable policy inventory used by A15. Reuse reachable model-policy inventory and expose exact aliases/pricing keys; missing approval/review/expiry metadata is unavailable, not inferred.
  2. Add a read-only attestation command reporting active, expiring, stale, held, missing, source/version/effective/review dates and coverage status without network scraping by default.
  3. Add deterministic before/after cost recomputation for recent canonical usage when an operator proposes a reviewed rate change; retain the old/new version/source and impact summary.
  4. Keep activation as an explicit reviewed configuration/rate-card change and preserve fail-before-provider behavior when the attestation is not valid. Preserve existing fail-before-provider behavior and add reviewed transition/activation semantics; do not auto-activate scraped rates or infer expiry from effective-date labels.
  5. Add tests for missing, expired, held, changed, cached-input and unknown-route pricing states.
- **Acceptance criteria:**
  - Every reachable priced production route appears in the attestation as active/expiring/stale/held/missing with source/version metadata.
  - Unknown, expired, held, or missing rates cannot silently execute as zero-cost or bypass spend authority.
  - A reviewed rate transition retains before/after estimates on recent canonical usage and an explicit operator acknowledgement; no command activates rates automatically.
  - Tests cover effective-date/freshness boundaries and cached-input pricing where applicable.

### Luna implementation prompt — E10

```text
Work on E10 — Attest active model-pricing rates before they become stale at the current MarketLense HEAD.
Owner specification: docs/backlog/E-evidence.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
---
 
## E12. Persist pre-category editorial context checkpoints

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `ING-08`.

- **Baseline:** Source/selection/vector checkpoints and prompt-family materialization already reuse compatible taxonomy/evidence/category outputs; E9's August 27 case proves narrower call avoidance. Recovery still starts before combined analysis rather than from a versioned pre-category checkpoint. Explicit context/planner proof that category-only recovery runs only category work and deterministic dependents remains open.
- **Target behaviour:** A versioned, lineage-validated checkpoint immediately before category fitting makes a genuine category-only recovery reuse all valid upstream taxonomy/evidence context and execute only the category model family plus its deterministic dependents.
- **What to implement, in order:**
  1. Define the pre-category checkpoint contract from approved taxonomy/evidence references, source/selection/vector identities, prompt/policy/schema/config hashes, and required compatibility metadata—no raw prompt duplication. Reference existing compatible family materializations/hashes rather than duplicate their payloads or introduce another reuse store.
  2. Persist the checkpoint atomically after all prerequisites validate and before category fitting starts.
  3. Extend minimum-execution/recovery planning so category-fit failures select this checkpoint only when every retained dependency remains compatible; otherwise fall back to the earliest proven safe checkpoint.
  4. Make actual execution audit planned versus reused/regenerated families and record avoided calls/tokens/cost.
  5. Add focused stale/incomplete/tampered checkpoint tests and one retained-report live recovery.
- **Acceptance criteria:**
  - Valid category-only recovery makes no source, extraction, vector, taxonomy or evidence provider call.
  - Stale/incomplete/incompatible checkpoint proof fails closed and selects the correct earlier recovery boundary instead of partial unsafe reuse.
  - Plan/actual audit names the exact reused/regenerated families and measured avoided calls/tokens/cost.
  - One retained live recovery proves the category-only path and all downstream semantic/grounding/publication gates remain active.

### Luna implementation prompt — E12

```text
Work on E12 — Persist pre-category editorial context checkpoints at the current MarketLense HEAD.
Owner specification: docs/backlog/E-evidence.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
### Linked technical implementation slices

Technical IDs below are **subtasks or investigations**, not additional canonical Active outcomes. Status notes are historical catalogue/reconciliation claims and require current-HEAD verification.
 
<a id="ing-08"></a>
#### ING-08 — Resume category fitting from a validated pre-category checkpoint

**Primary canonical owner:** [E12](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1; M–L, three slices; none. **Owner/backlog:** implement active E12 exactly; do not reopen closed E3/E7 or introduce an independent planner.

**Evidence and impact:** `CONSOLIDATED_TODO.md:458–472` explicitly records missing pre-category context checkpoint. `src/orchestrators/report_analysis_orchestrator.py:437–577` materializes vector-ready/taxonomy/evidence context inside analysis, before later category fitting; existing report-generation checkpoint stages are source/selection/analysis/render (`src/orchestrators/_report_generation_orchestrator/workflow.py:80–83`). **Confirmed backlog gap:** category recovery can replay upstream context rather than expressing a proven category-only plan. Existing prompt-family caches may prevent some provider calls, so wasted-call magnitude must be measured rather than assumed.

**Luna implementation:** (1) Add a versioned typed checkpoint referencing validated taxonomy/evidence, source/selection/vector identities and prompt/policy/schema/validator/config hashes, without copying prompts. Persist atomically after prerequisites pass and before category fit starts. (2) Add the checkpoint to existing lineage/minimum-execution/recovery rules with complete compatibility validation. (3) Restore typed context and run only category fitting and declared deterministic dependents; audit planned versus actual reused/regenerated families and avoided work.

**Success criteria:** Valid category-only replay makes zero source, selection, vector, taxonomy or evidence provider calls; stale/tampered/incomplete proof chooses the earliest safe prior checkpoint or fails closed. Downstream grounding/readiness outcomes remain unchanged, and rejected category output never becomes canonical context.

**Validation:** `python -m pytest -q tests/test_report_analysis_category_repair.py tests/test_context_category_fit_regressions.py tests/test_minimal_execution_planner.py tests/test_minimal_execution_enforcement.py`; replay a retained valid pre-category context with a first category failure, record each public service/model boundary call, then assert only the category family runs. Test source/prompt/taxonomy/version changes individually and interrupted checkpoint persistence.

**Luna implementation prompt — ING-08 (copy/paste)**

```text
Implement ING-08 — Resume category fitting from a validated pre-category checkpoint.
Objective: Deliver the verified behavior specified immediately above under canonical E12.
Source: docs/backlog/E-evidence.md, technical slice ING-08.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E12 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
 
## E13. Measure candidate-regeneration promotion effectiveness

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `VER-08`, `ARCH-D`.

- **Baseline:** Exact writable paths/minimal patches, retained-claim diagnostics, deterministic corrections, typed alternative evidence, one-call private decisions, retry deltas/strategy memory and repeated-candidate rejection are implemented. The frozen benchmark and scorecard exist; the remaining deficit is demonstrated safety/effectiveness, complete compatible denominators and repair-attributed usage, not absence of these foundations.
- **Target behaviour:** Existing atomic/adaptive regeneration must demonstrate reliable legal repairs while preserving the existing fail-closed promotion boundary. Every repair starts from the last promoted artifact, diagnoses the exact failing item/field and protected facts, chooses the cheapest safe repair action, changes only explicitly allowed paths, validates deterministic factual compatibility before the full gates, and records a machine-readable before/after failure delta. A rolled-back candidate never becomes the next baseline, but its strategy, evidence choices, resolved/persisting/introduced failures, and mutation scope inform the next attempt so retries deliberately use a different safe strategy rather than repeating the same failure. Deterministic corrections run without a model; model regeneration is reserved for source-grounded semantic/prose repair; unsupported items are removed/abstained rather than repeatedly paraphrased. Success is measured on a hash-pinned corpus of real historical repair failures.
- **What to implement, in order:**
  1. Preserve the atomic/protected-field, deterministic-first, promoted-baseline isolation, typed RepairDelta and strategy/candidate repetition safeguards in contracts, planner, generator and validation loop. Triage current frozen-scope/evidence/provenance failures through canonical production boundaries; do not expand legal scope or weaken validators to manufacture success.
  2. Retain every original frozen case, distinguishing currently reproducible, no-longer-reproducible, attempted, abstained, failed and strictly successful. Complete candidate/case/attempt identities and repair-attributed calls/tokens/cost/latency; whole-workflow usage and unavailable attribution are separate.
  3. Obtain an unchanged, version-compatible before/after measurement on one promoted revision; fix reproduced scope/evidence introductions and assert expected protected/derived leaf behavior. A final-validation pass, promoted candidate, removed unsupported item or no-longer-reproducible case is not automatically strict repair success.
  4. Confirm previously failing cases first, then rerun the required immutable failure corpus and affected downstream workflow canary with publication disabled. Preserve independent scorecard labels, exact identities, safety thresholds and unavailable comparisons; close only when every criterion below has proof.

**Latest retained measurement:** The October 1 replay at producer `eae746de7a6595b6dbddfcc69d7ad9ca8b26d2b6` retains seven unchanged frozen cases: four currently reproducible and three no longer reproducing. Strict success@1/@3 is 0/4, with nine candidate attempts, eight rollbacks and one promotion. The frozen scorecard records six out-of-scope attempts, seven unsupported-evidence introduction attempts, 18 new hard failures across eight attempts and one provenance/lineage introduction attempt. DoubleVerify's validation pass/promotion exceeded the frozen scope and is not strict success. Historical comparisons are identity-incompatible; no paired gain or residual-odds reduction is proven. Whole-replay usage is 165 calls and estimated $0.415041; complete repair attribution remains unavailable for Mobile. The separate IAS first-attempt canary passed readiness with 46 calls, publication disabled, and did not prove repair effectiveness. See the [result](../../docs/quality/e13-repair-benchmark/results/2026-10-01-eae746de.json), SHA-256 `08ba6900f921d839f6e34d509c0e41b4ec3091db70c329da486b97685b09efd6`, and [owning benchmark evidence](../../docs/quality/e13-repair-benchmark/README.md) for prior September measurements, exact commands and identities. E13 remains Active.

- **Acceptance criteria:**
  - Canonical rollback/promotion safety is unchanged: every attempt begins from the last promoted artifact, no rejected candidate can become canonical input, and full existing schema, evidence-lineage, grounding, semantic, public-editorial, readiness, and publication guards remain active.
  - Atomic targeted repair produces **zero out-of-scope mutation** on the retained real-failure corpus. A fixture that changes an unrelated family/field is rejected before promotion with a stable scope-violation reason, while explicitly declared deterministic dependents remain auditable.
  - A rolled-back attempt contributes a typed `RepairDelta` and strategy/evidence fingerprint to the next plan. Tests prove attempt 2 can start from the unchanged promoted baseline while avoiding an identical failed strategy/evidence combination and explicitly accounting for failures introduced by attempt 1.
  - `validate_retained_claims()` is reused in the central candidate path for supported factual material; numeric, quote, protected-fact and evidence-reference mismatches become structured repair diagnostics without weakening or bypassing the existing authoritative validators.
  - Every uniquely provable deterministic repair path performs **zero model calls** and preserves exact source-supported value/unit/label/timeframe/forecast/quote/evidence-page semantics. Ambiguous corrections abstain or escalate rather than guessing.
  - Alternative evidence selection never returns a quarantined ID, and retained fixtures with same-number/wrong-geography, wrong-period, wrong-cohort/denominator, forecast-vs-observed, or conflicting metric relationships rank the compatible source above lexical near-matches or abstain when none exists.
  - Retry strategies are materially distinct and bounded. The system never repeats an identical rejected candidate hash or identical failure-fingerprint+strategy+evidence combination without a material input/validator change; exhausting safe strategies ends in typed removal/abstention/failure rather than unbounded regeneration.
  - The hash-pinned real-failure benchmark reports complete denominators and version-compatible cohorts. The promoted implementation demonstrates at least **90% valid repair success@3** and a **10× reduction in residual repair-failure odds versus the exact retained baseline where baseline mathematics permits it**; if baseline success is already too high for a literal 10× odds reduction, it must reach at least **95% valid success@3** and document the ceiling calculation. Abstention/removal, invalid promotion, or suppressed failures cannot be counted as successful repair.
  - New hard-failure introduction is below **2% of attempts**, unsupported/hallucinated evidence introduction is **0%**, and improvement does not come from weaker validators, broader mutation scope, publisher/report-specific exceptions, higher retry limits, or materially higher average repair cost. Compatible before/after evidence retains calls, tokens, cost, latency, success@1/@3, and failure-class distributions.
  - The read-only E13 scorecard remains evidence-safe: it exposes bounded IDs/hashes/counts/usage/strategy/failure classes only, never raw source text, prompts, candidate/model responses, or unpublished repair diagnostics; no scorecard command automatically mutates prompt, routing, evidence, or validation policy.

### Luna implementation prompt — E13

```text
Work on E13 — Measure candidate-regeneration promotion effectiveness at the current MarketLense HEAD.
Owner specification: docs/backlog/E-evidence.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
### Linked technical implementation slices

Technical IDs below are **subtasks or investigations**, not additional canonical Active outcomes. Status notes are historical catalogue/reconciliation claims and require current-HEAD verification.
 
<a id="ver-08"></a>
#### VER-08 — Retain rejected repair memory and remaining budgets across restart

**Primary canonical owner:** [E13](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / existing E13 foundations; coordinate SYS crash-convergence but do not duplicate queue completion work.
- **Evidence / diagnosis:** Within one invocation the repair loop already enforces isolated candidates, monotonic deltas and strategy/candidate repetition guards (`_report_analysis_orchestrator/validation.py:1918–1999,2103–2118,2178–2193`); these must not be rebuilt. Residual restart risk: `_run_validation_regeneration_loop():1497–1503` starts attempts, rejected strategy/candidate sets and repair memory empty each time. Rich compatible audit records already exist at `1077–1174`, but this function does not hydrate them before planning. A restarted/manual repeat against unchanged inputs may therefore spend the same rejected strategies again; exact production restart behavior needs an integration reproduction before labelling an observed defect.
- **Luna implementation:** Reuse the existing candidate audit/loop state as the durable recovery input. Load only records matching canonical promoted artifact/evidence hash, prompt/schema/validator/configuration identities and the repair campaign identity. Reconstruct prior rejection keys, typed deltas, used broad fallback and consumed attempt/cost allowance before the next plan. Never load rejected candidate prose as baseline/evidence. Distinguish resumption from an explicitly authorized new campaign after material identity change. Use existing store/orchestrator boundaries and deterministic corruption failures; avoid a parallel repair ledger or unlimited history scan.
- **Success criteria:** Crash/reentry with unchanged inputs does not repeat a rejected strategy/evidence combination or replenish attempts. Recovery starts from the last promoted artifact and respects existing budgets; materially changed evidence/validator identity can begin a new attributed campaign. Corrupt/incompatible audit state fails or starts an explicitly recorded safe new campaign under policy, never silently claims continuation.
- **Validation:** Add controlled store-boundary failure/restart fixtures to `tests/test_atomic_regeneration_contract.py` and `tests/test_report_regeneration_identity_and_failures.py`; preserve no private-helper monkeypatching. Run these plus `tests/test_replay_validation_repair_benchmark.py tests/test_validation_repair_scorecard.py`. Replay the unchanged frozen E13 corpus with a simulated restart after rejection, verifying total calls and canonical hashes across both processes.

**Luna implementation prompt — VER-08 (copy/paste)**

```text
Implement VER-08 — Retain rejected repair memory and remaining budgets across restart.
Objective: Deliver the verified behavior specified immediately above under canonical E13.
Source: docs/backlog/E-evidence.md, technical slice VER-08.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E13 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="arch-d"></a>
#### ARCH-D — Refresh all materially dependent editorial families after atomic repairs

**Primary canonical owner:** [E13](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / `E3`, `E9`, `E13`; coordinate with follow-up C and `P16`. Preserve candidate isolation and rollback.
- **Evidence / diagnosis:** `ARTIFACT_ROOT_DEPENDENCIES` in `_artifact_generator/storage.py` rebuilds deterministic outputs such as metric spine, figures, cards, advisory and claim ledgers after an atomic source patch. The generation DAG also derives `expert_comment`, `linkedin_post` and `cover_semantics` from insight/summary inputs, but those LLM families are not declared as deterministic rebuild roots. Repair can therefore leave text or cover decisions semantically stale even when their literal claims still pass.
- **Luna implementation:** Extend the existing dependency/materialization plan to distinguish deterministic rebuilds from LLM family invalidation. On a material approved-source change, compare the affected canonical input identities; reuse unaffected prompt-family outputs and selectively regenerate stale families from the newly promoted approved facts. Keep every candidate private until its source patch, dependent outputs, evidence bindings and final validation pass together; otherwise rollback all candidate changes. Do not regenerate every family for formatting-only or unrelated patches, or weaken the atomic allowed-path contract.
- **Success criteria:** A repaired/removed insight or summary claim cannot leave an Expert View, LinkedIn assertion, cover premise or derived figure inconsistent with canonical facts. Unrelated families remain byte-identical/reused; rejected candidates never contaminate the promoted baseline, source lineage or later retries.
- **Validation:** Add a report-level controlled repair that removes or changes an insight used by all three editorial dependents, plus unchanged-family, failed-regeneration and restart fixtures. Assert exact dependency invalidation, candidate-only scope, zero stale factual carry-over, bounded calls and publish-readiness consistency on an E13 frozen failure.

**Luna implementation prompt — ARCH-D (copy/paste)**

```text
Implement ARCH-D — Refresh all materially dependent editorial families after atomic repairs.
Objective: Deliver the verified behavior specified immediately above under canonical E13.
Source: docs/backlog/E-evidence.md, technical slice ARCH-D.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E13 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
 
## E14. Calibrate category-fit coverage from retained outcomes

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** none; outcome specification stands alone.

- **Baseline:** Model fitting, deterministic inclusion/exclusion/centrality, supported rescue and repair/abstention records exist, with field-preserving fixtures and stage/outcome/failure `category_outcomes.csv` exports. Compatible-cohort scoring of valid exclusions versus unresolved gaps, selection/rescue distributions, attributable usage and recurring concepts—and review-only proposals—remains absent.
- **Target behaviour:** A bounded read-only category-fit scorecard identifies where deterministic mappings or prompts can improve grounded coverage and reduce unnecessary repair without forcing legitimate out-of-taxonomy reports into a category.
- **What to implement, in order:**
  1. Define compatibility cohorts from taxonomy/mapping version, prompt/model/policy, schema/validator and relevant configuration identities.
  2. Aggregate nonempty selection, explicit-uncategorized, selected-count distribution, deterministic rescue, repair rate, validation outcome, latency, tokens and cost by compatible identity. Extend current category-stage/usage exports; do not create a parallel outcome ledger or count regression fixtures as compatible-cohort calibration.
  3. Retain explicit exclusions/out-of-taxonomy outcomes separately from unresolved mapping gaps so the scorecard does not optimize against valid abstention.
  4. Rank recurring uncovered semantic concepts and excess-repair causes using bounded concept/rule IDs and produce reviewable mapping/prompt proposals only above sample/confidence gates.
  5. Validate a proposed mapping/prompt change through retained and bounded live compatible cohorts using the existing gates; do not mutate taxonomy automatically.
- **Acceptance criteria:**
  - Scorecard reports complete denominators and separates selected, explicit-uncategorized, explicit-exclusion, rescue and repair outcomes.
  - Incompatible taxonomy/mapping/prompt/model/policy cohorts are never merged.
  - Proposals are bounded to mapping/prompt review and include sample/confidence evidence; no automatic taxonomy/policy change occurs.
  - Retained/bounded live evidence demonstrates a measured increase in **grounded** nonempty selection or a reduction in unnecessary category-repair calls with no increase in invalid/forced assignments, or records a justified no-change result.

### Luna implementation prompt — E14

```text
Work on E14 — Calibrate category-fit coverage from retained outcomes at the current MarketLense HEAD.
Owner specification: docs/backlog/E-evidence.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
---
 
## E15. Make publication crops visually complete and repairable

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `CROP-01`, `CROP-02`, `CROP-03`, `CROP-04`, `CROP-05`, `CROP-06`, `CROP-07`, `CROP-08`, `CROP-09`, `CROP-10`, `ARCH-G`.

- **Baseline (updated 2026-10-08):** Detection/ranking/refinement, raster QA/sidecars and escalation exist. The October 8 crop patch (`207d6213`) adds finite/ordered bbox validation, displayed-page affine transforms back to canonical PDF coordinates and guards against near-page expansion, with focused transform/invalid-bbox tests. These geometry tests do not discharge historical semantic clipping, incomplete QA or destructive inward-refinement risks. A human-labelled `publication_strict` corpus, completeness/coverage measurement, final publication-DPI proof and verified directional repair remain open; no fresh human visual audit was performed.
- **Current scoped evidence:** Final figure promotion now requires an accepted `publication_strict` crop at configured final DPI with QA-sidecar and image-checksum proof; candidate previews are re-rendered before promotion, and cache reuse checks both rendered image and QA sidecar hashes. This closes an artifact-provenance gap only; human semantic completeness and the retained production-strict corpus remain open.
- **Target behaviour:** Every accepted publication crop contains the complete semantic visual—chart/table title when attached, full plot/table body, axes, labels, legend, annotations, headers, rows/columns, units, and attached note/source where applicable. Modest safe whitespace is preferable to missing content. Final geometry is localized once, protected by deterministic PDF-aware guardrails, rendered consistently, validated by type-specific completeness checks, and repaired by changing the bbox in the correct direction rather than cosmetically trimming an already-rendered PNG.
- **What to implement, in order:**
  1. Establish a retained human-labelled production crop corpus of roughly **50–100 visuals across 15–20 materially different publishers/report layouts**, with target visual identity, expected/acceptable bbox, required semantic components, defect edge/type, publication-ready decision, and exact source/producer hashes. Stratify ordinary charts/tables plus dashboards/multi-panel figures, external/shared legends, dense labels, rotated content, raster/vector mixtures, dark/coloured backgrounds, full-bleed slides, footnotes/sources, multi-column tables, and continued/multi-page tables. Measure candidate recall separately from bbox completeness so discovery misses are not confused with crop failures.
  2. For the small set of final ranked publication candidates, make visual crop localization mandatory until retained evidence proves a boundary-confidence skip is equivalent. Feed the model both an annotated full-page image with the candidate box visibly marked and a higher-resolution local context image around the candidate (roughly **180–220 DPI**); map the returned geometry deterministically back to PDF coordinates.
  3. Make the crop-refine objective explicit and ordered: **semantic completeness → exclusion of unrelated neighbours → safe margin → tightness**. Define required components separately for charts and tables and prefer a small margin over uncertain exclusion of an attached title, label, legend, note, or source. Label whether a panel is independently meaningful or requires a shared title/legend; treat a continued/multi-page table as ineligible for a single crop unless the complete reading order and repeated-header relationship are proven.
  4. Simplify post-model geometry to safety guardrails rather than repeated re-cropping: normalize page rotation/crop-box/media-box transforms, intersect with the physical page, fall back to the original candidate bbox on invalid/empty model output, expand for meaningfully intersected text/table rules/attached components, add a small safety margin, and prohibit heuristic inward shrink unless the removed region is provably whitespace/unrelated. Never convert an invalid model bbox into a whole-page crop.
  5. Standardize every crop that can become public to the configured final publication resolution (**216 DPI** under the current profile). Treat candidate-pack/preview crops as previews; do not reuse a lower-DPI cached crop as the final public asset unless its sidecar proves the required publication DPI/profile.
  6. Reduce raster trimming to conservative, provable background removal with a small per-edge cap and retained safety padding. Remove clipped-content defects from inward trim repair; a crop that is missing content cannot be repaired by deleting more pixels.
  7. Implement directional bbox repair with at most one bounded rerender by default: neighbour contamination shrinks only the offending edge; clipping or a missing semantic component expands only the relevant edge. Retain before/after bbox, defect edge/type, repair action, render profile and QA result in the sidecar.
  8. Make final QA type-aware and rejecting: table validation checks outer-rule/text crossings plus complete headers/rows/columns where detectable; chart validation checks all four edges and protects title/legend/axes/labels/annotations/source. Reject a whole-page or near-whole-page result when the labelled target is a smaller semantic visual, and reject unsupported panel separation or incomplete continued tables. Normalize defect labels so deterministic QA, escalation and release gates use the same canonical taxonomy.
  9. Run the retained corpus through the actual `publication_strict` path before and after the change, including the model-localization path where applicable. Use the human labels—not the cropper's own score—as the primary correctness outcome; only after the target is met should adaptive skipping or heuristic deletion be reconsidered for cost/speed.
- **Acceptance criteria:**
  - On the retained representative corpus, **100% of accepted publication crops** receive a human `publication_ready` decision with no blocking semantic clipping, wrong-panel selection, unrelated-neighbour contamination, incomplete continued table, or missing required title/axis/label/legend/header/row/column/note/source. At least **95% of human-labelled eligible visuals** produce an accepted publication-ready crop; the rest are explicit typed rejections/escalations, so precision cannot be achieved by rejecting everything.
  - The before/after corpus shows a material reduction in clipping and neighbour-contamination defects versus the exact retained baseline with no material regression in candidate recall or selected-visual usefulness.
  - Invalid/out-of-page/empty model geometry never becomes a whole-page crop; it deterministically falls back to the original candidate geometry or a typed rejection.
  - `edge_clipped_content`/missing-component failures can only trigger bbox expansion/rerender or rejection, never an inward PNG-only trim; neighbour contamination can only shrink the implicated edge.
  - Table completeness rejects a demonstrably cut boundary/header/row/column and any incomplete continued/multi-page table represented as complete; chart completeness evaluates all four edges. Multi-panel/shared-legend fixtures keep exactly the human-labelled semantic unit and required shared components, while near-whole-page false fallbacks are rejected.
  - Rotated pages and non-default PDF crop/media boxes map annotated/local model geometry back to the same intended PDF region within the retained tolerance; no transform error can silently select another panel or clip a required edge.
  - Every final public crop sidecar proves the configured publication DPI/profile, and lower-DPI preview/fallback artifacts cannot silently enter the public asset set.
  - Focused tests cover annotated/local vision inputs, invalid-bbox fallback, directional repair, four-edge chart validation, table-boundary rejection, conservative trim, DPI reuse, and sidecar taxonomy; the retained production-strict golden/human corpus passes on the exact implementation SHA.
  - The final selected-visual path remains bounded: no more than the configured localization call plus one repair/rerender per candidate by default, and no new model/library is introduced unless the retained corpus proves the existing stack cannot reach the target.

### Luna implementation prompt — E15

```text
Work on E15 — Make publication crops visually complete and repairable at the current MarketLense HEAD.
Owner specification: docs/backlog/E-evidence.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
### Linked technical implementation slices

Technical IDs below are **subtasks or investigations**, not additional canonical Active outcomes. Status notes are historical catalogue/reconciliation claims and require current-HEAD verification.
 
<a id="crop-01"></a>
#### CROP-01 — Add human semantic labels to the executable crop benchmark

**Primary canonical owner:** [E15](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependency:** P0 / M plus human review / none. Start the evaluation harness first; corpus completion can proceed alongside fixes.
- **Evidence and impact:** `scripts/quality/pdf_crop_refine_benchmark.py:20–69,104–163` records artifact/decision signatures, counts and estimated calls. `scripts/quality/crop_qa_scorecard.py:13–108` measures the cropper's own scores/defects. The golden README covers three report families. These are useful reproducibility checks, but cannot establish semantic completeness or best-value selection independently. Current E15 explicitly remains Active.
- **Luna implementation:** Extend the existing benchmark with a versioned label manifest: exact PDF/artifact hash, report/page/candidate identity, eligible target bbox/tolerance, required component boxes, editorial usefulness grade, acceptable shared-panel unit, reviewer attribution and publication-ready decision. Retain original source PDFs or approved immutable references; never infer labels from existing QA scores. Add separate denominators for target detection, shortlist retention, useful selection, crop coverage, accepted-crop precision, explicit rejection and missing labels. Bootstrap with existing IAS/Julius Baer/Worldpanel and `candidate_extraction/golden/crop_quality_v1`; expand toward E15's 50–100 visuals across 15–20 publishers/layouts. Missing source/labels must be `unmeasured`, never a pass. Do not have Luna impersonate the human reviewer.
- **Success criteria:** Every evaluated target has compatible source/producer identity; every failure remains in its denominator. Release objective: 100% human-ready precision among accepted crops and ≥95% coverage of labelled eligible targets; missing required component, wrong panel or unsupported continuation is blocking. Report candidate recall separately, with no material regression against the unchanged baseline.
- **Validation:** Add labelled complete/clipped/wrong-panel/abstained/missing-source cases to `tests/test_pdf_crop_refine_benchmark_gate.py` and `tests/test_crop_qa_scorecard.py`. Run `python -m pytest -q tests/test_pdf_crop_refine_benchmark_gate.py tests/test_crop_qa_scorecard.py`; preserve `python scripts/ci/check_pdf_crop_refine_benchmark.py`. Extend that existing gate to run the canonical `publication_strict` crop path using retained model decisions, with a separate bounded opt-in actual-model lane. Inspect generated crops against independent labels before refreshing any goldens.
- **Backlog overlap:** Implementation-sized measurement work for E15 steps 1/9; extends Closed E4/E5, does not reopen them or claim existing stability is semantic quality.

**Luna implementation prompt — CROP-01 (copy/paste)**

```text
Implement CROP-01 — Add human semantic labels to the executable crop benchmark.
Objective: Deliver the verified behavior specified immediately above under canonical E15.
Source: docs/backlog/E-evidence.md, technical slice CROP-01.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E15 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="crop-02"></a>
#### CROP-02 — Preserve small but valuable visuals through shortlist filtering

**Primary canonical owner:** [E15](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependency:** P1 / M / CROP-01 labels for promotion.
- **Evidence and impact:** `src/generators/_report_selection_generator/ranking.py:150–246` hard-rejects charts under 3.5% page area and weakly structured tables; priority rewards large area, row/column count and numeric density. `:308–365` truncates before semantic ranking. A compact high-value metric or qualitative comparison can therefore disappear before the model ever assesses it. This is a plausible recall risk from code, not a measured current false-negative rate.
- **Luna implementation:** Distinguish indisputable junk from uncertain candidates. Keep hard rejects for invalid geometry/known decorative evidence; turn uncertain size/data heuristics into priority penalties with bounded reserved shortlist slots. Select the normal deterministic shortlist plus a small stable reserve of plausible small/qualitative/text-dense visuals, under the existing total `rank_max_candidates` cap. Preserve reason codes and candidate IDs. Use available caption/context and typed features; no full-report model scan or publisher exceptions. Handle tiny standalone KPI cards as eligible only when units/context are present, not every number as a chart.
- **Success criteria:** On the fixed labels, ≥95% of eligible valuable visuals survive detection-to-shortlist; no regression in normal-chart/table recall; ranking candidate count and calls remain bounded by configured caps. All hard rejections have an auditable reason. False-positive shortlist volume must not rise above the frozen cap.
- **Validation:** Extend `tests/test_candidate_refine_selection.py` through its public test facade with a small valuable chart, two-row meaningful comparison, repeated decorative logo, prose block and cap-overflow cohort. Run `python -m pytest -q tests/test_candidate_refine_selection.py tests/test_pdf_candidate_benchmark_gate.py`; `python scripts/ci/check_pdf_candidate_benchmark.py`. Compare target recall and rank usage on the same retained cohort, not merely candidate counts.
- **Backlog overlap:** Supports E15 candidate-recall protection; extends existing Closed C3 shortcuts with measured safeguards, rather than deleting all deterministic filters.

**Luna implementation prompt — CROP-02 (copy/paste)**

```text
Implement CROP-02 — Preserve small but valuable visuals through shortlist filtering.
Objective: Deliver the verified behavior specified immediately above under canonical E15.
Source: docs/backlog/E-evidence.md, technical slice CROP-02.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E15 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="crop-03"></a>
#### CROP-03 — Rank visuals by incremental evidence value and remove redundant selections

**Primary canonical owner:** [E15](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependency:** P1 / M / CROP-01; CROP-02 recommended.
- **Evidence and impact:** `src/prompts/rank_candidates/user.yaml:1–36` emphasizes data density/metrics/insightfulness; `ranking.py:369–435` passes compact candidate rows without the report's analytical narrative. `figure_selection.py:35–78` ranks separate chunks of four; `_crop_refine/workflow.py:60–73,95–96,635–670` sorts by model score with per-kind quotas. There is no selection-level evidence-coverage objective here, so repeated versions of the same metric can consume slots and independently scored chunks may be weakly comparable.
- **Luna implementation:** Add a bounded, grounded editorial context to ranking: report title/topic, available source-page text and candidate-associated captions with page/evidence references, not regenerated prose. Selection currently precedes report analysis (`src/orchestrators/_report_generation_orchestrator/workflow.py:700,723`); do not depend on downstream analytical claims or reorder that pipeline. Link to bounded source evidence units already available at selection time. Require candidate-specific evidence-value reasons and supported source-evidence links in a versioned rank response. After individual scoring, use a deterministic small-set selector: disallow overlapping duplicates on the same page, penalize near-identical supported metric/context, prefer complementary source evidence/geographies/timeframes, and allow unused type slots when no worthwhile table/chart exists. Keep an overall cap and stable tie-breaks. Do not fill quotas with weak visuals or introduce an extra model call until measured need exists.
- **Success criteria:** Labelled top-k usefulness/NDCG improves ≥10% relative to the frozen baseline where room exists; duplicate-equivalent selected visuals ≤5%; all selected source-evidence links resolve to retained source spans; zero fabricated metric/period/unit. Same input yields same deterministic selection given retained rank outputs. Calls stay within existing ranking bounds.
- **Validation:** Add fixture cohorts with duplicate panels, repeated metric on two pages, distinct complementary source evidence, a strong all-chart report, and incomparable model scores from two chunks. Run `python -m pytest -q tests/test_candidate_refine_selection.py tests/test_key_figure_selection.py tests/test_figure_caption_generator.py`; replay selection through the existing report-selection workflow on the fixed labelled corpus. Track precision@k/usefulness and call/token deltas alongside crop completeness.
- **Backlog overlap:** Supports Active P17 adaptive visual stories and E15 selected-visual usefulness. This selects evidence; P17 owns the subsequent public narrative/layout.

**Luna implementation prompt — CROP-03 (copy/paste)**

```text
Implement CROP-03 — Rank visuals by incremental evidence value and remove redundant selections.
Objective: Deliver the verified behavior specified immediately above under canonical E15.
Source: docs/backlog/E-evidence.md, technical slice CROP-03.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E15 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="crop-04"></a>
#### CROP-04 — Localize selected visuals using an annotated overview and readable local context

**Primary canonical owner:** [E15](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependency:** P0 / M / CROP-01; CROP-05 transform contract before promotion.
- **Evidence and impact:** `_crop_refine/workflow.py:186–216,232–240,354–384` skips vision for `obvious_pass` and supplies one full-page image; `ranking.py:268–279` defines pass from structure/area/caption, not boundary certainty. Current `src/config/app.yaml:741–743` uses adaptive refinement, 110-DPI localization and 216-DPI final crops. Dense labels/shared legends cannot be assumed readable or correctly localized from these signals.
- **Luna implementation:** For the bounded final shortlist, replace the feature-based boundary bypass with mandatory localization until CROP-01 proves an equivalent safe skip. Render an overview with candidate ID and bbox visibly marked plus a local context crop at approximately 180–220 DPI; include neighbouring title/legend/note context. Extend the typed refine request/image service contract and prompt under `src/prompts`, including coordinate-frame metadata. Keep one localization decision per candidate/page batch plus at most one repair; consolidate existing coarse/finalize phases where the two inputs remove the need. Cache identities must include image hashes, render DPI, coordinate transform/version and localization-policy hash; the current `_crop_refine/cache.py:48–120` keys do not include render DPI.
- **Success criteria:** No publication candidate skips localization solely because it has many rows/area/caption. Dense/shared-legend targets meet CROP-01 completeness/coverage goals. Recorded input proves both views and mapping; changing DPI/transform invalidates refinement reuse. Calls remain explicitly bounded, with cancellation of unnecessary work.
- **Validation:** Extend `tests/test_candidate_refine_selection.py` with a fake canonical model service that records real generated overview/local images and returns retained decisions. Test dense labels, same-page neighbouring panels, shared legend and changed-DPI cache miss. Run `python -m pytest -q tests/test_candidate_refine_selection.py tests/test_pdf_crop_service.py`; run the existing crop benchmark plus labelled replay. Actual-model improvement requires an opt-in bounded cohort; offline replay alone cannot prove model localization accuracy.
- **Backlog overlap:** E15 steps 2/3/9/10; supersedes unsafe aspects of Closed C3 shortcuts without claiming vision/refinement is absent today.

**Luna implementation prompt — CROP-04 (copy/paste)**

```text
Implement CROP-04 — Localize selected visuals using an annotated overview and readable local context.
Objective: Deliver the verified behavior specified immediately above under canonical E15.
Source: docs/backlog/E-evidence.md, technical slice CROP-04.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E15 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="crop-05"></a>
#### CROP-05 — Reject invalid model geometry and normalize all page-coordinate transforms

**Primary canonical owner:** [E15](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

- **Priority / effort / dependency:** P0 / M / none; use CROP-01 for corpus acceptance.
- **Evidence and impact:** `src/services/_pdf/_crop/refine.py:215–221` intersects a proposed bbox with `page.rect` and substitutes the whole page when empty. `:98–101,140–151` exposes scale factors from rendered dimensions but no explicit rotation/crop-box transform in the response. A bad bbox can therefore become a plausible full-page asset, while rotated/non-default PDF boxes need explicit proof of coordinate mapping.
- **Luna implementation:** Validate finite, ordered, non-degenerate coordinates at the typed contract boundary. Carry the original candidate bbox and an explicit versioned affine transform from page/local-image coordinates to canonical PDF coordinates. Apply exactly one normalization for rotation/crop/media boxes. An invalid/outside proposal must fall back to a validated original candidate bbox with a degraded reason, or produce a typed rejection; never a whole-page fallback. Reject implausible jumps to near-whole-page unless the source-labelled target genuinely is full-page. Preserve canonical candidate identity and page reference.
- **Success criteria:** NaN/infinite/reversed/empty/out-of-page proposals never yield a whole-page accepted crop. Rotations 0/90/180/270 and shifted crop boxes map the intended visual within 1 PDF point on deterministic fixtures. Valid full-bleed infographics remain eligible. Failures are explicit and nonretryable when geometric evidence is invalid.
- **Validation:** Extend `tests/test_pdf_crop_service.py` and `tests/test_candidate_refine_selection.py` using locally built PDFs with asymmetric corner labels, rotation and non-default media/crop boxes; assert emitted crop pixels/components through public PDF operations. Run `python -m pytest -q tests/test_pdf_crop_service.py tests/test_pdf_crop_decomposition.py tests/test_candidate_refine_selection.py`; preserve both PDF benchmark gates. Compare before/after bounded-region outputs on retained PDFs.
- **Backlog overlap:** E15 step 4 and transform/invalid-output acceptance criteria.

**Luna implementation prompt — CROP-05 (copy/paste)**

```text
Implement CROP-05 — Reject invalid model geometry and normalize all page-coordinate transforms.
Objective: Deliver the verified behavior specified immediately above under canonical E15.
Source: docs/backlog/E-evidence.md, technical slice CROP-05.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E15 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="crop-06"></a>
#### CROP-06 — Protect the complete semantic bbox through one final geometry pass

**Primary canonical owner:** [E15](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependency:** P0 / M / CROP-05; CROP-04 for authoritative localization.
- **Evidence and impact:** `src/services/_pdf/_crop/geometry.py:450–552` expands intersected text then trims small intersections. `regions.py:218–238` subsequently calls chart/table tightening and another strict tightening. `regions.py:450–527` also trims the raster. These consecutive inward operations can remove meaning after a valid localization decision.
- **Luna implementation:** Introduce one service-owned final geometry result containing protected semantic components, safe bbox and explicit permitted background-removal bounds. For publication mode, preserve the localized semantic region; expand to include attached text/rules/components, intersect the physical page, add a small safety margin. Inward deletion is permitted only for verified background/unrelated content, with no overlap with protected components. Remove redundant publication-mode tightening passes rather than adding another heuristic. Keep legacy preview geometry behaviour where not required by this fix. Update artifact producer versions/cache keys for changed geometry.
- **Success criteria:** 100% of required title/axis/legend/label/table/header/note/source component boxes remain inside the emitted crop; modest whitespace is accepted. No removed region overlaps a protected component. Neighbour contamination does not increase against fixed labels; all geometry changes have recorded reasons and are deterministic.
- **Validation:** Add close title, outside legend, long bottom note, dark background, dense edge labels and adjacent-panel fixtures to `tests/test_pdf_crop_service.py`; verify final emitted images rather than private helpers alone. Run `python -m pytest -q tests/test_pdf_crop_service.py tests/test_pdf_crop_decomposition.py`; both candidate and crop benchmark gates; CROP-01 canonical strict-path replay. Golden changes require reviewed visual evidence, not automatic replacement.
- **Backlog overlap:** E15 steps 3/4/6; addresses observed shrink bias through the existing PDF service facade, not a module-count refactor.

**Luna implementation prompt — CROP-06 (copy/paste)**

```text
Implement CROP-06 — Protect the complete semantic bbox through one final geometry pass.
Objective: Deliver the verified behavior specified immediately above under canonical E15.
Source: docs/backlog/E-evidence.md, technical slice CROP-06.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E15 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="crop-07"></a>
#### CROP-07 — Repair clipped content by expanding and rerendering the source bbox

**Primary canonical owner:** [E15](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependency:** P0 / M / CROP-05/06; CROP-08 defect evidence recommended.
- **Evidence and impact:** `regions.py:569–612` classifies `edge_clipped_content` and `neighbor_contamination` as repairable, then runs the same inward `_content_aware_trim` up to twice and promotes a higher scalar score. Deleting pixels cannot recover missing labels or rows; a score improvement alone does not establish repair.
- **Luna implementation:** Produce typed defect direction/component evidence. Route clipping to bounded outward bbox expansion and rerender from the original PDF; route contamination to conservative removal only when the removed area is proven unrelated. Contradictory/missing direction must reject/escalate, never guess. Let the orchestrator own one repair budget and retry policy; the PDF service owns deterministic rerendering. Re-evaluate every hard completeness defect after repair. Persist old/new bbox, changed edges, attempt count and outcome; do not repair a PNG in isolation when source content is missing.
- **Success criteria:** Each labelled single-edge clipping fixture either restores the required component or ends in explicit rejection within one repair. A crop with any unresolved blocking defect cannot be promoted because its aggregate score rises. No repeated identical bbox repair, hidden model retry, extra publication side effect or unbounded spend.
- **Validation:** Add cut top title/right legend/bottom footnote/left axis plus contamination and contradictory-edge cases. Run `python -m pytest -q tests/test_pdf_crop_service.py tests/test_crop_qa_escalation_generator.py tests/test_candidate_refine_selection.py`; replay canonical report selection through strict QA and escalation with isolated state and retained responses. Compare restored-component rate, rejection reasons and per-candidate call/latency caps on fixed labels.
- **Backlog overlap:** E15 steps 6/7/10; extends Closed C2 escalation by wiring effective repair instead of treating an escalation's `repair` decision as successful output.

**Luna implementation prompt — CROP-07 (copy/paste)**

```text
Implement CROP-07 — Repair clipped content by expanding and rerendering the source bbox.
Objective: Deliver the verified behavior specified immediately above under canonical E15.
Source: docs/backlog/E-evidence.md, technical slice CROP-07.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E15 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="crop-08"></a>
#### CROP-08 — Make chart/table completeness a rejecting semantic gate

**Primary canonical owner:** [E15](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependency:** P0 / M / CROP-01; CROP-06 protected components.
- **Evidence and impact:** `boundary_detectors.py:207–214` always returns `accepted=True` for table boundaries; `:217–234` checks chart left/bottom edges only; `:71–91` never turns table-boundary failure into a defect. `image_ops.py:225–296` derives completeness mostly from pixel density and catches generic clipping only when all edge densities exceed a threshold. Missing top titles/right legends/table rows can evade these proxies.
- **Luna implementation:** Combine source-aware component coverage/text/rule crossings with conservative raster evidence. Charts validate four edges, axes/labels/legend/title/units/annotations/attached note; tables validate headers, visible row/column extent and outer rules/text crossings. A legitimate full-bleed coloured panel must not be rejected solely for edge colour. Where deterministic evidence cannot establish a required component, use the existing bounded semantic escalation or reject explicitly. Define one canonical defect taxonomy shared by deterministic QA, escalation and release reporting. Semantic hard failures override aggregate readability/score. Do not claim edge-density thresholds alone prove meaning.
- **Success criteria:** Every labelled omitted required component is rejected before asset promotion, with the correct reason and edge/component; zero false acceptance in blocking clipping fixtures. Valid full-bleed/dark-background visuals retain ≥95% eligible coverage on the corpus. Missing/unknown semantic evidence is not silently treated as complete.
- **Validation:** Build matched complete/clipped pairs for all four edges, borderless tables, coloured full-bleed panels, legends outside plot and notes below tables. Run `python -m pytest -q tests/test_pdf_crop_service.py tests/test_crop_qa_scorecard.py tests/test_crop_qa_escalation_generator.py`; existing crop benchmark and independent-label replay. Report precision/coverage by visual type and layout, not only mean QA score.
- **Backlog overlap:** E15 step 8; adds rejecting completeness to existing detectors rather than proposing detectors/QA from scratch.

**Luna implementation prompt — CROP-08 (copy/paste)**

```text
Implement CROP-08 — Make chart/table completeness a rejecting semantic gate.
Objective: Deliver the verified behavior specified immediately above under canonical E15.
Source: docs/backlog/E-evidence.md, technical slice CROP-08.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E15 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="crop-09"></a>
#### CROP-09 — Apply one final-publication profile to every reuse and fallback path

**Primary canonical owner:** [E15](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependency:** P0 / S–M / none; CROP-08 for semantic proof.
- **Evidence and impact:** `figure_selection.py:825–847` passes `final_crop_dpi` for selected slices, but `:893–928` loads candidate crop paths without validating strict sidecars/profile; `:960–974` fallback CropRequest omits DPI. `_figures/best_figure.py:177–273` can return an extracted embedded image without the strict crop path, and `figure_selection.py:606–626` constructs a legacy asset with no QA proof. Normal-path final-DPI tests already exist; fallback quality/DPI remains the gap.
- **Luna implementation:** Require a compatible publication artifact descriptor before any path is promoted to `ReportFigureAsset`: source/candidate hash, accepted strict QA, producer/policy version, final DPI/profile and image hash. A candidate preview can be reused as evidence but must rerender at the configured final DPI when its descriptor is incompatible or missing. Explicitly pass `final_crop_dpi` to fallback crops. Route the legacy best-image path through the same final validation/render boundary or omit it with a typed no-usable-visual reason. Reject/miss stale/tampered sidecars. Do not merely upscale low-resolution bitmap evidence and claim it becomes readable.
- **Success criteria:** Every public figure asset has accepted compatible `publication_strict` proof and the configured 216-DPI profile under the present configuration; preview-only/lower-DPI/missing-proof assets never silently publish. Warm compatible reuse renders nothing; incompatible reuse rerenders once. Readability failure in low-resolution source images is explicit.
- **Validation:** Extend existing fallback tests in `tests/test_candidate_refine_selection.py`: 110-DPI preview, absent/rejected/tampered sidecar, valid 216-DPI reuse, newly cropped fallback and legacy embedded bitmap. Run `python -m pytest -q tests/test_candidate_refine_selection.py tests/test_pdf_crop_service.py tests/test_render_service_figure_linkage.py`; replay a rank failure and all-crop rejection through selection/render/readiness in isolated output directories. Inspect asset-sidecar links and final DPI.
- **Backlog overlap:** E15 step 5; safeguards existing Closed E7 artifact reuse rather than removing it. Existing reuse tests that expect unconditional path reuse should be updated to assert the public invariant.

**Luna implementation prompt — CROP-09 (copy/paste)**

```text
Implement CROP-09 — Apply one final-publication profile to every reuse and fallback path.
Objective: Deliver the verified behavior specified immediately above under canonical E15.
Source: docs/backlog/E-evidence.md, technical slice CROP-09.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E15 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="crop-10"></a>
#### CROP-10 — Treat continued tables and shared-panel visuals as explicit semantic units

**Primary canonical owner:** [E15](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependency:** P1 / M / CROP-01/05/08; CROP-06 recommended.
- **Evidence and impact:** `table_continuation.py:231–326` already recognizes some adjacent wide tables and appends/prepends title/note strips using header-token matches. `regions.py:529–559` stacks those strips around each base image. That does not demonstrate that all continuation body rows were included or that two unrelated similar-header tables belong together. `_write_crop_diagnostics` in `regions.py:714–759` records one base page/bbox, not every composed region. E15 explicitly includes continued tables and shared legends.
- **Luna implementation:** Add a versioned semantic-unit descriptor: component candidate IDs, ordered source pages/bboxes, repeated-header relationship, required shared title/legend/note and complete-versus-fragment status. Detect continuation before final selection so selecting one fragment cannot falsely imply completeness. Default to explicit ineligibility for a single complete-table asset unless all parts are available and reading order/header compatibility is proven. If composing, include the full relevant body regions once, preserve column widths/units and retain per-region transforms/provenance; do not stitch just title/note strips into a falsely complete table. Use the same descriptor to prevent separating dashboard panels that require a shared legend/title. Bound composition size; no speculative arbitrary-document reconstruction.
- **Success criteria:** Every published continued table has all labelled rows/columns/header/units and correct order, or is explicitly rejected as incomplete. Unrelated adjacent tables with matching generic headers never merge. Shared-legend panels retain required shared components and correct identity. Every composed pixel region resolves to an immutable source page/bbox/hash.
- **Validation:** Extend existing `build_stream_country_table_split` fixtures with a two-page complete table, selected-only-second fragment, three-page continuation, unrelated matching-header tables and incompatible column-width case; add independent/shared-legend panel pairs. Run `python -m pytest -q tests/test_pdf_crop_service.py tests/test_pdf_figures_service/test_table_heuristics.py tests/test_candidate_refine_selection.py tests/test_render_service_figure_linkage.py`; labelled strict-path replay with source-coordinate/provenance checks. Verify no missing/duplicated rows, misleading complete labels or new unsupported metric claims downstream.
- **Backlog overlap:** E15 steps 3/8 and provenance requirements; strengthens existing continuation augmentation, does not claim continuation support is absent.

Suggested sequence: begin CROP-01 labels/harness; deliver CROP-05 and CROP-09 first for bounded safety corrections; then CROP-04/06/08/07 for complete cropping; then CROP-02/03/10 for recall, evidence value and complex semantic units. Do not claim E15 closure from these code changes alone: it requires the frozen human-grounded production-path outcome on the exact implementation SHA.

**Luna implementation prompt — CROP-10 (copy/paste)**

```text
Implement CROP-10 — Treat continued tables and shared-panel visuals as explicit semantic units.
Objective: Deliver the verified behavior specified immediately above under canonical E15.
Source: docs/backlog/E-evidence.md, technical slice CROP-10.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E15 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="arch-g"></a>
#### ARCH-G — Generate and fact-check figure captions from canonical approved context

**Primary canonical owner:** [E15](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / follow-ups C/D, `E15`, `P17`; extends existing `figure_caption_generator.py` and current grounding, not a new multimodal validator service.
- **Evidence / diagnosis:** `report_analysis_orchestrator.py` invokes `generate_figure_captions()` after artifact generation but before the initial comprehensive report-validation pass. Captions use figure context plus generated summary/findings, with image-model output and an optional fail-open detected/legacy caption fallback. The retained-claim inventory primarily targets structured editorial/public prose; the reviewed path does not establish equivalent semantic source-grounding for materially factual new figure captions.
- **Luna implementation:** Generate captions once from the validated promoted factual snapshot, preferably during render preparation or an equivalent post-validation stage; regenerate only when the exact figure/factual context changes. Reuse direct, source-derived captions when descriptive and correct. Bind material generated caption claims to the approved figure/source evidence and run existing protected-fact, quantity and semantic checks as applicable. A caption without established support must fall back to safe source wording or omit the material assertion; an optional caption failure must not bypass E15 image completeness or corrupt provenance.
- **Success criteria:** Invalid or rolled-back insight statements do not feed published captions; wrong quantified/causal/geographical caption claims cannot reach public HTML; optional caption failure does not block an otherwise publishable source-caption fallback, and no unavailable/unsafe visual becomes eligible.
- **Validation:** Test caption claim changes after an atomic repair, cached caption invalidation, source-detected fallback, visually complete but semantically false captions and publication-projection hashes. Use real accepted chart/table assets and one historical failure; measure extra calls, avoided calls and render latency.

**Luna implementation prompt — ARCH-G (copy/paste)**

```text
Implement ARCH-G — Generate and fact-check figure captions from canonical approved context.
Objective: Deliver the verified behavior specified immediately above under canonical E15.
Source: docs/backlog/E-evidence.md, technical slice ARCH-G.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E15 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
 
## E16. Make methodology, applicability, and uncertainty decision-grade

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `ANA-01`, `ANA-10`, `GRD-05`, `GRD-06`, `GRD-07`, `GRD-10`.

- **Baseline:** Explicit methods/limitations prompts, extraction strategies, family status, validation and free-text presentation exist. `src/schemas/methods_pack.schema.json` and `normalize_methods` still admit arbitrary objects; limitations normalization collapses structures to strings. Typed fact-level page/span identities, finite incomplete/conflict states and claim/action applicability links are absent. Retained PDF goldens include legacy tool-call-shaped methods and non-current limitation shapes; they are compatibility fixtures, not independently labelled methodology-quality evidence. E16 owns the underlying facts/constraints; P8 owns presentation and P16 decision logic.
- **Target behaviour:** Material methodology, scope, limitation, and uncertainty facts are versioned, source-linked, and machine-checkable. Missing disclosure remains an explicit unknown rather than an inferred weakness or invented fact. Claims and decision guidance are qualified or withheld when the evidence's population, geography, period, definition, method, or uncertainty does not support the proposed interpretation.
- **What to implement, in order:**
  1. Build a retained, human-labelled corpus spanning surveys/panels, market sizing, financial/administrative data, modelled forecasts, experiments, interviews/thought leadership, mixed-method reports, and reports with no usable method section. Label explicit sample/base, population, geography, fieldwork/data period, collection mode, weighting, coverage, metric definition, model/forecast basis, source-stated uncertainty, limitation, conflict, and applicability facts with exact evidence locations.
  2. Replace loose methods/limitations with a versioned typed contract and legacy adapter. Use finite `reported`, `not_reported`, `not_applicable`, `conflicting` and extraction-incomplete/unknown states. `not_reported` requires sufficient source coverage; legacy strings cannot acquire fabricated authoritative page/span roots.
  3. Extend existing methods/limitations prompt/extraction/reuse boundaries without another model step. Reject tool-call/operator/scaffold objects before accepting domain facts. Parse dates, samples, geographies, bases, units and definitions deterministically where adequate; validate probabilistic output against approved source roots and preserve abstention.
  4. Derive finite, explainable applicability/evidence-strength outcomes for the claims and decisions that depend on these facts. Record reason codes and the relevant scope mismatch or unknown; do not manufacture statistical confidence intervals, methodological quality scores, or causal strength when the source does not provide the inputs.
  5. Make claim validation, P16 decision synthesis, summaries/expert commentary, and cross-report comparison consume the same applicability constraints. P8 projects a concise safe subset publicly; internal provenance, diagnostics, and unsupported inferred judgments remain non-public.
  6. Add contract round-trip/schema snapshots, legacy-artifact migration tests, labelled-corpus extraction/grounding tests, contradiction/scope-mismatch fixtures, thin-source abstention fixtures, and retained expert-review evidence on the exact implementation SHA.
- **Acceptance criteria:**
  - Every accepted reported methodology/limitation fact has exact approved-source evidence identity and page/span provenance; no accepted fact invents sample size, fieldwork, weighting, geography, definition, uncertainty, model basis, or limitation.
  - On the retained labelled corpus, explicitly stated material facts achieve at least **95% recall**, while **100% of facts admitted to public or decision synthesis are human-verified correct and source-supported**; misses/rejections are reported separately so precision cannot be raised by suppressing the corpus.
  - Missing or ambiguous disclosure produces a typed unknown/conflict with an actionable reason, never a fabricated value, unqualified quality score, or silent assumption.
  - Independent source labels establish methodology accuracy; legacy PDF goldens remain compatibility tests. Tool/operator objects are never facts, and failed/incomplete extraction cannot be counted as source silence. Report extraction, completeness, applicability and compatibility denominators separately.
  - Every material claim or action whose applicability is limited by population, geography, period, definition, method, or uncertainty is explicitly qualified or withheld; incompatible scopes are never merged into one comparable trend.
  - Two independent methodology reviewers reach at least **90% agreement** with the system's supported/limited/unknown decisions on the retained cohort, with disagreements retained by reason code for remediation.
  - The change adds no provider call beyond the existing evidence/methods generation path, preserves legacy artifact readability through the declared transition, and passes schema, grounding, claim-validation, P6/P8/P16, readiness, and publication-projection tests.

### Luna implementation prompt — E16

```text
Work on E16 — Make methodology, applicability, and uncertainty decision-grade at the current MarketLense HEAD.
Owner specification: docs/backlog/E-evidence.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
### Linked technical implementation slices

Technical IDs below are **subtasks or investigations**, not additional canonical Active outcomes. Status notes are historical catalogue/reconciliation claims and require current-HEAD verification.
 
<a id="ana-01"></a>
#### ANA-01 — Preserve supported metric context through projection and readback

**Primary canonical owner:** [E16](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P0; M, three slices; GRD-07 for newly validated atomic observations. Existing metrics with already-approved context can be migrated independently. **Owner/backlog:** analytics projection contracts/store/readback; bounded extension to E16 methodology/applicability and P8 evidence transparency, not a second grounding validator.

**Evidence and impact:** `src/schemas/artifacts.schema.json:84–122` already carries `source_display_value`, numeric metadata, timeframe, geography, segment, comparator, subject, cohort, denominator and observation status. `_build_metrics()` in `src/generators/_analytics_projection/builders.py:117–159` discards them; `ReportMetricProjection` in `src/contracts/analytics_projection.py:155–170` lacks corresponding fields. `src/services/_analytics_store/cross_report_read.py:334–353` then provides only `context="pages=..."`. **Confirmed information loss:** downstream analysis cannot reliably distinguish a forecast from an observation or two differently defined percentages. The incidence of resulting bad Briefings is not measured.

**Luna implementation:** (1) Add a versioned context/quantity projection using approved artifact fields without deriving missing subjects, converting currencies or normalizing denominators. Preserve raw/source-display values alongside validated numeric metadata. (2) Add the smallest reports migration and lossless round-trip adapters; legacy rows carry explicit unknown fields, not invented defaults. (3) Pass retained context into raw-metric references and canonical embedding metadata where useful, invalidating only genuinely changed embedding identities. Comparison consumers must require supported compatibility, using GRD-07 rather than rechecking source numbers here.

**Success criteria:** All supported fields round-trip exactly on 30 labelled metric cases; incompatible cohort/geography/forecast pairs never become equivalent observations. Valid legacy rows remain readable with unknown context and zero provider calls; migration is idempotent.

**Validation:** `python -m pytest -q tests/test_analytics_projection_foundation.py tests/integration/test_analytics_store_cross_report_reads.py tests/test_cross_report_analysis_contracts.py`. Add fixtures for percent versus percentage points, millions versus billions, denominator changes and forecasts; replay canonical projection→read→Briefing inputs with temporary SQLite and recorded external boundaries.

**Luna implementation prompt — ANA-01 (copy/paste)**

```text
Implement ANA-01 — Preserve supported metric context through projection and readback.
Objective: Deliver the verified behavior specified immediately above under canonical E16.
Source: docs/backlog/E-evidence.md, technical slice ANA-01.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E16 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ana-10"></a>
#### ANA-10 — Separate publication date, observation period and projection timestamp

**Primary canonical owner:** [E16](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P0; M, three slices; none; ANA-01 supplies metric-level observation periods. **Owner/backlog:** analytics temporal projection/filtering; reuse existing publication-metadata resolution and E16 applicability, not another publication-date resolver.

**Evidence and impact:** `_report_date()` in `src/services/_analytics_store/cross_report_read.py:124–133` uses report `time_period`, otherwise the projection date. `_report_passes_filters():182–190` compares raw period strings lexically to ISO dates. Source selection subsequently parses `report_date` as a day (`src/generators/_cross_report_analysis_input/shared.py:109–126`) and scores recency. **Confirmed semantic conflation:** an undated old report reprojected today appears recent, while valid year/quarter/range periods become unparseable or inconsistently filtered. Existing source publication tables already have date/status/precision (`src/services/_sqlite_migration/_reports/schema.py:591–592,619–621`), so the required source of truth exists.

**Luna implementation:** (1) Extend analytics contracts/store/readback with supported publication date plus precision/status, observation-period bounds where explicitly known, and separate projection timestamp. Use existing resolved metadata; do not infer publication from upload/processing time. (2) Define each request date filter's semantic target explicitly and use validated interval comparison for partial dates; unknown dates abstain or receive a named exclusion reason. (3) Calculate recency only from the selected authoritative date semantics and retain unknown status; version/adapt legacy rows without fabricating exact January 1 dates.

**Success criteria:** Reprojecting unchanged content cannot alter publication recency. All 24 temporal fixtures filter correctly: exact dates, years, quarters, ranges, unknowns and malformed values; projection dates never substitute for publication. Equivalent interval forms yield identical membership, and conflicting/unsupported dates remain unknown. Migration is repeatable and provider-free.

**Validation:** `python -m pytest -q tests/integration/test_analytics_store_cross_report_reads.py tests/test_analytics_projection_foundation.py tests/test_cross_report_analysis_input_generator.py tests/test_source_identity_provenance.py`. Replay one old report before/after reprojection with a controlled clock and canonical source selection; assert stable membership, recency and source provenance, then run the affected Briefing theme-selection fixtures.

**Luna implementation prompt — ANA-10 (copy/paste)**

```text
Implement ANA-10 — Separate publication date, observation period and projection timestamp.
Objective: Deliver the verified behavior specified immediately above under canonical E16.
Source: docs/backlog/E-evidence.md, technical slice ANA-10.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E16 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="grd-05"></a>
#### GRD-05 — Preserve support grade and distinguish source extracts from model rationale

**Primary canonical owner:** [E16](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies / owner:** P0 / S–M, two slices / GRD-01/02 / findings normalization and support metadata. **Backlog:** E16 underlying evidence-strength facts and A21; public presentation remains P8, synthesis remains P16.

**Evidence and impact:** `src/generators/evidence_packs/findings_strategy.py:43–46` accepts `rationale` as fallback `evidence`; its normalized payload at lines 53–70 omits `quality_grade`, `support_grade` and `evidence_quality_grade`. `src/generators/validation/claim_support.py:190–238` consumes these grades but defaults findings to `explicit_finding`. **Confirmed and locally reproduced:** `weak_paraphrase` is dropped by `normalize_findings()`. A model explanation can therefore become evidence-shaped text and missing explicit weakness can become a stronger default. Separate source-fidelity checks still exist, so this is not evidence of a whole-pipeline gate bypass.

**Luna implementation:** (1) Define finite evidence-kind/support-grade semantics, preserving allowed grades across normalization, schema and retained packs. Keep source excerpts, model rationale and navigation summaries in separate fields. A missing grade is unknown/unassessed, not automatically direct proof. (2) Derive promotion to source-backed only from successful canonical source-root fidelity; do not trust a model's `direct_quote` label alone. Maintain a declared legacy adapter and update relevant prompts through prompt_service. Strong-claim policy consumes the canonical support grade rather than a parallel heuristic.

**Success criteria:** Weak grades survive all round trips; rationale-only findings cannot masquerade as literal source extracts. Grade promotion has retained source-fidelity evidence. Strong quantitative/absolute claims with unresolved support are qualified/withheld; valid direct facts retain current inexpensive deterministic paths.

**Validation:** Run `python -m pytest -q tests/test_evidence_pack_common.py tests/test_evidence_pack_generator.py tests/test_primary_generation_prompt_grounding.py tests/test_claim_validation_generator.py`. Add weak-grade, rationale-only, direct-extract, unknown-grade and forged-direct-grade fixtures; canonical normalization→source-fidelity→summary-support replay must preserve grade/root identity and show zero additional provider calls on unchanged valid deterministic evidence.

**Luna implementation prompt — GRD-05 (copy/paste)**

```text
Implement GRD-05 — Preserve support grade and distinguish source extracts from model rationale.
Objective: Deliver the verified behavior specified immediately above under canonical E16.
Source: docs/backlog/E-evidence.md, technical slice GRD-05.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E16 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="grd-06"></a>
#### GRD-06 — Retain all evidence fragments instead of discarding everything after the first

**Primary canonical owner:** [E16](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies / owner:** P1 / M, three slices / GRD-01/03/05 / evidence-pack adaptation. **Backlog:** A21 provenance and E16 applicability facts; CROP-10 handles visual/table continuation rather than textual evidence adaptation.

**Evidence and impact:** `src/generators/evidence_packs/common.py:156–182`, `extract_evidence_text()`, returns the first usable item in an evidence list. `normalize_findings()` at findings-strategy lines 43–46 uses that scalar extraction. **Confirmed and locally reproduced:** a value fragment followed by a geography/time/sample fragment is reduced to the first string, although plural pages remain. This loses qualifications that quantitative support needs and can cause either rejected valid claims or accepted overbroad interpretations; full-pipeline rates are unmeasured. Naively concatenating all fragments would also erase which qualifier belongs to which observation.

**Luna implementation:** (1) Introduce a bounded versioned fragment list with fragment identity, source text hash, page/span root, role and grouping relationship. Preserve scalar legacy evidence as a single explicitly adapted fragment. (2) Normalize every valid fragment, retaining deterministic order and deduplicating only identical source identity/hash. Cap fragment counts/characters using existing payload limits; overflow must be explicit, not silently dropped. (3) Feed claim-specific fragment groups to existing support/semantic inputs, preserving quote boundaries and qualifiers; retain a display string only as a derived compatibility field, never the authoritative lineage.

**Success criteria:** Value, denominator, period, geography and note fragments survive normalization/persistence without unrelated groups merging. Unsupported/unrooted fragments cannot become authoritative by adjacency. Same fragment group produces stable evidence hashes; changed qualifiers invalidate affected support. Provider input growth stays bounded.

**Validation:** Run `python -m pytest -q tests/test_evidence_pack_common.py tests/test_evidence_pack_generator.py tests/test_claim_validation_source_pages.py tests/test_retained_claim_grounding.py`. Add scalar/list/dict, multi-page qualifier, duplicated fragment, unrelated observation, empty fragment and overflow fixtures. Replay canonical source preparation→pack→claim package and assert complete fragment/root preservation, bounded serialized size and unchanged no-extra-call behavior for scalar legacy valid cases.

**Luna implementation prompt — GRD-06 (copy/paste)**

```text
Implement GRD-06 — Retain all evidence fragments instead of discarding everything after the first.
Objective: Deliver the verified behavior specified immediately above under canonical E16.
Source: docs/backlog/E-evidence.md, technical slice GRD-06.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E16 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="grd-07"></a>
#### GRD-07 — Bind numeric values to atomic source observations, not an unordered number bag

**Primary canonical owner:** [E16](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies / owner:** P0 / L, three bounded slices / GRD-02/03/06 / source quantitative support. **Backlog:** E16/A21 correctness foundation; ANA-01 owns lossless downstream metric projection/storage and ANA comparison work consumes these supported observations.

**Evidence and impact:** `src/generators/claim_validation_generator.py:550–577,1637–1667` flattens cited text into quantities and accepts each claim quantity when any matching evidence quantity exists. `src/contracts/protected_facts.py:213–240` compares sets of explicit values/units, while `metric_claim_text()` at claim-validation lines 456–475 assembles available context fields. **Confirmed and locally reproduced:** the fidelity validator locally supports “France 20%, Germany 40%” against “France 40%, Germany 20%”. Existing protected dimensions catch many mismatches, but unordered value/geography sets do not establish the relationship between them. This reproduction does not prove later full validation/publication acceptance.

**Luna implementation:** (1) Retain bounded atomic observations from approved source fragments: value/comparator/unit, subject, geography, period, population/denominator, observation status and span/cell root. Preserve raw displays and explicit unknowns. (2) Match claim observations directionally to one source observation or an explicitly documented source-linked derivation; matching different pieces from unrelated rows is forbidden. Simple supported extraction stays deterministic; ambiguous layout relations use existing bounded semantic evaluation or abstain. (3) Adapt retained metric claims to observation IDs and keep existing protected-fact diagnostics, hashes and gates authoritative. Do not normalize prices/periods/denominators or invent causal support.

**Success criteria:** Country/value, period/value and denominator/value permutation fixtures are never deterministically supported. Exact supported observations remain zero-provider; ambiguous relationships stay unresolved. Every accepted numeric relation traces to one approved observation/derivation and all displayed qualifiers.

**Validation:** Run `python -m pytest -q tests/test_claim_validation_generator.py tests/test_grounding_protected_facts.py tests/contracts/test_protected_facts.py tests/test_artifact_normalization_source_fidelity.py`. Add swapped countries, swapped forecast years, duplicate percentage/different denominators, signed directions, bounds and valid two-row fixtures; source→pack→metric→retained-claim replay plus labelled source observation review is required before claiming factual-error reduction.

**Luna implementation prompt — GRD-07 (copy/paste)**

```text
Implement GRD-07 — Bind numeric values to atomic source observations, not an unordered number bag.
Objective: Deliver the verified behavior specified immediately above under canonical E16.
Source: docs/backlog/E-evidence.md, technical slice GRD-07.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E16 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="grd-10"></a>
#### GRD-10 — Carry approved source-root lineage through cross-report evidence joins

**Primary canonical owner:** [E16](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies / owner:** P1 / M–L, three slices / GRD-01/03/07; coordinate ANA-01 / cross-report evidence reference contract. **Backlog:** P8 inspectable support, E16 applicability and A21 provenance. Existing frozen source hashes, report-scoped IDs and fresh-embedding checks remain intact; this is not another SYS output-hash/cache bug proposal.

**Evidence and impact:** `src/contracts/_cross_report_analysis/selection.py:222–240`, `CrossReportEvidenceReference`, has scoped evidence/report/entity IDs and open `source_metadata`, but no typed approved span/root/support disposition. `src/services/_analytics_store/cross_report_read.py:268–331` emits claim/finding evidence/pages and quote speaker/citation without canonical claim-package/span-root bindings. `src/generators/cross_report_analysis_generator.py:219–255`, `_validate_references()`, verifies selected-ID membership. **Confirmed metadata seam:** reference existence is established, but accepted original-source support is not encoded there. Hash-pinning and selected-ID validation already exist; fabricated synthesis acceptance is not proved.

**Luna implementation:** (1) Version cross-report references with approved report-artifact/source identity, claim-package/support-root identity, rooted spans and applicable observation IDs; project only bounded non-sensitive lineage. (2) Resolve joins within the existing read snapshot and reject/hold missing, mismatched or unapproved roots; legacy rows may remain diagnostic-only with explicit unavailable status until canonical projection refresh. (3) Carry immutable roots through synthesis evidence maps and retained output so approved citations can show page/source support without internal IDs. Preserve existing frozen-cohort and embedding freshness logic; no direct PDF/provider reread per citation.

**Success criteria:** Every accepted factual synthesis reference resolves to an approved original support record in the pinned source set. Orphaned, superseded and cross-report-colliding roots never silently become public support. Same source snapshot replays with zero extra provider calls; diagnostic unknown lineage is not claimed verified.

**Validation:** Run `python -m pytest -q tests/test_cross_report_analysis_contracts.py tests/integration/test_analytics_store_cross_report_reads.py tests/test_cross_report_analysis_input_generator.py tests/test_cross_report_analysis_generator.py`. Add temporary SQLite fixtures for valid joins, orphaned roots, refreshed source artifacts, report-scoped collisions and legacy missing lineage. Replay read→assemble→synthesize→render with recorded boundary results and reconcile every retained public reference to its approved source/span identity.

**Luna implementation prompt — GRD-10 (copy/paste)**

```text
Implement GRD-10 — Carry approved source-root lineage through cross-report evidence joins.
Objective: Deliver the verified behavior specified immediately above under canonical E16.
Source: docs/backlog/E-evidence.md, technical slice GRD-10.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update E16 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
---

## E17. Reduce LLM input, output, and cache cost without quality regression

**Canonical status:** Active; added 2026-10-11 as a new optimisation outcome, not as a completed code change or a refreshed run. **Mapped technical slices:** none from the archived proposal index; the five ordered implementation stages below are E17-local slices under this one canonical owner. **Priority:** P1; execute after current critical correctness/reliability blockers, unless measurement can proceed independently.

- **Baseline:** The retained 2026-10-06 single-report critical-path profile (47 calls) records 423,109 input tokens, 107,087 output tokens (35,614 reasoning tokens), and 53,889 cached-input tokens; grounding consumed 132,676 input and 72,460 output tokens. These are observed values for **one historical run**, not five-report averages, expected savings, or proof of current production economics. On inspected 2026-10-11 HEAD, `src/generators/validation/grounding.py` repeats `evidence_json` across bounded batches; `src/schemas/grounding_validation_output.schema.json` requires 12 protected dimensions with claim/evidence/status triples and repeated text; `artifact_base_variables` serializes whole DocMap/evidence packs for artifact prompts; and `src/services/_llm_service/openai_shared.py` does not populate cached-input telemetry in its Responses metadata adapter. Existing usage/pricing contracts record cached reads but not separately attributable provider cache-write tokens. Scope/methods/limitations can reuse the same shared retrieved source context. Do not extrapolate hypothetical savings from one report.
- **Target behaviour:** The existing LLM service sends the smallest **semantically sufficient** inputs and receives the smallest **complete, verifiable** structured outputs; provider caching reduces actual billed cost only where worthwhile. Source coverage, protected factual distinctions, exact evidence/provenance identities, editorial depth, successful autonomous completion, retries, and end-to-end elapsed time remain at least as good as the accepted baseline. Do not add another cache, token service, or generic context-rewriting layer.

- **What to implement, in order (one independently verified slice per commit):**
  1. **E17.1 — Attribute costs and establish baseline (P1).** Reuse the canonical provider usage adapter, usage ledger, costing/rate-card and existing quality/provider profiles. Measure per namespace/attempt: raw input/output, reasoning, cached-input reads, provider cache-write tokens **only where explicitly exposed**, known cache policy, charged/estimated cost, requests, repairs and wall-clock time; include relevant prompt-component sizes (instructions, schema, shared context, task-specific evidence and duplication) without logging sensitive prompt/report text. Reconcile Chat Completions and Responses adapters; unsupported write telemetry must be `unknown`, never silently zero. Respect A12/C1 accounting, A14 route economics and E10 reviewed price ownership; change the minimum contracts/migrations needed without duplicating those outcomes. Pin the existing frozen five-report cohort and accepted quality baseline before optimisation.
  2. **E17.2 — Compact grounding *output* contract (P1).** Investigate the actual share of reasoning versus JSON serialization before modification. Use a versioned, smaller provider-facing result with exact item IDs, verdicts, proposition status, necessary protected-dimension decisions and source/claim literal values where material. Omit echoed claim text and fully unknown dimension triples only where a deterministic, unambiguous adapter reconstructs the existing complete canonical contract. Preserve all 12 protected dimensions, incompatible facts, explicit unknowns, violation type/reasons, every public/retained item, fail-closed incomplete-coverage checks and substantive model judgment. Keep downstream validators, caches, claim package, recovery and publication contracts authoritative; version identities/invalidate incompatible reuse. Benchmark false accepts/rejects and structured recovery; do **not** initially lower reasoning effort or `max_output_tokens` to force shorter responses.
  3. **E17.3 — Remove redundant *input* context at generation boundaries (P1).** Measure overlap and eliminate only proved duplication: repeated grounding `evidence_json` versus claim-attached evidence; source-relevant corroboration without losing visual/source rechecks; and irrelevant full DocMap/evidence-pack fields in editorial plan, summary, insights, quotes, cover semantics and other artifacts. Use explicit task-specific projections built from existing canonical data, preserving original exact IDs, chart/table tuples, pages, source spans, period/population/caveats, counter-evidence, breadth and editorial-plan dependencies. Never strip source text by generic line-based truncation or replace the high-coverage DocMap with an unverified summary. Keep the internal canonical representations unchanged. Low-risk semantic-validation/ranking output shaping can be trialled only after the dominant measured opportunities.
  4. **E17.4 — Calibrate provider prompt-cache policy (P1).** Verify provider-specific supported controls and pinned SDK before using explicit cache hints or attempting to disable writes. Preserve beneficial stable-prefix reuse, especially grounding; avoid deliberately writing one-off report-specific bodies, images or OCR payloads without a demonstrated benefit. Keep local semantic response caching and E9 prompt-family materialisation separate from provider prefix caching. Compare cold/warm scenarios and cache-read/write economics, token charges, retries and latency; do not mistake cached tokens for physically avoided input tokens. If the provider does not expose cache-write quantity/control, state that limitation and optimise only measurable policy aspects.
  5. **E17.5 — Evaluate conditional secondary savings (P2).** Test combining scope, methods and limitations extraction into one schema-valid response from their shared source context, using existing pack normalizers/validators/status/provenance and preserving independent abstention/repair semantics; adopt only if complete coverage, parallel wall-clock time and reliability do not regress. Optionally trial smaller, equivalent semantic-verdict, figure-ranking, editorial-planning and cover-semantics responses. Do not shorten material DocMap, analytical insights, summary or expert reasoning simply to reduce output; if a candidate provides no credible net benefit, record **no change needed**.

- **Acceptance criteria:**
  - Exact-HEAD, frozen five-report **baseline and candidate** runs have compatible source/PDF hashes, task policies, prompt/schema identities, quality disposition and a per-namespace/attempt input/output/reasoning/cache/cost/latency/repair table. Historic single-run numbers are context only. Record any unmeasurable provider write usage, not manufactured estimates.
  - Output compaction retains one exact matching verdict per requested item and full canonical protected-fact semantics; no unknown/unsupported/contradicted dimension is fabricated or silently promoted to supported. Include adversarial numeric subject/cohort/period/denominator swaps, source ambiguity, unsupported editorial premises, incomplete JSON, cache-invalidation and repair/replay fixtures.
  - Input changes retain material report-theme breadth, relevant contrary evidence, exact source spans/IDs, methodology/limitations, chart/table relationships and all source-sensitive gates; no new factual false accepts, missed material source evidence or editorial flattening. Real report outputs, not only schemas/fixtures, are inspected.
  - Compared with accepted five-report results, no previously publishable report becomes invalid, and there is no material regression in grounded factual correctness, failure/repair rate, first-attempt success, publishing readiness, P6 editorial acceptance criteria, A21 reliability or publication projection. Re-run stochastic comparisons where one attempt cannot distinguish variance.
  - Each accepted change shows a **measured** improvement in total billed provider cost per successfully ready/publishable report, with wall-clock time non-regressing; report raw token changes separately from billed cache savings, retries, and any quality-recovery overhead. Savings targets are not assumed or achieved by narrowing the evidence corpus.
  - E9/A15/E10/R1/A21 and existing immutable provenance, privacy, budget, review/approval and sandbox publication safeguards remain authoritative. Before marking E17 Closed, retain results and producer SHAs in the existing `docs/quality/` or `docs/CTO_evidence/` evidence structure. If the cohort cannot substantiate a change, record `no change needed` and leave it unimplemented.

**Evidence update — 2026-10-25 (E17 P1.1 scoped verified-grounding input):**
The minimal `ee5ea175` slice removes only the repeated report-wide
`evidence_json` from verified grounding batches; complete canonical facts and
linked evidence remain in the existing batch payload, normal mode is
unchanged, recovery uses the same scoped variables, and the verified cache
identity advances with a `linked_batch_v1` scope marker. The accepted Adjust
baseline at `9b6ce50c` was not rerun. One fresh isolated optimized run on the
same hash-matched PDF reduced grounding input from **138,905 to 76,560
tokens (-44.88%)** and grounding cost from **$0.033034 to $0.029490
(-10.73%)**. The whole run observed **81 to 74 calls**, **1,017,364 to
831,132 input tokens**, **$0.197232 to $0.168355 (-$0.028877)**, and **1,144.0
to 1,063.0 seconds**; the whole-run deltas are not fully attributed because
the fresh model run selected a different non-grounding call mix. Three
structured-output recovery calls succeeded, with zero automatic repairs and
no workflow retry. Five final insights, five metric-spine rows, validation,
public editorial quality, and publication readiness passed; unsupported and
unresolved retained factual counts were zero. Direct PDF review confirmed
pages 9, 19, 29, and 35. The change is **KEPT** for the measured grounding
saving; E17 remains Active pending broader staged economics evidence. Full
metrics, repair ledger, and limitations are in
`docs/quality/verified-claims-step2-visual-shadow-20261018.md`.

**Completion evidence — E17 P1.1 — 2026-10-25:** Provider-free integration
tests now exercise real verified multi-fact batch construction and the actual
structured-output recovery path. They prove exact linked-fact retention,
exclusion of unrelated report facts, existing rejection of unknown evidence
IDs, verified recovery with `evidence_json="[]"`, and unchanged legacy recovery
serialization. The retained Adjust audit reconciles seven primary grounding
calls in each run: 138,905 → 76,560 input tokens and $0.033034 → $0.029490
primary grounding cost, a measured $0.003544 (10.73%) saving. The optimized
run's three successful structured-output recoveries are accounted for once in
the whole-run total; batch 06's trigger remains unknown because its retained
primary and recovery usage events contain no failure code or validation
diagnostic. The 59.482-second summed grounding-provider increase is retained
as an observation, distinct from the 1,144.0 → 1,063.0-second report
wall-clock decrease. The focused provider-free suite passed 236 tests; no
production behavior, prompt, schema, repair policy, publication state, or
live benchmark changed. **E17 P1.1 is complete; E17 remains Active.** E17.2
and later E17 slices remain unstarted. See the completion subsection in the
[Step 2 evidence report](../quality/verified-claims-step2-visual-shadow-20261018.md).

### Luna implementation prompt — E17

```text
Work on E17 — Reduce LLM input, output, and cache cost without quality regression at the current MarketLense HEAD.
Canonical status: CONSOLIDATED_TODO.md. Owner specification: docs/backlog/E-evidence.md.
Read AGENTS.md and the E17 baseline, staged work and acceptance criteria; inspect current code,
retained provider profiles, existing services/contracts and the accepted frozen five-report cohort.
Implement only the next unverified E17 stage, starting with E17.1 measurement. Do not combine
the five stages or relax factual/semantic, editorial, reuse, budget or publication safeguards.
Reuse existing usage, cost, schema, prompt, recovery and benchmark infrastructure.
Prove the objective with focused/adversarial tests and five-report before/after quality,
total billed cost, retries and wall-clock evidence; inspect actual outputs. Never assume savings.
Document exact HEAD/cohort, commands, measured results, skipped checks and remaining risks.
Update the canonical backlog evidence accurately; close E17 only when all criteria pass.
Commit and push the smallest verified slice.
```



---

## E18. Stabilize LLM report analysis and first-pass validation

**Canonical status:** Active; proposed 2026-10-11 from repository inspection and historical retained cohorts, **not** a verified current-HEAD stability regression or implementation. **Priority:** P1 (factual quality / autonomous first-pass reliability). **Mapped technical slices:** E18.1–E18.4 below, four sequentially verified stages under this single canonical owner; no new historical proposal-index IDs.

- **Observed baseline, not causation:** The existing insights-candidate prompt asks for 6–8 items while editorial plans allow 2–7 themes; candidates include LLM-authored relevance/novelty/metric scores, and final-insight and downstream prose stages still perform semantic editorial work. The current `effective_sampling_controls()` suppresses temperature/seed for configured GPT-6 reasoning calls; changing global temperature alone cannot stabilize those calls. Retained E11 three-report evidence establishes structured-output first-pass success only, not semantic/editorial repeatability. The historical October 2–3 A21 frozen 20-report run reached 16/20 readiness, with 8/20 bounded repairs; the later four-report rerun used a different producer SHA. Neither result proves that LLM output variability caused a failure, nor does it establish current-HEAD repeatability.
- **Target behaviour:** Identical approved report evidence produces materially consistent factual claims, protected metric/source bindings, selected themes and valid citations across independent model runs. Human-quality editorial wording and defensible analyst interpretation may vary; unsupported facts and bad source scope may not. First-pass validation and publish readiness improve without suppressing genuine violations, excessive model calls, lost report coverage or editorial flattening.
- **Ownership / no duplication:** A21 owns end-to-end first-attempt SLO and broad live cohort/readback; E18 owns **diagnosing and reducing within-report LLM analytical variability**. E16/GRD-07 owns any new atomic source-observation or methodology contract; E18 consumes existing source-bound evidence rather than rebuilding it. P17/ARCH-B owns a shared cross-surface evidence slate; E18 stabilizes use of the **current** editorial plan and insight-selection path, not a second ranking system. E13 owns candidate-repair promotion effectiveness; E18 changes only demonstrated unstable generation/validation behavior through existing scoped repairs. E17 owns token/cache economics; P6 owns independent human editorial acceptance; E11's closed structured-output milestone stays closed.

**Implementation evidence — 2026-10-13 (bounded E18.2 source-binding slice):** The Activate frozen-PDF page-53 defect was reproduced at the source-span boundary. Native text retained detached chart percentages but no platform-to-panel identity; page geometry did establish panel/cohort/metric rows, while platform identity was present only in the rendered logo labels. The implementation retains those as separately typed layout-derived and model-derived visual evidence, then checks the resulting platform/cohort/metric/population tuple in the existing factual validator. The exact frozen PDF replay supports the correct claim and rejects swapped platform values, swapped metrics, missing 50M+ cohort labels, population expansion, and removal of the visual identity span. The one targeted label transcription cost $0.000113 (967 input / 32 output tokens); an exploratory wider-crop call during diagnosis cost $0.000420, for $0.000533 total development usage. No OCR or publication was used. This is a narrow source-binding correction, not an E18 repeatability baseline or verification of final editorial quality/readiness; E18 remains Active.

**Implementation evidence — 2026-10-18 (Verified Claims Step 0 complete):** The exact frozen-five manifest was independently rehashed to 744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7; all five original PDFs matched the manifest MD5 and computed SHA-256. The retained current result at producer 469c13c15d0d654f60c04a84bb97bf7ee44d1de0 records 5/5 admission, validation and publication-readiness pass, zero operator interventions and no publication. Page-level inspection produced 15 independently confirmed source-reference cases, and the committed fixture record contains 39 candidate variants: 15 supported, 23 unsupported and 1 unresolved, with explicit forecast, cohort, denominator, comparative, geography, sign, reason-versus-observation, wrong-page and referral-period guardrails. Source-reference IDs are kept separate from persisted findings/doc-map IDs and editorial IDs; canonical factual bindings contain persisted findings IDs only, while DocMap references remain contextual. Current binding resolution is 4 exact, 8 partial and 3 explicitly unresolved. **Verified Claims Step 0: Complete — factual reference baseline established and approved for Step 1.** This closes only the Step 0 preparation task; E18 remains Active, repeated-run LLM stability and human editorial evaluation remain open, and Steps 2–7 have not started. The retained final-claim records have zero unsupported and zero unresolved factual claims, while 63 candidate-level unsupported propositions were correctly excluded by fail-closed evidence fidelity. The retained findings/doc-map/artifact dependencies are local-only and hash-pinned; their raw files are not committed. Report-level usage/repair attribution and repeated current-HEAD generation/validator baselines remain unavailable. The report and structured cases are docs/quality/verified-claims-step0-baseline-20261018.md and docs/quality/verified-claims-step0-reference-cases-20261018.json.

**Implementation evidence — 2026-10-18 (Verified Claims Step 1 shortlisting):** Implementation commits `cb5c7396`, `4596d6dd`, and P1 correction `a7fc47cd` update the existing selector/fallback boundary only. Final-stage wording now survives matching stable-ID selection while candidate metric/evidence/page/span fields remain authoritative; shared evidence IDs or excerpts no longer imply semantic equivalence; exact public duplicates still collapse only with compatible protected bindings; and fallback selection covers uncovered editorial themes before filling from eligible alternatives already filtered by fidelity and covered source IDs. The P1 factual-integrity correction groups same-ID candidates by compatible source identity and protected metric bindings before editorial ranking, fails closed on conflicting evidence or material metric fields, and restores complete candidate metric bindings including empty fields. Cache identity is now `evidence_backed_shortlisting:2`. Provider-free replay over the exact retained Capgemini, Activate, KPMG, Reuters Institute and Adjust artifacts preserved the same 29 selected IDs, 29/29 theme slots, final wording, evidence IDs, pages and spans; one Capgemini final-only metric binding was cleared and its lead order changed, while the other four reports retained their baseline order. Two-insight artifact-family results remain generated without padding, while the existing five-slot report-payload gate still rejects incomplete reports. The evidence ledger is [verified-claims-step1-shortlisting-20261018.md](../quality/verified-claims-step1-shortlisting-20261018.md). This is a **PARTIAL** Step 1 gate because the retained inputs are post-selection rosters and do not establish live pre-selector recall or repeated-run stability; E18 remains Active and Step 2 is unstarted.

**Implementation evidence — 2026-10-18 (Verified Claims Step 1 P2 provenance/numeric correction):** Commit `25e479d7` extends the same selector boundary with fail-closed physical provenance compatibility for same stable-ID candidates. Identical excerpts, overlapping spans, and source-consistent multi-page representations remain eligible; contradictory page, excerpt, or span bindings cannot be resolved by editorial score. The existing cache identity was advanced to `evidence_backed_shortlisting:3`, and focused regressions cover provenance ambiguity, alternative spans, numeric restoration, and invalidation of both prior selection versions. Provider-free replay against the exact frozen five-report retained artifacts compared with `a7fc47cd` preserved 29/29 selected IDs and wordings, 29/29 physical page/span bindings, 29/29 theme slots, and fallback availability. The real Capgemini candidate still has no structured metric binding, so its corrected replay intentionally omits the 62% metric spine/key figure rather than trusting final-only enrichment; a synthetic supported candidate value remains preserved downstream. No new live-quality claim, provider call, or publication write is made. Step 1 remains **PARTIAL**, E18 remains Active, and Step 2 is unstarted.

**Implementation evidence — 2026-10-18 (Verified Claims Step 1 final provenance-consistency correction):** Commit `2ce49d69` fixes the remaining shared-text shortcut at the existing selector boundary. When both candidates have concrete spans, span page/source/section/offset/excerpt compatibility is evaluated before top-level evidence text; conflicting source identities or non-overlapping physical excerpts fail closed, while overlapping spans and legitimate identical multi-page excerpts remain eligible. Cache identity is now `evidence_backed_shortlisting:4`. Provider-free replay against the exact frozen-five retained artifacts compared with `953555f` preserved 29/29 selected identities and wordings, all 29/29 theme slots, evidence IDs/pages/spans, protected metrics, metric-spine/key-figure counts, and fallback availability. No duplicate stable-ID group occurred in the retained roster, so the defect is covered by focused regressions rather than a live-frozen collision. No provider or publication writes were made. Step 1 remains **PARTIAL** only for the existing live-selection/repeated-run evidence limitation; no further Step 1 corrective work is indicated and Step 2 is unstarted.

**Correction evidence — 2026-10-19 (P1 source-evidence and duplicate-public-prose integrity):** Findings no longer self-support through their generated `text`; retained findings require an independent excerpt or an independently bound PDF source span, while quote-candidate source `text` and `quote_text` aliases remain valid. The selector now fails closed rather than score-resolving identical public prose with different protected metric signatures; matching stable IDs may use a distinct same-binding candidate formulation, and exact propositions with compatible bindings still deduplicate. Selection cache identity advanced to `evidence_backed_shortlisting:5`. Provider-free replay of the exact retained Capgemini, Activate, KPMG, Reuters Institute, and Adjust pack preserved **29/29** selected identities, **29/29** theme slots, wording, evidence IDs/pages/spans, protected fields, and zero duplicate public texts/evidence IDs. Focused suites passed: 93 claim-validation, 85 artifact-selection/normalization, 218 regeneration/contract, 75 public-quality, 58 Step 2, and 2,423 contract/schema/prompt tests. No provider, canonical, publication, or WordPress writes occurred. The cohort has no live collision, so the new behavior is supported by adversarial regressions rather than a fresh live-selection claim; Step 1 remains **PARTIAL** and Step 2 remains unstarted.

**Implementation evidence — 2026-10-18 (Verified Claims Step 2 visual correction and verification shadow mode):** The branch now contains versioned shadow-only contracts, separate correction and independent-verification prompt namespaces, complete physical-page rendering through the existing PDF service, GPT-6 Luna High policy enforcement, bounded two-attempt correction/verification, response-cache wiring, and immutable retained evidence bindings. Provider-free replay used the exact hash-matched frozen-five PDFs and retained artifacts: 15 source cases / 39 candidate variants, 29 retained selected insights, 29/29 theme slots, and zero source or publication writes. All 15 complete-page inputs were available, but no provider call was dispatched; therefore no corrected claim, verification rate, retry rate, false-accept/false-reject result, cost, or analytical-quality improvement is claimed. Focused and affected regression suites pass; the evidence ledger is [docs/quality/verified-claims-step2-visual-shadow-20261018.md](../quality/verified-claims-step2-visual-shadow-20261018.md). Step 2 is **PARTIAL** pending actual GPT-6 Luna High evaluation against the independent Step 0 reference cases; Step 3 remains unstarted and E18 remains Active.

**Correction evidence — 2026-10-18 (live Step 2 replay):** The dotenv-backed
configuration dispatched the bounded GPT-6 Luna High shadow replay over the
same 15 cases / 39 variants: 38 verified, 1 wrong-page case unresolved, 0
false rejects, and 1 unsupported-metric false accept. The run used 78 provider
calls and an estimated `$0.076812`; no corrected result was promoted,
persisted canonically, or published. The detailed ledger is
[verified-claims-step2-visual-shadow-20261018.md](../quality/verified-claims-step2-visual-shadow-20261018.md).
The earlier provider-free-only note above is superseded for provider
availability, but the overall Step 2 status remains **PARTIAL** because of the
false accept and outstanding human editorial review. Step 3 remains unstarted.

**Correction evidence — 2026-10-19 (verification reconciliation):** The final focused batches supersede the earlier counts in the preceding P1 correction note: 108 claim-validation, 88 artifact-selection/normalization, 218 regeneration/contract, 133 combined public-quality/Step 2, and 2,423 contract/schema/prompt tests passed. The repository type gate reports only 11 pre-existing unbaselined errors in `verified_claims_visual_generator.py`; the changed production modules add none. This correction made no provider or publication writes.

**Correction evidence — 2026-10-20 (CI grounding-contract and adversarial-gate closure):** The reviewed branch reproduced all 35 reported retained-grounding/cohort/report-analysis failures, while the same 139-test group passed in an isolated `origin/main` worktree. The failures were stale positive fixtures that supplied generated `findings[].text` without independent source excerpts; the fixtures now use the existing source-evidence contract, and generated-text-only negative cases remain fail-closed. The Step 2 adversarial runner now enforces exact nine-case identity/outcome matching, positive final text and source-page/hash/note provenance, with diagnostics, raw-result persistence and nonzero failure status; provider-free synthetic coverage passed 9/9 and rejected a corrupted strict-negative row. The focused final suite passed 151 tests with one expected integration skip and one deselected test. E18 remains Active: this closes the CI/test-contract and acceptance-gate defect, but does not establish the repeated-run stability, fresh selection-effectiveness, or independent editorial gates required by E18.1–E18.4. The aggregate local gate remains environment-blocked by the unchanged CPython 3.14 versus CPython 3.12 native-wheelhouse guard.
**Correction evidence — 2026-10-20 (final acceptance-integrity comparator):** The adversarial comparator now requires a matching successful verification attempt for positive outcomes and a substantive terminal source rejection for negative outcomes; missing-input, skipped, provider-error, malformed-response, and correction-only rows fail closed. It validates equal 64-character SHA-256 expected/actual values and the hash embedded in `source_identity`, and preserves the strict `BIG-ADV-002` page-8 binding against page-4 rescue. Provider-free result-shaped coverage passed 9/9 corpus identities and rejected a deliberate page-4 corruption. Hosted baseline run [39407483027](https://github.com/mbrakker/marketlense/actions/runs/39407483027) passed at `225d603e` on Python 3.12 with 7,845 pytest passes, 1 skip, both mutation jobs, and release evidence. The actual local merge-base is `bf736b47695605a9a00a1a8355c0d27ab0b0ab88`; the local Python 3.14 wheelhouse limitation is not a hosted failure. E18 remains Active and Step 2 remains **PARTIAL** pending fresh Step 1 selection effectiveness, canonical integration, and independent editorial approval.

**Correction evidence — 2026-10-20 (BigCommerce strict-page reconciliation):** Immutable v1 (`00b00a1d...`) accepted a stale page-8 wallet span after report-level recovery to page 4; immutable v4 (`6164b405...`) used the current strict no-recovery path and failed the same wrong-page row closed. Both bind the same PDF hash `29ffb53b9818460066c86e8d954bdd904bd0e11d2360d90dac040a5d33b9e7c3`; neither snapshot was overwritten. The visual boundary now omits unverified retained span text from correction/verification prompts, rejects a sufficiently specific strict span that uniquely matches another native PDF page, and clears model-supplied support-page metadata from non-verified attempts while preserving full internal/result spans. Three isolated actual-PDF BigCommerce runs verified the valid page-4 wallet case and failed the strict page-8 case closed (5–6 calls, $0.005763–$0.006871 each); no writes occurred. The stored v4 terminal counts are 8 verified/1 failed, while its pre-fix rejected-attempt metadata remains comparator-red; an in-memory normalized equivalent passes 9/9. E18 remains Active and Step 2 remains **PARTIAL**; Step 3 is unstarted. See [the Step 2 evidence report](../quality/verified-claims-step2-visual-shadow-20261018.md).

### Four stages — run in order, verify and commit separately

1. **E18.1 — Diagnose and pin a repeatability baseline (P1; prerequisite).** Inspect current prompts, evidence/doc-map retrieval, candidate generation, editorial-plan selection, model policies, validation, caches and repair telemetry. Reuse existing frozen-five source cohort and accepted artifacts. Start with provider-free comparison of retained outputs/audit metadata. Where insufficient, run a *budgeted* repeated experiment: at least three independent generation runs per report from identical frozen source/evidence inputs, with generated-analysis reuse disabled or isolated so a cache hit cannot masquerade as model stability; record a separate retrieval-stage experiment only if needed to explain different evidence sets. Independently run semantic validation at least three times on exactly the same pinned claim/evidence pairs. Compare hashes and substantive claim/selection identities, not prose byte equality. Attribute observed failures by stage, validator rule, evidence identity, real versus false-positive support failure, provider/model/policy/attempt, first-pass versus repaired success, wall time, tokens and cost. Use existing A21/E13/E9 and quality profiling infrastructure; no redundant telemetry service or production behavior changes. **Gate:** reproducible, source/commit-bound baseline with a ranked, evidence-backed failure/variability Pareto; if the source of instability is not established, abstain from code changes.
2. **E18.2 — Prevent factual drift at generation (P1; only if E18.1 identifies it).** Reuse canonical findings, evidence IDs, source spans, number/label/category/denominator/period/status relationships, source-display normalization and protected-field checks. Fix the earliest proven data-binding or prompt/normalization defect; keep canonical source truth authoritative and do not introduce a parallel facts store. Remove *forced* 6–8 candidate padding on sparse reports only if it demonstrably creates weak/duplicate/unsupported items, adapting the smallest necessary producer/consumer constraints while retaining broad-report coverage and accepted schemas. Prefer semantic reasoning where rule-based extraction or scoring would be disproportionately complex. **Gate:** focused numeric/table/forecast/scope adversarial tests and previously failing real-report fixtures show fewer genuine grounding failures without dropping important evidence, weakening controls, or increasing duplicate insights.
3. **E18.3 — Stabilize analytical selection (P1; only if E18.1 identifies it).** Reuse the existing editorial plan, stable evidence IDs, insight candidate pool and already-implemented theme-coverage/deduplication logic; resolve inconsistent downstream selection or rewording at its existing boundary. Avoid repeatedly choosing a different theme set or changing protected facts; apply deterministic eligibility/tie-breaking *only* for objectively equivalent candidates, leaving commercial relevance, synthesis and nuance to the LLM. Coordinate any shared cross-surface slate changes under P17/ARCH-B, not as an E18 duplicate. **Gate:** compared with E18.1, materially more stable supported selected findings and important theme/counter-signal coverage, with no loss in diversity, analyst significance, P6-quality criteria or first-pass factual fidelity.
4. **E18.4 — Stabilize semantic verdicts, scoped repair, and integrated regression (P1).** On frozen identical claim/evidence pairs, isolate genuinely inconsistent semantic judgments from legitimate unsupported-claim failures. Fix confirmed prompt/context/completeness/validator interpretation defects in the existing service; use deterministic checks for exact IDs/values and simple proven relationships, LLM for entailment. Never majority-vote away a genuine factual blocker, auto-approve uncertain claims, add a new validation framework, or relax the readiness gate. Reuse E13's bounded claim-scoped repair/promotion instead of regenerating whole families unnecessarily. Benchmark after changes against the pinned frozen-five repeated baseline (including at least three independent analysis runs per report when live evaluation is justified); inspect the actual final editorial outputs. **Gate:** documented decrease in genuine first-pass failures and/or false-positive repairs, no new false accepts, unchanged source/provenance/publication safeguards, and no unjustified total time/cost regression.

### Outcome-level acceptance

- Every implemented modification maps to a **measured** root cause and passes its own stage gate. If a suspected mechanism is already correct or tests show no benefit, record `no change needed` rather than adding code.
- For comparable frozen-five runs, retain per-report and aggregate first-pass validation/readiness, issue fingerprints, evidence/metric identity stability, theme coverage, repair frequency and promotions, human-reviewed substantive editorial quality, provider calls/tokens/cost and wall-clock latency. Same inputs/model/policies/producer SHA and explicit cache/replay semantics are mandatory for within-version variability measurements; version changes are labelled, not conflated with stochastic variation.
- Unsupported claims still fail closed; all pre-existing correctly publishable reports remain publishable. No regressions in numerical fidelity, attribution, methodological scope/forecast qualifiers, materially important findings, original-source support, P6 editorial standards, A21 reliability or approval/readback invariants. Publication is **disabled** during stability benchmarking.
- Reuse existing schema, retrieval, prompt, normalization, validator, regeneration, audit and benchmark infrastructure; no new services, default model change, global reasoning/sampling switch, or token optimisation without measured justification. Respect explicit provider budgets and existing protected caching/checkpoint identities.
- Close E18 only on exact-commit retained evidence from real reports proving improved stability/first-pass outcomes without quality regression. A21, E13, E16, E17, P6 and P17 statuses remain independently governed.

### Luna implementation prompts — E18 (one stage per Codex invocation)

**E18.1 — Diagnose and baseline**

```text
At current MarketLense HEAD, execute E18.1 only (docs/backlog/E-evidence.md).
Read AGENTS.md and inspect existing prompts, model policies, evidence/analysis/validation
code, retained five-report corpus and E9/E13/A21 telemetry. Pin a comparable,
budgeted multi-run generation and fixed-input semantic-validation baseline;
distinguish retrieval variation, generation variation, validator variation and
true unsupported claims. Do not mistake cache reuse for stability; do not change
production behavior. Retain root-cause evidence, hashes, costs and Pareto.
Use existing benchmark infrastructure; report limitations and next justified slice.
Verify, commit and push the measurement-only change.
```

**E18.2 — Factual stability**

```text
Implement E18.2 only if E18.1 proves relevant factual-generation instability.
Read AGENTS.md and the full E18 specification. Fix root causes at the earliest
existing evidence/normalization/prompt boundary; preserve exact numeric/source
tuples. Remove forced sparse-report candidate padding only if justified, with
downstream contract and broad-report coverage tests. Reuse E16's fact contracts
and all grounding/readiness safeguards. Inspect affected real-report output
and baseline deltas. If unproven, make no production change.
Record verification and commit/push the smallest proven change.
```

**E18.3 — Analytical selection**

```text
Implement E18.3 only if repeatability evidence supports a selection defect.
Read AGENTS.md and E18. Reuse the existing editorial plan, candidate set,
source identities and selectors; fix only observed drift or inconsistent
downstream re-selection. Avoid duplicate P17/ARCH-B selection architecture and
complex deterministic rankings where semantic judgment is better.
Compare same-evidence repeated runs for stability, coverage, factual fidelity,
editorial depth, cost and latency; inspect final prose. Revert ineffective fixes.
Commit and push the verified change and its retained evidence.
```

**E18.4 — Validation and full verification**

```text
Implement E18.4 after the preceding stage gates. Read AGENTS.md and E18.
Recheck fixed claim/evidence pairs for validator inconsistency; fix only proven
false-positive root causes using existing deterministic checks and semantic
validators. Keep fail-closed true factual violations, E13 scoped promotion and
all readiness safeguards. Run the frozen-five independent before/after evaluation
with existing tools, inspect outputs and record first-pass/repair/readiness,
quality, cost, speed, source identities and exact commits. No WordPress writes.
Do not claim stable or improved quality without comparative evidence.
Commit and push the verified changes; update E18 status only if all gates pass.
```
