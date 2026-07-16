from __future__ import annotations

"""Observability Streamlit pages owned by logs, cost, and storage workflows."""

from dataclasses import asdict
import streamlit as st

from src.contracts.costs import (
    CostReportRequest,
    CostReportingRequest,
    CostRollupRequest,
)
from src.contracts.semantic_ids import RunId
from src.orchestrators.cost_reporting_orchestrator import run_cost_reporting
from src.services.llm_usage_ledger_service import read_budget_authority_report
from src.ui import state as ui_state
from src.ui._streamlit_pages.read_models import (
    _discover_log_files,
    _invalidate_dashboard_read_models,
    _load_directory_count_rows,
    _load_ledger_entries,
    _load_log_events,
    _load_processed_rows,
    _load_published_rows,
    _load_report_rows,
    _lock_snapshot,
)
from src.ui.common import (
    UI_SURFACE_EXCEPTIONS,
    _append_terminal,
    _ctx,
    _page_shell,
    _render_terminal_panel,
    _tip,
)
from src.utils.gui_utils import compute_task_duration_rollups, filter_log_events


def render_cost_usage() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
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
                RunId(run_id_value)
                if filter_mode == "run_id" and run_id_value
                else None
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
    try:
        budget_authority = read_budget_authority_report(
            usage_db_path=settings.usage_db_path,
            run_id=selected_run_id,
            ctx=_ctx("budget_authority_report"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:
        budget_authority = None
        _append_terminal(f"Budget authority report failed: {exc}")

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
        st.subheader("Budget Authority")
        if budget_authority is not None:
            st.json(asdict(budget_authority))
        else:
            st.caption("Budget authority report is unavailable; inspect the terminal.")
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


def render_logs_events() -> None:
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


def render_system_storage() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
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


def render_developer_tools() -> None:
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
