from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable, MutableMapping, TypeVar

import streamlit as st

from src.contracts.costs import CostRollupRequest
from src.contracts.ops import OpsDashboardSnapshotRequest
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
from src.services.logging_service import DEFAULT_LOG_DIR, LOG_DIR_ENV, LOG_FILE_PREFIX
from src.ui import state as ui_state
from src.ui.common import _ctx
from src.ui.run_control import poll_selected_run
from src.utils.gui_utils import compute_task_duration_rollups, row_dicts

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
        f'<pre class="ml-terminal">{terminal_text}</pre>',
        unsafe_allow_html=True,
    )


def _as_utc(ts: int | float | str | None) -> str:
    if ts in (None, ""):
        return ""
    try:
        if isinstance(ts, str):
            if "T" in ts:
                return ts
            ts = float(ts)
        if not isinstance(ts, (int, float)):
            return str(ts)
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    except (OSError, OverflowError, TypeError, ValueError):
        return ""


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
                    schema_version="1.0",
                    output_dir=output_dir,
                    limit=200,
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
            ReportRowsLoadRequest(
                schema_version="1.0",
                reports_db=settings.reports_db,
            ),
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
                LockSnapshotLoadRequest(
                    schema_version="1.0",
                    lock_path=lock_path,
                ),
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


def _load_ledger_entries(
    ledger_path: str, *, limit: int = 2000
) -> list[dict[str, Any]]:
    response = load_ledger_entries(
        LedgerEntriesLoadRequest(
            schema_version="1.0",
            ledger_path=ledger_path,
            limit=limit,
        ),
        _ctx("load_ledger_entries"),
    )
    return response.entries


def _cost_rollup_rows(settings: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Any]:
    ledger_rows = _load_ledger_entries(settings.cost_ledger_path)
    log_files = _discover_log_files()
    event_rows = _load_log_events(
        [row["path"] for row in log_files[:3]],
        max_lines_per_file=4000,
    )
    duration_rows = compute_task_duration_rollups(event_rows)
    rollup_reporting = run_cost_reporting(
        src.contracts.costs.CostReportingRequest(
            schema_version="1.0",
            rollup_request=CostRollupRequest(
                schema_version="1.0",
                ledger_path=settings.cost_ledger_path,
                out_path=settings.cost_daily_path,
            ),
        ),
        _ctx("cost_rollup"),
    )
    return ledger_rows, duration_rows, rollup_reporting.rollup
