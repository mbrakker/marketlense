# Market Lense Streamlit GUI Architecture

## Purpose
Design a Streamlit-based GUI that exposes **all capabilities already present** in the Market Lense codebase, while keeping the interface minimal, discoverable, and aligned with the system’s architecture: contracts → services → generators → orchestrators. This GUI is an operational console for ingest, review, validation, publishing, monitoring, and configuration.

The UI must make the current CLI workflows (`ingest`, `publish-wp`, `recategorize`, `update-wp-categories`, `cost-report`, `golden-set-vector`) feel like clear, guided flows with transparency into inputs, outputs, and logs. 【F:src/cli.py†L1-L279】

---

## Information Architecture (Navigation)

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
  - Show whether analysis is in `local_text` or `vector_store` mode; whether compare mode is enabled. These are loaded from config/env and passed into `IngestSettings`. 【F:src/services/config_service.py†L145-L211】

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

---

## Visual Design Principles (Simplicity-First)

- **Single column main content** with optional right-side “Details” panel for selected report/log entry.
- **Inline action buttons** only at natural decision points (Run ingest, Publish, Recategorize, Update WP categories, Generate Cost Report).
- **Minimal color**: use status chips (success/warn/error) to avoid noisy interfaces.
- **Progress clarity**: stepper view for ingest stages when a run is active.
- **No hidden state**: every page should show the underlying source of truth (DB, file, config).

---

## Data & Action Sources (Implementation Guide)

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
