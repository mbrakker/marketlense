# TODO

Last reviewed: 2026-02-11

## Active Priorities

1. Upgrade and align prompts.
   - Prompt namespaces live under `src/prompts/**` (`report_generation`, `report_vs/{doc_map,evidence_packs,artifacts,validate,taxonomy}`, `rank_candidates`).
   - Refresh wording, safety, and output contracts; ensure variables match renderer usage in `prompt_service`.
   - Keep prompt hash/version logging intact for every generator call.

2. Add vector store deletion and lifecycle cleanup.
   - `src/services/vector_store_service.py` still has no delete/prune API (create/upload/attach/status/wait/update only).
   - `vector_store_keep` is used for reuse/caching, but not for cleanup of remote vector store assets.
   - Add explicit delete operations (vector store and uploaded files) and orchestrator hooks when retention is disabled.

3. Define and enforce cost limits.
   - Cost tracking exists (`cost_ledger_path`, `cost_daily_path`, pricing in `src/config/app.yaml`) but no run/day guardrails are enforced before model calls.
   - Add configurable thresholds (warn/block), check them in orchestrators, and log decisions with current spend and limits.

4. Refactor HTML template and remove duplication.
   - `templates/report.html.j2` still contains duplicated image rendering patterns and inline style fragments.
   - Extract reusable blocks/macros, unify figure/preview rendering, and keep metadata rendering consistent.

5. Improve figure candidate quality and ranking.
   - Current pipeline uses candidate extraction and ranking, but still lacks richer quality features (OCR density, chart/table confidence, low-information suppression) in rank inputs.
   - Keep existing text extractability gate as-is, but improve candidate-level filtering/cropping before ranking.

6. Add infographic asset generation for HTML and LinkedIn.
   - Artifacts currently include text outputs (summary, insights, quotes, expert comment, LinkedIn post) but no generated infographic assets.
   - Add generator/service flow for simple SVG/PNG infographics and wire output references into rendered HTML + publish artifacts.

7. Support multi-prompt variants per step.
   - Current generators load one prompt namespace per step.
   - Add config-driven variants (for expert roles/styles), capture logs per variant, and add selection/ensemble logic.

## Completed Recently (Removed from active TODO)

1. Report text extractability validation is implemented.
   - Sampling + halt behavior exists in `src/generators/report_generator.py` with `sample_pdf_text` and `pdf_text_sample_pages` (default `3`) from `src/contracts/ingest.py` and `src/config/app.yaml`.
   - On no extractable text in sampled pages, pipeline returns `pdf_text_unextractable` and stops.

## Detailed Proposals

### 1. Upgrade and align prompts

- Audit all namespaces for clarity/safety and schema alignment.
- Ensure every rendered variable is present and typed in generator context.
- Keep prompt hash logging (`prompt_system_sha256`, `prompt_user_sha256`) stable in generator logs.

Acceptance:

- No missing-variable prompt render failures.
- Prompt hashes visible for each model call path.

### 2. Add vector store deletion and lifecycle cleanup

- Extend `vector_store_service` with delete APIs.
- Add orchestrator-level cleanup policies (for completed, failed, and canceled runs).
- Log cleanup decisions and results with run/task/span identifiers.

Acceptance:

- No orphaned vector stores/files when cleanup is enabled.
- Cleanup operations are traceable in logs.

### 3. Define and enforce cost limits

- Add per-run and per-day thresholds in configuration.
- Evaluate thresholds before OpenAI calls.
- Add explicit actions: warn-only, soft-stop, hard-block.

Acceptance:

- Runs consistently stop/warn according to configured policy.
- Logs contain threshold values, spend snapshot, and action taken.

### 4. Refactor HTML template and remove duplication

- Introduce Jinja macros/partials for repeated preview/figure blocks.
- Move repeated inline image styles to shared CSS classes.
- Keep deterministic output structure for stable rendering and tests.

Acceptance:

- No duplicated preview/figure branches.
- Metadata and asset sections render consistently.

### 5. Improve figure candidate quality and ranking

- Add candidate-level quality signals (text density, chart/table confidence, visual entropy).
- Feed these signals into rank payloads.
- Improve crop bounds to reduce low-value fragments.

Acceptance:

- Lower rate of low-signal selected figures.
- Ranking inputs explicitly include quality fields.

### 6. Add infographic asset generation

- Add generator/service pair to produce infographic assets from validated highlights.
- Persist assets with metadata in report analysis outputs.
- Render generated assets in HTML and make them available for publishing.

Acceptance:

- Generated infographic assets exist per report.
- HTML and publishing paths can consume them.

### 7. Support multi-prompt variants per step

- Define variant config per namespace.
- Run variants and score/select outputs.
- Preserve per-variant prompt hashes, rendered prompts, and model metadata in logs.

Acceptance:

- Multiple variants can be executed and selected deterministically.
- Logs clearly show variant IDs and selection rationale.

## Codebase Audit Backlog (still open)

Findings (ordered by impact):

1. Monolithic generator with mixed responsibilities.
   - `src/generators/report_generator.py` is still very large and combines orchestration, caching, service coordination, rendering, and persistence.
2. Candidate extraction service is oversized and exception-heavy.
   - `src/services/candidate_extraction_service.py` remains large and branch-dense with broad exception handling.
3. Retry logic is duplicated and inconsistent.
   - Separate retry implementations remain in ingest/candidate-extraction/publish orchestrators with different behavior.
4. Duplicate skip checks in ingest flow.
   - Skip checks happen at list filtering and file-processing stages, causing repeated state checks in some paths.
5. Global SQLite locks serialize work.
   - `src/services/state_service.py` and `src/services/report_store_service.py` still use process-wide locks around DB access.
6. Cost rollup recomputes from full ledger frequently.
   - `src/services/openai_service.py` and `src/services/rank_service.py` append one entry and call full `rollup_daily`.
7. OpenAI request/cost logic remains duplicated.
   - Similar usage parsing and ledger write logic exists in both `openai_service` and `rank_service`.
8. WordPress term ensure logic is duplicated.
   - `ensure_categories` and `ensure_tags` follow similar N+1 request patterns in `src/services/wordpress_service.py`.
9. Repeated slugify calls in publish flow.
   - `src/generators/publish_generator.py` repeatedly slugifies tags in list comprehension.
10. PDF context reuse is still uneven in candidate extraction path.
11. O(n^2) table dedupe hotspot remains in candidate extraction.
12. Candidate crop output path is still unused in report generator.
13. `debug_candidate_gallery` config surface remains dead (not used by runtime).
14. Legacy `analysis_compare` is still surfaced while effectively forced off.
15. Jinja environment is recreated per render call in `src/services/render_service.py`.
16. Lock service still has a potential double-close fd path in exception handling.
17. Metadata JSON parsing logic is duplicated between `get_metadata` and `list_metadata` in `src/services/report_store_service.py`.
18. Duplicate duration scripts remain (`calculate_durations.py`, `scripts/calculate_durations.py`).
19. `src/streamlit_app.py` is still large and highly coupled.

Remediation plan:

1. P0 quick wins (1-2 days)
   - Remove/guard unused candidate crop pass.
   - Deduplicate tag slugs and avoid repeated slugify.
   - Cache Jinja `Environment` at module scope.
   - Fix lock fd handling.
   - Consolidate duration scripts.
2. P1 throughput (2-4 days)
   - Collapse repeated ingest skip checks where safe.
   - Move SQLite to WAL + busy timeout and narrow lock scope.
   - Make cost rollup incremental or scheduled (not per request).
3. P1 reliability (2-3 days)
   - Add shared retry utility (bounded exponential backoff + jitter + typed retry policy).
   - Reuse PDF context consistently across candidate extraction stages.
   - Replace broad exception catches with typed errors and explicit fallbacks.
4. P2 architecture (4-7 days)
   - Split `generate_report` into step-level generator modules with typed contracts.
   - Unify OpenAI call path to remove duplicated request/cost plumbing.
   - Extract reusable WordPress term ensure helper.
   - Extract shared metadata row parser for report store.
5. P2 cleanup/redundancy (1-2 days)
   - Remove or fully implement `debug_candidate_gallery`.
   - Remove legacy `analysis_compare` surface or implement real compare mode.
   - Normalize cache-key strategy across orchestrators.
6. Validation gate
   - Keep `pytest` green.
   - Add regression tests for extraction fallback and metadata parsing helpers.
   - Add benchmark checks for ingest throughput and cost-ledger growth.

## Test Suite Integrity Backlog (still open)

Findings to fix:

1. Retry behavior test is weak.
   - `tests/test_orchestrator_retry.py` asserts final error but does not assert attempt count/backoff behavior.
2. Parallel ingest test does not execute real parallel work.
   - `tests/test_ingest_parallel.py` uses a synchronous dummy executor.
3. Vector pipeline test gathers `vector_calls` but does not assert sequence/arguments.
   - `tests/test_vector_pipeline_wiring.py` appends call trace but does not validate expected order.
4. Over-mocking in orchestrator wiring tests reduces regression detection.
   - `tests/test_vector_pipeline_wiring.py`, `tests/test_publish_orchestrator.py`, and `tests/test_ingest_parallel.py` stub most collaborators.
5. Unsafe root smoke script remains.
   - `test_openai.py` prints API key prefix and performs a live API call at module execution.
6. UI navigation test is brittle.
   - `tests/test_streamlit_navigation.py` hardcodes full nav list order/text.

Remediation plan:

1. Strengthen retry verification.
   - Assert retry call count and `sleep` backoff progression in `tests/test_orchestrator_retry.py`.
2. Add one real-concurrency ingest test.
   - Keep deterministic unit test plus integration-style test using real `ThreadPoolExecutor`.
3. Enforce vector pipeline call contract.
   - Assert exact `vector_calls` sequence and key request fields in `tests/test_vector_pipeline_wiring.py`.
4. Reduce over-mocking with service-level integration fixtures.
   - Use temp-dir + sqlite fixtures, mock only true external boundaries.
5. Convert `test_openai.py` to explicit opt-in integration smoke test.
   - Move under `tests/integration/` or `scripts/`, add marker/guard, and remove key-prefix output.
6. Relax brittle UI snapshot checks.
   - Assert required sections/invariants instead of full ordered equality when ordering is not business-critical.
