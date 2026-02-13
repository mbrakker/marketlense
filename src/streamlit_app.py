from __future__ import annotations

import os
from html import escape
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import streamlit as st

from src.contracts.categories import CategoryMappingLoadRequest, RecategorizeRequest
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.costs import CostReportRequest, CostReportingRequest, CostRollupRequest
from src.contracts.cover_images import CoverImageOrchestratorRequest, CoverStyleLoadRequest
from src.contracts.files import FileStatRequest, ListDirectoryRequest, ReadTextRequest
from src.contracts.lock import LockGetRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.ops import OpsDashboardSnapshotRequest
from src.contracts.prompts import PromptNamespaceListRequest
from src.contracts.publish import PublishQueueRequest
from src.contracts.report_store import ReportMetadataListRequest
from src.contracts.state import (
    StateGetRequest,
    StateProcessedListRequest,
    StatePublishedListRequest,
)
from src.orchestrators.candidate_extraction_orchestrator import run_candidate_extraction
from src.orchestrators.cover_image_orchestrator import run_cover_image_generation
from src.orchestrators.cost_reporting_orchestrator import run_cost_reporting
from src.orchestrators.ingest_orchestrator import run_ingest
from src.orchestrators.ops_dashboard_orchestrator import collect_ops_dashboard_snapshot
from src.orchestrators.publish_orchestrator import run_publish
from src.orchestrators.publish_queue_orchestrator import build_publish_queue_snapshot
from src.orchestrators.recategorize_orchestrator import run_recategorize
from src.orchestrators.wp_category_update_orchestrator import run_update_wp_categories
from src.services.category_mapping_service import load_mappings
from src.services.config_service import build_ingest_settings, load_publish_settings, load_settings
from src.services.cover_style_service import load_cover_styles
from src.services.file_service import file_stat, list_directory, read_text
from src.services.lock_service import get_lock
from src.services.logging_service import DEFAULT_LOG_DIR, LOG_DIR_ENV, LOG_FILE_PREFIX, setup_logging
from src.services.prompt_service import list_prompt_namespaces
from src.services.report_store_service import list_metadata
from src.services.state_service import get as get_state
from src.services.state_service import list_processed, list_published
from src.utils.errors import AppError
from src.utils.gui_utils import (
    compute_task_duration_rollups,
    extract_log_date_from_filename,
    filter_log_events,
    parse_structured_log_line,
    safe_json_loads,
    status_chip_level,
)
from src.utils.logging import new_run_context
from src.utils.slugify import slugify


NAV_SECTIONS = [
    "Cockpit Overview",
    "Ingest Control",
    "Candidate Extraction",
    "Report Command Center",
    "Cover Images",
    "Analysis & Evidence",
    "Validation Center",
    "Publishing Control",
    "Category Manager",
    "Cost & Usage",
    "Logs & Live Terminal",
    "Settings & Prompts",
    "System & Storage",
    "Developer & Test Tools",
]

INGEST_STEPS = [
    "Drive list",
    "Cache hit/miss",
    "Download",
    "EOF check",
    "Skip check",
    "Report generation",
    "State record",
    "Cover image",
]

CANDIDATE_STEPS = [
    "Drive list",
    "Cache hit/miss",
    "Download",
    "EOF check",
    "Candidate pack generation",
]


def _ctx(task_id: str) -> Any:
    return new_run_context(task_id=f"gui:{task_id}")


def _to_dicts(items: Iterable[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if is_dataclass(item):
            rows.append(asdict(item))
        elif isinstance(item, dict):
            rows.append(item)
    return rows


def _chip_html(label: str, level: str, *, tooltip: str | None = None) -> str:
    tip = tooltip or _tip(
        "Status indicator for the current view.",
        f"If it shows '{label}', use that state to decide whether to run the page action.",
    )
    return f'<span class="status-chip status-{level}" title="{escape(tip)}">{label}</span>'


def _tip(description: str, example: str = "") -> str:
    text = description.strip()
    if example.strip():
        text = f"{text} Example: {example.strip()}"
    return text[:1000]


def _inject_theme() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Sora:wght@600;700&display=swap');

:root {
  --ml-bg: #f6f7f5;
  --ml-card: #ffffff;
  --ml-border: #d6ddd9;
  --ml-text: #151f1b;
  --ml-muted: #5b6761;
  --ml-accent: #0d8a6a;
  --ml-success: #0f7d45;
  --ml-warn: #bd7a12;
  --ml-error: #c93a3a;
  --ml-shadow: 0 10px 32px rgba(15, 27, 20, 0.08);
}

html, body, [class*="css"] {
  font-family: "Manrope", "Segoe UI", sans-serif;
}

[data-testid="stAppViewContainer"] {
  background: radial-gradient(circle at 0% 0%, #ecf4ef 0%, var(--ml-bg) 45%, #f5f6f4 100%);
}

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #10291f 0%, #16372b 100%);
  border-right: 1px solid rgba(255,255,255,0.08);
}

[data-testid="stSidebar"] * {
  color: #f2f6f3 !important;
  font-family: "Manrope", sans-serif !important;
}

[data-testid="stMain"] h1,
[data-testid="stMain"] h2,
[data-testid="stMain"] h3,
[data-testid="stMain"] h4,
[data-testid="stMain"] h5,
[data-testid="stMain"] h6,
[data-testid="stMain"] p,
[data-testid="stMain"] li,
[data-testid="stMain"] label,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] {
  color: var(--ml-text) !important;
}

[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] * {
  color: #000000 !important;
}

[data-testid="stMain"] [data-testid="stWidgetLabel"] *,
[data-testid="stMain"] .stSelectbox label,
[data-testid="stMain"] .stTextInput label,
[data-testid="stMain"] .stNumberInput label,
[data-testid="stMain"] .stDateInput label,
[data-testid="stMain"] .stMultiSelect label {
  color: var(--ml-text) !important;
}

[data-testid="stMain"] .stButton > button,
[data-testid="stMain"] [data-testid="baseButton-secondary"],
[data-testid="stMain"] [data-testid="baseButton-primary"] {
  background: #d7ecff !important;
  color: #06284c !important;
  border: 1px solid #8fbbe7 !important;
}

[data-testid="stMain"] .stButton > button:hover,
[data-testid="stMain"] [data-testid="baseButton-secondary"]:hover,
[data-testid="stMain"] [data-testid="baseButton-primary"]:hover {
  background: #c2e2ff !important;
  border-color: #74a9de !important;
}

[data-testid="stMain"] .stButton > button:active,
[data-testid="stMain"] [data-testid="baseButton-secondary"]:active,
[data-testid="stMain"] [data-testid="baseButton-primary"]:active {
  background: #b1d9ff !important;
}

.ml-page-title {
  font-family: "Sora", "Manrope", sans-serif;
  font-size: 2rem;
  margin-bottom: 0.35rem;
  color: var(--ml-text);
}

.status-chip {
  display: inline-block;
  border-radius: 999px;
  padding: 0.2rem 0.65rem;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  border: 1px solid transparent;
}

.status-success {
  color: var(--ml-success);
  background: rgba(15,125,69,0.12);
  border-color: rgba(15,125,69,0.2);
}

.status-warn {
  color: var(--ml-warn);
  background: rgba(189,122,18,0.12);
  border-color: rgba(189,122,18,0.2);
}

.status-error {
  color: var(--ml-error);
  background: rgba(201,58,58,0.12);
  border-color: rgba(201,58,58,0.2);
}

.status-info {
  color: #116f8f;
  background: rgba(17,111,143,0.12);
  border-color: rgba(17,111,143,0.2);
}

.ml-note {
  color: var(--ml-muted);
  font-size: 0.88rem;
}

.ml-stepper {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(126px, 1fr));
  gap: 0.45rem;
  margin: 0.5rem 0 0.8rem;
}

.ml-step {
  border-radius: 0.7rem;
  border: 1px solid var(--ml-border);
  background: var(--ml-card);
  box-shadow: var(--ml-shadow);
  padding: 0.45rem 0.55rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--ml-muted);
}

.ml-step-done {
  color: var(--ml-success);
  border-color: rgba(15,125,69,0.25);
}

.ml-step-active {
  color: var(--ml-accent);
  border-color: rgba(13,138,106,0.3);
}

.ml-step-error {
  color: var(--ml-error);
  border-color: rgba(201,58,58,0.3);
}

.ml-terminal {
  border-radius: 0.8rem;
  border: 1px solid #1b2b24;
  background: #0e1613;
  color: #ceefe1;
  font-family: "Courier New", monospace;
  font-size: 0.84rem;
  padding: 0.75rem;
  min-height: 260px;
  max-height: 420px;
  overflow: auto;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _page_shell(
    title: str,
    *,
    status_label: str,
    status_level: str,
    primary_action: str | None = None,
    primary_help: str = "",
    primary_key: str = "",
    primary_disabled: bool = False,
) -> tuple[bool, Any, Any, Any]:
    left, right = st.columns([7, 1], gap="large")
    with left:
        st.markdown(f'<div class="ml-page-title">{title}</div>', unsafe_allow_html=True)
        st.markdown(_chip_html(status_label, status_level), unsafe_allow_html=True)
    clicked = False
    with right:
        if primary_action:
            clicked = st.button(
                primary_action,
                key=primary_key,
                use_container_width=True,
                disabled=primary_disabled,
                help=primary_help[:1000] if primary_help else None,
            )
    filters_container = st.container()
    main_col, detail_col = st.columns([3.4, 1.6], gap="large")
    return clicked, filters_container, main_col, detail_col


def _render_stepper(steps: list[str], done_count: int = 0, *, active_index: Optional[int] = None, error_index: Optional[int] = None) -> None:
    parts: list[str] = ['<div class="ml-stepper">']
    for idx, step in enumerate(steps):
        cls = "ml-step"
        if error_index is not None and idx == error_index:
            cls += " ml-step-error"
        elif idx < done_count:
            cls += " ml-step-done"
        elif active_index is not None and idx == active_index:
            cls += " ml-step-active"
        tip = _tip("Pipeline step in the current run sequence.", f"Step {idx + 1}: {step}.")
        parts.append(f'<div class="{cls}" title="{escape(tip)}">{step}</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def _try_load_settings() -> tuple[Any | None, str | None]:
    try:
        settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), _ctx("load_settings"))
    except Exception as exc:  # pragma: no cover - runtime safeguard for UI
        return None, str(exc)
    return settings, None


def _try_load_publish_settings() -> tuple[Any | None, str | None]:
    try:
        settings = load_publish_settings(ConfigLoadRequest(schema_version="1.0", path=""), _ctx("load_publish_settings"))
    except Exception as exc:  # pragma: no cover - runtime safeguard for UI
        return None, str(exc)
    return settings, None


def _discover_log_files() -> list[dict[str, Any]]:
    log_dir = os.getenv(LOG_DIR_ENV, DEFAULT_LOG_DIR)
    try:
        response = list_directory(
            ListDirectoryRequest(
                schema_version="1.0",
                root_dir=log_dir,
                glob_pattern=f"{LOG_FILE_PREFIX}_*.log",
                recursive=False,
                include_files=True,
                include_dirs=False,
                limit=100,
            ),
            _ctx("list_logs"),
        )
    except AppError:
        return []
    rows = _to_dicts(response.entries)
    rows.sort(key=lambda row: float(row.get("mtime_utc") or 0.0), reverse=True)
    return rows


def _load_log_events(log_paths: list[str], *, max_lines_per_file: int = 5000) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in log_paths:
        try:
            text = read_text(ReadTextRequest(schema_version="1.0", path=path), _ctx("read_log")).content
        except AppError:
            continue
        log_date = extract_log_date_from_filename(path)
        lines = text.splitlines()
        for line in lines[-max_lines_per_file:]:
            event = parse_structured_log_line(line, log_date=log_date)
            if not event:
                continue
            event["log_path"] = path
            events.append(event)
    events.sort(key=lambda row: str(row.get("timestamp_utc") or row.get("timestamp_hms") or ""))
    return events


def _read_json(path: str) -> dict[str, Any] | list[Any] | None:
    try:
        payload = read_text(ReadTextRequest(schema_version="1.0", path=path), _ctx("read_json")).content
    except AppError:
        return None
    return safe_json_loads(payload)


def _append_terminal(message: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    previous = st.session_state.get("live_terminal_output", "")
    st.session_state["live_terminal_output"] = f"{previous}[{now}] {message}\n"


def _render_terminal_panel() -> None:
    terminal_text = st.session_state.get("live_terminal_output", "")
    if not terminal_text.strip():
        terminal_text = "No run output captured yet."
    st.markdown(f'<pre class="ml-terminal">{terminal_text}</pre>', unsafe_allow_html=True)


def _as_utc(ts: int | float | None) -> str:
    if ts is None:
        return ""
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return ""


def _storage_health(settings: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    targets = [
        ("output_dir", settings.output_dir),
        ("cache_dir", settings.cache_dir),
        ("state_db", settings.state_db),
        ("reports_db", settings.reports_db),
    ]
    for label, path in targets:
        try:
            stat = file_stat(FileStatRequest(schema_version="1.0", path=path), _ctx(f"stat:{label}"))
            rows.append({
                "name": label,
                "path": path,
                "exists": stat.exists,
                "size_bytes": stat.size_bytes,
                "modified_utc": _as_utc(stat.mtime_utc),
            })
        except AppError as exc:
            rows.append({
                "name": label,
                "path": path,
                "exists": False,
                "size_bytes": None,
                "modified_utc": "",
                "error": exc.message,
            })
    return rows


def _recent_validation_files(output_dir: str) -> list[dict[str, Any]]:
    try:
        response = list_directory(
            ListDirectoryRequest(
                schema_version="1.0",
                root_dir=output_dir,
                glob_pattern="validation*.json",
                recursive=True,
                include_files=True,
                include_dirs=False,
                limit=500,
            ),
            _ctx("list_validation"),
        )
    except AppError:
        return []
    return _to_dicts(response.entries)


def _load_report_rows(settings: Any) -> list[dict[str, Any]]:
    reports_resp = list_metadata(
        ReportMetadataListRequest(schema_version="1.1", db_path=settings.reports_db),
        _ctx("list_reports"),
    )
    rows = _to_dicts(reports_resp.records)
    rows.sort(key=lambda row: int(row.get("updated_at") or 0), reverse=True)
    return rows


def _load_processed_rows(settings: Any) -> list[dict[str, Any]]:
    processed_resp = list_processed(
        StateProcessedListRequest(schema_version="1.0", state_db=settings.state_db, limit=1000),
        _ctx("list_processed"),
    )
    return _to_dicts(processed_resp.rows)


def _load_published_rows(settings: Any) -> list[dict[str, Any]]:
    published_resp = list_published(
        StatePublishedListRequest(schema_version="1.0", state_db=settings.state_db, limit=1000),
        _ctx("list_published"),
    )
    return _to_dicts(published_resp.rows)


def _lock_snapshot(lock_path: str) -> dict[str, Any]:
    try:
        lock = get_lock(LockGetRequest(schema_version="1.0", lock_path=lock_path), _ctx("get_lock"))
    except AppError as exc:
        return {"found": False, "error": exc.message}
    row = {"found": lock.found}
    if lock.lock:
        row.update(asdict(lock.lock))
    return row


def _render_cockpit_overview(settings: Any) -> None:
    snapshot = collect_ops_dashboard_snapshot(
        OpsDashboardSnapshotRequest(
            schema_version="1.0",
            output_dir=settings.output_dir,
            cache_dir=settings.cache_dir,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            ingest_lock_path=settings.ingest_lock_path,
        ),
        _ctx("ops_snapshot"),
    )
    reports = snapshot.reports
    processed = snapshot.processed
    published = snapshot.published
    lock = asdict(snapshot.lock)
    health = [asdict(item) for item in snapshot.storage_health]
    logs = _discover_log_files()
    recent_paths = [row["path"] for row in logs[:2]]
    events = _load_log_events(recent_paths)

    status_level = "warn" if lock.get("found") else "success"
    clicked, filters, main_col, detail_col = _page_shell(
        "Cockpit Overview",
        status_label="Lock Active" if lock.get("found") else "System Ready",
        status_level=status_level,
        primary_action="Refresh",
        primary_help=_tip(
            "Reload dashboard metrics from reports DB, state DB, lock file, and latest logs.",
            "Use after an ingest or publish run to view updated counts.",
        ),
        primary_key="overview_refresh",
    )
    if clicked:
        st.rerun()

    with filters:
        st.caption("One-glance health for current lock, storage, run signals, and report inventory.")

    with main_col:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Reports", f"{len(reports)}")
        m2.metric("Processed", f"{len(processed)}")
        m3.metric("Published", f"{len(published)}")
        m4.metric("Recent Log Events", f"{len(events)}")
        st.subheader("Recent Reports")
        if reports:
            table = []
            for row in reports[:20]:
                table.append({
                    "title": row.get("title"),
                    "publisher": row.get("publisher"),
                    "analysis_mode": row.get("analysis_mode"),
                    "html_path": row.get("html_path"),
                    "updated_at_utc": _as_utc(row.get("updated_at")),
                })
            st.dataframe(table, use_container_width=True, hide_index=True)
        else:
            st.info("No report metadata records found.")

    with detail_col:
        st.subheader("System Health")
        st.dataframe(health, use_container_width=True, hide_index=True)
        st.subheader("Ingest Lock")
        if lock.get("found"):
            st.error(f"Locked by `{lock.get('owner_id')}` (pid={lock.get('pid')})")
        else:
            st.success("No active ingest lock.")
        if logs:
            st.subheader("Log Files")
            st.dataframe(
                [{"path": row["path"], "modified_utc": _as_utc(row.get("mtime_utc"))} for row in logs[:8]],
                use_container_width=True,
                hide_index=True,
            )


def _render_ingest_control(settings: Any) -> None:
    lock = _lock_snapshot(settings.ingest_lock_path)
    status_level = "warn" if lock.get("found") else "info"
    clicked, filters, main_col, detail_col = _page_shell(
        "Ingest Control",
        status_label="Lock Conflict" if lock.get("found") else "Ready to Run",
        status_level=status_level,
        primary_action="Run Ingest",
        primary_help=_tip(
            "Run the ingest orchestrator with the current controls.",
            "Set folder override and limit, then click to process a bounded batch.",
        ),
        primary_key="run_ingest",
        primary_disabled=False,
    )

    with filters:
        c1, c2 = st.columns(2)
        with c1:
            folder_override = st.text_input(
                "Folder Override",
                value="",
                placeholder="Optional Drive folder ID",
                help=_tip(
                    "Optional Google Drive folder ID that overrides the default ingest folder.",
                    "Paste a folder ID to run ingest on a specific collection.",
                ),
            )
        with c2:
            limit = st.number_input(
                "Limit",
                min_value=1,
                max_value=1000,
                value=int(settings.batch_limit),
                step=1,
                help=_tip(
                    "Maximum number of PDFs to ingest in this run.",
                    "Use 10 for a quick smoke test before full ingest.",
                ),
            )
        st.caption(
            f"Model `{settings.openai_model}` | temperature `{settings.temperature}` | timeout `{settings.openai_timeout_seconds}`s | compare `{settings.analysis_compare}`"
        )

    if clicked:
        _append_terminal("Ingest requested from UI.")
        try:
            outcomes = run_ingest(
                build_ingest_settings(
                    IngestSettingsBuildRequest(schema_version="1.0", app_settings=settings),
                    _ctx("build_ingest_settings"),
                ),
                folder_id=folder_override.strip() or None,
                limit=int(limit),
                ctx=_ctx("run_ingest"),
            )
            st.session_state["last_ingest_outcomes"] = outcomes
            processed_count = len([o for o in outcomes if o.status == "processed"])
            _append_terminal(f"Ingest complete. processed={processed_count} total={len(outcomes)}")
            st.success(f"Ingest completed with {processed_count} processed file(s).")
        except Exception as exc:
            _append_terminal(f"Ingest failed: {exc}")
            st.error(str(exc))

    outcomes = st.session_state.get("last_ingest_outcomes", [])
    done_count = len(INGEST_STEPS) if outcomes else 0
    has_errors = any(getattr(item, "status", "") == "error" for item in outcomes)

    with main_col:
        st.subheader("Pipeline Stepper")
        _render_stepper(INGEST_STEPS, done_count=done_count, error_index=(len(INGEST_STEPS) - 1 if has_errors else None))
        if outcomes:
            st.subheader("Ingest Outcomes")
            st.dataframe(_to_dicts(outcomes), use_container_width=True, hide_index=True)
        else:
            st.info("No ingest run executed in this session yet.")

    with detail_col:
        st.subheader("Lock & Config")
        if lock.get("found"):
            st.error(
                f"Conflict on `{settings.ingest_lock_path}` owner=`{lock.get('owner_id')}` pid=`{lock.get('pid')}`"
            )
        else:
            st.success("No lock conflict detected.")
        st.json(
            {
                "openai_model": settings.openai_model,
                "temperature": settings.temperature,
                "timeout_seconds": settings.openai_timeout_seconds,
                "batch_limit": settings.batch_limit,
                "analysis_mode": settings.analysis_mode,
                "analysis_compare": settings.analysis_compare,
            }
        )


def _render_candidate_extraction(settings: Any) -> None:
    clicked, filters, main_col, detail_col = _page_shell(
        "Candidate Extraction",
        status_label="Ready",
        status_level="info",
        primary_action="Run Extraction",
        primary_help=_tip(
            "Run candidate extraction for selected reports or a local PDF.",
            "Provide file_id for a single file or keep it empty to process by limit.",
        ),
        primary_key="run_candidates",
    )

    with filters:
        c1, c2, c3 = st.columns(3)
        with c1:
            folder_override = st.text_input(
                "Folder Override",
                value="",
                key="cand_folder",
                help=_tip(
                    "Optional Drive folder ID for candidate extraction scope.",
                    "Set this to extract from a folder different from default ingest settings.",
                ),
            )
        with c2:
            limit = st.number_input(
                "Limit",
                min_value=1,
                max_value=1000,
                value=5,
                key="cand_limit",
                help=_tip(
                    "Maximum number of items to process in candidate extraction.",
                    "Use 1 when validating extraction output for a single report.",
                ),
            )
        with c3:
            file_id = st.text_input(
                "file_id (optional)",
                value="",
                key="cand_file_id",
                help=_tip(
                    "Optional file_id filter for extracting one known document.",
                    "Paste a Drive file_id to bypass folder scanning.",
                ),
            )
        c4, c5 = st.columns(2)
        with c4:
            local_pdf = st.text_input(
                "Local PDF Path (optional)",
                value="",
                key="cand_local_pdf",
                help=_tip(
                    "Local PDF path for direct extraction without Drive lookup.",
                    r"Example path: C:\reports\sample.pdf",
                ),
            )
        with c5:
            report_id = st.text_input(
                "report_id override (optional)",
                value="",
                key="cand_report_id",
                help=_tip(
                    "Optional report_id override used when processing a local PDF.",
                    "Set report_id='my-test-report' for deterministic artifact paths.",
                ),
            )

    if clicked:
        _append_terminal("Candidate extraction requested from UI.")
        try:
            outcomes = run_candidate_extraction(
                build_ingest_settings(
                    IngestSettingsBuildRequest(schema_version="1.0", app_settings=settings),
                    _ctx("build_ingest_settings"),
                ),
                folder_id=folder_override.strip() or None,
                limit=int(limit),
                file_id=file_id.strip() or None,
                pdf_path=local_pdf.strip() or None,
                report_id=report_id.strip() or None,
                ctx=_ctx("run_candidates"),
            )
            st.session_state["last_candidate_outcomes"] = outcomes
            _append_terminal(f"Candidate extraction complete. outputs={len(outcomes)}")
            st.success(f"Candidate extraction complete for {len(outcomes)} item(s).")
        except Exception as exc:
            _append_terminal(f"Candidate extraction failed: {exc}")
            st.error(str(exc))

    outcomes = st.session_state.get("last_candidate_outcomes", [])
    with main_col:
        st.subheader("Pipeline Stepper")
        _render_stepper(CANDIDATE_STEPS, done_count=(len(CANDIDATE_STEPS) if outcomes else 0))
        if outcomes:
            st.subheader("Extraction Outcomes")
            st.dataframe(_to_dicts(outcomes), use_container_width=True, hide_index=True)
        else:
            st.info("No extraction run executed in this session yet.")

    with detail_col:
        st.subheader("Asset Viewer")
        if not outcomes:
            st.caption("Run extraction to inspect `candidates.json` and crops.")
            return
        labels = [f"{item.report_id} | {item.report_name}" for item in outcomes]
        selected = st.selectbox(
            "Select outcome",
            options=list(range(len(labels))),
            format_func=lambda idx: labels[idx],
            help=_tip(
                "Select an extraction outcome to inspect candidates JSON and generated crops.",
                "Choose the latest report to review candidate quality.",
            ),
        )
        outcome = outcomes[selected]
        parsed = _read_json(outcome.candidates_path) if outcome.candidates_path else None
        if parsed is not None:
            st.json(parsed)
        if outcome.crop_paths:
            st.caption(f"Crops ({len(outcome.crop_paths)})")
            for crop_path in outcome.crop_paths[:8]:
                candidate_path = Path(crop_path)
                if candidate_path.exists():
                    st.image(str(candidate_path), use_container_width=True)


def _render_report_command_center(settings: Any) -> None:
    clicked, filters, main_col, detail_col = _page_shell(
        "Report Command Center",
        status_label="Report Hub",
        status_level="info",
        primary_action="Refresh Catalog",
        primary_help=_tip(
            "Reload report metadata and refresh the report selector.",
            "Use after ingest, recategorize, or cover generation to pick up new records.",
        ),
        primary_key="refresh_reports_center",
    )
    if clicked:
        st.rerun()
    reports = _load_report_rows(settings)
    with filters:
        st.caption("Select one report from the metadata DB and inspect provenance, evidence packs, and cover assets.")
    with main_col:
        if not reports:
            st.warning("No reports found in the reports DB.")
            return
        labels = [f"{row['title']} ({row['file_id']})" for row in reports]
        selected_idx = st.selectbox(
            "Report",
            options=list(range(len(labels))),
            format_func=lambda idx: labels[idx],
            help=_tip(
                "Select a report metadata row for detailed provenance and artifact review.",
                "Pick the most recent title to inspect its latest evidence packs.",
            ),
        )
        report = reports[selected_idx]
        st.dataframe(
            [{
                "file_id": report.get("file_id"),
                "title": report.get("title"),
                "publisher": report.get("publisher"),
                "analysis_mode": report.get("analysis_mode"),
                "vector_store_id": report.get("vector_store_id"),
                "html_path": report.get("html_path"),
                "updated_at_utc": _as_utc(report.get("updated_at")),
            }],
            use_container_width=True,
            hide_index=True,
        )
        st.subheader("Evidence Pack Paths")
        evidence_paths = report.get("evidence_pack_paths") or {}
        if evidence_paths:
            st.dataframe(
                [{"pack": name, "path": path} for name, path in evidence_paths.items()],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No evidence packs recorded for this report.")

    with detail_col:
        if not reports:
            return
        report = reports[selected_idx]
        st.subheader("Metadata")
        st.json(
            {
                "file_id": report.get("file_id"),
                "title": report.get("title"),
                "publisher": report.get("publisher"),
                "region": report.get("region"),
                "time_period": report.get("time_period"),
                "taxonomy": report.get("taxonomy"),
                "categories": report.get("categories"),
                "html_path": report.get("html_path"),
                "md5": report.get("md5"),
                "analysis_mode": report.get("analysis_mode"),
            }
        )
        st.subheader("Provenance")
        state_row = get_state(
            StateGetRequest(schema_version="1.0", state_db=settings.state_db, file_id=report.get("file_id")),
            _ctx("report_center_state"),
        )
        if state_row:
            st.json(asdict(state_row))
        else:
            st.caption("No matching state record.")
        st.subheader("Artifacts")
        html_path = str(report.get("html_path") or "").strip()
        if html_path:
            st.code(html_path)
        publisher = str(report.get("publisher") or "").strip()
        title = str(report.get("title") or "").strip()
        if title:
            cover_path = Path(settings.output_dir) / slugify(f"{title}.pdf") / "assets" / f"{slugify(f'{publisher} {title}')}.png"
            if cover_path.exists():
                st.image(str(cover_path), caption="Cover preview", use_container_width=True)


def _render_cover_images(settings: Any) -> None:
    clicked, filters, main_col, detail_col = _page_shell(
        "Cover Images",
        status_label="Ready",
        status_level="info",
        primary_action="Generate Covers",
        primary_help=_tip(
            "Generate cover PNG assets from report metadata using the selected style config.",
            "Set limit=10 for a small batch, or specify file_id to regenerate one cover.",
        ),
        primary_key="generate_covers",
    )
    with filters:
        c1, c2, c3 = st.columns(3)
        with c1:
            style_path = st.text_input(
                "Style Config Path",
                value=settings.cover_style_path,
                help=_tip(
                    "Path to cover style YAML used for rendering cover images.",
                    "Point to a custom style file to test alternate branding.",
                ),
            )
        with c2:
            limit = st.number_input(
                "Limit",
                min_value=1,
                max_value=2000,
                value=10,
                help=_tip(
                    "Maximum number of report covers to generate in this run.",
                    "Use 5 for quick verification during style tuning.",
                ),
            )
        with c3:
            file_id = st.text_input(
                "file_id (optional)",
                value="",
                help=_tip(
                    "Optional single report file_id to generate one cover only.",
                    "Paste file_id to regenerate a failed cover asset.",
                ),
            )
        st.caption(f"Source of truth style config: `{settings.cover_style_path}`")

    if clicked:
        _append_terminal("Cover generation requested from UI.")
        try:
            outcomes = run_cover_image_generation(
                CoverImageOrchestratorRequest(
                    schema_version="1.0",
                    reports_db=settings.reports_db,
                    output_dir=settings.output_dir,
                    style_config_path=style_path.strip(),
                    limit=int(limit),
                    file_id=file_id.strip() or None,
                ),
                ctx=_ctx("run_covers"),
            )
            st.session_state["last_cover_outcomes"] = outcomes
            _append_terminal(f"Cover generation complete. outcomes={len(outcomes)}")
            st.success(f"Cover generation completed for {len(outcomes)} report(s).")
        except Exception as exc:
            _append_terminal(f"Cover generation failed: {exc}")
            st.error(str(exc))

    outcomes = st.session_state.get("last_cover_outcomes", [])
    with main_col:
        try:
            style_config = load_cover_styles(
                request=CoverStyleLoadRequest(schema_version="1.0", path=style_path.strip()),
                ctx=_ctx("load_cover_style"),
            )
            st.subheader("Style Summary")
            st.json(
                {
                    "layout": asdict(style_config.config.layout),
                    "categories": sorted(list(style_config.config.categories.keys())),
                }
            )
        except Exception as exc:
            st.warning(f"Unable to load style config: {exc}")
        if outcomes:
            st.subheader("Generation Outcomes")
            st.dataframe(_to_dicts(outcomes), use_container_width=True, hide_index=True)
        else:
            st.info("No cover generation run executed in this session yet.")

    with detail_col:
        st.subheader("Asset Viewer")
        generated = [item for item in outcomes if getattr(item, "output_path", None)]
        if not generated:
            st.caption("No generated assets yet.")
            return
        labels = [f"{item.file_id} | {item.title}" for item in generated]
        selected = st.selectbox(
            "Select output",
            options=list(range(len(labels))),
            format_func=lambda idx: labels[idx],
            help=_tip(
                "Select a generated cover output to preview the PNG artifact.",
                "Pick a report with recent style updates to validate rendering.",
            ),
        )
        selected_outcome = generated[selected]
        if selected_outcome.output_path:
            st.code(selected_outcome.output_path)
            if Path(selected_outcome.output_path).exists():
                st.image(selected_outcome.output_path, use_container_width=True)


def _render_analysis_and_evidence(settings: Any) -> None:
    clicked, filters, main_col, detail_col = _page_shell(
        "Analysis & Evidence",
        status_label="Vector Store",
        status_level="info",
        primary_action="Refresh Status",
        primary_help=_tip(
            "Refresh vector-store and evidence-pack status for the selected report.",
            "Run after indexing to confirm vector_store_status and artifact paths.",
        ),
        primary_key="analysis_refresh",
    )
    if clicked:
        st.rerun()
    reports = _load_report_rows(settings)
    with filters:
        st.caption("Inspect vector store indexing status and evidence packs backing a report.")
    if not reports:
        st.warning("No report metadata available.")
        return
    labels = [f"{row['title']} ({row['file_id']})" for row in reports]
    selected_idx = st.selectbox(
        "Report",
        options=list(range(len(labels))),
        format_func=lambda idx: labels[idx],
        help=_tip(
            "Choose which report to inspect for vector indexing and evidence packs.",
            "Select a report that recently completed ingest to confirm indexing status.",
        ),
    )
    report = reports[selected_idx]
    state_row = get_state(
        StateGetRequest(schema_version="1.0", state_db=settings.state_db, file_id=report["file_id"]),
        _ctx("analysis_state"),
    )
    evidence_paths = report.get("evidence_pack_paths") or {}

    with main_col:
        st.subheader("Vector Store Status")
        st.dataframe(
            [{
                "file_id": report.get("file_id"),
                "vector_store_id": report.get("vector_store_id") or (getattr(state_row, "vector_store_id", None) if state_row else None),
                "vector_store_status": getattr(state_row, "vector_store_status", None) if state_row else None,
                "indexed_at_utc": getattr(state_row, "indexed_at_utc", None) if state_row else None,
                "last_error": getattr(state_row, "last_error", None) if state_row else None,
            }],
            use_container_width=True,
            hide_index=True,
        )
        st.subheader("Evidence Pack Explorer")
        if evidence_paths:
            selected_pack = st.selectbox(
                "Pack",
                options=list(evidence_paths.keys()),
                help=_tip(
                    "Pick an evidence pack to inspect its JSON payload.",
                    "Open the 'summary' or 'claims' pack to verify extracted evidence.",
                ),
            )
            selected_path = evidence_paths[selected_pack]
            st.code(selected_path)
            payload = _read_json(selected_path)
            if payload is not None:
                st.json(payload)
            else:
                st.warning("Unable to parse selected pack JSON.")
        else:
            st.info("No evidence packs recorded for this report.")

    with detail_col:
        st.subheader("Compare Mode")
        if settings.analysis_compare:
            st.success("Compare mode is enabled.")
        else:
            st.info("Compare mode is disabled in settings (`analysis.compare=false`).")
        if state_row:
            st.subheader("State Snapshot")
            st.json(asdict(state_row))


def _render_validation_center(settings: Any, publish_settings: Any | None, publish_error: str | None) -> None:
    clicked, filters, main_col, detail_col = _page_shell(
        "Validation Center",
        status_label="Policy View",
        status_level="info",
        primary_action="Refresh Reports",
        primary_help=_tip(
            "Reload validation artifacts and compliance callouts from output storage.",
            "Use after running validation or publishing policy checks.",
        ),
        primary_key="validation_refresh",
    )
    if clicked:
        st.rerun()
    with filters:
        st.caption("Validation policy and artifact compliance status across reports.")
    files = _recent_validation_files(settings.output_dir)
    rows: list[dict[str, Any]] = []
    for row in files[:200]:
        payload = _read_json(row["path"])
        status = payload.get("status") if isinstance(payload, dict) else ""
        severity = payload.get("severity") if isinstance(payload, dict) else ""
        rows.append(
            {
                "path": row["path"],
                "status": status,
                "severity": severity,
                "chip_level": status_chip_level(str(severity or status)),
                "modified_utc": _as_utc(row.get("mtime_utc")),
            }
        )
    with main_col:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(_chip_html(f"data_gap_policy={settings.validation_data_gap_policy}", status_chip_level(settings.validation_data_gap_policy)), unsafe_allow_html=True)
        with c2:
            if publish_settings:
                st.markdown(_chip_html(f"publish_policy={publish_settings.validation_policy}", status_chip_level(publish_settings.validation_policy)), unsafe_allow_html=True)
            else:
                st.markdown(_chip_html("publish_policy=unavailable", "warn"), unsafe_allow_html=True)
        st.subheader("Validation Artifacts")
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("No validation artifacts found.")

    with detail_col:
        st.subheader("Compliance Callouts")
        total = len(rows)
        red = len([r for r in rows if r["chip_level"] == "error"])
        yellow = len([r for r in rows if r["chip_level"] == "warn"])
        green = len([r for r in rows if r["chip_level"] == "success"])
        st.metric("Green", green)
        st.metric("Yellow", yellow)
        st.metric("Red", red)
        st.metric("Total", total)
        if publish_error:
            st.caption(f"Publish settings unavailable: {publish_error}")


def _render_publishing_control(settings: Any, publish_settings: Any | None, publish_error: str | None) -> None:
    can_publish = publish_settings is not None
    clicked, filters, main_col, detail_col = _page_shell(
        "Publishing Control",
        status_label="Ready" if can_publish else "Config Missing",
        status_level="success" if can_publish else "error",
        primary_action="Publish Queue",
        primary_help=_tip(
            "Publish queued HTML reports to WordPress with the configured validation policy.",
            "Set publish limit to 20 for a controlled batch publish.",
        ),
        primary_key="run_publish",
        primary_disabled=not can_publish,
    )
    with filters:
        limit = st.number_input(
            "Publish Limit",
            min_value=1,
            max_value=1000,
            value=20,
            step=1,
            help=_tip(
                "Maximum number of queued HTML reports to publish in one run.",
                "Start with 5 to validate WordPress connectivity and permissions.",
            ),
        )
    if clicked and publish_settings:
        _append_terminal("Publish requested from UI.")
        try:
            outcomes = run_publish(publish_settings, limit=int(limit))
            st.session_state["last_publish_outcomes"] = outcomes
            published_count = len([o for o in outcomes if o.status == "published"])
            _append_terminal(f"Publish complete. published={published_count} total={len(outcomes)}")
            st.success(f"Publishing completed: {published_count} published.")
        except Exception as exc:
            _append_terminal(f"Publish failed: {exc}")
            st.error(str(exc))

    queue_rows: list[dict[str, Any]] = []
    try:
        queue_snapshot = build_publish_queue_snapshot(
            PublishQueueRequest(
                schema_version="1.0",
                output_dir=settings.output_dir,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            _ctx("publish_queue"),
        )
        queue_rows = _to_dicts(queue_snapshot.items)
    except AppError:
        queue_rows = []

    with main_col:
        st.subheader("Publish Queue")
        if queue_rows:
            st.dataframe(queue_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No HTML files found in output directory.")
        outcomes = st.session_state.get("last_publish_outcomes", [])
        if outcomes:
            st.subheader("Last Publish Results")
            st.dataframe(_to_dicts(outcomes), use_container_width=True, hide_index=True)

    with detail_col:
        st.subheader("Settings Summary")
        if publish_settings:
            st.json(
                {
                    "site_url": publish_settings.wp.site_url,
                    "username": publish_settings.wp.username,
                    "post_status": publish_settings.wp.post_status,
                    "validation_policy": publish_settings.validation_policy,
                }
            )
        else:
            st.error(f"Publish settings unavailable: {publish_error}")


def _render_category_manager(settings: Any, publish_settings: Any | None) -> None:
    clicked, filters, main_col, detail_col = _page_shell(
        "Category Manager",
        status_label="Mapping Loaded",
        status_level="info",
        primary_action="Recategorize",
        primary_help=_tip(
            "Apply category mappings to reports and persist recategorization outcomes.",
            "Run after updating category-mappings YAML to refresh assignments.",
        ),
        primary_key="run_recategorize",
    )
    with filters:
        st.caption("View category mapping source and trigger recategorize / WordPress category sync.")
    sync_clicked = detail_col.button(
        "Sync WP Categories",
        key="run_wp_sync",
        use_container_width=True,
        disabled=publish_settings is None,
        help=_tip(
            "Synchronize mapped categories from reports DB to WordPress categories.",
            "Run after mapping changes so WordPress taxonomy stays aligned.",
        ),
    )

    if clicked:
        _append_terminal("Recategorize requested from UI.")
        try:
            outcomes = run_recategorize(
                RecategorizeRequest(
                    schema_version="1.0",
                    db_path=settings.reports_db,
                    category_mapping_path=settings.category_mapping_path,
                )
            )
            st.session_state["last_recategorize_outcomes"] = outcomes
            _append_terminal(f"Recategorize complete. outcomes={len(outcomes)}")
            st.success(f"Recategorization completed for {len(outcomes)} reports.")
        except Exception as exc:
            _append_terminal(f"Recategorize failed: {exc}")
            st.error(str(exc))

    if sync_clicked and publish_settings:
        _append_terminal("WP category sync requested from UI.")
        try:
            outcomes = run_update_wp_categories(publish_settings)
            st.session_state["last_wp_sync_outcomes"] = outcomes
            _append_terminal(f"WP category sync complete. outcomes={len(outcomes)}")
            st.success(f"WordPress category sync completed for {len(outcomes)} reports.")
        except Exception as exc:
            _append_terminal(f"WP category sync failed: {exc}")
            st.error(str(exc))

    mapping_response = load_mappings(
        request=CategoryMappingLoadRequest(
            schema_version="1.0",
            path=settings.category_mapping_path,
            reload_if_changed=True,
            force_reload=False,
        ),
        ctx=_ctx("load_mapping"),
    )
    categories = _to_dicts(mapping_response.mappings.categories)

    with main_col:
        st.subheader("Category Mapping")
        st.dataframe(categories, use_container_width=True, hide_index=True)
        recat = st.session_state.get("last_recategorize_outcomes", [])
        if recat:
            st.subheader("Recategorize Outcomes")
            st.dataframe(_to_dicts(recat), use_container_width=True, hide_index=True)
    with detail_col:
        st.subheader("WP Sync")
        if publish_settings is None:
            st.caption("Publish settings missing; WP sync disabled.")
        sync = st.session_state.get("last_wp_sync_outcomes", [])
        if sync:
            st.dataframe(_to_dicts(sync), use_container_width=True, hide_index=True)


def _load_ledger_entries(ledger_path: str, *, limit: int = 2000) -> list[dict[str, Any]]:
    try:
        content = read_text(ReadTextRequest(schema_version="1.0", path=ledger_path), _ctx("read_ledger")).content
    except AppError:
        return []
    rows: list[dict[str, Any]] = []
    for line in content.splitlines():
        if not line.strip():
            continue
        payload = safe_json_loads(line.strip())
        if isinstance(payload, dict):
            rows.append(payload)
    rows = rows[-limit:]
    return rows


def _render_cost_and_usage(settings: Any) -> None:
    clicked, filters, main_col, detail_col = _page_shell(
        "Cost & Usage",
        status_label="Ledger Ready",
        status_level="info",
        primary_action="Run Cost Report",
        primary_help=_tip(
            "Generate a filtered cost report from the ledger.",
            "Choose date mode for daily spend or run_id mode for a single pipeline run.",
        ),
        primary_key="run_cost_report",
    )
    with filters:
        mode_col, value_col, top_col = st.columns(3)
        with mode_col:
            filter_mode = st.selectbox(
                "Filter Mode",
                options=["date", "run_id"],
                index=0,
                help=_tip(
                    "Choose how to filter the generated cost report.",
                    "Use 'date' for daily totals or 'run_id' for one execution trace.",
                ),
            )
        with value_col:
            if filter_mode == "date":
                filter_value = st.date_input(
                    "Date (UTC)",
                    help=_tip(
                        "UTC date filter used when Filter Mode is 'date'.",
                        "Pick today's UTC date to inspect current spend.",
                    ),
                ).strftime("%Y-%m-%d")
            else:
                filter_value = st.text_input(
                    "run_id",
                    value="",
                    help=_tip(
                        "Run identifier filter used when Filter Mode is 'run_id'.",
                        "Paste run_id from Logs & Live Terminal for per-run cost analysis.",
                    ),
                )
        with top_col:
            top_n = st.number_input(
                "Top N Steps",
                min_value=1,
                max_value=25,
                value=5,
                step=1,
                help=_tip(
                    "Number of highest-cost steps to include in the report breakdown.",
                    "Set 10 to get a wider optimization view.",
                ),
            )
    if clicked:
        run_id_value = filter_value.strip() if filter_mode == "run_id" else ""
        if filter_mode == "run_id" and not run_id_value:
            st.warning("Enter a run_id before running the cost report.")
            return
        try:
            reporting = run_cost_reporting(
                CostReportingRequest(
                    schema_version="1.0",
                    report_request=CostReportRequest(
                        schema_version="1.0",
                        ledger_path=settings.cost_ledger_path,
                        date_utc=filter_value if filter_mode == "date" else None,
                        run_id=run_id_value if filter_mode == "run_id" else None,
                        top_n=int(top_n),
                    ),
                ),
                _ctx("cost_report"),
            )
            report = reporting.report
            if report is None:
                raise RuntimeError("Cost report was not generated.")
            st.session_state["last_cost_report"] = report
            _append_terminal(
                f"Cost report generated: filter={report.filter_type}:{report.filter_value} entries={report.matched_entries}"
            )
            st.success("Cost report generated.")
        except Exception as exc:
            _append_terminal(f"Cost report failed: {exc}")
            st.error(str(exc))

    ledger_rows = _load_ledger_entries(settings.cost_ledger_path)
    log_files = _discover_log_files()
    event_rows = _load_log_events([row["path"] for row in log_files[:3]], max_lines_per_file=4000)
    duration_rows = compute_task_duration_rollups(event_rows)
    rollup_reporting = run_cost_reporting(
        CostReportingRequest(
            schema_version="1.0",
            rollup_request=CostRollupRequest(
                schema_version="1.0",
                ledger_path=settings.cost_ledger_path,
                out_path=settings.cost_daily_path,
            ),
        ),
        _ctx("cost_rollup"),
    )
    rollup = rollup_reporting.rollup

    with main_col:
        st.subheader("Ledger Explorer")
        if ledger_rows:
            st.dataframe(ledger_rows[-100:], use_container_width=True, hide_index=True)
        else:
            st.info("No ledger entries found.")
        st.subheader("Daily Spend")
        daily_points = []
        if rollup is not None:
            daily_points = [{"date": key, "usd": value.total_usd} for key, value in rollup.totals_by_date.items()]
        if daily_points:
            st.line_chart(daily_points, x="date", y="usd")
        st.subheader("Processing Time Rollups")
        if duration_rows:
            st.dataframe(duration_rows[:100], use_container_width=True, hide_index=True)
        else:
            st.caption("No structured events with timestamps available.")
        last_report = st.session_state.get("last_cost_report")
        if last_report:
            st.subheader("Cost Report Output")
            st.json(asdict(last_report))

    with detail_col:
        st.subheader("Pricing")
        st.json(settings.model_pricing)
        st.subheader("Paths")
        st.code(f"ledger: {settings.cost_ledger_path}\ndaily: {settings.cost_daily_path}")


def _render_logs_and_terminal() -> None:
    clicked, filters, main_col, detail_col = _page_shell(
        "Logs & Live Terminal",
        status_label="Observability",
        status_level="info",
        primary_action="Refresh Logs",
        primary_help=_tip(
            "Reload log files and rerender structured event views.",
            "Use after triggering a pipeline action to inspect new events immediately.",
        ),
        primary_key="refresh_logs",
    )
    if clicked:
        st.rerun()
    log_files = _discover_log_files()
    with filters:
        if not log_files:
            st.warning("No log files discovered.")
            _render_terminal_panel()
            return
        selected_paths = st.multiselect(
            "Log Files",
            options=[row["path"] for row in log_files],
            default=[row["path"] for row in log_files[:1]],
            help=_tip(
                "Select one or more structured log files to search and inspect.",
                "Choose today's file plus the previous file for cross-run debugging.",
            ),
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            run_id = st.text_input(
                "run_id",
                value="",
                help=_tip(
                    "Filter events by a specific run identifier.",
                    "Paste run_id from a recent orchestrator event.",
                ),
            )
            task_id = st.text_input(
                "task_id",
                value="",
                help=_tip(
                    "Filter events by task identifier.",
                    "Use task_id='gui:run_ingest' to inspect ingest calls from UI.",
                ),
            )
        with c2:
            span_id = st.text_input(
                "span_id",
                value="",
                help=_tip(
                    "Filter events by span identifier for finer trace slicing.",
                    "Paste span_id from one error event to follow its lifecycle.",
                ),
            )
            event_filter = st.text_input(
                "event",
                value="",
                help=_tip(
                    "Filter by event name.",
                    "Enter 'ingest_started' or 'publish_result' to narrow results.",
                ),
            )
        with c3:
            role_filter = st.text_input(
                "role",
                value="",
                help=_tip(
                    "Filter by emitting role: service, generator, or orchestrator.",
                    "Enter 'orchestrator' to focus on control-plane decisions.",
                ),
            )
            module_filter = st.text_input(
                "module",
                value="",
                help=_tip(
                    "Filter by Python module name.",
                    "Use 'src.orchestrators.ingest_orchestrator' for ingest internals.",
                ),
            )
        st.markdown('<div class="ml-note">Sensitive values are redacted in structured logs as <code>***REDACTED***</code>.</div>', unsafe_allow_html=True)

    events = _load_log_events(selected_paths, max_lines_per_file=6000)
    filtered = filter_log_events(
        events,
        run_id=run_id,
        task_id=task_id,
        span_id=span_id,
        event=event_filter,
        role=role_filter,
        module=module_filter,
    )

    with main_col:
        st.subheader("Structured Events")
        if filtered:
            table = []
            for row in filtered[-500:]:
                table.append(
                    {
                        "timestamp": row.get("timestamp_utc") or row.get("timestamp_hms"),
                        "run_id": row.get("run_id"),
                        "task_id": row.get("task_id"),
                        "span_id": row.get("span_id"),
                        "role": row.get("role"),
                        "event": row.get("event"),
                        "module": row.get("module"),
                    }
                )
            st.dataframe(table, use_container_width=True, hide_index=True)
        else:
            st.info("No events match current filters.")

        raw_candidates = []
        for row in filtered:
            fields = row.get("fields") or {}
            if not isinstance(fields, dict):
                continue
            if any(key in fields for key in ("raw_response", "response", "provider_response", "model_response")):
                raw_candidates.append(row)
        st.subheader("Raw Model Output Viewer")
        if raw_candidates:
            options = [f"{item.get('event')} | {item.get('task_id')}" for item in raw_candidates]
            index = st.selectbox(
                "Select Event",
                options=list(range(len(options))),
                format_func=lambda idx: options[idx],
                help=_tip(
                    "Select one event to inspect full raw model payload details.",
                    "Choose the latest model_call event when debugging response parsing.",
                ),
            )
            st.json(raw_candidates[index])
        else:
            st.caption("No raw-response events found in current filter scope.")

    with detail_col:
        st.subheader("Live Run Output")
        _render_terminal_panel()


def _render_settings_and_prompts(settings: Any, publish_settings: Any | None, publish_error: str | None) -> None:
    clicked, filters, main_col, detail_col = _page_shell(
        "Settings & Prompts",
        status_label="Read-Only",
        status_level="info",
        primary_action="Reload Settings",
        primary_help=_tip(
            "Reload config and prompt metadata from source-of-truth files and env overrides.",
            "Use after editing YAML or environment values.",
        ),
        primary_key="reload_settings",
    )
    if clicked:
        st.rerun()
    with filters:
        st.caption("Configuration and prompt registry visibility. Secrets are redacted.")

    prompt_namespaces = list_prompt_namespaces(
        PromptNamespaceListRequest(schema_version="1.0", reload_if_changed=True, force_reload=False),
        _ctx("prompt_namespaces"),
    )
    env_keys = [
        "OPENAI_API_KEY",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "GDRIVE_FOLDER_ID",
        "OPENAI_MODEL",
        "OPENAI_TIMEOUT_SECONDS",
        "WP_SITE_URL",
        "WP_USERNAME",
        "WP_APP_PASSWORD",
        "WP_BEARER_TOKEN",
        "PUBLISH_VALIDATION_POLICY",
        "OUTPUT_DIR",
        "CACHE_DIR",
        "STATE_DB",
        "REPORTS_DB",
    ]

    sanitized_settings = asdict(settings)
    sanitized_settings["openai_api_key"] = "***REDACTED***"
    if publish_settings:
        pub_data = asdict(publish_settings)
        pub_data["wp"]["app_password"] = "***REDACTED***" if pub_data["wp"].get("app_password") else None
        pub_data["wp"]["bearer_token"] = "***REDACTED***" if pub_data["wp"].get("bearer_token") else None
    else:
        pub_data = {"error": publish_error or "publish settings unavailable"}

    with main_col:
        st.subheader("Config Summary")
        st.json({"ingest": sanitized_settings, "publish": pub_data})
        st.subheader("Prompt Namespaces")
        st.dataframe(_to_dicts(prompt_namespaces.namespaces), use_container_width=True, hide_index=True)

    with detail_col:
        st.subheader("Env Override Badges")
        badges = []
        for key in env_keys:
            source = "env" if os.getenv(key, "").strip() else "yaml/default"
            level = "success" if source == "env" else "info"
            badges.append({"key": key, "source": source, "chip": _chip_html(source.upper(), level)})
        for row in badges:
            st.markdown(f"{row['key']} {row['chip']}", unsafe_allow_html=True)


def _render_system_and_storage(settings: Any) -> None:
    clicked, filters, main_col, detail_col = _page_shell(
        "System & Storage",
        status_label="State Snapshot",
        status_level="info",
        primary_action="Refresh Storage",
        primary_help=_tip(
            "Refresh DB snapshots, lock status, and artifact directory counts.",
            "Use after ingest or cleanup tasks to verify filesystem and state alignment.",
        ),
        primary_key="refresh_system_storage",
    )
    if clicked:
        st.rerun()
    with filters:
        st.caption("Explore DB records, lock status, and artifact directory mapping.")

    processed = _load_processed_rows(settings)
    published = _load_published_rows(settings)
    reports = _load_report_rows(settings)
    lock = _lock_snapshot(settings.ingest_lock_path)

    path_checks: list[dict[str, Any]] = []
    for label, root_dir, pattern, recursive, include_dirs in [
        ("HTML", settings.output_dir, "*.html", False, False),
        ("report_analysis dirs", settings.output_dir, "report_analysis", True, True),
        ("assets dirs", settings.output_dir, "assets", True, True),
        ("candidates dirs", settings.output_dir, "candidates", True, True),
        ("slices dirs", settings.output_dir, "slices", True, True),
        ("thumbs dirs", settings.output_dir, "thumbs", True, True),
    ]:
        try:
            resp = list_directory(
                ListDirectoryRequest(
                    schema_version="1.0",
                    root_dir=root_dir,
                    glob_pattern=pattern,
                    recursive=recursive,
                    include_files=not include_dirs,
                    include_dirs=include_dirs,
                    limit=5000,
                ),
                _ctx(f"storage:{label}"),
            )
            count = len(resp.entries)
        except AppError:
            count = 0
        path_checks.append({"name": label, "root": root_dir, "count": count})

    with main_col:
        st.subheader("State DB - Processed")
        st.dataframe(processed[:200], use_container_width=True, hide_index=True)
        st.subheader("State DB - Published")
        st.dataframe(published[:200], use_container_width=True, hide_index=True)
        st.subheader("Reports DB")
        st.dataframe(reports[:200], use_container_width=True, hide_index=True)

    with detail_col:
        st.subheader("Lock Status")
        if lock.get("found"):
            st.error(f"Locked by `{lock.get('owner_id')}` (pid={lock.get('pid')})")
        else:
            st.success("No active lock")
        st.subheader("Storage Map")
        st.dataframe(path_checks, use_container_width=True, hide_index=True)
        st.code(f"output={settings.output_dir}\ncache={settings.cache_dir}\nstate_db={settings.state_db}\nreports_db={settings.reports_db}")


def _render_developer_tools() -> None:
    _page_shell(
        "Developer & Test Tools",
        status_label="Disabled",
        status_level="warn",
        primary_action="Disabled",
        primary_help=_tip(
            "Reserved for future developer tooling; action intentionally disabled.",
            "No user action available on this page yet.",
        ),
        primary_key="dev_tools_disabled",
        primary_disabled=True,
    )
    st.info("This page is intentionally disabled until dedicated developer CLI/orchestrator tooling is added.")


def main() -> None:
    st.set_page_config(page_title="Market Lense Cockpit", page_icon="ML", layout="wide")
    _inject_theme()
    if not st.session_state.get("gui_logging_ready"):
        setup_logging(LoggingSetupRequest(schema_version="1.0"), _ctx("setup_logging"))
        st.session_state["gui_logging_ready"] = True
    st.session_state.setdefault("live_terminal_output", "")

    settings, settings_error = _try_load_settings()
    publish_settings, publish_error = _try_load_publish_settings()
    if settings_error or settings is None:
        st.error(f"Unable to load app settings: {settings_error}")
        st.stop()

    with st.sidebar:
        st.title("Market Lense")
        section = st.radio(
            "Navigation",
            options=NAV_SECTIONS,
            key="nav_section",
            help=_tip(
                "Primary section selector. Each page is scoped to one operational task.",
                "Choose 'Ingest Control' to run ingest, then move to 'Logs & Live Terminal' to inspect events.",
            ),
        )
        st.markdown("---")
        st.caption("One task per page. Source-of-truth first.")

    if section == "Cockpit Overview":
        _render_cockpit_overview(settings)
    elif section == "Ingest Control":
        _render_ingest_control(settings)
    elif section == "Candidate Extraction":
        _render_candidate_extraction(settings)
    elif section == "Report Command Center":
        _render_report_command_center(settings)
    elif section == "Cover Images":
        _render_cover_images(settings)
    elif section == "Analysis & Evidence":
        _render_analysis_and_evidence(settings)
    elif section == "Validation Center":
        _render_validation_center(settings, publish_settings, publish_error)
    elif section == "Publishing Control":
        _render_publishing_control(settings, publish_settings, publish_error)
    elif section == "Category Manager":
        _render_category_manager(settings, publish_settings)
    elif section == "Cost & Usage":
        _render_cost_and_usage(settings)
    elif section == "Logs & Live Terminal":
        _render_logs_and_terminal()
    elif section == "Settings & Prompts":
        _render_settings_and_prompts(settings, publish_settings, publish_error)
    elif section == "System & Storage":
        _render_system_and_storage(settings)
    elif section == "Developer & Test Tools":
        _render_developer_tools()


if __name__ == "__main__":
    main()
