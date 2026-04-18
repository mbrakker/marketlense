<<<<<<< ours
# Deep Analysis and x10 Improvement Plan (2026-04-15)

## Scope and methodology

This assessment covers the Python monolith under `src/`, CI quality gates under `scripts/ci/`, and supporting docs/process constraints.

Signals used:

1. Architecture contracts and role boundaries from `README.md` and `docs/architecture/role-boundaries.md`.
2. CI gate implementation details from:
   - `scripts/ci/check_coverage.py`
   - `scripts/ci/run_mutation_gate.py`
   - `scripts/ci/check_forbidden_patching.py`
3. Repository scale and concentration analysis from:
   - module counts by layer (`src/contracts`, `src/services`, `src/generators`, `src/orchestrators`, `src/utils`)
   - long-file report from `python scripts/count_long_files.py`

## Current codebase profile (high-level)

- Layer footprint is significant and mature:
  - contracts: 44 files
  - services: 51 files
  - generators: 63 files
  - orchestrators: 23 files
  - utils: 23 files
- Test suite breadth is high (`tests/` has 102 `test_*.py` files), indicating strong regression intent.
- Critical complexity concentration exists in a few very large modules (examples):
  - `src/services/_pdf/figures.py` (~7752 lines)
  - `src/services/report_store_service.py` (~3678 lines)
  - `src/services/publisher_inventory_service.py` (~2819 lines)
  - `src/services/openai_service.py` (~1801 lines)
  - `src/orchestrators/report_analysis_orchestrator.py` (~1306 lines)
  - `src/orchestrators/ingest_orchestrator.py` (~1013 lines)

## Key module opportunities (why x10 is realistic)

1. **PDF extraction pipeline** can unlock x10 throughput/cost improvements via deterministic prefilters, model-call minimization, and cache key hardening because it is one of the largest logic surfaces and likely dominates compute.
2. **OpenAI + LLM service boundaries** can unlock x10 reliability in degraded-provider periods by moving from retry-only behavior to adaptive budget/slo-aware model routing.
3. **Publisher inventory + browser download** can unlock x10 acquisition success for hard routes through route-memory reinforcement and classifier-assisted fallback selection.
4. **Orchestrators/state pipeline** can unlock x10 operational stability by introducing explicit SLO/error-budget control loops and idempotency audits at every transition.
5. **Contracts/validation/logging** can unlock x10 debugging speed with strict event schemas, failure bucketing, and replayable traces.
6. **CI quality system** can unlock x10 confidence-per-change by shifting from static threshold checks to risk-weighted, diff-aware quality gating.

---

## 50 proposals: solutions, approaches, and tooling

> Legend: Effort = S/M/L/XL. Impact = Medium/High/Very High/Transformational.

| # | Key module | Proposal | Why this can improve by >x10 | Effort / Impact | Pros | Cons |
|---|---|---|---|---|---|---|
| 1 | Contracts | Add `schema_version` to every major dataclass contract and reject unknown major versions | Prevents silent drift; compatibility incidents drop dramatically when strict version gates block invalid payloads early | M / Very High | Safer evolution, clear migrations | Requires migration adapters |
| 2 | Contracts | Generate JSON Schema from dataclasses in CI and snapshot diff per PR | Turns schema breakage into compile-time signal; cuts integration breakage detection latency by >x10 | M / High | Deterministic review artifact | Extra CI steps |
| 3 | Contracts | Add `required-field population` invariant checks in constructors (or validators) | Stops sentinel/default leakage that cascades into downstream LLM failures; sharply reduces latent defect propagation | M / Very High | Fails fast, clearer errors | More validation code paths |
| 4 | Contracts | Build contract compatibility matrix tests (N-1, N, N+adapter) | Enables safe rolling upgrades and replay; release safety can improve >x10 for mixed-version runs | L / High | Production-friendly evolution | Adds test maintenance |
| 5 | Contracts | Introduce typed semantic IDs (`ReportId`, `RunId`, `TaskId`) wrappers | Prevents accidental ID mixing, a common source of state corruption; can reduce class of bugs by order-of-magnitude | M / High | Strong compile-time semantics | Refactor breadth |
| 6 | Services / OpenAI | Add adaptive model routing by task criticality + token budget | Uses cheaper/faster models for low-risk steps and premium models only on high-uncertainty steps; cost-per-report can drop >x10 on large volumes | L / Transformational | Massive cost control | Needs robust quality guardrails |
| 7 | Services / OpenAI | Add response cache with semantic key (`prompt_hash + context_hash + model_config`) | Eliminates repeated calls on reruns/regeneration loops; for repeated corpora this yields >x10 token reduction | M / Transformational | Fast reruns, lower spend | Cache invalidation complexity |
| 8 | Services / OpenAI | Implement automatic prompt-minification with token budget planner | Reduces context size before calls; large prompt chains can see >x10 latency/cost gains in worst-case docs | M / High | Direct token savings | Risk of dropping relevant context |
| 9 | Services / OpenAI | Add provider failover abstraction (OpenAI primary, secondary gateway fallback) | During outages, availability can jump >x10 by avoiding single-provider hard failures | L / Very High | Better resilience | Multi-provider complexity |
| 10 | Services / OpenAI | Add structured refusal taxonomy and retry policy by refusal type | Distinguishes transient refusals vs permanent policy refusals; reduces useless retries and failures by large factor | M / High | Cleaner error handling | Needs taxonomy tuning |
| 11 | Services / PDF | Build page triage classifier to skip non-informative pages pre-extraction | Processing only high-value pages can cut expensive extraction by >x10 on long appendices | L / Transformational | Throughput and cost gains | Classifier false negatives risk |
| 12 | Services / PDF | Introduce deterministic content fingerprinting per page/figure | Enables precise cache reuse at sub-document level; avoids full-document recompute, giving >x10 rerun speedups | M / Very High | Fine-grained caching | Fingerprint maintenance |
| 13 | Services / PDF | GPU/parallelizable image preprocessing path behind feature flag | Heavy visual workloads can accelerate by >x10 when parallelized | L / High | Faster candidate extraction | Infra and portability constraints |
| 14 | Services / PDF | Add OCR confidence routing (native text first, OCR only below threshold) | Avoids expensive OCR for extractable docs; OCR spend can drop >x10 in mixed corpora | M / Very High | Cost and latency savings | Confidence calibration needed |
| 15 | Services / PDF | Add table/chart quality scoring model before crop refinement | Prevents low-value candidates from reaching costly steps; increases precision and reduces downstream waste | M / High | Better candidate quality | Requires labeled data |
| 16 | Services / Browser download | Introduce route-policy engine with exploit history (per publisher) | Learns best acquisition path over time; can improve success rate >x10 on previously failing publishers | L / Transformational | Self-improving acquisition | History store + governance |
| 17 | Services / Browser download | Add anti-flake stabilization via DOM event quorum instead of fixed waits | Reduces transient failures from timing races; success on dynamic sites can increase by an order of magnitude | M / Very High | More deterministic browser runs | More runtime instrumentation |
| 18 | Services / Browser download | Add lightweight document-type predictor before browser automation | Skip full browser for direct-PDF candidates; large speedup and cost reduction in easy routes | M / High | Faster happy path | Misclassification risk |
| 19 | Services / Browser download | Add sidecar HAR/network evidence pack for every failed attempt | Debug cycle time can improve >x10 with deterministic forensic evidence | M / High | Better root-cause analysis | Storage growth |
| 20 | Services / Browser download | Implement adaptive retry route switching (HTTP -> browser -> email path) with learned ordering | Avoids repeated dead-end retries; success-per-attempt can improve >x10 on gated ecosystems | L / Very High | Better acquisition yield | More policy complexity |
| 21 | Services / State | Add event-sourced state transitions with append-only audit table | Enables replay and exact transition diagnosis; recovery/debug can improve by >x10 | L / High | Strong auditability | Migration + storage overhead |
| 22 | Services / State | Add idempotency checksum per orchestrator step | Prevents duplicate side effects under retries/concurrency; stability can improve >x10 during incidents | M / Very High | Safe retries | Requires careful key design |
| 23 | Services / State | Add transactional outbox for notifications/publish effects | Eliminates partial-commit inconsistencies; reliability of side effects can improve drastically | L / High | Exactly-once-like behavior | More moving parts |
| 24 | Services / Config | Enforce startup config schema validation with environment profiles | Detects bad config before runtime; incident avoidance improves dramatically | S / High | Fast fail, safer deploys | Stricter startup |
| 25 | Services / Cost ledger | Real-time cost budget guard (per run and per tenant/publisher) | Hard budget stops runaway loops; worst-case spend can shrink >x10 | M / Transformational | Strong cost control | Might stop borderline runs |
| 26 | Generators / Evidence packs | Add confidence scoring + abstain mode per artifact family | Low-confidence outputs route to regeneration or fallback, reducing false facts substantially | M / Very High | Better trustworthiness | More states to manage |
| 27 | Generators / Evidence packs | Build ensemble validation (rules + LLM verifier + schema cross-check) | Layered verification catches different failure classes; quality uplift can exceed x10 in noisy domains | L / Transformational | Robust correctness | Higher compute unless optimized |
| 28 | Generators / Taxonomy | Add hierarchical taxonomy with contradiction checks | Reduces inconsistent tagging and improves retrieval relevance by large factor | M / High | Better discoverability | Requires taxonomy governance |
| 29 | Generators / Artifacts | Add strict citation span linking to doc_map sentence offsets | Hallucination exposure drops when every claim binds to spans; trust can improve >x10 | L / Very High | Auditable outputs | More extraction complexity |
| 30 | Generators / Validation | Introduce failure-to-fix planner (deterministic patch recipes) | Converts validation errors into targeted deterministic repairs; regeneration efficiency can improve by >x10 | L / Very High | Fewer full regenerations | Recipe maintenance |
| 31 | Generators / Prompt prep | Add automatic prompt A/B harness with offline scorecards | Prompt iteration speed can improve >x10 versus manual trial-and-error | M / High | Faster quality tuning | Needs benchmark corpus |
| 32 | Generators / Figure captions | Add multimodal caption verifier against nearby text + OCR | Reduces misleading captions significantly; precision can improve by order-of-magnitude in edge cases | M / High | Better visual trust | Extra inference cost |
| 33 | Orchestrators | Add per-step SLO and error budget enforcement | Makes retries budget-aware; prevents tail-latency blowups and increases stable throughput >x10 in overload | M / Very High | Predictable operations | Policy tuning required |
| 34 | Orchestrators | Introduce dynamic concurrency controller (queue depth + failure rate feedback) | Adapts throughput to environment; can improve sustained success by >x10 during burst load | L / Transformational | Better utilization and stability | Complexity in control logic |
| 35 | Orchestrators | Add checkpoint/restart at semantic boundaries | Avoids restarting entire pipeline after late failures; rerun time can drop >x10 | M / Very High | Faster recovery | Checkpoint compatibility work |
| 36 | Orchestrators | Standardize retry reason codes and backoff telemetry | Turns retry tuning into data science instead of guesswork; tuning speed improves dramatically | S / High | Better observability | Requires logging discipline |
| 37 | Orchestrators | Add dead-letter workflow for irrecoverable runs with auto triage labels | Keeps queues healthy and reduces human triage load by order-of-magnitude | M / High | Cleaner operations | Additional queue/process |
| 38 | Orchestrators | Add deterministic replay command (`run_id` -> reproduce path) | MTTR can improve >x10 when incidents are replayable end-to-end | M / Very High | Powerful debugging | Needs artifact retention policy |
| 39 | Observability | Define unified event schema + JSON log validator in CI | Prevents logging drift and missing fields; diagnosis reliability improves drastically | M / Very High | Structured debugging at scale | More schema maintenance |
| 40 | Observability | Add OpenTelemetry traces across orchestrator/service boundaries | Distributed timing insight can improve bottleneck discovery >x10 | M / High | Better performance tuning | Tracing overhead |
| 41 | Observability | Build run health scorecard (latency, cost, validation, retries) | Gives single-pane stability view; operations decisions become much faster | M / High | Better prioritization | Requires aggregation jobs |
| 42 | Observability | Add automatic anomaly detection on failure taxonomies | Early warning catches regressions before large fallout; prevention leverage can be >x10 | L / High | Proactive alerting | False positives initially |
| 43 | CI / Testing | Add diff-aware risk gate: stricter thresholds on touched critical modules | Raises confidence where it matters most; escaped defects in hot paths can drop >x10 | M / Very High | Smarter quality gating | More CI logic |
| 44 | CI / Testing | Add flaky-test detector with quarantine + owner enforcement | Stabilizes CI signal/noise ratio; developer productivity can improve >x10 on unstable suites | M / High | Faster trusted merges | Requires process discipline |
| 45 | CI / Testing | Add nightly stress/pipeline chaos tests for retry/idempotency | Hardens reliability under adverse conditions; incident frequency can fall by large factor | L / High | Realistic resilience testing | Longer infra/runtime cost |
| 46 | CI / Testing | Add performance regression gate (time + cost budgets per fixture corpus) | Prevents silent slowdowns/spend creep; protects x10 efficiency gains over time | M / Very High | Continuous guardrails | Benchmark maintenance |
| 47 | DevEx / GitHub | Add CODEOWNERS by bounded context + mandatory architecture checklist | Review quality scales with ownership clarity; architectural regressions can reduce >x10 | S / High | Better accountability | More reviewer coordination |
| 48 | DevEx / GitHub | Add PR bot that posts contract/schema/coverage/mutation diff summary | Review throughput and defect detection speed can improve by order-of-magnitude | M / High | Better reviewer context | Bot implementation effort |
| 49 | DevEx / GitHub | Add architectural linter for cross-layer import rules | Prevents role-boundary drift automatically; avoids costly refactor debt | M / Very High | Enforces constitution in code | Requires custom lint rules |
| 50 | DevEx / GitHub | Add release train with canary ingestion + automatic rollback gates | Production stability improves >x10 by limiting blast radius and rapid rollback | L / Transformational | Safer deployments | Requires deployment orchestration |

---

## Priority roadmap (recommended)

### Phase 1 (2-4 weeks, high ROI)

- #7 response cache
- #14 OCR confidence routing
- #22 idempotency checksum
- #33 per-step SLO/error budgets
- #43 diff-aware risk gate
- #49 architectural linter

### Phase 2 (4-8 weeks)

- #6 adaptive model routing
- #11 page triage classifier
- #16 route-policy engine
- #35 checkpoint/restart
- #46 performance + cost regression gates

### Phase 3 (8-16+ weeks)

- #9 provider failover
- #27 ensemble validation
- #34 dynamic concurrency controller
- #50 canary + rollback release train

## Expected aggregate outcomes

If phases are implemented with proper guardrails, realistic aggregate gains are:

- 3x-12x faster reruns for cache-friendly workloads
- 2x-10x lower model spend (higher on repetitive/regeneration-heavy runs)
- 2x-8x higher acquisition success on difficult publishers
- 5x-15x faster incident diagnosis (replayable traces + richer evidence)
- 2x-6x fewer escaped regressions via risk-weighted CI and architecture linting

## Risks to manage

- Over-optimization may increase complexity: enforce incremental rollout + feature flags.
- ML/classifier additions require calibration datasets and regular drift checks.
- Stronger gates may slow short-term delivery if introduced all at once.

## Suggested governance

- Track every proposal with: owner, metric baseline, target delta, and kill criteria.
- Require before/after metrics for any claim above 2x.
- Keep a monthly “x10 ledger” with wins, misses, and de-scoped experiments.
=======
# Deep Analysis and x10 Improvement Plan (2026-04-17)

Last updated: 2026-04-17

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

- **Title:** Enforce mandatory `schema_version` on all external contracts [Impact: 5/5, Effort: 3/5]
  - Explanation: Add explicit contract versioning and reject unknown major versions at boundaries. This removes silent contract drift and prevents bad payloads from propagating; compatibility incident rate can drop by >10x in mixed deployments.
  - Pros: Safer upgrades, explicit migration points, better forensic traceability.
  - Cons: Requires migration adapters and rollout coordination.
  - Acceptance Criteria:
    - All external-facing contracts carry `schema_version`.
    - Services reject unsupported major versions with typed `AppError`.
    - Compatibility tests cover N-1/N behavior.

- **Title:** Generate and snapshot JSON Schema for dataclasses in CI [Impact: 4/5, Effort: 3/5]
  - Explanation: Auto-generate schemas and diff them per PR. Breaking changes become visible in code review, reducing late-stage integration failures by >10x.
  - Pros: Deterministic artifact diffs, review-time safety.
  - Cons: Requires schema generation tooling and snapshots upkeep.
  - Acceptance Criteria:
    - CI job emits schema artifacts per contract module.
    - PR fails on unapproved schema breakage.
    - Approved schema changes include migration notes.

- **Title:** Add required-field population guards for contract construction [Impact: 5/5, Effort: 2/5]
  - Explanation: Enforce non-empty semantics for required fields at adaptation boundaries so sentinel/default leakage cannot pass silently. This can reduce downstream validation failures by >10x.
  - Pros: Fail-fast behavior, clearer defects.
  - Cons: Stricter behavior may surface existing hidden data gaps.
  - Acceptance Criteria:
    - Shared helper validates required fields by contract.
    - Missing required fields raise typed `AppError`.
    - Tests assert no default/sentinel-filled required outputs.

- **Title:** Build backward/forward compatibility test matrix [Impact: 4/5, Effort: 4/5]
  - Explanation: Add compatibility tests for current and previous contract versions to protect rolling runs. Release safety improves dramatically compared with single-version-only tests.
  - Pros: Upgrade confidence, safer phased deploys.
  - Cons: Larger test surface and fixtures.
  - Acceptance Criteria:
    - Contract compatibility suites run in CI.
    - Adapter logic covered with positive + negative cases.
    - Breaking changes require explicit version bump evidence.

- **Title:** Introduce typed semantic IDs (`RunId`, `TaskId`, `ReportId`) [Impact: 3/5, Effort: 3/5]
  - Explanation: Replace free-form string IDs with typed wrappers to prevent accidental ID mixing. This class of corruption bugs can reduce by >10x.
  - Pros: Stronger semantics, safer refactors.
  - Cons: Broad signature changes across modules.
  - Acceptance Criteria:
    - Shared ID contracts introduced and adopted in core paths.
    - Mixed-ID misuse triggers typing or runtime validation failure.
    - Orchestrator/state tests cover ID round-trips.

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

- **Title:** Unified event schema with CI log-shape validation [Impact: 5/5, Effort: 3/5]
  - Explanation: Standardize event fields and validate emitted logs in tests. Missing-context debugging failures can reduce by >10x.
  - Pros: Consistent observability.
  - Cons: Requires strict logging discipline.
  - Acceptance Criteria:
    - Event schema includes run/task/span/module/role/event.
    - CI test validates representative logs against schema.
    - Missing required fields fail tests.

- **Title:** End-to-end tracing across orchestrator/service boundaries [Impact: 4/5, Effort: 3/5]
  - Explanation: Add distributed traces for timing and dependency visibility. Bottleneck localization speed can improve by >10x.
  - Pros: Better performance diagnostics.
  - Cons: Telemetry overhead and storage planning.
  - Acceptance Criteria:
    - Trace spans created for major pipeline boundaries.
    - Trace IDs correlated with run/task IDs.
    - Dashboard surfaces critical-path timing.

- **Title:** Run health scorecards (latency/cost/retries/validation) [Impact: 4/5, Effort: 2/5]
  - Explanation: Produce one scorecard per run for immediate operational triage. Decision speed and issue detection improve significantly.
  - Pros: Fast operator insight.
  - Cons: Needs clear threshold definitions.
  - Acceptance Criteria:
    - Scorecards produced for ingest/report/publish flows.
    - Threshold breaches generate typed warnings.
    - Historical trends available for comparison.

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

- **Title:** Diff-aware risk gate for touched critical modules [Impact: 5/5, Effort: 3/5]
  - Explanation: Apply stricter quality thresholds when high-risk paths change (orchestrators/generators/services). Escaped regressions can reduce by >10x.
  - Pros: Better signal where it matters.
  - Cons: More CI policy complexity.
  - Acceptance Criteria:
    - Changed-file risk classification implemented.
    - Coverage/mutation floors increase on critical diffs.
    - CI output explains triggered risk policies.

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

- **Title:** Contract round-trip + schema-validation gate expansion [Impact: 4/5, Effort: 2/5]
  - Explanation: Enforce serialization/deserialization equivalence and schema validation for changed contracts by default. Contract bugs become much harder to ship.
  - Pros: Strong contract integrity.
  - Cons: Additional fixture maintenance.
  - Acceptance Criteria:
    - Changed contract files trigger round-trip tests.
    - Schema-backed payloads validated in CI.
    - Failures report exact field/path differences.

---

## 9) GitHub Workflow, Review Quality, and Governance

- **Title:** CODEOWNERS by bounded context + architecture checklist [Impact: 4/5, Effort: 1/5]
  - Explanation: Enforce expert review on sensitive modules and require role-boundary checklist completion. Architectural regressions can reduce by >10x.
  - Pros: Better review quality and accountability.
  - Cons: Potentially slower review queues initially.
  - Acceptance Criteria:
    - CODEOWNERS covers core contexts.
    - PR template includes architecture checklist.
    - Merge policy requires checklist completion.

- **Title:** PR quality bot posting schema/coverage/mutation diffs [Impact: 4/5, Effort: 3/5]
  - Explanation: Automate high-signal summary comments on each PR. Reviewer analysis time can improve by >10x for complex diffs.
  - Pros: Faster high-quality reviews.
  - Cons: Bot maintenance and noise tuning.
  - Acceptance Criteria:
    - Bot comment includes risk summary + key deltas.
    - Links to failing gates and artifacts are present.
    - Noise threshold tuned with team feedback.

- **Title:** Architectural import-rule linter (cross-layer drift guard) [Impact: 5/5, Effort: 3/5]
  - Explanation: Statically block forbidden reverse imports/role mixing. Prevents drift and expensive cleanup, often by an order-of-magnitude.
  - Pros: Enforces constitution automatically.
  - Cons: Rule edge cases need careful handling.
  - Acceptance Criteria:
    - Linter blocks forbidden import directions.
    - CI failure points to offending module and rule.
    - Exception process is explicit and auditable.

- **Title:** Risk-tiered merge requirements (tests/gates by change class) [Impact: 4/5, Effort: 2/5]
  - Explanation: Scale merge requirements with risk level (docs, low-risk code, critical pipeline code). Maintains speed without sacrificing safety.
  - Pros: Balanced velocity and quality.
  - Cons: Requires clear and trusted risk taxonomy.
  - Acceptance Criteria:
    - Risk classes documented with required gates.
    - PRs auto-classified from file patterns.
    - Enforcement is visible in GitHub checks.

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
- #7 unified event schema
- #8 diff-aware risk gate
- #9 architecture import linter

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
>>>>>>> theirs
