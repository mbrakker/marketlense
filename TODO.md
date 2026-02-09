# TODO

1. Upgrade all prompts.
   - Prompt namespaces live under `src/prompts/**` (report_generation, report_vs/{doc_map,evidence_packs,artifacts,validate}, rank_candidates). Refresh wording, safety, and output formats; ensure variables match renderer usage in `prompt_service` and bump schema/version hashes for logging.
2. Add vector store deletion support.
    - No delete API in `vector_store_service`; flag `vector_store_keep` is unused for cleanup. Add delete/prune operations (vector store + files) and orchestrator hooks to avoid orphaned stores.
3. Define and enforce cost limits.
    - Costs are tracked (`cost_ledger_path`, `cost_daily_path`, pricing in `app.yaml`) but not enforced. Add config thresholds (per-run/day) and guardrails in orchestrators before OpenAI calls, with blocking/warning behavior and logging.
4. Refine HTML and deduplicate repeated blocks.
    - `templates/report.html.j2` contains repeated preview/figure handling and inline styling. Extract reusable blocks/macros, de-duplicate preview/gallery logic, and ensure consistent metadata rendering to reduce drift.
5. Refine figure candidates and ranker to avoid low-data images.
    - Current figure selection relies on extracted candidates and ranking (see `figure_service`, `rank_service`, and `candidate_extraction_service` plus cropping). Add an image analysis step (OCR/content density/heuristics) to filter low-text/low-chart pages, improve table/chart detection and cropping, and feed richer features into the ranker to reduce weak visuals.
6. Add infographics creator for HTML design and LinkedIn posts.
    - Beyond text rendering, there is no infographic generation pipeline. Add a generator/service to produce simple infographics/hero visuals for HTML and LinkedIn artifacts, wired into rendering and artifact generation flows.
7. Support multiple prompts per process for variations/expert roles.
    - Today each step uses a single prompt set per namespace. Add a mechanism to run multiple prompt variants per step (e.g., different expert personas or stylistic variants), collect outputs, and select/ensemble or expose them, while keeping prompt logging/versioning intact.
8. Validate report text extractability.
    - Before uploading to the vector store, check three random pages of the report for extractable text (no OCR required). If no text is found, log an error and halt further processing.

# Detailed Proposals

## 1. Upgrade all prompts
- **Context**: Prompt namespaces live under `src/prompts/**` and are loaded via `prompt_service` contracts and `PromptLoadRequest`.
- **Proposal**:
  - Audit every namespace (report_generation, report_vs/{doc_map,evidence_packs,artifacts,validate}, rank_candidates) for clarity, safety, and schema alignment.
  - Update prompt variables to match renderer usage (e.g., `PromptRenderRequest` variable names in generators).
  - Bump prompt schema/version hashes and ensure logging is updated with new hashes.
- **Acceptance**:
  - All prompts render without missing variables.
  - Updated prompt hashes appear in generator logs.

## 2. Add vector store deletion support
- **Context**: No delete/prune API exists in `vector_store_service`; `vector_store_keep` is unused for cleanup.
- **Proposal**:
  - Add delete operations in `vector_store_service` and wire them into orchestrators when `vector_store_keep` is false.
  - Ensure deletion covers vector store assets and related files.
  - Log deletion decisions with run/task/span IDs.
- **Acceptance**:
  - Orphaned vector stores are cleaned up when configured.
  - Logs confirm deletion operations with IDs.

## 3. Define and enforce cost limits
- **Context**: Costs are tracked in `cost_ledger_path`/`cost_daily_path` but there are no guardrails.
- **Proposal**:
  - Add config thresholds in `app.yaml` (per-run and per-day) and surface them in `AppSettings`.
  - Add orchestrator checks before OpenAI calls to block or warn based on thresholds.
  - Log decisions and include the threshold values in structured logs.
- **Acceptance**:
  - Runs stop or warn when crossing configured cost limits.
  - Logs show thresholds and current spend when a block occurs.

## 4. Refine HTML and deduplicate repeated blocks
- **Context**: `templates/report.html.j2` has repeated preview/figure handling and inline styling.
- **Proposal**:
  - Extract Jinja macros/partials for repeated preview/figure blocks.
  - Normalize metadata rendering and shared styles to reduce drift.
  - Add a small fixture to confirm the output structure remains stable.
- **Acceptance**:
  - HTML template no longer duplicates preview/gallery logic.
  - Metadata block renders consistently across sections.

## 5. Refine figure candidates and ranker to avoid low-data images
- **Context**: Figure selection relies on `figure_service`, `rank_service`, and `candidate_extraction_service`, but low-signal images slip through.
- **Proposal**:
  - Add an image quality filter (OCR density, chart/table heuristics, minimum text coverage).
  - Extend candidate metadata with quality scores and feed them into ranking inputs.
  - Improve cropping for chart/table boundaries before ranking.
- **Acceptance**:
  - Candidate set excludes low-content images and prioritizes meaningful charts.
  - Ranking inputs include explicit quality features.

## 6. Add infographics creator for HTML design and LinkedIn posts
- **Context**: No pipeline exists for generating infographic assets beyond text artifacts.
- **Proposal**:
  - Add a generator/service pair to create infographic assets (SVG/PNG) from report highlights.
  - Wire into HTML rendering and LinkedIn artifact generation flows.
  - Store artifacts alongside existing outputs with metadata for reuse.
- **Acceptance**:
  - Infographic assets are created and referenced in HTML/LinkedIn outputs.
  - Artifacts are logged and stored with report metadata.

## 7. Support multiple prompts per process for variations/expert roles
- **Context**: Each step uses one prompt namespace; no multi-prompt selection exists.
- **Proposal**:
  - Add configuration for multiple prompt variants per namespace.
  - Generate outputs for each variant, then select/ensemble using a scoring heuristic or validation step.
  - Preserve prompt logging/versioning for each variant.
- **Acceptance**:
  - Multiple prompt variants can be run per step and results are captured.
  - Selection logic is logged with variant identifiers.

## 8. Validate report text extractability
- **Context**: Reports without extractable text may indicate issues with the input PDF or earlier processing steps, leading to wasted resources if uploaded to the vector store.
- **Proposal**:
  - Implement a validation step to randomly select three pages from the report and check for extractable text.
  - If none of the selected pages contain text, log an error message and stop further processing for the current report.
  - Ensure this validation step is integrated into the orchestrator pipeline before vector store upload.
- **Acceptance**:
  - Reports without extractable text are halted with a clear error message.
  - Logs & state database contain detailed information about the failure for debugging.

## Codebase Audit Backlog (added 2026-02-09)

### Findings (ordered by impact)
1. Monolithic generator with mixed responsibilities.
   - `generate_report` is ~1275 lines and combines orchestration, caching, service coordination, rendering, persistence, and cleanup in one place (`src/generators/report_generator.py:434`).
2. Candidate extraction service is oversized and exception-heavy.
   - Single module is ~2248 lines with many broad `except Exception` handlers and branch-heavy logic (`src/services/candidate_extraction_service.py:1317`).
3. Retry logic is duplicated and inconsistent.
   - Separate retry implementations with no jitter and different retry semantics (`src/orchestrators/ingest_orchestrator.py:283`, `src/orchestrators/candidate_extraction_orchestrator.py:32`, `src/orchestrators/publish_orchestrator.py:329`).
4. Redundant state checks in ingest.
   - Same file can trigger multiple already-processed checks in one lifecycle (`src/orchestrators/ingest_orchestrator.py:830`, `src/orchestrators/ingest_orchestrator.py:329`, `src/orchestrators/ingest_orchestrator.py:490`).
5. Global SQLite locks serialize work and cap throughput.
   - Full DB operations run under process-wide locks (`src/services/state_service.py:73`, `src/services/report_store_service.py:82`).
6. Cost rollup runs full aggregation per request.
   - Every model call appends one ledger entry and re-rolls the full ledger file (`src/services/cost_ledger_service.py:121`, calls from `src/services/openai_service.py` and `src/services/rank_service.py`).
7. OpenAI integration logic is duplicated.
   - Similar request/parse/cost logging flow exists across `openai_service` and `rank_service`.
8. WordPress term ensure logic is duplicated and N+1.
   - `ensure_categories` and `ensure_tags` mirror each other and issue sequential GET/POST calls (`src/services/wordpress_service.py:252`, `src/services/wordpress_service.py:347`).
9. Redundant slugify calls and no tag dedup before API calls.
   - Tag slug generation is repeated and not deduplicated (`src/generators/publish_generator.py:107`).
10. PDF reopened unnecessarily in candidate extraction path.
   - Charts may reuse context; tables reopen docs independently (`src/services/candidate_extraction_service.py:2231`, `src/services/candidate_extraction_service.py:1538`, `src/services/candidate_extraction_service.py:1543`).
11. O(n^2) table dedupe hotspot.
   - Candidate dedupe compares each new item against kept list linearly (`src/services/candidate_extraction_service.py:2182`).
12. Unused candidate crop output path.
   - Candidate crop results are created but not consumed downstream (`src/generators/report_generator.py:1018`, `src/generators/report_generator.py:1060`).
13. Dead/legacy config surface: `debug_candidate_gallery`.
   - Present in config/contracts but not used by runtime execution flow.
14. Legacy compare mode still exposed while forced off.
   - `analysis_compare` surfaced in UI but effectively hard-disabled (`src/services/config_service.py:195`, `src/streamlit_app.py:1087`).
15. Jinja environment recreated on each render call.
   - `Environment(...)` built per request (`src/services/render_service.py:24`).
16. Potential double-close FD path in lock handling.
   - `os.fdopen` context plus manual `os.close(fd)` in exception branch (`src/services/lock_service.py:140`, `src/services/lock_service.py:143`).
17. Repeated metadata JSON parsing logic.
   - `get_metadata` and `list_metadata` duplicate parsing/cleanup code (`src/services/report_store_service.py:350`, `src/services/report_store_service.py:503`).
18. Duplicate duration scripts with drift risk.
   - `calculate_durations.py` and `scripts/calculate_durations.py` overlap with different behavior.
19. Streamlit app is too large/highly coupled.
   - `src/streamlit_app.py` is ~1807 lines with large page/render functions.

### Remediation plan
1. P0 quick wins (1-2 days)
   - Remove/guard unused candidate crop pass.
   - Deduplicate tag slugs and avoid repeated slugify.
   - Cache Jinja `Environment` at module scope.
   - Fix lock FD handling.
   - Consolidate duration scripts.
2. P1 throughput (2-4 days)
   - Collapse ingest skip checks to a single state decision per file lifecycle.
   - Move SQLite to WAL + busy timeout and narrow lock scope.
   - Change cost rollup to incremental/periodic (not per request).
3. P1 reliability (2-3 days)
   - Add shared retry utility (bounded exponential backoff + jitter + typed retry policy).
   - Reuse PDF context across candidate extraction stages.
   - Replace broad exception catches with typed errors and explicit fallbacks.
4. P2 architecture (4-7 days)
   - Split `generate_report` into smaller generator steps with typed step contracts.
   - Unify OpenAI call path so rank flow reuses shared service logic.
   - Extract reusable WordPress term ensure helper.
   - Extract shared metadata row parser for report store.
5. P2 cleanup/redundancy (1-2 days)
   - Remove or fully implement `debug_candidate_gallery`.
   - Remove legacy `analysis_compare` UI/config surface or implement true compare mode.
   - Normalize cache-key strategy across orchestrators.
6. Validation gate
   - Keep `pytest` green; add perf/benchmark checks for ingest and cost-ledger growth.
   - Add regression tests for extraction fallback paths and metadata parsing helpers.

## Test Suite Integrity Backlog (added 2026-02-09)

### Findings to fix (anti-shortcuts / anti-cheats)
1. Retry behavior test is weak.
   - `tests/test_orchestrator_retry.py` currently asserts only final error outcome; it does not prove retries/backoff occurred.
2. Parallel ingest test does not run real parallel work.
   - `tests/test_ingest_parallel.py` uses a synchronous dummy executor, so concurrency/race behavior is not exercised.
3. Vector-store wiring test collects call trace but does not assert it.
   - `tests/test_vector_pipeline_wiring.py` records `vector_calls` but never validates expected create/upload/attach/wait sequence.
4. Over-mocking in orchestrator wiring tests reduces regression detection.
   - `tests/test_vector_pipeline_wiring.py`, `tests/test_publish_orchestrator.py`, and `tests/test_ingest_parallel.py` stub many boundaries and mostly validate mocked paths.
5. Unsafe smoke script in repository root.
   - `test_openai.py` prints API key prefix and performs a live API call at import-time if run directly.
6. Brittle full-list UI snapshot.
   - `tests/test_streamlit_navigation.py` hardcodes full nav order/text and may fail on low-risk copy/order updates.

### Remediation plan
1. Strengthen retry verification.
   - Assert retry attempt count (`generate_report` call count), `time.sleep` calls, and bounded backoff progression in `tests/test_orchestrator_retry.py`.
2. Add a real-concurrency ingest test.
   - Keep one unit test with fake executor for determinism, plus one integration-style test using real `ThreadPoolExecutor` and synchronization primitives.
3. Enforce vector pipeline call contract.
   - Add explicit assertions for `vector_calls` sequence and key parameters in `tests/test_vector_pipeline_wiring.py`.
4. Reduce over-mocking by adding service-level integration fixtures.
   - Introduce temp-dir + sqlite + fixture PDF based tests that keep real file/state/report services and only mock external APIs.
5. Convert `test_openai.py` into explicit opt-in integration smoke test.
   - Move under `tests/integration/` (or `scripts/`), add marker/guard, remove API key echo, and prevent execution on import.
6. Relax brittle UI snapshot checks.
   - Assert required sections and invariants instead of exact full list ordering where ordering is not business-critical.

