# ruff: noqa: B008, E501

from __future__ import annotations

import json
import os
from dataclasses import asdict

import typer
from rich import box
from rich.table import Table

from src._cli.app import cli_app, console, logger
from src._cli.runtime import sync_cli_patch_points
from src.contracts.artifact_lineage import (
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    ArtifactLineageAuditRequest,
    ArtifactLineageBackfillRequest,
)
from src.contracts.config import ConfigLoadRequest
from src.contracts.corpus_rehabilitation import (
    CorpusRehabilitationCampaignApprovalRequest,
    CorpusRehabilitationCampaignCreateRequest,
    CorpusRehabilitationPlanRequest,
)
from src.contracts.drive import DriveOAuthAuthorizeRequest
from src.contracts.files import ReadBytesRequest, WriteBytesRequest
from src.contracts.llm_usage import LLMPolicyEffectivenessRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.pdf_utils import PdfIntegrityCheckRequest
from src.contracts.publisher_profiles import PublisherSyncRequest
from src.contracts.report_store import AcquisitionRouteEconomicsRequest
from src.contracts.state import (
    SourceQuarantineGetRequest,
    SourceQuarantineListRequest,
    SourceQuarantineRecord,
    SourceQuarantineUpsertRequest,
)
from src.generators.claim_validation_generator import validate_retained_claims
from src.orchestrators.publisher_sync_orchestrator import run_publisher_sync
from src.orchestrators.corpus_rehabilitation_orchestrator import (
    submit_corpus_rehabilitation_campaign,
)
from src.services.config_service import (
    load_settings,
)
from src.services.drive_service import authorize_oauth_user
from src.services.file_service import read_bytes, write_bytes
from src.services.llm_usage_ledger_service import read_policy_effectiveness
from src.services.logging_service import setup_logging
from src.services.pdf_service import check_pdf_integrity
from src.services.report_store_service import (
    audit_artifact_lineage,
    backfill_artifact_lineage,
    read_acquisition_route_economics,
    read_corpus_rehabilitation_plan,
    approve_corpus_rehabilitation_campaign,
    create_corpus_rehabilitation_campaign,
)
from src.services.state_service import (
    get_source_quarantine,
    list_source_quarantines,
    upsert_source_quarantine,
)
from src.utils.logging import log_event, new_run_context

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


def _campaign_output(response) -> dict[str, object]:
    """Project campaign results without dumping an unbounded lineage-ID list."""
    campaign = asdict(response.campaign)
    return {
        "campaign": campaign,
        "created": response.created,
        "items": [
            {
                "report_id": item.report_id,
                "classification": item.classification,
                "disposition": item.disposition,
                "status": item.status,
                "reason": item.reason,
                "reusable_artifact_count": len(item.reusable_artifact_ids),
                "queue_job_id": item.queue_job_id,
            }
            for item in response.items
        ],
    }


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
    _sync_cli_patch_points()
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


@cli_app.command("sync-publishers")
def sync_publishers(
    snapshot_path: str = typer.Option(
        None,
        help="Optional override path to the publisher snapshot JSON sourced from Notion",
    ),
):
    _sync_cli_patch_points()
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


@cli_app.command("backfill-artifact-lineage")
def backfill_artifact_lineage_command(
    reports_db: str = typer.Option(
        "state/reports.sqlite",
        help="Existing reports SQLite database; does not require provider credentials.",
    ),
    checkpoint_root: str = typer.Option(
        "out/.checkpoints/report_generation",
        help="Existing report-generation checkpoint directory to scan",
    ),
    limit: int = typer.Option(100, min=1, help="Maximum checkpoint files to inspect"),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--apply",
        help="Inspect only by default; --apply records missing immutable lineage rows",
    ),
) -> None:
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_backfill_artifact_lineage")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    result = backfill_artifact_lineage(
        ArtifactLineageBackfillRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=reports_db,
            checkpoint_root=checkpoint_root,
            limit=limit,
            dry_run=dry_run,
        ),
        ctx,
    )
    table = Table(title="Artifact Lineage Backfill", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Mode", "dry run" if result.dry_run else "apply")
    table.add_row("Checkpoints scanned", str(result.scanned_checkpoints))
    table.add_row("Eligible artifacts", str(result.eligible_artifacts))
    table.add_row("New records", str(result.created_artifacts))
    table.add_row("Skipped", str(result.skipped_artifacts))
    table.add_row("Planner-unverified", str(result.incomplete_artifacts))
    console.print(table)
    if not dry_run:
        audit = audit_artifact_lineage(
            ArtifactLineageAuditRequest(
                schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
                db_path=reports_db,
            ),
            ctx,
        )
        console.print(
            "Lineage audit: "
            f"{len(audit.items)} records; status counts {audit.status_counts}"
        )


@cli_app.command("policy-effectiveness")
def policy_effectiveness(
    usage_db: str = typer.Option(
        "state/llm_usage.sqlite",
        help="Canonical usage SQLite database; report generation is read-only.",
    ),
) -> None:
    """Show bounded model-policy evidence grouped by execution identity."""

    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_policy_effectiveness")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    response = read_policy_effectiveness(
        LLMPolicyEffectivenessRequest(schema_version="1.0", db_path=usage_db), ctx
    )
    table = Table(title="LLM Policy Effectiveness", box=box.SIMPLE_HEAVY)
    table.add_column("Namespace")
    table.add_column("Identity")
    table.add_column("Calls", justify="right")
    table.add_column("Valid", justify="right")
    table.add_column("Cache", justify="right")
    table.add_column("Latency ms", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Regens", justify="right")
    for row in response.rows:
        table.add_row(
            row.prompt_namespace,
            row.execution_identity[:12],
            str(row.call_count),
            f"{row.validation_rate:.1%}",
            f"{row.cache_reuse_rate:.1%}",
            "-" if row.average_latency_ms is None else f"{row.average_latency_ms:.3f}",
            str(row.input_tokens + row.output_tokens),
            f"${row.estimated_cost_usd:.6f}",
            str(row.regeneration_count),
        )
    console.print(table)
    console.print(
        f"Legacy unattributed calls: {response.unattributed_legacy_call_count}; "
        f"execution-identity cohorts: {len(response.rows)}"
    )


@cli_app.command("corpus-rehabilitation-plan")
def corpus_rehabilitation_plan(
    reports_db: str = typer.Option(
        "state/reports.sqlite",
        help="Canonical reports database; this command is read-only.",
    ),
    limit: int = typer.Option(100, min=1, max=500),
) -> None:
    """Classify retained corpus candidates before an operator creates any campaign."""

    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_corpus_rehabilitation_plan")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    response = read_corpus_rehabilitation_plan(
        CorpusRehabilitationPlanRequest(
            schema_version="1.0", db_path=reports_db, limit=limit
        ),
        ctx,
    )
    table = Table(title="Corpus Rehabilitation Plan", box=box.SIMPLE_HEAVY)
    for heading in ("Report", "Classification", "Disposition", "Reuse", "Reason"):
        table.add_column(heading)
    for candidate in response.candidates:
        table.add_row(
            candidate.report_id,
            candidate.classification,
            candidate.disposition,
            str(candidate.reusable_artifact_count),
            candidate.reason,
        )
    console.print(table)
    console.print_json(data={"classification_counts": response.classification_counts})


@cli_app.command("corpus-rehabilitation-create")
def corpus_rehabilitation_create(
    reports_db: str = typer.Option("state/reports.sqlite"),
    report_id: list[str] = typer.Option([], "--report-id"),
    batch_size: int = typer.Option(10, min=1, max=100),
    created_by: str = typer.Option("operator"),
) -> None:
    """Persist a bounded retained-evidence campaign; this does not queue work."""
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_corpus_rehabilitation_create")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    result = create_corpus_rehabilitation_campaign(
        CorpusRehabilitationCampaignCreateRequest(
            schema_version="1.0", db_path=reports_db, report_ids=report_id,
            batch_size=batch_size, created_by=created_by,
        ),
        ctx,
    )
    console.print_json(data=_campaign_output(result))


@cli_app.command("corpus-rehabilitation-approve")
def corpus_rehabilitation_approve(
    campaign_id: str = typer.Option(...),
    approved_by: str = typer.Option(...),
    reason: str = typer.Option(...),
    reports_db: str = typer.Option("state/reports.sqlite"),
    yes: bool = typer.Option(False, "--yes"),
) -> None:
    """Record explicit approval before the campaign can enter the workflow queue."""
    if not yes:
        raise typer.BadParameter("--yes is required to approve a rehabilitation campaign")
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_corpus_rehabilitation_approve")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    result = approve_corpus_rehabilitation_campaign(
        CorpusRehabilitationCampaignApprovalRequest(
            schema_version="1.0", db_path=reports_db, campaign_id=campaign_id,
            approved_by=approved_by, reason=reason,
        ),
        ctx,
    )
    console.print_json(data=_campaign_output(result))


@cli_app.command("corpus-rehabilitation-submit")
def corpus_rehabilitation_submit(
    campaign_id: str = typer.Option(...),
    reports_db: str = typer.Option("state/reports.sqlite"),
    state_db: str = typer.Option("state/index.sqlite"),
    limit: int = typer.Option(10, min=1, max=100),
    yes: bool = typer.Option(False, "--yes"),
) -> None:
    """Hand off proof-complete approved items to the existing maintenance queue."""
    if not yes:
        raise typer.BadParameter("--yes is required to queue a rehabilitation campaign")
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_corpus_rehabilitation_submit")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    result = submit_corpus_rehabilitation_campaign(
        reports_db=reports_db, state_db=state_db, campaign_id=campaign_id,
        ctx=ctx, limit=limit,
    )
    console.print_json(data=_campaign_output(result))


@cli_app.command("route-economics")
def route_economics(
    reports_db: str = typer.Option(
        "state/reports.sqlite",
        help="Canonical reports SQLite database; report generation is read-only.",
    ),
) -> None:
    """Show compatible acquisition cohorts and operator-reviewable proposals."""

    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_route_economics")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    response = read_acquisition_route_economics(
        AcquisitionRouteEconomicsRequest(schema_version="1.0", db_path=reports_db),
        ctx,
    )
    table = Table(title="Acquisition Route Economics", box=box.SIMPLE_HEAVY)
    table.add_column("Publisher")
    table.add_column("Policy")
    table.add_column("Route")
    table.add_column("Complete/sample", justify="right")
    table.add_column("Verified", justify="right")
    table.add_column("p50/p95 ms", justify="right")
    table.add_column("Cost", justify="right")
    for row in response.cohorts:
        table.add_row(
            row.publisher_id,
            row.route_policy_hash[:12],
            row.route_family,
            f"{row.complete_sample_size}/{row.sample_size}",
            f"{row.verified_success_rate:.1%}",
            f"{row.median_elapsed_ms or '-'} / {row.p95_elapsed_ms or '-'}",
            "unknown" if row.estimated_cost_usd is None else f"${row.estimated_cost_usd:.6f}",
        )
    console.print(table)
    for recommendation in response.recommendations:
        console.print(
            f"{recommendation.publisher_id} [{recommendation.route_policy_hash[:12]}]: "
            f"{recommendation.disposition} — "
            f"{recommendation.proposal or ', '.join(recommendation.reasons)}"
        )


@cli_app.command("source-quarantines")
def source_quarantines(
    state_db: str = typer.Option(
        "state/index.sqlite",
        help="Canonical state SQLite database; it does not modify quarantine records.",
    ),
    status: list[str] | None = typer.Option(
        None, "--status", help="Optional status filter; may be supplied multiple times."
    ),
    limit: int = typer.Option(100, min=1, max=500),
) -> None:
    """List bounded source-PDF quarantine evidence for operator review."""

    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_source_quarantines")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    records = list_source_quarantines(
        SourceQuarantineListRequest(
            schema_version="1.0",
            state_db=state_db,
            statuses=list(status or []),
            limit=limit,
        ),
        ctx,
    ).records
    table = Table(title="Source PDF Quarantines", box=box.SIMPLE_HEAVY)
    for heading in ("Source", "Checksum", "Status", "Failure", "Failures", "Latest"):
        table.add_column(heading)
    for record in records:
        table.add_row(
            record.source_file_id,
            record.content_checksum[:16],
            record.status,
            record.failure_code or "-",
            str(record.failed_validation_count),
            record.latest_observed_at_utc,
        )
    console.print(table)


@cli_app.command("revalidate-source-pdf")
def revalidate_source_pdf(
    source_file_id: str = typer.Option(..., help="Drive source-file ID to update."),
    content_checksum: str = typer.Option(
        ..., help="Expected source MD5 or SHA-256 checksum."
    ),
    path: str = typer.Option(..., help="Existing retained PDF path to validate."),
    state_db: str = typer.Option("state/index.sqlite"),
) -> None:
    """Revalidate a retained source PDF and clear or retain its durable quarantine."""

    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_revalidate_source_pdf")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    integrity = check_pdf_integrity(
        PdfIntegrityCheckRequest(schema_version="1.0", path=path), ctx
    )
    checksum = content_checksum.strip().lower()
    if checksum not in {integrity.md5, integrity.sha256}:
        raise typer.BadParameter(
            "content checksum does not match retained PDF bytes", param_hint="--content-checksum"
        )
    existing = get_source_quarantine(
        SourceQuarantineGetRequest(
            schema_version="1.0",
            state_db=state_db,
            source_file_id=source_file_id,
            content_checksum=checksum,
            validator_version=integrity.validator_version,
        ),
        ctx,
    ).record
    failed = bool(integrity.failure_code)
    observed_at = integrity.validated_at_utc
    record = SourceQuarantineRecord(
        schema_version="1.0",
        source_file_id=source_file_id,
        content_checksum=checksum,
        validator_version=integrity.validator_version,
        status="active" if failed else "cleared",
        size_bytes=integrity.size_bytes,
        failure_code=integrity.failure_code,
        next_operator_action="revalidate_after_source_replacement" if failed else "",
        first_observed_at_utc=(
            existing.first_observed_at_utc if existing is not None else observed_at
        ),
        latest_observed_at_utc=observed_at,
        failed_validation_count=1 if failed else 0,
        cleared_at_utc="" if failed else observed_at,
    )
    stored = upsert_source_quarantine(
        SourceQuarantineUpsertRequest(
            schema_version="1.0", state_db=state_db, record=record
        ),
        ctx,
    ).record
    console.print_json(
        data={
            "source_file_id": stored.source_file_id,
            "content_checksum": stored.content_checksum,
            "status": stored.status,
            "failure_code": stored.failure_code,
            "validator_version": stored.validator_version,
        }
    )


@cli_app.command("validate-retained-claims")
def validate_retained_claims_command(
    artifacts_path: str = typer.Option(..., help="Retained artifacts.json path"),
    evidence_packs_path: str = typer.Option(
        "", help="Optional retained evidence-packs JSON path"
    ),
    output_path: str = typer.Option(
        "out/claim_validation_package.json",
        help="Validated claim package; safe to pass to publication readiness",
    ),
) -> None:
    """Validate retained report artifacts without source re-ingestion or model calls."""

    ctx = new_run_context(task_id="cli_validate_retained_claims")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    try:
        artifacts = json.loads(
            read_bytes(
                ReadBytesRequest(schema_version="1.0", path=artifacts_path), ctx
            ).content.decode("utf-8")
        )
        evidence_packs = (
            json.loads(
                read_bytes(
                    ReadBytesRequest(schema_version="1.0", path=evidence_packs_path),
                    ctx,
                ).content.decode("utf-8")
            )
            if evidence_packs_path.strip()
            else {}
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise typer.BadParameter("retained inputs must be JSON objects") from exc
    if not isinstance(artifacts, dict) or not isinstance(evidence_packs, dict):
        raise typer.BadParameter("retained inputs must be JSON objects")
    package = validate_retained_claims(artifacts, evidence_packs)
    write_bytes(
        WriteBytesRequest(
            schema_version="1.0",
            path=output_path,
            content=(
                json.dumps(asdict(package), ensure_ascii=True, indent=2) + "\n"
            ).encode("utf-8"),
            make_parents=True,
        ),
        ctx,
    )
    console.print_json(
        data={
            "readiness_status": package.readiness_status,
            "unsupported_factual_count": package.unsupported_factual_count,
            "unresolved_factual_count": package.unresolved_factual_count,
            "semantic_validation_count": package.semantic_validation_count,
            "output_path": output_path,
        }
    )
