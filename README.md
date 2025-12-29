# Market Lense

Enterprise PDF ingestion and analysis pipeline that converts Google Drive reports into structured HTML digests using an LLM and extraction heuristics.

---

## Executive Summary

Market Lense ingests PDFs from a configured Google Drive folder, extracts text and structured visual candidates (tables/charts), calls an LLM for a strict JSON analysis, ranks and crops key visuals, and renders a compact HTML digest. The system is organized around a strict architecture with contracts, services, generators, and orchestrators to ensure reliability, observability, and testability.

Key traits:
- Contract-first data model for all external I/O boundaries.
- Service isolation for all external systems and file I/O.
- Generator logic that composes services into domain outputs.
- Orchestrator that controls sequencing, retries, and state.
- Structured logging with run/task/span identifiers.

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

## End-to-End Flow

1. **Configuration load**
   - `src/services/config_service.py` loads environment variables and ensures required paths exist.
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
     - **Text extraction**: `openai_service` extracts text from the first N pages (local PDF parsing).
     - **LLM analysis**: Sends prompt + extracted text to OpenAI for structured JSON output.
     - **Normalization**: `normalize_service` enforces strict schema and list sizing.
     - **Figure selection**: `figure_service` selects a representative visual and caption.
     - **Candidate extraction**: `candidate_extraction_service` finds chart/table regions.
     - **Candidate ranking**: `rank_service` scores candidates via LLM.
     - **Cropping**: `crop_service` crops top-ranked regions.
     - **Preview rendering**: `preview_service` renders the first page to PNG.
     - **HTML rendering**: `render_service` generates the final HTML digest.

7. **State record**
   - The orchestrator records completion state after successful report generation.

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

Prompts are stored in YAML under:

```
src/prompts/report_generation/
  system.yaml
  user.yaml
```

Prompts are loaded and hashed by `src/services/prompt_service.py` and logged with their SHA256 hashes for reproducibility.

---

## Contracts and Schemas

Key contracts live under `src/contracts/`:
- `config.py`: `AppSettings`
- `drive.py`: Drive file and request/response contracts
- `openai.py`: OpenAI request/response contracts
- `report_models.py`: `ReportPayload`, `Quote`, `Figure`, etc.
- `report_assets.py`: request/response contracts for figure, preview, crop, ranking, etc.
- `normalize.py`: normalization request/response
- `state.py`: state store contracts
- `pdf_utils.py`: EOF check contract

---

## Testing

Minimal unit tests exist under `tests/`:
- `test_validation.py`: contract validation helpers
- `test_normalize_service.py`: normalization behavior
- `test_cli.py`: CLI wiring
- `test_orchestrator_retry.py`: retry behavior

Run tests locally:

```bash
python -m unittest discover -s tests
```

CI runs these tests via `.github/workflows/ci.yml`.

---

## Runtime Requirements

Required environment variables:
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GDRIVE_FOLDER_ID`
- `OPENAI_API_KEY`

Optional:
- `OPENAI_MODEL`
- `BATCH_LIMIT`
- `OUTPUT_DIR`
- `CACHE_DIR`
- `STATE_DB`
- `TEMPERATURE`

---

## CLI Usage

Primary entrypoint:

```bash
python -m src.cli ingest --limit 10
```

Backward-compatible shim:

```bash
python -m app.cli ingest --limit 10
```

---

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
```

---

## Migration Notes

Legacy `app/*` modules have been deprecated in favor of `src/*`. Import paths should target `src` only. Attempting to call deprecated app modules will raise runtime errors to enforce architectural boundaries.

Marker-based PDF-to-HTML conversion has been removed.

---

## Support and Extension Points

To extend the system:
- Add new services in `src/services` and define contracts in `src/contracts`.
- Add new prompts in `src/prompts/<use_case>/`.
- Add new generators to compose services into outputs.
- Add orchestrators for new pipelines or batch flows.

---

## Security and Compliance

- Secrets must not be committed to source control.
- Use `.env` locally and environment variables in CI/CD.
- Prompt logs are structured and should be routed to secure logging sinks in production.
