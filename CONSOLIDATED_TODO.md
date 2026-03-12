# Consolidated TODO

Last compiled: 2026-03-12

This file combines all TODOs found in the repository (from `TODO.md`, `html_todo.md`, and `potential-TODO.md`). Items are grouped by theme. Duplicates were merged. Each task includes: title, explanation (what & why), pros & cons, and acceptance criteria.

Completed items are removed from this backlog once their acceptance criteria are met. The PDF service internal split was completed on 2026-03-12 and is no longer tracked here as open work.

---

## 1. Prompts & Prompting

- **Title:** Upgrade and align prompts
  - Explanation: Audit and refresh prompt namespaces under `src/prompts/**` to ensure variables match renderer usage, improve wording and safety, and maintain prompt-hash/version logging so outputs are reproducible.
  - Pros: Better output quality, safer generation, clearer audit trail.
  - Cons: Requires careful migration and retesting; may surface transient failures.
  - Acceptance Criteria:
    - All prompt renders succeed without missing variables.
    - Prompt hash/version logged for each generator call.
    - No regression in key generator tests.

- **Title:** Support multi-prompt variants per step
  - Explanation: Add config-driven prompt variants (expert roles/styles) for generators, capture logs per variant, and provide selection/ensemble logic to pick best output.
  - Pros: Higher-quality outputs via ensemble, easier A/B testing.
  - Cons: Increases cost and logging volume; requires selection policy.
  - Acceptance Criteria:
    - Config accepts multiple variants per namespace.
    - Per-variant hashes and rendered prompts logged.
    - Deterministic selection mechanism implemented and covered by tests.

---

## 2. Cost, Billing & Resource Cleanup

- **Title:** Define and enforce cost limits
  - Explanation: Add per-run and per-day thresholds and enforce them in orchestrators (warn/block), logging decisions and spend snapshots.
  - Pros: Prevent runaway spend; operational safety.
  - Cons: May block valid runs; needs tuning.
  - Acceptance Criteria:
    - Configurable thresholds present in `src/config/app.yaml`.
    - Orchestrators check thresholds before model calls.
    - Tests cover warn/soft-stop/hard-block behaviors.

- **Title:** Add vector store deletion and lifecycle cleanup
  - Explanation: Extend `vector_store_service` with delete/prune APIs and add orchestrator hooks to remove remote assets when retention is disabled.
  - Pros: Avoids orphaned storage and repeated costs.
  - Cons: Risk of removing needed artifacts if misconfigured; needs idempotency.
  - Acceptance Criteria:
    - Delete API implemented and exercised by cleanup policies.
    - Cleanup logs include run/task/span identifiers and outcomes.
    - No orphaned vector assets after cleanup runs (when enabled).

---

## 3. HTML, Rendering & Assets

- **Title:** Refactor HTML template, remove duplication, and externalize styles
  - Explanation: Extract repeated blocks into Jinja macros/partials, move stable CSS to a shared file (keeping critical CSS inline), and unify image rendering patterns in `templates/report.html.j2`.
  - Pros: Easier maintenance, smaller templates, clearer tests.
  - Cons: Slight work to change rendering consumers; must preserve relative asset path conventions.
  - Acceptance Criteria:
    - No duplicated preview/figure branches in template.
    - Templates use shared CSS and macros; rendered output unchanged for canonical tests.
    - Relative asset paths remain stable for existing outputs.

- **Title:** Wire real image dimensions & responsive image pipeline
  - Explanation: Pass actual image dimensions from generation/crop pipeline into template context and generate responsive variants (webp + multiple widths) for `srcset`/`sizes`.
  - Pros: Reduces CLS, improves Core Web Vitals and mobile bandwidth.
  - Cons: Increased storage and generation complexity.
  - Acceptance Criteria:
    - Templates receive `width`/`height` and render them.
    - Generated responsive assets exist and `srcset` is present.
    - Measured decrease in CLS in sample reports (manual verification).

- **Title:** Add infographic asset generation for HTML and LinkedIn
  - Explanation: Create a generator/service pair that produces simple infographic SVG/PNG assets from highlights; persist assets and expose them to HTML and publishing flows.
  - Pros: Richer publishable artifacts; supports social sharing.
  - Cons: Additional generation cost and pipeline complexity.
  - Acceptance Criteria:
    - Infographic assets generated per report and stored with metadata.
    - HTML rendering includes generated infographic references where available.
    - Publish artifacts contain the asset links.

### HTML Editorial Improvements (readability + report data visibility)

- **Title:** Publisher attribution and report identity
  - Explanation: Replace `Unknown publisher` with `doc_map.publisher` attribution and add a compact "Report identity" line under the title (title, publisher, year, author).
  - Pros: Clearer source attribution and faster reader orientation.
  - Cons: Requires mapping fields from evidence packs and graceful fallbacks.
  - Acceptance Criteria:
    - `Unknown publisher` no longer appears when metadata is available.
    - Report identity line displays when at least one of the fields exists.

- **Title:** Split and present time-period fields
  - Explanation: Split current time-period copy into `Report focus year` and `Fieldwork dates` so readers can parse scope quickly.
  - Pros: Better clarity on when data was collected and what period it covers.
  - Cons: Requires source normalization in `doc_map`.
  - Acceptance Criteria:
    - Both fields available in template when source data exists.

- **Title:** Convert TOC chips to ordered chapter list with start pages
  - Explanation: Render covered topics / TOC as an ordered chapter list, include `doc_map.sections.start_page`, and sort by page number.
  - Pros: Improved navigation and faithful reading order.
  - Cons: Extra template logic and small data normalization step.
  - Acceptance Criteria:
    - Chapters show start pages and are sorted by page number.

- **Title:** Replace generic section kickers with semantic labels
  - Explanation: Replace placeholder section labels like "Section 1" with semantic, human-readable labels sourced from `doc_map.sections` or prompt-generated labels.
  - Pros: Improves reader orientation and accessibility.
  - Cons: Requires mapping or fallback rules for missing labels.
  - Acceptance Criteria:
    - Template uses semantic labels when available and falls back to numbered sections.

- **Title:** Explicit note when source URL missing
  - Explanation: If the source URL is unavailable, render an explicit note in the report instead of silently omitting reference links.
  - Pros: Clearer provenance for readers and fewer ambiguous missing links.
  - Cons: Minor UI copy decision and template change.
  - Acceptance Criteria:
    - Reports show a visible note when source URL is absent.

- **Title:** Methodology & digest coverage blocks
  - Explanation: Add "Methodology at a glance" (population, sample size, sponsor) and "What this digest covers" blocks sourced from scope objectives.
  - Pros: Readers quickly understand how findings were produced and the digest scope.
  - Cons: Requires extraction from `scope`/`doc_map` and fallback text.
  - Acceptance Criteria:
    - Both blocks render when data present; explicit "None extracted" when empty.

- **Title:** Key findings, limitations, and contact visibility
  - Explanation: Surface `findings.json` titles + descriptions, add a visible "Known limitations" block (explicitly state 'none' if empty), and surface `doc_map.contact` info.
  - Pros: Improves transparency and traceability.
  - Cons: Template changes and small content-mapping work.
  - Acceptance Criteria:
    - Findings, limitations, and contact lines appear where data exists.

- **Title:** TL;DR prioritization and executive summary improvements
  - Explanation: Move metadata below TL;DR, break executive summary into short bullets, keep each key insight to one sentence and move extended framing to a secondary line.
  - Pros: Faster reader scanning and better UX.
  - Cons: May require editing generated summary outputs for structure.
  - Acceptance Criteria:
    - Metadata appears below TL;DR.
    - Executive summary renders as short bullets with concise insights.

- **Title:** Citation micro-lines, quotes, and metric formatting
  - Explanation: Add citation micro-lines under insights (evidence id + page), replace `Unknown` quote speaker label with `Unattributed in report`, and reformat metric strings to natural language.
  - Pros: Stronger grounding and clearer citation UX.
  - Cons: Requires small changes in rendering and normalization logic.
  - Acceptance Criteria:
    - Citation micro-lines and improved quote labels appear when data exists.
    - Metric formatting follows natural-language pattern in examples.

- **Title:** Optional appendix for generated social/expert copy
  - Explanation: Move generated "Expert comment" and "LinkedIn post" into an appendix-style optional section so the digest stays report-first.
  - Pros: Keeps primary content focused while preserving generated assets.
  - Cons: Template additions and UI/UX decision.
  - Acceptance Criteria:
    - Expert comment and LinkedIn post appear only in appendix when present.

---

## 4. Candidate Extraction, Ranking & Quality

- **Title:** Improve figure candidate quality signals
  - Explanation: Add richer candidate signals (OCR density, chart/table confidence, visual entropy) and include them in rank payloads; tighten crop bounds to remove low-value fragments.
  - Pros: Higher-quality selected figures; fewer low-information assets.
  - Cons: Extra compute and feature engineering; ranking payloads grow.
  - Acceptance Criteria:
    - Candidate objects include new quality fields.
    - Ranking inputs include these fields and scoring improves on a validation set.
    - Reduced rate of low-signal selected figures in sample reports.

- **Title:** Pre-filter / compress candidate payload before LLM ranking
  - Explanation: Reduce prompt size and cost by pre-filtering unpromising candidates and compressing payloads prior to model calls.
  - Pros: Lower cost and faster ranking.
  - Cons: Risk of discarding rare but valuable candidates; needs conservative thresholds.
  - Acceptance Criteria:
    - A pre-filter step implemented with safe defaults.
    - Cost per ranking call measurably reduced in benchmarks.
    - No regression in ranking quality on held-out set.

---

## 5. Orchestration, Durability & Performance

- **Title:** Introduce durable, checkpointed pipeline stages
  - Explanation: Make pipeline stages durable and checkpointed so runs can resume mid-run and reprocess selective stages.
  - Pros: Faster recovery, selective reprocessing, operator convenience.
  - Cons: Requires state modeling and migration in DB.
  - Acceptance Criteria:
    - Stage-level checkpoints stored in state DB with artifact references.
    - A run can resume from a checkpoint and produce consistent results.

- **Title:** Centralize LLM orchestration with retry/backoff/circuit-breaker
  - Explanation: Provide a shared LLM orchestration layer to handle retries, backoff, timeouts, and circuit-breaking logic for all model calls.
  - Pros: Consistent error handling and simpler generator code.
  - Cons: One centralized layer must be robust and well-tested.
  - Acceptance Criteria:
    - New orchestration layer used by generators and services.
    - Retries and backoff are exercised in unit/integration tests.

- **Title:** Stream LLM responses with early validation / fail-fast
  - Explanation: Support streaming model responses and implement early validation to fail fast on invalid shapes or low-confidence content during generation.
  - Pros: Faster feedback, reduced wasted compute on clearly invalid outputs.
  - Cons: More complex streaming handlers and validation logic.
  - Acceptance Criteria:
    - Streaming path implemented for key generators.
    - Early validation hooks can abort and surface clear errors.

---

## 6. Publishing & WordPress

- **Title:** Parallelize WordPress media uploads & pass auth header from orchestrator
  - Explanation: Speed up publishing by parallelizing uploads and propagate auth header from orchestrator to generator to avoid duplicate auth derivation.
  - Pros: Faster publish time; simpler auth flows.
  - Cons: Concurrency and API rate-limit handling required.
  - Acceptance Criteria:
    - Media uploads run in parallel and respect rate limits.
    - Orchestrator passes required auth to publishers; no duplicate auth logic remains.

- **Title:** Move publishing to a durable queue with retry/backoff/idempotency
  - Explanation: Make publish operations durable by pushing publish tasks into a queue with retries, backoff, and idempotency to handle transient failures gracefully.
  - Pros: More reliable publishing and easier retry handling.
  - Cons: Operational overhead and queue infrastructure.
  - Acceptance Criteria:
    - Publish tasks can be enqueued and retried with idempotency keys.
    - Publish failures are retried with backoff and logged.

---

## 7. Schema, Validation & Output Quality

- **Title:** Re-validate cached payloads against current schema before returning cache hits
  - Explanation: Prevent stale invalid payloads from being served by validating cached payloads against the active schema.
  - Pros: Ensures cache correctness under schema changes.
  - Cons: Adds validation cost on cache reads.
  - Acceptance Criteria:
    - Cache read path validates payloads and invalidates stale ones.
    - Tests cover migration scenarios.

---

## 8. Codebase Audit: High-Impact Refactors

- **Title:** Cache Jinja `Environment` at module scope and unify render service
  - Explanation: Avoid recreating Jinja environment per render; centralize render service to return deterministic outputs and reduce overhead.
  - Pros: Performance and fewer subtle diffs.
  - Cons: Cache invalidation considerations for template changes.
  - Acceptance Criteria:
    - Jinja environment is cached and tests confirm deterministic output.

- **Title:** SQLite: adopt WAL and narrow lock scopes
  - Explanation: Reduce global SQLite locking by using WAL, setting busy timeouts, and minimizing critical sections for state updates.
  - Pros: Higher concurrency and throughput.
  - Cons: Requires migration and careful testing on Windows file systems.
  - Acceptance Criteria:
    - WAL mode enabled with safe busy timeouts.
    - Concurrency tests show reduced contention.

- **Title:** Deduplicate and remove small hotspots (slugify, duration scripts)
  - Explanation: Consolidate repeated slugify calls and merge duplicate duration scripts.
  - Pros: Cleaner codebase and smaller attack surface.
  - Cons: Low risk changes but requires tests to ensure behavior preserved.
  - Acceptance Criteria:
    - Duplicate scripts consolidated; related tests updated.
    - No functional change in publish flows.

### Additional Code Audit Items (explicit)

- **Title:** Fix O(n^2) table dedupe hotspot
  - Explanation: Replace the O(n^2) table dedupe algorithm in candidate extraction with a more efficient approach (hashing/indexing) to improve performance on large documents.
  - Pros: Better performance on large reports.
  - Cons: Requires careful correctness tests to avoid false merges.
  - Acceptance Criteria:
    - Dedupe algorithm updated and benchmarked with large PDFs.
    - No regressions in deduplication correctness tests.

- **Title:** Reuse candidate crop output path / guard unused crop pass
  - Explanation: Ensure candidate crop output paths are used or guard/remove the unused crop pass to avoid wasted computation and confusion.
  - Pros: Removes wasted I/O and clarifies pipeline.
  - Cons: Requires auditing downstream consumers.
  - Acceptance Criteria:
    - Unused crop pass removed or guarded behind config.
    - Crop output paths are consumed by report generator or persisted for debug.

- **Title:** Remove or implement `analysis_compare` and `debug_candidate_gallery` surfaces
  - Explanation: Either remove legacy `analysis_compare` and dead `debug_candidate_gallery` config surfaces or fully implement them to avoid dead code and confusion.
  - Pros: Cleaner codebase and fewer maintenance surprises.
  - Cons: Possible loss of legacy debugging features if removed; require migration notes.
  - Acceptance Criteria:
    - Dead config flags removed or implemented and tested.

- **Title:** Fix lock service double-close fd path and other minor fd issues
  - Explanation: Address potential double-close and FD-handling bugs in lock service and related code paths to avoid resource leaks and errors.
  - Pros: Reliability and fewer low-level crashes.
  - Cons: Low-level changes need careful testing.
  - Acceptance Criteria:
    - Lock service no longer has double-close paths (validated by code review and tests).

- **Title:** Add per-stage feature flags for controlled rollout
  - Explanation: Add feature-flagging at the stage level to enable controlled rollouts, A/B tests, and emergency disable switches for costly steps.
  - Pros: Safer deployments and cost governance.
  - Cons: Adds configuration surface and flag management.
  - Acceptance Criteria:
    - Per-stage flags configurable and respected by orchestrators.
    - Tests validate enabling/disabling stages.

---

## 9. Low-Effort / High-Impact Opportunities (Quick Wins)

- **Title:** Reuse contents-page preview when it overlaps with general preview rendering
  - Explanation: Detect when the contents-page preview output overlaps or duplicates the main preview and reuse the same rendered asset instead of generating a second one.
  - Pros: Saves CPU and I/O; reduces storage duplication; faster report generation.
  - Cons: Requires a small dedupe check and coordination in preview generation logic; small risk of edge-case layout mismatch.
  - Acceptance Criteria:
    - Preview generation detects overlap and reuses existing contents-page preview.
    - No visual regressions in sample reports.

- **Title:** Extract publish-time JSON parsing to a shared helper
  - Explanation: Centralize JSON parsing/validation used at publish time into a single helper/service to avoid duplicated parsing code and inconsistent error handling.
  - Pros: Less duplicated code; consistent error messages; simpler testing.
  - Cons: Small refactor and coordination across publish paths.
  - Acceptance Criteria:
    - A shared helper/service exists and is imported by publish flows.
    - All publish-time parsing uses the new helper and tests cover parsing edge cases.

- **Title:** Cache incremental cost rollups instead of recomputing full ledger per write
  - Explanation: Maintain an incremental cache or rolling aggregate for daily cost totals so each new ledger entry updates the aggregate instead of recomputing across the full ledger file on every write.
  - Pros: Significant CPU and I/O savings for high-volume runs; simpler thresholds checks.
  - Cons: Need correct invalidation/repair logic if ledger entries are backfilled or amended.
  - Acceptance Criteria:
    - Daily cost rollup updated incrementally on ledger writes.
    - Tests covering backfill/amend scenarios ensure aggregates remain correct.

Each quick-win should be documented with a short task when prioritized.

---
## 10. Architecture-Fit Additions (Incremental)

- **Title:** Enforce schema-version parity for all dataclass contracts
  - Explanation: Add a contract linter/test that fails when any dataclass in `src/contracts/**` lacks a `schema_version` field. Current audit found classes such as `PdfTextSample`, `CategoryDefinition`, and `UncategorizedTagsEntry` without explicit schema versioning.
  - Pros: Consistent contract evolution and safer migrations.
  - Cons: Small refactor burden for existing contracts and fixtures.
  - Acceptance Criteria:
    - Linter/test added and wired into CI.
    - All contracts include explicit `schema_version` (or documented exemption list with rationale).

- **Title:** Propagate CLI/GUI run context into publish pipeline
  - Explanation: Standardize `run_id/task_id/span_id` propagation from entry points into `run_publish` and downstream calls so publish logs correlate to the triggering command/session instead of creating a fresh top-level context per call.
  - Pros: Better traceability, easier incident debugging, consistent observability.
  - Cons: Requires small signature changes across orchestrator boundaries.
  - Acceptance Criteria:
    - `run_publish` accepts external context and uses it when provided.
    - Publish logs for CLI/GUI flows share the initiating `run_id`.
    - Tests assert context continuity in emitted log fields.

- **Title:** Harden config portability by removing environment-specific defaults from tracked YAML
  - Explanation: Move concrete deployment values (e.g., Drive folder IDs, site URLs, usernames) out of committed defaults into environment overlays (`app.example.yaml` + env vars) and document profile-based config loading.
  - Pros: Safer repo defaults, easier onboarding across environments, lower risk of accidental prod coupling.
  - Cons: Requires migration docs and bootstrap scripts for current deployments.
  - Acceptance Criteria:
    - `src/config/app.yaml` contains environment-neutral defaults only.
    - Example/local override pattern documented in README.
    - Bootstrapping tests verify env/profile overrides resolve correctly.

- **Title:** Add architecture boundary checks (import + I/O role linting)
  - Explanation: Introduce automated checks that enforce layer dependency rules (`services -> contracts/utils`, etc.) and flag direct filesystem/network usage in generators and utilities that should remain pure.
  - Pros: Prevents architectural drift and role leakage over time.
  - Cons: Requires curating false-positive exemptions for legitimate edge cases.
  - Acceptance Criteria:
    - Boundary linter runs in CI.
    - Violations report exact module and forbidden dependency/API usage.
    - Existing violations are fixed or explicitly documented with expiry dates.

### AGENTS.md Compliance Backlog (Audit 2026-02-21)

- **Title:** Remove placeholder/sentinel production outputs and fail explicitly
  - Explanation: Replace placeholder payloads/default-filled semantic fields with explicit typed `AppError` failures when required data cannot be produced.
  - Pros: Prevents silent quality degradation and improves correctness guarantees.
  - Cons: More hard-fail scenarios may require upstream handling and UX messaging.
  - Acceptance Criteria:
    - Placeholder text/sentinel payload paths removed from production generators.
    - Missing required contract fields cause typed `AppError` with context.
    - Tests verify no default/sentinel-filled required contract fields.

- **Title:** Ensure retryable `AppError` propagation from generators
  - Explanation: Remove generator-side swallowing of retryable failures and propagate retryable `AppError` to orchestrators for policy-driven retry.
  - Pros: Correct error taxonomy behavior and cleaner resilience model.
  - Cons: Requires revisiting existing fallback behavior and negative-path tests.
  - Acceptance Criteria:
    - Generators do not suppress retryable `AppError`.
    - Orchestrator tests verify retries/backoff/state transitions for propagated errors.
    - Error taxonomy assertions (`code`, `retryable`, `severity`) added for failure paths.

- **Title:** Enforce role-bound import rules and remove cross-role coupling
  - Explanation: Eliminate forbidden imports and coupling (service-to-service orchestration logic, generator-to-generator orchestration dependencies) to match AGENTS dependency boundaries.
  - Pros: Cleaner architecture and easier isolation testing.
  - Cons: Requires extracting shared behavior into proper utility/service boundaries.
  - Acceptance Criteria:
    - Services import only contracts/utils (and approved low-level primitives).
    - Generators import services/contracts/utils only; orchestration lives in orchestrators.
    - Boundary checks prevent regressions.

- **Title:** Enforce prompt immutability outside prompt service and complete prompt observability
  - Explanation: Ban runtime prompt text mutation/concatenation outside prompt service and ensure every model call logs prompt namespace, file paths, prompt hashes, exact rendered prompts, model params, and raw response.
  - Pros: Reproducibility and auditability of model behavior.
  - Cons: Larger logs and redaction policy tuning.
  - Acceptance Criteria:
    - No runtime prompt string concatenation outside prompt service.
    - Generator logs include required prompt and model metadata for every model call.
    - Raw model response logging present with redaction safeguards.

- **Title:** Remove direct file/network I/O from generators and pure utilities
  - Explanation: Replace direct filesystem operations in generators with service calls and keep utilities deterministic/pure without I/O.
  - Pros: Stronger layering and testability.
  - Cons: Refactor touches multiple cache/read paths.
  - Acceptance Criteria:
    - Generators perform no direct file reads/writes outside service interfaces.
    - Utility modules remain stateless and I/O-free.
    - Boundary lint/tests catch prohibited I/O usage.

- **Title:** Split remaining monolithic generator/service modules to single-responsibility units
  - Explanation: Break the remaining oversized mixed-responsibility modules (starting with `report_generator` and `openai_service`) into role-appropriate, single-purpose modules wired by orchestrators. The PDF service internal split is complete and removed from this backlog item.
  - Pros: Easier maintenance, lower regression risk, clearer ownership.
  - Cons: Large refactor with broad test impact.
  - Acceptance Criteria:
    - `report_generator` reduced to focused domain responsibilities.
    - Remaining oversized service/generator modules extract cross-cutting orchestration and I/O concerns to proper layers.
    - Equivalent behavior validated by pipeline tests.

- **Title:** Harden test integrity and required AGENTS fixtures
  - Explanation: Add mandatory shared fixtures (`assert_logs_have_required_fields`, `assert_no_defaulted_required_fields`, `assert_app_error`, `external_boundary_mocks_only`, `idempotency_guard`) and refactor tests to avoid private-helper monkeypatching and over-mocked narratives.
  - Pros: Higher confidence that tests validate real behavior.
  - Cons: Test rewrite effort, especially around orchestration-heavy paths.
  - Acceptance Criteria:
    - Required fixtures implemented in shared test infrastructure.
    - Private/helper patching removed from tests.
    - Orchestrator and service tests assert required structured log fields.
    - Idempotency behavior asserted where applicable.

- **Title:** Meet minimum integration-test coverage per service module
  - Explanation: Add at least one marked integration test per service module and keep live API calls out of unit tests.
  - Pros: Better boundary confidence and fewer production surprises.
  - Cons: More test runtime and environment setup complexity.
  - Acceptance Criteria:
    - `tests/integration/` includes at least one integration test per service module.
    - Integration tests are explicitly marked and excluded from default CI unit run.
    - Unit tests avoid live external calls.

---

## 11. Merged Audit Intake: Ineffective Choices Top 50

This section absorbs the 2026-03-08 low-effort/high-impact repository audit into the canonical backlog. Overlapping findings were deduplicated against existing items above; the tasks below capture the remaining gaps and name the concrete hotspots to refactor.

- **Title:** Split remaining monolithic UI, config, state, and ingest modules
  - Explanation: Extend the existing module-split backlog to cover `src/ui/streamlit_pages.py`, `src/services/config_service.py`, `src/services/state_service.py`, `src/orchestrators/ingest_orchestrator.py`, and `src/orchestrators/ingest_file_orchestrator.py`, plus their largest entrypoints such as `_render_structured_config_form`, `_render_settings_and_prompts`, `load_settings`, `run_ingest`, and `run_ingest_file`. This merges audit items 3, 8, 9, 10, 12, 14, 17, 18, 22, and 24 into actionable refactors.
  - Pros: Lower UI and ingest regression risk, faster code review, clearer role boundaries.
  - Cons: Requires coordinated signature cleanup and test updates across UI/orchestrator callers.
  - Acceptance Criteria:
    - Each target module is reduced to smaller role-consistent units with explicit helper boundaries.
    - The named oversized functions are decomposed into shorter phase-specific helpers.
    - Existing behavior is preserved by updated tests on the affected flows.

- **Title:** Phase-split oversized generation and validation flows
  - Explanation: Break large domain functions into typed phases for ranking, refinement, validation, and adaptation across `generate_report`, `_select_refined_candidate_items`, `generate_artifacts`, `_generate_pack`, `validate_report`, `_run_grounding_check`, `extract_taxonomy`, and `analyze_report`. This merges audit items 11, 13, 15, 19, 20, 21, 23, and 25.
  - Pros: Easier reasoning about generator behavior, smaller failure surfaces, better contract-level testing.
  - Cons: Refactor touches core generation paths and requires careful preservation of current outputs.
  - Acceptance Criteria:
    - Each listed flow is split into named phase helpers with typed intermediate contracts where appropriate.
    - Generator logs continue to expose the same prompt and validation observability after the split.
    - Sentinel or default-filled intermediate payloads are not introduced during refactoring.

- **Title:** Replace broad exception hotspots with typed `AppError` mapping
  - Explanation: Audit and narrow `except Exception` usage in `src/services/_pdf/text.py`, `src/services/_pdf/contents.py`, `src/services/_pdf/figures.py`, `src/services/_pdf/crop.py`, `src/services/openai_service.py`, `src/ui/streamlit_pages.py`, `src/generators/report_generator.py`, `src/services/file_service.py`, `src/services/lock_service.py`, `src/services/drive_service.py`, `src/orchestrators/ingest_orchestrator.py`, `src/services/wordpress_service.py`, and `src/services/report_store_service.py`. This merges audit items 26 through 35.
  - Pros: Better retry decisions, clearer root causes, and stronger compliance with the typed error taxonomy.
  - Cons: Requires revisiting negative-path tests and some UI error rendering assumptions.
  - Acceptance Criteria:
    - Broad catches are replaced with specific exception handling or explicit typed boundary mapping.
    - Negative-path tests assert `AppError.code`, `retryable`, and `severity` for the affected modules.
    - Retryable errors propagate to orchestrators instead of being downgraded to generic failures.

- **Title:** Replace monkeypatch-heavy tests with boundary fixtures and real-path assertions
  - Explanation: Prioritize `tests/test_vector_pipeline_wiring.py`, `tests/test_ingest_parallel.py`, `tests/test_candidate_extraction_orchestrator.py`, `tests/test_publish_orchestrator.py`, `tests/test_openai_vector_store.py`, `tests/test_candidate_refine_selection.py`, `tests/test_wordpress_service.py`, and `tests/test_publish_generator.py` for anti-cheat cleanup. Remove `sys.path.append(...)` setup hacks, patch only external boundaries, and assert real contracts, logs, retries, and side effects. This merges audit items 36 through 45.
  - Pros: Higher-confidence tests, better mutation resistance, less brittle fixture setup.
  - Cons: Test rewrites take time and may initially expose real defects.
  - Acceptance Criteria:
    - The targeted tests stop patching private helpers or internal orchestration paths.
    - Shared fixtures enforce external-boundary-only mocking and required structured log assertions.
    - At least one real-path integration or pipeline test covers each hotspot currently dominated by monkeypatching.

- **Title:** Decouple cross-role side effects in OpenAI, CLI, and control-flow helpers
  - Explanation: Remove cost-ledger persistence from `src/services/openai_service.py`, centralize repeated CLI status rendering instead of scattered `console.print(...)` calls in `src/cli.py`, and extract large branch-policy helpers from `src/ui/streamlit_pages.py` and `src/generators/report_generator.py`. This merges audit items 46, 47, and 49.
  - Pros: Cleaner service boundaries, more consistent operator UX, easier policy testing.
  - Cons: Requires small API changes between orchestrators, services, and UI helpers.
  - Acceptance Criteria:
    - OpenAI service emits cost/accounting data without directly persisting ledger side effects.
    - CLI status formatting is routed through shared rendering helpers.
    - Major branch policies in UI/report generation are moved into named helpers with focused tests.

- **Title:** Normalize config defaults and stop tracking generated operational artifacts
  - Explanation: Move hardcoded defaults and keyword lists out of `src/services/config_service.py` into schema-backed config constants or YAML, and remove generated `logs/*.csv` and `logs/*.json` artifacts from tracked repository state unless they are intentional documented fixtures. This merges audit items 48 and 50.
  - Pros: Safer configuration drift control, less repository noise, clearer operational hygiene.
  - Cons: Requires migration notes for current defaults and a review of any log files currently treated as fixtures.
  - Acceptance Criteria:
    - Config defaults are defined in one source of truth and documented in the README.
    - Generated log artifacts are ignored or moved to a documented fixture/snapshot location with rationale.
    - Tests or tooling verify config defaults and log artifact policies do not regress.
