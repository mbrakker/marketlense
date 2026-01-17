# TODO

1. Upgrade validator to perform semantic comparisons (reduce word-by-word false positives).
   - Current checks in `src/generators/validation_generator.py` rely on substring/regex matching (`_metric_value_supported`, `_contains_token`, `_validate_quotes`) and miss paraphrases/stem variants. Add semantic comparison (embeddings or LLM re-check) against evidence snippets to cut false negatives/positives while keeping schema validation intact.
2. Upgrade all prompts.
   - Prompt namespaces live under `src/prompts/**` (report_generation, report_vs/{doc_map,evidence_packs,artifacts,validate}, rank_candidates). Refresh wording, safety, and output formats; ensure variables match renderer usage in `prompt_service` and bump schema/version hashes for logging.
3. Parallelize report processing.
   - `run_ingest` in `src/orchestrators/ingest_orchestrator.py` processes PDFs serially and blocks on OpenAI calls. Add bounded concurrency per file while keeping lock semantics, and preserve cost ledger/state-db writes without races.
4. Consolidate services to match the service-consolidation rule.
   - Merge PDF-related services into a single `pdf_service.py` and refactor callers; eliminate thin wrapper service shards for any single external system.
5. [DONE] Add categories/tags to vector store records.
   - Vector store metadata is empty/default; no taxonomy or tags from `ReportPayload`/category mappings are propagated. Include categories/regions/time_period as metadata on create/attach so queries can filter and deletion/reuse works by tag.
6. Create a GUI.
   - Only `src/cli.py` exists. Provide a minimal web/desktop UI to trigger ingest/publish, view progress logs, inspect artifacts, cost tables, and vector store status.
7. Add vector store deletion support.
    - No delete API in `vector_store_service`; flag `vector_store_keep` is unused for cleanup. Add delete/prune operations (vector store + files) and orchestrator hooks to avoid orphaned stores.
8. Define and enforce cost limits.
    - Costs are tracked (`cost_ledger_path`, `cost_daily_path`, pricing in `app.yaml`) but not enforced. Add config thresholds (per-run/day) and guardrails in orchestrators before OpenAI calls, with blocking/warning behavior and logging.
9. Refine HTML and deduplicate repeated blocks.
    - `templates/report.html.j2` contains repeated preview/figure handling and inline styling. Extract reusable blocks/macros, de-duplicate preview/gallery logic, and ensure consistent metadata rendering to reduce drift.
10. Refine figure candidates and ranker to avoid low-data images.
    - Current figure selection relies on extracted candidates and ranking (see `figure_service`, `rank_service`, and `extract_service` plus cropping). Add an image analysis step (OCR/content density/heuristics) to filter low-text/low-chart pages, improve table/chart detection and cropping, and feed richer features into the ranker to reduce weak visuals.
11. Add infographics creator for HTML design and LinkedIn posts.
    - Beyond text rendering, there is no infographic generation pipeline. Add a generator/service to produce simple infographics/hero visuals for HTML and LinkedIn artifacts, wired into rendering and artifact generation flows.
12. Support multiple prompts per process for variations/expert roles.
    - Today each step uses a single prompt set per namespace. Add a mechanism to run multiple prompt variants per step (e.g., different expert personas or stylistic variants), collect outputs, and select/ensemble or expose them, while keeping prompt logging/versioning intact.

# Detailed Proposals

## 1. Upgrade validator to perform semantic comparisons
- **Context**: Validation in `src/generators/validation_generator.py` relies on exact substring or regex matching in `_metric_value_supported`, `_contains_token`, and `_validate_quotes`, which can miss paraphrases or stem variants.
- **Proposal**:
  - Add a semantic validation pass after `_collect_evidence_texts` that compares insight metrics and quotes against evidence snippets using embeddings or a lightweight LLM re-check.
  - Keep schema validation (`validate_schema`) unchanged; new checks should only produce `ValidationIssue` entries.
  - Wire model choice through `openai_service` with explicit logging of prompts, model, and evidence hashes.
- **Acceptance**:
  - Paraphrased metric values and quotes are flagged correctly with fewer false positives.
  - Validation report includes both semantic and exact-match findings with clear severity.

## 2. Upgrade all prompts
- **Context**: Prompt namespaces live under `src/prompts/**` and are loaded via `prompt_service` contracts and `PromptLoadRequest`.
- **Proposal**:
  - Audit every namespace (report_generation, report_vs/{doc_map,evidence_packs,artifacts,validate}, rank_candidates) for clarity, safety, and schema alignment.
  - Update prompt variables to match renderer usage (e.g., `PromptRenderRequest` variable names in generators).
  - Bump prompt schema/version hashes and ensure logging is updated with new hashes.
- **Acceptance**:
  - All prompts render without missing variables.
  - Updated prompt hashes appear in generator logs.

## 3. Parallelize report processing
- **Context**: `run_ingest` in `src/orchestrators/ingest_orchestrator.py` iterates PDFs sequentially and blocks on network/model calls.
- **Proposal**:
  - Add bounded concurrency (thread pool or asyncio) per file with a configurable limit in `IngestSettings`.
  - Preserve lock semantics and state DB writes, using per-file `RunContext` and serialized cost ledger updates.
  - Ensure retries still use `_run_step_with_retry` or a concurrency-safe equivalent.
- **Acceptance**:
  - Multiple PDFs process concurrently without double-processing or lock conflicts.
  - Cost ledger and state DB are consistent after parallel runs.

## 4. Consolidate services to match the service-consolidation rule
- **Context**: PDF processing is split across `pdf_utils_service`, `pdf_text_service`, `pdf_context_service`, `pdf_contents_service`, and `extract_service` while sharing the same external PDF libraries. Thin wrapper service shards for a single external system violate the rule.
- **Proposal**:
  - Consolidate all PDF I/O into a single PDF service module (e.g., `pdf_service`).
  - Move shared constants and path handling to that module; refactor callers in generators/orchestrators to use the consolidated API.
  - Eliminate thin wrapper services for any single external system (OpenAI/vector store/WordPress).
  - Ensure logs remain structured with `role="service"` and consistent `module` names.
- **Acceptance**:
  - Only one service module handles each external system.
  - All PDF-related calls originate from the consolidated service API.

## 5. Add categories/tags to vector store records
- **Status**: Completed (taxonomy metadata persists to vector store and report outputs).
- **Context**: Vector store metadata does not include report taxonomy, so filtering and cleanup cannot use categories.
- **Proposal**:
  - Add metadata fields (`categories`, `regions`, `time_period`) derived from `ReportPayload` and category mapping outputs.
  - Pass metadata through `vector_store_service` creation/attachment requests.
  - Ensure metadata is logged and kept in sync with state DB records.
- **Acceptance**:
  - Vector store records include taxonomy metadata and are queryable by tag.

## 6. Create a GUI
- **Context**: Only `src/cli.py` exists for interaction; no UI is available.
- **Proposal**:
  - Implement a minimal web UI (FastAPI + simple frontend or Streamlit) under `src/gui` or `src/orchestrators` with a dedicated service.
  - Include controls to trigger ingest/publish, view progress logs, and inspect artifacts/cost tables/vector store status.
  - Keep UI as a separate entrypoint to preserve CLI behavior.
- **Acceptance**:
  - UI can launch ingest/publish and show task status for a run.
  - Artifacts and cost tables are browsable from the UI.

## 7. Add vector store deletion support
- **Context**: No delete/prune API exists in `vector_store_service`; `vector_store_keep` is unused for cleanup.
- **Proposal**:
  - Add delete operations in `vector_store_service` and wire them into orchestrators when `vector_store_keep` is false.
  - Ensure deletion covers vector store assets and related files.
  - Log deletion decisions with run/task/span IDs.
- **Acceptance**:
  - Orphaned vector stores are cleaned up when configured.
  - Logs confirm deletion operations with IDs.

## 8. Define and enforce cost limits
- **Context**: Costs are tracked in `cost_ledger_path`/`cost_daily_path` but there are no guardrails.
- **Proposal**:
  - Add config thresholds in `app.yaml` (per-run and per-day) and surface them in `AppSettings`.
  - Add orchestrator checks before OpenAI calls to block or warn based on thresholds.
  - Log decisions and include the threshold values in structured logs.
- **Acceptance**:
  - Runs stop or warn when crossing configured cost limits.
  - Logs show thresholds and current spend when a block occurs.

## 9. Refine HTML and deduplicate repeated blocks
- **Context**: `templates/report.html.j2` has repeated preview/figure handling and inline styling.
- **Proposal**:
  - Extract Jinja macros/partials for repeated preview/figure blocks.
  - Normalize metadata rendering and shared styles to reduce drift.
  - Add a small fixture to confirm the output structure remains stable.
- **Acceptance**:
  - HTML template no longer duplicates preview/gallery logic.
  - Metadata block renders consistently across sections.

## 10. Refine figure candidates and ranker to avoid low-data images
- **Context**: Figure selection relies on `figure_service`, `rank_service`, and `extract_service`, but low-signal images slip through.
- **Proposal**:
  - Add an image quality filter (OCR density, chart/table heuristics, minimum text coverage).
  - Extend candidate metadata with quality scores and feed them into ranking inputs.
  - Improve cropping for chart/table boundaries before ranking.
- **Acceptance**:
  - Candidate set excludes low-content images and prioritizes meaningful charts.
  - Ranking inputs include explicit quality features.

## 11. Add infographics creator for HTML design and LinkedIn posts
- **Context**: No pipeline exists for generating infographic assets beyond text artifacts.
- **Proposal**:
  - Add a generator/service pair to create infographic assets (SVG/PNG) from report highlights.
  - Wire into HTML rendering and LinkedIn artifact generation flows.
  - Store artifacts alongside existing outputs with metadata for reuse.
- **Acceptance**:
  - Infographic assets are created and referenced in HTML/LinkedIn outputs.
  - Artifacts are logged and stored with report metadata.

## 12. Support multiple prompts per process for variations/expert roles
- **Context**: Each step uses one prompt namespace; no multi-prompt selection exists.
- **Proposal**:
  - Add configuration for multiple prompt variants per namespace.
  - Generate outputs for each variant, then select/ensemble using a scoring heuristic or validation step.
  - Preserve prompt logging/versioning for each variant.
- **Acceptance**:
  - Multiple prompt variants can be run per step and results are captured.
  - Selection logic is logged with variant identifiers.
