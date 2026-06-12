from __future__ import annotations

import json
from datetime import date
from typing import Any, cast

import typer
from rich.table import Table
from rich import box

from src.utils.errors import AppError
from src.contracts.config import ConfigLoadRequest
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisOrchestratorRequest,
    CrossReportAnalysisRequest,
    CrossReportProjectedDataReadRequest,
    PublicationMode,
)
from src.contracts.logging import LoggingSetupRequest
from src.orchestrators.cross_report_analysis_orchestrator import (
    run_cross_report_analysis as run_cross_report_analysis_orchestrator,
)
from src.services.config_service import (
    load_settings,
    load_publish_settings,
)
from src.services.logging_service import setup_logging
from src.utils.logging import log_event, new_run_context

from src._cli.app import cli_app, console, logger
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


_CROSS_REPORT_PUBLICATION_MODES = {
    "generate_only",
    "validate_only",
    "publish_dry_run",
    "publish_live",
}


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
    _sync_cli_patch_points()
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
    if outcome.publish_result.target_post_type:
        table.add_row("Target post type", outcome.publish_result.target_post_type)
    if outcome.publish_result.target_slug:
        table.add_row("Target slug", outcome.publish_result.target_slug)
    if outcome.publish_result.category_slugs:
        table.add_row("Categories", ", ".join(outcome.publish_result.category_slugs))
    if outcome.publish_result.tag_slugs:
        table.add_row("Tags", ", ".join(outcome.publish_result.tag_slugs))
    if outcome.publish_result.taxonomy_term_slugs:
        taxonomy_labels = [
            f"{taxonomy}: {', '.join(slugs)}"
            for taxonomy, slugs in sorted(
                outcome.publish_result.taxonomy_term_slugs.items()
            )
            if slugs
        ]
        if taxonomy_labels:
            table.add_row("Taxonomy terms", "; ".join(taxonomy_labels))
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
