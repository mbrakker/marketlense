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

Scoring rubric:

- `Impact`: `1` low leverage, `5` highest leverage across reliability, quality, cost, or architecture.
- `Effort`: `1` localized change, `5` broad refactor/migration with cross-module coordination.

---

## 1. Prompts & Prompting

- **Title:** Upgrade and align prompts [Impact: 4/5, Effort: 3/5]
  - Explanation: Audit and refresh prompt namespaces under `src/prompts/**` to ensure variables match renderer usage, improve wording and safety, and maintain prompt-hash/version logging so outputs are reproducible.
  - Pros: Better output quality, safer generation, clearer audit trail.
  - Cons: Requires careful migration and retesting; may surface transient failures.
  - Acceptance Criteria:
    - All prompt renders succeed without missing variables.
    - Prompt hash/version logged for each generator call.
    - No regression in key generator tests.

- **Title:** Support multi-prompt variants per step [Impact: 3/5, Effort: 4/5]
  - Explanation: Add config-driven prompt variants (expert roles/styles) for generators, capture logs per variant, and provide selection/ensemble logic to pick best output.
  - Pros: Higher-quality outputs via ensemble, easier A/B testing.
  - Cons: Increases cost and logging volume; requires selection policy.
  - Acceptance Criteria:
    - Config accepts multiple variants per namespace.
    - Per-variant hashes and rendered prompts logged.
    - Deterministic selection mechanism implemented and covered by tests.

- **Title:** Build a prompt namespace manifest and stop full-tree prompt scans on every listing [Impact: 3/5, Effort: 3/5]
  - Explanation: `src/services/prompt_service.py` currently discovers namespaces by recursively scanning `src/prompts/**` and loading each prompt set. Add a manifest/index file or cached namespace inventory so the UI and tooling can list prompts without repeatedly traversing and hashing the entire tree.
  - Pros: Faster settings/prompt screens, less filesystem churn, and simpler prompt discovery behavior.
  - Cons: Manifest invalidation and regeneration need to be reliable.
  - Acceptance Criteria:
    - Prompt namespace listing no longer depends on a full recursive scan for steady-state reads.
    - Manifest/cache invalidation occurs when prompt files change.
    - Prompt listing tests cover add/remove/rename scenarios.

- **Title:** Add repository-wide prompt dry-run validation with fixture inputs [Impact: 4/5, Effort: 3/5]
  - Explanation: Go beyond file existence checks by adding a prompt validation step that renders every prompt namespace against representative fixture inputs or declared variable contracts, failing fast when templates drift from generator usage.
  - Pros: Catches prompt breakage before runtime and reduces latent generator failures.
  - Cons: Requires maintaining representative fixture inputs for prompt families.
  - Acceptance Criteria:
    - CI runs a prompt dry-run command or test suite across active namespaces.
    - Missing variables and template syntax errors fail before runtime.
    - Fixture coverage exists for the main report, validation, ranking, and publishing prompt families.

---

## 2. Cost, Billing & Resource Cleanup

- **Title:** Define and enforce cost limits [Impact: 4/5, Effort: 2/5]
  - Explanation: Add per-run and per-day thresholds and enforce them in orchestrators (warn/block), logging decisions and spend snapshots.
  - Pros: Prevent runaway spend; operational safety.
  - Cons: May block valid runs; needs tuning.
  - Acceptance Criteria:
    - Configurable thresholds present in `src/config/app.yaml`.
    - Orchestrators check thresholds before model calls.
    - Tests cover warn/soft-stop/hard-block behaviors.

- **Title:** Add vector store deletion and lifecycle cleanup [Impact: 3/5, Effort: 3/5]
  - Explanation: Extend `vector_store_service` with delete/prune APIs and add orchestrator hooks to remove remote assets when retention is disabled.
  - Pros: Avoids orphaned storage and repeated costs.
  - Cons: Risk of removing needed artifacts if misconfigured; needs idempotency.
  - Acceptance Criteria:
    - Delete API implemented and exercised by cleanup policies.
    - Cleanup logs include run/task/span identifiers and outcomes.
    - No orphaned vector assets after cleanup runs (when enabled).

---

## 3. HTML, Rendering & Assets

- **Title:** Refactor HTML template, remove duplication, and externalize styles [Impact: 3/5, Effort: 3/5]
  - Explanation: Extract repeated blocks into Jinja macros/partials, move stable CSS to a shared file (keeping critical CSS inline), and unify image rendering patterns in `templates/report.html.j2`.
  - Pros: Easier maintenance, smaller templates, clearer tests.
  - Cons: Slight work to change rendering consumers; must preserve relative asset path conventions.
  - Acceptance Criteria:
    - No duplicated preview/figure branches in template.
    - Templates use shared CSS and macros; rendered output unchanged for canonical tests.
    - Relative asset paths remain stable for existing outputs.

- **Title:** Wire real image dimensions & responsive image pipeline [Impact: 3/5, Effort: 4/5]
  - Explanation: Pass actual image dimensions from generation/crop pipeline into template context and generate responsive variants (webp + multiple widths) for `srcset`/`sizes`.
  - Pros: Reduces CLS, improves Core Web Vitals and mobile bandwidth.
  - Cons: Increased storage and generation complexity.
  - Acceptance Criteria:
    - Templates receive `width`/`height` and render them.
    - Generated responsive assets exist and `srcset` is present.
    - Measured decrease in CLS in sample reports (manual verification).

- **Title:** Add infographic asset generation for HTML and LinkedIn [Impact: 2/5, Effort: 4/5]
  - Explanation: Create a generator/service pair that produces simple infographic SVG/PNG assets from highlights; persist assets and expose them to HTML and publishing flows.
  - Pros: Richer publishable artifacts; supports social sharing.
  - Cons: Additional generation cost and pipeline complexity.
  - Acceptance Criteria:
    - Infographic assets generated per report and stored with metadata.
    - HTML rendering includes generated infographic references where available.
    - Publish artifacts contain the asset links.

### HTML Editorial Improvements (readability + report data visibility)

- **Title:** Split and present time-period fields [Impact: 2/5, Effort: 1/5]
  - Explanation: Split current time-period copy into `Report focus year` and `Fieldwork dates` so readers can parse scope quickly.
  - Pros: Better clarity on when data was collected and what period it covers.
  - Cons: Requires source normalization in `doc_map`.
  - Acceptance Criteria:
    - Both fields available in template when source data exists.

- **Title:** Convert TOC chips to ordered chapter list with start pages [Impact: 2/5, Effort: 2/5]
  - Explanation: Render covered topics / TOC as an ordered chapter list, include `doc_map.sections.start_page`, and sort by page number.
  - Pros: Improved navigation and faithful reading order.
  - Cons: Extra template logic and small data normalization step.
  - Acceptance Criteria:
    - Chapters show start pages and are sorted by page number.

- **Title:** Replace generic section kickers with semantic labels [Impact: 2/5, Effort: 2/5]
  - Explanation: Replace placeholder section labels like "Section 1" with semantic, human-readable labels sourced from `doc_map.sections` or prompt-generated labels.
  - Pros: Improves reader orientation and accessibility.
  - Cons: Requires mapping or fallback rules for missing labels.
  - Acceptance Criteria:
    - Template uses semantic labels when available and falls back to numbered sections.

- **Title:** Methodology & digest coverage blocks [Impact: 2/5, Effort: 2/5]
  - Explanation: Add "Methodology at a glance" (population, sample size, sponsor) and "What this digest covers" blocks sourced from scope objectives.
  - Pros: Readers quickly understand how findings were produced and the digest scope.
  - Cons: Requires extraction from `scope`/`doc_map` and fallback text.
  - Acceptance Criteria:
    - Both blocks render when data present; explicit "None extracted" when empty.

- **Title:** Key findings, limitations, and contact visibility [Impact: 3/5, Effort: 2/5]
  - Explanation: Surface `findings.json` titles + descriptions, add a visible "Known limitations" block (explicitly state 'none' if empty), and surface `doc_map.contact` info.
  - Pros: Improves transparency and traceability.
  - Cons: Template changes and small content-mapping work.
  - Acceptance Criteria:
    - Findings, limitations, and contact lines appear where data exists.

- **Title:** TL;DR prioritization and executive summary improvements [Impact: 3/5, Effort: 2/5]
  - Explanation: Move metadata below TL;DR, break executive summary into short bullets, keep each key insight to one sentence and move extended framing to a secondary line.
  - Pros: Faster reader scanning and better UX.
  - Cons: May require editing generated summary outputs for structure.
  - Acceptance Criteria:
    - Metadata appears below TL;DR.
    - Executive summary renders as short bullets with concise insights.

- **Title:** Citation micro-lines, quotes, and metric formatting [Impact: 3/5, Effort: 2/5]
  - Explanation: Add citation micro-lines under insights (evidence id + page), replace `Unknown` quote speaker label with `Unattributed in report`, and reformat metric strings to natural language.
  - Pros: Stronger grounding and clearer citation UX.
  - Cons: Requires small changes in rendering and normalization logic.
  - Acceptance Criteria:
    - Citation micro-lines and improved quote labels appear when data exists.
    - Metric formatting follows natural-language pattern in examples.

---

## 4. Candidate Extraction, Ranking & Quality

- **Title:** Improve figure candidate quality signals [Impact: 4/5, Effort: 4/5]
  - Explanation: Add richer candidate signals (OCR density, chart/table confidence, visual entropy) and include them in rank payloads; tighten crop bounds to remove low-value fragments.
  - Pros: Higher-quality selected figures; fewer low-information assets.
  - Cons: Extra compute and feature engineering; ranking payloads grow.
  - Acceptance Criteria:
    - Candidate objects include new quality fields.
    - Ranking inputs include these fields and scoring improves on a validation set.
    - Reduced rate of low-signal selected figures in sample reports.

- **Title:** Pre-filter / compress candidate payload before LLM ranking [Impact: 4/5, Effort: 3/5]
  - Explanation: Reduce prompt size and cost by pre-filtering unpromising candidates and compressing payloads prior to model calls.
  - Pros: Lower cost and faster ranking.
  - Cons: Risk of discarding rare but valuable candidates; needs conservative thresholds.
  - Acceptance Criteria:
    - A pre-filter step implemented with safe defaults.
    - Cost per ranking call measurably reduced in benchmarks.
    - No regression in ranking quality on held-out set.

- **Title:** Share PDF page-artifact caches across visual, table, and crop passes [Impact: 5/5, Effort: 4/5]
  - Explanation: `src/services/_pdf/page_artifacts.py` is only reused by parts of extraction today, while crop and related flows still rebuild page text/block state separately. Introduce one internal page-artifact cache per page/document and feed it through visual, table, and crop services.
  - Pros: Less repeated PDF parsing, lower CPU cost on large reports, and fewer divergent heuristics.
  - Cons: Requires careful lifecycle management for document/page objects.
  - Acceptance Criteria:
    - Shared page artifact/context objects are reused across figure, table, and crop flows.
    - Duplicate text-block extraction paths are removed or delegated to the shared cache.
    - Benchmarks on large PDFs show reduced repeated page parsing work.

- **Title:** Replace loose `Candidate.meta` score inputs with a typed feature contract [Impact: 4/5, Effort: 4/5]
  - Explanation: Ranking, filtering, and crop-refine decisions currently depend on ad-hoc keys inside `Candidate.meta`. Add a typed candidate-feature dataclass so quality metrics, geometric signals, and scoring inputs have an explicit contract instead of stringly-typed lookups.
  - Pros: Safer refactors, clearer tests, and less hidden coupling between extraction and ranking.
  - Cons: Requires migrating multiple generators/services and adapting caches.
  - Acceptance Criteria:
    - Candidate quality/scoring features are represented by typed contracts.
    - Ranking and crop-refine code paths stop depending on magic `meta` keys for required fields.
    - Serialization and round-trip tests cover the new feature contract.

- **Title:** Cache visual probe rasters and image statistics for repeated bbox inspection [Impact: 3/5, Effort: 3/5]
  - Explanation: Visual/table heuristics repeatedly render and inspect the same page regions while computing edge density, grayscale variance, or image profiles. Cache probe rasters/statistics by page+bbox+render profile so repeated heuristics can reuse them.
  - Pros: Lower image-render overhead and faster candidate extraction on graphics-heavy PDFs.
  - Cons: Needs tight cache keys to avoid stale or mismatched probe data.
  - Acceptance Criteria:
    - Repeated bbox probe rendering/stat extraction is cached behind a stable key.
    - Visual/table extraction modules reuse the cache instead of re-rendering identical probes.
    - Benchmarks show lower extraction time on graphics-heavy sample PDFs.

- **Title:** Consolidate report-source cache boilerplate into one typed helper [Impact: 3/5, Effort: 2/5]
  - Explanation: `src/generators/report_source_generator.py` repeats near-identical cache load/write flows for PDF info, contents detection, and extracted text. Replace those repeated blocks with a shared typed helper, similar in spirit to `analysis_pack_cache.py`, while keeping pack-specific validation explicit.
  - Pros: Smaller generator surface, fewer cache bugs, and easier extension of source-analysis phases.
  - Cons: Needs careful API design to avoid over-generalizing distinct cache semantics.
  - Acceptance Criteria:
    - Repeated cache read/write/miss logging paths in report-source generation are centralized.
    - Each cached phase still validates its own payload shape explicitly.
    - Existing source-generation tests continue to cover hit/miss/stale-cache behavior.

---

## 5. Orchestration, Durability & Performance

- **Title:** Introduce durable, checkpointed pipeline stages [Impact: 5/5, Effort: 5/5]
  - Explanation: Make pipeline stages durable and checkpointed so runs can resume mid-run and reprocess selective stages.
  - Pros: Faster recovery, selective reprocessing, operator convenience.
  - Cons: Requires state modeling and migration in DB.
  - Acceptance Criteria:
    - Stage-level checkpoints stored in state DB with artifact references.
    - A run can resume from a checkpoint and produce consistent results.

- **Title:** Stream LLM responses with early validation / fail-fast [Impact: 3/5, Effort: 4/5]
  - Explanation: Support streaming model responses and implement early validation to fail fast on invalid shapes or low-confidence content during generation.
  - Pros: Faster feedback, reduced wasted compute on clearly invalid outputs.
  - Cons: More complex streaming handlers and validation logic.
  - Acceptance Criteria:
    - Streaming path implemented for key generators.
    - Early validation hooks can abort and surface clear errors.

- **Title:** Promote MD5 sidecar handling into a dedicated typed file-cache service [Impact: 3/5, Effort: 3/5]
  - Explanation: `src/orchestrators/ingest_orchestrator.py` currently owns md5 sidecar path construction, JSON parsing, stat reconciliation, and fallback logic. Move that into a dedicated service/contract pair so ingest orchestration only asks for typed cache answers.
  - Pros: Smaller orchestrator surface and fewer opportunities for ad-hoc cache drift.
  - Cons: Requires moving a well-tested but intertwined code path across layers.
  - Acceptance Criteria:
    - MD5 sidecar pathing, load, validation, and write logic live behind a service boundary.
    - Ingest orchestration no longer parses sidecar JSON directly.
    - Existing cache-hit/cache-miss correctness is preserved by tests.

- **Title:** Stream Drive pagination results instead of materializing entire page batches [Impact: 3/5, Effort: 2/5]
  - Explanation: `src/services/drive_service.py` currently accumulates full page responses in `_list_files_paginated()` before yielding files. Convert listing to a streaming iterator so large folders do not require materializing every page into intermediate lists.
  - Pros: Lower memory usage and earlier first-result latency for large Drive folders.
  - Cons: Requires careful logging and partial-failure behavior when streaming pages.
  - Acceptance Criteria:
    - Drive file listing yields results incrementally across paginated responses.
    - Large-folder ingest no longer depends on full in-memory page accumulation.
    - Listing tests cover partial completion and logging on mid-stream failures.

- **Title:** Cache resolved Drive folder scope for recursive listings [Impact: 3/5, Effort: 2/5]
  - Explanation: Recursive listing currently re-traverses Drive subfolder structure every time `_resolve_folder_scope()` runs. Cache the resolved folder-id set behind a key that includes the root folder and Drive settings, with explicit invalidation controls.
  - Pros: Less API chatter and faster repeated ingest/list operations on stable folder trees.
  - Cons: Folder topology changes need a reliable refresh path.
  - Acceptance Criteria:
    - Recursive folder-scope expansion is cached with explicit invalidation or TTL.
    - Repeated ingest/list operations reuse cached scope when inputs are unchanged.
    - Tests cover refresh behavior after folder additions/removals.

- **Title:** Bound and evict thread-scoped Drive client caches [Impact: 2/5, Effort: 2/5]
  - Explanation: `src/services/drive_service.py` caches Drive clients by auth mode, credential path, and thread id with no eviction strategy. Add bounded lifetime/cleanup rules so long-running sessions do not accumulate stale thread-bound clients indefinitely.
  - Pros: Lower memory/resource leakage risk and cleaner long-lived process behavior.
  - Cons: Needs eviction rules that do not thrash clients under normal concurrency.
  - Acceptance Criteria:
    - Drive client cache size/lifetime is bounded.
    - Stale thread-specific clients are evicted or refreshed safely.
    - Tests cover reuse, eviction, and concurrent access behavior.

- **Title:** Move vector-store wait loops out of services and into orchestrator retry policy [Impact: 4/5, Effort: 3/5]
  - Explanation: `src/services/vector_store_service.py` currently owns a polling loop with `sleep`, which mixes control-plane waiting into a service boundary. Make status fetch a pure service call and let orchestrators own wait/backoff/idempotency policy.
  - Pros: Cleaner role boundaries, easier retry testing, and more reusable status checks.
  - Cons: Requires touching vector-store orchestration and dependent tests.
  - Acceptance Criteria:
    - Service layer exposes status fetch without internal wait loops.
    - Polling/backoff lives in orchestrators or retry helpers with structured logging.
    - Vector-store timeout/failure behavior is preserved by pipeline tests.

- **Title:** Make analysis packs, HTML renders, and cache artifacts atomic on write [Impact: 4/5, Effort: 3/5]
  - Explanation: `src/services/report_analysis_store_service.py`, `src/services/render_service.py`, and cache-writing paths write directly to final files. Switch to temp-file + rename semantics so interrupted runs do not leave partial JSON/HTML artifacts behind.
  - Pros: Better durability and fewer corrupted artifacts after failures or interrupted runs.
  - Cons: Slightly more write-path complexity and temp-file cleanup logic.
  - Acceptance Criteria:
    - Analysis-pack, render, and cache writes use atomic replace semantics.
    - Interrupted writes do not leave partially written final artifacts.
    - Tests cover overwrite and failure-mid-write scenarios.

---

## 6. Publishing & WordPress

- **Title:** Parallelize WordPress media uploads and remove duplicated auth-header derivation [Impact: 4/5, Effort: 3/5]
  - Explanation: Speed up publishing by parallelizing uploads and pass the resolved auth header through the publish request flow. The current code still derives auth in both `publish_orchestrator` and `publish_generator`.
  - Pros: Faster publish time; simpler auth flows.
  - Cons: Concurrency and API rate-limit handling required.
  - Acceptance Criteria:
    - Media uploads run in parallel and respect rate limits.
    - Auth header is resolved once at the orchestration boundary and passed through to publish operations.
    - No duplicate auth derivation remains in the publish path.

- **Title:** Turn publish queue snapshot into a durable publish job queue with retry/backoff/idempotency [Impact: 5/5, Effort: 5/5]
  - Explanation: The repo already has `publish_queue_orchestrator`, but today it is a snapshot/read-model only. Extend publishing so jobs are enqueued, persisted, retried with backoff, and executed idempotently.
  - Pros: More reliable publishing and easier retry handling.
  - Cons: Operational overhead and queue infrastructure.
  - Acceptance Criteria:
    - Publish tasks can be enqueued and retried with idempotency keys.
    - Publish failures are retried with backoff and logged.

- **Title:** Introduce a shared WordPress request executor with pooled sessions and error adaptation [Impact: 4/5, Effort: 4/5]
  - Explanation: `src/services/wordpress_service.py` repeats request setup, SSL handling, error parsing, and JSON adaptation across upload/post/term operations. Centralize that into one internal request executor backed by a pooled `requests.Session`.
  - Pros: Less duplicated HTTP code, lower connection overhead, and more consistent error handling.
  - Cons: Requires careful migration of per-endpoint behavior and logging details.
  - Acceptance Criteria:
    - WordPress REST calls go through one shared executor or session helper.
    - Existing request/response logging and error taxonomy remain intact.
    - Connection reuse is covered by service tests or instrumentation.

- **Title:** Batch WordPress taxonomy/tag ensure flows [Impact: 3/5, Effort: 3/5]
  - Explanation: Taxonomy and tag ensure operations currently work through repeated lookup/create cycles. Add batched lookup and creation planning per publish run so term resolution happens once per taxonomy set instead of one item at a time.
  - Pros: Fewer WordPress round trips and simpler publish-generator control flow.
  - Cons: Needs careful handling of partial term-creation failures.
  - Acceptance Criteria:
    - Publish flows perform batched term lookup/planning per run.
    - Duplicate per-term REST calls are reduced for common publish cases.
    - Tests cover mixed existing/new term scenarios.

- **Title:** Remove duplicate HTML reads and parses from the publish path [Impact: 3/5, Effort: 2/5]
  - Explanation: `src/orchestrators/publish_orchestrator.py` may read HTML once to extract `file_id` and then process the same HTML again downstream. Carry preloaded HTML and parsed metadata through the publish request path instead of reopening the same file.
  - Pros: Less file I/O, simpler publish control flow, and fewer parsing inconsistencies.
  - Cons: Requires request/contract changes between orchestrator and generator.
  - Acceptance Criteria:
    - Publish flow reads each HTML artifact at most once per attempt.
    - File ID extraction, validation lookup, and publish generation reuse the same loaded HTML payload.
    - Publish tests cover both preloaded and non-preloaded entry paths.

- **Title:** Add a batch publish preflight read model for state and post lookups [Impact: 3/5, Effort: 3/5]
  - Explanation: Publishing currently performs per-file state checks, published checks, validation reads, and post lookups. Add a batch preflight read model so publish orchestration resolves these inputs once before iterating files.
  - Pros: Fewer repeated service calls and clearer decision-making for skip/error paths.
  - Cons: Adds a precomputation layer that must stay consistent with per-file behavior.
  - Acceptance Criteria:
    - Publish preflight data is loaded in batch for the selected HTML set.
    - Per-file publish decisions consume the batch snapshot instead of re-querying common state.
    - Tests verify parity with current skip/already-published behavior.

- **Title:** Preflight browser-report downloads with lightweight HTTP and wrapper inspection before agent launch [Impact: 4/5, Effort: 3/5]
  - Explanation: `src/services/browser_report_download_service.py` builds the browser-use runtime immediately, even when a direct PDF or simple wrapper page could be identified through a lightweight HTTP fetch. Add a preflight path that checks direct PDF signatures and embedded PDF wrappers before spinning up the browser agent.
  - Pros: Lower cost and latency for simple download routes.
  - Cons: Needs careful heuristics to avoid false positives on JS-heavy pages.
  - Acceptance Criteria:
    - Direct PDF and simple wrapper cases are handled without browser-agent startup.
    - Browser-agent launch remains the fallback for ambiguous or JS-dependent routes.
    - Tests cover direct-PDF, wrapper-page, and browser-required cases.

- **Title:** Move browser-download task prompts into prompt-service namespaces [Impact: 3/5, Effort: 2/5]
  - Explanation: `src/services/browser_report_download_service.py` currently constructs its agent task prompt inline. Move that text into dedicated prompt namespaces so browser-download instructions are versioned, hash-logged, and maintained consistently with the rest of the prompt system.
  - Pros: Better prompt observability, easier iteration, and reduced service-level string assembly.
  - Cons: Requires prompt fixtures and migration of prompt variables into explicit contracts.
  - Acceptance Criteria:
    - Browser-download task text is loaded and rendered via prompt service.
    - Prompt paths, hashes, and rendered text are logged for browser-download runs.
    - Existing browser-download tests are updated to cover prompt rendering.

---

## 7. Schema, Validation & Output Quality

---

## 8. Audit-Driven Refactors & Compliance

### 8.1 Core High-Impact Refactors
- **Title:** SQLite: adopt WAL and narrow lock scopes [Impact: 5/5, Effort: 3/5]
  - Explanation: Reduce global SQLite locking by using WAL, setting busy timeouts, and minimizing critical sections for state updates.
  - Pros: Higher concurrency and throughput.
  - Cons: Requires migration and careful testing on Windows file systems.
  - Acceptance Criteria:
    - WAL mode enabled with safe busy timeouts.
    - Concurrency tests show reduced contention.

- **Title:** Persist normalized publisher lookup keys and replace Python-side table scans [Impact: 4/5, Effort: 4/5]
  - Explanation: `src/services/report_store_service.py` repeatedly loads publisher rows and normalizes `insights_url` in Python for route and inventory lookups/updates. Persist normalized lookup keys in the database, index them, and query/update rows directly in SQL.
  - Pros: Faster publisher-state lookups, less repeated normalization logic, and smaller service methods.
  - Cons: Requires a schema migration and careful handling of normalization collisions.
  - Acceptance Criteria:
    - Normalized publisher lookup columns are stored and backfilled in the database.
    - Indexed SQL lookups replace current `fetchall()` + Python filtering paths for publisher route and inventory operations.
    - Collision behavior is defined and covered by tests.
    - Existing route/inventory tests continue to pass against the migrated schema.

### 8.2 Additional Audit Items

- **Title:** Fix O(n^2) table dedupe hotspot [Impact: 4/5, Effort: 3/5]
  - Explanation: Replace the O(n^2) table dedupe algorithm in candidate extraction with a more efficient approach (hashing/indexing) to improve performance on large documents.
  - Pros: Better performance on large reports.
  - Cons: Requires careful correctness tests to avoid false merges.
  - Acceptance Criteria:
    - Dedupe algorithm updated and benchmarked with large PDFs.
    - No regressions in deduplication correctness tests.

- **Title:** Reuse candidate crop output path / guard unused crop pass [Impact: 3/5, Effort: 2/5]
  - Explanation: Ensure candidate crop output paths are used or guard/remove the unused crop pass to avoid wasted computation and confusion.
  - Pros: Removes wasted I/O and clarifies pipeline.
  - Cons: Requires auditing downstream consumers.
  - Acceptance Criteria:
    - Unused crop pass removed or guarded behind config.
    - Crop output paths are consumed by report generator or persisted for debug.

- **Title:** Add per-stage feature flags for controlled rollout [Impact: 3/5, Effort: 3/5]
  - Explanation: Add feature-flagging at the stage level to enable controlled rollouts, A/B tests, and emergency disable switches for costly steps.
  - Pros: Safer deployments and cost governance.
  - Cons: Adds configuration surface and flag management.
  - Acceptance Criteria:
    - Per-stage flags configurable and respected by orchestrators.
    - Tests validate enabling/disabling stages.

### 8.3 Quick Wins

Each quick-win should be documented with a short task when prioritized.

### 8.4 Architecture-Fit Additions

- **Title:** Normalize config defaults, portability, and shared YAML loading [Impact: 4/5, Effort: 4/5]
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

- **Title:** Finish PDF extraction internal split and remove private cross-module imports [Impact: 5/5, Effort: 5/5]
  - Explanation: `src/services/_pdf/visual_candidates.py` and `src/services/_pdf/table_candidates.py` still import dozens of private helpers and constants from `src/services/_pdf/figures.py`, which keeps `figures.py` as a 7k-line god module. Extract shared geometry/text/caption/scoring heuristics into explicit internal modules and keep `pdf_service` as the only public boundary.
  - Pros: Lower cognitive load, clearer ownership of PDF heuristics, and easier performance tuning without touching one giant file.
  - Cons: Broad refactor with risk of subtle heuristic regressions if test coverage misses edge cases.
  - Acceptance Criteria:
    - Capability modules no longer import private helpers directly from `figures.py`.
    - Shared heuristics live in named internal modules with focused tests.
    - `src/services/pdf_service.py` remains the single canonical public boundary.
    - Existing candidate-extraction and crop tests continue to pass without behavior drift.

- **Title:** Externalize publisher-inventory browser scripts and traversal state [Impact: 3/5, Effort: 4/5]
  - Explanation: `src/services/publisher_inventory_service.py` embeds large JavaScript snippets with repeated selector, visibility, and normalization helpers, while traversal metrics are rebuilt repeatedly during browser flows. Move browser actions/state extraction into named internal script modules or assets, reuse one helper bundle, and model traversal state updates through explicit typed state helpers.
  - Pros: Smaller service surface, less duplicated browser logic, easier targeted testing, and less brittle DOM-script maintenance.
  - Cons: Requires careful script-loading and browser-test updates.
  - Acceptance Criteria:
    - Inline browser action/state scripts are replaced by named internal script builders or assets.
    - Shared selector/visibility/normalization logic is defined once and reused across browser actions.
    - Traversal state/metrics updates use explicit helpers instead of repeated manual dataclass reconstruction.
    - Browser-inventory tests cover the extracted script/runtime contract.

- **Title:** Expand architecture boundary checks from I/O linting to full import-role enforcement [Impact: 4/5, Effort: 3/5]
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

- **Title:** Enforce prompt immutability outside prompt service and complete prompt observability [Impact: 5/5, Effort: 3/5]
  - Explanation: Ban runtime prompt text mutation/concatenation outside prompt service and ensure every model call logs prompt namespace, file paths, prompt hashes, exact rendered prompts, model params, and raw response.
  - Pros: Reproducibility and auditability of model behavior.
  - Cons: Larger logs and redaction policy tuning.
  - Acceptance Criteria:
    - No runtime prompt string concatenation outside prompt service.
    - Generator logs include required prompt and model metadata for every model call.
    - Raw model response logging present with redaction safeguards.

- **Title:** Finish remaining generator/service/control-flow refactors and boundary cleanup [Impact: 5/5, Effort: 5/5]
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

- **Title:** Finish rollout of AGENTS test-integrity fixtures and boundary-only mocking [Impact: 4/5, Effort: 4/5]
  - Explanation: The shared fixtures now exist in `tests/conftest.py`, but the suite still contains raw `monkeypatch` usage against generator/orchestrator internals. Finish migrating remaining hotspots to boundary-only mocks and fixture-based assertions.
  - Pros: Higher confidence that tests validate real behavior.
  - Cons: Test rewrite effort, especially around orchestration-heavy paths.
  - Acceptance Criteria:
    - New and touched tests use the shared fixtures instead of ad-hoc assertion helpers.
    - Private/helper patching and internal orchestrator/generator patching are removed from remaining hotspots.
    - Orchestrator and service tests assert required structured log fields.
    - Idempotency behavior asserted where applicable.

- **Title:** Meet minimum integration-test coverage per service module [Impact: 4/5, Effort: 5/5]
  - Explanation: Add at least one marked integration test per service module and keep live API calls out of unit tests.
  - Pros: Better boundary confidence and fewer production surprises.
  - Cons: More test runtime and environment setup complexity.
  - Acceptance Criteria:
    - `tests/integration/` includes at least one integration test per service module.
    - Integration tests are explicitly marked and excluded from default CI unit run.
    - Unit tests avoid live external calls.

## 9. Supplemental Code-Reduction Intake

This section absorbs the remaining open appendix items from `docs/quality/ineffective-choices-top50.md` so the consolidated TODO remains the only active backlog.


