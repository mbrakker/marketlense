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
