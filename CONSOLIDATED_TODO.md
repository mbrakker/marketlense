# Consolidated TODO

Last compiled: 2026-03-26

This file combines all TODOs found in the repository (from `TODO.md`, `html_todo.md`, and `potential-TODO.md`). Items are grouped by theme. Duplicates were merged. Each task includes: title, explanation (what & why), pros & cons, and acceptance criteria.

Completed items are removed from this backlog once their acceptance criteria are met. The PDF service internal split, the report-generator phase split, the validation-generator rule split, the evidence-pack strategy split, the duration-tooling consolidation, the legacy `analysis.compare` / `ingest.debug_candidate_gallery` cleanup, the monkeypatch-heavy test hotspot cleanup, the publish file-id helper extraction, the contract `schema_version` parity sweep, the lock-service FD cleanup, and the direct-I/O boundary enforcement were completed on or before 2026-03-26 and are no longer tracked here as open work. This file is the single source of truth for open backlog items, including the remaining work previously tracked in `docs/quality/ineffective-choices-top50.md`.

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

- **Title:** Stream LLM responses with early validation / fail-fast
  - Explanation: Support streaming model responses and implement early validation to fail fast on invalid shapes or low-confidence content during generation.
  - Pros: Faster feedback, reduced wasted compute on clearly invalid outputs.
  - Cons: More complex streaming handlers and validation logic.
  - Acceptance Criteria:
    - Streaming path implemented for key generators.
    - Early validation hooks can abort and surface clear errors.

---

## 6. Publishing & WordPress

- **Title:** Parallelize WordPress media uploads and remove duplicated auth-header derivation
  - Explanation: Speed up publishing by parallelizing uploads and pass the resolved auth header through the publish request flow. The current code still derives auth in both `publish_orchestrator` and `publish_generator`.
  - Pros: Faster publish time; simpler auth flows.
  - Cons: Concurrency and API rate-limit handling required.
  - Acceptance Criteria:
    - Media uploads run in parallel and respect rate limits.
    - Auth header is resolved once at the orchestration boundary and passed through to publish operations.
    - No duplicate auth derivation remains in the publish path.

- **Title:** Turn publish queue snapshot into a durable publish job queue with retry/backoff/idempotency
  - Explanation: The repo already has `publish_queue_orchestrator`, but today it is a snapshot/read-model only. Extend publishing so jobs are enqueued, persisted, retried with backoff, and executed idempotently.
  - Pros: More reliable publishing and easier retry handling.
  - Cons: Operational overhead and queue infrastructure.
  - Acceptance Criteria:
    - Publish tasks can be enqueued and retried with idempotency keys.
    - Publish failures are retried with backoff and logged.

---

## 7. Schema, Validation & Output Quality

---

## 8. Audit-Driven Refactors & Compliance

### 8.1 Core High-Impact Refactors
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

- **Title:** Add per-stage feature flags for controlled rollout
  - Explanation: Add feature-flagging at the stage level to enable controlled rollouts, A/B tests, and emergency disable switches for costly steps.
  - Pros: Safer deployments and cost governance.
  - Cons: Adds configuration surface and flag management.
  - Acceptance Criteria:
    - Per-stage flags configurable and respected by orchestrators.
    - Tests validate enabling/disabling stages.

### 8.3 Quick Wins

- **Title:** Cache incremental cost rollups instead of recomputing full ledger per write
  - Explanation: Maintain an incremental cache or rolling aggregate for daily cost totals so each new ledger entry updates the aggregate instead of recomputing across the full ledger file on every write.
  - Pros: Significant CPU and I/O savings for high-volume runs; simpler thresholds checks.
  - Cons: Need correct invalidation/repair logic if ledger entries are backfilled or amended.
  - Acceptance Criteria:
    - Daily cost rollup updated incrementally on ledger writes.
    - Tests covering backfill/amend scenarios ensure aggregates remain correct.

Each quick-win should be documented with a short task when prioritized.

### 8.4 Architecture-Fit Additions

- **Title:** Normalize config defaults, portability, and shared YAML loading
  - Explanation: Merge the config-portability cleanup with the repeated YAML-loading/parsing refactor. Move concrete deployment values (e.g., Drive folder IDs, site URLs, usernames) out of committed defaults into environment overlays (`app.example.yaml` + env vars), move hardcoded defaults and keyword lists out of `src/services/config_service.py` into one documented source of truth, centralize shared YAML load/root-shape/parse-error wrapping where semantics match, and stop tracking generated operational artifacts such as `logs/*.csv` and `logs/*.json` unless they are intentional fixtures.
  - Pros: Safer repo defaults, easier onboarding across environments, less duplicated YAML boilerplate, and lower risk of accidental prod coupling.
  - Cons: Requires migration docs, bootstrap scripts, careful preservation of service-specific YAML error semantics, and a review of any current tracked artifacts treated as fixtures.
  - Acceptance Criteria:
    - `src/config/app.yaml` contains environment-neutral defaults only.
    - Config defaults are defined in one source of truth and documented in the README.
    - Shared YAML-loading helpers replace repeated load/root-shape/parse-error boilerplate where semantics match.
    - Service-specific error codes remain explicit at the public boundary.
    - Example/local override pattern documented in README.
    - Generated log artifacts are ignored or moved to a documented fixture/snapshot location with rationale.
    - Bootstrapping tests verify env/profile overrides resolve correctly.
    - File-not-found and invalid-YAML tests still distinguish the correct failure modes.

- **Title:** Expand architecture boundary checks from I/O linting to full import-role enforcement
  - Explanation: The repo already has direct-I/O boundary coverage in `tests/test_io_boundaries.py`. Extend that enforcement to import-direction checks (`services -> contracts/utils`, etc.) and explicit cross-role dependency violations.
  - Pros: Prevents architectural drift and role leakage over time.
  - Cons: Requires curating false-positive exemptions for legitimate edge cases.
  - Acceptance Criteria:
    - Existing I/O boundary lint remains in CI.
    - Import/dependency boundary lint also runs in CI.
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

- **Title:** Finish remaining generator/service/control-flow refactors and boundary cleanup
  - Explanation: Merge the remaining monolith-split work, oversized generation/validation phase splits, and the OpenAI/CLI/control-flow helper cleanup into one refactor track. Break the remaining oversized mixed-responsibility modules (notably `artifact_generator` and `openai_service`) into role-appropriate, single-purpose modules wired by orchestrators; phase-split large domain flows such as `generate_artifacts`, `_generate_pack`, `validate_report`, `_run_grounding_check`, `extract_taxonomy`, and `analyze_report`; remove cross-role side effects in `src/services/openai_service.py`; centralize repeated OpenAI cost/accounting and response-adaptation helpers; and route repeated CLI/control-flow status rendering through named helpers. The PDF service internal split, the report-generator phase split, the validation-generator rule split, and the evidence-pack strategy split are complete and removed from this backlog item.
  - Pros: Easier maintenance, lower regression risk, clearer service boundaries, and more focused tests around core generation flows.
  - Cons: Large refactor with broad test impact and small API/signature changes between services, generators, orchestrators, and CLI helpers.
  - Acceptance Criteria:
    - Remaining oversized service/generator modules extract cross-cutting orchestration and I/O concerns to proper layers.
    - The listed generation/validation flows are split into named phase helpers with typed intermediate contracts where appropriate.
    - OpenAI service emits cost/accounting data without directly persisting ledger side effects.
    - OpenAI cost/accounting and response adaptation use shared helpers instead of repeated internal blocks.
    - CLI status formatting and major branch policies in remaining control-flow hotspots are routed through named helpers with focused tests.
    - Generator logs continue to expose the same prompt and validation observability after the split.
    - Equivalent behavior is validated by pipeline tests without introducing default-filled or sentinel-filled intermediate payloads.

- **Title:** Finish rollout of AGENTS test-integrity fixtures and boundary-only mocking
  - Explanation: The shared fixtures now exist in `tests/conftest.py`, but the suite still contains raw `monkeypatch` usage against generator/orchestrator internals. Finish migrating remaining hotspots to boundary-only mocks and fixture-based assertions.
  - Pros: Higher confidence that tests validate real behavior.
  - Cons: Test rewrite effort, especially around orchestration-heavy paths.
  - Acceptance Criteria:
    - New and touched tests use the shared fixtures instead of ad-hoc assertion helpers.
    - Private/helper patching and internal orchestrator/generator patching are removed from remaining hotspots.
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

- **Title:** Factory-generate repetitive evidence-pack strategy scaffolding
  - Explanation: Replace repeated list-pack/scalar-pack strategy boilerplate with factory helpers, leaving pack-specific field maps and transforms explicit in each strategy module.
  - Pros: Smaller strategy modules and less repeated normalization shell code.
  - Cons: Must avoid over-abstracting genuinely different pack behavior.
  - Acceptance Criteria:
    - Common evidence-pack strategy scaffolding is centralized.
    - Pack-specific transforms and schema choices remain explicit.
    - Existing strategy outputs remain unchanged under tests.

