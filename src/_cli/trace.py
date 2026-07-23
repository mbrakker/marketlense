from __future__ import annotations

import json
from dataclasses import asdict

import typer
from rich.table import Table
from rich import box

from src.contracts.files import ReadTextRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.tracing import TraceBuildRequest
from src.generators.trace_generator import build_trace_summary
from src.services.file_service import read_text
from src.services.logging_service import setup_logging
from src.utils.gui_utils import (
    extract_log_date_from_filename,
    parse_structured_log_line,
)
from src.services.config_service import new_runtime_context as new_run_context
from src.utils.logging import child_context, log_event

from src._cli.app import cli_app, console, logger
from src._cli.common import _default_log_path
from src._cli.runtime import sync_cli_patch_points

_CLI_PATCH_POINTS = (
    "authorize_oauth_user",
    "build_ingest_settings",
    "console",
    "default_browser_doctor_verification_url",
    "default_ui_run_registry_path",
    "execute_ui_run",
    "get_ui_run_record",
    "load_browser_download_settings",
    "load_publish_settings",
    "load_publisher_inventory_settings",
    "load_settings",
    "promote_private_api_evidence_to_browser_playbook",
    "read_text",
    "replay_ui_run",
    "run_acquisition_audit",
    "run_browser_developer_diagnostics",
    "run_candidate_extraction",
    "run_cost_reporting",
    "run_cover_image_generation",
    "run_cross_report_analysis_orchestrator",
    "run_ingest",
    "run_publish",
    "run_publisher_inventory_discovery",
    "run_publisher_sync",
    "run_recategorize",
    "run_report_download",
    "run_update_wp_categories",
    "setup_logging",
    "write_ui_run_record",
    "write_ui_run_replay_manifest",
)


def _sync_cli_patch_points() -> None:
    sync_cli_patch_points(globals(), _CLI_PATCH_POINTS)


def _load_structured_log_events(log_path: str, ctx) -> list[dict]:
    _sync_cli_patch_points()
    read_ctx = child_context(ctx, task_id=f"{ctx.task_id}:read_trace_log")
    content = read_text(
        ReadTextRequest(schema_version="1.0", path=log_path),
        read_ctx,
    ).content
    log_date = extract_log_date_from_filename(log_path)
    events: list[dict] = []
    for line in content.splitlines():
        parsed = parse_structured_log_line(line, log_date=log_date)
        if parsed is not None:
            events.append(parsed)
    return events


def _trace_depths(result) -> dict[str, int]:
    spans_by_id = {span.span_id: span for span in result.spans}
    memo: dict[str, int] = {}

    def _depth(span_id: str) -> int:
        if span_id in memo:
            return memo[span_id]
        span = spans_by_id.get(span_id)
        if span is None or not span.parent_span_id:
            memo[span_id] = 0
            return 0
        memo[span_id] = _depth(span.parent_span_id) + 1
        return memo[span_id]

    for span_id in spans_by_id:
        _depth(span_id)
    return memo


@cli_app.command("trace-run")
def trace_run(
    run_id: str = typer.Option("", help="Run ID to inspect."),
    trace_id: str = typer.Option("", help="Trace ID to inspect."),
    task_id: str = typer.Option("", help="Optional task ID filter."),
    log_path: str = typer.Option("", help="Structured log path to inspect."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
):
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_trace_run")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    selected_log_path = str(log_path or "").strip() or _default_log_path()
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="trace_run_start",
            module=logger.name,
            fields={
                "run_id": run_id,
                "trace_id": trace_id,
                "task_id": task_id,
                "log_path": selected_log_path,
            },
        )
    )
    events = _load_structured_log_events(selected_log_path, ctx)
    result = build_trace_summary(
        TraceBuildRequest(
            schema_version="1.0",
            events=events,
            trace_id=str(trace_id or "").strip(),
            run_id=str(run_id or "").strip(),
            task_id=str(task_id or "").strip(),
        )
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="trace_run_complete",
            module=logger.name,
            fields={
                "trace_id": result.trace_id,
                "run_id": result.run_id,
                "event_count": result.event_count,
                "span_count": result.span_count,
                "diagnostic_count": result.diagnostic_count,
                "valid": result.valid,
            },
        )
    )
    if json_output:
        console.print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return

    table = Table(title="Trace", box=box.SIMPLE_HEAVY)
    table.add_column("Span")
    table.add_column("Role")
    table.add_column("Module")
    table.add_column("Events", justify="right")
    table.add_column("Duration ms", justify="right")
    table.add_column("Parent")
    depths = _trace_depths(result)
    for span in result.spans:
        indent = "  " * depths.get(span.span_id, span.span_depth)
        table.add_row(
            f"{indent}{span.span_name}",
            span.role,
            span.module,
            str(span.event_count),
            f"{span.duration_ms:.1f}",
            span.parent_span_id,
        )
    console.print(table)
    if result.workflow_stages:
        workflow_table = Table(title="Workflow Coverage", box=box.SIMPLE_HEAVY)
        workflow_table.add_column("Workflow")
        workflow_table.add_column("Roles")
        workflow_table.add_column("Spans", justify="right")
        workflow_table.add_column("Events", justify="right")
        workflow_table.add_column("Complete")
        for stage in result.workflow_stages:
            workflow_table.add_row(
                stage.workflow_name,
                ", ".join(stage.roles_seen),
                str(len(stage.span_ids)),
                str(stage.event_count),
                "yes" if stage.complete else "no",
            )
        console.print(workflow_table)
    if result.diagnostics:
        diagnostic_table = Table(title="Trace Diagnostics", box=box.SIMPLE_HEAVY)
        diagnostic_table.add_column("Severity")
        diagnostic_table.add_column("Code")
        diagnostic_table.add_column("Span")
        diagnostic_table.add_column("Field")
        diagnostic_table.add_column("Message")
        for diagnostic in result.diagnostics:
            diagnostic_table.add_row(
                diagnostic.severity,
                diagnostic.code,
                diagnostic.span_id,
                diagnostic.field_name,
                diagnostic.message,
            )
        console.print(diagnostic_table)
    console.print(
        "[green]Done: "
        f"{result.span_count} span(s), {result.event_count} event(s), "
        f"{result.diagnostic_count} diagnostic(s).[/green]"
    )
