# Consolidated TODO

Last compiled: 2026-04-28

This file is the single source of truth for open backlog items. It now includes the remaining consolidated backlog plus the moved items from `docs/quality/deep-analysis-x10-plan-2026-04-15.md`.

Items are grouped by workstream. Duplicates were merged. Each task includes: title, explanation (what & why), pros & cons, and acceptance criteria.

Completed items are removed from this backlog once their acceptance criteria are met. Prefer adding new tasks under the most relevant workstream instead of creating new append-only audit sections.

Deep-analysis evidence used for this consolidation:

- Architecture import gate passes: `python scripts/ci/check_architecture_imports.py`.
- Forbidden patching gate passes: `python scripts/ci/check_forbidden_patching.py`.
- Long-file concentration remains high in `src/services/report_store_service.py`, `src/services/_browser_report_download/artifact.py`, `src/services/config_service.py`, `src/ui/streamlit_pages.py`, `src/services/_browser_report_download/browser.py`, `src/services/publisher_inventory_service.py`, `src/generators/report_selection_generator.py`, and large paired tests.
- Additional hotspots from the 2026-04-28 scan: `src/generators/report_generation_dependencies.py` imports 90 symbols, several model-call paths still mix `openai_service` and `llm_service`, and SQLite DDL/migrations remain embedded in service startup paths.
- Prompt infrastructure now includes namespace-level dry-run contracts and loaders (`src/contracts/prompts.py`, `src/services/prompt_service.py`), so prompt workstream tasks should target CI enforcement and corpus quality thresholds instead of first-time scaffolding.
- `docs/quality/initiative_ledger.yaml` tracks active initiatives (`ocr-confidence-gating`, `side-effect-idempotency`, `spend-guardrails`, `prompt-dry-run-validation`) and already-completed initiatives (`performance-cost-regression`, `repository-hygiene`); backlog priorities should align to that ledger.
- Current x10 opportunities concentrate around cost-aware LLM routing, PDF/OCR triage, resumable orchestration, browser acquisition stability, publish durability, and regression gates.

How to use this backlog:

- Treat this file as the only active TODO source.
- Remove items once their acceptance criteria are fully met.
- Keep overlapping work merged into one item with explicit source notes in the explanation when needed.
- Every prioritized item must get an owner, baseline metric, target metric, and expiry/review date before implementation starts.

Scoring rubric:

- `Impact`: `1` low leverage, `5` highest leverage across reliability, quality, cost, speed, or architecture.
- `Effort`: `1` localized change, `5` broad refactor/migration with cross-module coordination.

Suggested priority order:

1. `1. LLM, Prompts, Cost & Provider Policy`
2. `3. PDF, OCR, Candidate Extraction & Ranking`
3. `5. Orchestration, State, Idempotency & Scheduling`
4. `6. Publishing & WordPress`
5. `8. CI, Observability, Governance & Release Safety`
6. `9. Architecture Simplification & Code Reduction`

---

## 1. LLM, Prompts, Cost & Provider Policy

- **Title:** Add prompt variant/A-B harness with offline scored corpora [Impact: 4/5, Effort: 4/5]
  - Explanation: Merge multi-prompt variants and the deep-analysis A/B harness into one capability: config-driven variants, deterministic selection, fixed corpora, and scorecards for schema validity, grounding, and cost.
  - Pros: Higher-quality outputs, safer prompt iteration, data-driven rollout decisions.
  - Cons: Increases evaluation cost and requires benchmark ownership.
  - Acceptance Criteria:
    - Config accepts multiple variants per prompt namespace.
    - Per-variant prompt hashes, rendered prompts, model parameters, costs, and scores are logged.
    - Offline scorecards include schema-valid, grounding, latency, and token/cost metrics.
    - Promotion policy defines when a variant can become default.

- **Title:** Implement budget-aware model routing with deterministic context compaction [Impact: 5/5, Effort: 4/5]
  - Explanation: Merge adaptive model routing and prompt-budget planning. Route low-risk steps to cheaper/faster models, preserve premium models for high-risk tasks, and compact over-budget context by deterministic policy rather than ad hoc trimming.
  - Pros: Major cost and latency reduction, fewer timeout risks, explicit quality/cost tradeoffs.
  - Cons: Requires quality guardrails, fallback policy, and careful evidence-retention tests.
  - Acceptance Criteria:
    - Policy table maps task families to model tiers, max input budget, fallback tier, and quality threshold.
    - Routing decision, budget decision, compaction strategy, and reason are logged per call.
    - Over-budget requests are trimmed by deterministic policy.
    - Regression tests protect key-evidence retention.
    - Benchmark shows material token/cost reduction without quality regression on a fixed corpus.

- **Title:** Add provider failover behind one compatible LLM response contract [Impact: 5/5, Effort: 5/5]
  - Explanation: Add a secondary provider path and normalize provider responses into one contract. Keep provider-specific details at the service boundary, while generators consume one typed response shape.
  - Pros: Higher availability during provider incidents and cleaner provider isolation.
  - Cons: Multi-provider complexity, cost variance, and more integration tests.
  - Acceptance Criteria:
    - Primary/secondary fallback policy exists and is tested.
    - Error taxonomy is normalized across providers.
    - Generator contracts do not depend on provider-specific response shapes.
    - Disaster-recovery test demonstrates failover success with logged provider decisions.

---

## 2. Cost, Resource Lifecycle & Artifact Durability

- **Title:** Enforce real-time spend guardrails across run/day/publisher budgets [Impact: 5/5, Effort: 2/5]
  - Explanation: Merge existing cost-limit work with the deep-analysis spend-guardrail item. Add hard and soft caps by run, day, and publisher, with policy outcomes such as warn, pause, stop, or explicit override.
  - Pros: Prevents runaway spend and makes cost decisions operationally visible.
  - Cons: May block valid runs without a clear override path.
  - Acceptance Criteria:
    - Configurable thresholds exist in YAML for run, day, and publisher scopes.
    - Orchestrators check thresholds before model or expensive browser/OCR calls.
    - Breaches emit typed events, state updates, and structured logs.
    - Tests cover warn, pause, hard-stop, and operator override behavior.

- **Title:** Add vector store deletion and lifecycle cleanup [Impact: 3/5, Effort: 3/5]
  - Explanation: Extend vector-store service boundaries with delete/prune APIs and add orchestrator hooks to remove remote assets when retention is disabled or expiry is reached.
  - Pros: Avoids orphaned storage and repeated remote costs.
  - Cons: Risk of deleting useful artifacts if policies are wrong; requires idempotency.
  - Acceptance Criteria:
    - Delete/prune APIs exist and return typed dataclass results.
    - Cleanup policies are driven by config and orchestrated with idempotency keys.
    - Cleanup logs include run/task/span identifiers and outcomes.
    - Tests cover missing remote assets, duplicate cleanup calls, and retention-disabled runs.

---

## 3. PDF, OCR, Candidate Extraction & Ranking

- **Title:** Add page-level triage before expensive PDF extraction [Impact: 5/5, Effort: 4/5]
  - Explanation: Score pages for likely information value before visual extraction, table extraction, cropping, and OCR. Appendix-heavy documents can avoid large amounts of waste while preserving recall through conservative thresholds.
  - Pros: Major throughput and cost gain on large reports.
  - Cons: False negatives are risky if triage is too aggressive.
  - Acceptance Criteria:
    - Triage score is computed per page and logged.
    - Skip policy is configurable and conservative by default.
    - Evaluation set confirms required recall threshold.
    - Stage metrics show extraction/crop/OCR work avoided.

- **Title:** Fix O(n^2) table dedupe hotspot [Impact: 4/5, Effort: 3/5]
  - Explanation: Replace the O(n^2) table dedupe algorithm in candidate extraction with a hash/index-assisted approach that preserves conservative merge behavior.
  - Pros: Better performance on large PDFs.
  - Cons: Requires careful tests to avoid false merges and missed duplicates.
  - Acceptance Criteria:
    - Dedupe algorithm is updated and benchmarked with large PDFs.
    - Correctness tests cover near-duplicate, overlapping, and distinct-table cases.
    - No regression in candidate quality on fixture reports.

## 4. Browser Acquisition & Publisher Inventory

- **Title:** Add deferred acquisition recovery recipes for high-confidence failures [Impact: 4/5, Effort: 3/5]
  - Explanation: Existing discovery docs identify second-pass recovery opportunities. Implement typed, bounded recovery recipes for strong candidates rejected due to recoverable landing-page/browser failures, without bypassing quality gates.
  - Pros: Higher acquisition yield on difficult publishers.
  - Cons: Adds recovery policy complexity and can increase browser cost.
  - Acceptance Criteria:
    - Recovery recipe contract defines trigger, retry limit, route, and stop conditions.
    - Orchestrators schedule recovery only for high-confidence, recoverable failures.
    - Recovery never bypasses artifact validation or landing-page quality gates.
    - Metrics compare recovered candidates against added cost.

---

## 5. Orchestration, State, Idempotency & Scheduling

- **Title:** Introduce durable, checkpointed pipeline stages with semantic restart [Impact: 5/5, Effort: 5/5]
  - Explanation: Merge durable pipeline checkpoints and checkpoint/restart into one program. Store stage-level checkpoints with artifact references so failed runs can resume from semantic boundaries instead of full reruns.
  - Pros: Faster recovery, lower rerun cost, better operator control.
  - Cons: Requires state modeling, migration, and checkpoint versioning.
  - Acceptance Criteria:
    - Checkpoint contracts are defined per major stage.
    - Stage-level checkpoints are stored with artifact references and schema versions.
    - Resume command supports selected stage restart.
    - Consistency tests compare full run vs resumed run output.

- **Title:** Add event-sourced state transitions with immutable audit log [Impact: 5/5, Effort: 5/5]
  - Explanation: Record lifecycle transitions as immutable events so state can be reconstructed, replayed, and audited after failures.
  - Pros: Strong auditability, deterministic replay, better debugging.
  - Cons: Migration complexity and storage growth.
  - Acceptance Criteria:
    - Transition events are stored append-only with run/task/span IDs.
    - Current state can be reconstructed from the event stream.
    - Replay tooling reproduces lifecycle transitions.
    - Tests cover migration from current state snapshots to event-backed reconstruction.

- **Title:** Add dynamic concurrency controller with capacity-aware publisher fairness [Impact: 5/5, Effort: 4/5]
  - Explanation: Merge dynamic concurrency and fair scheduling. Adjust concurrency based on queue depth, failure budget, cost budget, browser capacity, and publisher cohort fairness.
  - Pros: Better throughput stability, less starvation, safer burst handling.
  - Cons: Control-loop tuning complexity.
  - Acceptance Criteria:
    - Controller reads queue depth, recent failure metrics, browser capacity, and budget state.
    - Scheduling policy includes per-cohort quotas or weights.
    - Concurrency and fairness decisions are logged with rationale.
    - Load/simulation tests show improved stability and no cohort starvation.

- **Title:** Add per-stage feature flags for controlled rollout [Impact: 3/5, Effort: 3/5]
  - Explanation: Add feature flags at stage boundaries for controlled rollouts, A/B tests, emergency disable switches, and cost containment.
  - Pros: Safer deployments and operational control.
  - Cons: Adds configuration surface and flag governance.
  - Acceptance Criteria:
    - Per-stage flags are configurable in YAML and read by orchestrators.
    - Disabled stages fail explicitly, skip explicitly, or use a documented fallback policy.
    - Tests validate enabling/disabling key stages.

---

## 6. Publishing & WordPress

- **Title:** Turn publish queue into durable jobs with transactional outbox, retry, and idempotency [Impact: 5/5, Effort: 5/5]
  - Explanation: Merge publish-queue durability and transactional outbox. Persist publish intents, commit state and side-effect intents atomically, dispatch with retry/backoff, and make delivery idempotent.
  - Pros: More reliable publishing, fewer partial-commit inconsistencies, easier retry handling.
  - Cons: Adds queue/outbox infrastructure and operational behavior.
  - Acceptance Criteria:
    - Publish jobs can be enqueued, persisted, retried, and dead-lettered.
    - Outbox table records side-effect intents atomically with state changes.
    - Delivery attempts are idempotent and logged.
    - Failure-injection tests cover restart, retry, duplicate dispatch, and partial WordPress failures.

---

## 7. Schema, Validation, Output Quality & Rendering

- **Title:** Build backward/forward contract compatibility matrix [Impact: 4/5, Effort: 4/5]
  - Explanation: Add compatibility tests for current and previous contract versions, including adapter/migration paths, so rolling runs and stored artifacts survive contract evolution.
  - Pros: Safer phased deploys and clearer breaking-change discipline.
  - Cons: Larger fixture and test surface.
  - Acceptance Criteria:
    - Contract compatibility suites run in CI.
    - Adapter logic has positive and negative tests.
    - Breaking changes require explicit version bump evidence.
    - Serialized fixture snapshots cover representative stored artifacts.

- **Title:** Add ensemble validation with schema, deterministic rules, and LLM verifier [Impact: 5/5, Effort: 4/5]
  - Explanation: Combine orthogonal validators to catch failure modes that one validator misses. Aggregate conflicts into a typed validation report instead of hiding disagreement.
  - Pros: Higher robustness and better defect detection.
  - Cons: Additional compute and orchestration complexity.
  - Acceptance Criteria:
    - Multi-validator pipeline emits an aggregated validation report.
    - Conflicts between validators are surfaced explicitly.
    - Regression suite demonstrates improved defect detection on known bad fixtures.

- **Title:** Add deterministic failure-to-fix planner for targeted regeneration [Impact: 4/5, Effort: 4/5]
  - Explanation: Map known validation failure classes to deterministic repair recipes before full regeneration, reducing expensive broad reruns.
  - Pros: Fewer full reruns and clearer repair behavior.
  - Cons: Rule maintenance burden.
  - Acceptance Criteria:
    - Failure taxonomy maps to repair actions.
    - Repair attempts log before/after diffs and exact regenerated artifacts.
    - Benchmarks show lower regeneration volume.

- **Title:** Add infographic asset generation for HTML and LinkedIn [Impact: 2/5, Effort: 4/5]
  - Explanation: Create a generator/service pair that produces simple infographic SVG/PNG assets from highlights, persists metadata, and exposes assets to HTML and publishing flows.
  - Pros: Richer publishable artifacts and better social sharing.
  - Cons: Additional generation cost and pipeline complexity.
  - Acceptance Criteria:
    - Infographic assets are generated per report and stored with metadata.
    - HTML rendering includes generated infographic references where available.
    - Publish artifacts contain asset links.

---

## 8. CI, Observability, Governance & Release Safety

- **Title:** Harden architecture and test-integrity gates beyond current import/patch checks [Impact: 4/5, Effort: 3/5]
  - Explanation: Current import and forbidden-patching gates pass. Extend enforcement to role-mixing heuristics, direct I/O drift, monolithic-module growth, missing integration tests per service, required log-field checks, and contract round-trip coverage.
  - Pros: Prevents architectural drift and keeps tests hard to fake.
  - Cons: Requires curated exemptions for legitimate edge cases.
  - Acceptance Criteria:
    - Existing import and forbidden-patching gates remain in CI.
    - Gates report role mixing, direct I/O violations, and missing service integration coverage.
    - At least one marked integration test exists per service boundary or an explicit allowlist entry with expiry exists.
    - Required structured log fields are asserted for each orchestrator and service.
    - Contract round-trip tests cover every added/modified dataclass contract.

- **Title:** Add end-to-end tracing across orchestrator, generator, and service boundaries [Impact: 4/5, Effort: 3/5]
  - Explanation: Add trace spans for major pipeline boundaries and correlate them with run/task/span IDs to make critical-path timing and dependencies visible.
  - Pros: Faster bottleneck localization and stronger observability.
  - Cons: Telemetry overhead and storage planning.
  - Acceptance Criteria:
    - Trace spans are created for major orchestrator/generator/service boundaries.
    - Trace IDs correlate with run/task/span IDs in logs.
    - Dashboard or report surfaces critical-path timing.

- **Title:** Add failure taxonomy anomaly detection [Impact: 4/5, Effort: 4/5]
  - Explanation: Monitor error distributions for unusual spikes by stage, provider, route family, and publisher cohort.
  - Pros: Earlier reliability regression detection.
  - Cons: False positives during calibration.
  - Acceptance Criteria:
    - Baseline failure distributions are established.
    - Drift detector alerts on significant deviations.
    - Alert payload includes likely affected modules and recent change context.

- **Title:** Add flaky test detector and quarantine workflow [Impact: 4/5, Effort: 3/5]
  - Explanation: Detect intermittently failing tests and separate them from stable merge gates with explicit owner accountability and SLA.
  - Pros: Cleaner CI signal and better merge velocity.
  - Cons: Requires process enforcement.
  - Acceptance Criteria:
    - Flake detector records reproducibility rate.
    - Quarantined tests are tracked with owner, reason, and SLA.
    - Merge gate excludes quarantined tests only with explicit reporting.

- **Title:** Add nightly chaos/retry/idempotency stress suite [Impact: 4/5, Effort: 4/5]
  - Explanation: Validate transient failures, lock contention, retry storms, provider failures, browser timeouts, and duplicate side-effect attempts outside the normal fast CI path.
  - Pros: Stronger reliability under realistic failure modes.
  - Cons: Extra runtime and infrastructure cost.
  - Acceptance Criteria:
    - Stress suite includes failure-injection scenarios.
    - Attempt counts, backoff decisions, state transitions, and idempotency outcomes are asserted.
    - Results feed a reliability dashboard or summary artifact.

- **Title:** Add PR quality bot for schema, coverage, mutation, cost, and risk diffs [Impact: 4/5, Effort: 3/5]
  - Explanation: Post a high-signal PR summary with changed contracts, schema snapshots, coverage deltas, mutation score deltas, cost/performance benchmark deltas, and architecture-gate risk.
  - Pros: Faster, higher-quality reviews for complex changes.
  - Cons: Bot maintenance and noise tuning.
  - Acceptance Criteria:
    - Bot comment includes risk summary and key quality deltas.
    - Links to failing gates and artifacts are present.
    - Noise threshold is tuned with review feedback.

- **Title:** Add canary ingestion/release train with automatic rollback gates [Impact: 5/5, Effort: 4/5]
  - Explanation: Ship risky pipeline changes progressively with health checks and rollback on validation, cost, latency, or error SLO breach.
  - Pros: Smaller blast radius and safer production changes.
  - Cons: Deployment orchestration effort.
  - Acceptance Criteria:
    - Canary cohorts and rollback thresholds are defined.
    - Rollback triggers on validation, cost, latency, or error SLO breaches.
    - Post-deploy report records canary outcomes.

---

## 9. Architecture Simplification & Code Reduction

- **Title:** Split remaining service long-file hotspots only along real capability boundaries [Impact: 5/5, Effort: 5/5]
  - Explanation: The report-selection hotspot now uses a facade-plus-family layout (`src/generators/report_selection_generator.py` plus `src/generators/_report_selection_generator/*`). Remaining concentration still sits in report store, config service, browser-download artifact handling, PDF heuristics, and publisher inventory internals. Continue the same pattern only where a semantic family boundary is real: keep one canonical facade file per boundary, move coherent families into a same-name internal subfolder, and avoid pass-through wrapper layers.
  - Pros: Higher simplicity, lower cognitive load, better defect containment.
  - Cons: Large refactors can add fragmentation if boundaries are artificial.
  - Acceptance Criteria:
    - Remaining hotspots keep one canonical facade file, with real semantic families moved into a dedicated same-name internal subfolder.
    - Each split has a documented semantic responsibility and concrete reason.
    - Canonical service/generator/orchestrator entrypoints remain discoverable.
    - No new pass-through wrapper modules are introduced.
    - Long-file report shows reduced concentration in the remaining named hotspots.
    - Golden and behavior tests prove parity or explicitly approved improvements.

## Priority Launch Plan

### Phase 1: Highest-Leverage Foundations (2-4 weeks)

- OCR confidence gating hardening (threshold calibration + negative-path regression coverage).
- Idempotency checksum per side-effecting orchestrator step.
- Real-time spend guardrails at run/day/publisher scopes with operator override flow.
- Prompt dry-run validation enforcement in CI with fixture corpus coverage targets.

### Phase 2: Speed and Recovery (4-8 weeks)

- Budget-aware model routing with deterministic context compaction.
- Page-level PDF triage.
- Durable checkpoint/restart.
- Deterministic per-page/per-figure fingerprint cache.

### Phase 3: Resilience and Quality (8-16+ weeks)

- Provider failover contract.
- Ensemble validation and claim-span binding.
- Durable publish queue with transactional outbox.
- Canary release train.
- Dynamic concurrency and fairness controller.
- Dead-letter workflow with typed triage categories.

### Phase 4: Simplicity and Maintainability (ongoing)

- Long-file hotspot splits by real capability boundary using facade file + same-name internal family subfolder layout.
- Contract module family split using public module facade + same-name internal family subfolder layout.
- Report-generation dependency-bundle split using public facade + semantic dependency-family modules.
