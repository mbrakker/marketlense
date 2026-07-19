from __future__ import annotations

import time
from dataclasses import asdict

import typer
from rich import box
from rich.table import Table

from src._cli.app import cli_app, console, logger
from src._cli.runtime import sync_cli_patch_points
from src.contracts.categories import RecategorizeRequest
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.costs import CostReportingRequest, CostReportRequest
from src.contracts.cover_images import CoverImageOrchestratorRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.semantic_ids import RunId
from src.contracts.state import WorkflowControlObservationWriteRequest
from src.contracts.wordpress_intelligence_projection import (
    WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
    WordPressIntelligenceSourceReadRequest,
    WordPressIntelligenceSyncRequest,
)
from src.contracts.workflow_control import (
    PipelineExecutionAuthorizationRequest,
    WorkflowControlObservation,
)
from src.orchestrators import workflow_control_orchestrator as workflow_control
from src.orchestrators.candidate_extraction_orchestrator import run_candidate_extraction
from src.orchestrators.cost_reporting_orchestrator import run_cost_reporting
from src.orchestrators.cover_image_orchestrator import run_cover_image_generation
from src.orchestrators.ingest_orchestrator import run_ingest
from src.orchestrators.publish_orchestrator import run_publish
from src.orchestrators.recategorize_orchestrator import run_recategorize
from src.orchestrators.wordpress_intelligence_projection_orchestrator import (
    sync_wordpress_intelligence_projection,
)
from src.orchestrators.wp_category_update_orchestrator import run_update_wp_categories
from src.services.config_service import (
    build_ingest_settings,
    load_publish_settings,
    load_settings,
    load_workflow_control_settings,
)
from src.services.logging_service import setup_logging
from src.services.state_service import write_workflow_control_observation
from src.utils.clock import utc_now_iso
from src.utils.errors import AppError
from src.utils.logging import log_event, new_run_context
from src.utils.wp_auth import build_auth_header

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
    "write_workflow_control_observation",
    "_resolve_cli_workflow_control",
)


def _sync_cli_patch_points() -> None:
    sync_cli_patch_points(globals(), _CLI_PATCH_POINTS)


@cli_app.command("sync-wordpress-intelligence")
def sync_wordpress_intelligence() -> None:
    """Rebuild WordPress homepage intelligence from approved published entities."""
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_sync_wordpress_intelligence")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    settings = load_publish_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )
    auth_header = build_auth_header(
        username=settings.wp.username,
        app_password=settings.wp.app_password,
        bearer_token=settings.wp.bearer_token,
    )
    outcome = sync_wordpress_intelligence_projection(
        WordPressIntelligenceSyncRequest(
            schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
            source_request=WordPressIntelligenceSourceReadRequest(
                schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
                base_url=settings.wp.site_url,
                auth_header=auth_header,
                ssl_verify=settings.wp.ssl_verify,
                ca_bundle_path=settings.wp.ca_bundle_path,
            ),
            generated_at_utc=utc_now_iso(),
            state_db=settings.state_db,
        ),
        ctx,
    )
    table = Table(title="WordPress Intelligence Projection", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Approved entities", str(outcome.entity_count))
    table.add_row("Reports", str(outcome.projection.homepage_metrics.report_count))
    table.add_row("Briefings", str(outcome.projection.homepage_metrics.briefing_count))
    table.add_row("Signals", str(outcome.projection.homepage_metrics.signal_count))
    table.add_row("Generated", outcome.write_response.generated_at_utc)
    console.print(table)


def _resolve_cli_workflow_control(
    *,
    intent: str,
    ctx,
    subject: str = "",
    publisher: str = "",
    report_id: str = "",
    requested_side_effects: list[str] | None = None,
    run_profile: str = "",
    profile_overrides: dict[str, str | int | float | bool] | None = None,
) -> dict[str, object]:
    settings = load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )
    resolved = workflow_control.resolve_run_intent(
        workflow_control.RunIntent(
            schema_version="1.0",
            intent=intent,
            subject=subject,
            publisher=publisher,
            report_id=report_id,
            requested_side_effects=list(requested_side_effects or []),
            dry_run=False,
            allow_automation=True,
            metadata={"source": "cli"},
            run_profile=run_profile,
            profile_overrides=dict(profile_overrides or {}),
        ),
        settings,
        ctx=ctx,
    )
    plan = workflow_control.build_pipeline_execution_plan(
        workflow_control.RunIntent(
            schema_version="1.0",
            intent=intent,
            subject=subject,
            publisher=publisher,
            report_id=report_id,
            requested_side_effects=list(requested_side_effects or []),
            dry_run=True,
            allow_automation=False,
            metadata={"source": "cli"},
            run_profile=run_profile,
            profile_overrides=dict(profile_overrides or {}),
        ),
        settings,
        ctx=ctx,
    )
    authorization = workflow_control.authorize_pipeline_execution(
        PipelineExecutionAuthorizationRequest(
            schema_version="1.0",
            plan=plan,
            expected_workflow=resolved.workflow,
            requested_side_effects=list(requested_side_effects or []),
        ),
        ctx=ctx,
    )
    retry_policy_id = ""
    if resolved.workflow:
        step_name = (
            "wordpress_publish"
            if resolved.workflow == "publishing"
            else "report_pipeline"
            if resolved.workflow == "report_generation"
            else "execute"
        )
        retry_policy_id = workflow_control.resolve_retry_policy(
            settings,
            workflow_name=resolved.workflow,
            step_name=step_name,
            ctx=ctx,
        ).policy_id
    payload: dict[str, object] = {
        "status": resolved.status,
        "workflow": resolved.workflow,
        "preflight_profile": resolved.preflight_profile,
        "budget_profile": resolved.budget_profile,
        "retry_policy_id": retry_policy_id,
        "run_profile": plan.run_profile,
        "run_profile_hash": plan.run_profile_hash,
        "recommended_run_profile": plan.recommended_run_profile,
        "profile_effective_selections": dict(plan.profile_effective_selections),
        "resume_stage": resolved.resume_stage,
        "side_effect_plan": list(resolved.side_effect_plan),
        "alternatives": list(resolved.alternatives),
        "blockers": list(resolved.blockers),
        "execution_plan": {
            "schema_version": plan.schema_version,
            "intent_key": plan.intent_key,
            "workflow": plan.workflow,
            "profile": plan.profile,
            "ordered_steps": list(plan.ordered_steps),
            "skipped_steps": list(plan.skipped_steps),
            "blocked_steps": list(plan.blocked_steps),
            "required_credentials": list(plan.required_credentials),
            "checkpoints": list(plan.checkpoints),
            "expected_artifacts": list(plan.expected_artifacts),
            "planned_side_effects": list(plan.planned_side_effects),
            "idempotency_key": plan.idempotency_key,
            "executable": plan.executable,
            "blockers": list(plan.blockers),
        },
        "execution_authority": asdict(authorization),
    }
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_workflow_control_resolved",
            module=logger.name,
            fields=payload,
        )
    )
    console.print(
        "[cyan]Workflow control:[/cyan] "
        f"{payload['workflow'] or payload['status']} "
        f"(profile={payload['preflight_profile'] or '-'}, "
        f"retry={payload['retry_policy_id'] or '-'})"
    )
    return payload


def _record_cli_workflow_feedback(
    *,
    state_db: str,
    workflow: str,
    step_name: str,
    route: str,
    outcome: str,
    count: int,
    started_at: float,
    ctx,
) -> None:
    latency_ms = max(0, int((time.perf_counter() - started_at) * 1000))
    write_workflow_control_observation(
        WorkflowControlObservationWriteRequest(
            schema_version="1.0",
            state_db=state_db,
            observation=WorkflowControlObservation(
                schema_version="1.0",
                observed_at_utc=utc_now_iso(),
                run_id=str(ctx.run_id),
                workflow=workflow,
                step_name=step_name,
                route=route,
                publisher="",
                report_key="",
                outcome=outcome,
                error_code="",
                error_retryable=False,
                error_severity="",
                latency_ms=latency_ms,
                cost_usd=0.0,
                retry_count=0,
                resource_pressure={"item_count": int(count)},
            ),
        ),
        ctx,
    )


@cli_app.command("plan")
def plan_execution(
    intent: str = typer.Argument(..., help="Requested workflow outcome to plan"),
    subject: str = typer.Option("", help="Optional report, URL, or task subject"),
    publisher: str = typer.Option("", help="Optional publisher context"),
    report_id: str = typer.Option("", help="Optional report identifier"),
    profile: str = typer.Option(
        "",
        "--profile",
        help="Explicit approved profile; omit to retain safe default",
    ),
):
    """Print a side-effect-free execution plan without launching a workflow."""
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_execution_plan")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    settings = load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )
    plan = workflow_control.build_pipeline_execution_plan(
        workflow_control.RunIntent(
            schema_version="1.0",
            intent=intent,
            subject=subject,
            publisher=publisher,
            report_id=report_id,
            requested_side_effects=[],
            dry_run=True,
            allow_automation=False,
            metadata={"source": "cli_plan"},
            run_profile=profile,
        ),
        settings,
        ctx=ctx,
    )
    console.print_json(data=asdict(plan))


@cli_app.command("ingest")
def ingest(
    folder: str = typer.Option(None, help="Override Drive folder ID"),
    limit: int = typer.Option(None, help="Max PDFs to process this run"),
    force_report_cards: bool = typer.Option(
        False,
        "--force-report-cards",
        help="Reprocess reports whose report-card manifest is missing or invalid",
    ),
    rescan: bool = typer.Option(
        False,
        "--rescan",
        help="Ignore the ingest cursor and list Drive from the current folder scope",
    ),
):
    _sync_cli_patch_points()
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
    _resolve_cli_workflow_control(
        intent="ingest new reports",
        ctx=ctx,
        requested_side_effects=["pdf", "model"],
    )
    s = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    settings = build_ingest_settings(
        IngestSettingsBuildRequest(schema_version="1.0", app_settings=s),
        ctx,
    )
    console.print("[cyan]Running ingest pipeline...[/cyan]")
    started_at = time.perf_counter()
    try:
        outcomes = run_ingest(
            settings,
            folder_id=folder,
            limit=limit,
            ctx=ctx,
            force_report_cards=force_report_cards,
            rescan=rescan,
        )
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
    _record_cli_workflow_feedback(
        state_db=settings.state_db,
        workflow="report_generation",
        step_name="ingest",
        route="cli",
        outcome=(
            "succeeded"
            if any(outcome.status == "processed" for outcome in outcomes)
            else "completed"
        ),
        count=len(outcomes),
        started_at=started_at,
        ctx=ctx,
    )

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
    _sync_cli_patch_points()
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
    draft: bool = typer.Option(
        False,
        "--draft",
        help=(
            "Create new WordPress posts as drafts for review instead of using the "
            "configured publication status."
        ),
    ),
    force_report_cards: bool = typer.Option(
        False,
        "--force-report-cards",
        help="Update existing report posts in place with canonical card metadata",
    ),
):
    _sync_cli_patch_points()
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
    _resolve_cli_workflow_control(
        intent="publish ready reports",
        ctx=ctx,
        requested_side_effects=["wordpress", "publish"],
    )
    settings = load_publish_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )

    console.print("[cyan]Publishing reports to WordPress...[/cyan]")
    started_at = time.perf_counter()
    outcomes = run_publish(
        settings,
        limit=limit,
        ctx=ctx,
        force_report_cards=force_report_cards,
        force_draft=draft,
    )
    _record_cli_workflow_feedback(
        state_db=settings.state_db,
        workflow="publishing",
        step_name="wordpress_publish",
        route="cli",
        outcome=(
            "succeeded"
            if any(outcome.status == "published" for outcome in outcomes)
            else "completed"
        ),
        count=len(outcomes),
        started_at=started_at,
        ctx=ctx,
    )

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


@cli_app.command("recategorize")
def recategorize():
    _sync_cli_patch_points()
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
    _sync_cli_patch_points()
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
            schema_version="2.0",
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
    table.add_column("Small")
    table.add_column("Medium")
    table.add_column("Large")
    table.add_column("Error")
    for outcome in outcomes:
        assets = outcome.assets
        table.add_row(
            outcome.title,
            outcome.file_id,
            outcome.status,
            assets.small.output_path if assets else "",
            assets.medium.output_path if assets else "",
            assets.large.output_path if assets else "",
            outcome.error or "",
        )
    console.print(table)
    console.print(f"[green]Done: {len(outcomes)} report(s).[/green]")


@cli_app.command("update-wp-categories")
def update_wp_categories():
    _sync_cli_patch_points()
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
    _sync_cli_patch_points()
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
