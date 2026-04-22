# Deep Analysis and x10 Improvement Plan (2026-04-17)

Last updated: 2026-04-22

This file is intentionally formatted like `CONSOLIDATED_TODO.md`: every proposal has a title, explanation (what + why), pros/cons, and acceptance criteria.

## Scope and evidence base

This assessment targets the Python platform in `src/` (contracts/services/generators/orchestrators/utils), CI gates in `scripts/ci/`, and surrounding quality docs.

Signals used:

- Architecture and role boundaries in `README.md` and `docs/architecture/role-boundaries.md`.
- Quality gates in:
  - `scripts/ci/check_coverage.py`
  - `scripts/ci/run_mutation_gate.py`
  - `scripts/ci/check_forbidden_patching.py`
- Repository footprint checks:
  - module counts by layer
  - long-file concentration via `python scripts/count_long_files.py`

Current profile snapshot:

- `src/contracts`: 44 files
- `src/services`: 51 files
- `src/generators`: 63 files
- `src/orchestrators`: 23 files
- `src/utils`: 23 files
- `tests/test_*.py`: 102 files

Large-module concentration hotspots include:

- `src/services/_pdf/figures.py`
- `src/services/report_store_service.py`
- `src/services/publisher_inventory_service.py`
- `src/services/openai_service.py`
- `src/orchestrators/report_analysis_orchestrator.py`
- `src/orchestrators/ingest_orchestrator.py`

Scoring rubric:

- **Impact**: 1/5 (local) to 5/5 (transformational cross-workflow leverage)
- **Effort**: 1/5 (localized) to 5/5 (broad rollout + migration)

---

## 1) Contracts & Schema Governance

- **Title:** Build backward/forward compatibility test matrix [Impact: 4/5, Effort: 4/5]
  - Explanation: Add compatibility tests for current and previous contract versions to protect rolling runs. Release safety improves dramatically compared with single-version-only tests.
  - Pros: Upgrade confidence, safer phased deploys.
  - Cons: Larger test surface and fixtures.
  - Acceptance Criteria:
    - Contract compatibility suites run in CI.
    - Adapter logic covered with positive + negative cases.
    - Breaking changes require explicit version bump evidence.

---

## 2) OpenAI / LLM Cost, Reliability, and Throughput

- **Title:** Adaptive model routing by criticality + budget policy [Impact: 5/5, Effort: 4/5]
  - Explanation: Route low-risk generation steps to cheaper/faster models while preserving premium models for high-risk tasks. On multi-step pipelines this can reduce spend by >10x.
  - Pros: Major cost control, faster average latency.
  - Cons: Requires quality guardrails and fallback policies.
  - Acceptance Criteria:
    - Policy table maps task families to model tiers.
    - Routing decision + reason logged per call.
    - Quality/cost benchmark shows target savings without quality drop.

- **Title:** Semantic response cache (`prompt_hash + context_hash + params`) [Impact: 5/5, Effort: 3/5]
  - Explanation: Cache stable LLM outputs so reruns/regeneration loops skip repeated calls. Repeated workloads commonly see >10x token savings.
  - Pros: Fast reruns, direct cost reduction.
  - Cons: Cache invalidation and drift handling.
  - Acceptance Criteria:
    - Deterministic cache keys and TTL policy implemented.
    - Cache hit/miss metrics logged.
    - Rerun benchmarks show material token/latency reductions.

- **Title:** Prompt budget planner with automatic context compaction [Impact: 4/5, Effort: 3/5]
  - Explanation: Pre-compact low-value context before model calls to cap token bloat. Large-report scenarios can gain >10x latency reduction in worst cases.
  - Pros: Predictable token budgets, fewer timeout risks.
  - Cons: Compaction mistakes may lose important evidence.
  - Acceptance Criteria:
    - Compaction strategy is deterministic and logged.
    - Over-budget requests are trimmed by policy, not ad hoc.
    - Regression tests protect key-evidence retention.

- **Title:** Provider failover seam with compatible response contract [Impact: 5/5, Effort: 5/5]
  - Explanation: Add secondary provider path and normalize responses into one contract. During provider incidents, successful completion can improve by >10x.
  - Pros: Higher availability and operational resilience.
  - Cons: Multi-provider complexity + cost variance.
  - Acceptance Criteria:
    - Primary/secondary fallback policy exists and is tested.
    - Error taxonomy normalized across providers.
    - DR test demonstrates failover success.

- **Title:** Refusal/error-type-aware retry policy [Impact: 4/5, Effort: 2/5]
  - Explanation: Differentiate retryable transient errors from permanent refusals so retries stop wasting budget. Failed-attempt efficiency can improve by >10x for refusal-heavy paths.
  - Pros: Cleaner retries, lower waste.
  - Cons: Requires taxonomy tuning as providers evolve.
  - Acceptance Criteria:
    - Refusal classes mapped to retry/no-retry.
    - Retry reasons logged with structured code.
    - Tests assert bounded retry behavior per error class.

---

## 3) PDF Processing & Visual Candidate Pipeline

- **Title:** Page-level triage classifier before expensive extraction [Impact: 5/5, Effort: 4/5]
  - Explanation: Identify low-information pages early and bypass expensive extraction/crop steps. Appendix-heavy documents can see >10x compute savings.
  - Pros: Major throughput gain.
  - Cons: False negatives if triage too aggressive.
  - Acceptance Criteria:
    - Triage score computed per page and logged.
    - Skip policy configurable and conservative by default.
    - Evaluation set confirms recall threshold.

- **Title:** Deterministic per-page/per-figure fingerprint cache [Impact: 5/5, Effort: 3/5]
  - Explanation: Cache intermediate results at sub-document granularity to avoid full recompute when only portions change. Reruns can be >10x faster.
  - Pros: High rerun speedups, reduced CPU.
  - Cons: Additional storage and key lifecycle management.
  - Acceptance Criteria:
    - Fingerprint includes content + parser version components.
    - Cache invalidation tied to version changes.
    - Partial-change rerun benchmark demonstrates wins.

- **Title:** OCR confidence gating (native first, OCR selective fallback) [Impact: 5/5, Effort: 2/5]
  - Explanation: Use OCR only when native text extraction confidence is poor. Mixed corpora can cut OCR spend by >10x.
  - Pros: Lower cost and latency.
  - Cons: Confidence threshold calibration required.
  - Acceptance Criteria:
    - Confidence metric defined and logged.
    - OCR called only when threshold fails.
    - Cost report shows reduced OCR usage.

- **Title:** Typed candidate-feature contract for ranking/crop decisions [Impact: 4/5, Effort: 4/5]
  - Explanation: Replace ad-hoc `meta` keys with typed feature contracts for quality/ranking inputs. Prevents key drift bugs and improves ranking consistency significantly.
  - Pros: Safer evolution, better testability.
  - Cons: Broad migration across extraction/ranking.
  - Acceptance Criteria:
    - New feature dataclass replaces required `meta` lookups.
    - Serialization round-trip tests added.
    - Ranking/crop modules consume typed features only.

- **Title:** Shared raster/statistics probe cache for bbox analysis [Impact: 3/5, Effort: 3/5]
  - Explanation: Reuse rendered probes and derived stats across heuristics that inspect the same bbox. Graphics-heavy PDFs gain significant extraction speedups.
  - Pros: Less repeated rendering work.
  - Cons: Key correctness is critical.
  - Acceptance Criteria:
    - Cache key includes page+bbox+render profile.
    - Probe reuse observed in extraction logs.
    - Benchmarks show extraction time reduction.

---

## 4) Publisher Inventory & Browser Acquisition

- **Title:** Publisher-specific route-policy learning engine [Impact: 5/5, Effort: 4/5]
  - Explanation: Learn preferred acquisition strategy per publisher from route history. Hard-route success rates can improve by >10x over static heuristics.
  - Pros: Self-improving acquisition.
  - Cons: Requires policy governance and drift monitoring.
  - Acceptance Criteria:
    - Route outcome history persisted with typed reasons.
    - Planner ranks strategies by historical success.
    - A/B test shows success-rate uplift.

- **Title:** DOM-event quorum stabilization for browser terminal states [Impact: 4/5, Effort: 3/5]
  - Explanation: Replace brittle fixed sleeps with event quorum checks (URL, DOM markers, network). Flaky transient failures can drop by >10x.
  - Pros: More deterministic browser automation.
  - Cons: More instrumentation work.
  - Acceptance Criteria:
    - Stabilization policy codified per route family.
    - Terminal-state logs include quorum evidence.
    - Flake rate reduced in CI/integration runs.

- **Title:** Lightweight pre-browser doc-type predictor [Impact: 4/5, Effort: 2/5]
  - Explanation: Predict direct-PDF opportunities before launching full browser automation. Easy-route latency/cost can improve by >10x.
  - Pros: Fast path for common cases.
  - Cons: Misclassification fallback must be safe.
  - Acceptance Criteria:
    - Predictor score logged with decision reason.
    - False negatives trigger browser fallback.
    - End-to-end timing report shows speed gains.

- **Title:** Failure forensics pack (HAR + DOM + route evidence) [Impact: 3/5, Effort: 3/5]
  - Explanation: Persist standardized forensic artifacts for failed acquisition attempts. MTTR can improve by >10x due to faster debugging.
  - Pros: Better root-cause visibility.
  - Cons: Storage and retention policy overhead.
  - Acceptance Criteria:
    - Failed attempts attach forensic bundle metadata.
    - Logs include artifact links and error class.
    - Triage playbook uses bundle consistently.

- **Title:** Adaptive route switching retries with learned ordering [Impact: 5/5, Effort: 4/5]
  - Explanation: Use dynamic retry sequencing (HTTP -> browser -> email/onsite) based on learned success. Avoids repeated dead-ends and improves success-per-attempt by >10x on gated domains.
  - Pros: Better yield, fewer wasted attempts.
  - Cons: More complex planner and observability needs.
  - Acceptance Criteria:
    - Retry planner supports conditional route switching.
    - Attempt count and route reasons are logged.
    - Candidate cohorts show uplift in download success.

---

## 5) State, Idempotency, and Control-Plane Durability

- **Title:** Event-sourced state transitions with immutable audit log [Impact: 5/5, Effort: 5/5]
  - Explanation: Record each state transition as immutable events to enable deterministic replay and recovery. Debug/recovery effectiveness can improve by >10x.
  - Pros: Strong auditability and replay support.
  - Cons: Migration complexity and storage growth.
  - Acceptance Criteria:
    - Transition events stored append-only with run/task/span.
    - State reconstruction from event stream verified.
    - Replay tool reproduces lifecycle transitions.

- **Title:** Idempotency checksum per orchestrator step [Impact: 5/5, Effort: 3/5]
  - Explanation: Add stable idempotency keys to side-effecting steps so retries cannot duplicate output. Duplicate-side-effect incidents can drop by >10x.
  - Pros: Retry safety, cleaner failure handling.
  - Cons: Requires careful key semantics.
  - Acceptance Criteria:
    - Side-effecting steps persist idempotency key + outcome.
    - Duplicate invocation returns prior outcome.
    - Tests validate no duplicate rows/publications.

- **Title:** Transactional outbox for publish/notification side effects [Impact: 4/5, Effort: 4/5]
  - Explanation: Commit state changes and side-effect intents atomically, dispatch asynchronously. Partial-commit inconsistencies reduce dramatically.
  - Pros: Stronger consistency guarantees.
  - Cons: Additional queue/worker behavior.
  - Acceptance Criteria:
    - Outbox table + dispatcher introduced.
    - Delivery attempts are idempotent and logged.
    - Failure injection tests cover restart/retry behavior.

- **Title:** Checkpoint/restart at semantic pipeline boundaries [Impact: 5/5, Effort: 3/5]
  - Explanation: Resume runs from durable checkpoints after failure instead of full reruns. Late-failure recovery speed can improve by >10x.
  - Pros: Faster recovery, lower rerun cost.
  - Cons: Checkpoint versioning and artifact retention.
  - Acceptance Criteria:
    - Checkpoint contracts defined per stage.
    - Resume command supports selected stage restart.
    - Consistency tests compare full run vs resumed run output.

- **Title:** Dead-letter workflow with typed triage categories [Impact: 4/5, Effort: 3/5]
  - Explanation: Route irrecoverable runs into dead-letter queues with structured diagnosis metadata. Human triage throughput can improve by >10x.
  - Pros: Keeps primary queue healthy.
  - Cons: Needs process ownership.
  - Acceptance Criteria:
    - Dead-letter states and categories defined.
    - Auto-triage metadata includes error taxonomy and stage.
    - Ops dashboards expose dead-letter backlog trend.

---

## 6) Generators, Validation, and Output Correctness

- **Title:** Confidence + abstain mode for evidence/artifact families [Impact: 5/5, Effort: 3/5]
  - Explanation: Permit abstention when confidence is low and trigger targeted regeneration/fallback instead of shipping weak output. High-severity factual defects can drop by >10x.
  - Pros: Better trust profile.
  - Cons: More fallback states and policy decisions.
  - Acceptance Criteria:
    - Confidence score emitted per generated artifact family.
    - Low-confidence policy routes to regeneration or explicit abstain.
    - Validation metrics show reduced unsupported claims.

- **Title:** Ensemble validation (schema + deterministic rules + LLM verifier) [Impact: 5/5, Effort: 4/5]
  - Explanation: Combine orthogonal validators to catch failure modes one validator misses. Defect escape can improve by >10x in noisy data.
  - Pros: Higher robustness.
  - Cons: Additional compute and orchestration complexity.
  - Acceptance Criteria:
    - Multi-validator pipeline implemented with aggregated report.
    - Conflicts between validators are surfaced explicitly.
    - Regression suite demonstrates improved defect detection.

- **Title:** Citation span binding for every non-trivial claim [Impact: 5/5, Effort: 4/5]
  - Explanation: Require claims to carry evidence span references tied to doc_map/page offsets. Hallucination exposure can reduce by >10x.
  - Pros: Auditability and trust.
  - Cons: Requires robust span extraction and mapping.
  - Acceptance Criteria:
    - Claim contracts include span/evidence references.
    - Validation rejects unsupported claims.
    - HTML artifacts render citation micro-lines.

- **Title:** Deterministic failure-to-fix planner for targeted regeneration [Impact: 4/5, Effort: 4/5]
  - Explanation: Convert known validation failure classes into deterministic repair recipes before full regeneration. Repair cycle efficiency can improve by >10x.
  - Pros: Fewer expensive full reruns.
  - Cons: Rule maintenance burden.
  - Acceptance Criteria:
    - Failure taxonomy mapped to repair actions.
    - Repair attempts logged with before/after diffs.
    - Benchmarks show lower regeneration volume.

- **Title:** Prompt A/B harness with offline scored corpora [Impact: 4/5, Effort: 3/5]
  - Explanation: Evaluate prompt variants against fixed corpora with automated scoring, replacing ad hoc tuning. Iteration speed can improve by >10x.
  - Pros: Data-driven prompt tuning.
  - Cons: Needs benchmark dataset ownership.
  - Acceptance Criteria:
    - Harness supports multi-variant runs per namespace.
    - Scorecards include schema-valid + grounding metrics.
    - Promotion policy defined for variant rollout.

---

## 7) Observability, Debugging, and Reproducibility

- **Title:** End-to-end tracing across orchestrator/service boundaries [Impact: 4/5, Effort: 3/5]
  - Explanation: Add distributed traces for timing and dependency visibility. Bottleneck localization speed can improve by >10x.
  - Pros: Better performance diagnostics.
  - Cons: Telemetry overhead and storage planning.
  - Acceptance Criteria:
    - Trace spans created for major pipeline boundaries.
    - Trace IDs correlated with run/task IDs.
    - Dashboard surfaces critical-path timing.

- **Title:** Failure taxonomy anomaly detection [Impact: 4/5, Effort: 4/5]
  - Explanation: Monitor error distributions for unusual spikes by stage/provider/publisher. Early regression detection can improve by >10x.
  - Pros: Proactive reliability management.
  - Cons: False positives during calibration.
  - Acceptance Criteria:
    - Baseline failure distributions established.
    - Drift detector alerts on significant deviations.
    - Alert payload includes likely affected modules.

- **Title:** Deterministic replay command by `run_id` [Impact: 5/5, Effort: 3/5]
  - Explanation: Re-run pipeline using recorded inputs/config/prompts/artifacts for exact reproduction. MTTR often improves by >10x.
  - Pros: Powerful incident response.
  - Cons: Artifact retention and privacy controls required.
  - Acceptance Criteria:
    - Replay CLI/orchestrator path exists.
    - Replay logs compare output deltas against original run.
    - Incident playbook includes replay workflow.

---

## 8) CI/Testing Gates and Quality Integrity

- **Title:** Flaky test detector + quarantine workflow [Impact: 4/5, Effort: 3/5]
  - Explanation: Detect intermittently failing tests and separate them from stable merge gates with owner accountability. CI trust and merge velocity improve by >10x on unstable suites.
  - Pros: Cleaner CI signal.
  - Cons: Requires process and ownership enforcement.
  - Acceptance Criteria:
    - Flake detector records reproducibility rate.
    - Quarantined tests tracked with owner and SLA.
    - Merge gate excludes quarantined tests with explicit reporting.

- **Title:** Performance + cost regression gate for fixture corpus [Impact: 5/5, Effort: 3/5]
  - Explanation: Add budget thresholds for runtime and cost per fixture run. Prevents slow/cost creep; long-term efficiency protection can be >10x.
  - Pros: Sustains performance gains.
  - Cons: Benchmark stability maintenance.
  - Acceptance Criteria:
    - Baseline budgets stored in versioned artifact.
    - CI fails on unapproved regressions.
    - Reports include per-stage deltas.

- **Title:** Nightly chaos/retry/idempotency stress suite [Impact: 4/5, Effort: 4/5]
  - Explanation: Validate behavior under transient failures, lock contention, and retry storms. Incident-rate reduction in production can be substantial.
  - Pros: Realistic reliability hardening.
  - Cons: Infra/runtime cost.
  - Acceptance Criteria:
    - Stress suite includes failure injection scenarios.
    - Attempt counts and backoff decisions asserted.
    - Results feed reliability dashboard.

---

## 9) GitHub Workflow, Review Quality, and Governance

- **Title:** PR quality bot posting schema/coverage/mutation diffs [Impact: 4/5, Effort: 3/5]
  - Explanation: Automate high-signal summary comments on each PR. Reviewer analysis time can improve by >10x for complex diffs.
  - Pros: Faster high-quality reviews.
  - Cons: Bot maintenance and noise tuning.
  - Acceptance Criteria:
    - Bot comment includes risk summary + key deltas.
    - Links to failing gates and artifacts are present.
    - Noise threshold tuned with team feedback.

- **Title:** Monthly quality council with x10 ledger review [Impact: 3/5, Effort: 1/5]
  - Explanation: Track proposal outcomes with metric deltas and prune low-ROI initiatives. Improvement focus and execution consistency can improve dramatically.
  - Pros: Sustained governance discipline.
  - Cons: Requires routine coordination.
  - Acceptance Criteria:
    - Monthly review agenda + owners established.
    - Each initiative reports baseline/current/target metrics.
    - Stalled items are de-scoped or re-planned explicitly.

---

## 10) Release Safety, Operations, and Scale Controls

- **Title:** Canary ingestion/release train with automatic rollback gates [Impact: 5/5, Effort: 4/5]
  - Explanation: Ship changes progressively with health checks and automated rollback on SLO breach. Blast radius reduction can exceed 10x.
  - Pros: Safer production changes.
  - Cons: Deployment orchestration effort.
  - Acceptance Criteria:
    - Canary cohorts and rollback thresholds defined.
    - Rollback triggers on validation/cost/error SLOs.
    - Post-deploy report records canary outcomes.

- **Title:** Dynamic concurrency controller (feedback from queue/failure budget) [Impact: 5/5, Effort: 4/5]
  - Explanation: Adjust concurrency in real time based on queue pressure and error rates. Sustained success under burst load can improve by >10x.
  - Pros: Better throughput stability.
  - Cons: Control-loop tuning complexity.
  - Acceptance Criteria:
    - Controller reads queue depth + recent failure metrics.
    - Concurrency decisions logged with rationale.
    - Load tests show improved stability envelope.

- **Title:** Real-time spend guardrails (run/day/publisher budgets) [Impact: 5/5, Effort: 2/5]
  - Explanation: Enforce hard and soft spend caps with policy outcomes (warn, pause, stop). Worst-case overspend can reduce by >10x.
  - Pros: Strong financial control.
  - Cons: Potentially blocks runs needing override.
  - Acceptance Criteria:
    - Budget policy configured and enforced in orchestrators.
    - Breaches emit typed events and state updates.
    - Override path requires explicit operator action.

- **Title:** Capacity-aware scheduling with fairness by publisher cohort [Impact: 4/5, Effort: 3/5]
  - Explanation: Prevent starvation and over-allocation to noisy cohorts by using fairness-aware scheduling. Completion predictability improves significantly.
  - Pros: Better operational fairness and planning.
  - Cons: Adds scheduler policy complexity.
  - Acceptance Criteria:
    - Scheduling policy includes per-cohort quotas/weights.
    - Starvation and queue age metrics tracked.
    - Simulation tests validate fairness behavior.

- **Title:** Operational runbooks + auto-remediation hooks for top failures [Impact: 4/5, Effort: 2/5]
  - Explanation: Pair typed failure classes with remediation scripts and clear runbooks. Triage/remediation speed can improve by >10x.
  - Pros: Lower MTTR, reduced on-call load.
  - Cons: Needs disciplined upkeep.
  - Acceptance Criteria:
    - Top failure classes mapped to remediation actions.
    - Runbooks linked in alerts/dashboard.
    - Monthly drill verifies runbook freshness.

---

## Priority launch plan (suggested)

### Phase 1 (2-4 weeks)

- #2 semantic response cache
- #3 OCR confidence gating
- #5 idempotency checksum

### Phase 2 (4-8 weeks)

- #2 adaptive model routing
- #3 page triage classifier
- #4 route-policy learning engine
- #5 checkpoint/restart
- #8 performance+cost regression gate

### Phase 3 (8-16+ weeks)

- #2 provider failover seam
- #6 ensemble validation
- #10 canary release train
- #10 dynamic concurrency controller

## Expected aggregate outcomes (if executed with discipline)

- 3x-12x rerun speedups for cache-friendly workloads
- 2x-10x LLM spend reduction on repetitive/regeneration-heavy runs
- 2x-8x acquisition success uplift on difficult publishers
- 5x-15x faster incident diagnosis via replay + richer evidence
- 2x-6x reduction in escaped regressions through risk-weighted gates

## Governance rules for this roadmap

- Each item must have owner + baseline metric + target + expiry date.
- Any >2x claim must include before/after measurement artifacts.
- Items without measurable impact after two review cycles should be deprioritized.
