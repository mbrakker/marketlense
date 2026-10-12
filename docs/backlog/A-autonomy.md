# Autonomy, acquisition, processing, and reliability

Canonical owner IDs: A8, A15, A17, A18, A19, A20, A21. This document contains **Active outcome specifications and their retained technical proposal slices**. Status belongs to [CONSOLIDATED_TODO.md](../../CONSOLIDATED_TODO.md), not to individual proposal sections. The complete source texts are preserved unchanged in the [historical backlog](archive/CONSOLIDATED_TODO-20261011-preconsolidation.md) and [historical proposal catalogue](archive/10improvements-20261011-preconsolidation.md).

Before implementing a slice, verify its historic diagnosis at current HEAD; use its **Luna implementation prompt** together with the full evidence and criteria immediately above it. Proposed thresholds are acceptance targets, not current results. Closed parent milestones are not reopened by a proposal's historical wording.

---
 
## A8. Compare retained model-call replay bundles

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `ARCH-I`.

- **Baseline:** Model-call audit/replay contracts and a no-provider replay builder exist (`src/services/_llm_service/audit.py`). Bundles retain prompt/model/schema/cache and usage/validation fields but do not guarantee selected-evidence, execution-policy or output/artifact identities. Canonical zero-provider comparison/disposition remains unimplemented; join compatible retained artifacts safely and classify missing provenance incomplete rather than equivalent.
- **Target behaviour:** A read-only comparison command accepts two compatible replay bundles and deterministically explains whether they are equivalent, compatible-but-changed, incomplete, malformed, or materially regressed. It never calls a provider and never emits retained prompt/source/model-output content.
- **What to implement, in order:**
  1. Define one typed comparison request/response contract around baseline bundle, candidate bundle, artifact family, and optional compatibility expectations.
  2. Inventory safe bundle/linked-artifact fields; add a versioned adapter/link for retained evidence, policy, output and artifact identities. Extract only provenance-proven fields and distinguish absent, unknown and malformed values before comparison.
  3. Implement deterministic field-level classification for equivalent, expected-compatible change, material regression, missing evidence, and malformed bundle cases; bound the output and preserve stable ordering.
  4. Add a CLI/operator surface that prints the summary and references retained artifacts without provider construction or external writes.
  5. Add fixtures from real retained bundles and document the command in the existing recovery/evidence workflow rather than creating another evidence system.
- **Acceptance criteria:**
  - Equivalent bundles produce an identical deterministic result across repeated runs and no false regression.
  - Changed prompt/policy/evidence/schema/output cases identify the exact changed safe fields and artifact family without printing prompt, source, or model-response text.
  - Missing and malformed bundles fail with typed bounded diagnostics rather than partial success. Evidence/policy/output identity cannot be inferred from prompt/model equality; legacy bundles remain explicitly incomplete.
  - Tests cover equivalent, changed, missing, malformed, and deterministic-order cases and prove zero provider calls/external writes by default.

### Luna implementation prompt — A8

```text
Work on A8 — Compare retained model-call replay bundles at the current MarketLense HEAD.
Owner specification: docs/backlog/A-autonomy.md; canonical status: CONSOLIDATED_TODO.md.
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
 
<a id="arch-i"></a>
#### ARCH-I — Test whether verified selection can replace a redundant insight-generation step

**Primary canonical owner:** [A8](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Investigation; promote only on evidence.

- **Priority / effort / dependencies:** P2 / S investigation, M only if proven / follow-ups A–C, `A8`, `A21`, `E13`, `P6`; optimization, not a prerequisite for the quality changes.
- **Evidence / diagnosis:** `generation.py` currently creates `insights_candidates`, can supplement with retained findings, and then generates `insights_final`. A better verified/ranked evidence slate may make the separate candidate-generation model call unnecessary for some sources; equivalence has not been demonstrated. Smaller prompts or fewer calls alone do not prove better or faster reports.
- **Luna implementation:** A/B compare the existing two-stage route with a route that constructs candidate facts from approved findings and uses the existing final-insight semantic synthesis. Keep the same source corpus, coverage constraints, factual validators, model policy and parallel opportunity. Gate removal of the intermediate family on blind analytical-depth/report-specificity and first-pass quality, not on JSON validity or cost alone. Reuse E9 prompt-family caching, A8 model-call attribution and current checkpoint/repair contracts; no new provider or scheduling service.
- **Success criteria:** Candidate-stage elimination occurs only where editorial quality, relevant theme/counter-signal coverage, grounding and reliability are at least equivalent; it produces a measured total wall-clock or cost gain without higher downstream repair burden. Otherwise preserve the current two-stage pipeline and document the negative result.
- **Validation:** Repeat the frozen five-report comparison, affected prior-failure cases and representative P6 editorial review with identical prompt/model policy; report exact calls, input/output tokens, cost, wall-clock critical path, repairs, abstentions and review findings. Publication stays disabled.

**Implementation order:** First verify the existing P0-severity grounding/verifier prerequisites and baseline source-fidelity behavior. Then implement A+B as the shared eligible candidate and editorial slate, C+D as upstream validation and dependent-repair consistency, and E–G as downstream consumers. Investigate H/I only after measuring the quality and reliability effect. Preserve P6/E15/A21 independent release evidence; do not auto-enable WordPress publication or change sandbox HTTP policy as part of this work.

**Luna implementation prompt — ARCH-I (copy/paste)**

```text
Implement ARCH-I — Test whether verified selection can replace a redundant insight-generation step.
Objective: Deliver the verified behavior specified immediately above under canonical A8.
Source: docs/backlog/A-autonomy.md, technical slice ARCH-I.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A8 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
 
## A15. Complete explicit model-policy coverage and policy-effectiveness evidence

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `ING-09`.

- **Baseline:** Production configuration/namespace preflight, registered prompt policies and retained policy matrices already exist. Compatibility-default behavior remains where registration is not required, and empty injected policy settings can skip matrix checks; reconcile production reachability instead of asserting an observed live bypass. Legacy config adaptation is distinct from provider-call fallback. `policy-effectiveness` already projects calls, validity/cache, latency coverage, tokens/cost and regeneration counts; attributable compatible-cohort quality conclusions remain open.
- **Target behaviour:** Every reachable production model call resolves through one explicit versioned policy with no compatibility fallback. Operators can compare compatible policy cohorts for calls, validity, reuse, latency, tokens, cost, and validated-output quality without changing routing automatically.
- **What to implement, in order:**
  1. Reconcile actual provider call sites against the finite registry/preflight matrix, including registration-disabled resolution, empty injected policy settings and test-only overrides. Separate supported legacy config adaptation from live compatibility-default fallback.
  2. Replace only proved reachable provider-call compatibility fallbacks with explicit registered resolution; preserve routing/model/timeouts/retrieval/schema/retry/cache behavior and explicit test-only seams.
  3. Preserve existing startup/prompt fail-closed checks, policy identity and cache invalidation; cover any uncovered direct-call boundary rather than rebuild preflight.
  4. Extend existing policy-effectiveness output with attributable compatible-cohort sample/coverage, unavailable cost/latency/validation and validated-output quality linkage. Define actual-provider versus reuse denominators; schema validity alone is not editorial quality.
  5. Run retained-corpus and bounded live evidence for representative high-cost namespaces; produce operator-reviewable no-change/recommendation conclusions only when compatibility/sample requirements are met.
- **Acceptance criteria:**
  - No reachable provider call uses compatibility-default fallback; unregistered production namespaces fail before provider construction/I/O. Supported legacy configuration adaptation remains distinct.
  - Policy hashes invalidate incompatible cache/replay reuse while preserving valid compatible reuse.
  - Retained and bounded live checks cover all production policy families and show complete bounded effectiveness fields or explicit `insufficient_evidence`/unknown states.
  - No command automatically changes model/provider/policy from effectiveness results; existing semantic/output contracts and retry ownership remain unchanged.

### Luna implementation prompt — A15

```text
Work on A15 — Complete explicit model-policy coverage and policy-effectiveness evidence at the current MarketLense HEAD.
Owner specification: docs/backlog/A-autonomy.md; canonical status: CONSOLIDATED_TODO.md.
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
 
<a id="ing-09"></a>
#### ING-09 — Make a configured global model cap apply across transport operations

**Primary canonical owner:** [A15](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1; M, two slices; land before ING-01 production concurrency increase. **Owner:** canonical LLM service; preserve family-specific operator configuration. Extension to existing A6/A15 controls, not replacing budgets/circuit breakers.

**Evidence and impact:** `src/contracts/ingest.py:460–465,501–506` defines process-wide family caps. `src/services/_llm_service/policy.py:79–81,101–125` keys rate limiters by `scope:operation_name`; `_get_rate_limiter_state()` therefore allocates independent semaphores for different operations in the same scope. `src/generators/structured_output_execution.py:197–212` can choose either vector-store Responses or chat-JSON for a family. `src/orchestrators/report_pipeline_orchestrator.py:971–988` correctly supplies caps to evidence/artifact clients; the gap is limiter identity, not absence of a limiter. **Confirmed:** operation-specific semaphores do not enforce one aggregate family cap. Observed excess concurrency/provider throttling has not been measured.

**Luna implementation:** (1) Separate limiter scope identity from circuit-breaker operation identity. Reuse one process-wide limiter per explicit family/resource scope across compatible model-call transports; leave unrelated external operations and family limits distinct. (2) Define behavior when concurrent clients attempt conflicting policy values: deterministic configuration failure or one immutable active policy, never replacing a semaphore while calls are in flight. Retain bounded wait/rate telemetry. Extend the typed policy only if needed and document process-wide rather than distributed semantics.

**Success criteria:** With family cap=2, simultaneous chat and Responses calls across three report clients never exceed two aggregate active calls; configured minimum interval applies between any family call starts. Evidence and artifact caps remain independently enforceable, circuit-breaker diagnostics keep correct operation identity, and no permit leaks after exceptions.

**Validation:** `python -m pytest -q tests/test_llm_service.py tests/test_llm_service_boundary.py tests/test_run_budget_side_effects.py`; use event-controlled fake provider functions through the actual public LLM clients for mixed operations, multiple clients, exception release and conflicting policies. Run the existing evidence/artifact parallelism benchmarks to confirm unchanged successful output and count/spacing evidence.

**Luna implementation prompt — ING-09 (copy/paste)**

```text
Implement ING-09 — Make a configured global model cap apply across transport operations.
Objective: Deliver the verified behavior specified immediately above under canonical A15.
Source: docs/backlog/A-autonomy.md, technical slice ING-09.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A15 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
 
## A17. Calibrate deterministic admission thresholds from retained preflight funnels

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `ING-03`, `ING-10`.

- **Baseline:** Admission decisions and hashed funnel records exist, but compatible threshold calibration/proposals remain absent. Required-work forecasting covers configured evidence families (default `doc_map`), not the complete source-to-review-ready pipeline. Rejected-source outcomes are censored unless independently labelled/replayed; admitted-only success cannot establish false-rejection rates or safe threshold changes.
- **Target behaviour:** A read-only calibration surface compares only compatible admission cohorts, quantifies cost/work avoided versus downstream completion/validation quality, and emits threshold proposals only when minimum sample/confidence/improvement gates are met. It never mutates admission policy.
- **What to implement, in order:**
  1. Define the compatibility key for admission cohorts from preflight/policy/configuration/runtime decision hashes and exclude incompatible versions deterministically.
  2. Build a read-only funnel report for each threshold family: native-text, page/size limits, evidence-potential, duplicate/quarantine and related deterministic rejection reasons.
  3. Join bounded downstream outcomes to admitted cases so the report can show completion/validation rates and provider/vector/model work actually incurred or avoided. Declare the forecast horizon/stages and forecast-versus-actual attribution. Rejected cases stay censored/unknown without independent labels or controlled shadow replay; missing prices/excluded stages cannot become a complete zero-cost estimate.
  4. Add counterfactual threshold proposal logic with configured minimum sample, confidence, and material-improvement gates; report an impact range and abstain on weak/noisy evidence.
  5. Add CLI/tests and one bounded retained/live replay proving the report is deterministic and side-effect free.
- **Acceptance criteria:**
  - Incompatible decision versions never enter the same cohort or proposal.
  - The report exposes denominator, admitted/rejected outcomes, downstream completion/validation, and avoided provider/vector work using bounded metadata only.
  - Threshold proposals include exact compatible decision hashes, sample/confidence evidence, and counterfactual impact; insufficient evidence produces an explicit no-change result.
  - Tests prove deterministic ordering and zero model/vector/external writes; no threshold/configuration is modified automatically.

### Luna implementation prompt — A17

```text
Work on A17 — Calibrate deterministic admission thresholds from retained preflight funnels at the current MarketLense HEAD.
Owner specification: docs/backlog/A-autonomy.md; canonical status: CONSOLIDATED_TODO.md.
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
 
<a id="ing-03"></a>
#### ING-03 — Admit structurally valid image-only reports to a bounded OCR route

**Primary canonical owner:** [A17](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1; M, three slices; ING-10 for trustworthy forecast. **Owner:** admission preflight; narrow A17/A21 implementation subtask, not a blanket lowering of text thresholds.

**Evidence and impact:** `src/orchestrators/admission_preflight_orchestrator.py:381–427` rejects low native-text sources as `insufficient_content` after initial and middle sampling. `src/generators/_report_source_generator/workflow.py:95–146` later supports OCR after `pdf_text_unextractable`. The admitted path can therefore exclude a valid wholly scanned report before its OCR fallback runs. **Confirmed ordering gap;** prevalence and lost usable reports are unknown. Blank/corrupt files must continue to be rejected.

**Luna implementation:** (1) Add an admission result for valid, attributed PDFs with native text unavailable but visible page/image evidence and configured OCR capability. Reuse canonical integrity/page/sample services; native failure is not structural corruption. (2) Forecast a capped OCR plan and defer on missing capability/budget; retain the decision and reason in the current admission contract with an explicit version adapter. (3) Route admitted OCR candidates through the existing source-preparation fallback; require downstream text/evidence validity before review readiness. Retain `insufficient_content` for demonstrably blank material.

**Success criteria:** All labelled usable scan fixtures reach OCR source validation; all labelled blank/corrupt fixtures make zero model calls and remain rejected. OCR-disabled, unavailable or over-budget cases produce typed hold/rejection with no hidden live call. No publication/readiness gate is weakened.

**Validation:** `python -m pytest -q tests/test_admission_preflight_orchestrator.py tests/test_report_pipeline_admission.py tests/test_report_source_generator.py`; build a local native PDF, equivalent image-only PDF, genuinely blank PDF and corrupt PDF. Add canonical ingest-to-analysis provider-free replay with fake OCR text for the image-only PDF and explicit downstream page provenance. Add the labelled scan stratum to A21 before claiming a production recall improvement.

**Luna implementation prompt — ING-03 (copy/paste)**

```text
Implement ING-03 — Admit structurally valid image-only reports to a bounded OCR route.
Objective: Deliver the verified behavior specified immediately above under canonical A17.
Source: docs/backlog/A-autonomy.md, technical slice ING-03.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A17 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ing-10"></a>
#### ING-10 — Forecast complete review-ready work and show forecast error

**Primary canonical owner:** [A17](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1; M, three slices; none; ING-03/ING-04 contribute OCR feature counts when available. **Owner/backlog:** active A17 admission calibration plus existing A15 policy-effectiveness telemetry; retain hard per-call budget enforcement from closed A6/A12.

**Evidence and impact:** `src/orchestrators/admission_preflight_orchestrator.py:879–930`, `_forecast_required_work()`, estimates one call per required evidence family with sampled-character input and output maxima, omitting downstream artifact/validation/category/crop/OCR work. `_forecast_budget_decision():976–991` labels this `forecast_method='explicit'`, confidence=1.0. The retained queue-configured five cohort used 192 model calls in total. **Confirmed limited estimate/misleading confidence:** it is not a complete report cost forecast. The 192 historical calls do not directly establish per-case forecast error without joining compatible decisions; perform that join first.

**Luna implementation:** (1) Define the forecast scope explicitly as source-to-awaiting-review, reusing current planned required families, compatible retained artifacts and policy pricing. Count only work that will run; estimate conditional OCR/crop/repair work separately with stated range/confidence. (2) Join existing admission decisions to finalized compatible usage by source/run and stage, retaining prediction versus actual calls/tokens/spend/runtime with sample counts and coverage. (3) Use conservative calibrated ranges only when enough compatible retained cases exist; otherwise label low-confidence bounded estimates. Emit operator proposals through A17, not automatic thresholds or fabricated certainty. Keep actual reservation/enforcement at every external boundary.

**Success criteria:** Every forecast names scope, covered stages, excluded/conditional work and confidence basis; no partial estimate claims 100% confidence. Deterministic fixtures include all configured families and subtract proven cache hits correctly. On at least 20 compatible retained reports, calibrated 90% cost bands cover at least 90% of actual outcomes; insufficient samples explicitly abstain from calibration. Budget-blocked work still makes zero provider calls.

**Validation:** `python -m pytest -q tests/test_admission_preflight_orchestrator.py tests/test_run_budget_ledger_service.py tests/test_run_budget_side_effects.py`; fixtures for native versus OCR, warm versus cold artifact reuse, unknown price, no compatible history and changed policy identities. Replay retained finalized usage without external calls, assert exact denominators and predicted/actual joins, then use the frozen A21 lane for an optional separately authorized bounded live calibration.

**Review verification limitation:** Repository source, contracts, backlog and retained benchmark artifacts were inspected. Attempted `python -m pytest -q tests/test_report_source_generator.py tests/test_admission_preflight_orchestrator.py tests/test_workflow_supervisor_parallelism.py tests/test_report_analysis_orchestrator_decomposition.py` stopped before collection because the available Python has no `pytest` installed. No tests or live workflows were claimed to pass; no source was changed. All future commands above are implementation validation requirements, not results from this review.

**Luna implementation prompt — ING-10 (copy/paste)**

```text
Implement ING-10 — Forecast complete review-ready work and show forecast error.
Objective: Deliver the verified behavior specified immediately above under canonical A17.
Source: docs/backlog/A-autonomy.md, technical slice ING-10.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A17 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
 
## A18. Harden discovery recall and authoritative acquisition handoff

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `DISC-01`, `DISC-02`, `DISC-03`, `DISC-04`, `DISC-05`, `DISC-06`, `DISC-07`, `DISC-08`, `DISC-09`, `DISC-10`, `SYS-07`.

- **Baseline:** HTTP/browser discovery, semantic screening, landing qualification, snapshots and route memory exist. Low HTTP confidence is still filtered before screening; URL presence drives novelty, cached candidates dominate recovery and acquisition queue payloads lose qualification context. Domain/social-host matching, title-only deduplication and shrinkage checks on mixed partial refreshes add deterministic risks. Ground-truth recall, reversible decisions, executable recovery and lossless handoff remain open; incident rates are unmeasured.
- **Target behaviour:** Discovery is high-recall, reversible, and the single authority for report qualification. Acquisition receives the complete typed qualification context and decides *how* to obtain the report rather than independently re-deciding *whether* it is a report. First-run completeness and deferred recovery are explicit and executable.
- **What to implement, in order:**
  1. Retain a hash-pinned gold corpus of roughly 15–20 representative publishers and known report URLs spanning static, pagination, JS-hydrated, mixed-content, gated, multilingual, direct-PDF, and external/microsite cases; score recall and precision independently of production discovery.
  2. Convert the HTTP `0.60` confidence cutoff to ranking/triage for plausible candidates; reserve deterministic hard rejection for indisputable junk. Treat English keywords, multilingual evidence, and same-domain status as features rather than eligibility requirements. Correct compound/public-suffix host identity and exact-or-subdomain social matching; union ordinary and embedded-card observations instead of suppressing existing extraction when header anchors exist.
  3. Separate observation from decision state with lifecycle (`observed`, `screened`, `qualified`, `acquisition_attempted`, `acquired`), decision/policy hashes, reason/confidence/time, and deterministic re-screen conditions. Missing model decisions stay undecided/deferred with orchestrator-owned bounded recovery. Do not reject distinct editions/routes by title alone; merge only qualified aliases with retained route evidence.
  4. Route typed deferred-recovery recipes through the existing durable queue/remediation boundary with bounded attempts/idempotent terminal states, or remove `scheduled` terminology where no executor exists.
  5. Introduce one lossless typed qualified acquisition context carrying canonical URL/title, candidate PDF URL, source-page URLs, discovery provenance/confidence, route recommendation, and qualification/policy identity through the durable queue.
  6. Bypass the ad-hoc report-likelihood readiness classifier for discovery-qualified candidates; keep it only for direct/ad-hoc URLs that did not pass discovery.
  7. Require bounded first-run completeness proof (terminal pagination, declared total/structured source agreement, sitemap/archive corroboration, or one verification browser pass) before the first snapshot becomes authoritative. Preserve prior qualified identities on unexplained partial refresh even when one new report exists; require completeness proof before interpreting disappearance as removal.
- **Acceptance criteria:**
  - Fixed gold corpus reaches at least **97% report recall** with no material precision regression from the retained baseline; recall and precision are reported separately.
  - Mixed accepted/rejected delta fixtures prove a false negative remains eligible for later re-screening, and policy-hash changes can reconsider prior decisions without a new URL observation.
  - Plausible multilingual/external-host/report-detail cases are not hard-dropped solely for missing English tokens/domain equality; obvious junk stays deterministic/no-model.
  - At least one retained deferred-recovery case executes through the canonical durable path to `recovered|failed|held` with bounded attempts and idempotent replay.
  - The production worker receives the same candidate PDF/source-page/provenance/route evidence available to direct/audit execution.
  - Discovery-qualified candidates reach route planning without a second report-likelihood rejection; direct/ad-hoc URLs retain the fail-closed readiness guard.
  - First-run snapshots cannot become long-lived baselines without an explicit completeness proof.

### Luna implementation prompt — A18

```text
Work on A18 — Harden discovery recall and authoritative acquisition handoff at the current MarketLense HEAD.
Owner specification: docs/backlog/A-autonomy.md; canonical status: CONSOLIDATED_TODO.md.
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
 
<a id="disc-01"></a>
#### DISC-01 — Build an independent, stage-attributed discovery recall benchmark

**Primary canonical owner:** [A18](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P0; M; none. Foundation for the other nine tickets. Align with A18.1 and A21; reuse compatible retained acquisition evidence rather than selecting easy new publishers.
- **Verified evidence:** `src/generators/publisher_inventory_coverage_generator.py::_evaluate_coverage:61–143` evaluates observed candidate counts and earlier snapshots; `_is_undercoverage_regression:175–191` only compares production output with previous output. Neither supplies a denominator of known eligible publisher reports. A18 explicitly identifies the missing ground-truth measurement at `CONSOLIDATED_TODO.md:176–179`.
- **Impact / bounded implementation:** Add a hash-pinned manifest and replay runner covering 15–20 publishers, at least 200 eligible reports and 100 hard negatives. Include static, paginated, JS-hydrated, mixed content, gated, multilingual, external-host, direct PDF, duplicate-edition and blocked-page strata. Establish eligibility labels from retained publisher inventory evidence with a second review; model guesses must not become labels. Replay canonical `discover_publisher_inventory` orchestration with only external boundaries replaced by recorded HTTP/browser/model responses, an isolated database and fake artifact storage. Attribute each miss to extraction, HTTP triage, deterministic screen, semantic screen, landing qualification or persistence; include candidate-level confusion matrices and cost/latency. Expose a proposed runner such as `scripts/quality/evaluate_discovery_recall.py`; document its exact CLI once implemented. A deterministic replay establishes control-flow behavior; it cannot prove fresh live-browser/provider recall.
- **Success criteria:** 100% cohort members have eligibility, canonical identity and source hash; repeat replay produces identical deterministic results; initial baseline captured before tuning. Release gate reaches ≥97% eligible-report recall, ≥95% precision, and no stratum below 90% recall. No outcome-based cohort replacement; report raw TP/FP/FN counts and confidence intervals alongside percentages.
- **Validation:** Add `tests/test_discovery_recall_benchmark.py` with a hidden known report absent from production candidates, a false-positive product PDF, duplicate aliases and an abstention; prove the denominator stays fixed. Run `python -m pytest -q tests/test_discovery_recall_benchmark.py tests/test_publisher_inventory_orchestrator.py tests/test_publisher_inventory_generator.py`. Run the proposed replay runner on identical retained inputs before/after every discovery change; no network, email or publication side effects.

**Luna implementation prompt — DISC-01 (copy/paste)**

```text
Implement DISC-01 — Build an independent, stage-attributed discovery recall benchmark.
Objective: Deliver the verified behavior specified immediately above under canonical A18.
Source: docs/backlog/A-autonomy.md, technical slice DISC-01.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A18 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="disc-02"></a>
#### DISC-02 — Replace irreversible heuristic rejection with bounded triage of plausible report candidates

**Primary canonical owner:** [A18](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P0; M; DISC-01, DISC-04 for persistence of deferred cases. Implements A18.2; combine changes here rather than separately adding many language keyword lists.
- **Verified evidence:** `src/services/_publisher_inventory_service/_fetch/discovery.py::discover_inventory_via_http:207–226` removes candidates below 0.60 before semantic screening. `_discovery_activity/candidates.py::_score_http_candidate_confidence:282–315` assigns score mainly from English report markers. `_looks_like_report_candidate:390–394` rejects other domains before later title/context checks. `src/generators/_publisher_inventory_candidate_screening/deterministic.py::_prefilter_screening_decision:148–245` hard-rejects unsupported PDFs, query-based listing hints, generic CTAs and unknown candidates. Positive screening already exists; do not merely add another model pass to every item.
- **Impact / bounded implementation:** Preserve plausible report cards as observations; retain the HTTP score as ordering, not an eligibility decision. Keep deterministic rejection for unambiguous navigation/legal/social/junk identities. Send weak but report-card-supported candidates through existing landing inspection and semantic screening within the current publisher deadline/candidate budgets, carrying extracted title/context and provenance. Missing English tokens and domain equality alone must not reject candidates. Unknown candidates beyond the budget become typed deferred decisions with reasons; never silently disappear. Move only relevant operational budget knobs into canonical configuration; keep eligibility invariants code-owned. Include German/Spanish/Italian/French/Polish and external microsite evidence, avoiding a blanket acceptance of all outbound links.
- **Success criteria:** 100% labeled plausible reports that currently fail only a score/language/domain heuristic reach qualification or explicit deferred state; no obvious junk is sent to the model in the deterministic negative fixtures. DISC-01 reaches ≥97% recall and ≥95% precision. Proposed cost guard: no more than 20% increase in semantic-screen tokens per eligible report versus frozen baseline; report any recall/cost tradeoff rather than hide it by dropping candidates.
- **Validation:** Extend `tests/test_publisher_inventory_service/test_http_and_html_parsing.py` and `tests/test_publisher_inventory_candidate_screening_generator.py` with a 0.55 report, non-English detail slug, external report card, query-bearing document link, generic download CTA with a real report title, legal PDF and ordinary external product page. Run `python -m pytest -q tests/test_publisher_inventory_service/test_http_and_html_parsing.py tests/test_publisher_inventory_candidate_screening_generator.py tests/test_publisher_inventory_candidate_quality_generator.py tests/test_publisher_inventory_orchestrator.py`, then the fixed replay.

**Luna implementation prompt — DISC-02 (copy/paste)**

```text
Implement DISC-02 — Replace irreversible heuristic rejection with bounded triage of plausible report candidates.
Objective: Deliver the verified behavior specified immediately above under canonical A18.
Source: docs/backlog/A-autonomy.md, technical slice DISC-02.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A18 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="disc-03"></a>
#### DISC-03 — Correct host identity so unrelated domains cannot be treated as publisher siblings or social sites

**Primary canonical owner:** [A18](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1; S–M; DISC-01. Independent of DISC-02; it corrects identity features even when domain identity no longer gates eligibility.
- **Verified evidence:** `src/services/_publisher_inventory_service/_discovery_activity/urls.py::_apex_domain:57–61` takes the last two labels, so `publisher.co.uk` and `other.co.uk` both become `co.uk`; `_is_same_inventory_domain:35–40` treats them as equal. `_discovery_activity/candidates.py::_looks_like_report_candidate:360–361` uses substring matching against social host markers; `constants.py:69–76` includes `x.com`, so a synthetic innocent host such as `analyticsbox.com` matches that suffix substring. These are deterministic correctness risks, not claims about observed production incident frequency.
- **Impact / bounded implementation:** Replace social-host substring matching with normalized exact-or-subdomain equality (`host == allowed` or `host.endswith('.' + allowed)`). Replace two-label apex comparison with an existing compatible PSL-aware utility if available; otherwise add one canonical deterministic host-identity helper with a pinned offline public-suffix source and no runtime network fetch, subject to dependency policy. Preserve distinct tenant identities on shared hosting/private suffixes; IDNA-normalize and remove trailing dots. Reuse the helper in origin-host recovery to avoid inconsistent attribution; do not introduce a general domain registry service.
- **Success criteria:** Zero wrong equality/exclusion decisions on at least 30 labeled host pairs, including UK/JP compound suffixes, private hosting tenants, legitimate publisher subdomains, trailing dots and IDN. Same-publisher subdomain behavior stays unchanged; no new runtime network calls or per-candidate provider cost.
- **Validation:** Add observable extraction/recovery cases to existing service tests: unrelated `*.co.uk`, actual `sub.linkedin.com`, lookalike `linkedin.com.example.org`, and `analyticsbox.com`. Run `python -m pytest -q tests/test_publisher_inventory_service/test_http_and_html_parsing.py tests/test_publisher_inventory_service/test_preflight_and_routes.py tests/test_publisher_inventory_service/test_browser_traversal.py`; replay the external-host stratum from DISC-01. If adding a package, also follow repository `dependency-upgrade` policy and update the lock/constraints owner.

**Luna implementation prompt — DISC-03 (copy/paste)**

```text
Implement DISC-03 — Correct host identity so unrelated domains cannot be treated as publisher siblings or social sites.
Objective: Deliver the verified behavior specified immediately above under canonical A18.
Source: docs/backlog/A-autonomy.md, technical slice DISC-03.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A18 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="disc-04"></a>
#### DISC-04 — Separate seen URLs from qualified decisions and enable safe re-screening

**Primary canonical owner:** [A18](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P0; M–L; DISC-01. Implements A18.3. Persisted-contract change requires an explicit version transition/migration; split implementation into migration, selection and replay commits.
- **Verified evidence:** `src/generators/publisher_inventory_generator.py::build_publisher_inventory_snapshot:92–106` defines new candidates solely by URL absence from the prior raw snapshot. `src/orchestrators/publisher_inventory_orchestrator.py:309–325` screens only `build_response.new_items`. `src/generators/publisher_inventory_coverage_generator.py::_evaluate_coverage:119–143` preserves the snapshot when every new item is rejected, but permits it when a mixed delta has at least one qualified report; the rejected members can then become permanently seen.
- **Impact / bounded implementation:** Keep raw observations independent of per-candidate disposition in the existing report-store persistence boundary. Version a typed decision record with observation/content hash, screening/qualification policy and prompt hashes, outcome (`observed`, `screened`, `qualified`, plus acquisition milestones where already authoritative), reason, timestamps and retry eligibility. Select candidates by absent decision, changed evidence/policy, retryable/deferred decision due time or explicit re-screen request, not solely URL novelty. Reuse unchanged final decisions and acquired identities. Backfill legacy raw snapshots as observed/unqualified unless retained qualification evidence proves otherwise; never label legacy URLs acquired. Commit candidate decisions atomically with the relevant workflow state and preserve the previous authoritative snapshot on failure.
- **Success criteria:** In mixed accepted/rejected delta replay, 100% rejected plausible reports remain reconsiderable; a policy change reconsiders all eligible prior decisions without needing a new URL. Identical input/policy replay causes zero repeat model calls for final compatible decisions and zero duplicate source/acquisition queue records. Migration and restart preserve all previous qualified/acquired identities with zero count loss.
- **Validation:** Extend `tests/test_publisher_inventory_orchestrator.py` and integration report-store tests with two-report mixed delta, second-run policy change, unchanged successful replay, transient failure due date, crash between decision persistence and snapshot publication, and legacy migration replay. Run `python -m pytest -q tests/test_publisher_inventory_orchestrator.py tests/test_publisher_inventory_generator.py tests/test_report_store_service.py`; run discovery→durable-acquisition handoff on isolated state with downstream acquisition faked and publication disabled.

**Luna implementation prompt — DISC-04 (copy/paste)**

```text
Implement DISC-04 — Separate seen URLs from qualified decisions and enable safe re-screening.
Objective: Deliver the verified behavior specified immediately above under canonical A18.
Source: docs/backlog/A-autonomy.md, technical slice DISC-04.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A18 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="disc-05"></a>
#### DISC-05 — Require first-run completeness evidence and protect against partial-refresh replacement

**Primary canonical owner:** [A18](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P0; M; DISC-01. Implements A18.7 and also closes the partial-refresh gap beyond A18's first-run requirement.
- **Verified evidence:** `src/services/_publisher_inventory_service/_fetch/discovery.py::discover_inventory_via_http:80–83,189–204,235–238` stops on page budget, loops/duplicate anchors or absent next link; it can still return candidates as success at `290–323`. Response truncation is logged at `155` but is not a completeness decision here. `src/generators/publisher_inventory_coverage_generator.py::_is_undercoverage_regression:178–187` skips first runs, single-page comparisons and any shrinkage with raw/qualified additions; `_evaluate_coverage:136–142` defaults to an allowed snapshot.
- **Impact / bounded implementation:** Add typed traversal termination/completeness evidence to service response and version persisted snapshot metadata. Distinguish terminal pagination, declared-total agreement, truncation, cycle, budget exhaustion and unknown completeness. For first runs lacking proof, perform at most one existing bounded browser verification or mark the snapshot provisional; retain provisional discoveries but do not use them as a long-lived authoritative baseline. Refresh runs with unexplained report-set shrinkage must preserve earlier qualified identities even if one new report was found; do not interpret budget/timeout disappearance as publisher deletion. Confirm removal via positive publisher evidence or repeated complete snapshots according to a documented policy. Reuse existing traversal evidence rather than inventing another crawler.
- **Success criteria:** Zero truncated/budget-exhausted/unknown first-run fixtures become authoritative. Zero earlier qualified reports are removed by a partial refresh containing a new report. Complete terminal fixtures remain accepted with zero unnecessary browser calls. Fixed corpus first-run recall ≥97%; no cap bypass or unbounded verification retries.
- **Validation:** Add first-run hidden pagination, byte-truncated HTML, repeated page fingerprint, page-cap exhausted, one-page JS subset, and refresh 20→10 reports plus one new report fixtures. Run `python -m pytest -q tests/test_publisher_inventory_service/test_http_and_html_parsing.py tests/test_publisher_inventory_service/test_browser_traversal.py tests/test_publisher_inventory_orchestrator.py`; replay the complete and incomplete traversal strata through canonical orchestration and assert persisted authoritative/provisional state.

**Luna implementation prompt — DISC-05 (copy/paste)**

```text
Implement DISC-05 — Require first-run completeness evidence and protect against partial-refresh replacement.
Objective: Deliver the verified behavior specified immediately above under canonical A18.
Source: docs/backlog/A-autonomy.md, technical slice DISC-05.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A18 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="disc-06"></a>
#### DISC-06 — Turn deferred recovery records into executable, idempotent recovery work

**Primary canonical owner:** [A18](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P0; M; DISC-04; use existing durable queue/remediation machinery. Implements A18.4.
- **Verified evidence:** `src/orchestrators/_publisher_inventory_orchestrator/candidate_flow.py::_record_deferred_candidate_recovery_cache:179–207` reuses an existing `scheduled` record and sets new records to `scheduled` when enabled; `208–227` only persists a cache record. There is no enqueue/execution in this function. A18 baseline explicitly confirms that scheduling is not yet an authoritative executed second pass (`CONSOLIDATED_TODO.md:176`). `_publisher_inventory_candidate_quality/workflow.py:154–168` already creates typed recipes, so recipe construction does not need replacement.
- **Impact / bounded implementation:** Bind supported recipes to an existing durable queue handler that invokes canonical browser/landing inspection boundaries, then reuses canonical qualification. Use stable candidate + observation/policy/action idempotency identity, persisted due/lease/attempt count and explicit `recovered`, `failed` or `held` terminal states. `scheduled` is legal only after a durable queue record exists. Recovered data feeds DISC-04 re-screening and source recording. Initially support the existing concrete recipe actions only; cap each recipe at two attempts and current publisher/browser budget. If an action has no executor, persist `held` with a reason rather than claiming scheduling. Do not build a new scheduler or spawn a second crawler.
- **Success criteria:** 100% `scheduled` records correspond to runnable durable work. All retained recovery fixtures reach a terminal outcome within ≤2 attempts; duplicated delivery/restart causes zero repeated source writes. Proposed recovery target: ≥80% of independently labeled recoverable blocked/JS cases become qualified; impossible/unavailable cases terminate visibly without promoting an unrelated page.
- **Validation:** Add isolated queue integration cases for scheduled→lease→recover, restart after canonical inspection, duplicate delivery, permanent blocker, unsupported action and budget exhaustion. Extend `tests/test_publisher_inventory_orchestrator.py` and existing queue/remediation handler tests identified during implementation. Run the canonical queue worker against recorded service responses and a temporary database; downstream email/acquisition/publication remain disabled. Report actual attempts, latency, terminal state and source-count equality on replay.

**Luna implementation prompt — DISC-06 (copy/paste)**

```text
Implement DISC-06 — Turn deferred recovery records into executable, idempotent recovery work.
Objective: Deliver the verified behavior specified immediately above under canonical A18.
Source: docs/backlog/A-autonomy.md, technical slice DISC-06.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A18 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="disc-07"></a>
#### DISC-07 — Scope landing-page evidence to the report instead of shared navigation/footer content

**Primary canonical owner:** [A18](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1; M; DISC-01. Not a duplicate of existing landing quality checks; this changes the evidence feeding them.
- **Verified evidence:** `src/services/_publisher_inventory_service/_fetch/parsing.py::_LandingPageInspectionHtmlParser:273–371` accumulates all visible text, all forms and all link/button labels. `_fetch/inspection.py::_inspect_landing_page_item:322–355,371–380` derives report/download/document signals from page-wide combined text. `src/generators/_publisher_inventory_candidate_quality/evaluation.py::_qualify_observation:64–70,419–449` uses those booleans to accept gated/downloadable report pages. A report advertisement or newsletter form in chrome can contaminate the target-page signals; actual production frequency is not established by this source review.
- **Impact / bounded implementation:** Retain minimal typed evidence locations for candidate-associated main/article/report container, actual downloadable link target and actual report form. Separate main evidence from nav/footer/related content rather than deleting potentially useful raw observations. Anchor download/form signals to the resolved report title/heading/container or explicit structured metadata; generic newsletter/search forms are not report gates. Preserve current deterministic qualification for conclusive cases; send genuine ambiguous evidence to the bounded triage path. Detect truncation and classify insufficient evidence as deferred rather than proof of absence. Keep full page content outside standard logs.
- **Success criteria:** Zero acceptance on at least 30 hard-negative pages where only footer/sidebar supplies report/form/download terms. ≥95% acceptance of at least 30 genuine gated/downloadable reports with varied DOM structures; DISC-01 precision ≥95% with recall decrease ≤1 percentage point compared with the prior change. No added model calls for unambiguous fixture cases.
- **Validation:** Extend `tests/test_publisher_inventory_service/test_runtime_and_inspection.py` and `tests/test_publisher_inventory_candidate_quality_generator.py` with blog + report sidebar, product + newsletter form, genuine report form, report CTA behind a sibling container, malformed HTML and truncated evidence. Run `python -m pytest -q tests/test_publisher_inventory_service/test_runtime_and_inspection.py tests/test_publisher_inventory_candidate_quality_generator.py tests/test_publisher_inventory_orchestrator.py`; replay through source persistence and assert rejected pages never produce qualified records.

**Luna implementation prompt — DISC-07 (copy/paste)**

```text
Implement DISC-07 — Scope landing-page evidence to the report instead of shared navigation/footer content.
Objective: Deliver the verified behavior specified immediately above under canonical A18.
Source: docs/backlog/A-autonomy.md, technical slice DISC-07.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A18 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="disc-08"></a>
#### DISC-08 — Deduplicate by report identity after qualification, preserving alternative routes

**Primary canonical owner:** [A18](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1; M; DISC-01, DISC-04. Coordinate with the lossless acquisition context ticket in the interconnections bucket.
- **Verified evidence:** `src/generators/_publisher_inventory_candidate_screening/response_policy.py::_candidate_duplicate_key:283–289` collapses non-generic title fingerprints. `_deduplicate_screening_response:159–190` picks a winner and rejects the alternatives before landing quality; `_candidate_selection_key:292–303` prefers no query, early page and short path/URL, not document availability or verified identity. Different regional/year editions with equal displayed titles can merge; a short dead URL can win over a working report route.
- **Impact / bounded implementation:** Before qualification only merge proven URL aliases while unioning observations/provenance. Treat title equality as a candidate group, not evidence of duplicate reports. Qualify group members within existing limits, then merge only if retained canonical/redirect/document identity or edition metadata proves equivalence. Keep distinct period/geography/language editions. Preserve compatible PDF/detail/source-page aliases as alternative routes on the surviving report rather than recording them rejected. Prefer verified direct document/detail evidence, while leaving acquisition route choice to acquisition. Do not use an LLM for exact URL alias collapse and do not invent byte identity before a PDF exists.
- **Success criteria:** Zero distinct-edition merges on at least 40 labeled pairs; zero report losses when the lexically preferred URL fails and another works. Proven aliases create exactly one qualified source/queue entity with 100% route/provenance retention. Duplicate qualification work for exact URL aliases is zero.
- **Validation:** Extend `tests/test_publisher_inventory_candidate_screening_generator.py` and `tests/test_publisher_inventory_orchestrator.py` with identical titles but different region/year, dead short URL + live gated URL, detail + PDF alias, tracking URL alias and locale editions. Run `python -m pytest -q tests/test_publisher_inventory_candidate_screening_generator.py tests/test_publisher_inventory_candidate_quality_generator.py tests/test_publisher_inventory_orchestrator.py`; isolated discovery→queue roundtrip must retain all compatible alternative routes and one canonical identity.

**Luna implementation prompt — DISC-08 (copy/paste)**

```text
Implement DISC-08 — Deduplicate by report identity after qualification, preserving alternative routes.
Objective: Deliver the verified behavior specified immediately above under canonical A18.
Source: docs/backlog/A-autonomy.md, technical slice DISC-08.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A18 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="disc-09"></a>
#### DISC-09 — Union ordinary anchors with embedded report cards and improve card-associated titles

**Primary canonical owner:** [A18](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1; S–M; DISC-01, DISC-02. Not a rewrite of existing component extraction or WordPress AJAX supplementation.
- **Verified evidence:** `src/services/_publisher_inventory_service/_fetch/discovery.py::discover_inventory_via_http:170–175` only invokes existing component-link extraction when no ordinary anchors exist; a normal header/navigation can therefore suppress that route on pages whose report cards live in embedded components. `_extract_component_link_anchors` already exists in `_discovery_activity/candidates.py:145–184`. `_fetch/parsing.py::_InventoryHtmlParser.handle_endtag:246–265` finalizes `context_text` when the anchor closes, before a later sibling report heading can be seen; `_extract_candidates_from_html:113–141` retains the first occurrence of a URL.
- **Impact / bounded implementation:** Always union the current ordinary and embedded-component anchor outputs, deduplicate normalized URL observations and choose the strongest non-generic card title while retaining source provenance. Complete container-associated title collection before evaluating generic CTAs, so a later sibling heading can qualify the report without URL keyword dependence. Start with the already-supported component patterns and recorded publishers. Add standards-based JSON-LD `Report`/`CreativeWork`/`ItemList` only if DISC-01 includes missed eligible reports that the existing extractors cannot cover; this optional extension belongs to the same bounded parser, not a provider fallback. Reject malformed/unbounded embedded payloads with explicit diagnostics.
- **Success criteria:** 100% known reports on at least 10 mixed ordinary-anchor/component fixtures are observed, with zero duplicate canonical URLs. 100% generic-CTA-before-heading fixtures retain the correct heading. No extra HTTP/model calls; local parsing median overhead <10% relative to identical HTML baseline (report raw times, no noisy single-run proof).
- **Validation:** Extend `tests/test_publisher_inventory_service/test_http_and_html_parsing.py` with navigation anchors + embedded cards, same URL in both paths with different titles, CTA preceding sibling title, malformed escaped component payload, and irrelevant embedded links. Run `python -m pytest -q tests/test_publisher_inventory_service/test_http_and_html_parsing.py tests/test_publisher_inventory_generator.py tests/test_publisher_inventory_orchestrator.py`; fixed replay verifies downstream qualification and duplicate source counts, not merely parser output.

**Luna implementation prompt — DISC-09 (copy/paste)**

```text
Implement DISC-09 — Union ordinary anchors with embedded report cards and improve card-associated titles.
Objective: Deliver the verified behavior specified immediately above under canonical A18.
Source: docs/backlog/A-autonomy.md, technical slice DISC-09.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A18 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="disc-10"></a>
#### DISC-10 — Treat missing semantic decisions as incomplete work, with orchestrator-owned bounded recovery

**Primary canonical owner:** [A18](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1; M; DISC-01, DISC-04; DISC-06 if retry is deferred. Read repository `llm-change-eval` skill for the eventual model/schema change.
- **Verified evidence:** `src/generators/_publisher_inventory_candidate_screening/llm_batches.py::_screen_candidate_batch:152–204` recursively calls itself for missing decisions; `205–210` replaces remaining omissions with `_fallback_screening_decision`. `deterministic.py::_fallback_screening_decision:122–126` returns `accepted=False` for unknown cases. The one-item case bypasses the repair condition at `llm_batches.py:157`. This conflates model-output incompleteness with semantic rejection and owns repeat provider calls inside a generator.
- **Impact / bounded implementation:** Validate complete one-to-one candidate ID coverage independently of semantic content. Return typed per-candidate `undecided`/incomplete work or a partial typed response; never turn an omission into final semantic rejection. Orchestrator performs at most one smaller/single-item missing-only call within shared time/token budget, including a missing decision for an original one-item batch; if still incomplete, persist a deferred decision for canonical recovery. Keep valid decisions and deterministic provable junk outcomes; retries must not resubmit valid members. Preserve strict handling of duplicate/unknown IDs, boolean schema, reasons and ungrounded output. Record omission rate and calls/tokens without raw prompts. Update versioned contracts and canonical prompts only if needed for the new decision semantics.
- **Success criteria:** Zero final rejection caused solely by a missing provider decision. At most one immediate repair call per incomplete batch; zero successful members resent; budget exhaustion yields visible deferred state. Complete-response fixtures keep identical decisions/provider call count. Proposed live-evaluation threshold, only if later separately authorized: ≥99% complete candidate decisions after the bounded repair, with all residual omissions retained for re-screening.
- **Validation:** Extend `tests/test_publisher_inventory_candidate_screening_generator.py` and `tests/test_publisher_inventory_orchestrator.py` with one missing item, whole batch absent, omitted original singleton, duplicate/unknown candidate ID, bad boolean, repair still incomplete and timeout/cost budget exhausted. Use boundary provider fakes rather than monkeypatching private helpers. Run `python -m pytest -q tests/test_publisher_inventory_candidate_screening_generator.py tests/test_publisher_inventory_orchestrator.py`; replay missing-decision cohort through persistence and subsequent recovery, assert exact external-call count and no lost candidates.

Discovery review limitations: source inspection only; no live publishers, models or production database were accessed, and no runtime improvement is claimed. Existing retained evidence was inventoried but no production-frequency or baseline rate was derived from it. Validation commands above are implementation acceptance work, not tests run during this documentation-only review.

**Luna implementation prompt — DISC-10 (copy/paste)**

```text
Implement DISC-10 — Treat missing semantic decisions as incomplete work, with orchestrator-owned bounded recovery.
Objective: Deliver the verified behavior specified immediately above under canonical A18.
Source: docs/backlog/A-autonomy.md, technical slice DISC-10.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A18 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="sys-07"></a>
#### SYS-07 — Carry authoritative discovery qualification into acquisition

**Primary canonical owner:** [A18](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority:** P1. **Effort:** M. **Depends on:** SYS-01, discovery classification tasks. **Backlog:** A18, explicitly open.

**Evidence / diagnosis (confirmed):** `_publisher_discovery_handler` builds acquisition payloads from accepted new report URLs (`acquisition.py:177-210`) but retains title/URL rather than the qualification verdict, evidence locator and classifier/policy identity. `_report_download_orchestrator/candidate_readiness.py` performs another candidate-readiness assessment from URL/title/source signals. The backlog A18 specifically requires discovery-qualified candidates to reach route planning without a second report-likelihood rejection, while ad-hoc URLs retain the guard.

**Implementation for Luna:** Add a typed immutable discovery qualification reference/hash and carry candidate identity, verdict, evidence locator and policy version into acquisition. Resolve and validate it before route planning. Reuse only the report-likelihood verdict; structural PDF verification, rights/credentials, source identity, form restrictions and budgets must still run. Direct/manual URLs continue through ordinary readiness assessment; incompatible qualification triggers reassessment or explicit hold.

**Success criteria:** A valid accepted discovery candidate is not rejected again solely by weaker title/URL heuristics. Direct/ad-hoc false positives remain rejected. Missing, stale, forged or unrelated qualification cannot bypass acquisition safeguards.

**Validation:** Extend `tests/test_workflow_queue_registry.py`, `tests/test_report_download_orchestrator.py` and `tests/test_publisher_inventory_orchestrator.py` with accepted opaque URL, ad-hoc same URL, stale verdict and wrong candidate identity. Run those suites plus `tests/test_acquisition_ingest_handoff_orchestrator.py`; measure false-negative changes on the DISC labeled cohort.

**Luna implementation prompt — SYS-07 (copy/paste)**

```text
Implement SYS-07 — Carry authoritative discovery qualification into acquisition.
Objective: Deliver the verified behavior specified immediately above under canonical A18.
Source: docs/backlog/A-autonomy.md, technical slice SYS-07.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A18 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
 
## A19. Harden acquisition routes, terminal semantics, and artifact verification

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `ACQ-01`, `ACQ-02`, `ACQ-03`, `ACQ-04`, `ACQ-05`, `ACQ-06`, `ACQ-07`, `ACQ-08`, `ACQ-09`, `ACQ-10`.

- **Baseline:** Route execution/terminal budgets, required Drive-archive preflight, retained-file/MD5 handoff and route economics exist. Cross-route structural/completion semantics remain incomplete: polling can follow `email_required` without a verified submission watermark, mailbox materialization precedes relevance/structural checks, and route/source learning can precede required archive completion. Extend these boundaries rather than rebuild browser, archive, polling or budgets.
- **Target behaviour:** Every acquisition mechanism converges on one ingest-compatible structurally verified artifact definition with truthful terminal states, bounded resource use, and mechanism-level economics. Cheap deterministic paths remain first; Browser Use stays a last resort.
- **Current scoped evidence (through 2026-10-08):** Mailbox ZIP attachments have code-owned resource ceilings and typed per-attachment failures with sibling continuation (`bafd72ed`). IMAP selection is read-only with UID/UIDVALIDITY identity handling (`207d6213`). Queue-backed mailbox polling now requires schema 2.0 with the persisted verified request ID and exact submission watermark; only `email_requested` emits a mailbox child, legacy payloads fail closed, same-workflow retries reuse the request, and a new workflow ID creates a separate generation. HTML link candidates preserve exact signed URL bytes and carry bounded link-local context; signed query values are redacted from structured logs. Focused queue/request and link-selection tests cover these boundaries; broader route, structural artifact verification, accounting, and live-mailbox delivery proof remain active.
- **What to implement, in order:**
  1. Correct terminal/mail semantics: only verified `email_requested` may enqueue mailbox work; `email_required` is identity/configuration hold. Carry verified form-submission timing/request identity into mailbox payloads. Split broad access blockers into rate-limit/transient, JS/WAF challenge, CAPTCHA, authentication, forbidden/access-blocked, and terminal not-found classes. Carry a verified submission event ID/timestamp and effective configuration across acquisition/mailbox queue redelivery; URL identity alone cannot identify a new request.
  2. Reuse the canonical `pdf-integrity-v1` structural checks before success, route-memory promotion, cache population, durable archive completion, or ingest handoff for HTTP, browser, mailbox/ZIP, cache, private-API and specialist PDF outputs. Distinguish `artifact_verified_locally`, `artifact_archived`, and `acquisition_complete`.
  3. Harden HTTP/cache without making them browser-first: permit one evidence-triggered browser recovery when an apparent direct PDF proves to be HTML/WAF/viewer content; rank embedded/opaque/extensionless PDF candidates from explicit candidate evidence, DOM/CTA relation, MIME/response evidence and source relation before lexical hints; revalidate mutable cache entries with available ETag/Last-Modified/final URL/content-length/version evidence.
  4. Gate browser side effects: automatic pre-LLM form submission runs only for `browser_email_form` or strong proven report-delivery form evidence; generic PDF-click pages cannot submit newsletter/contact/demo forms. Keep deterministic playbooks/private APIs ahead of Browser Use where eligible; use a generic acquisition prompt when route family is genuinely uncertain.
  5. Make listing-hub recovery exceptional/self-healing by persisting the resolved canonical detail/download target back to source/discovery state for the next run.
  6. Unify onsite/specialist completeness: one evaluator for direct HTTP/browser capture; truncated content is never complete; HTML/Markdown remain support artifacts while ingest is PDF-only; Adobe text-only output is labelled explicitly; Issuu retains all-declared-pages verification with bounded concurrency/disk streaming.
  7. Make mailbox acquisition metadata-first and bounded: rank sender/subject/timestamp/body snippet/attachment metadata/anchor text before materialization; share affinity scoring for links and attachments; bound ZIP member count/single+total decompressed bytes/compression ratio/PDF count; suppress by message+exact normalized URL+failure class; continue through bounded lower-ranked candidates after candidate-specific failures; improve IMAP filtering/windowing. Preserve signed delivery URLs, use stable provider message IDs and nonmutating IMAP reads, and schedule due polls durably instead of occupying workers during long waits; retain finite expiry/read budgets.
  8. Persist mechanism-level accounting (`planned_route_family`, `resolution_method`, route kind/outcome/status, browser/Agent/mailbox usage, latency, resource counts, cost) and feed it into A14 rather than creating a parallel policy system.
  9. Reserve/finalize budgets for actual HTTP/browser/model/form/mailbox/PDF/Drive operations instead of a generic PDF-processing reservation for every attempt.
- **Acceptance criteria:**
  - `email_required` never polls; `email_requested` always carries verified submission timing and an older matching email cannot satisfy a newer request.
  - Static HTTP timeout cannot alone produce email-required/requested terminal evidence.
  - One shared structural verifier rejects malformed/truncated pseudo-PDFs consistently on every acquisition path before success is learned.
  - Onsite terminal success produces a structurally verified PDF while ingest remains PDF-only and records publisher-supplied versus rendered capture.
  - Apparent `.pdf` HTML/WAF/viewer wrappers get at most one bounded browser recovery; genuine PDFs complete without browser launch.
  - Opaque/extensionless valid PDF fixtures can succeed from DOM/MIME/candidate evidence without title tokens; probing remains bounded.
  - Pre-LLM automation cannot submit unrelated lead/newsletter/contact forms on a PDF-click route.
  - Listing-hub success repairs the future acquisition target so the next run does not repeat listing discovery.
  - Truncated onsite content is never complete; Adobe/Issuu semantics are explicit and memory/concurrency bounded.
  - Mailbox fixtures prove irrelevant messages do not materialize attachments, ZIP bombs are bounded, one failed same-host link does not suppress a valid sibling, and a retryable top candidate does not block a bounded valid lower-ranked candidate.
  - Route economics distinguish the actual resolution mechanisms and contain the resource/cost/latency fields required by A14.
  - Mutable cache freshness changes invalidate reuse; immutable/versioned sources retain cheap reuse.
  - Required archive failure leaves a recoverable pre-completion state and converges idempotently after storage recovers.
  - Route-specific budget tests prove operations are blocked only by the limits for side effects actually attempted.

### Luna implementation prompt — A19

```text
Work on A19 — Harden acquisition routes, terminal semantics, and artifact verification at the current MarketLense HEAD.
Owner specification: docs/backlog/A-autonomy.md; canonical status: CONSOLIDATED_TODO.md.
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
 
<a id="acq-01"></a>
#### ACQ-01 — Preserve one verified submission identity across acquisition and mailbox queues

**Primary canonical owner:** [A19](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P0 / M / none. **Backlog:** A19.1; A20 mailbox configuration preflight.
- **Evidence and impact:** `_acquisition_handler` in `src/orchestrators/_workflow_queue_handlers/acquisition.py:288–316` queues both `email_requested` and `email_required`, sets `request_watermark=""`, and uses source identity/digest as `delivery_request_id`. `_mailbox_delivery_handler:370–373` therefore loses the watermark and often resolves `workflow_request_id=0`, disabling request-scoped rejection persistence. `record_deferred_mail_delivery_request` in `src/orchestrators/_report_download_orchestrator/workflow.py:1060–1122` correctly requires `email_requested` and creates a numeric durable request, but uses run start as submission time and does not expose this record to the queue. This is an observed contract mismatch; actual old-email misacquisition frequency is unknown.
- **Bounded implementation for Luna:** Extend the acquisition result with the durable mail request identifier and confirmed submission timestamp/reference. Emit a mailbox child only after verified `email_requested`, with the real request ID and the exact persisted watermark. Return an actionable identity/configuration hold for `email_required`. Version/adapt persisted queue payloads explicitly; legacy jobs with no verified request evidence must be held for reconciliation rather than pretending they were submitted. Keep existing side-effect deduplication, and define a separate explicit new submission generation for legitimate later resubmission without reopening a succeeded old request. Update `docs/workflows/mailbox-acquisition.md` and queue contract schemas.
- **Success criteria:** Zero mailbox jobs from identity-only `email_required`; every new mailbox job refers to one persisted verified submission; watermark/recipient/report identity round-trips unchanged; replay produces one form side effect and one mailbox job; a newer report submission cannot silently reuse the completed old request.
- **Validation:** Local queue integration: missing identity, static gate, verified submit, delayed receipt, old matching email, crash after durable submission, replay, and explicit later submission. Commands: `python -m pytest -q tests/test_workflow_queue_decomposition.py tests/test_report_download_orchestrator.py tests/test_workflow_control_orchestrator.py tests/test_state_service.py`; then `python scripts/ci/check_contract_schemas.py`. Include the normal acquisition → mailbox → verified artifact → ingest handoff through production orchestration with isolated state.

**Luna implementation prompt — ACQ-01 (copy/paste)**

```text
Implement ACQ-01 — Preserve one verified submission identity across acquisition and mailbox queues.
Objective: Deliver the verified behavior specified immediately above under canonical A19.
Source: docs/backlog/A-autonomy.md, technical slice ACQ-01.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A19 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="acq-02"></a>
#### ACQ-02 — Make IMAP reads non-mutating and message identities genuinely stable

**Primary canonical owner:** [A19](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

- **Priority / effort / dependencies:** P0 / M / ACQ-01 for request correlation, otherwise independent. **Backlog:** A19.7 (extends IMAP hardening).
- **Evidence and impact:** `_search_imap_messages`, `src/services/mailbox_acquisition_service.py:413–439`, opens a writable mailbox, uses sequence-number `search`/`fetch`, fetches `(RFC822)`, and saves the sequence number as `provider_message_id`. Sequence numbers can change after expunges; full RFC822 fetch can set the Seen flag. The contract describes these IDs as stable in `src/contracts/mailbox_acquisition.py:64–66`. `_adapt_email_message:697` trusts sender Date, while `_message_date_to_utc:819–828` substitutes current time for malformed Date. This can admit old messages as new. Protocol defects are observed; live server behavior was not probed.
- **Bounded implementation for Luna:** Use read-only SELECT/EXAMINE, UID SEARCH and UID FETCH with `BODY.PEEK[]` (metadata first when ACQ-04 lands), and provider/account/mailbox/UIDVALIDITY/UID-scoped IDs. Use IMAP INTERNALDATE for receipt time; retain header Date only as optional provenance. Add a versioned adapter for legacy sequence IDs that invalidates unsafe seen caches rather than equating them to UIDs. Report UIDVALIDITY change as cursor reset and continue within bounds.
- **Success criteria:** Polling changes no message flags; deleting an earlier message cannot change the identity of another message; mailbox/account collisions are impossible in fixture tests; invalid sender Date never becomes evidence of post-submission receipt.
- **Validation:** Protocol fake records IMAP commands and flags; test EXPUNGE, UIDVALIDITY rollover, two accounts with same UID, malformed Date, and old INTERNALDATE with recent sender Date. Add service-boundary tests and run `python -m pytest -q tests/test_mail_report_acquisition_orchestrator.py tests/test_state_service.py tests/test_workflow_control_orchestrator.py`; include no downstream ingest for an old email.

**Luna implementation prompt — ACQ-02 (copy/paste)**

```text
Implement ACQ-02 — Make IMAP reads non-mutating and message identities genuinely stable.
Objective: Deliver the verified behavior specified immediately above under canonical A19.
Source: docs/backlog/A-autonomy.md, technical slice ACQ-02.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A19 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="acq-03"></a>
#### ACQ-03 — Retrieve report mail without top-ten starvation or coarse-window false matches

**Primary canonical owner:** [A19](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / ACQ-01, ACQ-02. **Backlog:** A19.7.
- **Evidence and impact:** IMAP only filters `SINCE` a calendar day and takes latest `max_results` (`mailbox_acquisition_service.py:407–425`), with no publisher/recipient/report filter. Gmail `_gmail_query:489–502` rounds a minute window to days, builds an ungrouped OR expression, and `_search_gmail_messages:347–360` reads one result page. Defaults are a 120-minute window and 10 results (`src/config/app.yaml:846–849`). Thus unrelated newer messages can hide a valid delivery; Gmail query scope needs explicit grouping proof. The production starvation rate is unmeasured.
- **Bounded implementation for Luna:** Pass verified request time into `MailboxSearchRequest`, compile explicit Gmail grouping `recipient AND time AND (publisher OR title OR report terms)`, and enforce an exact receipt window after retrieval. Apply recipient/sender/title metadata narrowing to IMAP. Use bounded pagination or UID batches, preferably persisting a request cursor; add a low-budget fallback for forwarded/alias-recipient deliveries only with strong publisher/report evidence. Do not use an unrestricted all-mail search or unbounded scan. Define a finite delivery retention/expiry horizon so late mail does not fall outside an arbitrary rolling 120-minute window.
- **Success criteria:** A requested report ranked after 25 unrelated messages is found within the configured scan budget; old and wrong-recipient fixtures are excluded; all retrieval work remains capped; a valid delayed message remains eligible until request expiry; search query grouping is exact in fake-provider tests.
- **Validation:** Replay recipient alias/forward, 25-message noise, page two result, old same-title message, late delivery, empty/very generic title, and budget exhaustion. Run `python -m pytest -q tests/test_mail_report_acquisition_orchestrator.py tests/test_mailbox_acquisition_config.py tests/test_workflow_control_orchestrator.py`. Collect scanned/fetched counts and correct-report precision/recall on frozen sanitized mail fixtures; target 100% expected match decisions in that fixture set.

**Luna implementation prompt — ACQ-03 (copy/paste)**

```text
Implement ACQ-03 — Retrieve report mail without top-ten starvation or coarse-window false matches.
Objective: Deliver the verified behavior specified immediately above under canonical A19.
Source: docs/backlog/A-autonomy.md, technical slice ACQ-03.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A19 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="acq-04"></a>
#### ACQ-04 — Rank message and attachment metadata before downloading or writing bytes

**Primary canonical owner:** [A19](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / ACQ-02, ACQ-03. **Backlog:** A19.7.
- **Evidence and impact:** `_gmail_message_parts` downloads every named attachment (`mailbox_acquisition_service.py:592–608`); `_adapt_gmail_message:538–546` and `_adapt_email_message:700–708` materialize all eligible PDFs/ZIPs before `_filter_messages_after_watermark` and report affinity selection in `mail_report_acquisition_orchestrator.py:163–184`. Unrelated or old mail can therefore incur attachment fetch, decompression, and disk writes before exclusion.
- **Bounded implementation for Luna:** Add typed attachment references carrying provider ID, attachment ID/MIME path, filename, type and declared size. Return envelope/snippet/attachment metadata first. The generator ranks request affinity; the orchestrator asks the canonical mailbox service to fetch only eligible message bodies and top-ranked attachment references. Keep payload bytes out of workflow payloads and logs; preserve provenance and finite candidate/byte limits. Combine attachment and link affinity rules but do not introduce an LLM for metadata matching.
- **Success criteria:** Unrelated/pre-watermark messages cause zero attachment downloads or writes; a fixture with 10 noisy messages and one delivery fetches at most the selected report attachment(s); observable report selection is unchanged for existing valid fixtures; total bytes fetched decrease versus eager baseline on the frozen noise cohort.
- **Validation:** Protocol/service fakes count list/get/attachment calls and bytes; local temporary directory asserts zero artifacts for rejected metadata; compare eager baseline counters with new counters, including a filename-only correct report and generic-subject delivery. Run `python -m pytest -q tests/test_mail_report_acquisition_orchestrator.py tests/test_workflow_control_orchestrator.py tests/test_workflow_queue_decomposition.py`; complete one normal mailbox-to-ingest fixture.

**Luna implementation prompt — ACQ-04 (copy/paste)**

```text
Implement ACQ-04 — Rank message and attachment metadata before downloading or writing bytes.
Objective: Deliver the verified behavior specified immediately above under canonical A19.
Source: docs/backlog/A-autonomy.md, technical slice ACQ-04.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A19 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="acq-05"></a>
#### ACQ-05 — Preserve signed URLs and capture actual HTML link context

**Primary canonical owner:** [A19](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P0 / M / ACQ-04 for structured metadata; URL preservation can land first. **Backlog:** A19.7, with signed-link correction beyond its current wording.
- **Evidence and impact:** `_clean_url` globally `unquote`s URLs (`mailbox_acquisition_service.py:844–845`), which can turn encoded query delimiters into separators and change signed URLs. `_dedupe_strings:852–860` lowercases complete URLs; `select_mail_report_link_candidates` also deduplicates by complete lowercased URL (`mail_report_acquisition_generator.py:66–69`), although paths/query values can be case-sensitive. HTML anchors are collected without anchor text (`mailbox_acquisition_service.py:835–838`), while candidate context searches plain-text body only (`mail_report_acquisition_generator.py:59–74,181–195`). HTML-only opaque tracking CTAs can lose their report context.
- **Bounded implementation for Luna:** Preserve the literal navigable HTTP URL, decode HTML entities once through parsing, and normalize only scheme/host/default port for identity while preserving path/query case and encoding. Add typed link metadata with anchor text and a bounded nearby text excerpt, deriving evidence from that link rather than any report phrase anywhere in the message. Only unwrap known tracking redirects when an unambiguous encoded target exists and preserve the original URL/provenance; otherwise use normal acquisition safely. Keep sensitive signed parameters out of standard logs.
- **Success criteria:** Encoded delimiter, plus, token-case and repeated query fixtures reach acquisition with byte-equivalent URL semantics; two distinct case-sensitive asset URLs remain distinct; HTML-only legitimate report CTA is selected; unsubscribe/privacy/social CTAs are excluded even inside a report-delivery message.
- **Validation:** Local HTTP fixture rejects altered signatures and serves two case-distinct assets; HTML-only email includes one valid opaque report link and negative CTAs. Run `python -m pytest -q tests/test_mail_report_acquisition_orchestrator.py tests/test_http_acquisition_service.py`; add contract serialization checks and sanitized-log assertions.

**Luna implementation prompt — ACQ-05 (copy/paste)**

```text
Implement ACQ-05 — Preserve signed URLs and capture actual HTML link context.
Objective: Deliver the verified behavior specified immediately above under canonical A19.
Source: docs/backlog/A-autonomy.md, technical slice ACQ-05.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A19 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="acq-06"></a>
#### ACQ-06 — Verify and rank attachment PDFs before declaring acquisition success

**Primary canonical owner:** [A19](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P0 / M / ACQ-04, ACQ-07 bounds. **Backlog:** A19.2 and A19.7; reuse the shared PDF integrity work.
- **Evidence and impact:** `_materialize_attachment` writes any `.pdf` name or `application/pdf` bytes (`mailbox_acquisition_service.py:732–747`), and `_acquire_matching_attachment` returns the first `.pdf` artifact after broad subject/body checks (`mail_report_acquisition_orchestrator.py:436–498`). It does not structurally validate PDF bytes, rank filenames/attachment semantics, or verify source/report affinity. Route memory is promoted immediately after this (`:185–192`). A corrupt PDF or unrelated first attachment can appear successful before ingest rejects it. Canonical structural checks exist in `src/services/_pdf/text.py` around `validator_version="pdf-integrity-v1"`; use the public PDF service entrypoint, not its private helper.
- **Bounded implementation for Luna:** Use one deterministic affinity rank for attachment and link candidates, including filename/title/publisher/recipient/time. Verify each selected PDF through the canonical structural validator before route promotion/handoff. Quarantine bounded invalid candidates with typed reasons, continue to a lower-ranked eligible artifact, and abstain on ambiguous different-report ties. Use content hashes and attachment/MIME identifiers in output filenames to avoid same-basename overwrite. Keep verified local acquisition versus durable archive completion distinct.
- **Success criteria:** Zero success or route promotion for renamed HTML, empty/truncated/corrupt PDF, wrong-report attachment or ambiguous tie; correct report selected when a brochure precedes it; two same-basename PDFs retain separate content/provenance; verified report completes one ingest handoff.
- **Validation:** Real local tiny PDFs and corrupt fixtures, not mocked validation; multi-attachment mail with brochure then target; two ZIP members sharing basename; route-memory boundary fake asserts no promotion on failure. Run `python -m pytest -q tests/test_mail_report_acquisition_orchestrator.py tests/test_acquisition_ingest_handoff_orchestrator.py tests/test_report_download_orchestrator.py tests/test_state_service.py` plus the repository PDF validator tests identified by Luna before editing.

**Luna implementation prompt — ACQ-06 (copy/paste)**

```text
Implement ACQ-06 — Verify and rank attachment PDFs before declaring acquisition success.
Objective: Deliver the verified behavior specified immediately above under canonical A19.
Source: docs/backlog/A-autonomy.md, technical slice ACQ-06.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A19 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="acq-07"></a>
#### ACQ-07 — Enforce finite ZIP and attachment resource limits before decompression

**Primary canonical owner:** [A19](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

- **Priority / effort / dependencies:** P0 / S–M / ACQ-04 improves avoidance but is not required. **Backlog:** A19.7.
- **Evidence and impact:** `_materialize_zip_pdfs`, `mailbox_acquisition_service.py:754–785`, iterates every PDF member and calls `archive.read(member)` with no compressed/uncompressed byte, member, PDF count or ratio limits. `MailboxAcquisitionSettings` has no attachment limits. A large/bomb-like archive can consume substantial memory/disk and stop unrelated acquisition. This is an observed missing bound; no hostile live archive was examined.
- **Bounded implementation for Luna:** Define code-owned mandatory safe ceilings, with narrower operator limits if appropriate, for raw attachment bytes, archive member count, individual and cumulative uncompressed bytes, PDF count and compression ratio. Check declared sizes before reading, stream/decompress with a hard output limit to defend inaccurate metadata, reject encrypted/unsupported entries with stable candidate-level codes, write atomically only after validation, and clean partial files. Do not support recursive nested archives.
- **Success criteria:** Every configured resource bound is enforced before excessive allocation/write; oversized, highly compressed, malformed and encrypted fixtures yield explicit candidate failures; valid small ZIP still produces verified PDFs; rejecting one archive leaves no partial outputs and does not discard another eligible report candidate.
- **Validation:** Generate local archives for each exact-limit and limit+1 case, many empty members, repeated basenames, high compression, malformed archive and encrypted metadata; assert maximum bytes read/written and cleanup. Run `python -m pytest -q tests/test_mail_report_acquisition_orchestrator.py tests/test_mailbox_acquisition_config.py`; add a bounded mailbox-to-ingest success/failure pair.

**Luna implementation prompt — ACQ-07 (copy/paste)**

```text
Implement ACQ-07 — Enforce finite ZIP and attachment resource limits before decompression.
Objective: Deliver the verified behavior specified immediately above under canonical A19.
Source: docs/backlog/A-autonomy.md, technical slice ACQ-07.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A19 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="acq-08"></a>
#### ACQ-08 — Continue past candidate failures and suppress only the exact failed asset

**Primary canonical owner:** [A19](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / ACQ-01 and ACQ-05. **Backlog:** A19.7.
- **Evidence and impact:** `run_mail_report_acquisition`, `mail_report_acquisition_orchestrator.py:239–278`, raises immediately when the first candidate has a retryable failure, skipping lower-ranked valid candidates. `_suppress_rejected_mailbox_candidates:716–730` suppresses message+host rather than exact URL; `_record_mailbox_candidate_rejection:770–786` stores host/error with a blanket seven-day expiry. SQLite uniqueness is request+message+host+reason (`src/services/_state_service/mail_delivery.py:265–270`). One bad CDN asset can therefore suppress the correct asset from the same email. Existing `test_mail_report_acquisition_stops_on_retryable_candidate_download_error` explicitly locks in first-transient abort behavior.
- **Bounded implementation for Luna:** Within a finite candidate/time/budget cap, continue after candidate-specific transient or permanent failures; immediately abort global authentication, budget or invalid-contract failures. Persist suppression by request+stable message identity+exact safe URL identity/hash+failure class; use retry-after/short backoff for transient and longer expiry only for stable permanent failure. Aggregate error evidence after all eligible candidates fail without nested hidden retries. Version/migrate rejection storage and adapt legacy host-only records so they cannot suppress unrelated URLs.
- **Success criteria:** First candidate timeout plus second valid PDF succeeds in the same bounded attempt; failed same-host URL never suppresses another URL; global budget/auth error causes zero further provider calls; a transient asset becomes eligible after its backoff; replay does not repeat a still-suppressed permanent URL.
- **Validation:** Update the first-transient test to new observable semantics; add same-host/different-path, identical URL from different message, expired suppression, global budget, all-failed aggregate and cap tests. Run `python -m pytest -q tests/test_mail_report_acquisition_orchestrator.py tests/test_state_service.py tests/test_workflow_control_orchestrator.py tests/test_workflow_queue_decomposition.py` and contract schema checks.

**Luna implementation prompt — ACQ-08 (copy/paste)**

```text
Implement ACQ-08 — Continue past candidate failures and suppress only the exact failed asset.
Objective: Deliver the verified behavior specified immediately above under canonical A19.
Source: docs/backlog/A-autonomy.md, technical slice ACQ-08.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A19 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="acq-09"></a>
#### ACQ-09 — Replace worker-blocking delivery waits with durable, bounded poll scheduling

**Primary canonical owner:** [A19](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / L / ACQ-01–03 and ACQ-08. **Backlog:** A19 bounded recovery; reuse existing queue scheduling rather than creating a scheduler.
- **Evidence and impact:** The mailbox orchestrator loops and sleeps (`mail_report_acquisition_orchestrator.py:140–159,325–356`), with default 900-second timeout and 60-second interval (`app.yaml:848–849`). Within the loop, it continues passing original seen IDs instead of updated poll state (`:157,170–176`). `run_due_mail_delivery_requests` processes requests sequentially (`workflow_control_orchestrator.py:1612–1629`); retryable errors are immediately due again, discard new seen IDs, and always clear the existing cursor (`:1637–1653`). Thus waits can monopolize workers and repeat expensive reads; receipt latency/cost under production load remains unmeasured.
- **Bounded implementation for Luna:** Make each production mailbox job one bounded scan, atomically checkpoint evaluated-message/candidate outcomes and cursor, then defer through the canonical queue at `next_attempt_after_utc` with bounded backoff/jitter and request expiry. Reuse verified submission age; do not resubmit a form merely because mail is late. Distinguish unseen, inspected-with-retryable-candidate, permanently rejected, and successful message states so a blanket seen flag cannot discard a transiently failed valid link. Add claim/lease protection or use the existing canonical queue lease to prevent duplicate concurrent request polls. Keep CLI synchronous polling only as an explicitly bounded wrapper around the same one-scan operation.
- **Success criteria:** No production worker sleeps awaiting delivery; empty-inbox attempt returns after one bounded scan; request resumes after restart with cursor/outcomes intact; transient candidate is retried when due; ten delayed requests cannot serialize ten 900-second waits; concurrent workers cause one active request poll and one ingest handoff; final expiry produces a stable operator-actionable outcome.
- **Validation:** Fake clock plus real temporary queue/state: delayed mail after three polls, crash between fetch/checkpoint, transient asset, two competing workers, expiry, long delivery delay, and unrelated noise. Run `python -m pytest -q tests/test_mail_report_acquisition_orchestrator.py tests/test_workflow_control_orchestrator.py tests/test_workflow_queue_worker_failures.py tests/test_workflow_queue_service.py tests/test_workflow_queue_decomposition.py`; replay the full local submission→deferred mail→artifact→ingest chain.

**Luna implementation prompt — ACQ-09 (copy/paste)**

```text
Implement ACQ-09 — Replace worker-blocking delivery waits with durable, bounded poll scheduling.
Objective: Deliver the verified behavior specified immediately above under canonical A19.
Source: docs/backlog/A-autonomy.md, technical slice ACQ-09.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A19 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="acq-10"></a>
#### ACQ-10 — Account for actual mailbox work and measure the verified delivery funnel

**Primary canonical owner:** [A19](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / ACQ-01, ACQ-04 and ACQ-09. **Backlog:** A19.8–9; feed A14 economics, not a second controller.
- **Evidence and impact:** `_reserve_mailbox_read` reserves one mailbox read (`mailbox_acquisition_service.py:63–95`), but search can issue list/search plus many message and attachment gets (`:347–374,592–599`). Finalization records provider attempt count (`:199–207,221–228`), not actual operations/bytes; reservation of one can also precede two provider attempts on fallback (`:152–183`). Existing logs show message/candidate/poll counts but no end-to-end confirmed-submission→correct-delivery rate. Therefore nominal budget usage can understate work, and a form confirmation cannot establish actual delivery success. Production delivery baselines are unavailable in this review.
- **Bounded implementation for Luna:** Clarify the existing `mailbox_read` unit (logical scan versus external call); record both actual provider calls and bytes with correct budget reservations/finalization through the canonical authority, including failures and fallback. Enforce per-request ceilings before each external step, and map global exhaustion to durable defer without bypass. Add one sanitized funnel keyed by durable request ID: verified submission, message observed, matched candidate, PDF verified, archived/ingest handoff, expired, plus receipt latency and candidate rejection reason. Report `verified correct acquisitions / verified submissions` with fixed maturity window and pending denominator; do not count `email_required` or pending deliveries as successes. Reuse retained evidence/telemetry exports.
- **Success criteria:** Fake call counters equal ledger usage for list/get/attachment/fallback/failure paths; configured ceilings are never exceeded; all terminal funnel outcomes reconcile to persisted requests without double count; a frozen local cohort has 100% outcome accounting and measured p50/p95 latency/call/byte counts. A live improvement target must be set only after a sanctioned baseline; no invented uplift.
- **Validation:** Protocol fakes instrument every operation; temporary usage ledger tests exhaustion before attachment download, failed OAuth/provider call, fallback and replay idempotency. Export a synthetic cohort containing success, late/pending, false match, corrupt PDF and expiry; independently reconcile exported totals with SQLite. Run `python -m pytest -q tests/test_llm_usage_ledger_service.py tests/test_mail_report_acquisition_orchestrator.py tests/test_workflow_control_orchestrator.py tests/test_workflow_queue_evidence.py` and `python scripts/ci/check_contract_schemas.py`.

**Review validation status:** Source/contracts/config/backlog/tests inspected. Attempted `python -m pytest -q tests/test_mail_report_acquisition_orchestrator.py tests/test_mailbox_acquisition_config.py`; it did not execute because the available Python environment lacks `pytest` (`No module named pytest`). No live Gmail/IMAP/browser/form calls or source modifications were made. The commands above are future implementation checks, not claimed passing checks.

**Luna implementation prompt — ACQ-10 (copy/paste)**

```text
Implement ACQ-10 — Account for actual mailbox work and measure the verified delivery funnel.
Objective: Deliver the verified behavior specified immediately above under canonical A19.
Source: docs/backlog/A-autonomy.md, technical slice ACQ-10.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A19 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
 
## A20. Prove clean-room capability readiness before first external work

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** none; outcome specification stands alone.

- **Baseline:** Profiles, path/LLM/prompt preflight, browser-doctor, dependency locks and canaries exist, but not one complete profile-derived capability proof. Path checks can create directories and write/delete fixed-name probes; successful policy preflight persists a matrix. These are reversible local probes, not a zero-local-write doctor. Distinguish no default external writes from uniquely scoped local probe/output writes and retain missing/skipped prerequisite evidence.
- **Target behaviour:** One capability doctor with no default external writes resolves exact intent/profile stages and capabilities before costly/mutating workflow work. Explicit local probes/proof artifacts are uniquely scoped, cleaned or declared and safe under concurrency. It distinguishes `ready`, `degraded-but-supported`, `not_required`, `not_checked` and `blocked`, retaining safe remediation and configuration/policy/build identity without exposing/changing secrets.
- **What to implement, in order:**
  1. Extend the existing pipeline-preflight contracts and orchestrator rather than adding a parallel health framework. Derive required checks from the canonical workflow/queue registry, selected run profile, planned side effects, and generated capability manifest; a stage cannot start if a required capability is absent from the proof.
  2. Add deterministic local probes for Python/locked-package compatibility, required imports and subprocess tools, configured font/template/prompt/schema assets, PDF/render/OCR availability, browser package/runtime compatibility, writable paths plus configurable free-space floor, and every canonical SQLite store's migration level, integrity, foreign keys, and bounded lock/write probe. Probes may create only uniquely named temporary files/transactions and must clean them up. Use uniquely named cleaned local probes and explicit write ownership; writability is not SQLite schema health/lockability. Consume existing R5 dependency-lock proof rather than recreate lock tooling.
  3. Add opt-in bounded live probes for the exact external capabilities selected by the profile: Drive list/read and optional archive-write authority, LLM model/structured-output compatibility, vector-store access, mailbox read/search, browser launch/network, and WordPress schema/auth/readback. Use zero-write/read-only operations wherever the provider supports them; any write probe must be explicitly enabled, budgeted, uniquely scoped, verified, and reversed.
  4. Reconcile operator policy before work: active price-card attestation, budget authority/ledger availability, source and target identity, publication approval mode, queue controls, recovery gates, and required secret *names* without ever printing values. Make `not_checked` blocking for a required capability when a live run is requested.
  5. Expose the same report through CLI and operator UI, with a bounded summary plus a retained detailed artifact. Every blocker must name the failed stage/capability, stable error code, safe evidence, exact next command/config key, whether automatic repair is prohibited, and the command to rerun the same proof.
  6. Prove the workflow from clean supported Windows and Ubuntu environments using the hash-locked install, empty runtime stores, a copied value-free local overlay, and sandbox/read-only credentials. Keep the ordinary CI lane provider-free and run live probes only behind the existing guarded integration controls.
- **Acceptance criteria:**
  - For every registered runnable intent/profile, the doctor lists all required stages and capabilities with no required stage left `not_checked`; manifest/registry drift fails a deterministic test.
  - Clean supported Windows and Ubuntu runs install from `requirements.lock`, initialize/migrate empty stores, resolve all assets/tools, and reach a retained `ready` or explicitly supported `degraded-but-supported` proof without source-code or committed-config edits.
  - Missing/wrong binary, stale schema, corrupt database, insufficient disk, locked store, incompatible browser, missing price, absent credential name, wrong provider model, denied Drive/mailbox/WordPress capability, and TLS/clock failure each block before the affected external/costly operation with one actionable stable code.
  - A required live capability cannot inherit a green result from a skipped probe. Offline planning remains available and labels live capabilities `not_checked` without pretending the workflow is executable.
  - Default execution performs zero provider/model/browser/mailbox/Drive/WordPress writes, logs no secret values or submitted/source content, leaves no probe artifacts, and produces identical ordered output for identical environment state.
  - Tests cover the capability matrix, local probe cleanup, redaction, profile-specific omission, live-guard behavior, and proof invalidation when configuration, policy, build, dependency, schema, or tool identity changes; canonical setup/configuration/troubleshooting docs carry the one supported procedure.

### Luna implementation prompt — A20

```text
Work on A20 — Prove clean-room capability readiness before first external work at the current MarketLense HEAD.
Owner specification: docs/backlog/A-autonomy.md; canonical status: CONSOLIDATED_TODO.md.
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
 
## A21. Establish a representative first-attempt end-to-end reliability SLO

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `ING-01`, `ING-02`, `ING-04`, `ING-05`, `ING-06`, `ING-07`, `SYS-01`, `SYS-02`, `SYS-03`, `SYS-04`, `SYS-05`, `SYS-06`, `SYS-08`, `SYS-09`, `SYS-10`, `CODE-01`, `CODE-02`, `CODE-03`, `CODE-06`, `CODE-07`, `CODE-08`, `CODE-09`, `ART-01`, `ART-02`, `ART-03`, `ART-04`, `ART-05`, `ANA-02`, `ANA-07`, `GRD-01`, `GRD-02`, `GRD-03`, `GRD-04`, `GRD-08`, `VER-01`, `VER-02`, `VER-03`, `VER-04`, `VER-05`, `VER-07`, `VER-09`, `ARCH-A`, `ARCH-C`, `ARCH-H`.

- **Current scoped evidence (through 2026-10-08):** Semantic validation requires attributable verdicts and quotes; retryable execution errors reach bounded queue retries; OCR text cache identity binds to derived PDF checksum/extractor, and inconsistent cached PDF-text provenance is rejected (`bafd72ed`). Queue changes reconcile expired outbox leases and reject incompatible idempotency-key reuse (`207d6213`). Signal publication now retains frozen candidate manifests with checksum/readback and report-attribution fixes (`296afecb`, `2e6eae39`, `83a8d250`). Focused tests were added, but no fresh exact-HEAD full-graph, external-readback or editorial-quality acceptance was observed.

- **Baseline:** Queues/checkpoints/lineage, first-pass/recovery telemetry, final-package/readiness binding and approved idempotent publication exist. The historical `bfab37bbd1e4c194c027f14dd54817fb61f940a6` 2/20 result is no longer the latest full-cohort measurement. The [October 2–3 full20 frozen-source run](../../docs/quality/reliability-cohort-20260927-grounding/full20-grounding-readiness-20261002/measurement.json), producer `23fec7388553041aabcc3e1e0775abb559c6695d`, records 18 final validations/packages, 16/20 readiness passes (80%), four typed failures, 720 calls, estimated $1.321959, 8/20 bounded repairs and zero operator interventions. The subsequent [selected-four regression](../../docs/quality/remaining-four-finalization-20261003/measurement.json), producer `9466f4c0b718c691817a820793b4fa97ac5d8040`, records all four former failures passing validation/readiness with 134 calls. Publication was disabled in both. Combining those revisions cannot prove a single-revision 20/20 result. Neither lane proves current-HEAD fresh discovery/acquisition, no-repair conversion, human acceptance or approved publish/readback/replay. A21 stays Active; E13 owns item-scoped repair and E11 remains a scoped structured-validity milestone. Current local regression coverage verifies bounded explicit requeue and terminal handling of final-attempt lease expiry; it does not add a fresh full-graph replay or change the retained cohort results.
- **Target behaviour:** A frozen representative program measures the probability that a newly admitted source reaches an immutable `awaiting_review` package on its first submitted workflow attempt, with no operator repair, cohort substitution, ungoverned retry, or reuse of derived editorial artifacts. After explicit approval, the ready subset reaches authenticated sandbox readback and a zero-write replay. Failures remain visible in the denominator and drive shared, publisher-agnostic prevention work.
- **What to implement, in order:**
  1. Preserve implemented first-attempt/first-pass/recovery/operator/replay classifications and reconcile them with immutable final-package/report-scoped readiness. Fill missing attribution rather than build another scorecard or count internally repaired success as first-pass.
  2. Freeze a stratified cohort by reusing the A18 discovery corpus, P6 editorial cohorts, and retained acquisition-route evidence where identities remain compatible. Cover direct PDF, report-page extraction, browser, gated/mailbox, on-site capture, short/long, native/OCR, data-heavy/narrative, multi-publisher, and visual/no-usable-visual cases; add only missing strata and never select or replace members based on generated outcome.
  3. Run two bound lanes on the exact implementation SHA: a deterministic provider-free replay of retained external-boundary fixtures for the whole queue graph, and a controlled live/sandbox lane from real discovery/acquisition through source ingest, analysis, render, analytics projection, publication readiness, Signal/Briefing opportunity where eligible, explicit approval, WordPress publication, authenticated readback, and identical-package replay.
  4. Complete missing cohort-bound stage/attempt/usage/intervention and queue-health joins using existing reliability entities/transitions/Pareto. Retain exact cohort/configuration/policy/build/fixture identity and denominator/availability; unavailable attribution is never zero.
  5. Preserve the selected-four corrections, then rerun the unchanged full20 on one promoted revision before assigning a current failure Pareto. Fix only reproduced shared causes at their owner; never reimplement proven fixes, relax gates/retries, delete failed members or combine revisions into synthetic 20/20 success. Confirm previously failing processes first, then the complete required cohort.
  6. Add a release-facing SLO check with separate deterministic and controlled-live dispositions. Test both default manual approval and the *separately opted-in* `autonomous_mvp` policy-gated approval through the canonical ledger and isolated sandbox readback. Enabled code is **not** proof of public auto-publication safety: reconcile P6 editorial and E15 visual acceptance before permitting unattended public writes.
- **Acceptance criteria:**
  - The frozen cohort and stratum manifest are hash-pinned before execution, every admitted member remains in every denominator, and derived report/editorial/crop/readiness caches are empty at start; only explicitly declared immutable source/route fixtures may be reused.
  - The provider-free full-graph replay completes **100%** of eligible entities to the expected terminal state with zero orphan jobs, lost outbox events, stale-lease commits, duplicate effective side effects, or unclassified failures.
  - In the controlled live lane, at least **95%** of valid admitted sources reach `awaiting_review` on the first submitted attempt without operator intervention, at least **90%** pass publish readiness without targeted editorial regeneration, and **100%** reach a typed terminal state within configured bounds. Source-invalid/rights/credential blockers are reported separately but remain in the intake funnel.
  - After checksum-bound approval (manual by default; automatic only in the explicitly enabled policy lane), **100% of publish-ready admitted packages attempted against the healthy sandbox** receive authenticated metadata/content/media readback, and replaying identical package requests performs zero WordPress post writes; target outages remain explicit unavailable evidence, not a pass.
  - Policy-enabled approvals fail closed on warnings, stale/changed packages, unsupported or unresolved claims, incomplete assets, missing no-override provenance and disabled configuration. Before public unattended writes, document the release decision and prove or enforce holds for unresolved P6/E15 acceptance; deterministic readiness alone is not independent human quality acceptance.
  - Stage results identify first-pass, internally repaired, retried, operator-requeued, and permanently held outcomes separately with exact calls/tokens/cost/duration; no successful retry rewrites the original first-attempt result.
  - Each promoted fix improves the compatible cohort's first-attempt conversion or cost/time-to-terminal without reducing source fidelity, editorial P6 scores, E15 crop acceptance/coverage, acquisition recall, or publication safeguards; the final evidence is bound to one exact SHA and the release surface.

### Luna implementation prompt — A21

```text
Work on A21 — Establish a representative first-attempt end-to-end reliability SLO at the current MarketLense HEAD.
Owner specification: docs/backlog/A-autonomy.md; canonical status: CONSOLIDATED_TODO.md.
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
 
<a id="ing-01"></a>
#### ING-01 — Refill ready queue work while long analysis jobs are running

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1; M, three implementation slices; ING-09 should land before materially increasing provider concurrency. **Owner:** workflow supervisor; implement as an A21 performance subtask. D1 remains deferred: no new DAG engine or deployable.

**Evidence and impact:** `src/orchestrators/workflow_supervisor_orchestrator.py:218–281`, `_run_worker_batches_parallel()`, constructs a fixed candidate list and dispatches at most `max_jobs_per_queue` jobs from each queue during a pass. A downstream queue marked idle stays inactive throughout the pass even if upstream work subsequently enqueues its inputs. Retained `docs/quality/frozen-five-ingestion-performance-baseline-20261004-queue-configured.json`, `telemetry.queue_concurrency` and timing rows, shows cap=5, observed=1 and source-ingest waits up to approximately 896 seconds. **Confirmed:** fixed-pass scheduling and retained observations. **Hypothesis:** work-conserving refill materially reduces cohort time; increasing limits alone is not proven to do so.

**Luna implementation:** (1) Add a provider-free scheduling fixture with five ready sources, slow analyses, fast render/readiness jobs and a child becoming ready after an idle probe. (2) Replace the precomputed dispatch snapshot with bounded round-robin refill of ready queues; recheck an idle queue only after a completion/outbox materialization can have created work. Preserve durable queue worker limits, total-job allowance, lease uniqueness and runtime stop. (3) Add ready/running/idle/dispatch-gap counts to existing telemetry, then benchmark unchanged workloads before selecting defaults.

**Success criteria:** Identical job identities, terminal outcomes and zero publication writes; configured cap=1 remains serial; configured cap=3 actually overlaps independent jobs without exceeding three. Provider-free cohort median time improves at least 25% over five repeated equivalent runs; promote a production default only after compatible retained/live evidence passes all existing quality gates.

**Validation:** `python -m pytest -q tests/test_workflow_supervisor_parallelism.py tests/test_workflow_supervisor_orchestrator.py tests/test_workflow_control_supervisor.py`; extend those tests with idle-to-ready transitions, failure, budget defer and runtime exhaustion. Reuse `scripts/quality/benchmark_ingest_parallelism.py`; a supervisor fixture benchmark must separately report scheduler time because that existing benchmark alone does not validate supervisor dispatch.

**Luna implementation prompt — ING-01 (copy/paste)**

```text
Implement ING-01 — Refill ready queue work while long analysis jobs are running.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ING-01.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ing-02"></a>
#### ING-02 — Bind extracted OCR text to the derived OCR artifact identity

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

**Priority / effort / dependencies:** P0; S–M, two slices; none. **Owner:** report-source cache. Targeted correctness extension to closed E7/E9; those closures do not prove this subsidiary cache is fresh.

**Evidence and impact:** `src/generators/_report_source_generator/source_loading.py:330–345`, `_load_text()`, uses `text_cache_key(runtime.md5, runtime.settings)` for both native and `ocr_text` extraction. `src/generators/report_generation_shared.py:141–153` includes original MD5 and extraction limits, but no derived OCR PDF/prompt/model identity. By contrast `src/generators/pdf_text_ocr_generator.py:92–103` invalidates the OCR response/PDF on prompt/model changes. **Confirmed cache-key mismatch:** a newly generated OCR PDF can therefore encounter an older matching `ocr_text` cache for the same original source. Frequency and real affected reports are unmeasured.

**Luna implementation:** (1) Extend the source-cache binding input to carry a canonical analysis-artifact checksum or OCR aggregate compatibility hash. Keep native extraction keyed to original content. (2) Version the OCR-text key to include derived artifact identity plus extractor generation/limits; do not merely include the path. Invalidate legacy OCR-text entries through the version transition while retaining native cache reuse. Record identity/hash and hit/miss reason without source text.

**Success criteria:** Same original PDF with two different valid OCR outputs always returns the matching current text; changing OCR prompt/model/policy invalidates only incompatible derived text. An unchanged OCR artifact performs zero extra OCR/model calls and no redundant extraction.

**Validation:** `python -m pytest -q tests/test_report_source_generator.py tests/test_prompt_family_minimal_execution.py`; add fixtures containing original PDF A, OCR output A1 and A2 with distinct page text, same original MD5, and a legacy cache. Exercise the real cache reader/writer and canonical source preparation with fake PDF/model service boundaries. Check downstream page spans against the new OCR output.

**Luna implementation prompt — ING-02 (copy/paste)**

```text
Implement ING-02 — Bind extracted OCR text to the derived OCR artifact identity.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ING-02.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ing-04"></a>
#### ING-04 — Recover weak pages without OCRing every healthy page

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1; L, four independent slices; ING-02/ING-03. **Owner:** PDF OCR and report source preparation. New bounded efficiency/correctness extension; preserve the existing native-first policy and canonical PDF boundary.

**Evidence and impact:** `src/generators/_report_source_generator/text_validation.py:267–374` samples native confidence and requests OCR at document level. `src/generators/pdf_text_ocr_generator.py:170–199` splits the entire source and loops all chunks; no selected-page set is supplied. **Confirmed:** fallback is full-document despite the `native_first_selective` policy name. **Hypothesis:** mixed native/scanned reports lose weak pages when sampled pages look healthy, or incur unnecessary full OCR when fallback triggers. Do not promise improvement on fully scanned documents.

**Luna implementation:** (1) Retain per-page native availability/confidence for the actual extracted range, with explicit unevaluated pages. (2) Add an optional ordered page-selection contract to canonical OCR splitting; preserve source page numbers when grouping sparse pages. (3) Merge validated OCR only for selected weak pages with native text for healthy pages; create a page-preserving analysis artifact rather than renumbering into a shorter document. (4) Keep full-document OCR for explicit `always` or truly wholly unreadable sources. Gate any selection algorithm change on the retained mixed-PDF corpus.

**Success criteria:** A 20-page fixture with two unreadable content pages sends only those two pages to OCR, retains all 20 provenance positions and healthy text unchanged. OCRed-page count decreases by at least 80% on that fixture, while all labelled recoverable evidence remains available; fully scanned fixture coverage is unchanged. Duplicate/out-of-range OCR pages fail closed.

**Validation:** `python -m pytest -q tests/test_report_source_generator.py tests/test_openai_ocr_service.py tests/test_claim_validation_source_pages.py`; extend fixtures with interleaved scans, intentionally blank pages, nonconsecutive weak pages and rotated pages. Run `python scripts/ci/check_pdf_candidate_benchmark.py` plus affected source-to-selection replay to prove crop/source coordinates still refer to the original PDF.

**Luna implementation prompt — ING-04 (copy/paste)**

```text
Implement ING-04 — Recover weak pages without OCRing every healthy page.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ING-04.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ing-05"></a>
#### ING-05 — Persist validated OCR chunks before later chunks can fail

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1; M, three slices; ING-02; ING-04 optional. **Owner:** OCR artifact reuse. Extension to closed E9; no additional hidden retry loop.

**Evidence and impact:** `src/generators/pdf_text_ocr_generator.py:194–304` accumulates chunk results in memory; aggregate cache writing occurs only after all chunks and PDF rendering finish at approximately lines 312–344. If a later chunk/provider call or final rendering fails, successful earlier chunk responses have no reusable per-chunk artifact. **Confirmed reuse gap;** actual wasted cost is not measured.

**Luna implementation:** (1) Define a versioned chunk result with source content identity, selected source-page range/set, chunk bytes hash, prompt/policy/model/schema identity, validated mapped pages and usage reference. (2) Atomically materialize a chunk only after schema and source-page mapping validate; before each chunk call resolve an exact compatible result. (3) Assemble only a complete ordered chunk set, then render through the current service. Keep retries with orchestrators and leave partial work visibly incomplete; do not mark an aggregate cache hit from incomplete chunks.

**Success criteria:** On a three-chunk fixture failing at chunk three, replay performs no provider call for chunks one/two and produces the same canonical aggregate/page provenance after chunk three succeeds. Changed prompt/model/chunk bytes invalidate affected results; interrupted writes or duplicate/missing page output never become reusable. Cost/usage attribution counts first-run and replay calls once each.

**Validation:** `python -m pytest -q tests/test_report_source_generator.py tests/test_openai_ocr_service.py tests/test_prompt_family_minimal_execution.py`; inject failures through the public OCR client and render service, not private helper patching. Test corrupt sidecars, atomic-write interruption, invalid page maps and final-render-only retry. Compare provider-call counts and output hashes before/after on an unchanged local source.

**Luna implementation prompt — ING-05 (copy/paste)**

```text
Implement ING-05 — Persist validated OCR chunks before later chunks can fail.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ING-05.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ing-06"></a>
#### ING-06 — Reject inconsistent cached PDF-text provenance instead of silently dropping pages

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

**Priority / effort / dependencies:** P0; S–M, two slices; none. **Owner:** source-cache contract validation; surgical correctness extension to E7/E9 and R3.

**Evidence and impact:** `src/generators/_report_source_generator/cache_io.py:95–127`, `_adapt_cached_text()`, accepts numeric counts/density without consistency/range/finite checks and silently skips malformed page entries. `src/generators/report_source_cache.py:108–124` treats any non-None adapted value with the key as a hit. `src/contracts/pdf_text.py:13–64` dataclasses describe page/count semantics without runtime validators. `src/orchestrators/report_analysis_orchestrator.py:488–499` uses retained pages as grounding spans. **Confirmed:** a malformed cache can be reused with missing/invalid provenance even when top-level text/counts look valid; runtime frequency unknown.

**Luna implementation:** (1) Implement deterministic semantic validation of supported source-cache versions: integer nonnegative counts, finite nonnegative density, `char_count == len(text)`, positive unique ordered page numbers within the known source range and valid page texts. Account for legitimate text truncation explicitly; do not require concatenated page text to equal truncated global text. (2) Invalid/incomplete current-version caches become a reasoned cache miss and are regenerated through canonical extraction; older caches lacking optional pages must follow an explicit compatibility policy, not silently masquerade as fully provenance-capable. Apply analogous finite/range checks to PDF info/contents adapters.

**Success criteria:** Every malformed fixture is rejected or adapted explicitly; none yields a false hit or unsupported page span. Valid current entries reuse with zero PDF/model calls. Legacy adaptation is deterministic and documented, preserving legitimate truncated text semantics.

**Validation:** `python -m pytest -q tests/test_report_source_generator.py tests/test_claim_validation_source_pages.py tests/test_source_identity_provenance.py`; table-driven cache fixtures for duplicate/negative/out-of-range pages, NaN density, mismatched count, malformed page object, valid truncation and older schema. Replay downstream grounding with a real valid cache and prove stable source spans.

**Luna implementation prompt — ING-06 (copy/paste)**

```text
Implement ING-06 — Reject inconsistent cached PDF-text provenance instead of silently dropping pages.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ING-06.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ing-07"></a>
#### ING-07 — Stop launching artifact work once a required artifact has failed

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1; M, two slices; none. **Owner:** analysis artifact scheduler. Targeted cost extension to existing bounded batches, not generic concurrency infrastructure.

**Evidence and impact:** `src/orchestrators/_report_analysis_orchestrator/artifact_batches.py:76–107`, `_execute_artifact_step_batch()`, eagerly submits every task; it collects all future outcomes, then calls `cancel()` only after `as_completed()` has exhausted them. **Confirmed:** that cancellation cannot prevent queued provider work by that point. A failed required artifact can consequently be followed by avoidable calls. Savings depend on failure frequency and batch shape; not measured.

**Luna implementation:** (1) Submit at most the effective worker count and refill as results arrive, preserving stable output key semantics. (2) On the first required failure, stop refill and cancel futures that have not started; allow already-running boundary calls to finish safely and account for their usage. Surface the original typed failure and retain validated completed-family artifacts through existing materialization; do not claim interruption of active HTTP requests. (3) Preserve the sequential path and existing retry ownership; clarify any genuinely optional task before excluding it from fail-fast policy.

**Success criteria:** With eight tasks and two workers, an immediate required-task failure causes no provider call from a task still unscheduled when the failure was observed. Maximum concurrency stays two; successful batches retain exact output/schema/provenance. Already-started calls are accounted, and no incomplete batch is promoted.

**Validation:** `python -m pytest -q tests/test_report_analysis_orchestrator_decomposition.py tests/test_artifact_parallelism_benchmark.py tests/test_artifact_generator.py`; add event-controlled fake external clients covering first/last failure, simultaneous completion, cancellation and successful out-of-order responses. Reuse `scripts/quality/benchmark_artifact_parallelism.py` for no-failure output/time parity and a failure lane reporting avoided calls.

**Luna implementation prompt — ING-07 (copy/paste)**

```text
Implement ING-07 — Stop launching artifact work once a required artifact has failed.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ING-07.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="sys-01"></a>
#### SYS-01 — Preserve effective configuration across the entire acquisition-to-publication graph

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority:** P0. **Effort:** M. **Depends on:** none. **Backlog:** A18/A19/A21 implementation detail; complements existing downstream configuration-isolation work.

**Evidence / diagnosis (confirmed):** `src/orchestrators/_workflow_queue_handlers/acquisition.py:153-415` loads discovery, acquisition and mailbox settings with `ConfigLoadRequest(path="")`. Its child payloads omit `config_path`; `src/orchestrators/acquisition_ingest_handoff_orchestrator.py:135-158` carries only acquisition route in attributes. Conversely, `_workflow_queue_handlers/report_pipeline.py:370-376` and `analytics.py:187-188` honor a carried configuration path. An isolated acquisition job can therefore enter default stores/settings before the already-fixed downstream isolation takes effect. A path alone also does not pin mutable configuration between workers.

**Implementation for Luna:** Add a versioned, non-secret effective-configuration reference/hash to the common queue envelope, with an adapter for legacy payloads. Resolve it through the configuration service, verify compatibility before external I/O, and propagate it through discovery, acquisition, mailbox, verified handoff and all children. Retain immutable public settings/provenance or reject incompatible drift; continue resolving credentials through the canonical service. Extend the existing isolation test rather than create another configuration loader.

**Success criteria:** Every child preserves the effective configuration identity. A temporary-config full graph touches only its designated databases/artifact roots; drift fails before any provider or storage write. Default CLI behavior remains supported through an explicit legacy adapter.

**Validation:** Extend `tests/test_workflow_queue_config_isolation.py` and `tests/test_acquisition_ingest_handoff_orchestrator.py` with two distinct temporary configurations, service-boundary fakes and a mid-run configuration change. Run `python -m pytest -q tests/test_workflow_queue_config_isolation.py tests/test_validation_queue_lineage.py tests/test_acquisition_ingest_handoff_orchestrator.py`; run the contract snapshot gate after contract migration.

**Luna implementation prompt — SYS-01 (copy/paste)**

```text
Implement SYS-01 — Preserve effective configuration across the entire acquisition-to-publication graph.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice SYS-01.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="sys-02"></a>
#### SYS-02 — Maintain real lease ownership throughout long-running workflows

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority:** P0. **Effort:** M. **Depends on:** none. **Backlog:** A21/R2. Separate from CODE-01/02 attempt exhaustion and ING supervisor throughput.

**Evidence / diagnosis (confirmed gap; outage manifestation conditional):** `workflow_worker_orchestrator.py:56-172` executes the handler synchronously, never calls the existing `heartbeat_workflow_job`, and passes its same `now_utc` to claim, start and completion. The supervisor passes its start timestamp to every worker (`workflow_supervisor_orchestrator.py:289-304`). Its singleton lease is acquired once and not renewed, while the parallel loop waits for running futures beyond its dispatch deadline (`:238-282`). Base supervisor lease is 180 seconds, but report-stage leases and handlers are much longer (`src/config/app.yaml:961-977,1050-1061`). A second supervisor/reaper can reclaim still-active work; frozen time can let an expired worker appear current.

**Implementation for Luna:** Use an injectable clock whose production value advances. Renew worker and singleton leases at bounded intervals while work is active; keep I/O in queue services and heartbeat ownership in orchestrators. Detect lease loss and stop new irreversible/provider operations at safe boundaries. Do not change at-least-once delivery or manufacture exactly-once guarantees. Enforce a dispatch deadline separately from an honest drain duration.

**Success criteria:** No worker commits against an expired/reassigned lease; long healthy jobs retain ownership; a second supervisor stays busy until the first exits or genuinely loses ownership. Crash recovery still works after renewal stops.

**Validation:** Extend `tests/test_workflow_supervisor_orchestrator.py`, `tests/test_workflow_control_supervisor.py` and `tests/test_workflow_queue_worker_failures.py` using clock/service seams and a blocking controlled handler. Exercise elapsed lease, heartbeat failure, owner replacement, exception cleanup and process-loss recovery. Run these focused suites plus `tests/test_workflow_supervisor_parallelism.py`.

**Luna implementation prompt — SYS-02 (copy/paste)**

```text
Implement SYS-02 — Maintain real lease ownership throughout long-running workflows.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice SYS-02.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="sys-03"></a>
#### SYS-03 — Give maintenance queues explicit capability semantics before enabling them

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority:** P0. **Effort:** L split into one adapter per PR. **Depends on:** SYS-01/02 for enabled execution. **Backlog:** A21/R2; architecture documentation already acknowledges unmigrated adapters.

**Evidence / diagnosis (confirmed):** `_workflow_queue_handlers/registry.py:173-196,374-442` defaults maintenance registrations to `_verified_reference_handler`. `shared.py:177-206` accepts nonempty reference/hash strings and returns `output_verified=True`, without opening/verifying them or executing repair, retention, reconciliation or evidence generation. This is a documented compatibility bridge, not proof those domain actions are implemented.

**Implementation for Luna:** First mark each registry capability as operational or reference-only and reject newly requested operational maintenance for reference-only adapters with an actionable typed hold. Preserve intentional compatibility reads. Then wire existing canonical orchestrators individually, starting with `artifact_repair` and `public_render_repair`; only enable a queue after its observable domain effect, checkpoint, retry policy and downstream handoff are tested. Do not invent a generic DAG or parallel repair subsystem.

**Success criteria:** Operational repair/maintenance never reports success merely because strings exist. Every enabled adapter performs and verifies its declared effect; unavailable adapters remain explicit, without provider calls or dropped requests.

**Validation:** Extend `tests/test_workflow_queue_registry.py` and `tests/test_workflow_queue_architecture.py` with capability matrix, missing/corrupt artifact and real local repair fixtures. Run both plus `tests/test_workflow_queue_service.py`; run lineage/minimum-execution tests for repair adapters. Update the canonical asynchronous-queue documentation after capability changes.

**Luna implementation prompt — SYS-03 (copy/paste)**

```text
Implement SYS-03 — Give maintenance queues explicit capability semantics before enabling them.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice SYS-03.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="sys-04"></a>
#### SYS-04 — Hash and identify each stage's actual output, rather than reuse the source PDF hash

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority:** P1. **Effort:** M. **Depends on:** SYS-03 for maintenance semantics. **Backlog:** A21/E13/R2.

**Evidence / diagnosis (confirmed):** `_workflow_queue_handlers/report_pipeline.py:593-605` returns an HTML output reference when present, but `output_content_hash=source_hash`, the original PDF hash. Before render, output reference likewise points to the source rather than the stage checkpoint. `complete_workflow_job` persists this pair as stage output and attempt evidence (`services/_workflow_queue_service/completion.py:74-208`). It cannot truthfully prove the referenced stage artifact's bytes or distinguish two renders of one PDF.

**Implementation for Luna:** Define stage-specific output reference/hash semantics using existing checkpoint manifests and artifact lineage. Source ingest may identify its prepared checkpoint; selection/analysis identify their manifests; render identifies HTML/package checksum. Keep source hash in its existing input/provenance field. Verify each hash through the file/artifact service before success and migrate legacy evidence explicitly; do not compare unlike MD5/SHA-256 formats.

**Success criteria:** All newly succeeded report stages have a reference whose stored digest matches the declared output type. Changing HTML or a selected crop changes the relevant output digest while source identity remains constant; tampering blocks completion/resume.

**Validation:** Extend `tests/test_report_queue_publication.py`, `tests/test_validation_queue_lineage.py`, `tests/test_report_checkpoint_lineage_validation.py` with unchanged-PDF/changed-output and tampering cases. Run these suites plus `tests/test_workflow_queue_service.py`; check contract schemas and retained evidence exports.

**Luna implementation prompt — SYS-04 (copy/paste)**

```text
Implement SYS-04 — Hash and identify each stage's actual output, rather than reuse the source PDF hash.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice SYS-04.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="sys-05"></a>
#### SYS-05 — Prove crash convergence between domain persistence and queue completion

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority:** P1. **Effort:** M. **Depends on:** SYS-04, CODE idempotency fixes. **Backlog:** A21/R7. **Diagnosis:** integration-risk hypothesis, not a claim the existing queue outbox is non-atomic.

**Evidence:** `complete_workflow_job` atomically commits job success and child outbox within the state database. However, verified handoff writes source observations/report metadata in the reports database before that queue commit (`acquisition_ingest_handoff_orchestrator.py:108-135,190-242`); report processing writes files/checkpoints and analytics to other stores before returning. These boundaries cannot share the current state-db transaction. Existing idempotency/checkpoints mitigate replay; comprehensive crash convergence must be demonstrated rather than assumed.

**Implementation for Luna:** Build a local fault-injection matrix around the real graph: after retained file write, source identity upsert, checkpoint promotion, domain side effect, before success commit, and before/after outbox materialization. First reproduce divergence; fix only failing seams with existing stable domain keys, verified readback and retained completion receipts. Do not add distributed transactions or a second ledger unless a reproduced gap requires it.

**Success criteria:** Each tested crash followed by restart converges to one effective domain result and one effective downstream job, with compatible lineage and no duplicate external effect. Invalid/incomplete writes are held, never treated as reusable.

**Validation:** Extend `tests/test_acquisition_ingest_handoff_orchestrator.py`, `tests/test_workflow_queue_service.py`, `tests/test_validation_queue_lineage.py`; use subprocess termination or injected public service boundaries with temporary SQLite and files. Run the deterministic full-graph lane described by A21; no live publication is needed.

**Luna implementation prompt — SYS-05 (copy/paste)**

```text
Implement SYS-05 — Prove crash convergence between domain persistence and queue completion.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice SYS-05.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="sys-06"></a>
#### SYS-06 — Add cooperative stop checks for already-running expensive work

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority:** P1. **Effort:** M. **Depends on:** SYS-02. **Backlog:** A21/A15. **Diagnosis:** observed capability gap, not an assertion that pause currently promises cancellation.

**Evidence:** `services/_workflow_queue_service/completion.py:308-350` permits cancellation only for pending/retry-wait jobs. Queue controls prevent new claims, but `workflow_worker_orchestrator.py:87-114` proceeds through a synchronous handler without checking a later emergency stop. A running analysis/browser job can continue incurring cost after the operator stops intake.

**Implementation for Luna:** Preserve existing pause/drain semantics. Add a distinct durable stop-request control for active work and a bounded check at existing stage/provider/side-effect boundaries. Complete any in-flight atomic write safely; retain resumable checkpoints and typed stopped outcome. Keep polling outside pure helpers and separate this control from publication approval. Wire the stop signal through existing orchestrator dependencies, not global monkeypatches.

**Success criteria:** After a stop is observed, zero new external calls or downstream jobs are started; already in-flight work is accounted for. Stop/restart preserves compatible checkpoints and cannot duplicate writes. Pause continues to mean intake pause unless explicitly requesting stop.

**Validation:** Extend `tests/test_workflow_queue_worker_failures.py` and `tests/test_workflow_control_supervisor.py` with controlled handlers whose public boundary records calls. Request stop after one stage/call, assert the second never starts, then resume safely. Include stop during checkpoint commit and publication preflight; run existing report lineage and publish queue tests.

**Luna implementation prompt — SYS-06 (copy/paste)**

```text
Implement SYS-06 — Add cooperative stop checks for already-running expensive work.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice SYS-06.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="sys-08"></a>
#### SYS-08 — Reconcile retained artifact integrity as well as queue row existence

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority:** P1. **Effort:** M. **Depends on:** SYS-04/05. **Backlog:** A21/R7. **Diagnosis:** confirmed reconciliation coverage gap, not a claim every completed artifact is broken.

**Evidence:** `services/_workflow_queue_service/health.py:273-314` repairs materialized-outbox rows whose job is missing and reports succeeded jobs with empty output references. A nonempty path with deleted/modified bytes is not checked. Resume lineage validation can fail later, but the queue health surface can remain green while its retained output is unusable.

**Implementation for Luna:** Add a bounded integrity-check pass through existing artifact/file services for succeeded jobs' canonical output references/digests and required artifacts. Distinguish unavailable storage from missing/corrupt output. Record a typed anomaly and reuse the minimum-regeneration/remediation pathway; do not mutate historical success, silently regenerate or contact providers during health reads. Bound work by count/cursor and check one shared artifact only once per pass.

**Success criteria:** Deleted/tampered completed outputs are detected in the next selected integrity pass; intact outputs produce no remediation. A corrupt render plans render/readiness repair only, preserving source/evidence and publication approval invalidation. Health reads make zero provider or WordPress calls.

**Validation:** Extend `tests/test_workflow_queue_service.py`, `tests/test_workflow_queue_evidence.py` and `tests/test_minimal_execution_enforcement.py` with deleted HTML, changed manifest, inaccessible storage and shared artifact cases. Assert bounded reads and smallest valid repair plan; run all three suites.

**Luna implementation prompt — SYS-08 (copy/paste)**

```text
Implement SYS-08 — Reconcile retained artifact integrity as well as queue row existence.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice SYS-08.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="sys-09"></a>
#### SYS-09 — Make reliability exports tell the same truth as authoritative terminal results

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority:** P1. **Effort:** S. **Depends on:** none. **Backlog:** A21/R1. **Diagnosis:** confirmed reporting defect.

**Evidence:** `scripts/quality/export_reliability_run_evidence.py:397-431` reads authoritative terminal results but still hardcodes `audit_findings.status="failed_reliability_targets"` and says success thresholds were not met. The older export path repeats the literal near line 707. `docs/quality/remaining-four-finalization-20261003/README.md` explicitly acknowledges that 4/4 readiness passed while the exporter retained that failure label. This makes downstream dashboards/release interpretation misleading.

**Implementation for Luna:** Derive disposition from immutable cohort outcomes plus explicit target/phase definitions. Separate readiness passed, SLO failed, publication not attempted and publication unavailable; absence of approved publishing cannot imply readiness failure. If no threshold is retained, label threshold evaluation unavailable rather than invent it. Generate audit sentences from the same projection used for CSV/funnel views and preserve prior evidence as historical.

**Success criteria:** All-pass, partial-fail, missing-threshold and no-publish exports have consistent machine fields and prose. `awaiting_review` is readiness success with human review pending; it is never counted as a completed live publication. Existing evidence files are not rewritten without deliberate regeneration.

**Validation:** Extend `tests/test_export_reliability_run_evidence.py` with all four dispositions and contradiction assertions. Run `python -m pytest -q tests/test_export_reliability_run_evidence.py tests/test_workflow_queue_evidence.py`; project a copied retained 4-report result into temporary output and compare counts with its authoritative JSON.

**Luna implementation prompt — SYS-09 (copy/paste)**

```text
Implement SYS-09 — Make reliability exports tell the same truth as authoritative terminal results.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice SYS-09.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="sys-10"></a>
#### SYS-10 — Treat downstream capacity as durable backpressure, not spent execution attempts

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority:** P1. **Effort:** M. **Depends on:** CODE-03 outbox recovery. **Backlog:** A21/A15. **Diagnosis:** confirmed policy gap; frequency requires measurement.

**Evidence:** `services/_workflow_queue_service/submission.py:119-135` correctly rejects a full queue with retryable `workflow_queue_at_capacity`. `outbox.py:97-115` counts every such materialization failure against the same finite outbox attempt limit and can dead-letter it. Thus a correctly completed upstream stage can lose automatic downstream progress merely because the next queue stays full; no domain work failed. Existing per-queue caps should remain.

**Implementation for Luna:** Classify capacity exhaustion as a bounded deferral with retained event identity, age/deadline and next eligible time. Do not spend domain failure attempts while no job or side effect starts. Surface old/exhausted deferrals as operator-held with exact reason; add queue-pressure summary to existing health. Optionally stop new upstream dispatch when downstream saturation is established, using the existing fixed graph, not an adaptive scheduler.

**Success criteria:** Filling a downstream queue across more than the ordinary retry count then draining it yields exactly one child automatically. Capacity limits are never exceeded; expired deferral is visible and recoverable; malformed submissions still consume/fail normal attempts. No infinite busy retry loop.

**Validation:** Extend `tests/test_workflow_queue_service.py`, `tests/test_workflow_queue_evidence.py`, `tests/test_workflow_supervisor_orchestrator.py` with temporary queues at capacity, advanced clock, draining, duplicate materialization, malformed payload and deadline cases. Run these suites and verify backlog/health counts reconcile to the retained outbox.

**Luna implementation prompt — SYS-10 (copy/paste)**

```text
Implement SYS-10 — Treat downstream capacity as durable backpressure, not spent execution attempts.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice SYS-10.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="code-01"></a>
#### CODE-01 — Make explicit requeue grant a real, bounded recovery attempt

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

- **Status/evidence:** Confirmed and locally reproduced. `src/services/_workflow_queue_service/completion.py:351–394`, `requeue_workflow_job`, sets an exhausted dead-letter job back to `pending` without changing its attempt allowance. `leasing.py:201–205`, `claim_next_workflow_job`, excludes `attempt_count >= max_attempts`. A one-attempt job failed, was explicitly requeued, and remained `pending, attempt_count=1, max_attempts=1`; the next claim returned `None`. The existing test named `test_retry_budget_defer_cancel_and_explicit_requeue` does not actually exercise exhausted explicit requeue.
- **Trigger/impact:** An operator repairs the underlying failure and requeues exhausted work. The UI/CLI reports recovery but the job can never run, leaving acquisitions, ingest, or publication preparation indefinitely stuck.
- **Luna implementation:** Amend only the canonical requeue service and its CLI contract as necessary. Preserve lifetime attempt history; on an explicit authorized requeue grant one bounded additional attempt by advancing the allowance to at least `attempt_count + 1`. Record the granted allowance in the existing transition details. Do not reset attempt numbers, delete audit rows, or allow automatic infinite retries.
- **Success criteria:** Every valid explicit requeue is claimable once; after another failure it returns to an appropriate bounded terminal state. Old attempt history remains unchanged and new attempt numbers stay unique.
- **Validation:** Add a service-level real-SQLite test covering `max_attempts=1 -> failure -> requeue -> claim/start -> failure`; also test replay/repeated requeue and an invalid lifecycle state. Run affected worker failure and CLI tests.
- **Priority/effort/dependencies/backlog:** P1 / S / no prerequisite. Concrete regression extension of A21/R3; A10's completed remediation adapters do not establish this queue behavior.

**Luna implementation prompt — CODE-01 (copy/paste)**

```text
Implement CODE-01 — Make explicit requeue grant a real, bounded recovery attempt.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice CODE-01.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="code-02"></a>
#### CODE-02 — Terminalize exhausted crashed jobs instead of creating unclaimable pending work

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

- **Status/evidence:** Confirmed and locally reproduced. `src/services/_workflow_queue_service/leasing.py:134–165`, `release_expired_workflow_leases`, unconditionally sends expired `leased`/`running` jobs to `pending`; the claim filter at lines 201–205 rejects exhausted attempts. Expiring a running job at `attempt_count=max_attempts=1` produced `pending` followed by `claim=None`.
- **Trigger/impact:** A process dies or misses its lease on its final allowed attempt. The job is neither runnable nor truthfully terminal; pending-depth limits and health summaries continue to count dead work. The unfinished attempt audit also lacks a terminal outcome.
- **Luna implementation:** In the same existing reaper transaction, distinguish an expired lease before start from an expired running attempt. Return work to pending only when automatic attempt allowance remains; otherwise set `dead_letter` with a stable exhaustion/lease-expiry reason. Close the corresponding running attempt with its actual lease-expired outcome. Preserve previous external-effect metadata; never infer that an external write did not happen.
- **Success criteria:** After reaping, zero automatic pending jobs have exhausted allowance; final-attempt expiry is terminal and visible; a leased-but-not-started job does not incorrectly consume an attempt.
- **Validation:** Real-SQLite cases for first/final running attempt, leased-before-start, already heartbeated lease, stale completion rejection, and idempotent reaper replay. Run queue health/evidence tests and a local worker crash/restart scenario.
- **Priority/effort/dependencies/backlog:** P1 / S / coordinate with CODE-01 and SYS lease-renewal work, but this is the independent crash fallback. A21/R3 extension, not a claim that A3 is absent.

**Luna implementation prompt — CODE-02 (copy/paste)**

```text
Implement CODE-02 — Terminalize exhausted crashed jobs instead of creating unclaimable pending work.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice CODE-02.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="code-03"></a>
#### CODE-03 — Reclaim expired outbox leases so committed downstream work survives a crash

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

- **Status/evidence:** Confirmed source defect; crash execution not performed. `src/services/_workflow_queue_service/outbox.py:75–91`, `materialize_workflow_outbox`, commits `status='leased'` before enqueueing the child. Its selector accepts only `pending/retry_wait`. `health.py:273–313`, `reconcile_workflow_queue`, repairs materialised events referencing missing jobs but never expired leased events. Repository-wide `workflow_outbox` search found no alternative expired-lease reaper.
- **Trigger/impact:** The process exits after leasing an event, including after creating a child but before acknowledging it. The committed parent stays succeeded while its event is never materialised/reconciled, breaking the pipeline despite transactional outbox intent.
- **Luna implementation:** Extend canonical queue reconciliation to atomically reclaim only expired outbox leases with bounded attempt accounting and a stable reason. Replay the existing enqueue deduplication boundary; if a child already exists, reconcile to that compatible child. Fence acknowledgement by lease generation/owner and check update rowcount so an expired materialiser cannot acknowledge someone else's lease. Do not add a second scheduler.
- **Success criteria:** Both crash windows recover to exactly one effective child; no expired leased event remains stuck; stale materialisers cannot change a renewed event; poison events end in bounded dead-letter state.
- **Validation:** Use subprocess crash tests or controlled persisted-state fixtures at lease-before-enqueue and enqueue-before-ack. Run two materialisers against real SQLite, advance injected public clock input, reconcile, and assert one child plus one final event. Include unexpired lease and malformed submission cases.
- **Priority/effort/dependencies/backlog:** P1 / M / CODE-09 compatibility checks strengthen replay. A21/R3 extension. Cross-store domain/queue atomicity belongs to SYS work; this fix is wholly within the existing outbox state machine.

**Luna implementation prompt — CODE-03 (copy/paste)**

```text
Implement CODE-03 — Reclaim expired outbox leases so committed downstream work survives a crash.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice CODE-03.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="code-06"></a>
#### CODE-06 — Reject foreign-identity and unsupported-schema checksum sidecars

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Status/evidence:** Confirmed and locally reproduced. `src/services/file_cache_service.py:99–164`, `resolve_md5_sidecar`, verifies size/time but never record `file_id` equality. `_record_from_payload:263–289` accepts arbitrary/missing schema versions and substitutes request identity when absent. A sidecar written for `fileA` returned a checksum cache hit for a request for `fileB`. Ingest `_resolve_cache_hit` assigns `sidecar_response.resolved_md5` as runtime source MD5 without hashing on this path.
- **Trigger/impact:** Copied/misassociated sidecars, cache-path reuse, or future incompatible records. Work can inherit another source's hash/provenance or evade actual hashing; that undermines artifact reuse and source identity.
- **Luna implementation:** Require exact normalized file identity and a supported sidecar version before a hit. Treat legacy missing identity/version or unsupported versions as explicit misses requiring the existing actual-file hash path; write back only after successful revalidation. Keep basename/name informational. Make sidecar writes atomic via unique sibling temporary file and replace to avoid partial JSON, using existing file-service conventions where present.
- **Success criteria:** Wrong/missing identity and unknown schemas produce no `resolved_md5`; valid same-identity records preserve hits; fallback recomputes from real bytes and repairs the sidecar.
- **Validation:** Extend `tests/test_file_cache_service.py` with foreign/missing ID and supported/unknown version fixtures; run ingest-file cache integration with real local PDF bytes and controlled boundary services. Assert the expensive path is skipped only for valid records and provenance stays source-bound.
- **Priority/effort/dependencies/backlog:** P1 / S / independent of CODE-07. Concrete integrity extension to completed E7/E8/P11, not a proposal to rebuild identity reuse.

**Luna implementation prompt — CODE-06 (copy/paste)**

```text
Implement CODE-06 — Reject foreign-identity and unsupported-schema checksum sidecars.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice CODE-06.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="code-07"></a>
#### CODE-07 — Stop losing subsecond freshness in the checksum cache

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Status/evidence:** Confirmed and locally reproduced. `src/services/file_cache_service.py:361–367`, `_normalize_mtime`, truncates to integer seconds, also encoded in `src/contracts/file_cache.py`, `FileCacheMd5SidecarRecord.mtime_utc`. Writing four bytes at `mtime=1000.1`, caching their MD5, replacing with different four bytes at `1000.9`, and resolving returned `hit=True` with the wrong hash. Both ingest cache and prefetch trust this sidecar shortcut before hashing.
- **Trigger/impact:** Same-size rapid rewrite/replacement within a second, including retries or concurrent file delivery. The cache can label changed bytes with the old MD5 and incorrectly reuse analysis/artifacts. This is an integrity defect, not just a missed cache optimization.
- **Luna implementation:** Add nanosecond file modification identity to the canonical file stat contract/service and a versioned sidecar format. Optionally include file-generation/inode identity where portable, but do not promise stat alone detects deliberately preserved timestamps. Treat old second-granularity records as one-time misses and recompute hashes. Preserve the existing authoritative Drive checksum comparison; version changes require an adapter/miss policy, not silent reinterpretation.
- **Success criteria:** Same-size changes with distinct observed subsecond mtimes cannot hit; unchanged files hit without full hashing; legacy records safely refresh. When filesystem precision is insufficient, resolve by hash instead of falsely declaring freshness.
- **Validation:** Real-file controlled `os.utime(ns=...)` test, same-size replacement, legacy format miss, unchanged warm replay, and unavailable/coarse stat precision cases. Run ingest-file and prefetch cache tests; assert source hash equals actual bytes after change.
- **Priority/effort/dependencies/backlog:** P1 / M / coordinate version transition with CODE-06. E7/E8/P11 integrity regression; no new hashing algorithm or general cache layer required.

**Luna implementation prompt — CODE-07 (copy/paste)**

```text
Implement CODE-07 — Stop losing subsecond freshness in the checksum cache.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice CODE-07.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="code-08"></a>
#### CODE-08 — Make idempotency checksum validation atomic with the upsert

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Status/evidence:** Source-grounded concurrency risk, not locally reproduced. `src/services/idempotency_service.py:257–311`, `record_outcome`, performs checksum SELECT before any `BEGIN IMMEDIATE`, then its upsert unconditionally updates `input_checksum` and outcome. `_conn` commits setup before yielding. Two writers can both observe an absent row; the later upsert can overwrite the first with a different checksum, bypassing the sequential mismatch guard already tested in `tests/test_idempotency_service.py`.
- **Trigger/impact:** Concurrent callers record the same logical key with different input hashes. A durable completed effect may be rebound to incompatible inputs, defeating the central publication/acquisition/discovery duplicate-side-effect safety assumption.
- **Luna implementation:** Place read, mismatch validation, and write inside a single immediate transaction, or use an equivalent conditional write plus readback with stable typed mismatch handling. Never overwrite another input checksum. Preserve valid same-checksum update behavior only where the public contract intentionally permits it; do not add service-owned workflow retries.
- **Success criteria:** Concurrent conflicting submissions produce one persisted checksum and a typed mismatch for the incompatible writer; no successful return claims a checksum different from its stored record. Compatible replay retains existing behavior.
- **Validation:** Real SQLite multiprocess/thread contention with barriers at public entry, incompatible and compatible payloads, database-busy errors, and sequential mismatch tests. Repeat enough to exercise scheduling, checking stored data and outcomes. A service-level proof does not establish exactly-once external writes; existing publish/readback tests remain required downstream.
- **Priority/effort/dependencies/backlog:** P1 / S / no prerequisite. R3/A21 extension, complements SYS cross-store convergence rather than duplicating it.

**Luna implementation prompt — CODE-08 (copy/paste)**

```text
Implement CODE-08 — Make idempotency checksum validation atomic with the upsert.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice CODE-08.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="code-09"></a>
#### CODE-09 — Reject queue deduplication keys reused for incompatible jobs

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

- **Status/evidence:** Confirmed and locally reproduced. `src/services/_workflow_queue_service/submission.py:108–117`, `enqueue_workflow_job`, returns the existing job on `(deduplication_scope,idempotency_key)` without comparing queue, job type, input hash, policy/processing version, or typed payload. Same key/scope with a different `input_content_hash` returned `created=False` and the original hash. The uniqueness domain can also span queue names; it is not a validated compatibility contract.
- **Trigger/impact:** Key construction error or policy/input change accidentally reuses a logical key. Required new work is silently suppressed, or a downstream outbox links to an unrelated prior job. It can look like successful reuse while preserving stale analysis.
- **Luna implementation:** Define a small canonical semantic compatibility comparison for existing/new submissions: queue and job type/version, normalized payload/input identity, processing/prompt policy, immutable artifact refs, and entity identity. Return reuse only if compatible; otherwise raise a stable nonretryable idempotency-conflict AppError with bounded hashes/field names. Exclude scheduling metadata such as availability/priority from semantic equality where intentionally mutable. Audit outbox acknowledgment so conflicts never masquerade as materialised success.
- **Success criteria:** Compatible duplicate submissions still create exactly one effective job; differing semantic inputs cannot return a successful reuse. No external calls occur to diagnose a conflict.
- **Validation:** Real-SQLite same/different hash, queue/type, policy version, artifact refs, and concurrent submissions; outbox conflict becomes typed terminal error. Run queue config-isolation, registry, and workflow handoff tests.
- **Priority/effort/dependencies/backlog:** P1 / M / helps CODE-03 recovery. Specific R3/A21 correctness fix; SYS-05 tests cross-store crash convergence, while this enforces the concrete queue compatibility invariant.

**Luna implementation prompt — CODE-09 (copy/paste)**

```text
Implement CODE-09 — Reject queue deduplication keys reused for incompatible jobs.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice CODE-09.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="art-01"></a>
#### ART-01 — Retain completed artifact families before a later family fails

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1 / M, three slices / none; complementary to ING-07, which owns dispatch cancellation. **Backlog:** A21/E9 extension; successful checkpoint reuse remains implemented.

**Evidence / diagnosis:** `src/generators/_artifact_generator/generation.py:687–706` retains individual model outputs only in local `family_outputs`; `:1165–1216` stores them inside the final assembled artifact pack after cover and distribution work finish. `src/orchestrators/_report_generation_orchestrator/checkpoints.py:371–403,722–740` materializes artifact families at analysis/render-complete checkpoints. **Confirmed narrower gap:** an exception before assembly/checkpoint prevents those newly completed artifact outputs from entering this reuse path. Previously retained families can still be reused; actual repeated-call cost is unmeasured.

**Luna implementation:** (1) Add a failure-after-summary/quotes fixture through the real generator with only model/store boundaries faked. (2) Stage each schema/reference-valid output through existing retained storage with exact producing identity, input hash and verified dependency hashes. Keep raw family output separate from transformed public output; retain private soft-copy bindings. (3) Give staged results an explicit unpromoted status: they cannot masquerade as `validation_status=pass`, public acceptance or canonical reusable proof. Resume may load the staged candidate to avoid another generation call, but must run the normal final transforms, grounding/semantic gates and promotion before the ordinary reuse reader can accept it. Version/adapt contracts where necessary; do not weaken their pass requirement. Orchestrators own recovery; no new ledger or private retry loop.

**Success criteria:** Failure in the final distribution family followed by replay makes zero calls for earlier compatible, validated families; missing/changed/corrupt dependency or incomplete binding prevents reuse. Overall report still requires normal validation/readiness. Failed writes never become reusable.

**Validation:** `python -m pytest -q tests/test_artifact_generator.py tests/test_prompt_family_materialization.py tests/test_prompt_family_minimal_execution.py tests/test_report_checkpoint_lineage_validation.py`; add interrupted-write, late-failure, changed-input and invalid-soft-copy cases with temporary stores. Replay canonical analysis→validation→render after recovery; report exact avoided calls including failed first-run calls.

**Luna implementation prompt — ART-01 (copy/paste)**

```text
Implement ART-01 — Retain completed artifact families before a later family fails.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ART-01.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="art-02"></a>
#### ART-02 — Make editorial-plan reuse real, with complete family registration

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

**Priority / effort / dependencies:** P1 / S–M / none; ART-01 for failure-before-checkpoint reuse. **Backlog:** targeted E9/A21 correction, not a claim E9's implemented families lack reuse.

**Evidence / diagnosis:** `src/generators/_artifact_generator/generation.py:116–127,842–851` declares `report_vs/artifacts/editorial_plan` and resolves it through the same pre-call reuse reader as other families. However, `src/orchestrators/_report_generation_orchestrator/checkpoints.py:722–976`, `_record_prompt_family_materializations()`, persists summary, candidate/final insights, quotations, cover and distribution outputs but never the editorial-plan family. **Confirmed registration omission:** the successful checkpoint path cannot create the plan materialization that its later reader requests. An unchanged composite artifact-cache hit can still avoid all generation, so the practical effect is specifically composite misses and minimum regeneration.

**Luna implementation:** (1) Register the producing plan output and identity through the existing materializer with verified DocMap/evidence dependencies. Specify whether the reusable value is raw normalized plan or the deterministically stabilized plan, and preserve a separate versioned transformation identity; do not falsely assign model provenance to later deterministic additions. (2) Add the plan to existing family dependency/compatibility mappings where it actually feeds summary, candidates, final insights and distribution. (3) Add a bounded parity test over declared generation roots, persisted family roots and planner dependencies to catch another missing family; do not introduce a general plugin registry.

**Success criteria:** A successful cold run followed by an incompatible composite-cache but identical plan-input replay makes zero editorial-plan model calls. Changed plan prompt/evidence invalidates the plan and its genuine dependents only; unrelated quotations remain reusable. Every declared reusable production family has an exercised producer/readback path.

**Validation:** `python -m pytest -q tests/test_artifact_generator.py tests/test_prompt_family_materialization.py tests/test_prompt_family_minimal_execution.py tests/test_report_artifact_registry.py`; new plan-only warm replay, stabilization-version change and prompt-change fixtures. Validate downstream theme identity/coverage, not merely a stored filename.

**Luna implementation prompt — ART-02 (copy/paste)**

```text
Implement ART-02 — Make editorial-plan reuse real, with complete family registration.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ART-02.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="art-03"></a>
#### ART-03 — Send each artifact family only its required evidence context

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1 / M, three slices / ART-02 for dependency-parity coverage. **Backlog:** E9/A21 efficiency extension; existing October retrieval savings remain intact.

**Evidence / diagnosis:** `src/generators/artifact_normalization.py:133–150`, `artifact_base_variables()`, serializes the complete DocMap and evidence packs. `src/generators/_artifact_generator/generation.py:870–900,986–1023` spreads that payload into quotes, candidates, final insights and cover semantics. Quotations prompt `src/prompts/report_vs/artifacts/quotes/user.yaml:3–24` requires copying retained candidates exactly, yet also receives all packs. Cover semantics receives full packs plus summary and insights. `generation.py:485–505` hashes all supplied variables, so unrelated input changes can also defeat family reuse. **Confirmed broad input scope; hypothesis:** narrower sufficient context reduces tokens, distraction and avoidable cache misses without lowering quality.

**Luna implementation:** Freeze per-family input/usage and output baselines first. Add deterministic generator-owned projections with explicit source identity, approved evidence IDs/spans, necessary methods/limitations and relevant editorial themes. Start with quotes and cover, then final insights; leave evidence-sensitive summary/Expert View unchanged unless equivalence is demonstrated. Prompt service still renders/hashes resources; new projections carry a version in relevant-input identity. Do not silently truncate evidence or drop counter-signals to satisfy a token target. A projection lacking required context must use the current bounded full-context path or hold explicitly.

**Success criteria:** Quotes/cover median estimated prompt tokens decrease at least 25% on the same frozen cohort, with zero lost selected evidence/qualifiers and no higher repair or abstention rate. Irrelevant pack change preserves eligible reuse; any relevant source change invalidates it. Report actual calls/cost separately from token estimates.

**Validation:** `python -m pytest -q tests/test_artifact_generator.py tests/test_artifact_evidence_binding.py tests/test_prompt_fixture_corpus_regression.py tests/test_prompt_family_minimal_execution.py`; add irrelevant-versus-relevant pack-change and long-report projection fixtures. Run the canonical prompt fixture gate and retained analysis→render lane; semantic-quality promotion needs bounded model evaluation plus P6 review, not fixture output equality alone.

**Luna implementation prompt — ART-03 (copy/paste)**

```text
Implement ART-03 — Send each artifact family only its required evidence context.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ART-03.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="art-04"></a>
#### ART-04 — Apply upstream family policy before producing dependent public copy

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1 / M / none; ART-01 preserves valid earlier work. **Backlog:** A21/E13 generation sequencing subtask; no duplicate of ING-07 scheduler cancellation.

**Evidence / diagnosis:** `src/generators/_artifact_generator/generation.py:1010–1036` creates cover semantics; `:1106–1141` then produces Expert View and LinkedIn copy. Only afterwards, `:1148–1163`, `apply_artifact_family_policy()` can replace weak summary/insights/quotes with empty values. The policy is implemented in `src/generators/_artifact_generator/family_policy.py:28–97,196–282`. **Confirmed ordering:** dependent generation can consume families that the final policy later rejects. Assembly and verification still protect public output; it is not evidence that invalid copy currently publishes. Avoidable calls and downstream abstention rates require measurement.

**Luna implementation:** Separate deterministic upstream-status evaluation from final distribution status. Apply summary/insight/quote policy after binding and source-display correction, before constructing downstream context. If a required premise family is rejected, record an explicit dependency hold or supported abstention and leave its existing orchestrator-owned repair route intact. Generate distribution only when its actual retained premises meet eligibility; a genuinely optional quote is not a universal prerequisite. Derive cover from approved source context or defer it when no grounded basis exists. Preserve distinct generation and public-validation identities.

**Success criteria:** No dependent prompt contains an upstream family that final assembly has deterministically abstained. Weak required-insight fixtures make zero Expert/LinkedIn calls until repaired; strong quote-less reports retain supported distribution. Successful supported reports keep equivalent factual coverage and no increased calls.

**Validation:** `python -m pytest -q tests/test_artifact_generator.py tests/test_report_analysis_generator.py tests/test_report_analysis_orchestrator_decomposition.py tests/test_soft_copy_finalization.py`; add weak-summary, insufficient-insights, optional-quotes-absent and successful-repair fixtures through public model boundaries. Assert call order/count and eventual readiness; do not merely inspect helper return values.

**Luna implementation prompt — ART-04 (copy/paste)**

```text
Implement ART-04 — Apply upstream family policy before producing dependent public copy.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ART-04.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="art-05"></a>
#### ART-05 — Use a deterministic quotation fast path where semantic selection is unnecessary

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1 / S–M / none; GRD-08 before promoting attribution-sensitive quotes. **Backlog:** E9/A21 narrow optimization; grounding owns verbatim/speaker proof.

**Evidence / diagnosis:** `src/generators/_artifact_generator/generation.py:865,891–898` always adds the quote model task; `:968–982` already falls back to retained candidates if output is empty. `src/prompts/report_vs/artifacts/quotes/user.yaml` instructs exact copying of up to three complete candidates, with no rewriting. `src/generators/artifact_normalization.py:2185–2235` provides a deterministic retained-candidate fallback. **Confirmed redundant opportunity:** candidate-empty and uniquely eligible small pools can enter a model call whose permitted output is already tightly constrained. It is not established that every candidate can be ranked safely without semantic judgment.

**Luna implementation:** Determine authoritative candidate-pack completeness/status first; missing/failed extraction is not proof that a report has no quotations. For a complete empty pool record supported `not_found`/abstention. For at most three distinct candidates passing the canonical quote/source/attribution checks, copy them deterministically in retained order. Preserve exact text, ID and location; never infer a speaker. Use the current semantic family only when a larger or genuinely ambiguous pool needs relevance selection. Persist a deterministic producer/version and its dependencies rather than inventing a model prompt identity. Keep caller/readiness adapters explicit.

**Success criteria:** Complete-empty and uniquely eligible ≤3-candidate fixtures make zero quote model calls, while approved final text/ID/location exactly match source candidates. Failed/incomplete pool holds visibly; conflicting attribution cannot enter the fast path. Genuine selection cases stay bounded and quality-equivalent.

**Validation:** `python -m pytest -q tests/test_artifact_generator.py tests/test_artifact_normalization.py tests/test_report_analysis_generator.py tests/test_prompt_family_minimal_execution.py`; add empty-complete versus missing pack, one/three/four candidates, duplicate quote and ambiguous-speaker fixtures. Validate quote-less downstream render and GRD-08 source-attribution tests before promotion.

**Luna implementation prompt — ART-05 (copy/paste)**

```text
Implement ART-05 — Use a deterministic quotation fast path where semantic selection is unnecessary.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ART-05.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ana-02"></a>
#### ANA-02 — Separate successful persistence from usable analytical coverage

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1; M, three slices; none; consume GRD-10 eligibility results when available. **Owner/backlog:** projection completeness contract and cross-report input readiness; extension beneath A21, not a replacement for SYS-09 reliability exports or source-validation gates.

**Evidence and impact:** `src/generators/_analytics_projection/workflow.py:58–76,99–129` defaults missing evidence/artifact families to empty maps/lists. Builders skip non-object rows (`builders.py:38–40,83–85,126–128,233–235`). `src/services/_analytics_store/projection_write.py:783–790` nevertheless returns `projected`; cross-report readiness checks only that status (`source_selection.py:113–119`). **Confirmed:** `projected` means persistence succeeded, not that required analytical evidence is present or that dropped rows were deliberate. Empty quotes or metrics can be legitimate; do not impose arbitrary minimum counts or call this a reproduced production corruption.

**Luna implementation:** (1) Derive a compact versioned coverage result from the authoritative analysis families: present/absent/not-applicable, approved input count, projected count, intentional omission count and typed invalid-row reason. Do not duplicate full evidence or logs. (2) Persist coverage atomically with existing projections; retain `projected` as persistence status and add a distinct analytical-eligibility decision. (3) Make source selection require eligible evidence for the requested classes; diagnostic reads expose deficiencies without promoting them. Invalid expected rows fail with typed errors; genuinely not-applicable families remain permissible.

**Success criteria:** Every omitted expected row has a stable reason; 100% of malformed/absent required-family fixtures are ineligible, while all labelled legitimate-empty cases remain usable. Reprojecting an incomplete newer analysis cannot silently replace usable evidence with an apparently complete empty set. No added LLM calls.

**Validation:** Extend `tests/test_analytics_projection_foundation.py`, `tests/integration/test_analytics_store_cross_report_reads.py` and `tests/test_cross_report_analysis_input_generator.py`; run those three files with `python -m pytest -q`. Fixtures distinguish no quotes, intentionally excluded quotes, missing summary, malformed finding and unsupported legacy coverage. Validate canonical projection→source-selection state transitions in a temporary store.

**Luna implementation prompt — ANA-02 (copy/paste)**

```text
Implement ANA-02 — Separate successful persistence from usable analytical coverage.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ANA-02.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ana-07"></a>
#### ANA-07 — Require item-level support before counting a Signal's evidence

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1; M, three slices; ANA-06; ANA-04 optional. **Owner/backlog:** Signal evidence matching/scoring; extends existing extraction beneath A21, not a new taxonomy or audience feature.

**Evidence and impact:** `_evidence_matches_signal()` in `src/generators/_cross_report_analysis_input/evidence_signals.py:386–407` returns true when the report's taxonomy contains the signal label, even if the item's text does not. Signal scoring then counts all those items as recurrence and supporting sources (`520–563`). Thus a broadly tagged report can make unrelated evidence appear to support every inherited tag. Separately, `_topic_terms()` sorts tokens (`shared.py:63–69`), while the multiword regex uses that sorted order (`397–404`), missing differently ordered phrases before falling back to report metadata. **Confirmed mechanisms; measured false-support rate unknown.**

**Luna implementation:** (1) Separate candidate-report eligibility from item relevance: inherited tags may admit a report, never prove an individual evidence item supports a proposition. (2) Use deterministic item/topic/entity matching preserving phrase order, with bounded existing semantic relevance only when justified; return matched/uncertain/unrelated with reasons. (3) Compute recurrence/support/source diversity only from matched evidence and abstain or label weak coverage when insufficient. Retain uncertain items for diagnostics, not confident candidate evidence; leave final grounding/publication gates intact.

**Success criteria:** On 50 labelled item/signal pairs, unrelated inherited-tag items contribute zero support; item-match precision reaches at least 95% with recall at least 90%. Multiword/reordered paraphrase fixtures preserve relevant matches. Increasing unrelated items in an eligible report cannot increase signal confidence or recurrence. Pure deterministic matching makes zero provider calls.

**Validation:** `python -m pytest -q tests/test_cross_report_analysis_input_generator.py tests/test_signal_candidate_generator.py tests/test_signal_candidate_orchestrator.py`. Fixtures include a five-topic report with one relevant finding, literal multiword phrases, synonyms, title-only matches and no item-level support; replay canonical extraction and compare exact supporting evidence IDs plus labelled precision/recall.

**Luna implementation prompt — ANA-07 (copy/paste)**

```text
Implement ANA-07 — Require item-level support before counting a Signal's evidence.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ANA-07.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="grd-01"></a>
#### GRD-01 — Make the report evidence registry collision-safe

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies / owner:** P0 / M, two slices / none / evidence-pack and claim-provenance contracts. **Backlog:** concrete A21 source-integrity subtask; strengthens closed A9/E9 without declaring their identity/reuse mechanisms absent. This is evidence-input identity, not VER's semantic verdict-ID completeness.

**Evidence and impact:** `src/generators/claim_validation_generator.py:176–212`, `_evidence_index()`, walks all list-valued pack fields and writes a plain `indexed[evidence_id]` entry. Conflicting IDs overwrite silently. `src/generators/validation/evidence.py:55–59,68–73` likewise replaces mappings. **Confirmed and locally reproduced:** findings and quote candidates sharing `same` resolve to the latter pack; `validate_retained_claims()` reports the quote-supported assertion supported. That is not proof final publication accepts it, but the canonical support binding is ambiguous before downstream checks.

**Luna implementation:** (1) Introduce one deterministic registry builder keyed by report/source identity, evidence family and local ID; retain explicit compatibility aliases only when unique. Detect conflicting duplicate text/pages/pack owners before constructing claim references. Exact identical repeats may deduplicate with preserved aliases. (2) Route generation, soft-copy bindings and validation through that registry, with a versioned persisted-reference adapter. Ambiguous legacy references must hold/regenerate the affected artifact, never choose alphabetical pack order. Keep current semantic batching/reuse.

**Success criteria:** Every accepted reference resolves to exactly one approved record; duplicate conflicting IDs yield a typed integrity failure before provider calls. Reordering packs does not change support ownership, hashes or outputs. Unique existing references remain compatible through the declared adapter.

**Validation:** Extend `tests/test_artifact_evidence_binding.py`, `tests/test_claim_validation_generator.py` and `tests/test_soft_copy_claim_provenance.py`; run all three. Add cross-pack identical-ID/different-text, different-page, case-alias collision, same-record duplicate and reordered-pack fixtures. Exercise public generation-to-retained-claim bindings with recorded model boundaries; assert the selected source family and text hash, not only a passed disposition.

**Luna implementation prompt — GRD-01 (copy/paste)**

```text
Implement GRD-01 — Make the report evidence registry collision-safe.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice GRD-01.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="grd-02"></a>
#### GRD-02 — Separate authoritative source support from generated navigation context

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies / owner:** P0 / M, three slices / GRD-01 / validation evidence preparation. **Backlog:** A21 source-fidelity extension and E16 source-backed facts. Not a request to remove already implemented File Search reuse or create another retrieval service.

**Evidence and impact:** `src/generators/validation/evidence.py:61–143`, `collect_evidence_texts()`, collects artifact evidence, generated DocMap summaries/key points and generated finding text alongside PDF text. `src/generators/validation/preparation.py:42–50` turns that mixed collection into support windows. `src/generators/claim_validation_generator.py:190–203` also merges assertion and evidence fields. **Confirmed:** a derived invented assertion enters the local support corpus; whether any particular full pipeline incorrectly accepts it is unmeasured. The separate evidence-fidelity stage already filters findings/quotes, but DocMap/navigation context must not become independent proof of its own assertion.

**Luna implementation:** (1) Tag retained support records as authoritative source spans, fidelity-approved derived summaries with source roots, or navigation-only context. (2) Build factual support windows from source spans/approved rooted records only; DocMap remains useful for locating sections, not a substitute for missing source evidence. Preserve source/page/span identity through windowing and constrain neighbor expansion to the same source sequence rather than adjacent unrelated generated texts. (3) Bind support roots into existing evidence hashes; incompatible legacy windows become a bounded miss, not a blanket fresh retrieval.

**Success criteria:** Copying a claim into artifacts/DocMap cannot create new factual support. Every factual window has an inspectable source root and hash. Valid source paraphrases remain evaluable; unavailable authoritative support stays unknown/held, never silently supported. Identical approved inputs retain existing zero-provider reuse.

**Validation:** Run `python -m pytest -q tests/test_validation_evidence_retrieval.py tests/test_validation_doc_map_evidence.py tests/test_retained_claim_grounding.py`. Add self-echo, conflicting source, navigation-only, neighboring unrelated text and valid exact-source fixtures; replay canonical evidence preparation→grounding with recorded results and inspect actual evidence submitted at the public model boundary.

**Luna implementation prompt — GRD-02 (copy/paste)**

```text
Implement GRD-02 — Separate authoritative source support from generated navigation context.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice GRD-02.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="grd-03"></a>
#### GRD-03 — Preserve complete page sets and explicit page-number semantics

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies / owner:** P1 / M, three slices / GRD-01; ING-06 protects upstream cached pages / claim evidence references. **Backlog:** A9/A21 provenance extension; not another OCR/cache repair.

**Evidence and impact:** Findings retain plural `pages` in `src/generators/evidence_packs/findings_strategy.py:48–59`, but `src/generators/claim_validation_generator.py:205–211`, `_evidence_index()`, only reads singular `page`. Quote normalization keeps `pages[0]` at `src/generators/evidence_packs/quote_candidates_strategy.py:51–70`. `_source_page_for_reference()` at claim-validation lines 836–879 treats DocMap pages as printed labels and other pages as physical numbers, using inferred header/footer text for DocMap resolution. **Confirmed lossy representation/implicit convention:** downstream source binding may lack the full evidence page set. Existing exact-page hashing and printed-to-physical resolution are real; their extension is required, not replacement by blind PDF indexing.

**Luna implementation:** (1) Version references to retain ordered source span/page sets with declared `physical_pdf` versus `printed_label` semantics. (2) Resolve printed labels once into an explicit unique mapping tied to the original source identity, preserving both coordinates; unknown/ambiguous labels remain unresolved. Carry findings' plural pages and multi-page quotes through normalization, soft-copy and semantic evidence assembly. (3) Add a legacy adapter using existing conventions only when provably unambiguous; retain an unavailable-provenance state otherwise. Do not change crop zero-based coordinates silently.

**Success criteria:** Two-page findings/quotes retain both physical page roots and corresponding printed labels through persistence/replay. Front matter offsets, missing printed labels and duplicate labels cannot bind to a guessed page. Page-source changes invalidate affected evidence identities without forcing unrelated model regeneration.

**Validation:** Run `python -m pytest -q tests/test_claim_validation_source_pages.py tests/test_evidence_pack_generator.py tests/test_soft_copy_claim_provenance.py`; add physical 44/printed 42, duplicate printed 42, Roman front matter, two-page quote and legacy singular/plural fixtures. Canonical analysis→claim-package replay must prove unchanged source/page roots reach downstream rendered citations.

**Luna implementation prompt — GRD-03 (copy/paste)**

```text
Implement GRD-03 — Preserve complete page sets and explicit page-number semantics.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice GRD-03.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="grd-04"></a>
#### GRD-04 — Treat ambiguous page recovery as ambiguity, not a tie-breaking opportunity

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies / owner:** P1 / S–M, two slices / GRD-03 / source-reference recovery. **Backlog:** bounded A21 evidence-fidelity reliability subtask; preserve current conservative recovery and explicit abstention.

**Evidence and impact:** `src/generators/claim_validation_generator.py:1530–1573`, `_matched_source_pages()`, returns `exact[:1]` when the same text appears on multiple pages. Its approximate route uses `max(quantity_overlap, token_overlap, page)`, so equal support scores favor a page number rather than proven unique origin. `_source_references()` at lines 1493–1527 turns that choice into authoritative source references. **Confirmed arbitrary ambiguity resolution;** production misbinding frequency is unknown. A repeated executive-summary metric and its detailed page can have identical words but different denominators/notes, making lineage certainty important.

**Luna implementation:** (1) Return a bounded typed recovery result distinguishing declared-page resolution, unique exact match, unique conservative approximate candidate and ambiguous/unavailable. Include candidate page IDs, match reasons and a scalar score margin, without logging text. (2) Require uniqueness or independently bound section/span context before promoting a recovered page. When multiple matches have genuinely identical approved evidence semantics, retain the candidate set or explicit equivalent-source status rather than fabricate a unique origin. Reuse existing source fidelity to resolve support; ambiguous lineage must not trigger unbounded retrieval or silent full-document support.

**Success criteria:** Equal-score approximate candidates and repeated exact snippets never silently become a uniquely asserted page. A unique valid match remains recoverable. Input-order/page-number changes cannot manufacture a different accepted lineage. Ambiguity has an observable stable reason and a bounded hold/abstention route.

**Validation:** Run `python -m pytest -q tests/test_claim_validation_generator.py tests/test_claim_validation_source_pages.py tests/test_evidence_compatibility.py`. Extend the public `validate_evidence_fidelity()` fixtures with repeated snippets, equal quantities/different populations, two exact hits, unique exact hit and unique approximate hit; replay reordered source spans and assert provenance outcomes. Track recovered/ambiguous/unresolved denominators separately on a retained labelled source cohort before claiming higher success rates.

**Luna implementation prompt — GRD-04 (copy/paste)**

```text
Implement GRD-04 — Treat ambiguous page recovery as ambiguity, not a tie-breaking opportunity.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice GRD-04.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="grd-08"></a>
#### GRD-08 — Bind quote wording and speaker attribution separately to exact source spans

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies / owner:** P1 / M, three slices / GRD-03/06 / quotation source provenance. **Backlog:** A9/A21 source identity and quote fidelity extension; artifact-stage work owns quote discovery/selection, not this factual support binding.

**Evidence and impact:** `src/generators/evidence_packs/quote_candidates_strategy.py:44–70` normalizes `source`, `citation`, `speaker`, `author` or even `evidence_id` into one `source` string and keeps only one page. Final quotes retain `speaker` in `src/generators/artifact_normalization.py:1524–1531`, but `src/generators/claim_validation_generator.py:368–420` creates the quotation candidate from quote `text`; `_checks()` at lines 578–600 verifies wording against joined retained text, not the separately displayed speaker. **Confirmed representational/check-input gap:** attribution lacks an equally explicit binding. Broader grounding may detect some attribution drift; current incident frequency is unknown.

**Luna implementation:** (1) Retain exact source quote span(s) with original-source/page/offset hashes, normalized-match policy and separately source-backed speaker identity/context. Preserve unknown attribution instead of substituting report publisher/author. (2) Carry distinct verbatim/excerpt/explicit paraphrase semantics through approved quote generation; edited omissions may use ordered source spans but cannot imply one contiguous verbatim statement. (3) Build speaker attribution as its own factual premise within existing claim packages and bind final quote display to approved wording/attribution roots. Do not add publisher-name exceptions or a model call when exact source support is sufficient.

**Success criteria:** Correct wording assigned to the wrong speaker is never source-approved; absent attribution stays unknown/omitted. Multi-page quotes retain both roots; reordered or meaning-changing omissions fail/hold. Existing honest paraphrases remain clearly labelled and supported rather than forced into verbatim format.

**Validation:** Run `python -m pytest -q tests/test_claim_validation_generator.py tests/test_evidence_pack_generator.py tests/test_grounding_protected_facts.py tests/test_render_service_public_prose.py`. Add two speakers/same sentence, report-author versus interviewed-speaker, cross-page quote, safe ellipsis, negation omission and honest paraphrase fixtures; inspect final rendered attribution against approved retained roots through analysis-to-render replay.

**Luna implementation prompt — GRD-08 (copy/paste)**

```text
Implement GRD-08 — Bind quote wording and speaker attribution separately to exact source spans.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice GRD-08.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ver-01"></a>
#### VER-01 — Require one semantic verdict for every requested item

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

- **Priority / effort / dependencies:** P0 / S / none; coordinate with GRD response contracts. Extend the existing validator, not a second judge.
- **Evidence / diagnosis:** Confirmed contract gap: `src/schemas/semantic_validation_output.schema.json:5–30` permits empty response arrays and unconstrained IDs. `src/generators/validation/semantic.py:460–534` parses whatever rows arrive, silently skips blank IDs, and overwrites duplicate IDs in dictionaries; it never compares returned IDs with the request assembled at `428–457`. `run_semantic_validation():316–350` can materialize a schema-valid primary output before this semantic completeness check. Other grounding/readiness gates still protect claims; the defect is that this particular verifier can report incomplete work as a normal outcome.
- **Luna implementation:** Derive canonical expected metric/quote ID sets from the existing semantic payload; reject duplicate or blank input IDs before calling the model. Validate the returned set, multiplicity and family before parsing, on fresh outputs and reusable materializations. Missing, duplicate, unknown or wrong-family rows produce a stable typed completeness failure; never synthesize a supported verdict. Move successful materialization after complete response validation and bump the owning processing/validator identity. Preserve the existing orchestrator-owned bounded recovery and compatible old-reader behavior, but incompatible verdicts must regenerate.
- **Success criteria:** Every requested item has exactly one attributable verdict; partial/all-empty output for nonempty input fails this rule. Legitimately empty requests make zero calls with explicit non-applicability. Incomplete outputs are never retained as independently reusable successful validations.
- **Validation:** Add complete, omitted-last-item, all-empty, duplicate, foreign and blank-ID cases to `tests/test_validation_generator.py`, covering fresh and reused responses through `validate_report()`. Run `python -m pytest -q tests/test_validation_generator.py tests/test_prompt_family_materialization.py tests/test_publish_readiness_gate.py`. Test production readiness, not only parsing.

**Luna implementation prompt — VER-01 (copy/paste)**

```text
Implement VER-01 — Require one semantic verdict for every requested item.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice VER-01.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ver-02"></a>
#### VER-02 — Make malformed or unavailable semantic judgments explicit, not ordinary warnings

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P0 / M / VER-01; extend existing semantic schema and failure taxonomy.
- **Evidence / diagnosis:** Confirmed weak judge-output contract: `semantic_validation_output.schema.json:14–15,27–28` accepts arbitrary strings for booleans/confidence. `semantic.py:472–484,505–517` coerces unknown confidence to zero and derives rejection severity from model-supplied confidence; a false verdict with low/malformed confidence becomes warning-only. `semantic.py:393–425` converts nonretryable semantic execution failures into a warning. `validation_generator.py:131–138` labels a warning-only aggregate `pass`; readiness's `_validation_result():636–657` rejects errors/deferred issues, not these warning-only execution gaps. This proves an ambiguous verifier disposition, not that other retained-claim gates can be bypassed.
- **Luna implementation:** Version the model schema to require booleans and finite numeric confidence within [0,1]; canonical compatibility adapters may recognize explicitly documented legacy literals only. Separate content findings from verifier execution/completeness status. A failed required judge is `not_verified`/blocking, not a claim contradiction; uncertain unsupported material requires existing removal/abstention/review policy rather than being accepted because the judge expresses low confidence. Keep retryable infrastructure failures retryable and avoid broad threshold changes. Propagate the typed execution status into readiness through the current validation contract.
- **Success criteria:** Malformed confidence, unknown boolean strings, invalid JSON and exhausted judge recovery cannot satisfy a required semantic gate. Uncertainty is visible and never silently treated as support. Known supported/contradicted outcomes retain their existing factual safeguards and model-call bounds.
- **Validation:** Add boundary fixtures for negative/over-one/NaN/string confidence, unknown boolean values, refused/truncated output, nonretryable schema failure and low-confidence disagreement. Run `python -m pytest -q tests/test_validation_generator.py tests/test_grounding_semantic_outcomes.py tests/test_publish_readiness_gate.py tests/test_prompt_dry_run_validation.py`. Record any changed legacy compatibility behavior; no live model is required to establish fail-closed disposition.

**Luna implementation prompt — VER-02 (copy/paste)**

```text
Implement VER-02 — Make malformed or unavailable semantic judgments explicit, not ordinary warnings.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice VER-02.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ver-03"></a>
#### VER-03 — Persist proof of required rule execution, not only a list of issues

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / VER-01/02; extends P15 and existing validation contracts.
- **Evidence / diagnosis:** Confirmed observability/acceptance-proof gap: `src/contracts/validation.py:60–105` persists aggregate status and issues, but no required/executed/nonapplicable rule inventory or validation mode. `registry.py:84–87` emits only findings, so a successful executed rule and an omitted rule both contribute nothing. Mode selection at `90–102` excludes semantic and grounding for `inline_deterministic`, while `deferred_grounding` selects only grounding. The current explicit inline call (`_report_analysis_orchestrator/validation.py:1864–1869`) intentionally handles an already-rejected deterministic candidate; initial analysis defaults to full validation. `validation_generator.py:110–124,220–235` records a deferred issue and readiness blocks it. No production skipped-rule bypass is asserted; the residual gap is positive execution proof.
- **Luna implementation:** Add versioned per-rule evidence to the canonical `ValidationReport`: rule identity/version, applicability, disposition, checked-item count and compatible input identity. Determine required rules from the existing registry and current report contents, not operator-supplied arbitrary lists. Distinguish empty/nonapplicable from skipped/deferred/error. Merge compatible inline/deferred evidence without overwriting completed earlier checks; otherwise require a normal full validation. Readiness checks complete required coverage before accepting the aggregate. Provide explicit legacy interpretation that forces refresh where coverage cannot be proven.
- **Success criteria:** A successful report proves every applicable mandatory rule ran against compatible inputs. Deferred-only output cannot masquerade as full validation. Empty quotes are nonapplicable; removed semantic evidence is not a success. Serial and parallel runs yield equivalent canonical coverage.
- **Validation:** Extend `tests/test_validation_generator.py`, `tests/test_validation_queue_lineage.py` and `tests/test_publish_readiness_gate.py` for full/inline/deferred mode compositions, missing rows, incompatible input identities, nonapplicable rules and serial/parallel equivalence. Run these suites plus `tests/test_validation_run_manifest.py`. Validate the canonical queue's supported configuration before claiming an async failure; keep this proposal a coverage-proof extension until that behavior is reproduced.

**Luna implementation prompt — VER-03 (copy/paste)**

```text
Implement VER-03 — Persist proof of required rule execution, not only a list of issues.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice VER-03.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ver-04"></a>
#### VER-04 — Preserve retryable validation failures through the orchestration boundary

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

- **Priority / effort / dependencies:** P0 / S / none; extends canonical AppError/retry ownership, not CODE queue recovery.
- **Evidence / diagnosis:** Confirmed loss of error semantics: `src/orchestrators/_report_analysis_orchestrator/validation.py::_run_validation_with_fallback:217–306` catches every `Exception` and converts it into an ordinary failed `ValidationReport` without preserved `AppError` semantics. This includes a retryable `AppError` deliberately rethrown by `semantic.py:393–404`. The fallback issue at `269–275` has no stable rule/failure code, retryability or cause identity. The outer workflow cannot distinguish a temporary unavailable verifier from a valid completed rejection using this return value. The fallback is correctly fail-closed; the improvement is recoverability and diagnosis, not weaker acceptance.
- **Luna implementation:** Catch `AppError` separately, retain safe bounded code/cause metadata, and rethrow retryable errors to the existing orchestrator/queue retry mechanism. Keep a persisted non-publishable execution diagnostic if needed, but do not replace the exception with an ordinary content-validation result. Nonretryable validation execution failures receive stable rule/violation codes distinct from actual unsupported claims. Unexpected programming exceptions remain fail-closed and actionable. Do not add generator retries, inflate existing limits or expose raw exception/prompt/source content in logs.
- **Success criteria:** A transient verifier timeout follows the existing bounded retry path and can later complete without user requeue. A completed unsupported-claim verdict does not retry as an infrastructure failure. Exhaustion produces one typed terminal reason and never permits publication. Error context is redacted and stable enough for cohort failure attribution.
- **Validation:** Exercise canonical report-analysis dependencies with public-boundary fakes returning retryable AppError, nonretryable AppError, unsupported validation and unexpected exceptions. Run `python -m pytest -q tests/test_report_analysis_orchestrator_decomposition.py tests/test_validation_generator.py tests/test_validation_queue_lineage.py tests/test_atomic_regeneration_contract.py`. Add focused behavior cases to the existing report-analysis/atomic suite rather than relying on decomposition checks alone. Include a queue replay showing retry→success and retry exhaustion; component tests alone cannot prove workflow retry behavior.

**Luna implementation prompt — VER-04 (copy/paste)**

```text
Implement VER-04 — Preserve retryable validation failures through the orchestration boundary.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice VER-04.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ver-05"></a>
#### VER-05 — Add a deterministic adversarial corpus for the complete acceptance path

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / VER-01–04 for fixes; extend A21/R1 existing retained fixtures, not CROP-01 visual labels.
- **Evidence / diagnosis:** The repository already has focused verification suites (`tests/test_validation_generator.py`, `test_publish_readiness_gate.py`, `test_regeneration_candidate.py`) and an exact-identity frozen repair runner, `scripts/quality/replay_validation_repair_benchmark.py:532–680`. That benchmark preflights frozen repair cases; it is not evidence that every release gate rejects independently mutated negative fixtures. The migration evidence at `docs/quality/gpt6-luna-evaluation-20260923.md:49–72` supplies real classes: untrusted evidence rendered, provider markers, share mistaken for CAGR, and provenance failures. Gap is regression coverage assurance, not a claim that current guards miss those examples.
- **Luna implementation:** Start with a small hash-pinned subset of already-valid retained report packages. Define deterministic one-defect mutation operators with expected rejecting boundary/rule: omit judge verdict, change identity, corrupt readiness result, remove required rule, introduce unsupported sentence, swap forecast/observation or reference, alter protected field outside repair scope, and leak raw provider marker. Reuse canonical production validation/readiness orchestration with recorded external-boundary verdict fixtures. Include unmodified positive controls and legitimate near-neighbor cases to detect overblocking. Store approved fixture evidence through existing retention conventions; no public writes or new generic fuzzing framework.
- **Success criteria:** All critical invalid mutations are rejected at their specified boundary with stable reasons; positive controls remain accepted. Every mutation stays in the denominator, expected unavailable prerequisites are distinct from successful rejection, and execution uses zero providers/emails/publication. Claimed coverage lists exact rule IDs and input/validator hashes.
- **Validation:** Add `tests/test_verification_acceptance_mutations.py` as a proposed new suite and wire it into the existing relevant quality gate. Run it with `tests/test_publish_readiness_gate.py tests/test_regeneration_candidate.py tests/test_public_report_quality_gate.py`; repeat serial/parallel fixture replay. Baseline existing rejection outcomes before changing behavior, and never update expected outcomes merely to make a failing implementation pass.

**Luna implementation prompt — VER-05 (copy/paste)**

```text
Implement VER-05 — Add a deterministic adversarial corpus for the complete acceptance path.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice VER-05.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ver-07"></a>
#### VER-07 — Reject internally inconsistent persisted readiness decisions

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P0 / S–M / VER-03 coverage schema; extends P15/current checksum-bound readiness boundary.
- **Evidence / diagnosis:** Confirmed consumer-side consistency gap: `publish_readiness_generator.py:513–572` accepts arbitrary per-rule statuses/IDs and an empty `rule_results` list. `verify_publish_readiness():575–618` checks aggregate `status`, schema/version, content checksum, HTML/configuration/revision and expiry, but does not require the canonical rule set, unique IDs or all mandatory per-rule statuses `pass`. The normal producer correctly computes `all(item.status == "pass")` at `474–476`. `_artifact_signature():1721–1727` is a self-computed SHA-256 integrity checksum, not an authorization signature; it cannot by itself establish semantic consistency. This is a malformed-producer/legacy-consumer risk, not evidence of malicious access or an observed release.
- **Luna implementation:** Define required readiness rule IDs/applicability alongside the existing producer rules, code-owned and versioned. At parse/verify boundaries reject duplicate/unknown/omitted mandatory results, unsupported statuses/versions, aggregate disagreement and incomplete required validation coverage. Preserve explicit documented nonapplicability, never encode it as arbitrary success. Use normal refresh planning for incompatible old decisions. Do not rerun expensive quality models at publication and do not introduce cryptographic infrastructure without a separate security need; reuse the retained checksum and provenance.
- **Success criteria:** A checksum-valid readiness payload with empty rules, one failed required rule, duplicate or missing IDs, or inconsistent aggregate status cannot authorize publication. Current well-formed passing decisions remain reusable with zero model calls; expired/stale policies still refresh through the existing mechanism.
- **Validation:** Add crafted canonical-hash payloads to `tests/test_publish_readiness_gate.py`, proving integrity alone is insufficient. Run `python -m pytest -q tests/test_publish_readiness_gate.py tests/test_publish_readiness_refresh.py tests/test_publish_readiness_refresh_measurement.py tests/test_control_plane_quality_gates.py`. Exercise the publication preflight consumer with no external write, and verify legacy refresh rather than silently broadening acceptance.

**Luna implementation prompt — VER-07 (copy/paste)**

```text
Implement VER-07 — Reject internally inconsistent persisted readiness decisions.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice VER-07.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ver-09"></a>
#### VER-09 — Run cheap mandatory prerequisites before launching expensive verification

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / VER-03; ING-09 global provider limit remains separate.
- **Evidence / diagnosis:** Confirmed avoidable-work path: `registry.py:30–63` places deterministic claim support/quality and semantic checks in the same bootstrap stage. In parallel mode `130–140` launches all bootstrap and independent grounding work before deterministic failures are collected. `claim_support.py:77–125` can already identify absent/unknown evidence references and missing spans without a provider. Rejected invalid input can therefore consume semantic/grounding calls despite mechanically known prerequisite failure. This is not permission to skip final gates for a valid candidate or to accept incomplete diagnostics as success.
- **Luna implementation:** Introduce the smallest registry prerequisite distinction: schema/identity/required source-reference completeness first, then probabilistic checks only for inputs eligible for meaningful judgment. Preserve useful deterministic diagnostics and classify skipped costly checks `blocked_by_prerequisite` in VER-03's coverage result. Failed prerequisites remain non-publishable and route to existing typed repair/recovery. Keep independent costly checks parallel for eligible reports; do not serialize all validation or bypass checks merely because an editorial warning exists. Measure exact source-identical cohorts before/after using existing usage ledger and retained rule timings.
- **Success criteria:** Structurally unjudgeable fixture inputs invoke zero semantic/grounding providers and retain the same or stronger blocking reason. Valid controls still execute every required rule and produce equivalent readiness/claim disposition. Calls, cost and time decrease for the measured invalid-input cohort without moving failure detection downstream or weakening acceptance. Report actual deltas rather than promising an unmeasured percentage.
- **Validation:** Add counting public-provider fakes and malformed/valid controls to `tests/test_validation_generator.py`; test both worker modes and deferred behavior. Run this suite plus `tests/test_validation_evidence_retrieval.py tests/test_grounding_semantic_outcomes.py tests/test_publish_readiness_gate.py`. Validate the affected downstream repair/readiness path on the frozen corpus; record eligibility denominators, zero-call rejection counts and complete coverage before accepting the optimization.

**Luna implementation prompt — VER-09 (copy/paste)**

```text
Implement VER-09 — Run cheap mandatory prerequisites before launching expensive verification.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice VER-09.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="arch-a"></a>
#### ARCH-A — Reuse an item-level verified evidence pool rather than re-verifying source facts per artifact

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / `GRD-01/02/05/07/09`, `E16`; extends `A21` evidence integrity and `ART-04` upstream family policy. No new retrieval service, database or independent grounding judge.
- **Evidence / diagnosis:** `evidence_pack_generator.py` already runs `validate_evidence_fidelity()` against PDF-derived spans and `exclude_untrusted_evidence()` for findings and quote candidates before artifact generation. Retained support outcomes and provenance exist, but the verified candidate's eligibility, source-root binding, protected qualifiers and later editorial priority are not one coherent downstream selection contract. The evidence-pack family confidence score measures content presence/completeness, not factual certainty.
- **Luna implementation:** Reuse retained per-claim fidelity results and source/evidence identities. Expose a compact versioned candidate view with candidate ID, source family, exact evidence binding, support disposition, methodological/applicability qualifiers, provenance and validation identity. Reuse existing materialization/cache rules only when claim text, evidence, validator and source identity match. Unsupported candidates are ineligible; unresolved candidates may receive bounded existing semantic evidence checks or remain held, not silently promoted. Do not conflate an interpretive recommendation with a verified source-stated fact.
- **Success criteria:** Every selected factual candidate resolves to one unambiguous approved source binding and compatible current verification; no quarantined, stale or unresolved material fact enters downstream public generation as verified. Unknown methodology remains explicitly unknown. Previously supported evidence retains its eligibility without an unnecessary provider call.
- **Validation:** Add focused source-ID collision, stale evidence, mismatched cohort/period/denominator, incomplete provenance and support-grade fixtures through existing evidence/claim public boundaries. Run the affected claim-validation, evidence-fidelity, serialization/reuse and readiness suites, then at least one real previously failed report. Record newly avoided and introduced provider calls separately.

**Luna implementation prompt — ARCH-A (copy/paste)**

```text
Implement ARCH-A — Reuse an item-level verified evidence pool rather than re-verifying source facts per artifact.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ARCH-A.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="arch-c"></a>
#### ARCH-C — Validate generated insight candidates before dependent prose and substitute approved reserves

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / follow-ups A/B, `ART-04`, `VER-09`, `E13`; extends `A21` first-pass reliability.
- **Evidence / diagnosis:** `generation.py` builds and normalizes insight candidates, fills gaps from findings, produces final insights and then schedules Expert View, LinkedIn and cover generation. Full claim grounding and public editorial validation happen after artifact assembly. Existing final-insight reference checks and protected candidate factual restoration do not establish that every newly worded material claim is factually supported before dependent generation.
- **Luna implementation:** At the candidate and finalized-insight boundaries, reuse `validate_retained_claims()`, protected-fact/numeric/reference checks and compatible cached semantic verdicts. Reject mechanically proven invalid facts before launching dependent families. Batch semantic adjudication only for unresolved material new assertions; avoid a second full report-level grounding pass. Prefer substitution from the approved, theme-compatible reserve, then bounded local correction or abstention under the existing planner. Do not force a rigid insight count unsupported by source breadth.
- **Success criteria:** A known wrong value, unit, period, geography, cohort, denominator, unsupported causal premise or source reference cannot seed Expert View, LinkedIn, Key Figures or cover semantics. A valid substitute preserves theme diversity and provenance. Eligible reports still complete all final grounding/readiness rules; fewer repairs must not be obtained by dropping meaningful reporting.
- **Validation:** Replay real failed-insight cases plus positive and ambiguous controls; assert downstream model calls do not start on proven-invalid prerequisites, substitutions reference only approved evidence, and final textual/semantic quality is maintained. Measure first-pass pass rate, downstream calls, repairs, tokens and wall-clock time on identical frozen inputs.

**Luna implementation prompt — ARCH-C (copy/paste)**

```text
Implement ARCH-C — Validate generated insight candidates before dependent prose and substitute approved reserves.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ARCH-C.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="arch-h"></a>
#### ARCH-H — Consolidate only proven redundant validation work and short-circuit unjudgeable inputs

**Primary canonical owner:** [A21](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Investigation; promote only on evidence.

- **Priority / effort / dependencies:** P2 / S–M investigation before changes / `VER-09`, `VER-05/06`, `A21`; preserve all release guards.
- **Evidence / diagnosis:** `validation.semantic` judges metric/quote support; `validation.grounding` judges broader public/retained claims including some metrics and quotations. Their scopes overlap but are not shown to be interchangeable. Public editorial checks also run before and after regeneration and again on final output; some unchanged-input work may be reusable. Parallel provider execution means deleting one call does not guarantee equivalent wall-clock savings.
- **Luna implementation:** On an unchanged frozen cohort, attribute each validator's unique hard-failure detections, false positives, reused verdicts, calls and critical-path time. Move cheap structural/source-reference prerequisites ahead of expensive semantic work per existing VER-09 rather than serializing eligible verification wholesale. Reuse an unchanged deterministic/editorial report only with exact artifact/input/policy/validator identity. Remove or merge a semantic pass only if independent adversarial/human adjudication proves no lost critical coverage. Keep render-specific HTML checks and final checksum/source/claim readiness distinct.
- **Success criteria:** Invalid mechanically unjudgeable inputs consume no unnecessary provider calls; valid inputs execute all mandatory checks. No newly accepted unsupported claim, missing verdict or stale readiness package; any wall-clock/cost gain is measured rather than estimated. If equivalence is unproven, retain both semantic paths without adding a new abstraction.
- **Validation:** Run VER-05 adversarial positive/negative controls, VER-06 labelled judgments where available, full validation/readiness tests and the immutable five-report cohort; compare unique rejection coverage, false-accept/false-reject counts, usage and end-to-end timings.

**Luna implementation prompt — ARCH-H (copy/paste)**

```text
Implement ARCH-H — Consolidate only proven redundant validation work and short-circuit unjudgeable inputs.
Objective: Deliver the verified behavior specified immediately above under canonical A21.
Source: docs/backlog/A-autonomy.md, technical slice ARCH-H.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update A21 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
