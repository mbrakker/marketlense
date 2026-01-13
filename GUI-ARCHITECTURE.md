<<<<<<< ours
# Market Lense Streamlit GUI Architecture

## Purpose
Design a Streamlit-based GUI that exposes **all capabilities already present** in the Market Lense codebase, while keeping the interface minimal, discoverable, and aligned with the system’s architecture: contracts → services → generators → orchestrators. This GUI is an operational console for ingest, review, validation, publishing, monitoring, and configuration.

The UI must make the current CLI workflows (`ingest`, `publish-wp`, `recategorize`, `update-wp-categories`, `cost-report`) feel like clear, guided flows with transparency into inputs, outputs, and logs. 【F:src/cli.py†L1-L279】
=======
# Market Lense Streamlit Admin & Control Panel Architecture

## Purpose
Build a **fully functional admin/control panel (cockpit)** in Streamlit that surfaces **every existing capability** of Market Lense with clear actions, diagnostics, and operational guardrails. The UI is not a new product layer; it is a thin, transparent shell over the existing **contracts → services → generators → orchestrators** architecture and current storage layout.

This cockpit must:
- Expose all CLI workflows (`ingest`, `publish-wp`, `recategorize`, `update-wp-categories`, `cost-report`) as guided UI actions.【F:src/cli.py†L1-L279】
- Provide deep, inspectable views into **settings**, **databases**, **artifact files**, **logs**, **validation**, and **costs**.
- Make the system’s **state, locks, retries, and live execution output** visible and explainable.
>>>>>>> theirs

---

## Information Architecture (Navigation)

<<<<<<< ours
**Primary navigation (left sidebar):**
1. **Overview** — system status + recent activity summary
2. **Ingest** — Google Drive ingest pipeline
3. **Reports** — metadata database + report detail view
4. **Analysis & Evidence** — vector store evidence packs + artifacts
5. **Validation** — validation reports & policies
6. **Publishing** — WordPress publishing and category syncing
7. **Categories** — category mappings & recategorize runs
8. **Costs** — cost ledger, rollups, and cost reports
9. **Logs** — structured event viewer
10. **Settings** — app.yaml + env overrides visibility
11. **System** — databases, locks, and storage paths

Each section is tied to code modules or persisted outputs to avoid inventing new system behavior.

---

## 1) Overview (Dashboard)

**Goal:** Provide a “single glance” status of the system and recent work.

**Features (mapped to code & artifacts):**
- **Latest run summary**: Use structured logs and/or output state to show most recent run_id, task count, successes/errors. Logs are emitted by services/orchestrators with `run_id`, `task_id`, `span_id`, `event`. 【F:src/utils/logging.py†L1-L112】
- **Recent reports list**: Pull from the reports DB (SQLite) via `reports` table. Display title, publisher, file ID, created/updated time, and HTML path. 【F:src/services/report_store_service.py†L16-L206】
- **Ingest lock status**: Show whether a lock file exists and its owner/pid metadata (ingest lock path). The ingest orchestrator uses a lock with TTL to prevent concurrent runs. 【F:src/orchestrators/ingest_orchestrator.py†L44-L124】
- **Storage health**: Show configured output/cache/state paths from `app.yaml`/env, and whether directories exist (created by config service). 【F:src/services/config_service.py†L120-L243】

**Why this UI matters:** It exposes key operational signals: pipeline activity, outputs, and concurrency protection.

---

## 2) Ingest (Google Drive → HTML)

**Goal:** Run the ingest pipeline with clarity on inputs, progress, and outputs.

**Features:**
- **Input controls**
  - Drive folder ID override (`--folder`) and batch limit (`--limit`). These map directly to the CLI options. 【F:src/cli.py†L19-L101】
  - Display service account path and OpenAI model from config for transparency. 【F:src/services/config_service.py†L120-L243】
- **Pipeline stages view**
  - List PDFs from Drive, cache hit/miss, download status, EOF check, and skip logic for already-processed items. 【F:src/orchestrators/ingest_orchestrator.py†L122-L229】
  - Show processing outcomes per file: status, HTML path, md5, vector store ID/status (if present). 【F:src/orchestrators/ingest_orchestrator.py†L231-L314】
- **Mode controls (read-only display + info)**
  - Show analysis mode (`vector_store`, default/only) and compare toggle (legacy/ignored). These are loaded from config/env and passed into `IngestSettings`. 【F:src/services/config_service.py†L145-L211】

**Why this UI matters:** It makes the ingest orchestration and its skip/lock behavior visible without leaving Streamlit.

---

## 3) Reports (Metadata DB + HTML access)

**Goal:** Provide a report catalog and deep access to each report’s metadata and HTML output.

**Features:**
- **Report catalog**
  - Table backed by the `reports` SQLite table (title, file ID, publisher, categories, taxonomy, md5, analysis mode, HTML path). 【F:src/services/report_store_service.py†L16-L206】
- **Report detail**
  - Read full metadata (region, time period, PDF metadata, contents page number, vector store ID, evidence pack paths). 【F:src/services/report_store_service.py†L207-L364】
  - Provide a “Open HTML” link/button to render the output digest (`html_path` stored in DB). 【F:src/services/report_store_service.py†L207-L364】

**Why this UI matters:** It centralizes output discovery, which is currently file-system and SQLite driven.

---

## 4) Analysis & Evidence (Vector Store + Evidence Packs)

**Goal:** Expose the evidence-pack artifacts produced during vector store analysis.

**Features:**
- **Vector store status**
  - Surface `vector_store_id`, `vector_store_status`, and indexing timestamps from the state DB. 【F:src/services/state_service.py†L8-L120】
- **Evidence pack viewer**
  - Use `evidence_pack_paths` stored in `reports` metadata to open JSON files (scope, methods, findings, limitations, quote candidates). 【F:src/services/report_store_service.py†L207-L364】
- **Compare mode context**
  - When `analysis_compare` is enabled, show dual HTML outputs and evidence pack paths per mode. The setting is part of `AppSettings` loaded in config. 【F:src/services/config_service.py†L145-L211】

**Why this UI matters:** It turns the vector store evidence outputs into inspectable, QA-friendly artifacts.

---

## 5) Validation

**Goal:** Centralize the validation outputs and policy enforcement.

**Features:**
- **Validation policy display**
  - Show `ingest.validation.data_gap_policy` (warn vs fail) from config. 【F:src/services/config_service.py†L108-L211】
  - Show publish validation policy (`block` vs `warn`) used in WordPress publishing. 【F:src/services/config_service.py†L300-L380】
- **Validation report viewer**
  - Display validation JSON saved per report (paths referenced in evidence pack metadata or stored in output directories). The generator records these artifacts during ingest. 【F:src/orchestrators/ingest_orchestrator.py†L231-L314】

**Why this UI matters:** Validation outcomes affect publish behavior and user trust in the output.

---

## 6) Publishing (WordPress)

**Goal:** Support one-click or batched publication of generated HTML.

**Features:**
- **Publish queue**
  - List HTML files discovered under `OUTPUT_DIR` and show which file IDs have already been published (state DB). 【F:src/services/state_service.py†L121-L195】
- **Publish action**
  - Trigger the publish orchestrator (equivalent to `publish-wp` CLI). 【F:src/cli.py†L78-L135】
- **Publish settings summary**
  - Display WordPress site URL, username, post status, and validation policy as read-only settings for clarity. 【F:src/services/config_service.py†L300-L380】
- **Publish status table**
  - Show publish results (status, post URL). Persisted in state DB. 【F:src/services/state_service.py†L121-L229】

**Why this UI matters:** It enables safe, auditable publication without jumping to CLI.

---

## 7) Categories (Taxonomy Management)

**Goal:** Manage content taxonomy and keep report categories aligned with mappings.

**Features:**
- **Category mapping viewer**
  - Render `src/config/category-mappings.yaml` as a searchable list of categories/tags. Path is managed in config. 【F:src/services/config_service.py†L104-L211】
- **Recategorize action**
  - Trigger the recategorize orchestrator (`recategorize` CLI) to recompute categories for all reports. 【F:src/cli.py†L137-L178】
- **Update WordPress categories**
  - Trigger `update-wp-categories` to sync WP categories with the updated mappings. 【F:src/cli.py†L180-L216】

**Why this UI matters:** Taxonomy impacts discoverability of published reports and is meant to be iterated.

---

## 8) Costs (LLM Ledger)

**Goal:** Provide accountability and visibility into LLM usage and cost.

**Features:**
- **Cost ledger viewer**
  - Surface `cost-ledger.jsonl` and daily rollups (`cost-daily.json`) configured in `app.yaml`. 【F:src/config/app.yaml†L1-L45】
- **Cost report tool**
  - Run cost reports by date or run ID, showing top-cost steps and token totals (mirrors `cost-report` CLI). 【F:src/cli.py†L218-L279】
- **Pricing table**
  - Display model pricing entries from config (`cost.pricing`). 【F:src/config/app.yaml†L33-L45】

**Why this UI matters:** Cost transparency supports governance and optimization.

---

## 9) Logs (Structured Observability)

**Goal:** Provide a structured log viewer that respects the system’s event model.

**Features:**
- **Log file discovery**
  - Show the log directory and current log file name (defaults to `logs/market_lense_YYYY-MM-DD.log`). 【F:src/services/logging_service.py†L1-L47】
- **Structured log viewer**
  - Filter by `run_id`, `task_id`, `span_id`, `event`, `role`, and `module` using JSON log lines produced by `log_event`. 【F:src/utils/logging.py†L63-L112】
- **Redaction reminder**
  - UI hint that sensitive fields are redacted (`***REDACTED***`) in logs for safety. 【F:src/utils/logging.py†L24-L79】

**Why this UI matters:** It makes the existing observability model usable without grep.

---

## 10) Settings (Configuration & Prompts)

**Goal:** Provide visibility into configuration without leaking secrets.

**Features:**
- **Config summary**
  - Read-only view of `app.yaml` (paths, ingest, rank, publish, analysis, cost). 【F:src/config/app.yaml†L1-L45】
- **Env overrides status**
  - Display which values are coming from env vs YAML, mirroring config service behavior. 【F:src/services/config_service.py†L41-L213】
- **Prompt namespaces**
  - List prompt namespaces under `src/prompts` (report_generation, report_vs, artifacts, etc.) and show each prompt’s SHA256 hash. This maps to prompt loading in `prompt_service`. 【F:src/services/prompt_service.py†L21-L122】

**Why this UI matters:** It avoids configuration guesswork and supports reproducibility.

---

## 11) System (Databases, Locks, Storage)

**Goal:** Surface system-level state and storage to operators.

**Features:**
- **State DB explorer**
  - Display `processed` and `published` tables with file IDs, md5, vector store status, and post URLs. 【F:src/services/state_service.py†L16-L229】
- **Reports DB explorer**
  - Inspect full report metadata (`reports` table). 【F:src/services/report_store_service.py†L16-L206】
- **Lock file status**
  - Read the ingest lock path and show whether it exists or is stale. Lock behavior is used during ingest orchestration. 【F:src/orchestrators/ingest_orchestrator.py†L44-L124】
- **Storage map**
  - Present output layout (`out/`, `cache/`, `state/`) from config and list key artifact folders (HTML, report_analysis, assets). 【F:src/config/app.yaml†L1-L45】

**Why this UI matters:** It makes storage and state explicit for troubleshooting.
=======
**Primary navigation (sidebar):**
1. **Cockpit Overview** — system health, current locks, recent runs
2. **Ingest Control** — Drive ingest pipeline control center
3. **Report Command Center** — report-centric inspection (all data + processing history)
4. **Analysis & Evidence** — vector-store evidence packs + artifacts
5. **Validation Center** — validation outputs + policy
6. **Publishing Control** — WordPress publish + category sync
7. **Category Manager** — taxonomy mappings + recategorize
8. **Cost & Usage** — spend + processing time graphs
9. **Logs & Live Terminal** — structured events + real-time terminal mirroring
10. **Settings & Prompts** — editable non-secret config + prompt registry
11. **System & Storage** — DB tables, locks, output folders

This layout groups actions by operational role and keeps the UI minimal: one dominant task per page with a clear “source of truth.”

---

## 1) Cockpit Overview (Admin Dashboard)

**Goal:** One-glance operational status.

**Core widgets (mapped to code/artifacts):**
- **Active run/last run summary**: show `run_id`, number of tasks, success/error count from log events (`run_id`, `task_id`, `event`).【F:src/utils/logging.py†L1-L112】
- **Recent reports**: latest entries from `reports` DB (title, publisher, HTML path, analysis mode).【F:src/services/report_store_service.py†L16-L206】
- **Ingest lock**: show lock file path and owner to confirm concurrency control (`ingest_lock_path`).【F:src/orchestrators/ingest_orchestrator.py†L44-L124】
- **Storage health**: status of `output_dir`, `cache_dir`, `state_db`, `reports_db` from config service (paths are created on load).【F:src/services/config_service.py†L120-L243】

**Admin value:** immediate visibility into current workload and system readiness.

---

## 2) Ingest Control (Google Drive → HTML)

**Goal:** A full operational console for ingest and evidence generation.

**Inputs & switches:**
- **Folder override** and **limit** (mapped to CLI `--folder` and `--limit`).【F:src/cli.py†L19-L101】
- **Read-only settings**: OpenAI model, temperature, timeout, batch limit, pdf text settings (from config).【F:src/services/config_service.py†L120-L243】
- **Mode display**: Single vector_store analysis; compare toggle is legacy/ignored. 【F:src/services/config_service.py†L145-L211】

**Pipeline timeline:**
- Stepper view showing:
  - Drive list → cache hit/miss → download → EOF check → skip check → report generation → state record.【F:src/orchestrators/ingest_orchestrator.py†L122-L314】
- Per-file status cards with:
  - `file_id`, md5, HTML output path, vector store id/status, evidence pack count.【F:src/orchestrators/ingest_orchestrator.py†L231-L314】

**Controls & safeguards:**
- **Run ingest** button triggers `run_ingest`.【F:src/orchestrators/ingest_orchestrator.py†L49-L119】
- If lock conflict is detected, display a blocking alert with the existing owner/ttl.【F:src/orchestrators/ingest_orchestrator.py†L61-L93】

**Admin value:** safe ingest execution with full pipeline transparency and artifact tracking.

---

## 3) Report Command Center (Report-Centric View)

**Goal:** A single report-focused workspace where an operator can select a report and see **all related data, processing info, and artifacts**.

**Core report selector:**
- Use the `reports` DB as the source of truth for selecting a report (title, file_id).【F:src/services/report_store_service.py†L16-L206】

**Report detail sections (all tied to persisted data):**
- **Metadata**: title, publisher, region, time period, taxonomy, categories, html_path, md5, analysis mode.【F:src/services/report_store_service.py†L207-L364】
- **Processing provenance**:
  - vector_store_id and evidence pack paths (for vector mode).【F:src/services/report_store_service.py†L207-L364】
  - state DB status including vector store indexing status and errors (if any).【F:src/services/state_service.py†L8-L120】
- **Artifacts panel**:
  - HTML output link/button (from `html_path`).【F:src/services/report_store_service.py†L207-L364】
  - Evidence packs JSON view (scope/methods/findings/limitations/quote candidates) via stored paths.【F:src/services/report_store_service.py†L207-L364】

**Admin value:** a true report-centric cockpit that answers “everything about this report” in one place.

---

## 4) Analysis & Evidence (Vector Store + Packs)

**Goal:** Inspect the evidence layer behind the report.

**Features:**
- **Vector store status**: show `vector_store_id`, `vector_store_status`, indexing timestamp from state DB.【F:src/services/state_service.py†L8-L120】
- **Evidence pack explorer**: open JSON from paths stored in metadata (`scope`, `methods`, `findings`, `limitations`, `quote_candidates`).【F:src/services/report_store_service.py†L207-L364】
- **Compare mode**: if enabled, show side-by-side outputs and pack paths for the two analysis modes.【F:src/services/config_service.py†L145-L211】

**Admin value:** QA and auditability of evidence and LLM reasoning inputs.

---

## 5) Validation Center

**Goal:** Ensure outputs meet validation policies and surface failures.

**Features:**
- **Validation policy panel**:
  - `ingest.validation.data_gap_policy` (warn/fail).【F:src/services/config_service.py†L108-L211】
  - `publish.validation.policy` (block/warn).【F:src/services/config_service.py†L300-L380】
- **Validation report viewer**:
  - Show validation JSON artifacts written during ingest (referenced in output directories). Orchestrator records outcomes alongside ingest results.【F:src/orchestrators/ingest_orchestrator.py†L231-L314】

**Admin value:** explicit confidence and compliance controls for output quality.

---

## 6) Publishing Control (WordPress)

**Goal:** Controlled publishing and category syncing.

**Features:**
- **Publish queue**: HTML files found under `OUTPUT_DIR`, with publish state from `state_db`.【F:src/services/state_service.py†L121-L229】
- **Publish action**: trigger `run_publish` (CLI `publish-wp`).【F:src/cli.py†L78-L135】
- **Settings summary**: site URL, username, post status, publish policy (read-only).【F:src/services/config_service.py†L300-L380】
- **Result table**: status and post URL for each published report (stored in state DB).【F:src/services/state_service.py†L121-L229】

**Admin value:** safe, auditable publishing with clear validation gating.

---

## 7) Category Manager (Taxonomy)

**Goal:** Manage and re-apply taxonomy mappings.

**Features:**
- **Mapping viewer**: render `src/config/category-mappings.yaml` categories/tags. Path is in config.【F:src/services/config_service.py†L104-L211】
- **Recategorize action**: trigger CLI `recategorize` to re-score all reports.【F:src/cli.py†L137-L178】
- **WP category sync**: trigger `update-wp-categories` to align WordPress taxonomy.【F:src/cli.py†L180-L216】

**Admin value:** keeps categorization consistent and aligned to latest mappings.

---

## 8) Cost & Usage (Spend + Processing Time)

**Goal:** Govern spend and performance with trend graphs.

**Features:**
- **Ledger explorer**: open `cost-ledger.jsonl` and rollups `cost-daily.json` from config.【F:src/config/app.yaml†L1-L45】
- **Cost report**: run by date or run_id (mirrors `cost-report` CLI).【F:src/cli.py†L218-L279】
- **Usage graphs** (daily/weekly/per report):
  - Spend per run/task and aggregated by day/week from the ledger file. The ledger entries provide the cost inputs for visualization (token usage + estimated cost).【F:src/services/cost_ledger_service.py†L1-L214】
- **Processing time per process**:
  - Use structured log event timestamps and run/task spans to compute elapsed time per step/run (log lines are timestamped and include `run_id`, `task_id`, `event`).【F:src/utils/logging.py†L63-L112】
- **Pricing table**: display `cost.pricing` for model rate awareness.【F:src/config/app.yaml†L33-L45】

**Admin value:** clear budget and performance monitoring with trend visibility.

---

## 9) Logs & Live Terminal (Observability)

**Goal:** Full observability console with **real-time terminal mirroring**.

**Features:**
- **Log file discovery**: list the current log file based on `MARKET_LENSE_LOG_DIR` and naming convention.【F:src/services/logging_service.py†L1-L47】
- **Structured log filters**: filter by `run_id`, `task_id`, `span_id`, `event`, `role`, `module`.【F:src/utils/logging.py†L63-L112】
- **Real-time terminal mirroring**:
  - Stream the running CLI process output (stdout/stderr) into a live panel so operators can see exactly “what is happening now.” The terminal output should match the same commands invoked by the UI actions (ingest/publish/etc.).【F:src/cli.py†L1-L279】
- **Redaction awareness**: show that sensitive data is redacted via `***REDACTED***` in structured log output.【F:src/utils/logging.py†L24-L79】

**Admin value:** true operational cockpit visibility while jobs are running.

---

## 10) Settings & Prompts (Editable, Non-Secret)

**Goal:** Allow operators to **adjust configuration and prompts** safely, without exposing secrets.

**Editable (non-secret) controls:**
- **Config editor** for `app.yaml`:
  - Update non-secret fields such as paths, ingest settings, analysis flags, model names, temperatures, and cost settings. The config file is the canonical source for these values.【F:src/config/app.yaml†L1-L45】
- **Model selection**:
  - Editable OpenAI model names (ingest + rank), temperatures, timeouts, and batch limits. These are already modeled in config and loaded by config service.【F:src/services/config_service.py†L72-L211】
- **Prompt editor**:
  - View/edit prompt YAML files under `src/prompts/**` with live SHA256 hash updates from prompt loading logic. Prompt content is read and hashed by `prompt_service`.【F:src/services/prompt_service.py†L21-L122】

**Not editable:**
- **Secrets** (OpenAI API keys, WP tokens, etc.) remain strictly in environment variables and are not exposed in UI. Config service loads these from env only.【F:src/services/config_service.py†L72-L211】

**Admin value:** safe configuration tuning and prompt iteration without leaking credentials.

---

## 11) System & Storage (Databases + Locks)

**Goal:** Provide direct visibility into the system’s state and file outputs.

**Features:**
- **State DB explorer**: show `processed` + `published` rows, including vector store status.【F:src/services/state_service.py†L16-L229】
- **Reports DB explorer**: show `reports` rows with metadata and analysis mode.【F:src/services/report_store_service.py†L16-L206】
- **Lock status**: display ingest lock path/owner to help resolve stuck runs.【F:src/orchestrators/ingest_orchestrator.py†L44-L124】
- **Storage map**: show `out/`, `cache/`, `state/` paths and core artifact subfolders.【F:src/config/app.yaml†L1-L45】

**Admin value:** clear operational control of persistence and concurrency.
>>>>>>> theirs

---

## Visual Design Principles (Simplicity-First)

<<<<<<< ours
- **Single column main content** with optional right-side “Details” panel for selected report/log entry.
- **Inline action buttons** only at natural decision points (Run ingest, Publish, Recategorize, Update WP categories, Generate Cost Report).
- **Minimal color**: use status chips (success/warn/error) to avoid noisy interfaces.
- **Progress clarity**: stepper view for ingest stages when a run is active.
- **No hidden state**: every page should show the underlying source of truth (DB, file, config).

---

## Data & Action Sources (Implementation Guide)
=======
- **One task per page**; sidebar navigation never overflows.
- **Primary actions top-right**: “Run ingest”, “Publish”, “Recategorize”, etc.
- **Minimal color**: status chips for success/warn/error.
- **Details panel** on the right: metadata + file paths for selected rows.
- **No hidden state**: always show the underlying source (DB, file, config).

---

## Data & Action Sources (Implementation Mapping)
>>>>>>> theirs

| UI Element | Source of Truth | Code Module |
| --- | --- | --- |
| Config values | `src/config/app.yaml` + env | `config_service.load_settings` / `load_publish_settings` |
| Ingest actions | Orchestrator | `run_ingest` in `ingest_orchestrator` |
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
<<<<<<< ours
- Overview
- Ingest
- Reports
- Analysis & Evidence
- Validation
- Publishing
- Categories
- Costs
- Logs
- Settings
- System

[Main]
- Title + status chip
- Contextual filters (date/run/file)
- Primary table or detail view
- Right panel (metadata + actions)
```

This architecture ensures **every feature in the codebase is surfaced**, every setting is visible, and every operational process is observable without adding non-existent functionality.
=======
- Cockpit Overview
- Ingest Control
- Report Command Center
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

This architecture upgrades the previous document into a **true admin and control cockpit**, while remaining strictly grounded in existing Market Lense capabilities, settings, databases, and logs.
>>>>>>> theirs
