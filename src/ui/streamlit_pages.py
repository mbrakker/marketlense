from __future__ import annotations

import os
from html import escape
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, MutableMapping, Optional, TypeVar

import streamlit as st
import yaml

from src.contracts.categories import CategoryMappingLoadRequest, RecategorizeRequest
from src.contracts.config import (
    AppConfigReadRequest,
    AppConfigWriteRequest,
    ConfigLoadRequest,
)
from src.contracts.costs import (
    CostReportRequest,
    CostReportingRequest,
    CostRollupRequest,
)
from src.contracts.cover_images import CoverStyleLoadRequest
from src.contracts.ops import OpsDashboardSnapshotRequest
from src.contracts.prompts import PromptNamespaceListRequest
from src.contracts.publish import PublishQueueRequest
from src.contracts.state import StateGetRequest
from src.contracts.streamlit_dashboard import (
    DirectoryCountCheck,
    DirectoryCountsRequest,
    JsonPayloadReadRequest,
    LedgerEntriesLoadRequest,
    LockSnapshotLoadRequest,
    LogEventLoadRequest,
    LogFileDiscoveryRequest,
    ReportRowsLoadRequest,
    StateRowsLoadRequest,
    StorageHealthRequest,
    StorageTarget,
    ValidationArtifactSummaryRequest,
)
from src.contracts.semantic_ids import RunId
from src.generators.streamlit_dashboard_generator import (
    collect_directory_counts,
    collect_storage_health,
    discover_log_files,
    load_ledger_entries,
    load_lock_snapshot,
    load_log_events,
    load_report_rows,
    load_state_rows,
    read_json_payload,
    summarize_validation_artifacts,
)
from src.orchestrators.cost_reporting_orchestrator import run_cost_reporting
from src.orchestrators.ops_dashboard_orchestrator import collect_ops_dashboard_snapshot
from src.orchestrators.publish_queue_orchestrator import build_publish_queue_snapshot
from src.orchestrators.recategorize_orchestrator import run_recategorize
from src.orchestrators.wp_category_update_orchestrator import run_update_wp_categories
from src.services.category_mapping_service import load_mappings
from src.services.config_service import (
    load_publish_settings,
    load_settings,
    read_app_config,
    write_app_config,
)
from src.services.cover_style_service import load_cover_styles
from src.services.logging_service import DEFAULT_LOG_DIR, LOG_DIR_ENV, LOG_FILE_PREFIX
from src.services.prompt_service import list_prompt_namespaces
from src.ui import state as ui_state
from src.ui.run_control import launch_background_run, list_recent_runs, poll_selected_run
from src.services.state_service import get as get_state
from src.utils.coercion import (
    coerce_extended_bool as _as_bool,
    coerce_float as _as_float,
    coerce_int as _as_int,
)
from src.utils.errors import AppError
from src.utils.gui_utils import (
    mapping_from_editor_records,
    normalize_text_lines,
    pricing_from_editor_records,
    row_dicts,
    compute_task_duration_rollups,
    filter_log_events,
    status_chip_level,
)
from src.utils.cover_path_utils import build_cover_asset_path
from src.utils.logging import new_run_context
from src.utils.slugify import slugify

UI_SURFACE_EXCEPTIONS = (AppError, OSError, RuntimeError, ValueError, TypeError, yaml.YAMLError)

_DASHBOARD_READ_MODEL_CACHE_KEY = "dashboard_read_models"
_DASHBOARD_CACHE_INVALIDATION_REASON_KEY = "dashboard_read_models_last_invalidation"
_T = TypeVar("_T")

_DASHBOARD_CACHE_INVALIDATION_RULES: dict[str, set[str] | None] = {
    "refresh_all": None,
    "ingest": {
        "ops_snapshot",
        "report_rows",
        "processed_rows",
        "published_rows",
        "log_files",
        "log_events",
        "lock_snapshot",
        "storage_health",
        "validation_files",
        "directory_counts",
    },
    "publish": {
        "ops_snapshot",
        "report_rows",
        "published_rows",
        "log_files",
        "log_events",
        "validation_files",
    },
    "recategorize": {
        "ops_snapshot",
        "report_rows",
        "log_files",
        "log_events",
    },
    "cover_images": {
        "report_rows",
        "directory_counts",
    },
    "settings": None,
}

_UI_RUN_INVALIDATION_BY_TYPE: dict[str, str | None] = {
    "ingest": "ingest",
    "publish": "publish",
    "cover_images": "cover_images",
    "candidate_extraction": None,
    "publisher_discovery": None,
    "report_download": None,
    "acquisition_audit": None,
}


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


def _selected_ui_run(
    settings: Any,
    *,
    run_type: str | None = None,
    max_bytes: int = 65536,
) -> Any | None:
    polled = poll_selected_run(settings, max_bytes=max_bytes)
    if polled is None:
        return None
    record = polled.record
    if run_type and record.run_type != run_type:
        return None
    if record.status == "succeeded":
        cache_key = f"ui_run_cache_synced:{record.run_id}"
        if not st.session_state.get(cache_key):
            reason = _UI_RUN_INVALIDATION_BY_TYPE.get(record.run_type)
            if reason:
                _invalidate_dashboard_read_models(st.session_state, reason=reason)
            st.session_state[cache_key] = True
    return polled


def _selected_report_index(reports: list[dict[str, Any]]) -> int:
    selected_report_id = ui_state.get_selected_report_id()
    if not selected_report_id:
        return 0
    for idx, row in enumerate(reports):
        if str(row.get("file_id") or "").strip() == selected_report_id:
            return idx
    return 0

def _chip_html(label: str, level: str, *, tooltip: str | None = None) -> str:
    tip = tooltip or _tip(
        "Status indicator for the current view.",
        f"If it shows '{label}', use that state to decide whether to run the page action.",
    )
    return (
        f'<span class="status-chip status-{level}" title="{escape(tip)}">{label}</span>'
    )


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
  --ml-bg: #8e949b;
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
  background: var(--ml-bg) !important;
}

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #10291f 0%, #16372b 100%);
  border-right: 1px solid rgba(255,255,255,0.08);
}

[data-testid="stSidebar"] * {
  color: #f2f6f3 !important;
  font-family: "Manrope", sans-serif !important;
}

[data-testid="stAppViewContainer"] [data-testid="stMain"] {
  --text-color: #000000 !important;
  --body-text-color: #000000 !important;
  --secondary-text-color: #000000 !important;
  color: #000000 !important;
}

[data-testid="stAppViewContainer"] [data-testid="stMain"] h1,
[data-testid="stAppViewContainer"] [data-testid="stMain"] h2,
[data-testid="stAppViewContainer"] [data-testid="stMain"] h3,
[data-testid="stAppViewContainer"] [data-testid="stMain"] h4,
[data-testid="stAppViewContainer"] [data-testid="stMain"] h5,
[data-testid="stAppViewContainer"] [data-testid="stMain"] h6,
[data-testid="stAppViewContainer"] [data-testid="stMain"] p,
[data-testid="stAppViewContainer"] [data-testid="stMain"] li,
[data-testid="stAppViewContainer"] [data-testid="stMain"] label,
[data-testid="stAppViewContainer"] [data-testid="stMain"] [data-testid="stHeadingWithActionElements"],
[data-testid="stAppViewContainer"] [data-testid="stMain"] [data-testid="stHeadingWithActionElements"] *,
[data-testid="stAppViewContainer"] [data-testid="stMain"] [data-testid="stMetricLabel"],
[data-testid="stAppViewContainer"] [data-testid="stMain"] [data-testid="stMetricLabel"] *,
[data-testid="stAppViewContainer"] [data-testid="stMain"] [data-testid="stMetricValue"],
[data-testid="stAppViewContainer"] [data-testid="stMain"] [data-testid="stMetricValue"] *,
[data-testid="stAppViewContainer"] [data-testid="stMain"] [data-testid="stMetricDelta"],
[data-testid="stAppViewContainer"] [data-testid="stMain"] [data-testid="stWidgetLabel"],
[data-testid="stAppViewContainer"] [data-testid="stMain"] [data-testid="stWidgetLabel"] *,
[data-testid="stAppViewContainer"] [data-testid="stMain"] .stTextInput label,
[data-testid="stAppViewContainer"] [data-testid="stMain"] .stNumberInput label,
[data-testid="stAppViewContainer"] [data-testid="stMain"] .stSelectbox label,
[data-testid="stAppViewContainer"] [data-testid="stMain"] .stMultiSelect label,
[data-testid="stAppViewContainer"] [data-testid="stMain"] .stCheckbox label,
[data-testid="stAppViewContainer"] [data-testid="stMain"] .stRadio label,
[data-testid="stAppViewContainer"] [data-testid="stMain"] [data-testid="stMarkdownContainer"],
[data-testid="stAppViewContainer"] [data-testid="stMain"] [data-testid="stCaptionContainer"],
[data-testid="stAppViewContainer"] [data-testid="stMain"] [data-testid="stCaptionContainer"] *,
[data-testid="stAppViewContainer"] [data-testid="stMain"] .stCaption,
[data-testid="stAppViewContainer"] [data-testid="stMain"] figcaption,
[data-testid="stAppViewContainer"] [data-testid="stMain"] .ml-note,
[data-testid="stAppViewContainer"] [data-testid="stMain"] .ml-step,
[data-testid="stAppViewContainer"] [data-testid="stMain"] .ml-panel p {
  color: #000000 !important;
  -webkit-text-fill-color: #000000 !important;
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

.ml-panel {
  border-radius: 1rem;
  border: 1px solid var(--ml-border);
  background: linear-gradient(165deg, #ffffff 0%, #f7fbf9 100%);
  box-shadow: var(--ml-shadow);
  padding: 0.85rem 1rem;
  margin-bottom: 0.75rem;
}

.ml-panel h4 {
  font-family: "Sora", "Manrope", sans-serif;
  font-size: 0.95rem;
  margin: 0 0 0.35rem;
}

.ml-panel p {
  margin: 0;
  color: var(--ml-muted);
  font-size: 0.84rem;
}

[data-testid="stTextArea"] textarea {
  border-radius: 0.8rem !important;
  border: 1px solid #9ecbbd !important;
  background: #f9fffc !important;
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


def _render_stepper(
    steps: list[str],
    done_count: int = 0,
    *,
    active_index: Optional[int] = None,
    error_index: Optional[int] = None,
) -> None:
    parts: list[str] = ['<div class="ml-stepper">']
    for idx, step in enumerate(steps):
        cls = "ml-step"
        if error_index is not None and idx == error_index:
            cls += " ml-step-error"
        elif idx < done_count:
            cls += " ml-step-done"
        elif active_index is not None and idx == active_index:
            cls += " ml-step-active"
        tip = _tip(
            "Pipeline step in the current run sequence.", f"Step {idx + 1}: {step}."
        )
        parts.append(f'<div class="{cls}" title="{escape(tip)}">{step}</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def _try_load_settings() -> tuple[Any | None, str | None]:
    try:
        settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), _ctx("load_settings")
        )
    except UI_SURFACE_EXCEPTIONS as exc:  # pragma: no cover - runtime safeguard for UI
        return None, str(exc)
    return settings, None


def _try_load_publish_settings() -> tuple[Any | None, str | None]:
    try:
        settings = load_publish_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            _ctx("load_publish_settings"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:  # pragma: no cover - runtime safeguard for UI
        return None, str(exc)
    return settings, None


def _try_read_app_config() -> tuple[Any | None, str | None]:
    try:
        response = read_app_config(
            AppConfigReadRequest(schema_version="1.0", path=""), _ctx("read_app_config")
        )
    except UI_SURFACE_EXCEPTIONS as exc:  # pragma: no cover - runtime safeguard for UI
        return None, str(exc)
    return response, None


def _try_write_app_config(
    content: str, *, make_backup: bool
) -> tuple[Any | None, str | None]:
    try:
        response = write_app_config(
            AppConfigWriteRequest(
                schema_version="1.0",
                path="",
                content=content,
                make_backup=make_backup,
            ),
            _ctx("write_app_config"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:  # pragma: no cover - runtime safeguard for UI
        return None, str(exc)
    return response, None


def _dashboard_read_model_store(
    session_state: MutableMapping[str, Any],
) -> dict[tuple[object, ...], Any]:
    cache = session_state.get(_DASHBOARD_READ_MODEL_CACHE_KEY)
    if isinstance(cache, dict):
        return cache
    created: dict[tuple[object, ...], Any] = {}
    session_state[_DASHBOARD_READ_MODEL_CACHE_KEY] = created
    return created


def _load_dashboard_read_model(
    session_state: MutableMapping[str, Any],
    *,
    view_name: str,
    identity: tuple[object, ...] = (),
    loader: Callable[[], _T],
) -> _T:
    cache = _dashboard_read_model_store(session_state)
    cache_key = (view_name, *identity)
    if cache_key not in cache:
        cache[cache_key] = loader()
    return cache[cache_key]


def _invalidate_dashboard_read_models(
    session_state: MutableMapping[str, Any], *, reason: str
) -> list[str]:
    if reason not in _DASHBOARD_CACHE_INVALIDATION_RULES:
        raise ValueError(f"Unknown dashboard cache invalidation reason: {reason}")
    cache = _dashboard_read_model_store(session_state)
    targets = _DASHBOARD_CACHE_INVALIDATION_RULES[reason]
    if targets is None:
        removed_keys = list(cache.keys())
        cache.clear()
    else:
        removed_keys = [
            key
            for key in list(cache.keys())
            if isinstance(key, tuple) and key and key[0] in targets
        ]
        for key in removed_keys:
            cache.pop(key, None)
    session_state[_DASHBOARD_CACHE_INVALIDATION_REASON_KEY] = reason
    return [str(key[0]) for key in removed_keys if isinstance(key, tuple) and key]


def _discover_log_files() -> list[dict[str, Any]]:
    log_dir = os.getenv(LOG_DIR_ENV, DEFAULT_LOG_DIR)
    return _load_dashboard_read_model(
        st.session_state,
        view_name="log_files",
        identity=(log_dir, LOG_FILE_PREFIX, 100),
        loader=lambda: row_dicts(
            discover_log_files(
                LogFileDiscoveryRequest(
                    schema_version="1.0",
                    log_dir=log_dir,
                    file_prefix=LOG_FILE_PREFIX,
                    limit=100,
                ),
                _ctx("discover_logs"),
            ).records
        ),
    )


def _load_log_events(
    log_paths: list[str], *, max_lines_per_file: int = 5000
) -> list[dict[str, Any]]:
    return _load_dashboard_read_model(
        st.session_state,
        view_name="log_events",
        identity=(tuple(log_paths), max_lines_per_file),
        loader=lambda: load_log_events(
            LogEventLoadRequest(
                schema_version="1.0",
                log_paths=log_paths,
                max_lines_per_file=max_lines_per_file,
            ),
            _ctx("load_log_events"),
        ).events,
    )


def _read_json(path: str) -> dict[str, Any] | list[Any] | None:
    response = read_json_payload(
        JsonPayloadReadRequest(schema_version="1.0", path=path),
        _ctx("read_json"),
    )
    return response.payload


def _append_terminal(message: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    previous = st.session_state.get("live_terminal_output", "")
    st.session_state["live_terminal_output"] = f"{previous}[{now}] {message}\n"


def _render_terminal_panel() -> None:
    terminal_text = st.session_state.get("live_terminal_output", "")
    if not terminal_text.strip():
        terminal_text = "No run output captured yet."
    st.markdown(
        f'<pre class="ml-terminal">{terminal_text}</pre>', unsafe_allow_html=True
    )


def _as_utc(ts: int | float | None) -> str:
    if ts is None:
        return ""
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    except (OSError, OverflowError, TypeError, ValueError):
        return ""


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _optional_int_from_text(value: str, *, field: str, errors: list[str]) -> int | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        errors.append(f"{field} must be an integer or blank.")
        return None


def _storage_health(settings: Any) -> list[dict[str, Any]]:
    return _load_dashboard_read_model(
        st.session_state,
        view_name="storage_health",
        identity=(
            settings.output_dir,
            settings.cache_dir,
            settings.state_db,
            settings.reports_db,
        ),
        loader=lambda: row_dicts(
            collect_storage_health(
                StorageHealthRequest(
                    schema_version="1.0",
                    targets=[
                        StorageTarget(
                            schema_version="1.0",
                            name="output_dir",
                            path=settings.output_dir,
                        ),
                        StorageTarget(
                            schema_version="1.0",
                            name="cache_dir",
                            path=settings.cache_dir,
                        ),
                        StorageTarget(
                            schema_version="1.0",
                            name="state_db",
                            path=settings.state_db,
                        ),
                        StorageTarget(
                            schema_version="1.0",
                            name="reports_db",
                            path=settings.reports_db,
                        ),
                    ],
                ),
                _ctx("storage_health"),
            ).rows
        ),
    )


def _recent_validation_files(output_dir: str) -> list[dict[str, Any]]:
    return _load_dashboard_read_model(
        st.session_state,
        view_name="validation_files",
        identity=(output_dir, 200),
        loader=lambda: row_dicts(
            summarize_validation_artifacts(
                ValidationArtifactSummaryRequest(
                    schema_version="1.0", output_dir=output_dir, limit=200
                ),
                _ctx("validation_summary"),
            ).rows
        ),
    )


def _load_report_rows(settings: Any) -> list[dict[str, Any]]:
    return _load_dashboard_read_model(
        st.session_state,
        view_name="report_rows",
        identity=(settings.reports_db,),
        loader=lambda: load_report_rows(
            ReportRowsLoadRequest(schema_version="1.0", reports_db=settings.reports_db),
            _ctx("load_report_rows"),
        ).rows,
    )


def _load_processed_rows(settings: Any) -> list[dict[str, Any]]:
    return _load_dashboard_read_model(
        st.session_state,
        view_name="processed_rows",
        identity=(settings.state_db, 1000),
        loader=lambda: load_state_rows(
            StateRowsLoadRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                kind="processed",
                limit=1000,
            ),
            _ctx("load_processed_rows"),
        ).rows,
    )


def _load_published_rows(settings: Any) -> list[dict[str, Any]]:
    return _load_dashboard_read_model(
        st.session_state,
        view_name="published_rows",
        identity=(settings.state_db, 1000),
        loader=lambda: load_state_rows(
            StateRowsLoadRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                kind="published",
                limit=1000,
            ),
            _ctx("load_published_rows"),
        ).rows,
    )


def _lock_snapshot(lock_path: str) -> dict[str, Any]:
    return _load_dashboard_read_model(
        st.session_state,
        view_name="lock_snapshot",
        identity=(lock_path,),
        loader=lambda: asdict(
            load_lock_snapshot(
                LockSnapshotLoadRequest(schema_version="1.0", lock_path=lock_path),
                _ctx("load_lock_snapshot"),
            )
        ),
    )


def _load_ops_dashboard_snapshot(settings: Any) -> Any:
    return _load_dashboard_read_model(
        st.session_state,
        view_name="ops_snapshot",
        identity=(
            settings.output_dir,
            settings.cache_dir,
            settings.state_db,
            settings.reports_db,
            settings.ingest_lock_path,
        ),
        loader=lambda: collect_ops_dashboard_snapshot(
            OpsDashboardSnapshotRequest(
                schema_version="1.0",
                output_dir=settings.output_dir,
                cache_dir=settings.cache_dir,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                ingest_lock_path=settings.ingest_lock_path,
            ),
            _ctx("ops_snapshot"),
        ),
    )


def _load_directory_count_rows(settings: Any) -> list[dict[str, Any]]:
    return _load_dashboard_read_model(
        st.session_state,
        view_name="directory_counts",
        identity=(settings.output_dir, 5000),
        loader=lambda: row_dicts(
            collect_directory_counts(
                DirectoryCountsRequest(
                    schema_version="1.0",
                    checks=[
                        DirectoryCountCheck(
                            schema_version="1.0",
                            name="HTML",
                            root_dir=settings.output_dir,
                            glob_pattern="*.html",
                            recursive=False,
                            include_dirs=False,
                        ),
                        DirectoryCountCheck(
                            schema_version="1.0",
                            name="report_analysis dirs",
                            root_dir=settings.output_dir,
                            glob_pattern="report_analysis",
                            recursive=True,
                            include_dirs=True,
                        ),
                        DirectoryCountCheck(
                            schema_version="1.0",
                            name="assets dirs",
                            root_dir=settings.output_dir,
                            glob_pattern="assets",
                            recursive=True,
                            include_dirs=True,
                        ),
                        DirectoryCountCheck(
                            schema_version="1.0",
                            name="candidates dirs",
                            root_dir=settings.output_dir,
                            glob_pattern="candidates",
                            recursive=True,
                            include_dirs=True,
                        ),
                        DirectoryCountCheck(
                            schema_version="1.0",
                            name="slices dirs",
                            root_dir=settings.output_dir,
                            glob_pattern="slices",
                            recursive=True,
                            include_dirs=True,
                        ),
                        DirectoryCountCheck(
                            schema_version="1.0",
                            name="thumbs dirs",
                            root_dir=settings.output_dir,
                            glob_pattern="thumbs",
                            recursive=True,
                            include_dirs=True,
                        ),
                    ],
                    limit=5000,
                ),
                _ctx("directory_counts"),
            ).rows
        ),
    )


def _render_cockpit_overview(settings: Any) -> None:
    snapshot = _load_ops_dashboard_snapshot(settings)
    reports = snapshot.reports
    processed = snapshot.processed
    published = snapshot.published
    lock = asdict(snapshot.lock)
    health = [asdict(item) for item in snapshot.storage_health]
    logs = _discover_log_files()
    recent_paths = [row["path"] for row in logs[:2]]
    events = _load_log_events(recent_paths)
    active_runs = list_recent_runs(settings, statuses=["queued", "running"], limit=20).records
    recent_runs = list_recent_runs(settings, limit=20).records
    recent_failures = [item for item in recent_runs if item.status == "failed"][:5]

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
        _invalidate_dashboard_read_models(st.session_state, reason="refresh_all")
        st.rerun()

    with filters:
        st.caption(
            "One-glance health for current lock, storage, run signals, and report inventory."
        )

    with main_col:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Reports", f"{len(reports)}")
        m2.metric("Active Runs", f"{len(active_runs)}")
        m3.metric("Processed", f"{len(processed)}")
        m4.metric("Published", f"{len(published)}")
        m5, m6 = st.columns(2)
        m5.metric("Recent Log Events", f"{len(events)}")
        m6.metric("Failed Runs", f"{len(recent_failures)}")
        st.subheader("Active Runs")
        if active_runs:
            st.dataframe(row_dicts(active_runs), use_container_width=True, hide_index=True)
        else:
            st.caption("No queued or running background jobs.")
        st.subheader("Recent Reports")
        if reports:
            table = []
            for row in reports[:20]:
                table.append(
                    {
                        "title": row.get("title"),
                        "publisher": row.get("publisher"),
                        "analysis_mode": row.get("analysis_mode"),
                        "html_path": row.get("html_path"),
                        "updated_at_utc": _as_utc(row.get("updated_at")),
                    }
                )
            st.dataframe(table, use_container_width=True, hide_index=True)
        else:
            st.info("No report metadata records found.")

    with detail_col:
        st.subheader("System Health")
        st.dataframe(health, use_container_width=True, hide_index=True)
        st.subheader("Recent Failures")
        if recent_failures:
            st.dataframe(row_dicts(recent_failures), use_container_width=True, hide_index=True)
        else:
            st.caption("No failed background runs recorded.")
        st.subheader("Ingest Lock")
        if lock.get("found"):
            st.error(f"Locked by `{lock.get('owner_id')}` (pid={lock.get('pid')})")
        else:
            st.success("No active ingest lock.")
        if logs:
            st.subheader("Log Files")
            st.dataframe(
                [
                    {"path": row["path"], "modified_utc": _as_utc(row.get("mtime_utc"))}
                    for row in logs[:8]
                ],
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
            f"Model `{settings.openai_model}` | temperature `{settings.temperature}` | timeout `{settings.openai_timeout_seconds}`s"
        )

    if clicked:
        response = launch_background_run(
            settings,
            run_type="ingest",
            display_name="Ingest",
            request_payload={
                "folder_id": folder_override.strip(),
                "limit": int(limit),
            },
        )
        _append_terminal(f"Ingest launched: {response.record.run_id}")
        st.success(f"Ingest launched: {response.record.run_id}")

    polled = _selected_ui_run(settings, run_type="ingest")
    run_status = polled.record.status if polled is not None else ""
    done_count = len(INGEST_STEPS) if run_status == "succeeded" else 0
    active_index = 0 if run_status in {"queued", "running"} else None
    error_index = len(INGEST_STEPS) - 1 if run_status == "failed" else None

    with main_col:
        st.subheader("Pipeline Stepper")
        _render_stepper(
            INGEST_STEPS,
            done_count=done_count,
            active_index=active_index,
            error_index=error_index,
        )
        if polled is None:
            st.info("Launch ingest to create a tracked background run.")
        else:
            st.subheader("Selected run summary")
            st.json(polled.record.result_summary)
            if polled.output_chunk is not None:
                st.subheader("Worker output")
                st.code(polled.output_chunk.text or "[worker] no output yet")

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
                "analysis_mode": "vector_store",
            }
        )
        if polled is not None:
            st.subheader("Run record")
            st.json(polled.record.__dict__)


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
        response = launch_background_run(
            settings,
            run_type="candidate_extraction",
            display_name="Candidate extraction",
            request_payload={
                "folder_id": folder_override.strip(),
                "limit": int(limit),
                "file_id": file_id.strip(),
                "pdf_path": local_pdf.strip(),
                "report_id": report_id.strip(),
            },
        )
        _append_terminal(f"Candidate extraction launched: {response.record.run_id}")
        st.success(f"Candidate extraction launched: {response.record.run_id}")

    polled = _selected_ui_run(settings, run_type="candidate_extraction")
    with main_col:
        st.subheader("Pipeline Stepper")
        _render_stepper(
            CANDIDATE_STEPS,
            done_count=(len(CANDIDATE_STEPS) if polled and polled.record.status == "succeeded" else 0),
            active_index=(0 if polled and polled.record.status in {"queued", "running"} else None),
            error_index=(len(CANDIDATE_STEPS) - 1 if polled and polled.record.status == "failed" else None),
        )
        if polled is None:
            st.info("Launch extraction to create a tracked background run.")
        else:
            st.subheader("Selected run summary")
            st.json(polled.record.result_summary)
            if polled.output_chunk is not None:
                st.subheader("Worker output")
                st.code(polled.output_chunk.text or "[worker] no output yet")

    with detail_col:
        st.subheader("Asset Viewer")
        if polled is None:
            st.caption("Run extraction to inspect generated candidate artifacts.")
            return
        if polled.record.artifact_paths:
            st.dataframe(
                [{"path": path} for path in polled.record.artifact_paths],
                use_container_width=True,
                hide_index=True,
            )
            first_json = next(
                (
                    path
                    for path in polled.record.artifact_paths
                    if str(path).strip().lower().endswith(".json")
                ),
                "",
            )
            if first_json:
                payload = _read_json(first_json)
                if payload is not None:
                    st.subheader("Artifact preview")
                    st.json(payload)
        else:
            st.caption("No artifact paths recorded yet.")


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
        _invalidate_dashboard_read_models(st.session_state, reason="refresh_all")
        st.rerun()
    reports = _load_report_rows(settings)
    with filters:
        st.caption(
            "Select one report from the metadata DB and inspect provenance, evidence packs, and cover assets."
        )
    with main_col:
        if not reports:
            st.warning("No reports found in the reports DB.")
            return
        labels = [f"{row['title']} ({row['file_id']})" for row in reports]
        selected_idx = st.selectbox(
            "Report",
            options=list(range(len(labels))),
            index=_selected_report_index(reports),
            format_func=lambda idx: labels[idx],
            help=_tip(
                "Select a report metadata row for detailed provenance and artifact review.",
                "Pick the most recent title to inspect its latest evidence packs.",
            ),
        )
        report = reports[selected_idx]
        ui_state.set_selected_report_id(str(report.get("file_id") or ""))
        st.dataframe(
            [
                {
                    "file_id": report.get("file_id"),
                    "file_name": report.get("file_name"),
                    "title": report.get("title"),
                    "publisher": report.get("publisher"),
                    "analysis_mode": report.get("analysis_mode"),
                    "vector_store_id": report.get("vector_store_id"),
                    "html_path": report.get("html_path"),
                    "updated_at_utc": _as_utc(report.get("updated_at")),
                }
            ],
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
                "file_name": report.get("file_name"),
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
            StateGetRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                file_id=report.get("file_id"),
            ),
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
        file_id = str(report.get("file_id") or "").strip()
        if title and file_id:
            report_slug = Path(html_path).stem if html_path else None
            cover_path = build_cover_asset_path(
                settings.output_dir,
                file_id=file_id,
                title=title,
                publisher=publisher,
                report_slug=report_slug,
            )
            legacy_cover_path = build_cover_asset_path(
                settings.output_dir,
                file_id=file_id,
                title=title,
                publisher=publisher,
            )
            legacy_cover_path_older = (
                Path(settings.output_dir)
                / slugify(f"{title}.pdf")
                / "assets"
                / f"{slugify(f'{publisher} {title}')}.png"
            )
            if cover_path.exists():
                st.image(
                    str(cover_path), caption="Cover preview", use_container_width=True
                )
            elif legacy_cover_path.exists():
                st.image(
                    str(legacy_cover_path),
                    caption="Cover preview",
                    use_container_width=True,
                )
            elif legacy_cover_path_older.exists():
                st.image(
                    str(legacy_cover_path_older),
                    caption="Cover preview",
                    use_container_width=True,
                )


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
        response = launch_background_run(
            settings,
            run_type="cover_images",
            display_name="Cover image generation",
            request_payload={
                "style_config_path": style_path.strip(),
                "limit": int(limit),
                "file_id": file_id.strip(),
            },
        )
        _append_terminal(f"Cover generation launched: {response.record.run_id}")
        st.success(f"Cover generation launched: {response.record.run_id}")

    polled = _selected_ui_run(settings, run_type="cover_images")
    with main_col:
        try:
            style_config = load_cover_styles(
                request=CoverStyleLoadRequest(
                    schema_version="1.0", path=style_path.strip()
                ),
                ctx=_ctx("load_cover_style"),
            )
            st.subheader("Style Summary")
            st.json(
                {
                    "layout": asdict(style_config.config.layout),
                    "categories": sorted(list(style_config.config.categories.keys())),
                }
            )
        except UI_SURFACE_EXCEPTIONS as exc:
            st.warning(f"Unable to load style config: {exc}")
        if polled is None:
            st.info("Launch cover generation to create a tracked background run.")
        else:
            st.subheader("Selected run summary")
            st.json(polled.record.result_summary)
            if polled.output_chunk is not None:
                st.subheader("Worker output")
                st.code(polled.output_chunk.text or "[worker] no output yet")

    with detail_col:
        st.subheader("Asset Viewer")
        generated_paths = [
            path
            for path in (polled.record.artifact_paths if polled is not None else [])
            if str(path).strip()
        ]
        if not generated_paths:
            st.caption("No generated assets recorded yet.")
            return
        labels = [Path(path).name for path in generated_paths]
        selected = st.selectbox(
            "Select output",
            options=list(range(len(labels))),
            format_func=lambda idx: labels[idx],
            help=_tip(
                "Select a generated cover output to preview the PNG artifact.",
                "Pick a report with recent style updates to validate rendering.",
            ),
        )
        selected_path = generated_paths[selected]
        st.code(selected_path)
        if Path(selected_path).exists():
            st.image(selected_path, use_container_width=True)


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
        _invalidate_dashboard_read_models(st.session_state, reason="refresh_all")
        st.rerun()
    reports = _load_report_rows(settings)
    with filters:
        st.caption(
            "Inspect vector store indexing status and evidence packs backing a report."
        )
    if not reports:
        st.warning("No report metadata available.")
        return
    labels = [f"{row['title']} ({row['file_id']})" for row in reports]
    selected_idx = st.selectbox(
        "Report",
        options=list(range(len(labels))),
        index=_selected_report_index(reports),
        format_func=lambda idx: labels[idx],
        help=_tip(
            "Choose which report to inspect for vector indexing and evidence packs.",
            "Select a report that recently completed ingest to confirm indexing status.",
        ),
    )
    report = reports[selected_idx]
    ui_state.set_selected_report_id(str(report.get("file_id") or ""))
    state_row = get_state(
        StateGetRequest(
            schema_version="1.0", state_db=settings.state_db, file_id=report["file_id"]
        ),
        _ctx("analysis_state"),
    )
    evidence_paths = report.get("evidence_pack_paths") or {}

    with main_col:
        st.subheader("Vector Store Status")
        st.dataframe(
            [
                {
                    "file_id": report.get("file_id"),
                    "vector_store_id": report.get("vector_store_id")
                    or (
                        getattr(state_row, "vector_store_id", None)
                        if state_row
                        else None
                    ),
                    "vector_store_status": getattr(
                        state_row, "vector_store_status", None
                    )
                    if state_row
                    else None,
                    "indexed_at_utc": getattr(state_row, "indexed_at_utc", None)
                    if state_row
                    else None,
                    "last_error": getattr(state_row, "last_error", None)
                    if state_row
                    else None,
                }
            ],
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
        st.subheader("Analysis Mode")
        st.info("`vector_store`")
        if state_row:
            st.subheader("State Snapshot")
            st.json(asdict(state_row))


def _render_validation_center(
    settings: Any, publish_settings: Any | None, publish_error: str | None
) -> None:
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
        _invalidate_dashboard_read_models(st.session_state, reason="refresh_all")
        st.rerun()
    with filters:
        st.caption("Validation policy and artifact compliance status across reports.")
    rows = _recent_validation_files(settings.output_dir)
    with main_col:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                _chip_html(
                    f"data_gap_policy={settings.validation_data_gap_policy}",
                    status_chip_level(settings.validation_data_gap_policy),
                ),
                unsafe_allow_html=True,
            )
        with c2:
            if publish_settings:
                st.markdown(
                    _chip_html(
                        f"publish_policy={publish_settings.validation_policy}",
                        status_chip_level(publish_settings.validation_policy),
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    _chip_html("publish_policy=unavailable", "warn"),
                    unsafe_allow_html=True,
                )
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


def _render_publishing_control(
    settings: Any, publish_settings: Any | None, publish_error: str | None
) -> None:
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
        response = launch_background_run(
            settings,
            run_type="publish",
            display_name="Publish queue",
            request_payload={"limit": int(limit)},
        )
        _append_terminal(f"Publish launched: {response.record.run_id}")
        st.success(f"Publish launched: {response.record.run_id}")

    queue_rows: list[dict[str, Any]] = []
    try:
        queue_snapshot = build_publish_queue_snapshot(
            PublishQueueRequest(
                schema_version="1.0",
                output_dir=settings.output_dir,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                post_type=(
                    publish_settings.wp.post_type
                    if publish_settings is not None
                    else "ml_report"
                ),
            ),
            _ctx("publish_queue"),
        )
        queue_rows = row_dicts(queue_snapshot.items)
    except AppError:
        queue_rows = []

    with main_col:
        st.subheader("Publish Queue")
        if queue_rows:
            st.dataframe(queue_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No HTML files found in output directory.")
        polled = _selected_ui_run(settings, run_type="publish")
        if polled is not None:
            st.subheader("Selected run summary")
            st.json(polled.record.result_summary)
            if polled.output_chunk is not None:
                st.subheader("Worker output")
                st.code(polled.output_chunk.text or "[worker] no output yet")

    with detail_col:
        st.subheader("Settings Summary")
        if publish_settings:
            st.json(
                {
                    "site_url": publish_settings.wp.site_url,
                    "username": publish_settings.wp.username,
                    "post_status": publish_settings.wp.post_status,
                    "post_type": publish_settings.wp.post_type,
                    "validation_policy": publish_settings.validation_policy,
                }
            )
        else:
            st.error(f"Publish settings unavailable: {publish_error}")
        if can_publish and polled is not None:
            st.subheader("Artifacts")
            st.dataframe(
                [{"path": path} for path in polled.record.artifact_paths],
                use_container_width=True,
                hide_index=True,
            )


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
        st.caption(
            "View category mapping source and trigger recategorize / WordPress category sync."
        )
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
                    settings=settings,
                )
            )
            st.session_state["last_recategorize_outcomes"] = outcomes
            _invalidate_dashboard_read_models(st.session_state, reason="recategorize")
            _append_terminal(f"Recategorize complete. outcomes={len(outcomes)}")
            st.success(f"Recategorization completed for {len(outcomes)} reports.")
        except UI_SURFACE_EXCEPTIONS as exc:
            _append_terminal(f"Recategorize failed: {exc}")
            st.error(str(exc))

    if sync_clicked and publish_settings:
        _append_terminal("WP category sync requested from UI.")
        try:
            wp_sync_outcomes = run_update_wp_categories(publish_settings)
            st.session_state["last_wp_sync_outcomes"] = wp_sync_outcomes
            _invalidate_dashboard_read_models(st.session_state, reason="publish")
            _append_terminal(
                f"WP category sync complete. outcomes={len(wp_sync_outcomes)}"
            )
            st.success(
                f"WordPress category sync completed for {len(wp_sync_outcomes)} reports."
            )
        except UI_SURFACE_EXCEPTIONS as exc:
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
    categories = row_dicts(mapping_response.mappings.categories)

    with main_col:
        st.subheader("Category Mapping")
        st.dataframe(categories, use_container_width=True, hide_index=True)
        recat = st.session_state.get("last_recategorize_outcomes", [])
        if recat:
            st.subheader("Recategorize Outcomes")
            st.dataframe(row_dicts(recat), use_container_width=True, hide_index=True)
    with detail_col:
        st.subheader("WP Sync")
        if publish_settings is None:
            st.caption("Publish settings missing; WP sync disabled.")
        sync = st.session_state.get("last_wp_sync_outcomes", [])
        if sync:
            st.dataframe(row_dicts(sync), use_container_width=True, hide_index=True)


def _load_ledger_entries(
    ledger_path: str, *, limit: int = 2000
) -> list[dict[str, Any]]:
    response = load_ledger_entries(
        LedgerEntriesLoadRequest(
            schema_version="1.0", ledger_path=ledger_path, limit=limit
        ),
        _ctx("load_ledger_entries"),
    )
    return response.entries


def _render_cost_and_usage(settings: Any) -> None:
    selected_run_id = ui_state.get_selected_run_id()
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
            default_mode = "run_id" if selected_run_id else "date"
            filter_mode = st.segmented_control(
                "Filter Mode",
                options=["date", "run_id"],
                default=default_mode,
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
                    value=selected_run_id,
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
            resolved_run_id = (
                RunId(run_id_value) if filter_mode == "run_id" and run_id_value else None
            )
            reporting = run_cost_reporting(
                CostReportingRequest(
                    schema_version="1.0",
                    report_request=CostReportRequest(
                        schema_version="1.0",
                        ledger_path=settings.cost_ledger_path,
                        date_utc=filter_value if filter_mode == "date" else None,
                        run_id=resolved_run_id,
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
        except UI_SURFACE_EXCEPTIONS as exc:
            _append_terminal(f"Cost report failed: {exc}")
            st.error(str(exc))

    ledger_rows = _load_ledger_entries(settings.cost_ledger_path)
    log_files = _discover_log_files()
    event_rows = _load_log_events(
        [row["path"] for row in log_files[:3]], max_lines_per_file=4000
    )
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
            daily_points = [
                {"date": key, "usd": value.total_usd}
                for key, value in rollup.totals_by_date.items()
            ]
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
        st.code(
            f"ledger: {settings.cost_ledger_path}\ndaily: {settings.cost_daily_path}"
        )


def _render_logs_and_terminal() -> None:
    default_run_id = ui_state.get_selected_run_id()
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
        _invalidate_dashboard_read_models(st.session_state, reason="refresh_all")
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
                value=default_run_id,
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
        st.markdown(
            '<div class="ml-note">Sensitive values are redacted in structured logs as <code>***REDACTED***</code>.</div>',
            unsafe_allow_html=True,
        )

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
                        "timestamp": row.get("timestamp_utc")
                        or row.get("timestamp_hms"),
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
            if any(
                key in fields
                for key in (
                    "raw_response",
                    "response",
                    "provider_response",
                    "model_response",
                )
            ):
                raw_candidates.append(row)
        st.subheader("Raw Model Output Viewer")
        if raw_candidates:
            options = [
                f"{item.get('event')} | {item.get('task_id')}"
                for item in raw_candidates
            ]
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


def _render_structured_config_form_legacy(
    config_payload: dict[str, Any], *, editor_key: str
) -> None:
    working = deepcopy(config_payload)
    if not isinstance(working.get("paths"), dict):
        working["paths"] = {}
    if not isinstance(working.get("ingest"), dict):
        working["ingest"] = {}
    if not isinstance(working.get("openai_models"), dict):
        working["openai_models"] = {}
    if not isinstance(working.get("rank"), dict):
        working["rank"] = {}
    if not isinstance(working.get("publish"), dict):
        working["publish"] = {}
    if not isinstance(working.get("analysis"), dict):
        working["analysis"] = {}
    if not isinstance(working.get("cost"), dict):
        working["cost"] = {}

    paths = _as_mapping(working.get("paths"))
    ingest = _as_mapping(working.get("ingest"))
    if not isinstance(ingest.get("drive"), dict):
        ingest["drive"] = {}
    if not isinstance(ingest.get("pdf_text"), dict):
        ingest["pdf_text"] = {}
    if not isinstance(ingest.get("validation"), dict):
        ingest["validation"] = {}
    if not isinstance(ingest.get("contents_page"), dict):
        ingest["contents_page"] = {}
    if not isinstance(ingest.get("evidence_packs"), dict):
        ingest["evidence_packs"] = {}
    if not isinstance(ingest.get("artifacts"), dict):
        ingest["artifacts"] = {}
    drive = _as_mapping(ingest.get("drive"))
    pdf_text = _as_mapping(ingest.get("pdf_text"))
    ingest_validation = _as_mapping(ingest.get("validation"))
    contents_page = _as_mapping(ingest.get("contents_page"))
    evidence_packs = _as_mapping(ingest.get("evidence_packs"))
    artifacts = _as_mapping(ingest.get("artifacts"))
    openai_models = _as_mapping(working.get("openai_models"))
    rank = _as_mapping(working.get("rank"))
    publish = _as_mapping(working.get("publish"))
    if not isinstance(publish.get("wp"), dict):
        publish["wp"] = {}
    if not isinstance(publish.get("validation"), dict):
        publish["validation"] = {}
    wp = _as_mapping(publish.get("wp"))
    publish_validation = _as_mapping(publish.get("validation"))
    analysis = _as_mapping(working.get("analysis"))
    cost = _as_mapping(working.get("cost"))
    pricing = _as_mapping(cost.get("pricing"))

    st.markdown(
        '<div class="ml-panel"><h4>Structured Editor</h4><p>Edit config by fields, apply changes, then use YAML tab to save.</p></div>',
        unsafe_allow_html=True,
    )

    with st.form("app_yaml_structured_form", border=False):
        st.subheader("Core")
        core_col1, core_col2, core_col3 = st.columns(3, gap="large")
        with core_col1:
            schema_version = st.text_input(
                "Schema Version", value=_as_str(working.get("schema_version"), "1.0")
            )
        with core_col2:
            ingest_openai_model = st.text_input(
                "Ingest OpenAI Model",
                value=_as_str(ingest.get("openai_model"), "gpt-5-mini"),
            )
        with core_col3:
            rank_model = st.text_input(
                "Rank Model", value=_as_str(rank.get("model"), ingest_openai_model)
            )

        with st.expander("Paths", expanded=True):
            p1, p2 = st.columns(2, gap="large")
            with p1:
                path_output_dir = st.text_input(
                    "Output Dir", value=_as_str(paths.get("output_dir"), "./out")
                )
                path_state_db = st.text_input(
                    "State DB",
                    value=_as_str(paths.get("state_db"), "./state/index.sqlite"),
                )
                path_category_mappings = st.text_input(
                    "Category Mappings YAML",
                    value=_as_str(
                        paths.get("category_mappings"),
                        "./src/config/category-mappings.yaml",
                    ),
                )
                path_cover_styles = st.text_input(
                    "Cover Styles YAML",
                    value=_as_str(
                        paths.get("cover_styles"), "./src/config/cover-styles.yaml"
                    ),
                )
            with p2:
                path_cache_dir = st.text_input(
                    "Cache Dir", value=_as_str(paths.get("cache_dir"), "./cache")
                )
                path_reports_db = st.text_input(
                    "Reports DB",
                    value=_as_str(paths.get("reports_db"), "./state/reports.sqlite"),
                )
                path_html_tag_acronyms = st.text_input(
                    "HTML Tag Acronyms YAML",
                    value=_as_str(
                        paths.get("html_tag_acronyms"),
                        "./src/config/html-tag-acronyms.yaml",
                    ),
                )
                path_ingest_lock = st.text_input(
                    "Ingest Lock Path",
                    value=_as_str(paths.get("ingest_lock"), "./state/ingest.lock"),
                )

        with st.expander("Ingest Core", expanded=True):
            i1, i2, i3 = st.columns(3, gap="large")
            with i1:
                ingest_google_sa_path = st.text_input(
                    "Google SA Path",
                    value=_as_str(ingest.get("google_sa_path"), "./sa.json"),
                )
                ingest_temperature = st.number_input(
                    "Ingest Temperature",
                    value=_as_float(ingest.get("temperature"), 1.0),
                    step=0.1,
                    format="%.3f",
                )
                ingest_batch_limit = st.number_input(
                    "Batch Limit",
                    value=_as_int(ingest.get("batch_limit"), 20),
                    min_value=1,
                    step=1,
                )
                ingest_worker_limit = st.number_input(
                    "Worker Limit",
                    value=_as_int(ingest.get("worker_limit"), 2),
                    min_value=1,
                    step=1,
                )
            with i2:
                ingest_gdrive_folder_id = st.text_input(
                    "GDrive Folder ID",
                    value=_as_str(ingest.get("gdrive_folder_id"), ""),
                )
                ingest_timeout_seconds = st.number_input(
                    "OpenAI Timeout Seconds",
                    value=_as_float(ingest.get("timeout_seconds"), 600.0),
                    min_value=1.0,
                    step=1.0,
                    format="%.1f",
                )
                ingest_report_worker_limit = st.number_input(
                    "Report Worker Limit",
                    value=_as_int(ingest.get("report_worker_limit"), 2),
                    min_value=1,
                    step=1,
                )
                ingest_lock_ttl_seconds = st.number_input(
                    "Lock TTL Seconds",
                    value=_as_float(ingest.get("lock_ttl_seconds"), 7200.0),
                    min_value=0.0,
                    step=60.0,
                    format="%.1f",
                )
            with i3:
                ingest_seed_text = st.text_input(
                    "Ingest Seed (blank for null)",
                    value=""
                    if ingest.get("seed") in {None, ""}
                    else _as_str(ingest.get("seed")),
                )
                ingest_cover_cache_enabled = st.checkbox(
                    "Cover Cache Enabled",
                    value=_as_bool(ingest.get("cover_cache_enabled"), True),
                )

        with st.expander("Drive", expanded=False):
            d1, d2 = st.columns(2, gap="large")
            with d1:
                drive_supports_all_drives = st.checkbox(
                    "Supports All Drives",
                    value=_as_bool(drive.get("supports_all_drives"), True),
                )
                drive_include_items_from_all_drives = st.checkbox(
                    "Include Items From All Drives",
                    value=_as_bool(drive.get("include_items_from_all_drives"), True),
                )
            with d2:
                drive_id = st.text_input(
                    "Drive ID (optional)", value=_as_str(drive.get("drive_id"), "")
                )
                drive_list_mode = st.selectbox(
                    "Drive List Mode",
                    options=["metadata", "full"],
                    index=0
                    if _as_str(drive.get("list_mode"), "metadata").strip().lower()
                    != "full"
                    else 1,
                )

        with st.expander("PDF Text & Contents", expanded=False):
            pt1, pt2 = st.columns(2, gap="large")
            with pt1:
                pdf_text_max_pages = st.number_input(
                    "PDF Text Max Pages",
                    value=_as_int(pdf_text.get("max_pages"), 5),
                    min_value=1,
                    step=1,
                )
                pdf_text_max_chars = st.number_input(
                    "PDF Text Max Chars",
                    value=_as_int(pdf_text.get("max_chars"), 80000),
                    min_value=1000,
                    step=1000,
                )
                pdf_text_min_density = st.number_input(
                    "PDF Text Min Density",
                    value=_as_float(pdf_text.get("min_density"), 250.0),
                    min_value=0.0,
                    step=10.0,
                )
                pdf_text_sample_pages = st.number_input(
                    "PDF Text Sample Pages",
                    value=_as_int(pdf_text.get("sample_pages"), 3),
                    min_value=1,
                    step=1,
                )
            with pt2:
                contents_max_pages = st.number_input(
                    "Contents Max Pages",
                    value=_as_int(contents_page.get("max_pages"), 8),
                    min_value=1,
                    step=1,
                )
                contents_min_headings = st.number_input(
                    "Contents Min Headings",
                    value=_as_int(contents_page.get("min_headings"), 3),
                    min_value=1,
                    step=1,
                )
                contents_preview_enabled = st.checkbox(
                    "Contents Preview Enabled",
                    value=_as_bool(contents_page.get("preview_enabled"), True),
                )
                contents_render_dpi = st.number_input(
                    "Contents Render DPI",
                    value=_as_int(contents_page.get("render_dpi"), 144),
                    min_value=72,
                    step=1,
                )
            raw_keywords = contents_page.get("keywords")
            keywords_default: list[Any] = (
                raw_keywords if isinstance(raw_keywords, list) else []
            )
            contents_keywords_text = st.text_area(
                "Contents Keywords (one per line)",
                value="\n".join(
                    str(item).strip() for item in keywords_default if str(item).strip()
                ),
                height=100,
            )

        with st.expander("Validation + Parallelism", expanded=False):
            vp1, vp2, vp3 = st.columns(3, gap="large")
            with vp1:
                validation_data_gap_policy = st.selectbox(
                    "Validation Data Gap Policy",
                    options=["warn", "fail"],
                    index=0
                    if _as_str(ingest_validation.get("data_gap_policy"), "warn")
                    .strip()
                    .lower()
                    != "fail"
                    else 1,
                )
            with vp2:
                evidence_parallel_workers = st.number_input(
                    "Evidence Packs Parallel Workers",
                    value=_as_int(evidence_packs.get("parallel_workers"), 3),
                    min_value=1,
                    step=1,
                )
                evidence_global_max_in_flight = st.number_input(
                    "Evidence Packs Global Max In Flight",
                    value=_as_int(evidence_packs.get("global_max_in_flight"), 2),
                    min_value=1,
                    step=1,
                )
                evidence_global_min_interval_ms = st.number_input(
                    "Evidence Packs Global Min Interval (ms)",
                    value=_as_int(evidence_packs.get("global_min_interval_ms"), 250),
                    min_value=0,
                    step=1,
                )
            with vp3:
                artifact_parallel_workers = st.number_input(
                    "Artifacts Parallel Workers",
                    value=_as_int(artifacts.get("parallel_workers"), 4),
                    min_value=1,
                    step=1,
                )
                artifact_global_max_in_flight = st.number_input(
                    "Artifacts Global Max In Flight",
                    value=_as_int(artifacts.get("global_max_in_flight"), 2),
                    min_value=1,
                    step=1,
                )
                artifact_global_min_interval_ms = st.number_input(
                    "Artifacts Global Min Interval (ms)",
                    value=_as_int(artifacts.get("global_min_interval_ms"), 250),
                    min_value=0,
                    step=1,
                )

        with st.expander("OpenAI Namespace Model Overrides", expanded=False):
            openai_rows = [
                {"namespace": key, "model": value}
                for key, value in sorted(openai_models.items())
            ]
            openai_models_editor = st.data_editor(
                openai_rows,
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
            )

        with st.expander("Rank", expanded=False):
            r1, r2, r3 = st.columns(3, gap="large")
            with r1:
                rank_temperature = st.number_input(
                    "Rank Temperature",
                    value=_as_float(rank.get("temperature"), 1.0),
                    step=0.1,
                    format="%.3f",
                )
                rank_timeout_seconds = st.number_input(
                    "Rank Timeout Seconds",
                    value=_as_float(rank.get("timeout_seconds"), 600.0),
                    min_value=1.0,
                    step=1.0,
                    format="%.1f",
                )
                rank_seed_text = st.text_input(
                    "Rank Seed (blank for null)",
                    value=""
                    if rank.get("seed") in {None, ""}
                    else _as_str(rank.get("seed")),
                )
                rank_max_candidates = st.number_input(
                    "Rank Max Candidates",
                    value=_as_int(rank.get("max_candidates"), 40),
                    min_value=1,
                    step=1,
                )
                rank_selected_max = st.number_input(
                    "Rank Selected Max",
                    value=_as_int(rank.get("selected_max"), 5),
                    min_value=1,
                    step=1,
                )
            with r2:
                rank_min_overall_score = st.number_input(
                    "Rank Min Overall Score",
                    value=_as_int(rank.get("min_overall_score"), 78),
                    min_value=0,
                    max_value=100,
                    step=1,
                )
                rank_min_quality_score = st.number_input(
                    "Rank Min Quality Score",
                    value=_as_int(rank.get("min_quality_score"), 75),
                    min_value=0,
                    max_value=100,
                    step=1,
                )
                rank_min_insight_score = st.number_input(
                    "Rank Min Insight Score",
                    value=_as_int(rank.get("min_insight_score"), 75),
                    min_value=0,
                    max_value=100,
                    step=1,
                )
                rank_min_data_score = st.number_input(
                    "Rank Min Data Score",
                    value=_as_int(rank.get("min_data_score"), 70),
                    min_value=0,
                    max_value=100,
                    step=1,
                )
            with r3:
                rank_crop_refine_enabled = st.checkbox(
                    "Crop Refine Enabled",
                    value=_as_bool(rank.get("crop_refine_enabled"), True),
                )
                rank_crop_refine_mode = st.selectbox(
                    "Crop Refine Mode",
                    options=["adaptive", "always", "off"],
                    index=["adaptive", "always", "off"].index(
                        _as_str(rank.get("crop_refine_mode"), "adaptive")
                        .strip()
                        .lower()
                    )
                    if _as_str(rank.get("crop_refine_mode"), "adaptive").strip().lower()
                    in {"adaptive", "always", "off"}
                    else 0,
                )
                rank_crop_refine_page_dpi = st.number_input(
                    "Crop Refine Page DPI",
                    value=_as_int(rank.get("crop_refine_page_dpi"), 110),
                    min_value=72,
                    step=1,
                )
                rank_crop_refine_temperature = st.number_input(
                    "Crop Refine Temperature",
                    value=_as_float(rank.get("crop_refine_temperature"), 0.0),
                    step=0.1,
                    format="%.3f",
                )
                rank_crop_refine_timeout_seconds = st.number_input(
                    "Crop Refine Timeout Seconds",
                    value=_as_float(
                        rank.get("crop_refine_timeout_seconds"),
                        _as_float(rank.get("timeout_seconds"), 600.0),
                    ),
                    min_value=1.0,
                    step=1.0,
                    format="%.1f",
                )

        with st.expander("Publish", expanded=False):
            pub1, pub2 = st.columns(2, gap="large")
            with pub1:
                wp_site_url = st.text_input(
                    "WordPress Site URL", value=_as_str(wp.get("site_url"), "")
                )
                wp_username = st.text_input(
                    "WordPress Username", value=_as_str(wp.get("username"), "")
                )
                wp_post_status = st.selectbox(
                    "WordPress Post Status",
                    options=["publish", "draft", "pending", "private"],
                    index=0
                    if _as_str(wp.get("post_status"), "publish")
                    not in {"publish", "draft", "pending", "private"}
                    else ["publish", "draft", "pending", "private"].index(
                        _as_str(wp.get("post_status"), "publish")
                    ),
                )
                wp_post_type = st.text_input(
                    "WordPress Post Type Endpoint",
                    value=_as_str(wp.get("post_type"), "ml_report"),
                    help="REST endpoint slug used for publishing (for example: ml_report or posts).",
                )
            with pub2:
                publish_validation_policy = st.selectbox(
                    "Publish Validation Policy",
                    options=["block", "warn"],
                    index=0
                    if _as_str(publish_validation.get("policy"), "block")
                    .strip()
                    .lower()
                    != "warn"
                    else 1,
                )

        with st.expander("Analysis & Cost", expanded=False):
            ac1, ac2 = st.columns(2, gap="large")
            with ac1:
                analysis_vector_store_keep = st.checkbox(
                    "Vector Store Keep",
                    value=_as_bool(analysis.get("vector_store_keep"), True),
                )
                analysis_cost_ledger_path = st.text_input(
                    "Cost Ledger Path",
                    value=_as_str(
                        analysis.get("cost_ledger_path"), "./out/cost-ledger.jsonl"
                    ),
                )
            with ac2:
                cost_daily_path = st.text_input(
                    "Cost Daily Path",
                    value=_as_str(cost.get("daily_path"), "./out/cost-daily.json"),
                )
            pricing_rows = []
            for model, model_prices in sorted(pricing.items()):
                if not isinstance(model_prices, dict):
                    continue
                pricing_rows.append(
                    {
                        "model": str(model),
                        "input_tokens_per_1k_usd": _as_float(
                            model_prices.get("input_tokens_per_1k_usd"), 0.0
                        ),
                        "output_tokens_per_1k_usd": _as_float(
                            model_prices.get("output_tokens_per_1k_usd"), 0.0
                        ),
                        "tool_call_usd": _as_float(
                            model_prices.get("tool_call_usd"), 0.0
                        ),
                    }
                )
            pricing_editor = st.data_editor(
                pricing_rows,
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
            )

        apply_clicked = st.form_submit_button(
            "Apply Structured Changes To YAML",
            type="secondary",
            use_container_width=True,
        )

    if not apply_clicked:
        return

    errors: list[str] = []
    ingest_seed = _optional_int_from_text(
        ingest_seed_text, field="Ingest seed", errors=errors
    )
    rank_seed = _optional_int_from_text(
        rank_seed_text, field="Rank seed", errors=errors
    )
    keywords = normalize_text_lines(contents_keywords_text)
    if not keywords:
        errors.append("Contents keywords must contain at least one keyword.")
    openai_models_map = mapping_from_editor_records(
        openai_models_editor,
        key_field="namespace",
        value_field="model",
    )
    pricing_map, pricing_errors = pricing_from_editor_records(pricing_editor)
    errors.extend(pricing_errors)

    if errors:
        for message in errors:
            st.error(message)
        return

    working["schema_version"] = schema_version.strip() or "1.0"
    paths["output_dir"] = path_output_dir.strip()
    paths["cache_dir"] = path_cache_dir.strip()
    paths["state_db"] = path_state_db.strip()
    paths["reports_db"] = path_reports_db.strip()
    paths["category_mappings"] = path_category_mappings.strip()
    paths["html_tag_acronyms"] = path_html_tag_acronyms.strip()
    paths["cover_styles"] = path_cover_styles.strip()
    paths["ingest_lock"] = path_ingest_lock.strip()
    working["paths"] = paths

    ingest["google_sa_path"] = ingest_google_sa_path.strip()
    ingest["gdrive_folder_id"] = ingest_gdrive_folder_id.strip()
    ingest["openai_model"] = ingest_openai_model.strip()
    ingest["temperature"] = float(ingest_temperature)
    ingest["timeout_seconds"] = float(ingest_timeout_seconds)
    ingest["lock_ttl_seconds"] = float(ingest_lock_ttl_seconds)
    ingest["seed"] = ingest_seed
    ingest["batch_limit"] = int(ingest_batch_limit)
    ingest["worker_limit"] = int(ingest_worker_limit)
    ingest["report_worker_limit"] = int(ingest_report_worker_limit)
    ingest["cover_cache_enabled"] = bool(ingest_cover_cache_enabled)

    drive["supports_all_drives"] = bool(drive_supports_all_drives)
    drive["include_items_from_all_drives"] = bool(drive_include_items_from_all_drives)
    drive["drive_id"] = drive_id.strip()
    drive["list_mode"] = drive_list_mode
    ingest["drive"] = drive

    pdf_text["max_pages"] = int(pdf_text_max_pages)
    pdf_text["max_chars"] = int(pdf_text_max_chars)
    pdf_text["min_density"] = float(pdf_text_min_density)
    pdf_text["sample_pages"] = int(pdf_text_sample_pages)
    ingest["pdf_text"] = pdf_text

    ingest_validation["data_gap_policy"] = validation_data_gap_policy
    ingest["validation"] = ingest_validation

    contents_page["max_pages"] = int(contents_max_pages)
    contents_page["min_headings"] = int(contents_min_headings)
    contents_page["keywords"] = keywords
    contents_page["preview_enabled"] = bool(contents_preview_enabled)
    contents_page["render_dpi"] = int(contents_render_dpi)
    ingest["contents_page"] = contents_page

    evidence_packs["parallel_workers"] = int(evidence_parallel_workers)
    evidence_packs["global_max_in_flight"] = int(evidence_global_max_in_flight)
    evidence_packs["global_min_interval_ms"] = int(evidence_global_min_interval_ms)
    ingest["evidence_packs"] = evidence_packs

    artifacts["parallel_workers"] = int(artifact_parallel_workers)
    artifacts["global_max_in_flight"] = int(artifact_global_max_in_flight)
    artifacts["global_min_interval_ms"] = int(artifact_global_min_interval_ms)
    ingest["artifacts"] = artifacts
    working["ingest"] = ingest

    working["openai_models"] = openai_models_map

    rank["model"] = rank_model.strip() or ingest_openai_model.strip()
    rank["temperature"] = float(rank_temperature)
    rank["timeout_seconds"] = float(rank_timeout_seconds)
    rank["seed"] = rank_seed
    rank["max_candidates"] = int(rank_max_candidates)
    rank["selected_max"] = int(rank_selected_max)
    rank["min_overall_score"] = int(rank_min_overall_score)
    rank["min_quality_score"] = int(rank_min_quality_score)
    rank["min_insight_score"] = int(rank_min_insight_score)
    rank["min_data_score"] = int(rank_min_data_score)
    rank["crop_refine_enabled"] = bool(rank_crop_refine_enabled)
    rank["crop_refine_mode"] = rank_crop_refine_mode
    rank["crop_refine_page_dpi"] = int(rank_crop_refine_page_dpi)
    rank["crop_refine_temperature"] = float(rank_crop_refine_temperature)
    rank["crop_refine_timeout_seconds"] = float(rank_crop_refine_timeout_seconds)
    working["rank"] = rank

    wp["site_url"] = wp_site_url.strip()
    wp["username"] = wp_username.strip()
    wp["post_status"] = wp_post_status
    wp["post_type"] = wp_post_type.strip().strip("/") or "ml_report"
    publish["wp"] = wp
    publish_validation["policy"] = publish_validation_policy
    publish["validation"] = publish_validation
    working["publish"] = publish

    analysis["vector_store_keep"] = bool(analysis_vector_store_keep)
    analysis["cost_ledger_path"] = analysis_cost_ledger_path.strip()
    working["analysis"] = analysis

    cost["daily_path"] = cost_daily_path.strip()
    cost["pricing"] = pricing_map
    working["cost"] = cost

    rendered_yaml = yaml.safe_dump(working, sort_keys=False, allow_unicode=False)
    st.session_state[editor_key] = rendered_yaml
    st.session_state["app_yaml_notice"] = (
        "Structured changes applied to YAML editor. Open 'YAML Editor' tab and click Save."
    )
    st.rerun()


def _render_settings_and_prompts_legacy(
    settings: Any | None,
    publish_settings: Any | None,
    publish_error: str | None,
    settings_error: str | None = None,
) -> None:
    clicked, filters, main_col, detail_col = _page_shell(
        "Settings & Prompts",
        status_label="Config Error" if settings_error else "Editable",
        status_level="error" if settings_error else "success",
        primary_action="Reload From Disk",
        primary_help=_tip(
            "Reload app.yaml editor content from disk and discard unsaved changes.",
            "Use after external file edits or after a failed save attempt.",
        ),
        primary_key="reload_app_yaml",
    )
    with filters:
        st.caption(
            "Edit every key in `src/config/app.yaml`, save from UI, and inspect prompt/runtime state."
        )

    config_doc, config_error = _try_read_app_config()
    editor_key = "app_yaml_editor_text"
    saved_key = "app_yaml_saved_text"
    if config_doc and editor_key not in st.session_state:
        st.session_state[editor_key] = config_doc.content
    if config_doc and saved_key not in st.session_state:
        st.session_state[saved_key] = config_doc.content
    if clicked and config_doc:
        st.session_state[editor_key] = config_doc.content
        st.session_state[saved_key] = config_doc.content
        st.session_state["app_yaml_notice"] = "Reloaded editor content from disk."
    elif clicked and config_error:
        st.session_state["app_yaml_notice"] = f"Reload failed: {config_error}"

    try:
        prompt_namespaces = list_prompt_namespaces(
            PromptNamespaceListRequest(
                schema_version="1.0", reload_if_changed=True, force_reload=False
            ),
            _ctx("prompt_namespaces"),
        )
        prompt_rows = row_dicts(prompt_namespaces.namespaces)
        prompt_error = None
    except UI_SURFACE_EXCEPTIONS as exc:  # pragma: no cover - runtime safeguard for UI
        prompt_rows = []
        prompt_error = str(exc)
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
    if settings:
        sanitized_settings = asdict(settings)
        sanitized_settings["openai_api_key"] = "***REDACTED***"
    else:
        sanitized_settings = {"error": settings_error or "ingest settings unavailable"}
    if publish_settings:
        pub_data = asdict(publish_settings)
        pub_data["wp"]["app_password"] = (
            "***REDACTED***" if pub_data["wp"].get("app_password") else None
        )
        pub_data["wp"]["bearer_token"] = (
            "***REDACTED***" if pub_data["wp"].get("bearer_token") else None
        )
    else:
        pub_data = {"error": publish_error or "publish settings unavailable"}
    if "app_yaml_notice" in st.session_state:
        st.info(str(st.session_state.pop("app_yaml_notice")))

    with main_col:
        if settings_error:
            st.error(f"Runtime settings validation failed: {settings_error}")
        if config_error:
            st.error(f"Unable to load app.yaml: {config_error}")

        st.markdown(
            '<div class="ml-panel"><h4>Config Studio</h4><p>Use the YAML editor below to update any key in app.yaml, then save directly from this page.</p></div>',
            unsafe_allow_html=True,
        )
        form_payload = config_doc.payload if config_doc else {}
        form_payload_source = "disk"
        form_payload_error = ""
        editor_candidate = str(st.session_state.get(editor_key, "") or "")
        if editor_candidate.strip():
            try:
                parsed_editor_payload = yaml.safe_load(editor_candidate) or {}
                if isinstance(parsed_editor_payload, dict):
                    form_payload = parsed_editor_payload
                    form_payload_source = "yaml editor"
                else:
                    form_payload_error = "Current YAML editor content root is not a mapping; form is using disk payload."
            except yaml.YAMLError:
                form_payload_error = "Current YAML editor content is invalid; form is using disk payload."

        tab_form, tab_editor, tab_runtime, tab_prompts = st.tabs(
            ["Structured Form", "YAML Editor", "Runtime Snapshot", "Prompt Registry"]
        )
        with tab_form:
            st.caption(
                f"Form source: {form_payload_source}. Apply changes to update the YAML editor."
            )
            if form_payload_error:
                st.warning(form_payload_error)
            _render_structured_config_form(form_payload, editor_key=editor_key)

        with tab_editor:
            if editor_key not in st.session_state:
                st.session_state[editor_key] = config_doc.content if config_doc else ""
            if saved_key not in st.session_state:
                st.session_state[saved_key] = st.session_state.get(editor_key, "")
            editor_text = st.text_area(
                "app.yaml",
                key=editor_key,
                height=650,
                help=_tip(
                    "Full app.yaml editor. Every config key is editable here.",
                    "Change ingest.batch_limit or rank.* values, then save.",
                ),
            )
            unsaved = editor_text != st.session_state.get(saved_key, "")
            act_col, backup_col, dirty_col = st.columns([1.2, 1.3, 2.5], gap="large")
            with backup_col:
                make_backup = st.checkbox(
                    "Create backup on save",
                    value=True,
                    key="app_yaml_make_backup",
                    help=_tip(
                        "When enabled, saves a timestamped `.bak` copy beside app.yaml before overwriting.",
                        "Disable only for quick iterative edits.",
                    ),
                )
            with act_col:
                save_clicked = st.button(
                    "Save app.yaml",
                    type="primary",
                    use_container_width=True,
                    help=_tip(
                        "Validate YAML structure and write to app.yaml.",
                        "Invalid YAML is rejected and file is unchanged.",
                    ),
                )
            with dirty_col:
                if unsaved:
                    st.warning("Unsaved changes detected.")
                else:
                    st.success("Editor is in sync with disk.")
            if save_clicked:
                save_response, save_error = _try_write_app_config(
                    editor_text, make_backup=make_backup
                )
                if save_error:
                    st.error(f"Save failed: {save_error}")
                elif save_response is None:
                    st.error("Save failed: empty response from config service.")
                else:
                    refreshed_doc, refresh_error = _try_read_app_config()
                    if refreshed_doc and not refresh_error:
                        st.session_state[editor_key] = refreshed_doc.content
                        st.session_state[saved_key] = refreshed_doc.content
                    else:
                        st.session_state[saved_key] = editor_text
                    _invalidate_dashboard_read_models(
                        st.session_state, reason="settings"
                    )
                    _append_terminal(
                        f"app.yaml saved ({save_response.bytes_written} bytes, keys={len(save_response.top_level_keys)})"
                    )
                    detail = (
                        f" Backup: `{save_response.backup_path}`."
                        if save_response.backup_path
                        else ""
                    )
                    st.success(f"Saved `{save_response.path}`.{detail}")
                    candidate_settings, candidate_error = _try_load_settings()
                    if candidate_error:
                        st.warning(
                            f"Saved, but runtime settings are currently invalid: {candidate_error}"
                        )
                    elif candidate_settings:
                        st.success("Runtime settings load check passed.")

        with tab_runtime:
            st.subheader("Resolved Settings")
            st.json({"ingest": sanitized_settings, "publish": pub_data})
            st.subheader("Top-Level app.yaml Keys")
            st.code(
                "\n".join(str(key) for key in config_doc.payload.keys())
                if config_doc
                else ""
            )

        with tab_prompts:
            if prompt_error:
                st.error(f"Prompt namespace load failed: {prompt_error}")
            elif prompt_rows:
                st.dataframe(prompt_rows, use_container_width=True, hide_index=True)
            else:
                st.caption("No prompt namespaces discovered.")

    with detail_col:
        st.subheader("Config File")
        if config_doc:
            st.metric("Size", f"{config_doc.size_bytes:,} bytes")
            st.metric("Modified (UTC)", _as_utc(config_doc.modified_utc) or "n/a")
            st.code(config_doc.path)
        st.subheader("Env Override Badges")
        badges = []
        for key in env_keys:
            source = "env" if os.getenv(key, "").strip() else "yaml/default"
            level = "success" if source == "env" else "info"
            badges.append(
                {
                    "key": key,
                    "source": source,
                    "chip": _chip_html(source.upper(), level),
                }
            )
        for row in badges:
            st.markdown(f"{row['key']} {row['chip']}", unsafe_allow_html=True)


def _render_structured_config_form(
    config_payload: dict[str, Any], *, editor_key: str
) -> None:
    from src.ui.settings_page import render_structured_config_form

    render_structured_config_form(config_payload=config_payload, editor_key=editor_key)


def _render_settings_and_prompts(
    settings: Any | None,
    publish_settings: Any | None,
    publish_error: str | None,
    settings_error: str | None = None,
) -> None:
    from src.ui.settings_page import render_settings_and_prompts

    render_settings_and_prompts(
        settings=settings,
        publish_settings=publish_settings,
        publish_error=publish_error,
        settings_error=settings_error,
    )


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
        _invalidate_dashboard_read_models(st.session_state, reason="refresh_all")
        st.rerun()
    with filters:
        st.caption("Explore DB records, lock status, and artifact directory mapping.")

    processed = _load_processed_rows(settings)
    published = _load_published_rows(settings)
    reports = _load_report_rows(settings)
    lock = _lock_snapshot(settings.ingest_lock_path)

    path_checks = _load_directory_count_rows(settings)

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
        st.code(
            f"output={settings.output_dir}\ncache={settings.cache_dir}\nstate_db={settings.state_db}\nreports_db={settings.reports_db}"
        )


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
    st.info(
        "This page is intentionally disabled until dedicated developer CLI/orchestrator tooling is added."
    )


def main() -> None:
    from src import streamlit_app

    streamlit_app.main()


if __name__ == "__main__":
    main()
