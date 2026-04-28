from __future__ import annotations

from typing import Any

import streamlit as st

from src.ui import streamlit_pages as legacy
from src.ui import state as ui_state
from src.ui.common import _page_shell, _render_empty_state, _tip
from src.ui.run_control import (
    cancel_selected_run,
    launch_background_run,
    list_recent_runs,
    poll_selected_run,
)


def build_run_dashboard_metrics(
    *,
    active_runs: list[Any],
    recent_runs: list[Any],
    recent_failures: list[Any],
    recent_events: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "label": "Active runs",
            "value": str(len(active_runs)),
            "delta": f"{len([item for item in active_runs if getattr(item, 'status', '') == 'running'])} running",
        },
        {
            "label": "Succeeded",
            "value": str(
                len(
                    [
                        item
                        for item in recent_runs
                        if getattr(item, "status", "") == "succeeded"
                    ]
                )
            ),
            "delta": f"{len(recent_runs)} tracked",
        },
        {
            "label": "Failed",
            "value": str(len(recent_failures)),
            "delta": "needs attention" if recent_failures else "clear",
        },
        {
            "label": "Recent events",
            "value": str(len(recent_events)),
            "delta": "latest log tail",
        },
    ]


def build_run_table_rows(records: list[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in records:
        rows.append(
            {
                "workflow": str(
                    getattr(record, "display_name", "")
                    or getattr(record, "run_type", "")
                ),
                "status": str(getattr(record, "status", "")),
                "run_id": str(getattr(record, "run_id", ""))[:8],
                "created_at_utc": str(getattr(record, "created_at_utc", "")),
                "started_at_utc": str(getattr(record, "started_at_utc", "")),
                "finished_at_utc": str(getattr(record, "finished_at_utc", "")),
                "error_code": str(getattr(record, "error_code", "")),
                "pid": ""
                if getattr(record, "pid", None) is None
                else str(getattr(record, "pid", "")),
            }
        )
    return rows


def build_report_rows(
    reports: list[dict[str, Any]], *, limit: int = 8
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in reports[:limit]:
        rows.append(
            {
                "title": str(row.get("title") or ""),
                "publisher": str(row.get("publisher") or ""),
                "analysis_mode": str(row.get("analysis_mode") or ""),
                "updated_at_utc": legacy._as_utc(row.get("updated_at")),
                "html_path": str(row.get("html_path") or ""),
            }
        )
    return rows


def build_log_event_rows(
    events: list[dict[str, Any]], *, limit: int = 8
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for event in events[:limit]:
        message = str(
            event.get("message") or event.get("event") or event.get("detail") or ""
        )
        rows.append(
            {
                "ts_utc": legacy._as_utc(event.get("ts_utc") or event.get("timestamp")),
                "level": str(event.get("level") or ""),
                "event": str(event.get("event") or event.get("module") or ""),
                "message": message[:140],
            }
        )
    return rows


def build_auth_status_rows(
    settings: Any | None, publish_settings: Any | None
) -> list[dict[str, str]]:
    return [
        {
            "name": "Drive auth",
            "status": str(getattr(settings, "drive_auth_mode", "unknown") or "unknown"),
            "source": "app.yaml",
        },
        {
            "name": "OpenAI key",
            "status": "present"
            if getattr(settings, "openai_api_key", "")
            else "missing",
            "source": "env/config",
        },
        {
            "name": "WordPress auth",
            "status": (
                "present"
                if publish_settings
                and (
                    getattr(publish_settings.wp, "app_password", "")
                    or getattr(publish_settings.wp, "bearer_token", "")
                )
                else "missing"
            ),
            "source": "config-service",
        },
    ]


def _render_metric_row(metrics: list[dict[str, str]]) -> None:
    with st.container(horizontal=True):
        for metric in metrics:
            st.metric(
                metric["label"],
                metric["value"],
                metric["delta"],
                border=True,
            )


def _render_table_card(
    title: str,
    rows: list[dict[str, str]],
    *,
    empty_title: str,
    empty_detail: str,
    column_config: dict[str, Any] | None = None,
) -> None:
    with st.container(border=True):
        st.subheader(title)
        if rows:
            st.dataframe(
                rows,
                width="stretch",
                hide_index=True,
                column_config=column_config,
            )
        else:
            _render_empty_state(empty_title, empty_detail)


def render_cockpit_overview() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return

    snapshot = legacy._load_ops_dashboard_snapshot(settings)
    reports = snapshot.reports
    processed = snapshot.processed
    published = snapshot.published
    lock = legacy.asdict(snapshot.lock)
    health = [legacy.asdict(item) for item in snapshot.storage_health]
    logs = legacy._discover_log_files()
    recent_paths = [row["path"] for row in logs[:2]]
    events = legacy._load_log_events(recent_paths)
    active_runs = list_recent_runs(
        settings, statuses=["queued", "running"], limit=20
    ).records
    recent_runs = list_recent_runs(settings, limit=20).records
    recent_failures = [
        item for item in recent_runs if getattr(item, "status", "") == "failed"
    ][:6]

    status_level = "warn" if lock.get("found") else "success"
    clicked, filters, main_col, detail_col = _page_shell(
        "Cockpit Overview",
        status_label="Lock Active" if lock.get("found") else "System Ready",
        status_level=status_level,
        primary_action="Refresh overview",
        primary_help=_tip(
            "Reload dashboard metrics from reports DB, state DB, lock file, and latest logs.",
            "Use after ingest, discovery, or publish runs to refresh the control-panel summary.",
        ),
        primary_key="overview_refresh",
    )
    if clicked:
        legacy._invalidate_dashboard_read_models(st.session_state, reason="refresh_all")
        st.rerun()

    with filters:
        st.caption(
            "Run-first summary for queue health, recent report movement, storage signals, and the latest operator-facing failures."
        )

    with main_col:
        _render_metric_row(
            build_run_dashboard_metrics(
                active_runs=active_runs,
                recent_runs=recent_runs,
                recent_failures=recent_failures,
                recent_events=events,
            )
        )
        upper_left, upper_right = st.columns(2, gap="large")
        with upper_left:
            _render_table_card(
                "Active jobs",
                build_run_table_rows(active_runs),
                empty_title="No active jobs",
                empty_detail="Launch ingest, discovery, or publish work from the operations pages to populate this queue.",
                column_config={
                    "workflow": "Workflow",
                    "status": "Status",
                    "run_id": "Run",
                    "started_at_utc": "Started (UTC)",
                    "pid": "PID",
                },
            )
        with upper_right:
            _render_table_card(
                "Recent failures",
                build_run_table_rows(recent_failures),
                empty_title="No recent failures",
                empty_detail="The latest tracked background runs completed without recorded failure states.",
                column_config={
                    "workflow": "Workflow",
                    "error_code": "Error code",
                    "finished_at_utc": "Finished (UTC)",
                    "run_id": "Run",
                },
            )
        lower_left, lower_right = st.columns(2, gap="large")
        with lower_left:
            _render_table_card(
                "Recent reports",
                build_report_rows(reports, limit=10),
                empty_title="No report metadata yet",
                empty_detail="Run ingest or report acquisition to create report inventory and downstream analysis records.",
                column_config={
                    "title": "Title",
                    "publisher": "Publisher",
                    "analysis_mode": "Mode",
                    "updated_at_utc": "Updated (UTC)",
                    "html_path": st.column_config.TextColumn(
                        "HTML path", width="large"
                    ),
                },
            )
        with lower_right:
            _render_table_card(
                "Latest log events",
                build_log_event_rows(events, limit=10),
                empty_title="No recent log events",
                empty_detail="Recent logs could not be discovered. Refresh after the next workflow run.",
                column_config={
                    "ts_utc": "Time (UTC)",
                    "level": "Level",
                    "event": "Event",
                    "message": st.column_config.TextColumn("Message", width="large"),
                },
            )

    with detail_col:
        with st.container(border=True):
            st.subheader("System pulse")
            pulse_cols = st.columns(2)
            pulse_cols[0].metric("Reports", len(reports), f"{len(processed)} processed")
            pulse_cols[1].metric("Published", len(published), f"{len(logs)} log files")
            if health:
                st.dataframe(health, width="stretch", hide_index=True)
            else:
                _render_empty_state(
                    "No storage health rows",
                    "Refresh the overview after the storage snapshot generator has written fresh diagnostics.",
                )
        with st.container(border=True):
            st.subheader("Ingest lock")
            if lock.get("found"):
                st.error(f"Locked by `{lock.get('owner_id')}` (pid={lock.get('pid')})")
            else:
                st.success("No active ingest lock.")
            st.caption(f"Lock file: `{settings.ingest_lock_path}`")
        with st.container(border=True):
            st.subheader("Access posture")
            st.dataframe(
                build_auth_status_rows(
                    settings=settings,
                    publish_settings=ui_state.get_publish_settings(),
                ),
                width="stretch",
                hide_index=True,
            )


def render_run_center() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return

    clicked, filters, main_col, detail_col = _page_shell(
        "Run Center",
        status_label="Run Control",
        status_level="info",
        primary_action="Refresh runs",
        primary_help=_tip(
            "Refresh persisted background run state and output logs.",
            "Use after launching ingest or discovery to inspect the latest status.",
        ),
        primary_key="refresh_run_center",
    )
    if clicked:
        st.rerun()

    active = list_recent_runs(
        settings, statuses=["queued", "running"], limit=20
    ).records
    recent = list_recent_runs(settings, limit=50).records
    failed = [record for record in recent if getattr(record, "status", "") == "failed"]

    with filters:
        view_mode = st.segmented_control(
            "Run window",
            options=["All runs", "Active only", "Failures"],
            default="All runs",
            help=_tip(
                "Choose which run slice drives the selection picker below.",
                "Switch to Failures when triaging the latest broken workflow.",
            ),
        )
        source_rows = recent
        if view_mode == "Active only":
            source_rows = active
        elif view_mode == "Failures":
            source_rows = failed
        selection_rows = source_rows or recent
        selected_run_id = ui_state.get_selected_run_id()
        st.caption(
            "Tracked background jobs launched from the control panel. The selected run also drives log and cost context on other pages."
        )
        if selection_rows:
            default_index = 0
            if selected_run_id:
                for idx, record in enumerate(selection_rows):
                    if record.run_id == selected_run_id:
                        default_index = idx
                        break
            selected_index = st.selectbox(
                "Selected run",
                options=list(range(len(selection_rows))),
                index=default_index,
                format_func=lambda idx: (
                    f"{selection_rows[idx].status} | {selection_rows[idx].display_name} | {selection_rows[idx].run_id[:8]}"
                ),
                help=_tip(
                    "Choose a persisted background run to inspect details and output.",
                    "Select the latest ingest run to view live output, artifacts, and request payload.",
                ),
            )
            ui_state.set_selected_run_id(selection_rows[selected_index].run_id)
    polled = poll_selected_run(settings, max_bytes=64000)

    with main_col:
        _render_metric_row(
            [
                {
                    "label": "Active runs",
                    "value": str(len(active)),
                    "delta": f"{len([item for item in active if item.status == 'running'])} running",
                },
                {
                    "label": "Succeeded",
                    "value": str(
                        len([item for item in recent if item.status == "succeeded"])
                    ),
                    "delta": f"{len(recent)} tracked",
                },
                {
                    "label": "Failed",
                    "value": str(len(failed)),
                    "delta": "triage now" if failed else "clear",
                },
                {
                    "label": "Canceled",
                    "value": str(
                        len([item for item in recent if item.status == "canceled"])
                    ),
                    "delta": "manual stops",
                },
            ]
        )
        top_left, top_right = st.columns(2, gap="large")
        with top_left:
            _render_table_card(
                "Active queue",
                build_run_table_rows(active),
                empty_title="Nothing is running",
                empty_detail="Launch a workflow from the operations pages when you need a persisted run to monitor here.",
                column_config={
                    "workflow": "Workflow",
                    "status": "Status",
                    "run_id": "Run",
                    "started_at_utc": "Started (UTC)",
                    "pid": "PID",
                },
            )
        with top_right:
            _render_table_card(
                "Recent run history",
                build_run_table_rows(recent[:12]),
                empty_title="No run history yet",
                empty_detail="The run registry is empty. Start with Ingest Control, Publisher Discovery, or Report Download Lab.",
                column_config={
                    "workflow": "Workflow",
                    "status": "Status",
                    "run_id": "Run",
                    "created_at_utc": "Created (UTC)",
                    "finished_at_utc": "Finished (UTC)",
                },
            )
        with st.container(border=True):
            st.subheader("Live output")
            if polled is None:
                _render_empty_state(
                    "No selected run output",
                    "Select a tracked run above to inspect the latest worker output and registry state.",
                )
            else:
                st.code(
                    (polled.output_chunk.text if polled.output_chunk else "")
                    or "[worker] no output yet"
                )

    with detail_col:
        with st.container(border=True):
            st.subheader("Selected run detail")
            if polled is None:
                _render_empty_state(
                    "No selected run",
                    "Choose a run from the selector above. The same selected run follows you into logs and cost views.",
                )
            else:
                selected_record = polled.record
                summary_cols = st.columns(2)
                summary_cols[0].metric("Status", selected_record.status)
                summary_cols[1].metric("Artifacts", len(selected_record.artifact_paths))
                st.caption(
                    f"Run `{selected_record.run_id[:8]}` | type `{selected_record.run_type}` | created `{selected_record.created_at_utc}`"
                )
                if selected_record.artifact_paths:
                    st.dataframe(
                        [{"path": path} for path in selected_record.artifact_paths],
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "path": st.column_config.TextColumn(
                                "Artifact path", width="large"
                            )
                        },
                    )
                with st.expander("Result summary", expanded=True):
                    st.json(selected_record.result_summary)
                with st.expander("Request payload"):
                    st.json(selected_record.request_payload)
                with st.expander("Registry record"):
                    st.json(selected_record.__dict__)
                with st.container(horizontal=True):
                    if selected_record.status in {"queued", "running"}:
                        if st.button(
                            "Cancel run",
                            type="primary",
                            width="stretch",
                            key="cancel_selected_run",
                            help=_tip(
                                "Terminate the selected running background job.",
                                "Use when a batch run is stuck or launched with the wrong parameters.",
                            ),
                        ):
                            cancel_selected_run(settings)
                            st.rerun()
                    else:
                        if st.button(
                            "Retry run",
                            type="primary",
                            width="stretch",
                            key="retry_selected_run",
                            help=_tip(
                                "Launch the same request payload again as a new tracked run.",
                                "Use after fixing config or transient external issues.",
                            ),
                        ):
                            launch_background_run(
                                settings,
                                run_type=selected_record.run_type,
                                display_name=selected_record.display_name,
                                request_payload=selected_record.request_payload,
                            )
                            st.rerun()
