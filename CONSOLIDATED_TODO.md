# Consolidated TODO

Last compiled: 2026-03-25

This file combines all TODOs found in the repository (from `TODO.md`, `html_todo.md`, and `potential-TODO.md`). Items are grouped by theme. Duplicates were merged. Each task includes: title, explanation (what & why), pros & cons, and acceptance criteria.

Completed items are removed from this backlog once their acceptance criteria are met. The PDF service internal split, the report-generator phase split, the validation-generator rule split, the evidence-pack strategy split, the duration-tooling consolidation, the legacy `analysis.compare` / `ingest.debug_candidate_gallery` cleanup, and the monkeypatch-heavy test hotspot cleanup were completed on or before 2026-03-25 and are no longer tracked here as open work. This file is the single source of truth for open backlog items, including the remaining work previously tracked in `docs/quality/ineffective-choices-top50.md`.

How to use this backlog:

- Treat this file as the only active TODO source.
- Remove items once their acceptance criteria are fully met.
- Prefer adding new tasks under the most relevant workstream instead of creating new append-only audit sections.
- Keep overlapping work merged into one item with explicit source notes in the explanation when needed.

Section guide:

- `1-7`: product, pipeline, publishing, and quality workstreams
- `8`: audit-driven refactors and compliance backlog
- `9`: supplemental code-reduction opportunities

Suggested reading order when prioritizing:

1. `5. Orchestration, Durability & Performance`
2. `6. Publishing & WordPress`
3. `7. Schema, Validation & Output Quality`
4. `8. Audit-Driven Refactors & Compliance`
5. `9. Supplemental Code-Reduction Intake`

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
  - Explanation: Provide a shared LLM orchestration layer to handle retries, backoff, timeouts, and circuit-breaking logic for all model calls, and remove thin local pass-through retry wrappers in favor of one shared retry API.
  - Pros: Consistent error handling and simpler generator code.
  - Cons: One centralized layer must be robust and well-tested.
  - Acceptance Criteria:
    - New orchestration layer used by generators and services.
    - Local pass-through retry wrappers are removed from affected modules.
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

## 8. Audit-Driven Refactors & Compliance

### 8.1 Core High-Impact Refactors
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

### 8.2 Additional Audit Items

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

### 8.3 Quick Wins

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

### 8.4 Architecture-Fit Additions

- **Title:** Enforce schema-version parity for all dataclass contracts
  - Explanation: Add a contract linter/test that fails when any dataclass in `src/contracts/**` lacks a `schema_version` field. Current audit found classes such as `PdfTextSample`, `CategoryDefinition`, and `UncategorizedTagsEntry` without explicit schema versioning.
  - Pros: Consistent contract evolution and safer migrations.
  - Cons: Small refactor burden for existing contracts and fixtures.
  - Acceptance Criteria:
    - Linter/test added and wired into CI.
    - All contracts include explicit `schema_version` (or documented exemption list with rationale).

- **Title:** Normalize config defaults, portability, and tracked operational artifacts
  - Explanation: Move concrete deployment values (e.g., Drive folder IDs, site URLs, usernames) out of committed defaults into environment overlays (`app.example.yaml` + env vars), move hardcoded defaults and keyword lists out of `src/services/config_service.py` into one documented source of truth, and stop tracking generated operational artifacts such as `logs/*.csv` and `logs/*.json` unless they are intentional fixtures.
  - Pros: Safer repo defaults, easier onboarding across environments, lower risk of accidental prod coupling, and less repository noise.
  - Cons: Requires migration docs, bootstrap scripts, and a review of any current tracked artifacts treated as fixtures.
  - Acceptance Criteria:
    - `src/config/app.yaml` contains environment-neutral defaults only.
    - Config defaults are defined in one source of truth and documented in the README.
    - Example/local override pattern documented in README.
    - Generated log artifacts are ignored or moved to a documented fixture/snapshot location with rationale.
    - Bootstrapping tests verify env/profile overrides resolve correctly.

- **Title:** Add architecture boundary checks (import + I/O role linting)
  - Explanation: Introduce automated checks that enforce layer dependency rules (`services -> contracts/utils`, etc.), flag direct filesystem/network usage in generators and utilities that should remain pure, and drive removal of existing cross-role coupling so the same rule exists only once in the backlog.
  - Pros: Prevents architectural drift and role leakage over time.
  - Cons: Requires curating false-positive exemptions for legitimate edge cases.
  - Acceptance Criteria:
    - Boundary linter runs in CI.
    - Violations report exact module and forbidden dependency/API usage.
    - Forbidden cross-role imports/coupling are removed from current hotspots.
    - Existing violations are fixed or explicitly documented with expiry dates.

### 8.5 AGENTS.md Compliance Backlog

- **Title:** Ensure retryable `AppError` propagation from generators
  - Explanation: Remove generator-side swallowing of retryable failures and propagate retryable `AppError` to orchestrators for policy-driven retry.
  - Pros: Correct error taxonomy behavior and cleaner resilience model.
  - Cons: Requires revisiting existing fallback behavior and negative-path tests.
  - Acceptance Criteria:
    - Generators do not suppress retryable `AppError`.
    - Orchestrator tests verify retries/backoff/state transitions for propagated errors.
    - Error taxonomy assertions (`code`, `retryable`, `severity`) added for failure paths.

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
  - Explanation: Break the remaining oversized mixed-responsibility modules (notably `artifact_generator` and `openai_service`) into role-appropriate, single-purpose modules wired by orchestrators. The PDF service internal split, the report-generator phase split, the validation-generator rule split, and the evidence-pack strategy split are complete and removed from this backlog item.
  - Pros: Easier maintenance, lower regression risk, clearer ownership.
  - Cons: Large refactor with broad test impact.
  - Acceptance Criteria:
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

### 8.6 Merged Audit Intake: Ineffective Choices Top 50

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
  - Explanation: Break large domain functions into typed phases for generation, validation, and adaptation across `generate_artifacts`, `_generate_pack`, `validate_report`, `_run_grounding_check`, `extract_taxonomy`, and `analyze_report`. The `report_generator` and candidate-selection splits are complete and removed from this backlog item. This merges audit items 15, 19, 20, 21, 23, and 25.
  - Pros: Easier reasoning about generator behavior, smaller failure surfaces, better contract-level testing.
  - Cons: Refactor touches core generation paths and requires careful preservation of current outputs.
  - Acceptance Criteria:
    - Each listed flow is split into named phase helpers with typed intermediate contracts where appropriate.
    - Generator logs continue to expose the same prompt and validation observability after the split.
    - Sentinel or default-filled intermediate payloads are not introduced during refactoring.

- **Title:** Decouple cross-role side effects in OpenAI, CLI, and control-flow helpers
  - Explanation: Remove cost-ledger persistence from `src/services/openai_service.py`, centralize repeated OpenAI cost-estimation/ledger-update blocks behind one helper while keeping side effects outside the service boundary, centralize repeated CLI status rendering instead of scattered `console.print(...)` calls in `src/cli.py`, and extract large branch-policy helpers from `src/ui/streamlit_pages.py` and the remaining oversized generation flows. This merges audit items 46, 47, and 49.
  - Pros: Cleaner service boundaries, more consistent operator UX, easier policy testing.
  - Cons: Requires small API changes between orchestrators, services, and UI helpers.
  - Acceptance Criteria:
    - OpenAI service emits cost/accounting data without directly persisting ledger side effects.
    - OpenAI cost/accounting adaptation uses one shared helper instead of repeated ledger-write blocks.
    - CLI status formatting is routed through shared rendering helpers.
    - Major branch policies in UI/report generation are moved into named helpers with focused tests.

## 9. Supplemental Code-Reduction Intake

This section absorbs the remaining open appendix items from `docs/quality/ineffective-choices-top50.md` so the consolidated TODO remains the only active backlog.

- **Title:** Centralize OpenAI response metadata adaptation
  - Explanation: Deduplicate request-id, token-count, tool-call, and parsed-JSON extraction logic across JSON chat, image chat, and vector-store response flows.
  - Pros: More consistent provider adaptation and simpler service maintenance.
  - Cons: Shared adapters must preserve subtle response-shape differences.
  - Acceptance Criteria:
    - Shared response metadata adapter used by the repeated OpenAI response paths.
    - Returned dataclass contracts remain unchanged.
    - Tests cover identical metadata extraction across the affected flows.

- **Title:** Unify vector-store operation scaffolding in OpenAI service
  - Explanation: Collapse repeated create/upload/attach/status/update scaffolding in `src/services/openai_service.py` into shared operation helpers while keeping one canonical OpenAI service boundary.
  - Pros: Lower duplication and more consistent error mapping.
  - Cons: Needs explicit contracts so the shared layer does not become vague pass-through indirection.
  - Acceptance Criteria:
    - Common vector-store client init/log/error mapping is centralized.
    - Operation-specific request/response contracts remain explicit.
    - Existing vector-store tests continue to validate behavior without regressions.

- **Title:** Replace inline config parsing chains with declarative resolvers
  - Explanation: Refactor `load_settings` and adjacent config normalization code to use field-spec tables or section resolvers that define source path, env fallback, coercion, and default behavior once.
  - Pros: Less default drift and easier config extension.
  - Cons: Broad config refactor needs exact compatibility preservation.
  - Acceptance Criteria:
    - Config field resolution is table-driven or section-driven instead of one long inline chain.
    - Adding a new config field becomes localized.
    - Existing config-behavior tests continue to pass without semantic drift.

- **Title:** Promote duplicated coercion helpers into shared utils
  - Explanation: Replace repeated boolean/numeric coercion helpers in config, rank, and UI code with shared pure utility functions.
  - Pros: Consistent parsing semantics and smaller modules.
  - Cons: Requires checking for behavior mismatches in edge-case coercion.
  - Acceptance Criteria:
    - Shared coercion helpers live in `src/utils`.
    - Duplicate local coercion helpers are removed where semantics match.
    - Truthy/falsy and numeric parsing behavior is covered by tests.

- **Title:** Centralize YAML loading and parse-error wrapping where semantics match
  - Explanation: Introduce shared YAML-loading helpers for the common pattern of load, root-shape validation, and typed parse-error mapping, while preserving service-specific error codes at the boundary.
  - Pros: Less boilerplate and more consistent config/schema loading behavior.
  - Cons: Shared loader must not blur domain-specific error semantics.
  - Acceptance Criteria:
    - Repeated YAML loading boilerplate is replaced with shared helpers.
    - Service-specific error codes remain explicit at the public boundary.
    - File-not-found and invalid-YAML tests still distinguish the correct failure modes.

- **Title:** Factory-generate repetitive evidence-pack strategy scaffolding
  - Explanation: Replace repeated list-pack/scalar-pack strategy boilerplate with factory helpers, leaving pack-specific field maps and transforms explicit in each strategy module.
  - Pros: Smaller strategy modules and less repeated normalization shell code.
  - Cons: Must avoid over-abstracting genuinely different pack behavior.
  - Acceptance Criteria:
    - Common evidence-pack strategy scaffolding is centralized.
    - Pack-specific transforms and schema choices remain explicit.
    - Existing strategy outputs remain unchanged under tests.

- **Title:** Pass evidence-pack strategy objects directly through the generator
  - Explanation: Simplify evidence-pack execution by building work directly from `EvidencePackStrategy` objects and scheduling metadata instead of tuple-based indirection and thin wrappers.
  - Pros: Lower indirection and clearer execution flow.
  - Cons: Requires careful refactor of registry/execution plumbing.
  - Acceptance Criteria:
    - Evidence-pack execution steps are derived directly from strategy objects.
    - Pack ordering and registry behavior remain unchanged.
    - Helper indirection around strategy metadata is reduced.

- **Title:** Share publish file-id mapping helpers across publish orchestrators
  - Explanation: Deduplicate HTML path canonicalization and reports-DB file-id mapping logic currently split across `publish_orchestrator` and `publish_queue_orchestrator`.
  - Pros: Consistent file-id resolution and less orchestration duplication.
  - Cons: Shared helper boundary must stay narrow and orchestration-specific logic must not leak across modules.
  - Acceptance Criteria:
    - One shared helper module owns HTML-path canonicalization and file-id map loading.
    - Publish queue and publish flows resolve file IDs exactly as before.
    - Duplicate helper bodies are removed from both orchestrators.

- **Title:** Centralize dataclass-to-dict row serialization for UI and dashboards
  - Explanation: Replace repeated “dataclass/dict/object to row dict” helpers across UI, ops dashboard, and related table-rendering code with one shared pure serializer.
  - Pros: Less duplication and more consistent row-shaping behavior.
  - Cons: Shared helper must preserve current UI table expectations.
  - Acceptance Criteria:
    - One shared serializer handles the repeated row-conversion pattern.
    - Duplicate local helpers are removed from UI/dashboard modules.
    - Rendered rows remain unchanged in existing tests.

- **Title:** Promote repeated small text/tag helpers into shared utilities
  - Explanation: Consolidate recurring helpers like tag normalization, category label normalization, pluralization shorthands, and JSON dump wrappers where their semantics are truly shared.
  - Pros: Smaller modules and more consistent helper behavior.
  - Cons: Needs discipline to avoid moving business logic into generic utils.
  - Acceptance Criteria:
    - Repeated small helper functions are centralized only where semantics match.
    - Business-specific behavior remains in its bounded context.
    - Existing helper behavior is preserved by tests.

- **Title:** Replace regeneration branch chain with a handler registry
  - Explanation: Refactor `src/generators/report_regeneration_generator.py` to dispatch by `target.target_section` through a handler registry that owns namespace selection, variable assembly, normalization, and state updates.
  - Pros: Lower branching complexity and clearer per-section behavior.
  - Cons: Requires preserving exact regeneration behavior across all target sections.
  - Acceptance Criteria:
    - Regeneration section dispatch uses a handler registry instead of a long `if/elif` chain.
    - Output remains identical for existing covered target sections.
    - Tests cover handler selection and per-section behavior.
