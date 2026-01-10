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
- Optional compare mode: run both `local_text` and `vector_store` analyses in one pass, persist both snapshots, and render a secondary HTML for side-by-side diffing/debugging.

---

## Architecture Overview

The codebase follows a strict layered architecture under `src/`:

```
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
- **Generators**: Compose services and enforce domain rules (e.g., which charts are selected, how outputs are structured).
- **Orchestrators**: Define when and in what order things happen, including retries and state transitions.
- **Utils**: Pure deterministic functions (no I/O, no global state).

---

## Configuration (YAML + .env)

Primary config: `src/config/app.yaml`. Missing values can be provided via `.env` (loaded by `config_service`). Secrets must come from environment variables.

Key fields and env overrides:
- Paths: `paths.output_dir` (`OUTPUT_DIR`, default `./out`), `paths.cache_dir` (`CACHE_DIR`, default `./cache`), `paths.state_db` (`STATE_DB`), `paths.reports_db` (`REPORTS_DB`), `paths.category_mappings` (defaults to `src/config/category-mappings.yaml`).
- Ingest: `ingest.google_sa_path` (`GOOGLE_SERVICE_ACCOUNT_JSON`), `ingest.gdrive_folder_id` (`GDRIVE_FOLDER_ID`), `ingest.openai_model` (`OPENAI_MODEL`), `ingest.batch_limit` (`BATCH_LIMIT`, default 20), `ingest.temperature` (`TEMPERATURE`, default 1.0), `ingest.timeout_seconds` (`OPENAI_TIMEOUT_SECONDS`, default 600), `ingest.lock_ttl_seconds` (`INGEST_LOCK_TTL_SECONDS`, default 7200), `ingest.contents_page.*` (keywords, max_pages, min_headings, render_dpi).
- Analysis mode: `analysis.mode` (`ANALYSIS_MODE`, default `local_text`; set `vector_store` to enable file-search/Responses path).
- Vector store toggles: `analysis.use_vector_store` (`USE_VECTOR_STORE`, default derived from mode), `analysis.vector_store_keep` (`VECTOR_STORE_KEEP`, default `true`).
- Compare toggle: `analysis.compare` (`ANALYSIS_COMPARE`, default `false`) to run both modes and store comparison artifacts/HTML.
- Cost tracking: `analysis.cost_ledger_path` (`COST_LEDGER_PATH`, default `./out/cost-ledger.jsonl`), `cost.daily_path` (default `./out/cost-daily.json`), `cost.pricing` (per-model pricing map used by `utils.costing`).
- Validation: `publish.validation.policy` (`PUBLISH_VALIDATION_POLICY`, default `block`; set to `warn` to allow publish with issues).

Secrets (env only):
- `OPENAI_API_KEY` (required)
- `WP_APP_PASSWORD` or `WP_BEARER_TOKEN` (publishing)
- Optional provider keys (e.g., `MINERU_API_KEY`) if used.

Prompt locations:
- Local text analysis: `src/prompts/report_generation/`
- Vector store evidence packs: `src/prompts/report_vs/**` (`doc_map/`, `evidence_packs/{scope,methods,findings,limitations,quote_candidates}/`)
- Artifact generation: `src/prompts/report_vs/artifacts/**` (toc, summary, insights candidates/final, quotes, expert comment, LinkedIn post)
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
   - `src/orchestrators/ingest_orchestrator.py` loads settings and coordinates the ingest flow.

3. **Drive discovery**
   - `src/services/drive_service.py` lists PDF files in the target Drive folder.
   - Produces `DriveFile` contracts.

4. **Download + integrity check**
   - `drive_service.download_pdf(...)` downloads the PDF into cache.
   - `src/services/pdf_utils_service.py` checks for EOF marker and redownloads once if missing.

5. **State management**
   - `src/services/state_service.py` maintains a SQLite store of processed file IDs and hashes.
   - Skips already-processed documents.

6. **Report generation (per file)**
   - `src/generators/report_generator.py` runs the core pipeline:
     - **PDF info**: `pdf_utils_service.extract_pdf_info` captures page count and sanitized PDF metadata for persistence.
     - **PDF context**: `pdf_context_service.build_pdf_context` opens PyMuPDF and pypdf handles once; downstream services reuse them and fall back to local opens if unavailable.
     - **Contents/index detection**: scans the first pages for a contents/index section, renders a screenshot when found, and records the page number for HTML + DB output.
     - **Text extraction**: `pdf_text_service` extracts text from the first N pages (reusing the shared context when present).
- **LLM analysis**:
  - `local_text` mode: Sends prompt + extracted text to OpenAI for structured JSON output.
  - `vector_store` mode: Ensures a vector store exists (create → upload PDF → attach → wait for indexing via `vector_store_service`), then calls `openai_service.openai_respond_with_vector_store` (Responses API + file search). Evidence packs are generated via `src/generators/evidence_pack_generator.py` (doc_map, scope, methods, findings, limitations, quote_candidates), stored under `out/report_analysis/<file_id>/*.json`, and persisted in the metadata DB (`reports` table columns `vector_store_id`, `evidence_packs_json`; state DB stores `vector_store_status`, `indexed_at_utc`, `openai_file_id`, `last_error`). Orchestrator logs `VECTOR_STORE_CREATED`, `VECTOR_STORE_INDEXED`, `EVIDENCE_READY`.
  - **Validation**: `src/generators/validation_generator.py` runs semantic checks (metrics vs evidence, quotes verbatim, no new numbers in expert/LinkedIn) and LLM grounding (`src/prompts/report_vs/validate/grounding`). Results are stored at `out/report_analysis/<file_id>/validation*.json`, added to the rendered payload, and logged.
     - **Normalization**: `normalize_generator` enforces strict schema and list sizing.
     - **Categorization**: taxonomy tags are scored against `src/config/category-mappings.yaml`; top 3 categories are stored and rendered, and unmapped tags are appended under `uncategorized` in that YAML.
     - **Figure selection**: `figure_service` selects a representative visual and caption.
     - **Candidate extraction**: `extract_service` finds chart/table regions.
     - **Candidate ranking**: `rank_service` scores candidates via LLM.
     - **Cropping**: `crop_service` crops top-ranked regions.
     - **Preview rendering**: `preview_service` renders the first page to PNG.
     - **HTML rendering**: `render_service` generates the final HTML digest; when compare mode is on, an additional `<report>-<mode>.html` is rendered for each comparison mode (e.g., vector_store) and recorded under `html_<mode>` in evidence pack paths.

7. **State record**
   - The orchestrator records completion state after successful report generation.

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

The orchestrator retries report generation when a retryable `AppError` is raised, with bounded attempts and backoff.

---

## Prompt Management

Prompts are stored in YAML by namespace:

```
src/prompts/report_generation/          # local_text mode
src/prompts/report_vs/doc_map/          # vector_store doc map
src/prompts/report_vs/evidence_packs/   # vector_store packs (scope/methods/findings/limitations/quote_candidates)
src/prompts/report_vs/artifacts/        # artifact sections (toc, summary, insights, quotes, expert comment, LinkedIn)
```

Prompts are rendered with Jinja2 (`{{ variable }}`), loaded and hashed by `src/services/prompt_service.py`, and logged with their SHA256 hashes for reproducibility.

- Prompt caching: prompt sets are cached in-memory per namespace for the duration of a process. `PromptLoadRequest` supports `reload_if_changed` (mtime check) and `force_reload` (bypass cache) when you need to pick up edited prompt files mid-run.

---

## Category mappings

- Source of truth: `src/config/category-mappings.yaml` (versioned by `schema_version`).
- Scoring: each matched tag adds +1 to a category; top 3 categories are assigned to the report and stored in the metadata DB; categories sync to WordPress posts but are not rendered in HTML.
- Maintenance: add categories with `id` (snake_case), `label`, `description`, and a focused `tags` list (lowercase, snake_case). Place new entries at the top to keep recent taxonomies visible.
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

Schema validation is performed by `src/utils/schema_validator.py` and logged per pack.

---

## Testing

Minimal unit tests exist under `tests/`:
- `test_validation.py`: contract validation helpers
- `test_normalize_service.py`: normalization behavior
- `test_cli.py`: CLI wiring
- `test_orchestrator_retry.py`: retry behavior
- `test_publish_orchestrator.py`: publish orchestration
- `test_html_utils.py`: HTML parsing helpers
- `test_artifact_generator.py`: artifact JSON generation/validation
- `test_render_service_artifacts.py`: HTML sections for artifact rendering
- `test_golden_set.py`: regression on golden fixtures in `out/fixtures/golden_set/` (expects metadata.yaml + expected JSON/HTML + referenced PDFs)

Run tests locally:

```bash
python -m pytest
```

CI runs these tests via `.github/workflows/ci.yml`.

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

Golden-set (vector store) harness for local PDFs:

```bash
python -m src.cli golden-set-vector --fixtures <dir> --limit <N>
# --fixtures: directory containing PDFs
# --limit: max PDFs to process (optional)
```
Golden-set source PDFs now live under `out/fixtures/golden_set/pdfs`; pass that directory to the `--fixtures` flag when running locally.

Vector-store ingest mode:

```bash
ANALYSIS_MODE=vector_store USE_VECTOR_STORE=1 python -m src.cli ingest --limit 1
```

This reuses existing vector stores when `VECTOR_STORE_KEEP=true`, otherwise creates/attaches/waits per file and writes packs to `out/report_analysis/<file_id>/`.

CLI options summary:
- `--limit`: optional integer across batch commands.
- `--folder`: optional Drive folder override for ingest.
- `--fixtures`: required for `golden-set-vector`.

## Output Layout

Default output structure:

```
./out/
  <report-name>.html
  <report-name>/
    assets/
      <report-name>.png
    slices/
      <report-name>.png
      <report-name>1.png
    thumbs/
      <report-name>.png
  report_analysis/
    <file_id>/
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
- Add new generators to compose services into outputs (local text or vector store flows).
- Add orchestrators for new pipelines or batch flows (for example, additional golden-set harnesses).

---

## Security and Compliance

- Secrets must not be committed to source control.
- Use `.env` locally and environment variables in CI/CD.
- Prompt logs are structured and should be routed to secure logging sinks in production.

---

## Vector Store & Cost Tracking Highlights

- Vector stores: `src/services/vector_store_service.py` handles create/upload/attach/status/wait using OpenAI vector stores; used by vector-mode generators and the golden-set harness.
- Analysis modes: `ANALYSIS_MODE=local_text` (default) keeps existing behavior; `ANALYSIS_MODE=vector_store` or `USE_VECTOR_STORE=true` enables file-search/Responses path.
- Evidence packs: `src/generators/evidence_pack_generator.py` uses `src/prompts/report_vs/**` and writes packs + `out/report_analysis/<report_id>/*.json`; validation uses `src/schemas/evidence_pack.schema.json` (permissive for empty fields).
- Golden-set vector harness: `src/orchestrators/golden_set_orchestrator.py` + CLI `golden-set-vector` process local PDFs end-to-end and write packs to `out/golden_set/<report_id>/packs/*.json`.
- Cost ledger: `src/services/cost_ledger_service.py` appends JSONL entries for every LLM call and writes daily rollups (`./out/cost-ledger.jsonl`, `./out/cost-daily.json`) using per-model pricing from config.
