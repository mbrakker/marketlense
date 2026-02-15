# Market Lense Streamlit Admin & Control Panel Architecture

## Purpose

Design a Streamlit-based admin/control panel that exposes every **existing** Market Lense capability with clear actions, diagnostics, and operational guardrails. The UI is a thin, transparent shell over the current **contracts -> services -> generators -> orchestrators** architecture and storage layout.

This cockpit must surface all CLI workflows as guided UI actions:

- `ingest`
- `extract-candidates`
- `generate-covers`
- `publish-wp`
- `recategorize`
- `update-wp-categories`
- `cost-report`

The UI must make inputs, outputs, logs, and artifact locations visible without inventing new system behavior.

---

## Information Architecture (Navigation)

**Primary navigation (sidebar):**

1. **Cockpit Overview** - system health, current locks, recent runs
2. **Ingest Control** - Drive ingest pipeline control center
3. **Candidate Extraction** - charts/tables candidate pack generation
4. **Report Command Center** - report-centric inspection (metadata + artifacts)
5. **Cover Images** - cover generation + asset viewer
6. **Analysis & Evidence** - vector-store evidence packs + artifacts
7. **Validation Center** - validation outputs + policy
8. **Publishing Control** - WordPress publish + category sync
9. **Category Manager** - taxonomy mappings + recategorize
10. **Cost & Usage** - spend + processing time summaries
11. **Logs & Live Terminal** - structured events + live run output
12. **Settings & Prompts** - read-only config + prompt registry
13. **System & Storage** - DB tables, locks, output folders
14. **Developer & Test Tools** - future / optional debug tooling

This layout keeps the UI minimal: one dominant task per page with a clear, inspectable source of truth.

---

## 1) Cockpit Overview (Admin Dashboard)

**Goal:** One-glance operational status.

**Core widgets (mapped to code/artifacts):**

- **Active run/last run summary**: show `run_id`, task counts, and success/error totals from structured log events.
- **Recent reports**: latest entries from the reports DB (title, publisher, HTML path, analysis mode).
- **Ingest lock**: display lock file path and owner to confirm concurrency control.
- **Storage health**: status of `output_dir`, `cache_dir`, `state_db`, `reports_db` from config service (paths are created on load).

**Admin value:** immediate visibility into system readiness and current workload.

---

## 2) Ingest Control (Google Drive -> HTML)

**Goal:** A full operational console for ingest and report generation.

**Inputs & switches:**

- **Folder override** and **limit** (mapped to CLI `--folder` and `--limit`).
- **Read-only settings**: OpenAI model, temperature, timeout, batch limit, PDF text settings (from config).
- **Mode display**: vector_store analysis and compare toggle (legacy/ignored).

**Pipeline timeline:**

- Stepper view showing:
  - Drive list -> cache hit/miss -> download -> EOF check -> skip check -> report generation -> state record.
- **Cover image creation** is part of report generation and should appear as a pipeline stage with output path details.

**Controls & safeguards:**

- **Run ingest** button triggers `run_ingest`.
- If lock conflict is detected, display a blocking alert with owner/TTL.

**Admin value:** safe ingest execution with full pipeline transparency and artifact tracking.

---

## 3) Candidate Extraction (Charts/Tables)

**Goal:** Generate and inspect candidate packs for charts/tables.

**Inputs:**

- **Folder override** and **limit**, plus optional **file_id** for a single report (mapped to CLI `extract-candidates`).
- **Local PDF path** with optional `report_id` override (supported by the orchestrator for non-Drive sources).

**Pipeline view:**

- Drive list -> cache hit/miss -> download -> EOF check -> candidate pack generation.

**Outputs:**

- Show `candidates.json` path, candidate count, chart/table counts, and crop count. Candidate packs are written under `output_dir/<report_name>/candidates/candidates.json` with crops under `output_dir/<report_name>/candidates/` (where `report_name` is the slugified PDF filename).
- Provide a viewer for the saved JSON and cropped image paths (if present).
**Admin value:** supports visual QA and asset harvesting without leaving Streamlit.

---

## 4) Report Command Center (Report-Centric View)

**Goal:** A single report-focused workspace where an operator can select a report and see all related data and artifacts.

**Core report selector:**

- Use the `reports` DB as the source of truth for selecting a report (title, file_id).

**Report detail sections:**

- **Metadata**: title, publisher, region, time period, taxonomy, categories, HTML path, md5, analysis mode.
- **Processing provenance**:
  - vector_store_id and evidence pack paths (for vector mode).
  - state DB status including vector store indexing status and errors (if any).
- **Artifacts panel**:
  - HTML output link/button (from `html_path`).
  - Evidence pack JSON view (doc_map, scope, methods, findings, limitations, quote_candidates) plus artifacts/validation if present. Packs live under `output_dir/<report_name>/report_analysis/*.json`.
  - **Cover image preview** if present under `output_dir/<report_slug>/assets/<bounded-publisher-title>-<file-id>.png`.

**Admin value:** a true report-centric cockpit that answers "everything about this report" in one place.

---

## 5) Cover Images (Generation + Assets)

**Goal:** Generate or regenerate report cover images and inspect outputs.

**Features:**

- **Generate covers** action (CLI `generate-covers`) with optional `style_config`, `limit`, and `file_id` overrides.
- **Cover generation pipeline** backed by the cover image orchestrator and generator.
- **Style config visibility**: display configured cover style YAML path from settings (`paths.cover_styles`).
- **Output viewer**: show generated PNG paths under `output_dir/<slugified_title>.pdf/assets/` (slugified publisher + title filename).

**Admin value:** reproducible cover generation without ad-hoc scripts.

---

## 6) Analysis & Evidence (Vector Store + Packs)

**Goal:** Inspect the evidence layer behind a report.

**Features:**

- **Vector store status**: show `vector_store_id`, `vector_store_status`, indexing timestamp from state DB.
- **Evidence pack explorer**: open JSON from stored pack paths (doc_map, scope, methods, findings, limitations, quote_candidates) plus artifacts/validation when present.
- **Vector store actions**: status refresh only. Create/upload/attach/wait occur within ingest; there is no separate delete/reindex endpoint exposed today.
- **Compare mode**: if enabled, show side-by-side outputs and pack paths for the two analysis modes (currently disabled in settings).

**Admin value:** QA and auditability of evidence and LLM reasoning inputs.

---

## 7) Validation Center

**Goal:** Ensure outputs meet validation policies and surface failures.

**Features:**

- **Validation policy panel**:
  - `ingest.validation.data_gap_policy` (warn/fail).
  - `publish.validation.policy` (block/warn).
- **Validation report viewer**:
  - Show validation JSON artifacts written during ingest (under `output_dir/<report_name>/report_analysis/validation*.json` and optional legacy mirror).

**Admin value:** explicit confidence and compliance controls for output quality.

---

## 8) Publishing Control (WordPress)

**Goal:** Controlled publishing and category syncing.

**Features:**

- **Publish queue**: HTML files found under `output_dir`, with publish state from `state_db`.
- **Publish action**: trigger `run_publish` (CLI `publish-wp`).
- **Settings summary**: site URL, username, post status, publish policy (read-only).
- **Result table**: status and post URL for each published report (stored in state DB).

**Admin value:** safe, auditable publishing with clear validation gating.

---

## 9) Category Manager (Taxonomy)

**Goal:** Manage and re-apply taxonomy mappings.

**Features:**

- **Mapping viewer**: render `src/config/category-mappings.yaml` categories/tags. Path is in config.
- **Recategorize action**: trigger CLI `recategorize` to re-score all reports.
- **WP category sync**: trigger `update-wp-categories` to align WordPress taxonomy.

**Admin value:** keeps categorization consistent and aligned to latest mappings.

---

## 10) Cost & Usage (Spend + Processing Time)

**Goal:** Govern spend and performance with trend summaries.

**Features:**

- **Ledger explorer**: open `cost-ledger.jsonl` and rollups `cost-daily.json` from config.
- **Cost report**: run by date or run_id (mirrors `cost-report` CLI).
- **Usage summaries**:
  - Spend per run/task and aggregated by day/week from the ledger file (token usage + estimated cost).
  - Processing time per step derived from structured log timestamps and run/task spans.
- **Pricing table**: display `cost.pricing` for model rate awareness.

**Admin value:** clear budget and performance monitoring with trend visibility.

---

## 11) Logs & Live Terminal (Observability)

**Goal:** Full observability console with live run output.

**Features:**

- **Log file discovery**: list the current log file based on `MARKET_LENSE_LOG_DIR` and naming convention.
- **Structured log filters**: filter by `run_id`, `task_id`, `span_id`, `event`, `role`, `module`.
- **Live run output**: when the UI triggers a CLI workflow, stream stdout/stderr into a live panel so operators can see real-time progress for ingest/publish/covers/candidates.
- **Raw model output viewer**: surface raw model responses that are captured in structured logs for artifacts generation, ranking, and validation so operators can inspect the JSON payloads.
- **Redaction awareness**: show that sensitive data is redacted via `***REDACTED***` in structured log output.

**Admin value:** true operational visibility while jobs are running.

---

## 12) Settings & Prompts (Read-Only)

**Goal:** Provide visibility into configuration without leaking secrets.

**Features:**

- **Config summary**: read-only view of `app.yaml` (paths, ingest, analysis, publish, cost).
- **Env overrides status**: display which values are coming from env vs YAML, mirroring config service behavior.
- **Prompt namespaces**: list prompt namespaces under `src/prompts` and show each prompt's SHA256 hash as computed by prompt service.

**Not displayed:**

- Secrets (OpenAI keys, WP tokens, etc.) remain strictly in environment variables and are not exposed in UI.

**Admin value:** configuration and prompt transparency without credential exposure.

---

## 13) System & Storage (Databases + Locks)

**Goal:** Direct visibility into system state and file outputs.

**Features:**

- **State DB explorer**: show `processed` + `published` rows, including vector store status.
- **Reports DB explorer**: show `reports` rows with metadata and analysis mode.
- **Lock status**: display ingest lock path/owner to help resolve stuck runs.
- **Storage map**: show `out/`, `cache/`, `state/` paths and core artifact subfolders (HTML, report_analysis, assets, candidates, slices, thumbs).

**Admin value:** clear operational control of persistence and concurrency.

---

## 14) Developer & Test Tools (Future / Optional)

**Goal:** Provide a place for testing and developer-facing debug tools when separate orchestration or CLI hooks exist.

**Notes:** There is no dedicated test runner or prompt sandbox service today; any developer tooling should be added as a separate orchestrator/CLI command before being surfaced in the UI.

---

## Visual Design Principles (Simplicity-First)

- **One task per page**; sidebar navigation never overflows.
- **Primary actions top-right**: "Run ingest", "Publish", "Generate covers", "Extract candidates".
- **Minimal color**: status chips for success/warn/error.
- **Details panel** on the right: metadata + file paths for selected rows.
- **No hidden state**: always show the underlying source (DB, file, config).
- **Progress clarity**: stepper view for ingest and candidate extraction stages.

---

## Data & Action Sources (Implementation Mapping)

| UI Element | Source of Truth | Code Module |
| --- | --- | --- |
| Config values | `src/config/app.yaml` + env | `config_service.load_settings` / `load_publish_settings` |
| Ingest actions | Orchestrator | `run_ingest` in `ingest_orchestrator` |
| Candidate extraction | Orchestrator | `run_candidate_extraction` in `candidate_extraction_orchestrator` |
| Cover generation | Orchestrator | `run_cover_image_generation` in `cover_image_orchestrator` |
| Publish actions | Orchestrator | `run_publish` in `publish_orchestrator` |
| Recategorize actions | Orchestrator | `run_recategorize` in `recategorize_orchestrator` |
| Update WP categories | Orchestrator | `run_update_wp_categories` in `wp_category_update_orchestrator` |
| Cost reports | Service | `cost_ledger_service.generate_cost_report` |
| Reports catalog | SQLite | `report_store_service.list_metadata` |
| Publish state | SQLite | `state_service.get_publish` / `already_published` |
| Evidence packs / validation artifacts | Files | `report_analysis_store_service` (paths persisted via report metadata) |
| Logs | Log file | `logging_service.setup_logging` + `utils.logging.log_event` |

---

## Minimal Streamlit Layout Sketch

```text
[Sidebar]
- Cockpit Overview
- Ingest Control
- Candidate Extraction
- Report Command Center
- Cover Images
- Analysis & Evidence
- Validation Center
- Publishing Control
- Category Manager
- Cost & Usage
- Logs & Live Terminal
- Settings & Prompts
- System & Storage

[Main]
- Title + status chip
- Primary action (button)
- Contextual filters (date/run/file)
- Primary table or cards
- Details panel (metadata + paths)
```

This architecture keeps the GUI grounded in existing Market Lense capabilities while ensuring every operational surface (ingest, candidates, covers, validation, publishing, costs, logs) is inspectable from one cockpit.
