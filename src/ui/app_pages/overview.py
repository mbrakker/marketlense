from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import streamlit as st

from src.ui import state as ui_state
from src.ui._streamlit_pages.read_models import (
    _as_utc,
    _discover_log_files,
    _invalidate_dashboard_read_models,
    _load_log_events,
    _load_ops_dashboard_snapshot,
)
from src.ui.common import _page_shell, _render_empty_state, _tip
from src.ui.run_control import (
    cancel_selected_run,
    discard_dead_letter,
    launch_background_run,
    list_dead_letters,
    list_recent_runs,
    list_selected_dead_letter_actions,
    mark_dead_letter_recovery_requested,
    poll_selected_run,
)


def _parse_utc(value: object) -> datetime | None:
    token = str(value or "").strip()
    if not token:
        return None
    try:
        return datetime.fromisoformat(token.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def _age_hours_label(value: object) -> str:
    parsed = _parse_utc(value)
    if parsed is None:
        return ""
    hours = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 3600.0)
    return f"{hours:.1f}h"


def build_run_dashboard_metrics(
    *,
    active_runs: list[Any],
    recent_runs: list[Any],
    recent_failures: list[Any],
    dead_letter_backlog: list[Any],
    recent_events: list[dict[str, Any]],
) -> list[dict[str, str]]:
    oldest_dead_letter_age = (
        max(
            (
                _age_hours_label(getattr(item, "failed_at_utc", ""))
                for item in dead_letter_backlog
            ),
            default="clear",
        )
        if dead_letter_backlog
        else "clear"
    )
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
            "label": "Dead letters",
            "value": str(len(dead_letter_backlog)),
            "delta": oldest_dead_letter_age,
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


def build_dead_letter_rows(records: list[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in records:
        taxonomy = getattr(record, "error_taxonomy", None)
        identity = getattr(record, "identity", None)
        remediation = getattr(record, "remediation", None)
        rows.append(
            {
                "workflow": str(getattr(record, "display_name", "")),
                "triage_status": str(getattr(record, "triage_status", "")),
                "triage_category": str(getattr(record, "triage_category", "")),
                "stage": str(getattr(taxonomy, "stage", "")),
                "error_code": str(getattr(taxonomy, "error_code", "")),
                "publisher_name": str(getattr(identity, "publisher_name", "")),
                "report_url": str(getattr(identity, "report_url", "")),
                "remediation_code": str(getattr(remediation, "remediation_code", "")),
                "checkpoint_stage": str(getattr(remediation, "checkpoint_stage", "")),
                "runbook_link": str(getattr(remediation, "runbook_link", "")),
                "failed_at_utc": str(getattr(record, "failed_at_utc", "")),
                "age": _age_hours_label(getattr(record, "failed_at_utc", "")),
            }
        )
    return rows


def build_dead_letter_age_trend_rows(records: list[Any]) -> list[dict[str, str]]:
    buckets = {
        "lt_4h": 0,
        "4h_to_24h": 0,
        "1d_to_3d": 0,
        "gt_3d": 0,
    }
    for record in records:
        parsed = _parse_utc(getattr(record, "failed_at_utc", ""))
        if parsed is None:
            continue
        age_hours = max(
            0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 3600.0
        )
        if age_hours < 4:
            buckets["lt_4h"] += 1
        elif age_hours < 24:
            buckets["4h_to_24h"] += 1
        elif age_hours < 72:
            buckets["1d_to_3d"] += 1
        else:
            buckets["gt_3d"] += 1
    return [
        {"bucket": "<4h", "count": str(buckets["lt_4h"])},
        {"bucket": "4h-24h", "count": str(buckets["4h_to_24h"])},
        {"bucket": "1d-3d", "count": str(buckets["1d_to_3d"])},
        {"bucket": ">3d", "count": str(buckets["gt_3d"])},
    ]


def build_dead_letter_action_rows(actions: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "action": str(getattr(item, "action", "")),
            "actor": str(getattr(item, "actor", "")),
            "note": str(getattr(item, "note", "")),
            "related_run_id": str(getattr(item, "related_run_id", ""))[:8],
            "created_at_utc": str(getattr(item, "created_at_utc", "")),
        }
        for item in actions
    ]


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
                "updated_at_utc": _as_utc(row.get("updated_at")),
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
                "ts_utc": _as_utc(event.get("ts_utc") or event.get("timestamp")),
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

    snapshot = _load_ops_dashboard_snapshot(settings)
    reports = snapshot.reports
    processed = snapshot.processed
    published = snapshot.published
    lock = asdict(snapshot.lock)
    health = [asdict(item) for item in snapshot.storage_health]
    logs = _discover_log_files()
    recent_paths = [row["path"] for row in logs[:2]]
    events = _load_log_events(recent_paths)
    active_runs = list_recent_runs(
        settings, statuses=["queued", "running"], limit=20
    ).records
    recent_runs = list_recent_runs(settings, limit=20).records
    recent_failures = [
        item for item in recent_runs if getattr(item, "status", "") == "failed"
    ][:6]
    dead_letter_backlog = list_dead_letters(
        settings, triage_statuses=["open"], limit=20
    ).records

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
        _invalidate_dashboard_read_models(st.session_state, reason="refresh_all")
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
                dead_letter_backlog=dead_letter_backlog,
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
                "Dead-letter backlog",
                build_dead_letter_rows(dead_letter_backlog[:10]),
                empty_title="No open dead letters",
                empty_detail="Background runs that fail final triage will appear here with typed categories and ages.",
                column_config={
                    "workflow": "Workflow",
                    "triage_status": "Status",
                    "triage_category": "Category",
                    "stage": "Stage",
                    "error_code": "Error code",
                    "publisher_name": "Publisher",
                    "remediation_code": "Remediation",
                    "checkpoint_stage": "Checkpoint",
                    "runbook_link": "Runbook",
                    "age": "Age",
                },
            )
        with lower_right:
            _render_table_card(
                "Dead-letter age trend",
                build_dead_letter_age_trend_rows(dead_letter_backlog),
                empty_title="No dead-letter age trend",
                empty_detail="Open dead letters will be bucketed by age to highlight stale operational backlog.",
                column_config={
                    "bucket": "Age bucket",
                    "count": "Open dead letters",
                },
            )
        with st.container(border=True):
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
        with st.container(border=True):
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
    dead_letters = list_dead_letters(settings, limit=50).records

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
                    "label": "Dead letters",
                    "value": str(
                        len(
                            [
                                item
                                for item in dead_letters
                                if getattr(item, "triage_status", "") == "open"
                            ]
                        )
                    ),
                    "delta": "operator backlog",
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
                "Dead-letter queue",
                build_dead_letter_rows(dead_letters[:12]),
                empty_title="No dead-letter queue",
                empty_detail="Failed background runs that require operator triage will appear here.",
                column_config={
                    "workflow": "Workflow",
                    "triage_status": "Status",
                    "triage_category": "Category",
                    "stage": "Stage",
                    "publisher_name": "Publisher",
                    "remediation_code": "Remediation",
                    "checkpoint_stage": "Checkpoint",
                    "runbook_link": "Runbook",
                    "age": "Age",
                },
            )
        with st.container(border=True):
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
                dead_letter_actions = list_selected_dead_letter_actions(
                    settings, limit=20
                )
                summary_cols = st.columns(2)
                summary_cols[0].metric("Status", selected_record.status)
                summary_cols[1].metric("Artifacts", len(selected_record.artifact_paths))
                st.caption(
                    f"Run `{selected_record.run_id[:8]}` | type `{selected_record.run_type}` | created `{selected_record.created_at_utc}`"
                )
                if polled.failure_classification is not None:
                    classification = polled.failure_classification
                    st.info(
                        f"Recommended action: {classification.action}. {classification.reason} "
                        f"Side-effect warning: {classification.side_effect_warning}"
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
                if dead_letter_actions and dead_letter_actions.actions:
                    with st.expander("Dead-letter actions", expanded=True):
                        st.dataframe(
                            build_dead_letter_action_rows(dead_letter_actions.actions),
                            width="stretch",
                            hide_index=True,
                            column_config={
                                "action": "Action",
                                "actor": "Actor",
                                "note": st.column_config.TextColumn(
                                    "Note", width="large"
                                ),
                                "related_run_id": "Recovery run",
                                "created_at_utc": "Recorded (UTC)",
                            },
                        )
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
                            response = launch_background_run(
                                settings,
                                run_type=selected_record.run_type,
                                display_name=selected_record.display_name,
                                request_payload=selected_record.request_payload,
                            )
                            if selected_record.status == "failed":
                                mark_dead_letter_recovery_requested(
                                    settings,
                                    run_id=str(selected_record.run_id),
                                    recovery_run_id=str(response.record.run_id),
                                    note="Retry launched from Run Center.",
                                )
                                ui_state.set_selected_run_id(
                                    str(response.record.run_id)
                                )
                            st.rerun()
                        if selected_record.status == "failed":
                            if st.button(
                                "Discard dead letter",
                                width="stretch",
                                key="discard_selected_dead_letter",
                                help=_tip(
                                    "Mark the failed run as intentionally discarded.",
                                    "Use when the failure is understood and you do not want it counted as open backlog anymore.",
                                ),
                            ):
                                discard_dead_letter(
                                    settings,
                                    run_id=str(selected_record.run_id),
                                    note="Discarded from Run Center.",
                                )
                                st.rerun()
