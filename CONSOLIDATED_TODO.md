# Consolidated TODO

Last compiled: 2026-05-01

This file is the single source of truth for open backlog items. It supersedes the remaining backlog plus the archived planning work from `docs/quality/deep-analysis-x10-plan-2026-04-15.md`.

Items below were re-based against the current repository state, not against earlier planning assumptions. Completed or materially landed capabilities are removed from the active backlog. Partially landed capabilities stay only when there is a clear remaining gap.

Deep-analysis evidence used for this consolidation:

- Architecture import gate passed on 2026-05-01: `python scripts/ci/check_architecture_imports.py`.
- Forbidden patching gate passed on 2026-05-01: `python scripts/ci/check_forbidden_patching.py`.
- CI already runs formatting, typing, architecture-import, forbidden-patching, repository-hygiene, quality-ledger, remediation-runbook, backlog-source, contract-schema, coverage, mutation, quality-regression, and prompt-fixture regression gates through `.github/workflows/ci.yml`.
- Prompt dry-run infrastructure and fixture-corpus regression are already landed through `src/contracts/prompts.py`, `src/services/prompt_service.py`, `scripts/ci/check_prompt_fixture_regression.py`, `tests/test_prompt_dry_run_validation.py`, and `tests/test_prompt_fixture_corpus_regression.py`.
- `docs/quality/initiative_ledger.yaml` now marks `ocr-confidence-gating` as completed. Native-text confidence thresholds and OCR fallback controls already exist in `src/config/app.yaml` and `src/generators/report_source_generator.py`.
- Publisher-discovery typed route traces, scenario summaries, deferred recovery recipes, recovery-cache persistence, and direct-detail handling are already landed in code, tests, and docs, but rollout flags remain disabled by default in `src/config/app.yaml`.
- Targeted validation regeneration and claim/evidence binding are already landed through `src/generators/report_regeneration_generator.py`, `src/generators/validation/*`, and the current README validation sections.
- `src/services/idempotency_service.py` is already live and now backs the publish boundary plus the remaining side-effecting write steps in `report_download_orchestrator` and `publisher_inventory_orchestrator`, with checksum/outcome/artifact-reference persistence documented in `README.md`.
- Candidate extraction already performs binary page triage and shared page-artifact/fingerprint caching through `src/services/_pdf/figures.py`, `src/services/_pdf/page_artifacts.py`, and `src/services/_pdf/fingerprint_cache.py`.
- `src/services/llm_service.py` still logs `provider_decision="openai_primary"` and `budget_decision="not_configured"`, which is the strongest current signal that dynamic routing, provider failover, and spend-aware policy are still missing.
- `src/services/vector_store_service.py` supports create/upload/attach/status/update, but delete/prune lifecycle operations are still absent.
- Long-file concentration shifted after April refactors. Current first-party hotspots from `python scripts/count_long_files.py` are `src/services/_browser_report_download/artifact.py`, `src/services/_browser_report_download/browser.py`, `src/services/_pdf/table_heuristics.py`, `src/services/config_service.py`, `src/generators/artifact_generator.py`, `src/services/publisher_inventory_service.py`, `src/services/openai_service.py`, `src/orchestrators/report_download_orchestrator.py`, `src/services/_pdf/crop.py`, and large paired tests.
- Recent facade splits establish the required shape for the remaining hotspot work: keep one public boundary file and move semantic families into a same-name internal folder. Current reference examples are `src/services/report_store_service.py` over `src/services/_report_store_service/*` and `src/generators/report_generation_dependencies.py` over `src/generators/_report_generation_dependencies/*`.

Removed from the active backlog because the core capability already ships:

- OCR confidence gating and native-confidence-based OCR fallback controls.
- Prompt dry-run namespace validation scaffolding and prompt-fixture corpus regression baseline.
- Targeted artifact regeneration for mapped validation failures, including deterministic TOC repair.
- Claim/evidence span binding and validation-level evidence normalization.
- Core publisher-discovery memory/recovery/direct-detail implementation work.
- Report-store and report-generation dependency facade splits.
- UI-run dead-letter workflow, replay manifests, and operator triage surfaces.

How to use this backlog:

- Treat this file as the only active TODO source.
- Remove items once their acceptance criteria are fully met.
- Keep overlapping work merged into one item with explicit source notes in the explanation when needed.
- Every prioritized item must get an owner, baseline metric, target metric, and expiry/review date before implementation starts.

Scoring rubric:

- `Impact`: `1` low leverage, `5` highest leverage across reliability, quality, cost, speed, or architecture.
- `Effort`: `1` localized change, `5` broad refactor/migration with cross-module coordination.

Suggested priority order:

1. `1. Spend Guardrails, LLM Routing & Prompt Evaluation`
2. `4. Publisher Discovery Rollout & Precision`
3. `5. Idempotency, Checkpoints & Publish Durability`
4. `3. PDF Extraction, OCR & Candidate Ranking`
5. `7. Architecture Simplification, CI & Observability`

---

## 1. Spend Guardrails, LLM Routing & Prompt Evaluation

- **Title:** Extend the prompt fixture corpus into variant-aware promotion scorecards [Impact: 4/5, Effort: 4/5]
  - Explanation: The repo already validates active namespaces and measures the prompt fixture corpus, but only for the currently active template pair per namespace. The remaining gap is controlled prompt variants, deterministic selection, offline scorecards, and promotion policy.
  - Pros: Safer prompt iteration, measurable quality/cost tradeoffs, cleaner rollouts.
  - Cons: More benchmark maintenance and CI/runtime cost.
  - Acceptance Criteria:
    - Config supports multiple named variants per prompt namespace.
    - Prompt selection is deterministic and logged with namespace, variant, hashes, rendered prompts, model parameters, and cost data.
    - Corpus metrics are emitted per namespace plus variant, not only per namespace.
    - Promotion policy defines when a variant can replace the default.

- **Title:** Implement budget-aware model routing with deterministic context compaction [Impact: 5/5, Effort: 4/5]
  - Explanation: Model resolution is still mostly static through `openai_models` and namespace matching, while `llm_service` logs `budget_decision="not_configured"`. The next step is policy-driven model tiering, context budgeting, and deterministic compaction before requests exceed practical token or cost limits.
  - Pros: Material cost and latency reduction, fewer timeout risks, explicit quality/cost tradeoffs.
  - Cons: Requires careful evidence-retention tests and benchmark ownership.
  - Acceptance Criteria:
    - Policy table maps task families to model tier, max input budget, fallback tier, and quality threshold.
    - Routing decision, budget decision, compaction strategy, and reason are logged for each call.
    - Over-budget requests are compacted by deterministic policy rather than ad hoc trimming.
    - Regression tests protect key evidence retention.
    - Benchmarks show meaningful token/cost reduction without quality regression on a fixed corpus.

- **Title:** Add provider failover behind one LLM response contract [Impact: 5/5, Effort: 5/5]
  - Explanation: Production report generation still depends on one OpenAI-backed LLM path even though other repo areas know about OpenRouter/browser-provider settings. The missing piece is a provider-agnostic generator contract plus orchestrated primary/secondary failover for report-pipeline LLM work.
  - Pros: Higher availability during provider incidents and cleaner provider isolation.
  - Cons: More integration-test surface and normalized error-handling complexity.
  - Acceptance Criteria:
    - Primary and secondary provider policy is explicit and tested.
    - Provider responses and errors are normalized into one typed generator-facing contract.
    - Generators do not branch on provider-specific response shapes.
    - Failure-injection tests prove logged failover behavior and successful fallback.

- **Title:** Enforce real-time spend guardrails across run/day/publisher budgets [Impact: 5/5, Effort: 2/5]
  - Explanation: Cost ledger append and rollup paths exist, but they are post-hoc reporting only. There is still no pre-call policy that warns, pauses, or blocks expensive model/browser/OCR work based on live spend.
  - Pros: Prevents runaway spend and makes cost decisions operationally visible.
  - Cons: May block legitimate runs without a good override flow.
  - Acceptance Criteria:
    - YAML config defines thresholds for run, day, and publisher scopes.
    - Orchestrators check thresholds before model, browser, OCR, or other expensive calls.
    - Breaches emit typed events, structured logs, and explicit policy outcome (`warn`, `pause`, `stop`, `override`).
    - Tests cover warn, hard-stop, and operator-override paths.

---

## 2. Resource Lifecycle & Vector Stores

- **Title:** Add vector-store deletion, prune, and retention cleanup [Impact: 3/5, Effort: 3/5]
  - Explanation: The vector-store boundary currently covers create/upload/attach/status/update, but not retention cleanup. `analysis.vector_store_keep` can express intent, yet no canonical delete/prune path exists to clean up remote assets deterministically.
  - Pros: Avoids orphaned remote storage and repeated provider cost.
  - Cons: Risk of deleting useful assets if retention policy is wrong; requires strong idempotency.
  - Acceptance Criteria:
    - Delete and prune request/response dataclass contracts exist.
    - `vector_store_service` exposes canonical delete/prune operations with structured logging.
    - Orchestrators run cleanup when retention is disabled or expiry is reached.
    - Tests cover missing remote assets, duplicate cleanup calls, and retention-disabled runs.

---

## 3. PDF Extraction, OCR & Candidate Ranking

- **Title:** Upgrade binary page triage into scored, recall-calibrated page gating [Impact: 5/5, Effort: 4/5]
  - Explanation: Candidate extraction already skips obvious full-page-scan/no-text negatives and excludes contents pages. The remaining gap is richer page-value scoring before chart/table extraction and crop refinement so expensive PDF work is reduced with measurable recall protection.
  - Pros: Better throughput on large reports and fewer wasted extraction passes.
  - Cons: False negatives become dangerous if scoring is aggressive or poorly calibrated.
  - Acceptance Criteria:
    - Per-page triage reason and score are logged.
    - Thresholds and skip policy are configurable.
    - Evaluation fixtures define a recall floor that the triage gate must preserve.
    - Stage metrics show extraction work avoided without quality regression.

- **Title:** Fix the table dedupe hot path in `table_candidates.py` and `table_heuristics.py` [Impact: 4/5, Effort: 3/5]
  - Explanation: Table extraction still performs nested candidate comparison in the final dedupe path, and the deeper heuristics module remains one of the largest first-party hotspots. Replace the O(n^2)-style merge path with a keyed or spatially indexed approach while preserving conservative merge behavior.
  - Pros: Faster processing on dense and wide PDFs.
  - Cons: Requires careful correctness tests to avoid false merges or missed duplicates.
  - Acceptance Criteria:
    - Dedupe logic is rewritten around an indexed candidate lookup instead of repeated full scans.
    - Benchmarks on large fixtures show lower runtime.
    - Correctness tests cover near-duplicate, overlapping, and distinct-table cases.
    - Candidate quality does not regress on existing fixture reports.

---

## 4. Publisher Discovery Rollout & Precision

- **Title:** Promote structured discovery memory, deferred recovery, and direct-detail routing from gated code to measured defaults [Impact: 5/5, Effort: 3/5]
  - Explanation: Typed route traces, scenario summaries, deferred recovery recipes, recovery-cache persistence, and direct-detail routing already exist, but the rollout flags `enable_deferred_candidate_recovery`, `enable_structured_route_reuse`, and `enable_preflight_classifier_and_direct_detail` remain disabled by default in `src/config/app.yaml`.
  - Pros: Unlocks already-built acquisition improvements and reduces repeated exploratory browser churn.
  - Cons: Needs KPI guardrails so memory or rescue logic does not broaden false positives.
  - Acceptance Criteria:
    - Each flag has a documented canary sequence, KPI set, and rollback condition.
    - Logs and run-quality outputs surface scenario, memory, and recovery decisions clearly.
    - Default-on criteria are defined and tested against representative publishers.
    - README and the discovery playbook are updated when rollout state changes.

- **Title:** Reduce low-yield browser-to-HTTP recovery and mixed-content false positives [Impact: 4/5, Effort: 3/5]
  - Explanation: The current discovery playbook shows the remaining waste is not missing core traversal mechanics; it is spending effort on candidates that later die in qualification or route recovery. Recovery triggers and source-surface precision still need tightening.
  - Pros: Higher yield per browser attempt and cleaner quality gates on mixed-content hubs.
  - Cons: Too much tightening could suppress legitimate rescues.
  - Acceptance Criteria:
    - Recovery attempts and outcomes are logged by typed recovery class.
    - Trigger policy blocks low-yield recovery paths that do not add signal.
    - Sampled runs show lower recovery miss rate without a rise in editorial/service false positives.
    - Tests assert which recovery classes are allowed, blocked, or deferred.

---

## 5. Idempotency, Checkpoints & Publish Durability

- **Title:** Introduce durable, checkpointed pipeline stages with semantic restart [Impact: 5/5, Effort: 5/5]
  - Explanation: Replay manifests exist for UI runs, but the report pipeline itself still resumes by rerunning whole stages rather than restarting from durable semantic checkpoints with artifact references.
  - Pros: Faster recovery, lower rerun cost, better operator control.
  - Cons: Requires checkpoint versioning, storage modeling, and migration discipline.
  - Acceptance Criteria:
    - Checkpoint contracts exist for major pipeline stages.
    - Stage checkpoints store artifact references plus schema versions.
    - Resume tooling supports restarting from a selected stage boundary.
    - Consistency tests compare full-run output with resumed-run output.

- **Title:** Turn the publish queue into durable jobs with transactional outbox, retry, and idempotency [Impact: 5/5, Effort: 5/5]
  - Explanation: The current `publish_queue_orchestrator.py` only builds a snapshot for UI and ops views. It does not persist publish intents as durable jobs or atomically couple publish-side effects to state transitions.
  - Pros: More reliable publishing and clearer recovery from partial failures.
  - Cons: Adds queue/outbox infrastructure and operational behavior.
  - Acceptance Criteria:
    - Publish jobs can be enqueued, persisted, retried, and dead-lettered.
    - Outbox records side-effect intents atomically with related state changes.
    - Delivery attempts are idempotent and logged.
    - Failure-injection tests cover restart, retry, duplicate dispatch, and partial WordPress failures.

---

## 6. Schema Compatibility & Repair

- **Title:** Build a backward/forward contract compatibility matrix [Impact: 4/5, Effort: 4/5]
  - Explanation: Contract round-trip tests and schema snapshots already exist, but the repo still lacks a first-class compatibility matrix for persisted artifacts and stored rows across schema versions.
  - Pros: Safer staged deploys and clearer breaking-change discipline.
  - Cons: Larger fixture surface and more adapter maintenance.
  - Acceptance Criteria:
    - Compatibility suites run in CI for representative current and previous contract versions.
    - Adapter or migration logic has positive and negative tests.
    - Breaking changes require explicit version-bump evidence.
    - Representative stored artifacts are covered by fixture snapshots.

- **Title:** Expand targeted regeneration beyond the current artifact-family repair map [Impact: 4/5, Effort: 4/5]
  - Explanation: Targeted regeneration already handles mapped artifact families and deterministic TOC repair. The remaining gap is broader pack-level or rule-specific repair routing so more validation failures can be fixed without broad reruns.
  - Pros: Fewer full reruns and clearer repair behavior.
  - Cons: Repair-taxonomy maintenance burden.
  - Acceptance Criteria:
    - Failure classes map to explicit repair actions beyond the current artifact-family set.
    - Repair attempts log before/after diffs and the exact regenerated artifacts or packs.
    - Benchmarks show lower full-regeneration volume on known failure fixtures.
    - Negative-path tests prove unsupported repair targets fail explicitly.

---

## 7. Architecture Simplification, CI & Observability

- **Title:** Split current first-party long-file hotspots into facade plus semantic-family folders without breaking canonical boundaries [Impact: 5/5, Effort: 4/5]
  - Explanation: April facade refactors already removed some earlier hotspots, but the remaining first-party heavy files are still large enough to slow review and encourage role drift. The required split pattern is now explicit: keep the original module path as the only public facade, create a same-name internal folder, and move internals into semantic family files instead of creating competing peer entrypoints.
  - Pros: Lower cognitive load, tighter role boundaries, easier testing.
  - Cons: Large refactors can destabilize import surfaces if done carelessly.
  - Acceptance Criteria:
    - Public facades remain singular and discoverable, and callers continue importing only the original public boundary.
    - Each split candidate uses the same-name family-folder pattern:
      `src/services/config_service.py` stays as a facade and `src/services/_config_service/*` holds semantic families; `src/generators/artifact_generator.py` maps to `src/generators/_artifact_generator/*`; `src/orchestrators/report_download_orchestrator.py` maps to `src/orchestrators/_report_download_orchestrator/*`.
    - `config_service` is split by semantic resolver families rather than by arbitrary file size, with a target shape like `paths.py`, `ingest.py`, `openai.py`, `browser_download.py`, `publisher_discovery.py`, `publish.py`, and `validation.py` under `src/services/_config_service/`, while `src/services/config_service.py` stays facade-only.
    - The same facade-plus-family-folder rule is applied to the remaining named hotspots that still act as concentration points: `publisher_inventory_service`, `openai_service`, `artifact_generator`, `report_download_orchestrator`, `publish_orchestrator`, `report_analysis_orchestrator`, `analytics_store_service`, `sqlite_migration_service`, `drive_service`, `run_registry_service`, and `wordpress_service`.
    - Already-internal hotspot modules are split one level deeper by family without changing their canonical boundary path, for example `src/services/_browser_report_download/browser.py` plus `src/services/_browser_report_download/_browser/*`, `src/services/_browser_report_download/artifact.py` plus `src/services/_browser_report_download/_artifact/*`, and `src/services/_pdf/table_heuristics.py` plus `src/services/_pdf/_table_heuristics/*`.
    - README architecture notes are updated for every new facade/internal-family split.
    - `python scripts/count_long_files.py` shows a material reduction in first-party hotspot concentration.

- **Title:** Extend CI gates from current quality coverage into role-mixing and monolith-growth enforcement [Impact: 4/5, Effort: 3/5]
  - Explanation: The repo already has strong CI coverage, so the remaining gap is not "add more generic checks." The useful next step is automation around role mixing, direct-I/O drift, service integration coverage waivers, and first-party long-file growth.
  - Pros: Prevents architectural drift earlier and keeps the current rule set enforceable.
  - Cons: Requires careful allowlist design for legitimate edge cases.
  - Acceptance Criteria:
    - New gate logic flags role mixing, direct I/O drift, or monolith-growth violations on first-party files.
    - Allowlist entries require owner plus expiry date.
    - Missing per-service integration coverage requires either a marked test or an explicit temporary waiver.
    - README documents how to add and retire waivers.

- **Title:** Add end-to-end tracing above current `run_id` / `task_id` / `span_id` logging [Impact: 4/5, Effort: 3/5]
  - Explanation: Structured logs are already strong, but there is still no true cross-boundary trace model for critical-path timing, dependency edges, or flame-graph style analysis.
  - Pros: Faster bottleneck localization and better incident debugging.
  - Cons: Telemetry overhead and storage planning.
  - Acceptance Criteria:
    - Trace IDs and nested spans correlate with existing structured logs.
    - Major orchestrator, generator, and service boundaries emit consistent tracing metadata.
    - Operators can inspect one report or publisher run as a trace rather than stitching logs manually.

---

## Priority Launch Plan

### Phase 1: Highest-Leverage Controls (2-4 weeks)

- Real-time spend guardrails at run/day/publisher scopes with explicit override flow.
- Discovery rollout of structured memory, deferred recovery, and direct-detail routing with KPI gates.
- Prompt variant scorecards on top of the existing prompt-fixture corpus.

### Phase 2: Throughput and Durability (4-8 weeks)

- Budget-aware model routing with deterministic context compaction.
- Scored PDF page gating and table-dedupe rewrite.
- Vector-store cleanup and retention orchestration.
- First-party hotspot splits using one public facade plus same-name semantic-family folders for `config_service`, `publisher_inventory_service`, `openai_service`, `artifact_generator`, `report_download_orchestrator`, `publish_orchestrator`, `report_analysis_orchestrator`, `analytics_store_service`, `sqlite_migration_service`, `drive_service`, `run_registry_service`, `wordpress_service`, and browser-download/PDF extraction internals.

### Phase 3: Resilience and Compatibility (8-16+ weeks)

- Provider failover behind one LLM response contract.
- Durable checkpoint/restart for report pipeline stages.
- Durable publish jobs with transactional outbox.
- Contract compatibility matrix for persisted artifacts and stored rows.
- End-to-end tracing across orchestrator/generator/service boundaries.
