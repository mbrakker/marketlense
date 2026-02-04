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
【F:src/cli.py†L1-L320】

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
14. **Developer & Test Tools** - prompt sandbox, raw model outputs (debug)

This layout keeps the UI minimal: one dominant task per page with a clear, inspectable source of truth.

This layout keeps the UI minimal: one dominant task per page with a clear, inspectable source of truth.

---

## 1) Cockpit Overview (Admin Dashboard)

**Goal:** One-glance operational status.

**Core widgets (mapped to code/artifacts):**
- **Active run/last run summary**: show `run_id`, task counts, and success/error totals from structured log events.【F:src/utils/logging.py†L1-L112】
- **Recent reports**: latest entries from the reports DB (title, publisher, HTML path, analysis mode).【F:src/services/report_store_service.py†L16-L206】
- **Ingest lock**: display lock file path and owner to confirm concurrency control.【F:src/orchestrators/ingest_orchestrator.py†L44-L124】
- **Storage health**: status of `output_dir`, `cache_dir`, `state_db`, `reports_db` from config service (paths are created on load).【F:src/services/config_service.py†L88-L243】

**Admin value:** immediate visibility into system readiness and current workload.

---

## 2) Ingest Control (Google Drive -> HTML)

**Goal:** A full operational console for ingest and report generation.

**Inputs & switches:**
- **Folder override** and **limit** (mapped to CLI `--folder` and `--limit`).【F:src/cli.py†L32-L127】
- **Read-only settings**: OpenAI model, temperature, timeout, batch limit, PDF text settings (from config).【F:src/services/config_service.py†L88-L243】
- **Mode display**: vector_store analysis and compare toggle (legacy/ignored).【F:src/services/config_service.py†L145-L211】

**Pipeline timeline:**
- Stepper view showing:
  - Drive list -> cache hit/miss -> download -> EOF check -> skip check -> report generation -> state record.【F:src/orchestrators/ingest_orchestrator.py†L122-L314】
- **Cover image creation** is part of report generation and should appear as a pipeline stage with output path details.【F:src/generators/report_generator.py†L1065-L1116】

**Controls & safeguards:**
- **Run ingest** button triggers `run_ingest`.【F:src/orchestrators/ingest_orchestrator.py†L44-L124】
- If lock conflict is detected, display a blocking alert with owner/TTL.【F:src/orchestrators/ingest_orchestrator.py†L61-L93】

**Admin value:** safe ingest execution with full pipeline transparency and artifact tracking.

---

## 3) Candidate Extraction (Charts/Tables)

**Goal:** Generate and inspect candidate packs for charts/tables.

**Inputs:**
- **Folder override** and **limit**, plus optional **file_id** for a single report (mapped to CLI `extract-candidates`).【F:src/cli.py†L78-L127】
- **Local PDF path** with optional `report_id` override (supported by the orchestrator for non-Drive sources).【F:src/orchestrators/candidate_extraction_orchestrator.py†L94-L206】

**Pipeline view:**
- Drive list -> cache hit/miss -> download -> EOF check -> candidate pack generation.【F:src/orchestrators/candidate_extraction_orchestrator.py†L1-L206】

**Outputs:**
- Show `candidates.json` path, candidate count, chart/table counts, and crop count. Candidate packs are written under `output_dir/<report_name>/candidates/` by the generator.【F:src/generators/candidate_extraction_generator.py†L1-L190】
- Provide a viewer for the saved JSON and cropped image paths (if present).【F:src/generators/candidate_extraction_generator.py†L1-L190】
**Ranking controls & debug:**
- Allow re-running candidate ranking for a selected `candidates.json`, select rank model/temperature/seed override, and re-run ranking without a full ingest. Show ranked table and let operators select a top-N crop operation.
- Expose raw model outputs and debug files (e.g., `debug/rank_raw_<ts>.txt`) for troubleshooting ranking prompts and model responses.
**Admin value:** supports visual QA and asset harvesting without leaving Streamlit.

---

## 4) Report Command Center (Report-Centric View)

**Goal:** A single report-focused workspace where an operator can select a report and see all related data and artifacts.

**Core report selector:**
- Use the `reports` DB as the source of truth for selecting a report (title, file_id).【F:src/services/report_store_service.py†L16-L206】

**Report detail sections:**
- **Metadata**: title, publisher, region, time period, taxonomy, categories, HTML path, md5, analysis mode.【F:src/services/report_store_service.py†L207-L364】
- **Processing provenance**:
  - vector_store_id and evidence pack paths (for vector mode).【F:src/services/report_store_service.py†L207-L364】
  - state DB status including vector store indexing status and errors (if any).【F:src/services/state_service.py†L8-L120】
- **Artifacts panel**:
  - HTML output link/button (from `html_path`).【F:src/services/report_store_service.py†L207-L364】
  - Evidence packs JSON view (scope/methods/findings/limitations/quote candidates).【F:src/services/report_store_service.py†L207-L364】
  - **Cover image preview** if present under `output_dir/<slugified_title>.pdf/assets/*.png` (cover generator output path).【F:src/generators/cover_image_generator.py†L144-L206】

**Admin value:** a true report-centric cockpit that answers "everything about this report" in one place.

---

## 5) Cover Images (Generation + Assets)

**Goal:** Generate or regenerate report cover images and inspect outputs.

**Features:**
- **Generate covers** action (CLI `generate-covers`) with optional `style_config`, `limit`, and `file_id` overrides.【F:src/cli.py†L205-L250】
- **Cover generation pipeline** backed by the cover image orchestrator and generator.【F:src/orchestrators/cover_image_orchestrator.py†L1-L120】【F:src/generators/cover_image_generator.py†L1-L220】
- **Style config visibility**: display configured cover style YAML path from settings (`paths.cover_styles`).【F:src/config/app.yaml†L1-L20】【F:src/services/config_service.py†L88-L211】
- **Output viewer**: show generated PNG paths under `output_dir/<slugified_title>.pdf/assets/`.【F:src/generators/cover_image_generator.py†L144-L206】

**Admin value:** reproducible cover generation without ad-hoc scripts.

---

## 6) Analysis & Evidence (Vector Store + Packs)

**Goal:** Inspect the evidence layer behind a report.

**Features:**
- **Vector store status**: show `vector_store_id`, `vector_store_status`, indexing timestamp from state DB.【F:src/services/state_service.py†L8-L120】
- **Evidence pack explorer**: open JSON from paths stored in metadata (`scope`, `methods`, `findings`, `limitations`, `quote_candidates`).【F:src/services/report_store_service.py†L207-L364】
- **Re-generate evidence packs**: allow re-running `generate_evidence_packs` for a report (writes refreshed pack JSON and updates stored pack paths).【F:src/generators/evidence_pack_generator.py†L1-L240】
- **Vector store actions**: surface actions to force reindexing/status refresh, and (only if supported by the provider) delete/prune vector store instances; the UI should disable or hide delete when a delete API is not available.
- **Compare mode**: if enabled, show side-by-side outputs and pack paths for the two analysis modes.【F:src/services/config_service.py†L145-L211】

**Admin value:** QA and auditability of evidence and LLM reasoning inputs.

---

## 7) Validation Center

**Goal:** Ensure outputs meet validation policies and surface failures.

**Features:**
- **Validation policy panel**:
  - `ingest.validation.data_gap_policy` (warn/fail).【F:src/services/config_service.py†L88-L211】
  - `publish.validation.policy` (block/warn).【F:src/services/config_service.py†L300-L380】
- **Validation report viewer**:
  - Show validation JSON artifacts written during ingest (referenced in output directories).【F:src/orchestrators/ingest_orchestrator.py†L231-L314】

**Admin value:** explicit confidence and compliance controls for output quality.

---

## 8) Publishing Control (WordPress)

**Goal:** Controlled publishing and category syncing.

**Features:**
- **Publish queue**: HTML files found under `output_dir`, with publish state from `state_db`.【F:src/services/state_service.py†L121-L229】
- **Publish action**: trigger `run_publish` (CLI `publish-wp`).【F:src/cli.py†L130-L168】
- **Settings summary**: site URL, username, post status, publish policy (read-only).【F:src/services/config_service.py†L300-L380】
- **Result table**: status and post URL for each published report (stored in state DB).【F:src/services/state_service.py†L121-L229】

**Admin value:** safe, auditable publishing with clear validation gating.

---

## 9) Category Manager (Taxonomy)

**Goal:** Manage and re-apply taxonomy mappings.

**Features:**
- **Mapping viewer**: render `src/config/category-mappings.yaml` categories/tags. Path is in config.【F:src/services/config_service.py†L88-L211】
- **Recategorize action**: trigger CLI `recategorize` to re-score all reports.【F:src/cli.py†L169-L204】
- **WP category sync**: trigger `update-wp-categories` to align WordPress taxonomy.【F:src/cli.py†L252-L286】

**Admin value:** keeps categorization consistent and aligned to latest mappings.

---

## 10) Cost & Usage (Spend + Processing Time)

**Goal:** Govern spend and performance with trend summaries.

**Features:**
- **Ledger explorer**: open `cost-ledger.jsonl` and rollups `cost-daily.json` from config.【F:src/config/app.yaml†L1-L45】
- **Cost report**: run by date or run_id (mirrors `cost-report` CLI).【F:src/cli.py†L287-L320】
- **Usage summaries**:
  - Spend per run/task and aggregated by day/week from the ledger file (token usage + estimated cost).【F:src/services/cost_ledger_service.py†L1-L214】
  - Processing time per step derived from structured log timestamps and run/task spans.【F:src/utils/logging.py†L63-L112】
- **Pricing table**: display `cost.pricing` for model rate awareness.【F:src/config/app.yaml†L33-L45】

**Admin value:** clear budget and performance monitoring with trend visibility.

---

## 11) Logs & Live Terminal (Observability)

**Goal:** Full observability console with live run output.

**Features:**
- **Log file discovery**: list the current log file based on `MARKET_LENSE_LOG_DIR` and naming convention.【F:src/services/logging_service.py†L1-L47】
- **Structured log filters**: filter by `run_id`, `task_id`, `span_id`, `event`, `role`, `module`.【F:src/utils/logging.py†L63-L112】
- **Live run output**: when the UI triggers a CLI workflow, stream stdout/stderr into a live panel so operators can see real-time progress for ingest/publish/covers/candidates.
- **Raw model output viewer**: surface saved raw model responses (debug directory) for artifacts generation, ranking, semantic validation, etc., so operators can download and inspect raw JSON/edge-cases.
- **Redaction awareness**: show that sensitive data is redacted via `***REDACTED***` in structured log output.【F:src/utils/logging.py†L24-L79】

**Admin value:** true operational visibility while jobs are running.

---

## 12) Settings & Prompts (Read-Only)

**Goal:** Provide visibility into configuration without leaking secrets.

**Features:**
- **Config summary**: read-only view of `app.yaml` (paths, ingest, analysis, publish, cost).【F:src/config/app.yaml†L1-L45】
- **Env overrides status**: display which values are coming from env vs YAML, mirroring config service behavior.【F:src/services/config_service.py†L41-L213】
- **Prompt namespaces**: list prompt namespaces under `src/prompts` and show each prompt's SHA256 hash as computed by prompt service.【F:src/services/prompt_service.py†L1-L122】- **Prompt sandbox / test harness**: allow operators to render a prompt with custom variables, view the rendered system & user prompt text, and optionally run a dry LLM invocation (JSON mode or vector-backed) to observe a sample response. Save sandbox runs to the debug directory for review.
**Not displayed:**
- Secrets (OpenAI keys, WP tokens, etc.) remain strictly in environment variables and are not exposed in UI.【F:src/services/config_service.py†L41-L213】

**Admin value:** configuration and prompt transparency without credential exposure.

---

## 13) System & Storage (Databases + Locks)

**Goal:** Direct visibility into system state and file outputs.

**Features:**
- **State DB explorer**: show `processed` + `published` rows, including vector store status.【F:src/services/state_service.py†L16-L229】
- **Reports DB explorer**: show `reports` rows with metadata and analysis mode.【F:src/services/report_store_service.py†L16-L206】
- **Lock status**: display ingest lock path/owner to help resolve stuck runs.【F:src/orchestrators/ingest_orchestrator.py†L44-L124】
- **Storage map**: show `out/`, `cache/`, `state/` paths and core artifact subfolders (HTML, evidence packs, assets, candidates).【F:src/config/app.yaml†L1-L45】

**Admin value:** clear operational control of persistence and concurrency.

---

## 14) Developer & Test Tools (Testing & Debug)

**Goal:** Provide a place for testing and developer-facing debug tools.

**Features:**
- **Test runner**: allow launching selected test markers or CI-like smoke tests to validate environment health.
- **Debug tools**: prompt sandbox, raw model outputs viewer (debug), re-run evidence packs, re-run ranking, and a place to stash curated test variables/configs.

**Admin value:** makes it easy to validate behavior and triage model-output edge cases.

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
| Logs | Log file | `logging_service.setup_logging` + `utils.logging.log_event` |

---

## Minimal Streamlit Layout Sketch

```
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
