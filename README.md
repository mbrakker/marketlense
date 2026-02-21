# Market Lense

Enterprise PDF ingestion and analysis pipeline that converts Google Drive reports into structured HTML digests using an LLM and extraction heuristics.

---

## Executive Summary

Market Lense ingests PDFs from a configured Google Drive folder, extracts text and structured visual candidates (tables/charts), calls an LLM for a strict JSON analysis, ranks and crops key visuals, renders a compact HTML digest, and can publish the digest to WordPress. The system is organized around a strict architecture with contracts, services, generators, and orchestrators to ensure reliability, observability, and testability.

Key traits:

- Contract-first data model for all external I/O boundaries.
- Service isolation for all external systems and file I/O.
- Generator logic that composes services into domain outputs.
- Orchestrator that controls sequencing, retries, and state (including publishing).
- Structured logging with run/task/span identifiers.
- Built-in validation: semantic checks plus LLM grounding with persisted reports and publish-time policy controls.
- Text extractability gate: before analysis, the pipeline samples deterministic pages and aborts early with `pdf_text_unextractable` when none contain extractable text.
- DocMap validation gate: if the doc_map evidence pack is empty (no sections/title/doc_id/summary), processing halts for that PDF; the orchestrator logs a detailed summary and stores it in the state DB.
- Cached execution: PDF info/contents/text extraction are cached by md5, and analysis outputs (evidence packs, artifacts, validation, HTML, crop-refine decisions) are cached by md5 + prompt/template hashes to skip redundant work.
- Batched state prefilter: Drive-list skip checks for `(file_id, md5)` are grouped into batch SQLite queries to reduce per-file DB round trips; per-file state checks run only when the final resolved md5 differs from the Drive md5.
- Low-text resilience: text density heuristics detect PDFs with little/no extractable text and emit explicit "not available from text" artifacts + HTML notices instead of blank sections.
- HTML digest quality: rendered HTML now uses semantic sections (`header/main/section`), premium split hero layout, sticky glass navigation with scrollspy + reading progress, reveal animations (with reduced-motion fallback), signal-style insight cards, editorial quote cards, and long-text chunking for generated prose.
- Figure UX: rendered digests now include a template-native figure carousel with prev/next controls, keyboard and swipe support, thumbnail rail, slide counter, and fullscreen lightbox.
- OpenAI image-call compatibility: crop-refine image requests to the Responses API automatically retry without unsupported parameters (e.g., `temperature`/`seed`) when a model rejects them, preserving full crop-refine functionality.
- Figure quality gate: candidate visuals now pass deterministic prefilters plus LLM thresholds (overall + quality + insight + data), kind-split ranking (tables and charts ranked independently), adaptive GPT crop refinement, and strict final cropping. Per-kind caps now ensure balanced outputs (up to `rank.selected_max` tables and `rank.selected_max` charts). If none pass, the figure section is hidden.
- Crop-refine edge guard: final LLM-refined bboxes now apply conservative padding plus text-edge correction so partial cut letters/lines at crop borders are automatically expanded (or trimmed if only tiny accidental overlap), reducing visibly clipped figure outputs.
- Strict crop output safety: final crop filenames are now candidate-ID based, preventing table/chart overwrite collisions when strict table and strict chart crops are written to the same `slices/` directory.
- Strict crop spillover control: strict crop modes additionally tighten bottom-edge partial text spillover so body paragraph fragments below a figure/table are trimmed while preserving the main visual content.
- SEO-ready HTML: rendered digests include shortened `<title>` handling, `meta description`, Open Graph/Twitter cards, optional canonical URL, JSON-LD (`Article`) structured data, explicit image `width`/`height` attributes to reduce CLS, and automatic `noindex,nofollow` on low-content fallback pages.
- Vector store is the default and only analysis path; legacy local_text prompt stuffing has been removed now that vector_store is validated.
- Taxonomy extraction maps tags to categories (vector retrieval on cache miss, cached taxonomy reuse on eligible reruns); tags and categories are rendered in the HTML metadata block.
- HTML metadata chips normalize slug-style taxonomy values into readable labels (e.g., `ai-in-retail` -> `AI in Retail`) with acronym preservation loaded from `src/config/html-tag-acronyms.yaml`.
- Publish file ID resolution is DB-first: publish/publish-queue resolve `file_id` from reports metadata (`html_path -> file_id`) and fall back to HTML parsing only when mapping is unavailable.

---

## Architecture Overview

The codebase follows a strict layered architecture under `src/`:

```text
src/
  contracts/         # Dataclass contracts for inputs/outputs
  services/          # External I/O services (Drive, OpenAI, files, etc.)
  generators/        # Domain logic (report generation)
  orchestrators/     # Control plane / pipelines
  utils/             # Pure helpers (no I/O)
  prompts/           # LLM prompt templates (YAML)
```

### Roles

- **Contracts**: Define schema and shape of inputs/outputs at service boundaries. No logic.
- **Services**: Only I/O. Talk to external APIs, filesystem, databases, or system resources. No business logic.
- **Schema validation**: JSON schema loading/validation is treated as I/O and lives in `src/services/schema_validator_service.py`.
- **Generators**: Compose services and enforce domain rules (e.g., which charts are selected, how outputs are structured).
- **Orchestrators**: Define when and in what order things happen, including retries and state transitions.
- **Utils**: Pure deterministic functions (no I/O, no global state).

Current control-plane modules in `src/orchestrators/` include:

- `ingest_orchestrator.py`: batch-level ingest control (locking, DB access checks, worker fanout, cursor updates).
- `ingest_file_orchestrator.py`: single-file ingest execution (cache/download/EOF checks, report pipeline call, state writes).
- `report_pipeline_orchestrator.py`: report-generation pipeline boundary with retry-aware control around report generation.
- `publish_orchestrator.py`: publish workflow and publish-state transitions.
- `publish_queue_orchestrator.py`: publish queue snapshot assembly for UI/ops surfaces.
- `cost_reporting_orchestrator.py`: filtered cost report + rollup orchestration.
- `ops_dashboard_orchestrator.py`: dashboard snapshot aggregation (reports/state/lock/storage).
- `candidate_extraction_orchestrator.py`, `cover_image_orchestrator.py`, `recategorize_orchestrator.py`, `wp_category_update_orchestrator.py`: feature-specific workflows.

---

## Configuration (YAML + .env)

Primary config: `src/config/app.yaml`. Missing values can be provided via `.env` (loaded by `config_service`). Secrets must come from environment variables.

For dev wiring, use `src.services.config_service.build_ingest_settings` with `IngestSettingsBuildRequest` to adapt `AppSettings` into `IngestSettings` without hand-copying fields; new config keys are picked up automatically.

Key fields and env overrides:

- Paths: `paths.output_dir` (`OUTPUT_DIR`, default `./out`), `paths.cache_dir` (`CACHE_DIR`, default `./cache`), `paths.state_db` (`STATE_DB`), `paths.reports_db` (`REPORTS_DB`), `paths.category_mappings` (defaults to `src/config/category-mappings.yaml`), `paths.html_tag_acronyms` (defaults to `src/config/html-tag-acronyms.yaml`).
- Ingest: `ingest.google_sa_path` (`GOOGLE_SERVICE_ACCOUNT_JSON`), `ingest.gdrive_folder_id` (`GDRIVE_FOLDER_ID`), `ingest.openai_model` (`OPENAI_MODEL`), `ingest.batch_limit` (`BATCH_LIMIT`, default 20), `ingest.worker_limit` (`INGEST_WORKER_LIMIT`, default 2), `ingest.report_worker_limit` (`INGEST_REPORT_WORKER_LIMIT`, default 2), `ingest.temperature` (`TEMPERATURE`, default 1.0), `ingest.timeout_seconds` (`OPENAI_TIMEOUT_SECONDS`, default 600), `ingest.lock_ttl_seconds` (`INGEST_LOCK_TTL_SECONDS`, default 7200), `ingest.contents_page.*` (keywords, max_pages, min_headings, render_dpi, preview_enabled), `ingest.evidence_packs.parallel_workers` (`EVIDENCE_PACK_PARALLEL_WORKERS`, default 3), `ingest.evidence_packs.global_max_in_flight` (`EVIDENCE_PACK_GLOBAL_MAX_IN_FLIGHT`, default 2), `ingest.evidence_packs.global_min_interval_ms` (`EVIDENCE_PACK_GLOBAL_MIN_INTERVAL_MS`, default 250), `ingest.evidence_packs.doc_map_max_attempts` (`EVIDENCE_PACK_DOC_MAP_MAX_ATTEMPTS`, default 3), `ingest.evidence_packs.doc_map_retry_delay_ms` (`EVIDENCE_PACK_DOC_MAP_RETRY_DELAY_MS`, default 500), `ingest.artifacts.parallel_workers` (`ARTIFACT_PARALLEL_WORKERS`, default 4), `ingest.artifacts.global_max_in_flight` (`ARTIFACT_GLOBAL_MAX_IN_FLIGHT`, default 2), `ingest.artifacts.global_min_interval_ms` (`ARTIFACT_GLOBAL_MIN_INTERVAL_MS`, default 250).
- Ranking/crop refinement: `rank.max_candidates`, `rank.selected_max` (default `5`), `rank.min_overall_score`, `rank.min_quality_score`, `rank.min_insight_score`, `rank.min_data_score`, `rank.crop_refine_enabled`, `rank.crop_refine_mode` (`adaptive|always|off`), `rank.crop_refine_page_dpi`, `rank.crop_refine_temperature`, `rank.crop_refine_timeout_seconds` (defaults to `rank.timeout_seconds` when omitted).
- Drive listing: `ingest.drive.supports_all_drives`, `ingest.drive.include_items_from_all_drives` (shared drive flags), `ingest.drive.drive_id` (shared drive scope), and `ingest.drive.list_mode` (`full` vs `metadata` to omit names until needed).
- PDF text extraction: `ingest.pdf_text.max_pages` and `ingest.pdf_text.max_chars` cap how much text is sampled per PDF; `ingest.pdf_text.min_density` (default `250` chars/page) triggers "not available from text" fallbacks when extraction is sparse; `ingest.pdf_text.sample_pages` (default `3`) controls the deterministic sample used to validate extractability before analysis.
- Model overrides: `openai_models` maps prompt namespaces (or prefixes) to model IDs. Longest-prefix match wins. Falls back to `ingest.openai_model` for most prompts and to `rank.model` for `rank_candidates` unless an override is provided.
- HTML rendering labels: `paths.html_tag_acronyms` points to a YAML file that defines `html_tag_acronyms` tokens preserved in uppercase when slug labels are humanized.

Per-step model selection (new):

- Set `openai_models` entries to pin specific prompt calls to specific models (e.g., `report_vs/artifacts/summary`, `report_vs/evidence_packs/findings`, `report_vs/validate/grounding`, `rank_candidates`, `rank_candidates/crop_refine`).
- Prefix keys apply to all nested namespaces unless a more specific key exists (e.g., `report_vs/evidence_packs` covers all evidence packs).
- Vector store: `analysis.vector_store_keep` (`VECTOR_STORE_KEEP`, default `true`) controls whether to retain caches between runs (including evidence pack reuse). Analysis always uses the vector_store path; compare toggles are legacy/ignored. Evidence/validation JSONs are written only to `out/<report-slug>/report_analysis/`.
- Artifact retrieval mode: `analysis.artifacts_use_vector_store` (`ARTIFACTS_USE_VECTOR_STORE`, default `false`) controls whether artifact model calls use vector-store retrieval. Default is closed-context JSON chat; set to `true` to restore legacy vector retrieval behavior.
- Validation grounding retrieval mode: `analysis.validation_grounding_use_vector_store` (`VALIDATION_GROUNDING_USE_VECTOR_STORE`, default `false`) controls whether grounding checks use vector-store retrieval. Default is closed-context JSON chat; set to `true` to restore legacy vector retrieval behavior.
- Cost tracking: `analysis.cost_ledger_path` (`COST_LEDGER_PATH`, default `./out/cost-ledger.jsonl`), `cost.daily_path` (default `./out/cost-daily.json`), `cost.pricing` (per-model pricing map used by `utils.costing`).
- Validation: `ingest.validation.data_gap_policy` (default `warn`) controls whether missing evidence/text gaps downgrade errors to warnings; `publish.validation.policy` (`PUBLISH_VALIDATION_POLICY`, default `block`; set to `warn` to allow publish with issues).
- Taxonomy extraction: set `openai_models.report_vs/taxonomy` to override the tag/region/time period extractor.
- Cover images: `paths.cover_styles` points to `src/config/cover-styles.yaml` (defaults to that path). Fonts are local files; the default config uses `templates/GOTHICB.TTF` for both regular/bold. Ensure the font file exists on the host; otherwise cover rendering will fail with `cover_font_invalid`. Background image is optional; leave blank for a solid background.

Secrets (env only):

- `OPENAI_API_KEY` (required)
- `WP_APP_PASSWORD` or `WP_BEARER_TOKEN` (publishing)
- Optional provider keys (e.g., `MINERU_API_KEY`) if used.

Prompt locations:

- Vector store evidence packs: `src/prompts/report_vs/**` (`doc_map/`, `evidence_packs/{scope,methods,findings,limitations,quote_candidates}/`)
- Artifact generation: `src/prompts/report_vs/artifacts/**` (toc, summary, insights candidates/final, quotes, expert comment, LinkedIn post)
- Taxonomy extraction: `src/prompts/report_vs/taxonomy/`

Prompts are YAML (system/user), hashed and logged by `src/services/prompt_service.py`.

---

## End-to-End Flow (Ingest)

1. **Configuration load**
   - `src/services/config_service.py` loads YAML from `src/config/app.yaml` and ensures required paths exist.
   - Missing values fall back to `.env` (for example Drive folder ID, service account path, and WordPress site/user).
   - Secrets (OpenAI and WordPress tokens) come from `.env`.
   - Produces `AppSettings` contract.

2. **Pipeline orchestration**
   - Entry point: `src/cli.py`.
   - `src/orchestrators/ingest_orchestrator.py` coordinates run-level ingest flow (locks, DB checks, list/fanout, cursor transitions).
   - `src/orchestrators/ingest_file_orchestrator.py` handles per-file execution inside the ingest worker pool.
   - Per-file cache eligibility is logged via `report_cache_prereq` (`md5_present`, `vector_store_keep`, `eligible`), with an explicit event when `vector_store_keep=false` disables analysis-cache reuse.
   - Before doing any work, ingest probes `state_db` and `reports_db` for write access (SQLite `BEGIN IMMEDIATE`). If either DB is locked, the run exits early with `db_locked` to avoid partial outputs.
   - Per-file processing runs in a bounded worker pool controlled by `ingest.worker_limit` (default `2`).

3. **Drive discovery**
   - `src/services/drive_service.py` lists PDF files in the target Drive folder.
   - Produces `DriveFile` contracts.
   - Supports shared-drive scoping (`drive_id` + `corpora=drive`) and configurable `supportsAllDrives`/`includeItemsFromAllDrives`.
   - Metadata-only listing (`ingest.drive.list_mode=metadata`) skips names until a file is actually processed.
   - State skip prefiltering batches Drive metadata checks (`state_service.already_processed_batch`) for files that already include `md5Checksum`, reducing SQLite round trips during listing.
   - If an ingest cursor exists, listings filter on `modifiedTime > last_successful_ingest_utc` for full runs; limited runs ignore the cursor and instead scan newest-first until they find unprocessed PDFs.

4. **Download + integrity check**
   - Cache paths are keyed by `file_id` (not file name) under `cache_dir`.
   - `file_service.file_stat(...)` reads exists/size/mtime and consults a `.md5.json` sidecar to avoid re-hashing cached files.
   - Before report generation, if md5 is still missing, ingest computes md5 from the cached PDF and writes/refreshes the md5 sidecar so md5-gated caches remain eligible.
   - Cache hits skip EOF checks; if Drive provides `md5Checksum`, it is compared against cached md5.
   - Drive API clients are cached per thread to keep googleapiclient/httplib2 usage thread-safe when `ingest.worker_limit > 1`.
   - `drive_service.download_pdf_to_path(...)` streams PDF bytes directly to disk while computing md5.
   - `src/services/pdf_service.py` checks for EOF marker using only tail bytes and redownloads once if missing.

5. **State management**
   - `src/services/state_service.py` maintains a SQLite store of processed file IDs and hashes.
   - If Drive provides `md5Checksum`, already-processed files are skipped before any download or hashing.
   - A separate ingest cursor (`last_successful_ingest_utc`) is recorded on successful runs and used to filter subsequent Drive listings.

6. **Report generation (per file)**
   - `src/orchestrators/report_pipeline_orchestrator.py` controls report-generation retries and delegates domain generation to `src/generators/report_generator.py`.
   - `src/generators/report_generator.py` runs the core domain pipeline:
     - Optional within-file parallelism uses `ingest.report_worker_limit` to overlap PDF info/contents/text extraction and visual prep when enabled (default `2`).
     - **PDF info**: `pdf_service.extract_pdf_info` captures page count and sanitized PDF metadata for persistence (cached by md5 under `cache_dir/pdf_cache/`).
     - **PDF context**: `pdf_service.build_pdf_context` opens PyMuPDF and pypdf handles once; downstream services reuse them and fall back to local opens if unavailable.
    - **Contents/index detection**: scans the first pages for a contents/index section, records the page number for DB/runtime routing, and can render an internal preview asset for diagnostics (detection cached by md5 + settings).
     - **Text extraction**: `pdf_service.extract_pdf_text` extracts text from the first N pages (reusing the shared context when present) and computes text density (cached by md5 + extraction settings); if density falls below `ingest.pdf_text.min_density`, downstream artifacts short-circuit to explicit “not available from text” placeholders with HTML notices.
     - **Text extractability check**: deterministically samples `ingest.pdf_text.sample_pages` pages (seeded by file id + hash) via `pdf_service.sample_pdf_text`; if none contain extractable text, the run aborts early with `pdf_text_unextractable` before any vector store or LLM work.
     - **LLM analysis**:
       - `vector_store` mode (only path): Ensures a vector store exists (create -> upload PDF -> attach) and starts provider-side indexing first.
       - While indexing runs, the generator continues PDF-only work (figure/candidate extraction, ranking, preview).
       - It waits for indexing only right before vector-dependent stages (taxonomy/evidence/artifacts) via `vector_store_service.wait_until_indexed`.
       - After indexing is ready, taxonomy/category resolution and evidence-pack generation run concurrently when `ingest.report_worker_limit > 1` (serial when `= 1`).
      - Evidence packs are generated via `src/generators/evidence_pack_generator.py` (doc_map, scope, methods, findings, limitations, quote_candidates), where `doc_map` runs first as a hard gate and the remaining packs run in parallel (`ingest.evidence_packs.parallel_workers`). Global evidence-pack rate limiting is applied at the orchestrator boundary (`src/orchestrators/report_pipeline_orchestrator.py`) using `ingest.evidence_packs.global_max_in_flight` + `ingest.evidence_packs.global_min_interval_ms`.
      - Artifacts are generated via `src/generators/artifact_generator.py` using a dependency-aware parallel DAG: `toc` + `summary` + `insights_candidates` + `quotes` in parallel, then `insights_final`, then `expert_comment` + `linkedin_post` in parallel. Independent steps use `ingest.artifacts.parallel_workers`. Global artifact rate limiting is applied at the orchestrator boundary (`src/orchestrators/report_pipeline_orchestrator.py`) using `ingest.artifacts.global_max_in_flight` + `ingest.artifacts.global_min_interval_ms`. By default these artifact model calls run closed-context (`chat_json`); vector retrieval is opt-in via `analysis.artifacts_use_vector_store`.
       - Packs are stored under `out/<report-slug>/report_analysis/*.json` and persisted in the metadata DB (`reports` table columns `vector_store_id`, `evidence_packs_json`; state DB stores `vector_store_status`, `indexed_at_utc`, `openai_file_id`, `last_error`).
       - Orchestrator logs `VECTOR_STORE_CREATED`, `VECTOR_STORE_INDEXED`, `EVIDENCE_READY`.
       - Evidence packs, artifacts, validation reports, and HTML are cached by md5 + prompt/template hashes to skip repeat LLM and rendering work when inputs are unchanged. Artifact and validation caches are retrieval-mode aware, so `chat_json` and vector-retrieval outputs are isolated.
      - DocMap retries/fallback: `doc_map` generation performs JSON-from-text fallback (including fenced blocks/extracted object) in the generator, while retry/backoff decisions are owned by `src/orchestrators/report_pipeline_orchestrator.py`. Retry attempts are bounded by `ingest.evidence_packs.doc_map_max_attempts` and use jittered backoff.
       - DocMap validation: if the `doc_map` pack remains empty after retries/fallback (no sections/title/doc_id/summary), the report is halted for that PDF and the error is logged/recorded with a summary persisted to the state DB.
       - DocMap normalization: responses wrapped under `docmap`/`doc_map`/`docMap` are unwrapped; `document.title`/`document.publisher` + `structure` are normalized into canonical top-level `title`/`publisher`/`sections`; missing `doc_id` is filled with the report ID; section `id`s (and `pages` from `page`) are auto-generated/coerced before schema validation.
       - Reports DB metadata sourcing: `reports.title` is written from `doc_map.title` (fallback to file-derived title only when doc_map title is empty), `reports.publisher` is sourced from `doc_map.publisher` or `doc_map.organization`, `reports.file_name` stores the source PDF filename, and `reports.time_period` is normalized to canonical year / quarter-year / month-year forms (including ranges like `2025-2026`, `Q1-Q3 2026`, `June-November 2023`). During HTML render, `title`/`publisher`/`time_period` are read from `reports` DB metadata only.
       - Taxonomy extraction: `src/generators/taxonomy_generator.py` uses `src/prompts/report_vs/taxonomy/` to extract tags/regions/time_period from the vector store; tags map to categories and persist to the reports DB and HTML. Taxonomy output is cached at `out/<report-slug>/report_analysis/taxonomy.json` when `md5` is available and `analysis.vector_store_keep=true`.
     - **Validation**: `src/generators/validation_generator.py` now does a two-pass check:
       - Canonical normalization: shared `normalize_text()` / `normalize_for_lookup()` (`src/utils/text_normalization.py`) are used for quote matching, numeric parsing, and evidence retrieval indexing.
       - Generic quantity grounding: `src/utils/quantity.py` parses comparator + value + unit family + magnitude + timeframe across `%`, `pp`, currencies (`$ € £ ¥`, `k/m/b/bn/mn`), ratios (`1 in 10`, `x`), ranges, rates (`YoY/MoM/CAGR`), counts (`N=`), and date/quarter tokens.
       - Canonical quantity matching: validator accepts equivalent numeric surface forms (e.g. `37.0` / `37%` / `0.37` in percent context, `$3M` / `3 million USD`, `>10` with explicit USD-billions context, range overlap, approx/comparator compatibility, rounding tolerance by unit family).
       - Figure/new-number checks compare numeric values in a unit-agnostic way (unit labels are ignored for those checks), reducing false fails from `%`/currency/count unit wording differences.
       - Section policy: `strict` (`insights`, `quotes`, claims/metrics), `soft` (`expert_comment`, `linkedin_post`), `mixed` (`summary`). Soft sections allow interpretation/recommendations; unsupported quantities are warning-by-default unless clearly metric-attributed.
       - Evidence retrieval: validation builds overlapping evidence windows (token windows with stride), scores via hybrid lexical overlap + BM25-like term hits + quantity boost, and expands with neighbor windows to reduce page-break false negatives. Cached PDF text (`cache/pdf_cache/<md5>/text_*.json`) is included in retrieval windows when available.
       - Quote validation: verbatim quotes require normalized near-verbatim support (substring/lexical threshold). Paraphrase-labeled quotes are allowed with semantic support.
       - Semantic: LLM re-check via `src/prompts/report_vs/validate/semantic/{system,user}.yaml` (model resolved via `openai_models` longest-prefix match) that scores metric/quote support against evidence snippets and logs prompt hashes + evidence/metric/quote SHA-256. Semantic “supported” adds `info` issues; “unsupported” raises `warning|error`.
       - Grounding rubric (`src/prompts/report_vs/validate/grounding/{system,user}.yaml`): validator distinguishes `factual_claim`, `analyst_interpretation`, and `prescriptive_recommendation`. Hard fails are reserved for hallucinated entities/events, unsupported metrics, misattributed quotes, and “the report said/instructed X” misattributions; retrieval failures are tracked separately. Grounding defaults to closed-context (`chat_json`) and can be switched back to vector retrieval via `analysis.validation_grounding_use_vector_store`.
       - Parallel execution: when `ingest.report_worker_limit > 1`, semantic, grounding, and new-number checks run concurrently; metric/quote exact checks run immediately after semantic completes. Issue merge order remains deterministic as `semantic -> metrics -> quotes -> new_numbers -> grounding` to prevent behavioral drift.
       - Results persist to `out/<report-slug>/report_analysis/validation*.json` and flow into HTML and publish policy decisions. When `ingest.validation.data_gap_policy` is `warn`, missing evidence/text downgrades to warnings. Schema validation is performed via `schema_validator_service`.
     - **Normalization**: `normalize_generator` enforces strict schema and list sizing.
     - **Categorization**: taxonomy tags are scored against `src/config/category-mappings.yaml`; top 3 categories are stored and rendered, and unmapped tags are appended under `uncategorized` in that YAML.
     - **Figure selection**: `pdf_service.extract_best_figure` selects a representative visual and caption.
    - **Candidate extraction**: `pdf_service.collect_candidates` finds chart/table regions, parallelizes page-level extraction (bounded by `ingest.report_worker_limit`), and excludes the detected contents/index page from candidate output when present.
     - **Candidate prefilter + ranking**: deterministic prefilter removes obvious low/no-data fragments, then `rank_service` scores candidates via LLM (overall + quality + insight + data + keep/reject_reason; model resolves from `openai_models.rank_candidates` if set, else `rank.model`, then `ingest.openai_model`).
     - **Adaptive crop refinement**: ambiguous candidates call `rank_candidates/crop_refine` with page image context; obvious pass/reject candidates skip LLM. Ambiguous page renders are pre-rendered in parallel and ambiguous LLM refinement calls run in bounded parallel mode. Crop refinement now runs in two passes (coarse -> finalize) to improve edge precision and reduce clipped text artifacts.
     - **Strict cropping**: final crops are routed by visual kind (`table_strict` for tables, `chart_strict` for charts) so each class uses tailored border trimming instead of a monolithic crop mode.
    - **Zero-pass behavior**: if no final candidate passes, the HTML figure section is disabled.
     - **Preview rendering**: `pdf_service.render_preview` renders the first page to PNG.
      - **Cover image generation**: `cover_image_generator` resolves style from `cover-styles.yaml` using the report’s first category (falls back to `default` for styling only), while the rendered label text, title, publisher, time period, and region always come from report metadata in the DB. Cover assets are now written into the canonical report folder (`out/<report-slug>/assets/`) with length-bounded, file-id-suffixed filenames via `src/utils/cover_path_utils.py`; Streamlit preview lookup follows the same path logic with legacy-path fallback.
     - **HTML rendering**: `render_service` generates the final HTML digest with premium template UX (split hero, sticky nav + progress, section accents, signal cards, editorial quotes, figure carousel/lightbox), plus SEO metadata (OG/Twitter/canonical/JSON-LD) and explicit image dimensions.
   - If the reports DB already has `html_path` for the same `file_id` + md5 and the HTML exists on disk, the orchestrator skips report generation.

7. **State record**
   - The orchestrator records completion or failure state after each report generation attempt (including `doc_map_empty` and `pdf_text_unextractable` errors). DocMap failures persist a `doc_map_summary_json` payload for debugging.

---

## End-to-End Flow (Publish to WordPress)

1. **Configuration load**
   - `src/services/config_service.py` loads WordPress settings from YAML; secrets from `.env`.
   - Produces `PublishSettings` contract.

2. **Pipeline orchestration**
   - Entry point: `src/cli.py` (`publish-wp`).
   - `src/orchestrators/publish_orchestrator.py` coordinates HTML publishing.

3. **HTML discovery**
   - `src/services/file_service.py` lists generated HTML files in `OUTPUT_DIR`.
   - `file_id` is resolved from reports metadata (`reports.html_path -> reports.file_id`) when available; HTML parsing is used only as fallback.

4. **State checks**
   - `src/services/state_service.py` verifies the report was processed and not already published.

5. **Publishing (per file)**
   - `src/generators/publish_generator.py` uploads report images, swaps image URLs, and creates a WordPress post.
   - `src/services/wordpress_service.py` handles media and post API calls.

6. **State record**
   - Published posts are recorded with post ID and URL for idempotency.
   - Validation policy: `publish.validation.policy` set to `block` skips publish when validation fails/missing; `warn` logs issues but proceeds. Publish outcomes include validation status/issues.

---

## Logging and Observability

Structured logs are emitted by all services and orchestrators using `src/utils/logging.py`.
Redaction covers API keys, bearer tokens, and common PII patterns before log emission.

CLI-provided run contexts flow into the ingest orchestrator so CLI run/task IDs stay consistent across downstream orchestrator/service logs.

Every log event includes:

- `run_id`: pipeline run identifier
- `task_id`: per-file identifier
- `span_id`: per-operation span identifier
- `module`: logger name
- `role`: service / generator / orchestrator
- `event`: logical event name

Examples:

- `openai_analyze_start`
- `openai_prompts_loaded`
- `drive_download_complete`
- `report_generate_complete`

---

## Error Taxonomy and Retries

All external I/O services raise `AppError` with attributes:

- `code`
- `message`
- `cause`
- `retryable`
- `severity`
- `context`

Retry behavior is centralized in `src/orchestrators/retry_orchestrator.py` and reused by ingest, candidate-extraction, publish, and report-pipeline orchestrators: only retryable `AppError` instances are retried, with bounded attempts and linear backoff (`1s`, `2s`, ... by default, plus optional jitter support).

---

## Prompt Management

Prompts are stored in YAML by namespace:

```text
src/prompts/report_vs/doc_map/          # vector_store doc map
src/prompts/report_vs/evidence_packs/   # vector_store packs (scope/methods/findings/limitations/quote_candidates)
src/prompts/report_vs/artifacts/        # artifact sections (toc, summary, insights, quotes, expert comment, LinkedIn)
```

Prompts are rendered with Jinja2 (`{{ variable }}`), loaded and hashed by `src/services/prompt_service.py`, and logged with their SHA256 hashes for reproducibility.

- Prompt caching: prompt sets are cached in-memory per namespace for the duration of a process. `PromptLoadRequest` supports `reload_if_changed` (mtime check) and `force_reload` (bypass cache) when you need to pick up edited prompt files mid-run.

---

## Category mappings

- Source of truth: `src/config/category-mappings.yaml` (versioned by `schema_version`).
- Scoring: each matched tag adds +1 to a category; top 3 categories are assigned to the report, stored in the metadata DB, rendered in HTML metadata, and synced to WordPress posts.
- Taxonomy prompt: allowed tags from the mappings are provided to `src/prompts/report_vs/taxonomy/`; unmapped tags are appended under `uncategorized` for review.
- Maintenance: add categories with `id` (snake_case), `label`, `description`, and a focused `tags` list (lowercase, snake_case). Place new entries at the top to keep recent taxonomies visible.
- Coverage constraints: keep every category populated with more than 10 tags, keep every tag categorized (no orphan tags), and limit any single tag to at most 5 category lists even when copied for high relevance.
- Current taxonomy highlights: `digital_payments`, `retail_logistics`, `consumer_behavior`, `business_performance`, `agentic_commerce`, plus existing advertising, commerce, CTV, social video, and measurement tracks.
- Unmapped handling: uncategorized tags are removed once mapped; if new tags appear, run `python -m src.cli recategorize` to refresh assignments and prune stale uncategorized entries.
- Mapping caching: category mappings are cached in-memory per path with optional `reload_if_changed`/`force_reload` flags on `CategoryMappingLoadRequest`. Uncategorized tag writes are batched in memory and flushed once per run by orchestrators (ingest/recategorize) to reduce YAML churn.

---

## Contracts and Schemas

Key contracts live under `src/contracts/`:

- `config.py`: `AppSettings`
- `drive.py`: Drive file and request/response contracts
- `openai.py`: OpenAI request/response contracts
- `pdf_text.py`: PDF text extraction contracts
- `prompts.py`: Prompt load/render contracts
- `report_models.py`: `ReportPayload`, `Quote`, `Figure`, etc.
- `report_assets.py`: request/response contracts for figure, preview, crop, ranking, etc.
- `publish.py`: publish settings, requests, and outcomes
- `state.py`: state store contracts
- `wordpress.py`: WordPress request/response and auth settings
- `pdf_context.py`: shared PDF context (PyMuPDF + pypdf handles) and build request/response contracts
- `pdf_utils.py`: EOF check and PDF info (page count + metadata) contracts
- `report_store.py`: report metadata upsert/get/list contracts, including page count and flattened PDF metadata
- `validation.py`: validation requests, issues, and reports (persisted per report)

---

## Schemas (JSON)

Location: `src/schemas/`

- `doc_map.schema.json`: required fields for DocMap outputs (id/title/publisher/year/figures, etc.).
- `evidence_pack.schema.json`: permissive; accepts optional/empty `scope`, `methods`, `findings`, `limitations`, and `quote_candidates` with nullable fields and extra properties.
- `artifacts.schema.json`: artifacts/toc/summary/insights/quotes/expert_comment/linkedin payload shape.
- `validation_report.schema.json`: structure for validation results.
- `taxonomy.schema.json`: taxonomy extractor response schema for tags/regions/time_period.
- Union `type` arrays are validated as true unions (for example `["string", "null"]` now accepts either a string or `null` and rejects other types).

Schema validation is performed by `src/services/schema_validator_service.py` and logged per pack.

---

## Testing

Test suites live under `tests/` (unit + contract + integration marker support):

- `test_validation.py`: contract validation helpers
- `test_normalize_service.py`: normalization behavior
- `test_cli.py`: CLI wiring
- `test_orchestrator_retry.py`: retry behavior
- `test_publish_orchestrator.py`: publish orchestration
- `test_html_utils.py`: HTML parsing helpers
- `test_artifact_generator.py`: artifact JSON generation/validation
- `test_render_service_artifacts.py`: HTML sections for artifact rendering
- `contracts/test_contract_roundtrip.py`: dataclass serialization/deserialization round-trip gate for `src/contracts/*`

Install dev/test tooling:

```bash
pip install -r requirements-dev.txt
```

Run tests locally:

```bash
pytest
```

`pytest.ini` sets `pythonpath = .` so `src.*` imports resolve without exporting `PYTHONPATH`.
Default runs exclude `integration`-marked tests (`addopts = -m "not integration"`).

Run the live OpenAI smoke test explicitly (opt-in):

```bash
RUN_OPENAI_SMOKE_TEST=1 OPENAI_API_KEY=... pytest -m integration tests/integration/test_openai_smoke.py
```

CI gates (see `.github/workflows/ci.yml`):

- `python scripts/ci/check_formatting.py` (format gate, `ruff format --check` for CI scripts/contract tests)
- `python scripts/ci/run_type_check.py` (type gate, `mypy` for `src/contracts` + CI scripts)
- `python scripts/ci/check_forbidden_patching.py` (fails on private-helper/dataclass-constructor patching patterns in tests)
- `python -m pytest --cov=src --cov-report=xml --cov-report=term-missing` (default suite excludes integration tests)
- `python scripts/ci/check_coverage.py --coverage-xml coverage.xml` (global + per-critical-package thresholds)
- `python scripts/ci/run_mutation_gate.py` (mutation score gate for one orchestrator + one generator target)

---

## Runtime Requirements

Configuration lives in `src/config/app.yaml` with `.env` fallback for any missing values. Secrets come from environment variables.

- Contents/index detection is configured under `ingest.contents_page` (keywords, max_pages, min_headings, render_dpi).

Required environment variables:

- `OPENAI_API_KEY`
- `WP_APP_PASSWORD` (or `WP_BEARER_TOKEN` if using bearer auth)
- Optional: other provider keys (e.g., `MINERU_API_KEY`), `WP_USERNAME`/`WP_SITE_URL` if not set in YAML.

---

## CLI Usage

Primary entrypoint (defaults to `ingest` if no subcommand):

```bash
python -m src.cli ingest --limit 10
```

Publish generated HTML to WordPress:

```bash
python -m src.cli publish-wp --limit 10
```

Re-score categories for all stored reports (updates DB + uncategorized tags list):

```bash
python -m src.cli recategorize
```

Update WordPress categories for already-published posts to match the latest mappings/DB:

```bash
python -m src.cli update-wp-categories
```

Summarize LLM spend by date or run (using `cost_ledger_path` + `cost_daily_path` from config):

```bash
python -m src.cli cost-report --date YYYY-MM-DD
python -m src.cli cost-report --run-id <run_id>
```

`cost-report` is routed through `src/orchestrators/cost_reporting_orchestrator.py`, which centralizes filtered report generation and daily rollup orchestration.

Extract chart/table candidates without running LLM analysis (writes JSON + crops):

```bash
python -m src.cli extract-candidates --limit 10
python -m src.cli extract-candidates --file-id <drive_file_id>
python -m src.cli extract-candidates --pdf "C:\\path\\report.pdf"
```

Vector-store ingest mode:

```bash
ANALYSIS_MODE=vector_store python -m src.cli ingest --limit 1
```

This reuses existing vector stores when `VECTOR_STORE_KEEP=true`, otherwise creates/attaches/waits per file and writes packs to `out/<report-slug>/report_analysis/`.

CLI options summary:

- `--limit`: optional integer across batch commands.
- `--folder`: optional Drive folder override for ingest.

## Streamlit Cockpit

The repository includes a full Streamlit admin/control panel aligned to `GUI-ARCHITECTURE.md`.
The entrypoint is intentionally thin and now delegates into dedicated UI + generator modules:

- `src/streamlit_app.py`: entrypoint only (page config + handoff).
- `src/ui/streamlit_pages.py`: Streamlit presentation/rendering for sidebar sections.
- `src/generators/streamlit_dashboard_generator.py`: dashboard data assembly and normalization (logs, JSON payloads, validation summaries, lock/state/report snapshots, ledger parsing, directory counts).
- `src/contracts/streamlit_dashboard.py`: dataclass contracts for Streamlit dashboard generator I/O.

Run locally:

```bash
streamlit run src/streamlit_app.py
```

Primary sidebar navigation (14 sections):

1. Cockpit Overview
2. Ingest Control
3. Candidate Extraction
4. Report Command Center
5. Cover Images
6. Analysis & Evidence
7. Validation Center
8. Publishing Control
9. Category Manager
10. Cost & Usage
11. Logs & Live Terminal
12. Settings & Prompts
13. System & Storage
14. Developer & Test Tools (disabled stub)

Design and behavior highlights:

- One dominant task per page with a consistent shell: title + status chip + primary action + filters + main data region + right-side details panel.
- Status chips are normalized to `success` / `warn` / `error` semantics for consistent operational feedback.
- Accessibility/readability defaults: captions are rendered in black and action buttons use a light-blue background for consistent contrast in the main content area.
- Interactive controls (navigation, actions, inputs, selectors) expose concise hover help with usage examples (capped at 1000 characters per tooltip).
- Pages are wired to existing contracts/services/orchestrators as source-of-truth surfaces (DB, files, config, and logs).
- Cockpit overview and publish queue views now use dedicated orchestrators (`ops_dashboard_orchestrator`, `publish_queue_orchestrator`) so UI code stays presentation-focused.
- The logs page supports structured filtering (`run_id`, `task_id`, `span_id`, `event`, `role`, `module`) and includes a terminal-style panel for UI-triggered run output history.
- The **Settings & Prompts** page now includes a full `app.yaml` editor with direct save support (optional timestamped backups), so every config key in `src/config/app.yaml` can be changed from the Streamlit UI.
- The same page now also provides a **Structured Form** tab with field-by-field widgets for all `app.yaml` sections (paths, ingest, rank, publish, analysis, cost, and model maps), designed for non-technical config editing.
- If runtime config validation fails, the UI still opens directly into **Settings & Prompts** so `app.yaml` can be fixed without leaving Streamlit.
- Extracted dashboard business logic is unit-tested in `tests/test_streamlit_dashboard_generator.py`.

## Output Layout

Default output structure:

```text
./out/
  <report-name>.html
  <report-name>/
    assets/
      <report-name>.png
    slices/
      <report-name>.png
      <report-name>1.png
    candidates/
      <report-name>.png
      <report-name>1.png
    thumbs/
      <report-name>.png
  candidates/
    <report_id>/
      candidates.json
  <report-name>/
    report_analysis/
      doc_map.json
      scope.json
      methods.json
      findings.json
      limitations.json
      quote_candidates.json
```

---

## Migration Notes

Marker-based PDF-to-HTML conversion has been removed.

---

## Support and Extension Points

To extend the system:

- Add new services in `src/services` and define contracts in `src/contracts`.
- Add new prompts in `src/prompts/<use_case>/`.
- Add new generators to compose services into outputs.
- Add orchestrators for new pipelines or batch flows as needed.

---

## Security and Compliance

- Secrets must not be committed to source control.
- Use `.env` locally and environment variables in CI/CD.
- Prompt logs are structured and should be routed to secure logging sinks in production.

---

## Vector Store & Cost Tracking Highlights

- Vector stores: `src/services/vector_store_service.py` handles create/upload/attach/status/wait using OpenAI vector stores; used by vector-mode generators.
- Analysis uses vector_store only; `ANALYSIS_MODE`/`USE_VECTOR_STORE` toggles are no longer needed.
- Evidence packs: `src/generators/evidence_pack_generator.py` uses `src/prompts/report_vs/**` and writes packs to `out/<report-slug>/report_analysis/*.json`; `doc_map` runs first, and remaining packs run in parallel with process-wide rate limiting via `ingest.evidence_packs.*`; validation uses `src/schemas/evidence_pack.schema.json` (permissive for empty fields).
- Artifacts: `src/generators/artifact_generator.py` writes `artifacts.json` under the same analysis path, parallelizing independent steps with dependency ordering and process-wide rate limiting via `ingest.artifacts.*`.
- Cost ledger: `src/services/cost_ledger_service.py` appends JSONL entries for every LLM call and writes daily rollups (`./out/cost-ledger.jsonl`, `./out/cost-daily.json`) using per-model pricing from config.
