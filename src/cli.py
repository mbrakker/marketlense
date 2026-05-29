from __future__ import annotations

import logging
import os
import json
from dataclasses import asdict
from datetime import date
from typing import Any, cast

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from src.utils.errors import AppError
from src.contracts.acquisition_audit import AcquisitionAuditBatchRequest
from src.contracts.costs import CostReportRequest, CostReportingRequest
from src.contracts.browser_download import ReportDownloadOrchestratorRequest
from src.contracts.browser_download import BrowserDeveloperDiagnosticsRequest
from src.contracts.browser_download import BrowserDownloadSessionReusePolicy
from src.contracts.browser_download import BrowserRoutePrivateApiPromotionRequest
from src.contracts.categories import RecategorizeRequest
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisOrchestratorRequest,
    CrossReportAnalysisRequest,
    CrossReportProjectedDataReadRequest,
    PublicationMode,
)
from src.contracts.cover_images import CoverImageOrchestratorRequest
from src.contracts.drive import DriveOAuthAuthorizeRequest
from src.contracts.files import ReadTextRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.publisher_inventory import PublisherInventoryDiscoveryRequest
from src.contracts.publisher_profiles import PublisherSyncRequest
from src.contracts.semantic_ids import RunId
from src.contracts.tracing import TraceBuildRequest
from src.contracts.ui_run_control import (
    UiRunRecord,
    UiRunRecordGetRequest,
    UiRunRecordWriteRequest,
    UiRunWorkerRequest,
)
from src.contracts.ui_run_replay import (
    UiRunReplayCaptureRequest,
    UiRunReplayRequest,
)
from src.orchestrators.report_download_orchestrator import run_report_download
from src.orchestrators.acquisition_audit_orchestrator import run_acquisition_audit
from src.orchestrators.cost_reporting_orchestrator import run_cost_reporting
from src.orchestrators.ingest_orchestrator import run_ingest
from src.orchestrators.candidate_extraction_orchestrator import run_candidate_extraction
from src.orchestrators.cover_image_orchestrator import run_cover_image_generation
from src.orchestrators.cross_report_analysis_orchestrator import (
    run_cross_report_analysis as run_cross_report_analysis_orchestrator,
)
from src.orchestrators.publisher_inventory_orchestrator import (
    run_publisher_inventory_discovery,
)
from src.orchestrators.publisher_sync_orchestrator import run_publisher_sync
from src.orchestrators.publish_orchestrator import run_publish
from src.orchestrators.recategorize_orchestrator import run_recategorize
from src.orchestrators.ui_run_execution_orchestrator import (
    PROMPT_TREE_ROOT,
    SOURCE_TREE_ROOT,
    execute_ui_run,
)
from src.orchestrators.ui_run_replay_orchestrator import replay_ui_run
from src.orchestrators.wp_category_update_orchestrator import run_update_wp_categories
from src.generators.trace_generator import build_trace_summary
from src.services.config_service import (
    build_ingest_settings,
    load_browser_download_settings,
    load_publisher_inventory_settings,
    load_settings,
    load_publish_settings,
)
from src.services.browser_report_download_service import (
    default_browser_doctor_verification_url,
    promote_private_api_evidence_to_browser_playbook,
    run_browser_developer_diagnostics,
)
from src.services.drive_service import authorize_oauth_user
from src.services.file_service import read_text
from src.services.logging_service import setup_logging
from src.services.run_registry_service import (
    default_ui_run_registry_path,
    get_ui_run_record,
    write_ui_run_record,
)
from src.services.ui_run_replay_service import write_ui_run_replay_manifest
from src.utils.gui_utils import (
    extract_log_date_from_filename,
    parse_structured_log_line,
)
from src.utils.logging import child_context, log_event, new_run_context


cli_app = typer.Typer(
    add_completion=False,
    help="PDF -> Structured HTML digests",
    pretty_exceptions_show_locals=False,
)
console = Console()
logger = logging.getLogger("market_lense.cli")
_CROSS_REPORT_PUBLICATION_MODES = {
    "generate_only",
    "validate_only",
    "publish_dry_run",
    "publish_live",
}


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _default_log_path() -> str:
    from datetime import datetime

    return os.path.join("logs", f"market_lense_{datetime.now().date().isoformat()}.log")


def _split_cli_filter_values(raw_value: str, *, option_name: str) -> list[str]:
    value = str(raw_value or "").strip()
    if not value:
        return []
    pieces = [piece.strip() for piece in value.split(",")]
    if any(not piece for piece in pieces):
        raise AppError(
            code="cross_report_cli_filter_invalid",
            message=f"{option_name} contains an empty comma-separated value.",
            retryable=False,
            severity="error",
            context={"option": option_name, "value": value},
        )
    return pieces


def _cross_report_publish_mode(raw_value: str) -> PublicationMode:
    mode = str(raw_value or "").strip().lower()
    if mode not in _CROSS_REPORT_PUBLICATION_MODES:
        raise AppError(
            code="cross_report_cli_publish_mode_invalid",
            message="Cross-report publish mode is invalid.",
            retryable=False,
            severity="error",
            context={
                "publication_mode": mode,
                "allowed": sorted(_CROSS_REPORT_PUBLICATION_MODES),
            },
        )
    return cast(PublicationMode, mode)


def _normalize_cross_report_cli_date(raw_value: str, *, option_name: str) -> str | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise AppError(
            code="cross_report_cli_date_invalid",
            message=f"--{option_name} must be a valid YYYY-MM-DD date.",
            cause=exc,
            retryable=False,
            severity="error",
            context={"option": option_name, "value": value},
        ) from exc


def _optional_int_cli_value(raw_value: object) -> int | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, int):
        return raw_value
    return None


def _cross_report_cli_request_id(payload: dict[str, object]) -> str:
    import hashlib

    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"cli-cross-report:{hashlib.sha256(encoded).hexdigest()[:16]}"


def _string_list_payload(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _int_list_payload(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    integers: list[int] = []
    for item in value:
        if isinstance(item, int):
            integers.append(item)
            continue
        text = str(item).strip()
        if text.isdigit():
            integers.append(int(text))
    return integers


def _required_int_payload(
    payload: dict[str, Any], *, field_name: str, request_json: str
) -> int:
    value = payload.get(field_name)
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    raise AppError(
        code="browser_route_private_api_promotion_request_invalid",
        message=f"Private-API playbook promotion field {field_name} must be an integer.",
        retryable=False,
        severity="error",
        context={"request_json": request_json, "field": field_name},
    )


def _load_private_api_promotion_request(
    *, request_json: str, ctx
) -> BrowserRoutePrivateApiPromotionRequest:
    response = read_text(
        ReadTextRequest(schema_version="1.0", path=request_json),
        ctx,
    )
    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="browser_route_private_api_promotion_request_json_invalid",
            message="Private-API playbook promotion request JSON is invalid.",
            cause=exc,
            retryable=False,
            context={"request_json": request_json},
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="browser_route_private_api_promotion_request_invalid",
            message="Private-API playbook promotion request must be a JSON object.",
            retryable=False,
            context={"request_json": request_json},
        )
    expected_status_codes = _int_list_payload(payload.get("expected_status_codes"))
    if not expected_status_codes:
        expected_status_codes = [200]
    return BrowserRoutePrivateApiPromotionRequest(
        schema_version=str(payload.get("schema_version") or "").strip(),
        playbook_dir=str(payload.get("playbook_dir") or "").strip(),
        source_url=str(payload.get("source_url") or "").strip(),
        route_family=str(payload.get("route_family") or "").strip(),
        route_kind=str(payload.get("route_kind") or "").strip(),
        endpoint_pattern=str(payload.get("endpoint_pattern") or "").strip(),
        method=str(payload.get("method") or "").strip(),
        request_shape_summary=str(payload.get("request_shape_summary") or "").strip(),
        response_pdf_url_json_pointer=str(
            payload.get("response_pdf_url_json_pointer") or ""
        ).strip(),
        validated_success_count=_required_int_payload(
            payload,
            field_name="validated_success_count",
            request_json=request_json,
        ),
        fallback_route_family=str(payload.get("fallback_route_family") or "").strip(),
        expected_status_codes=expected_status_codes,
        required_response_markers=_string_list_payload(
            payload.get("required_response_markers")
        ),
        evidence_labels=_string_list_payload(payload.get("evidence_labels")),
        observed_at=str(payload.get("observed_at") or "").strip(),
    )


def _build_cross_report_cli_request(
    *,
    settings,
    topic: str,
    auto_theme: bool | None,
    category: str,
    tag: str,
    publisher: str,
    date_start: str,
    date_end: str,
    max_report_count: int | None,
    max_evidence_items: int | None,
    max_prompt_chars: int | None,
    publish_mode: str,
    output_root: str,
    idempotency_db: str,
    request_id: str,
) -> CrossReportAnalysisOrchestratorRequest:
    categories = _split_cli_filter_values(category, option_name="category")
    tags = _split_cli_filter_values(tag, option_name="tag")
    publishers = _split_cli_filter_values(publisher, option_name="publisher")
    normalized_topic = str(topic or "").strip()
    configured_auto_theme = bool(
        getattr(settings, "cross_report_analysis_auto_theme_enabled", True)
    )
    normalized_auto_theme = (
        configured_auto_theme if auto_theme is None else bool(auto_theme)
    )
    if not normalized_topic and not normalized_auto_theme:
        raise AppError(
            code="cross_report_cli_topic_required",
            message="Provide --topic or enable --auto-theme for cross-report analysis.",
            retryable=False,
            severity="error",
        )
    report_count = (
        int(max_report_count)
        if max_report_count is not None
        else int(getattr(settings, "cross_report_analysis_max_source_reports", 6))
    )
    if report_count <= 0:
        raise AppError(
            code="cross_report_cli_max_report_count_invalid",
            message="--max-report-count must be greater than zero.",
            retryable=False,
            severity="error",
            context={"max_report_count": report_count},
        )
    evidence_item_count = (
        int(max_evidence_items)
        if max_evidence_items is not None
        else int(getattr(settings, "cross_report_analysis_max_evidence_items", 48))
    )
    if evidence_item_count <= 0:
        raise AppError(
            code="cross_report_cli_max_evidence_items_invalid",
            message="--max-evidence-items must be greater than zero.",
            retryable=False,
            severity="error",
            context={"max_evidence_items": evidence_item_count},
        )
    prompt_char_count = (
        int(max_prompt_chars)
        if max_prompt_chars is not None
        else int(getattr(settings, "cross_report_analysis_max_prompt_chars", 60000))
    )
    if prompt_char_count <= 0:
        raise AppError(
            code="cross_report_cli_max_prompt_chars_invalid",
            message="--max-prompt-chars must be greater than zero.",
            retryable=False,
            severity="error",
            context={"max_prompt_chars": prompt_char_count},
        )
    publication_mode = _cross_report_publish_mode(publish_mode)
    normalized_date_start = _normalize_cross_report_cli_date(
        date_start,
        option_name="date-start",
    )
    normalized_date_end = _normalize_cross_report_cli_date(
        date_end,
        option_name="date-end",
    )
    request_payload: dict[str, Any] = {
        "topic": normalized_topic,
        "auto_theme": normalized_auto_theme,
        "category_filters": categories,
        "tag_filters": tags,
        "publisher_filters": publishers,
        "date_range_start": normalized_date_start,
        "date_range_end": normalized_date_end,
        "max_source_reports": report_count,
        "max_evidence_items": evidence_item_count,
        "max_prompt_chars": prompt_char_count,
        "publication_mode": publication_mode,
    }
    resolved_request_id = str(request_id or "").strip() or _cross_report_cli_request_id(
        request_payload
    )
    return CrossReportAnalysisOrchestratorRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        analysis_request=CrossReportAnalysisRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            request_id=resolved_request_id,
            topic=normalized_topic,
            auto_theme=normalized_auto_theme,
            category_filters=categories,
            tag_filters=tags,
            publisher_filters=publishers,
            date_range_start=normalized_date_start,
            date_range_end=normalized_date_end,
            max_source_reports=report_count,
            diagnostic=False,
            override_publishability=False,
            publication_mode=publication_mode,
        ),
        projected_data_request=CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=settings.reports_db,
            publisher_filters=publishers,
            date_range_start=normalized_date_start,
            date_range_end=normalized_date_end,
            category_filters=categories,
            tag_filters=tags,
            content_classes=["claim", "finding", "quote", "metric"],
            minimum_projection_status="projected",
        ),
        idempotency_db_path=str(idempotency_db or "").strip() or settings.state_db,
        output_root=str(output_root or "").strip() or settings.output_dir,
        max_evidence_items=evidence_item_count,
        max_signals=8,
        max_prompt_chars=prompt_char_count,
        retry_retries=2,
        retry_base_delay_seconds=1.0,
        retry_backoff_step_seconds=1.0,
        retry_jitter_seconds=0.25,
        publish_target_route="wordpress:ml_briefing",
    )


def _load_structured_log_events(log_path: str, ctx) -> list[dict]:
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


def _load_ui_run_worker_request(path: str) -> UiRunWorkerRequest:
    request_path = str(path or "").strip()
    if not request_path:
        raise AppError(
            code="ui_run_worker_request_missing",
            message="UI run worker request path is required",
            retryable=False,
        )
    try:
        payload = json.loads(open(request_path, "r", encoding="utf-8").read())
    except FileNotFoundError as exc:
        raise AppError(
            code="ui_run_worker_request_missing",
            message=f"UI run worker request not found: {request_path}",
            cause=exc,
            retryable=False,
        ) from exc
    except json.JSONDecodeError as exc:
        raise AppError(
            code="ui_run_worker_request_invalid",
            message=f"UI run worker request JSON invalid: {request_path}",
            cause=exc,
            retryable=False,
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="ui_run_worker_request_invalid",
            message=f"UI run worker request root must be an object: {request_path}",
            retryable=False,
        )
    return UiRunWorkerRequest(
        schema_version=str(payload.get("schema_version", "1.0")),
        registry_path=str(payload.get("registry_path") or "").strip(),
        run_id=RunId(str(payload.get("run_id") or "").strip()),
        run_type=str(payload.get("run_type") or "").strip(),
        request_payload=dict(payload.get("request_payload") or {}),
    )


def _update_ui_run_record(
    *,
    worker_request: UiRunWorkerRequest,
    run_ctx,
    status: str,
    started_at_utc: str | None = None,
    finished_at_utc: str | None = None,
    pid: int | None = None,
    exit_code: int | None = None,
    result_summary: dict[str, object] | None = None,
    artifact_paths: list[str] | None = None,
    error_code: str = "",
    error_message: str = "",
    error_retryable: bool | None = None,
    error_severity: str = "",
) -> UiRunRecord:
    existing = get_ui_run_record(
        UiRunRecordGetRequest(
            schema_version="1.0",
            registry_path=worker_request.registry_path,
            run_id=worker_request.run_id,
        ),
        run_ctx,
    ).record
    if existing is None:
        raise AppError(
            code="ui_run_not_found",
            message=f"UI run record not found for worker: {worker_request.run_id}",
            retryable=False,
        )
    updated = UiRunRecord(
        schema_version="1.0",
        run_id=existing.run_id,
        run_type=existing.run_type,
        display_name=existing.display_name,
        status=status,
        request_payload=existing.request_payload,
        command=existing.command,
        created_at_utc=existing.created_at_utc,
        updated_at_utc=_utc_now(),
        started_at_utc=started_at_utc
        if started_at_utc is not None
        else existing.started_at_utc,
        finished_at_utc=finished_at_utc
        if finished_at_utc is not None
        else existing.finished_at_utc,
        output_path=existing.output_path,
        request_path=existing.request_path,
        artifact_paths=artifact_paths
        if artifact_paths is not None
        else existing.artifact_paths,
        result_summary=result_summary
        if result_summary is not None
        else existing.result_summary,
        pid=pid if pid is not None else existing.pid,
        exit_code=exit_code if exit_code is not None else existing.exit_code,
        error_code=error_code,
        error_message=error_message,
        error_retryable=error_retryable,
        error_severity=error_severity,
    )
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=worker_request.registry_path,
            record=updated,
        ),
        run_ctx,
    )
    return updated


@cli_app.command("ingest")
def ingest(
    folder: str = typer.Option(None, help="Override Drive folder ID"),
    limit: int = typer.Option(None, help="Max PDFs to process this run"),
):
    ctx = new_run_context(task_id="cli_ingest")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    console.print("[cyan]Loading settings...[/cyan]")
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_load_settings_start",
            module=logger.name,
            fields={},
        )
    )
    s = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    settings = build_ingest_settings(
        IngestSettingsBuildRequest(schema_version="1.0", app_settings=s),
        ctx,
    )

    console.print("[cyan]Running ingest pipeline...[/cyan]")
    try:
        outcomes = run_ingest(settings, folder_id=folder, limit=limit, ctx=ctx)
    except AppError as exc:
        if exc.code == "ingest_locked":
            console.print(
                f"[red]{exc.message} (lock: {settings.ingest_lock_path})[/red]"
            )
            raise typer.Exit(code=1)
        if exc.code == "db_locked":
            console.print(f"[red]{exc.message}[/red]")
            raise typer.Exit(code=1)
        raise

    table = Table(title="Processed Reports", box=box.SIMPLE_HEAVY)
    table.add_column("File")
    table.add_column("ID")
    table.add_column("MD5")
    table.add_column("HTML")
    processed = 0
    for outcome in outcomes:
        if outcome.status == "processed":
            processed += 1
        md5_short = (outcome.md5 or "")[:10] + ":" if outcome.md5 else ""
        table.add_row(outcome.name, outcome.file_id, md5_short, outcome.html_path or "")

    console.print(table)
    console.print(f"[green]Done: {processed} file(s).[/green]")


@cli_app.command("extract-candidates")
def extract_candidates(
    folder: str = typer.Option(None, help="Override Drive folder ID"),
    limit: int = typer.Option(None, help="Max PDFs to process this run"),
    file_id: str = typer.Option(None, help="Optional Drive file ID to process"),
    pdf: str = typer.Option(None, help="Local PDF path to process instead of Drive"),
    report_id: str = typer.Option(
        None, help="Optional report ID override for local PDFs"
    ),
):
    ctx = new_run_context(task_id="cli_extract_candidates")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    console.print("[cyan]Loading settings...[/cyan]")
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_candidate_extract_start",
            module=logger.name,
            fields={
                "folder": folder or "",
                "limit": limit,
                "file_id": file_id or "",
                "pdf": pdf or "",
            },
        )
    )
    s = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    settings = build_ingest_settings(
        IngestSettingsBuildRequest(schema_version="1.0", app_settings=s),
        ctx,
    )

    console.print("[cyan]Running candidate extraction...[/cyan]")
    outcomes = run_candidate_extraction(
        settings,
        folder_id=folder,
        limit=limit,
        file_id=file_id,
        pdf_path=pdf,
        report_id=report_id,
        ctx=ctx,
    )

    table = Table(title="Candidate Extraction", box=box.SIMPLE_HEAVY)
    table.add_column("Report")
    table.add_column("ID")
    table.add_column("Candidates", justify="right")
    table.add_column("Charts", justify="right")
    table.add_column("Tables", justify="right")
    table.add_column("JSON")
    for outcome in outcomes:
        table.add_row(
            outcome.report_name,
            outcome.report_id,
            str(outcome.candidate_count),
            str(outcome.chart_count),
            str(outcome.table_count),
            outcome.candidates_path or "",
        )
    console.print(table)
    console.print(f"[green]Done: {len(outcomes)} run(s).[/green]")


@cli_app.command("publish-wp")
def publish_wp(
    limit: int = typer.Option(None, help="Max HTML reports to publish this run"),
):
    ctx = new_run_context(task_id="cli_publish")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    console.print("[cyan]Loading settings...[/cyan]")
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_load_publish_settings_start",
            module=logger.name,
            fields={},
        )
    )
    settings = load_publish_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )

    console.print("[cyan]Publishing reports to WordPress...[/cyan]")
    outcomes = run_publish(settings, limit=limit, ctx=ctx)

    table = Table(title="Published Reports", box=box.SIMPLE_HEAVY)
    table.add_column("HTML")
    table.add_column("File ID")
    table.add_column("Status")
    table.add_column("Post URL")
    published = 0
    for outcome in outcomes:
        if outcome.status == "published":
            published += 1
        table.add_row(
            outcome.html_path,
            outcome.file_id or "",
            outcome.status,
            outcome.post_url or "",
        )

    console.print(table)
    console.print(f"[green]Done: {published} post(s) published.[/green]")


@cli_app.command("trace-run")
def trace_run(
    run_id: str = typer.Option("", help="Run ID to inspect."),
    trace_id: str = typer.Option("", help="Trace ID to inspect."),
    task_id: str = typer.Option("", help="Optional task ID filter."),
    log_path: str = typer.Option("", help="Structured log path to inspect."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
):
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
    console.print(
        f"[green]Done: {result.span_count} span(s), {result.event_count} event(s).[/green]"
    )


@cli_app.command("recategorize")
def recategorize():
    ctx = new_run_context(task_id="cli_recategorize")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    console.print("[cyan]Loading settings...[/cyan]")
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_load_settings_start",
            module=logger.name,
            fields={},
        )
    )
    s = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    console.print("[cyan]Recomputing categories...[/cyan]")
    outcomes = run_recategorize(
        RecategorizeRequest(
            schema_version="1.0",
            db_path=s.reports_db,
            category_mapping_path=s.category_mapping_path,
            settings=s,
        )
    )
    table = Table(title="Recategorization", box=box.SIMPLE_HEAVY)
    table.add_column("Title")
    table.add_column("File ID")
    table.add_column("Categories")
    table.add_column("Unmapped")
    table.add_column("Status")
    updated = 0
    for outcome in outcomes:
        if outcome.status == "updated":
            updated += 1
        cats = ", ".join(outcome.categories)
        unmapped = ", ".join(outcome.unmapped_tags)
        table.add_row(
            outcome.title,
            outcome.file_id,
            cats,
            unmapped,
            outcome.status
            if not outcome.error
            else f"{outcome.status}:{outcome.error}",
        )
    console.print(table)
    console.print(f"[green]Done: {updated} record(s) updated.[/green]")


@cli_app.command("generate-covers")
def generate_covers(
    style_config: str = typer.Option("", help="Override path to cover style YAML"),
    limit: int = typer.Option(None, help="Max reports to process this run"),
    file_id: str = typer.Option(None, help="Optional report file ID to process"),
):
    ctx = new_run_context(task_id="cli_generate_covers")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    console.print("[cyan]Loading settings...[/cyan]")
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_cover_generate_start",
            module=logger.name,
            fields={
                "style_config": style_config or "",
                "limit": limit,
                "file_id": file_id or "",
            },
        )
    )
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)

    console.print("[cyan]Generating cover images...[/cyan]")
    outcomes = run_cover_image_generation(
        CoverImageOrchestratorRequest(
            schema_version="1.0",
            reports_db=settings.reports_db,
            output_dir=settings.output_dir,
            style_config_path=style_config,
            limit=limit,
            file_id=file_id,
        ),
        ctx=ctx,
    )

    table = Table(title="Cover Images", box=box.SIMPLE_HEAVY)
    table.add_column("Report")
    table.add_column("File ID")
    table.add_column("Status")
    table.add_column("Output")
    for outcome in outcomes:
        table.add_row(
            outcome.title,
            outcome.file_id,
            outcome.status,
            outcome.output_path or outcome.error or "",
        )
    console.print(table)
    console.print(f"[green]Done: {len(outcomes)} report(s).[/green]")


@cli_app.command("update-wp-categories")
def update_wp_categories():
    ctx = new_run_context(task_id="cli_update_wp_categories")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    console.print("[cyan]Loading publish settings...[/cyan]")
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_load_publish_settings_start",
            module=logger.name,
            fields={},
        )
    )
    settings = load_publish_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )
    console.print("[cyan]Updating WordPress categories...[/cyan]")
    outcomes = run_update_wp_categories(settings)
    table = Table(title="WP Category Updates", box=box.SIMPLE_HEAVY)
    table.add_column("File ID")
    table.add_column("Post ID")
    table.add_column("Categories")
    table.add_column("Status")
    updated = 0
    for outcome in outcomes:
        if outcome.status == "updated":
            updated += 1
        cats = ", ".join(outcome.categories)
        table.add_row(
            outcome.file_id,
            str(outcome.post_id or ""),
            cats,
            outcome.status
            if not outcome.error
            else f"{outcome.status}:{outcome.error}",
        )
    console.print(table)
    console.print(f"[green]Done: {updated} post(s) updated.[/green]")


@cli_app.command("cost-report")
def cost_report(
    date: str = typer.Option(None, help="UTC date (YYYY-MM-DD) to summarize"),
    run_id: str = typer.Option(None, help="Run identifier to summarize"),
    top: int = typer.Option(5, help="Number of top-cost steps to show"),
):
    if (date and run_id) or (not date and not run_id):
        raise typer.BadParameter("Provide exactly one of --date or --run-id.")
    if top <= 0:
        raise typer.BadParameter("--top must be greater than zero.")

    console.print("[cyan]Loading settings...[/cyan]")
    ctx = new_run_context(task_id="cli_cost_report")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_cost_report_start",
            module=logger.name,
            fields={"date": date, "run_id": run_id, "top": top},
        )
    )
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)

    try:
        reporting = run_cost_reporting(
            CostReportingRequest(
                schema_version="1.0",
                report_request=CostReportRequest(
                    schema_version="1.0",
                    ledger_path=settings.cost_ledger_path,
                    date_utc=date,
                    run_id=RunId(run_id) if run_id else None,
                    top_n=top,
                ),
            ),
            ctx,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    report = reporting.report
    if report is None:
        console.print("[red]Cost report was not generated.[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[cyan]Cost report for {report.filter_type}={report.filter_value}[/cyan]"
    )
    totals = report.totals
    totals_table = Table(title="Totals", box=box.SIMPLE_HEAVY)
    totals_table.add_column("Metric")
    totals_table.add_column("Value", justify="right")
    totals_table.add_row("total_input_tokens", str(totals.total_input_tokens))
    totals_table.add_row("total_output_tokens", str(totals.total_output_tokens))
    totals_table.add_row("total_tool_calls", str(totals.total_tool_calls))
    totals_table.add_row("estimated_cost_usd", f"{totals.estimated_cost_usd:.6f}")
    console.print(totals_table)

    if report.top_steps:
        steps_table = Table(title="Top steps by cost", box=box.SIMPLE_HEAVY)
        steps_table.add_column("Step")
        steps_table.add_column("Cost (USD)", justify="right")
        steps_table.add_column("Input", justify="right")
        steps_table.add_column("Output", justify="right")
        steps_table.add_column("Tool calls", justify="right")
        for step in report.top_steps:
            steps_table.add_row(
                step.step_name,
                f"{step.estimated_cost_usd:.6f}",
                str(step.total_input_tokens),
                str(step.total_output_tokens),
                str(step.total_tool_calls),
            )
        console.print(steps_table)
    else:
        console.print("[yellow]No matching ledger entries found.[/yellow]")

    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_cost_report_complete",
            module=logger.name,
            fields={
                "filter_type": report.filter_type,
                "filter_value": report.filter_value,
                "matched_entries": report.matched_entries,
                "top_steps": len(report.top_steps),
            },
        )
    )


@cli_app.command("download-report")
def download_report(
    url: str = typer.Argument(..., help="Absolute report landing-page URL"),
    delivery_email: str = typer.Option(
        None,
        help="Optional email address used when the report is gated behind an email form",
    ),
    publisher_insights_url: str = typer.Option(
        None,
        help="Optional publisher insights URL used to resolve the publisher Drive folder",
    ),
    publisher_google_folder: str = typer.Option(
        None,
        help="Optional publisher Drive folder URL or folder ID for acquired artifacts",
    ),
):
    ctx = new_run_context(task_id="cli_download_report")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_download_report_start",
            module=logger.name,
            fields={
                "url": url,
                "has_delivery_email": bool(delivery_email),
                "has_publisher_insights_url": bool(publisher_insights_url),
                "has_publisher_google_folder": bool(publisher_google_folder),
            },
        )
    )
    settings = load_browser_download_settings(
        ConfigLoadRequest(schema_version="1.0", path=""),
        ctx,
    )
    result = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url=url,
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            delivery_email=delivery_email,
            publisher_insights_url=publisher_insights_url,
            publisher_google_folder=publisher_google_folder,
        ),
        ctx=ctx,
    )

    table = Table(title="Report Download", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("URL", result.source_url)
    table.add_row("Normalized URL", result.normalized_url)
    table.add_row("Route", result.route_kind)
    table.add_row("Outcome", result.outcome)
    table.add_row("Used memory route", "yes" if result.used_memory_route else "no")
    table.add_row("Final page", result.final_page_url)
    table.add_row(
        "Encountered form fields",
        ", ".join(result.encountered_form_fields),
    )
    table.add_row(
        "Identity fields added",
        ", ".join(result.identity_fields_added),
    )
    table.add_row("File", result.downloaded_file_path or "")
    table.add_row(
        "Drive uploads",
        ", ".join(
            f"{item.status}:{item.drive_file.file_id}" for item in result.drive_uploads
        ),
    )
    table.add_row("Summary", result.route_summary)
    console.print(table)


@cli_app.command("browser-doctor")
def browser_doctor(
    profile_dir: str = typer.Option(
        "out/browser_doctor/profile",
        help="Browser-use profile directory for the diagnostic run.",
    ),
    downloads_dir: str = typer.Option(
        "out/browser_doctor/downloads",
        help="Browser-use downloads directory for the diagnostic run.",
    ),
    verification_url: str = typer.Option(
        "",
        help="URL opened to verify browser-use tab/CDP state.",
    ),
    cdp_url: str = typer.Option(
        "",
        help="Optional existing Chrome remote-debugging URL to connect to.",
    ),
    headed: bool = typer.Option(
        False,
        "--headed",
        help="Run the diagnostic browser headed for manual inspection.",
    ),
    keep_browser_open: bool = typer.Option(
        False,
        "--keep-browser-open",
        help="Leave the diagnostic browser open after checks complete.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print the diagnostic result as JSON.",
    ),
    timeout_seconds: float = typer.Option(
        20.0,
        "--timeout-seconds",
        help="Per-operation browser diagnostic timeout.",
    ),
    reuse_session_key: str = typer.Option(
        "",
        "--reuse-session-key",
        help="Optional developer-canary browser session key for bounded profile reuse.",
    ),
    reuse_publisher_scope: str = typer.Option(
        "",
        "--reuse-publisher-scope",
        help="Publisher/domain scope allowed to reuse the browser session key.",
    ),
    reuse_ttl_seconds: float = typer.Option(
        0.0,
        "--reuse-ttl-seconds",
        help="TTL in seconds for developer-canary browser session profile reuse.",
    ),
    reuse_base_dir: str = typer.Option(
        "",
        "--reuse-base-dir",
        help="Optional base directory for reusable browser session profiles.",
    ),
):
    ctx = new_run_context(task_id="cli_browser_doctor")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    selected_verification_url = (
        str(verification_url or "").strip() or default_browser_doctor_verification_url()
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_browser_doctor_start",
            module=logger.name,
            fields={
                "profile_dir": profile_dir,
                "downloads_dir": downloads_dir,
                "verification_url": selected_verification_url,
                "has_cdp_url": bool(str(cdp_url or "").strip()),
                "headed": headed,
                "keep_browser_open": keep_browser_open,
            },
        )
    )
    result = run_browser_developer_diagnostics(
        BrowserDeveloperDiagnosticsRequest(
            schema_version="1.0",
            profile_path=profile_dir,
            downloads_path=downloads_dir,
            headed=bool(headed),
            verification_url=selected_verification_url,
            cdp_url=str(cdp_url or "").strip(),
            activate_verification_tab=True,
            cleanup_stale_once=True,
            keep_browser_open=bool(keep_browser_open),
            timeout_seconds=float(timeout_seconds),
            session_reuse_policy=BrowserDownloadSessionReusePolicy(
                schema_version="1.0",
                enabled=bool(str(reuse_session_key or "").strip()),
                mode="developer_canary",
                session_key=str(reuse_session_key or "").strip(),
                publisher_scope=str(reuse_publisher_scope or "").strip(),
                ttl_seconds=float(reuse_ttl_seconds),
                base_dir=str(reuse_base_dir or "").strip(),
                cleanup_expired=True,
                allow_cross_publisher=False,
            ),
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_browser_doctor_complete",
            module=logger.name,
            fields={
                "status": result.status,
                "browser_use_connected": result.browser_use_connected,
                "cdp_available": result.cdp_available,
                "real_tab_available": result.real_tab_available,
                "cleanup_attempted": result.cleanup_attempted,
                "cleanup_status": result.cleanup_status,
                "verification_tab_activated": result.verification_tab_activated,
            },
        )
    )
    if json_output:
        console.print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        table = Table(title="Browser Doctor", box=box.SIMPLE_HEAVY)
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Message")
        table.add_column("Detail")
        for check in result.checks:
            table.add_row(check.name, check.status, check.message, check.detail)
        console.print(table)
        console.print(f"[cyan]Profile:[/cyan] {result.profile_path}")
        console.print(f"[cyan]Downloads:[/cyan] {result.downloads_path}")
        console.print(f"[cyan]Active tab:[/cyan] {result.active_tab_url}")
        console.print(f"[cyan]CDP URL:[/cyan] {result.cdp_url or '(not exposed)'}")
    if result.status == "failed":
        raise typer.Exit(code=1)
    console.print(f"[green]Done: browser doctor {result.status}.[/green]")


@cli_app.command("promote-private-api-playbook")
def promote_private_api_playbook(
    request_json: str = typer.Option(
        ...,
        "--request-json",
        help=(
            "Path to a JSON BrowserRoutePrivateApiPromotionRequest produced from "
            "validated browser network evidence."
        ),
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print the promotion response as JSON.",
    ),
):
    ctx = new_run_context(task_id="cli_promote_private_api_playbook")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    request = _load_private_api_promotion_request(
        request_json=request_json,
        ctx=ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_private_api_playbook_promotion_start",
            module=logger.name,
            fields={
                "request_json": request_json,
                "source_url": request.source_url,
                "route_family": request.route_family,
                "route_kind": request.route_kind,
                "validated_success_count": request.validated_success_count,
                "endpoint_pattern": request.endpoint_pattern,
            },
        )
    )
    response = promote_private_api_evidence_to_browser_playbook(
        request=request,
        ctx=ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_private_api_playbook_promotion_complete",
            module=logger.name,
            fields={
                "playbook_id": response.playbook_id,
                "version": response.version,
                "path": response.path,
                "status": response.status,
                "review_diff_line_count": len(response.review_diff.splitlines()),
            },
        )
    )
    if json_output:
        console.print(json.dumps(asdict(response), ensure_ascii=False, indent=2))
    else:
        table = Table(title="Private API Playbook Promotion", box=box.SIMPLE_HEAVY)
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("Playbook", f"{response.playbook_id}@{response.version}")
        table.add_row("Status", response.status)
        table.add_row("Path", response.path)
        table.add_row("Review diff lines", str(len(response.review_diff.splitlines())))
        console.print(table)
    console.print(
        f"[green]Done: promoted private API playbook {response.playbook_id}.[/green]"
    )


@cli_app.command("discover-publisher-inventory")
def discover_publisher_inventory(
    insights_url: str = typer.Argument(..., help="Publisher insights URL to crawl"),
):
    ctx = new_run_context(task_id="cli_discover_publisher_inventory")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    settings = load_publisher_inventory_settings(
        ConfigLoadRequest(schema_version="1.0", path=""),
        ctx,
    )
    try:
        result = run_publisher_inventory_discovery(
            PublisherInventoryDiscoveryRequest(
                schema_version="1.0",
                insights_url=insights_url,
                reports_db=settings.reports_db,
                settings=settings,
            ),
            ctx=ctx,
        )
    except AppError as exc:
        if exc.code == "publisher_inventory_browser_pagination_limit":
            table = Table(title="Publisher Inventory Discovery", box=box.SIMPLE_HEAVY)
            table.add_column("Field")
            table.add_column("Value")
            table.add_row("Insights URL", insights_url)
            table.add_row("Outcome", "bounded")
            table.add_row("Status code", exc.code)
            table.add_row("Message", exc.message)
            console.print(table)
            return
        raise
    table = Table(title="Publisher Inventory Discovery", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Publisher", result.publisher_name)
    table.add_row("Insights URL", result.insights_url)
    table.add_row("Normalized URL", result.normalized_insights_url)
    table.add_row("Current reports", str(result.current_report_count))
    table.add_row("Previous reports", str(result.previous_report_count))
    table.add_row("Used memory route", "yes" if result.used_memory_route else "no")
    table.add_row("Snapshot changed", "yes" if result.snapshot_changed else "no")
    table.add_row("Run quality", result.run_quality_summary.quality_band)
    table.add_row("Run outcome", result.run_quality_summary.outcome)
    table.add_row(
        "Next route",
        result.run_quality_summary.recommended_route_kind,
    )
    console.print(table)

    diff_table = Table(title="New Report URLs", box=box.SIMPLE_HEAVY)
    diff_table.add_column("Page")
    diff_table.add_column("Title")
    diff_table.add_column("URL")
    for item in result.new_report_urls:
        diff_table.add_row(
            str(item.discovered_on_page_number),
            item.title,
            item.canonical_url,
        )
    console.print(diff_table)


@cli_app.command("drive-oauth-login")
def drive_oauth_login(
    client_json: str = typer.Option(
        "",
        help="Path to the Google OAuth desktop client JSON",
    ),
    token_json: str = typer.Option(
        "",
        help="Path where the authorized-user token JSON should be written",
    ),
    open_browser: bool = typer.Option(
        True,
        "--open-browser/--no-browser",
        help="Open the system browser for the OAuth consent flow",
    ),
    port: int = typer.Option(
        0,
        help="Local loopback port for the OAuth callback server; 0 picks a free port",
    ),
):
    ctx = new_run_context(task_id="cli_drive_oauth_login")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    resolved_client_json = (
        client_json.strip() or os.getenv("GOOGLE_OAUTH_CLIENT_JSON", "").strip()
    )
    resolved_token_json = (
        token_json.strip() or os.getenv("GOOGLE_OAUTH_TOKEN_JSON", "").strip()
    )
    if not resolved_client_json:
        console.print(
            "[red]Missing OAuth client JSON path. Pass --client-json or set GOOGLE_OAUTH_CLIENT_JSON.[/red]"
        )
        raise typer.Exit(code=1)
    if not resolved_token_json:
        console.print(
            "[red]Missing OAuth token output path. Pass --token-json or set GOOGLE_OAUTH_TOKEN_JSON.[/red]"
        )
        raise typer.Exit(code=1)
    result = authorize_oauth_user(
        DriveOAuthAuthorizeRequest(
            schema_version="1.0",
            client_secret_path=resolved_client_json,
            token_output_path=resolved_token_json,
            open_browser=open_browser,
            port=port,
        ),
        ctx,
    )
    table = Table(title="Drive OAuth Login", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Token path", result.token_output_path)
    table.add_row("Scopes", ", ".join(result.scopes))
    table.add_row("Refresh token", "yes" if result.refresh_token_present else "no")
    console.print(table)


@cli_app.command("audit-acquisition-paths")
def audit_acquisition_paths(
    publisher_limit: int = typer.Option(
        None,
        help="Optional maximum number of current publishers to audit",
    ),
    candidate_limit_per_publisher: int = typer.Option(
        None,
        help="Optional maximum number of current candidates to audit per publisher",
    ),
    delivery_email: str = typer.Option(
        None,
        help="Optional delivery email used when a report is gated behind email delivery",
    ),
):
    ctx = new_run_context(task_id="cli_audit_acquisition_paths")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_audit_acquisition_paths_start",
            module=logger.name,
            fields={
                "publisher_limit": publisher_limit,
                "candidate_limit_per_publisher": candidate_limit_per_publisher,
                "has_delivery_email": bool(delivery_email),
            },
        )
    )
    app_settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    publisher_inventory_settings = load_publisher_inventory_settings(
        ConfigLoadRequest(schema_version="1.0", path=""),
        ctx,
    )
    browser_download_settings = load_browser_download_settings(
        ConfigLoadRequest(schema_version="1.0", path=""),
        ctx,
    )
    result = run_acquisition_audit(
        AcquisitionAuditBatchRequest(
            schema_version="1.0",
            reports_db=app_settings.reports_db,
            publisher_inventory_settings=publisher_inventory_settings,
            browser_download_settings=browser_download_settings,
            output_dir=app_settings.output_dir,
            delivery_email=delivery_email,
            publisher_limit=publisher_limit,
            candidate_limit_per_publisher=candidate_limit_per_publisher,
        ),
        ctx=ctx,
    )

    summary_table = Table(title="Acquisition Audit", box=box.SIMPLE_HEAVY)
    summary_table.add_column("Field")
    summary_table.add_column("Value")
    summary_table.add_row("Generated at", result.generated_at_utc)
    summary_table.add_row("Artifact", result.output_path)
    summary_table.add_row("Publishers", str(result.publisher_count))
    summary_table.add_row("Candidates", str(result.candidate_count))
    console.print(summary_table)

    publisher_table = Table(title="Publisher Recommendations", box=box.SIMPLE_HEAVY)
    publisher_table.add_column("Publisher")
    publisher_table.add_column("Candidates", justify="right")
    publisher_table.add_column("Discovery")
    publisher_table.add_column("Recommendation")
    for publisher in result.publishers:
        publisher_table.add_row(
            publisher.publisher_name,
            str(publisher.current_candidate_count),
            publisher.recommended_discovery_route_kind,
            publisher.recommended_publisher_flow,
        )
    console.print(publisher_table)


@cli_app.command("sync-publishers")
def sync_publishers(
    snapshot_path: str = typer.Option(
        None,
        help="Optional override path to the publisher snapshot JSON sourced from Notion",
    ),
):
    ctx = new_run_context(task_id="cli_sync_publishers")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_sync_publishers_start",
            module=logger.name,
            fields={"snapshot_path_override": snapshot_path or ""},
        )
    )
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    result = run_publisher_sync(
        PublisherSyncRequest(
            schema_version="1.0",
            snapshot_path=snapshot_path or settings.publisher_profiles_path,
            reports_db=settings.reports_db,
        ),
        ctx=ctx,
    )

    table = Table(title="Publishers Sync", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Snapshot", result.snapshot_path)
    table.add_row("Reports DB", result.reports_db)
    table.add_row("Source page", result.source_page_url)
    table.add_row("Replaced publishers", str(result.replaced_count))
    console.print(table)


@cli_app.command("replay-run")
def replay_run(
    run_id: str = typer.Option(..., help="Original UI run identifier to replay"),
    registry_path: str | None = typer.Option(
        None,
        help="Optional UI-run registry path. Defaults to the configured state DB sibling.",
    ),
):
    ctx = new_run_context(task_id=f"cli_replay_run:{run_id}")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    resolved_registry_path = str(registry_path or "").strip()
    if not resolved_registry_path:
        settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
        resolved_registry_path = default_ui_run_registry_path(settings.state_db)
    result = replay_ui_run(
        UiRunReplayRequest(
            schema_version="1.0",
            registry_path=resolved_registry_path,
            run_id=RunId(run_id),
        ),
        ctx,
    )
    table = Table(title="UI Run Replay", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Run ID", str(result.original_record.run_id))
    table.add_row("Run type", result.original_record.run_type)
    table.add_row("Replay status", result.report.replay_status)
    table.add_row("Matched", str(result.report.matched))
    table.add_row("Manifest", result.manifest_path)
    table.add_row("Report", result.report_path)
    table.add_row("Delta count", str(len(result.report.deltas)))
    console.print(table)
    if not result.report.matched:
        raise typer.Exit(code=1)


@cli_app.command("generate-cross-report-analysis")
def generate_cross_report_analysis_cli(
    topic: str = typer.Option(
        "",
        "--topic",
        help="Topic text for the cross-report analysis.",
    ),
    auto_theme: bool | None = typer.Option(
        None,
        "--auto-theme/--no-auto-theme",
        help="Allow deterministic automatic theme selection; omitted uses YAML config.",
    ),
    category: str = typer.Option(
        "",
        "--category",
        "--categories",
        help="Comma-separated category filters.",
    ),
    tag: str = typer.Option(
        "",
        "--tag",
        "--tags",
        help="Comma-separated tag filters.",
    ),
    publisher: str = typer.Option(
        "",
        "--publisher",
        "--publishers",
        help="Comma-separated publisher filters.",
    ),
    date_start: str = typer.Option(
        "",
        "--date-start",
        help="Inclusive report date lower bound in YYYY-MM-DD format.",
    ),
    date_end: str = typer.Option(
        "",
        "--date-end",
        help="Inclusive report date upper bound in YYYY-MM-DD format.",
    ),
    max_report_count: int | None = typer.Option(
        None,
        "--max-report-count",
        help="Maximum source reports to select.",
    ),
    max_evidence_items: int | None = typer.Option(
        None,
        "--max-evidence-items",
        help="Maximum evidence references to retain for synthesis.",
    ),
    max_prompt_chars: int | None = typer.Option(
        None,
        "--max-prompt-chars",
        help="Maximum rendered prompt characters before model generation.",
    ),
    publish_mode: str = typer.Option(
        "generate_only",
        "--publish-mode",
        help="One of generate_only, validate_only, publish_dry_run, publish_live.",
    ),
    output_root: str = typer.Option(
        "",
        "--output-root",
        help="Override output root for generated artifacts.",
    ),
    idempotency_db: str = typer.Option(
        "",
        "--idempotency-db",
        help="Override SQLite idempotency database path.",
    ),
    request_id: str = typer.Option(
        "",
        "--request-id",
        help="Optional stable request id; defaults to a hash of normalized inputs.",
    ),
):
    ctx = new_run_context(task_id="cli_generate_cross_report_analysis")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    try:
        settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
        request = _build_cross_report_cli_request(
            settings=settings,
            topic=topic,
            auto_theme=auto_theme,
            category=category,
            tag=tag,
            publisher=publisher,
            date_start=date_start,
            date_end=date_end,
            max_report_count=max_report_count,
            max_evidence_items=_optional_int_cli_value(max_evidence_items),
            max_prompt_chars=_optional_int_cli_value(max_prompt_chars),
            publish_mode=publish_mode,
            output_root=output_root,
            idempotency_db=idempotency_db,
            request_id=request_id,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="cli_generate_cross_report_analysis_start",
                module=logger.name,
                fields={
                    "request_id": request.analysis_request.request_id,
                    "topic": request.analysis_request.topic,
                    "auto_theme": request.analysis_request.auto_theme,
                    "publication_mode": request.analysis_request.publication_mode,
                    "output_root": request.output_root,
                },
            )
        )
        publish_settings = None
        if request.analysis_request.publication_mode == "publish_live":
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="cli_cross_report_load_publish_settings_start",
                    module=logger.name,
                    fields={
                        "request_id": request.analysis_request.request_id,
                        "publication_mode": request.analysis_request.publication_mode,
                    },
                )
            )
            publish_settings = load_publish_settings(
                ConfigLoadRequest(schema_version="1.0", path=""),
                ctx,
            )
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="cli_cross_report_load_publish_settings_complete",
                    module=logger.name,
                    fields={
                        "request_id": request.analysis_request.request_id,
                        "site_url": publish_settings.wp.site_url,
                        "post_type": publish_settings.wp.post_type,
                        "post_status": publish_settings.wp.post_status,
                    },
                )
            )
        outcome = run_cross_report_analysis_orchestrator(
            request,
            settings,
            ctx,
            publish_settings=publish_settings,
        )
    except AppError as exc:
        console.print(f"[red]Error [{exc.code}]: {exc.message}[/red]")
        raise typer.Exit(code=1) from exc

    table = Table(title="Cross-Report Analysis", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Artifact", outcome.artifact_path)
    table.add_row("Selected theme", outcome.generated_result.selected_theme.label)
    table.add_row(
        "Selected reports", str(len(outcome.generated_result.selected_sources))
    )
    table.add_row("Validation", outcome.validation_result.status)
    table.add_row("Publication mode", outcome.publish_result.publication_mode)
    table.add_row("Target route", outcome.publish_result.target_route)
    if outcome.publish_result.post_id is not None:
        table.add_row("Post ID", str(outcome.publish_result.post_id))
    if outcome.publish_result.post_url:
        table.add_row("Post URL", outcome.publish_result.post_url)
    table.add_row("Idempotency reused", "yes" if outcome.idempotency_reused else "no")
    cost_summary = outcome.generated_result.cost_summary or {}
    if cost_summary:
        table.add_row("Cost summary", json.dumps(cost_summary, ensure_ascii=False))
    console.print(table)
    console.print(f"[green]Done: {outcome.status}.[/green]")


@cli_app.command("ui-run-worker", hidden=True)
def ui_run_worker(
    request_json: str = typer.Option(
        ...,
        "--request-json",
        help="Internal worker request JSON path.",
    ),
):
    worker_request = _load_ui_run_worker_request(request_json)
    ctx = new_run_context(task_id=f"ui_run_worker:{worker_request.run_type}")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    started_at = _utc_now()
    _update_ui_run_record(
        worker_request=worker_request,
        run_ctx=ctx,
        status="running",
        started_at_utc=started_at,
        pid=os.getpid(),
    )
    print(
        f"[ui-run-worker] started run_id={worker_request.run_id} type={worker_request.run_type}",
        flush=True,
    )
    try:
        execution = execute_ui_run(worker_request, ctx)
        finished_at = _utc_now()
        write_ui_run_replay_manifest(
            UiRunReplayCaptureRequest(
                schema_version="1.0",
                registry_path=worker_request.registry_path,
                run_id=worker_request.run_id,
                run_type=worker_request.run_type,
                status=execution.status,
                recorded_at_utc=finished_at,
                request_payload=worker_request.request_payload,
                config_snapshot=execution.config_snapshot,
                config_fingerprint=execution.config_fingerprint,
                source_tree_root=str(SOURCE_TREE_ROOT),
                prompt_tree_root=str(PROMPT_TREE_ROOT),
                artifact_paths=execution.artifact_paths,
                result_summary=execution.result_summary,
                error_code=execution.error_code,
                error_message=execution.error_message,
            ),
            ctx,
        )
        if execution.status != "succeeded":
            _update_ui_run_record(
                worker_request=worker_request,
                run_ctx=ctx,
                status="failed",
                finished_at_utc=finished_at,
                pid=os.getpid(),
                exit_code=1,
                error_code=execution.error_code or "ui_run_worker_failed",
                error_message=execution.error_message or "UI run execution failed.",
                error_retryable=execution.error_retryable,
                error_severity=execution.error_severity,
            )
            print(
                f"[ui-run-worker] failed run_id={worker_request.run_id} code={execution.error_code} message={execution.error_message}",
                flush=True,
            )
            raise typer.Exit(code=1)
        _update_ui_run_record(
            worker_request=worker_request,
            run_ctx=ctx,
            status="succeeded",
            finished_at_utc=finished_at,
            pid=os.getpid(),
            exit_code=0,
            result_summary=execution.result_summary,
            artifact_paths=execution.artifact_paths,
        )
        print(
            f"[ui-run-worker] completed run_id={worker_request.run_id}",
            flush=True,
        )
    except AppError as exc:
        _update_ui_run_record(
            worker_request=worker_request,
            run_ctx=ctx,
            status="failed",
            finished_at_utc=_utc_now(),
            pid=os.getpid(),
            exit_code=1,
            error_code=exc.code,
            error_message=exc.message,
            error_retryable=exc.retryable,
            error_severity=exc.severity,
        )
        print(
            f"[ui-run-worker] failed run_id={worker_request.run_id} code={exc.code} message={exc.message}",
            flush=True,
        )
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _update_ui_run_record(
            worker_request=worker_request,
            run_ctx=ctx,
            status="failed",
            finished_at_utc=_utc_now(),
            pid=os.getpid(),
            exit_code=1,
            error_code="ui_run_worker_failed",
            error_message=str(exc),
            error_retryable=False,
            error_severity="error",
        )
        print(
            f"[ui-run-worker] failed run_id={worker_request.run_id} error={exc}",
            flush=True,
        )
        raise typer.Exit(code=1)


@cli_app.callback(invoke_without_command=True)
def cli(
    ctx: typer.Context,
    folder: str = typer.Option(None, help="Override Drive folder ID"),
    limit: int = typer.Option(None, help="Max PDFs to process this run"),
):
    if ctx.invoked_subcommand is None:
        ingest(folder=folder, limit=limit)


def main() -> None:
    cli_app()


if __name__ == "__main__":
    main()
