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
- Long-file concentration shifted after April refactors and the May facade work. Remaining first-party hotspots from `python scripts/count_long_files.py` are concentrated in deeper PDF/browser internals, publisher-discovery workflow internals, and large paired tests rather than the public `config_service`, `openai_service`, `artifact_generator`, `publisher_inventory_service`, and `report_download_orchestrator` boundaries.
- Recent facade splits establish the required shape for future hotspot work: keep one public boundary file and move semantic families into a same-name internal folder. Current reference examples are `src/services/report_store_service.py` over `src/services/_report_store_service/*`, `src/generators/report_generation_dependencies.py` over `src/generators/_report_generation_dependencies/*`, `src/services/config_service.py` over `src/services/_config_service/*`, `src/services/openai_service.py` over `src/services/_openai_service/*`, and `src/generators/artifact_generator.py` over `src/generators/_artifact_generator/*`.

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

- **Title:** Add bounded persistent browser-session reuse for developer canaries and same-publisher batches [Impact: 4/5, Effort: 3/5]
  - Explanation: Confirmed useful but must be bounded. `browser-harness` relies on persistent real-browser sessions for speed and continuity, while Marketlense production currently favors isolated managed profiles. Copy/adapt the existing `browser-harness` session-reuse discipline into Marketlense's browser-use integration only for developer mode, canary runs, or same-publisher batches with explicit session keys, TTLs, and cleanup. Do not create a separate session manager from scratch.
  - Pros: Reduces startup overhead, avoids repeated consent or navigation setup, speeds iterative publisher route debugging.
  - Cons: Profile reuse can leak state across publishers or hide first-run failures if used too broadly.
  - Acceptance Criteria:
    - Persistent sessions are disabled by default for production acquisition.
    - Session behavior follows copied/adapted `browser-harness` lifecycle practices where compatible with browser-use.
    - Session reuse is implemented with Marketlense-owned configuration and lifecycle code, with no `browser-harness` dependency.
    - Allowed reuse modes require explicit session key, publisher scope, TTL, and cleanup event logs.
    - Canary metrics compare browser startup time, agent calls, and verified PDF yield against isolated-profile baseline.
    - Tests assert cross-publisher session reuse is rejected unless explicitly allowed by configuration.

- **Title:** Copy browser-harness developer-mode self-healing diagnostics into repo tooling [Impact: 3/5, Effort: 2/5]
  - Explanation: Confirmed useful for local Marketlense development. `browser-harness` setup and doctor flows detect Chrome remote-debugging state, stale daemon sessions, missing real tabs, and CDP attach failures. Copy/adapt that existing diagnostic process pattern into Marketlense-owned developer tooling around browser-use instead of embedding recovery loops in production generators or designing new diagnostics from scratch.
  - Pros: Faster local setup, fewer manual browser debugging steps, clearer failure messages for agent operators.
  - Cons: Self-healing can mask environment issues if enabled in production paths.
  - Acceptance Criteria:
    - A developer-only diagnostic command or documented workflow checks CDP availability, active tab, profile path, downloads path, and browser-use connectivity.
    - Diagnostic checks are copied/adapted from `browser-harness` setup/doctor behavior where applicable.
    - Diagnostic tooling is fully self-contained in the Marketlense repo and does not require `browser-harness` to be installed.
    - Stale browser connection cleanup is attempted once and logged.
    - Setup or verification tabs are activated when opened during manual developer workflows.
    - Production browser workflows do not depend on developer-mode self-healing.

- **Title:** Reuse screenshot-first coordinate fallbacks for hard UI surfaces [Impact: 4/5, Effort: 2/5]
  - Explanation: Additional browser-harness practice worth copying. The harness favors screenshot inspection and compositor-level coordinate clicks for cases where selectors fail, especially complex dropdowns, shadow DOM, canvas-like controls, and cross-origin iframes. Browser-use already supports coordinate-style interaction, so Marketlense should copy/adapt this fallback policy inside the repo instead of inventing a new interaction strategy.
  - Pros: Improves success on difficult publisher portals without adding publisher-specific automation code.
  - Cons: Coordinate use is brittle if stored as permanent route knowledge.
  - Acceptance Criteria:
    - Fallback policy requires selector/state attempts before coordinate interaction unless the page surface is known selector-hostile.
    - Fallback sequencing is copied/adapted from `browser-harness` screenshot-first interaction practices.
    - Coordinate fallback implementation and policy are fully independent of `browser-harness`.
    - Coordinates are derived from current screenshots and never stored as durable playbook facts.
    - Every coordinate action is followed by screenshot or page-info verification.
    - Tests or replay fixtures cover at least one selector-failure-to-coordinate-success path.

- **Title:** Copy browser-harness tab and target hygiene for headed and persistent browser runs [Impact: 3/5, Effort: 2/5]
  - Explanation: Additional reusable practice from browser-harness. Its tab guidance filters internal targets, fake omnibox targets, zero-size surfaces, and explicitly activates known targets when visibility matters. Copy/adapt those target-hygiene rules into Marketlense's browser-use developer, headed, and future persistent-session paths so verification captures the intended tab.
  - Pros: Fewer wrong-tab screenshots, clearer developer diagnostics, safer future session reuse.
  - Cons: Mostly benefits headed/developer workflows unless persistent sessions become more common.
  - Acceptance Criteria:
    - Target hygiene logic is self-contained in Marketlense-owned browser tooling and does not require `browser-harness`.
    - Behavior is copied/adapted from `browser-harness` internal-target filtering and target activation practices.
    - Internal Chrome/devtools/about/omnibox targets are excluded from user-facing browser evidence.
    - Zero-size or stale targets trigger a typed diagnostic or reattach decision.
    - Tests cover internal-target filtering and stale/zero-size target handling.

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

- **Title:** Extend CI gates from current quality coverage into role-mixing and monolith-growth enforcement [Impact: 4/5, Effort: 3/5]
  - Explanation: The repo already has strong CI coverage, so the remaining gap is not "add more generic checks." The useful next step is automation around role mixing, direct-I/O drift, service integration coverage waivers, and first-party long-file growth.
  - Pros: Prevents architectural drift earlier and keeps the current rule set enforceable.
  - Cons: Requires careful allowlist design for legitimate edge cases.
  - Acceptance Criteria:
    - New gate logic flags role mixing, direct I/O drift, or monolith-growth violations on first-party files.
    - Allowlist entries require owner plus expiry date.
    - Missing per-service integration coverage requires either a marked test or an explicit temporary waiver.
    - README documents how to add and retire waivers.

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

### Phase 3: Resilience and Compatibility (8-16+ weeks)

- Provider failover behind one LLM response contract.
- Durable checkpoint/restart for report pipeline stages.
- Durable publish jobs with transactional outbox.
- Contract compatibility matrix for persisted artifacts and stored rows.
- End-to-end tracing across orchestrator/generator/service boundaries.

---

## 8. Deep Codebase Audit (2026-05-06)

- **Title:** Restore CI baseline integrity after facade/module splits [Impact: 5/5, Effort: 4/5]
  - Explanation: A full CI preflight plus a second-pass recheck found the type gate currently failing with 1,365 mypy errors across 43 files. Errors cluster in newly split internal modules (`src/services/_config_service/*`, `src/services/_pdf/_visual_heuristics/*`) and now-unsafe orchestrator/generator typing edges. This is an immediate CI blocker and also signals cross-module contract drift after refactors.
  - Pros: Unblocks all PRs, restores confidence in type contracts, reduces runtime defect risk from incorrect assumptions.
  - Cons: Requires disciplined staged fixes and temporary ownership focus across several bounded contexts.
  - Acceptance Criteria:
    - `python scripts/ci/run_type_check.py` passes with zero unbaselined errors.
    - Any remaining baseline entries are intentional, owner-tagged, expiry-dated, and justified.
    - `src/services/_config_service/*` exports/imports are repaired so split modules resolve shared helpers/constants/types without `name-defined` failures.
    - `src/services/_pdf/_visual_heuristics/*` re-exports/constants are reconciled so submodules no longer depend on missing symbols.
    - Critical typed logic fixes land for currently unbaselined failures in:
      - `src/generators/artifact_normalization.py`
      - `src/orchestrators/_report_download_orchestrator/workflow.py`
      - `src/orchestrators/publisher_inventory_orchestrator.py`
      - `src/orchestrators/publish_orchestrator.py`
      - `src/services/_report_store_service/common.py`

- **Title:** Add automated post-refactor symbol-linking guard for split service internals [Impact: 4/5, Effort: 2/5]
  - Explanation: The dominant errors are unresolved names caused by internal module fission where helper symbols are no longer imported/exported coherently. The existing architecture gate checks import direction but does not catch missing symbol wiring early.
  - Pros: Prevents future large-scale CI failures after mechanical module splits.
  - Cons: One more CI check to maintain.
  - Acceptance Criteria:
    - A fast static check validates required exported symbols for split boundary families (at minimum `_config_service` and `_pdf/_visual_heuristics`).
    - The check runs before mypy in CI and fails with grouped actionable diagnostics.
    - README documents when to run the check locally during refactors.

- **Title:** Repair `config_service` facade split so internal modules compile and preserve one canonical boundary [Impact: 5/5, Effort: 3/5]
  - Explanation: Deep audit plus second-pass rerun showed that `src/services/_config_service/app_settings.py` and `src/services/_config_service/analysis.py` currently reference many missing shared symbols (types, helpers, logger/constants, and dotenv hooks). This indicates an incomplete internal split that broke symbol wiring while keeping `src/services/config_service.py` as the public boundary.
  - Pros: Restores deterministic config loading and prevents runtime surprises from dead code paths hidden behind import-time failures.
  - Cons: Requires careful re-stitching of internal helpers without reintroducing monolithic `config_service.py` logic.
  - Acceptance Criteria:
    - Internal `_config_service/*` modules import all required shared symbols explicitly and mypy no longer reports `name-defined` errors in this family.
    - `config_service.py` remains the single canonical public entrypoint while internal modules stay capability-scoped.
    - Regression tests cover both positive config load and failure taxonomy paths for missing/invalid settings.
    - `python scripts/ci/run_type_check.py` shows zero unbaselined `_config_service` errors.

- **Title:** Reconcile `_pdf/_visual_heuristics` module fission with explicit constant ownership and exports [Impact: 4/5, Effort: 3/5]
  - Explanation: The audit found a high-volume cluster of unresolved constants and export issues across `src/services/_pdf/_visual_heuristics/panel_detection.py` and `src/services/_pdf/visual_heuristics.py` (`CHART_CAPTION_HINTS`, title thresholds, regex constants, and missing `__all__`). Current structure suggests ineffective split mechanics where consumers rely on symbols no longer owned or re-exported coherently.
  - Pros: Reduces fragile cross-file coupling and stabilizes PDF chart/table heuristics behavior.
  - Cons: Touches dense heuristic code that needs careful non-regression validation.
  - Acceptance Criteria:
    - Shared constants are centralized in one internal owner module and imported explicitly by all heuristic submodules.
    - `visual_heuristics.py` re-export policy is explicit and type-safe (including `__all__` where required).
    - Type gate and PDF heuristic tests pass without new baselined exceptions.
    - A short module docstring explains ownership boundaries to prevent repeat drift.

- **Title:** Close unbaselined orchestrator/generator type-safety gaps that can corrupt publish/download behavior [Impact: 5/5, Effort: 2/5]
  - Explanation: Repeated type-gate runs consistently flagged unbaselined errors in `publish_orchestrator`, `publisher_inventory_orchestrator`, `_report_download_orchestrator/workflow`, and `artifact_normalization` (unsafe `object` assumptions, contract-mismatch assignments, and nullable comparisons). These are high-risk paths where ineffective typing choices can mask functional bugs.
  - Pros: Prevents silent contract corruption in core side-effecting workflows.
  - Cons: Requires focused fixes plus small targeted tests instead of broad refactors.
  - Acceptance Criteria:
    - All currently unbaselined errors in the listed orchestrator/generator files are resolved (or explicitly owner-tagged with expiry if deferred).
    - Tests assert corrected contract types for taxonomy/tag ensure flows, post lookup batch handling, checksum hashing inputs, and nullable normalization guards.
    - A follow-up double-run of `python scripts/ci/run_type_check.py` produces identical clean results for these files.

- **Title:** Tighten risk-policy scope so doc-only changes cannot hide repository-wide CI breakage [Impact: 4/5, Effort: 1/5]
  - Explanation: Current risk classification marks a `CONSOLIDATED_TODO.md`-only change as `docs` while the repository remains red on hard gates. This can create false confidence during maintenance updates.
  - Pros: Better signal to maintainers, fewer “green-looking” local checks when mainline is failing.
  - Cons: May mark more changes as higher risk and increase required local preflight work.
  - Acceptance Criteria:
    - Risk-policy output surfaces current repository CI health independently from changed-file classification.
    - For docs-only changes, policy clearly reports whether hard gates are presently failing on mainline baseline.
    - Operator docs include a “docs-only but repo-red” handling path.
