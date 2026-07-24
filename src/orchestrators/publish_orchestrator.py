from __future__ import annotations

# This compatibility facade deliberately re-exports migration seams for callers/tests.
# ruff: noqa: F401
import copy
import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, TypedDict, cast
from urllib.parse import urlparse

from src.contracts.artifact_lineage import (
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    ArtifactLineageStorageLookupRequest,
)
from src.contracts.categories import CategoryMappingLoadRequest
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportPublishPackage,
    CrossReportPublishResultSummary,
    CrossReportPublishStatus,
    PublicationMode,
    validate_cross_report_contract,
)
from src.contracts.files import (
    FileExistsRequest,
    ListHtmlRequest,
    PipelineCheckpointWriteRequest,
    PipelineStageCheckpoint,
    ReadTextRequest,
)
from src.contracts.idempotency import (
    OrchestratorIdempotencyGetRequest,
    OrchestratorIdempotencyRecordRequest,
)
from src.contracts.minimal_execution_plan import (
    MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
    ExecutionCompatibilityVersions,
    ExecutionPlanRecordRequest,
    ExecutionPlanResultRequest,
    MinimalExecutionPlan,
    MinimalExecutionPlanBuildRequest,
    MinimalExecutionPlanInput,
    RetainedArtifactGraph,
)
from src.contracts.publish import (
    PublishEntityMetadata,
    PublishHtmlSnapshot,
    PublishOutcome,
    PublishRequest,
    PublishResolvedTerms,
    PublishSettings,
)
from src.contracts.remediation import (
    RemediationArtifactReference,
    RemediationCheckpointReference,
    RemediationIdempotencyKey,
)
from src.contracts.report_store import (
    ReportMetadataGetResponse,
    ReportMetadataListRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId, ValidationRunId
from src.contracts.state import (
    StateGetRequest,
    StateGetResponse,
    StatePublishRecordRequest,
)
from src.contracts.validation import ValidationReport
from src.contracts.validation_run_manifest import (
    ValidationRunManifestAuditRequest,
    ValidationRunManifestRecordRequest,
    ValidationRunManifestStageRecord,
)
from src.contracts.wordpress import (
    WordPressPostLookupBatchItem,
    WordPressPostLookupBatchRequest,
    WordPressPostLookupRequest,
    WordPressPostLookupResponse,
    WordPressPostReadRequest,
    WordPressTagEnsureRequest,
    WordPressTagEnsureResponse,
    WordPressTaxonomyEnsureRequest,
    WordPressTaxonomyEnsureResponse,
    WordPressTaxonomyTerm,
)
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPublishProjection,
)
from src.generators.publish_generator import publish_html
from src.orchestrators._publish_orchestrator.budget import (
    build_publish_budget,
    read_publish_budget_usage,
)
from src.orchestrators._publish_orchestrator.cross_report import (
    _briefing_url_is_in_section,
    _cross_report_post_type_for_target_route,
    _cross_report_publisher_labels,
    _cross_report_result_fields,
    _cross_report_result_from_outcome,
    _cross_report_settings_for_target_route,
    _cross_report_wordpress_classification,
    _publish_entity_metadata_for_route,
    _resolve_cross_report_terms,
    _signal_projection_package,
    _signal_url_is_in_section,
    _unique_terms_from_labels,
)
from src.orchestrators._publish_orchestrator.idempotency import (
    _cross_report_publish_checksum,
    _cross_report_publish_idempotency_key,
    _lookup_cross_report_publish_idempotency,
    _lookup_publish_idempotency,
    _publish_checksum,
    _publish_idempotency_key,
    _record_cross_report_publish_idempotency,
    _record_publish_idempotency,
)
from src.orchestrators._publish_orchestrator.models import (
    _CROSS_REPORT_PUBLISH_IDEMPOTENCY_SCOPE,
    _CROSS_REPORT_WORDPRESS_POST_TYPES,
    _PUBLISH_ENTITY_ROUTES,
    _PUBLISH_IDEMPOTENCY_SCOPE,
    _PUBLISH_ROUTES_BY_INTENT,
    _CrossReportResultFields,
    _CrossReportWordPressClassification,
    _PublishCandidate,
    _PublishEntityRoute,
    _PublishPreflightEntry,
)
from src.orchestrators._publish_orchestrator.preflight import (
    _batch_lookup_existing_posts,
    _build_publish_preflight_entries,
    _load_validation_report,
    _resolve_batch_term_assignments,
    _validation_paths,
    _with_validation,
)
from src.orchestrators._publish_orchestrator.routing import (
    _metadata_index,
    _normalize_string_list,
    _normalize_tag_slugs,
    _publish_entity_error,
    _publish_settings_for_post_type,
    _require_publish_settings,
    _resolve_publish_candidates,
    _route_publish_entity_metadata,
    _sort_auto_discovered_html_paths,
)
from src.orchestrators.publish_shared import canonicalize_html_path
from src.orchestrators.remediation_orchestrator import (
    record_workflow_failure,
    remediation_budget_summary,
)
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.services import idempotency_service
from src.services.category_mapping_service import (
    load_mappings as load_category_mappings,
)
from src.services.file_service import (
    file_exists,
    list_html,
    read_text,
    write_pipeline_checkpoint,
)
from src.services.report_store_service import (
    audit_validation_run_manifest,
    build_minimal_execution_plan,
    get_artifact_lineage_for_storage,
    list_metadata,
    record_minimal_execution_plan,
    record_minimal_execution_plan_result,
    record_validation_run_manifest_stage,
)
from src.services.state_service import get as state_get
from src.services.state_service import record_publish as state_record_publish
from src.services.wordpress_service import (
    ensure_tags,
    ensure_taxonomy_terms,
    find_post_by_file_id,
    find_posts_by_file_id_batch,
    read_post_by_id,
)
from src.utils.cache_utils import sha256_json
from src.utils.clock import utc_now_seconds_z
from src.utils.errors import AppError
from src.utils.html_utils import (
    build_publish_html_snapshot,
    ensure_publish_entity_metadata_html,
)
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.slugify import slugify
from src.utils.validation import parse_validation_report_payload
from src.utils.wp_auth import build_auth_header

logger = logging.getLogger("market_lense.publish_orchestrator")


def _publication_recovery_evidence(
    *,
    settings: PublishSettings,
    file_id: str,
    html_path: str,
    publish_checksum: str,
    idempotency_key: str,
    post_type: str,
    ctx: RunContext,
) -> tuple[
    RemediationCheckpointReference | None,
    list[RemediationArtifactReference],
]:
    """Persist the pre-write proof required for GET-only readback recovery.

    Publication recovery must never infer a post or reconstruct a report.  The
    preflight therefore retains only the verified rendered package lineage and
    the immutable publication idempotency identity.  Missing active lineage is
    intentionally not repaired here; a resulting readback failure remains an
    operator-held remediation record.
    """

    lineage = get_artifact_lineage_for_storage(
        ArtifactLineageStorageLookupRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=settings.reports_db,
            report_id=file_id,
            artifact_kind="rendered_html",
            storage_ref=html_path,
        ),
        ctx,
    ).record
    if (
        lineage is None
        or lineage.state != "active"
        or lineage.lineage_status != "complete"
        or not lineage.artifact_id
    ):
        return None, []
    checkpoint = PipelineStageCheckpoint(
        schema_version="1.0",
        pipeline_name="publishing",
        file_id=file_id,
        report_slug=slugify(Path(html_path).stem) or file_id,
        stage_name="publication_preflight",
        stage_status="completed",
        artifact_refs={
            "rendered_html": html_path,
            "publish_readiness": idempotency_key,
        },
        payload={
            "schema_version": "1.0",
            "artifact_lineage": {"rendered_html": lineage.artifact_id},
            "publication": {
                "idempotency_key": idempotency_key,
                "post_type": post_type,
                "publish_checksum": publish_checksum,
            },
        },
        completed_at_utc=utc_now_seconds_z(),
        source_run_id=str(ctx.run_id),
        source_task_id=str(ctx.task_id),
    )
    checkpoint_write = write_pipeline_checkpoint(
        PipelineCheckpointWriteRequest(
            schema_version="1.0",
            checkpoint_root=settings.output_dir,
            checkpoint=checkpoint,
        ),
        ctx,
    )
    return (
        RemediationCheckpointReference(
            schema_version="1.0",
            path=checkpoint_write.checkpoint_path,
            stage_name=checkpoint.stage_name,
            checksum_sha256=sha256_json(asdict(checkpoint)),
            lineage_ref=lineage.artifact_id,
        ),
        [
            RemediationArtifactReference(
                schema_version="1.0",
                name="rendered_html",
                reference=html_path,
                checksum_sha256=lineage.content_hash,
                lineage_ref=lineage.artifact_id,
            ),
            RemediationArtifactReference(
                schema_version="1.0",
                name="publish_readiness",
                reference=idempotency_key,
                lineage_ref=lineage.artifact_id,
            ),
        ],
    )


def _load_validation_cohort_for_publish(
    cohort_manifest: str, ctx: RunContext
) -> tuple[ValidationRunId, str, str, str, dict[str, dict[str, object]]]:
    """Load immutable cohort provenance needed to close WordPress outcomes."""
    try:
        payload = json.loads(
            read_text(
                ReadTextRequest(schema_version="1.0", path=cohort_manifest), ctx
            ).content
        )
        members = payload["members"]
        cohort_id = str(payload["cohort_id"])
        configuration_hash = str(payload["configuration_hash"])
        policy_hash = str(payload["policy_hash"])
        validation_run_id = str(payload.get("validation_run_id") or "")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            code="validation_cohort_manifest_invalid",
            message="WordPress validation closure requires a valid cohort manifest",
            cause=exc,
            retryable=False,
        ) from exc
    if (
        not cohort_id
        or not configuration_hash
        or not policy_hash
        or not isinstance(members, list)
    ):
        raise AppError(
            code="validation_cohort_manifest_invalid",
            message="WordPress validation closure requires complete cohort provenance",
            retryable=False,
        )
    by_file_id = {
        str(member.get("file_id") or ""): member
        for member in members
        if isinstance(member, dict) and str(member.get("file_id") or "")
    }
    if len(by_file_id) != len(members):
        raise AppError(
            code="validation_cohort_manifest_invalid",
            message="WordPress validation closure requires unique cohort file IDs",
            retryable=False,
        )
    return (
        ValidationRunId(validation_run_id or f"validation:{cohort_id}"),
        cohort_id,
        configuration_hash,
        policy_hash,
        by_file_id,
    )


def _record_validation_cohort_publish_outcomes(
    *,
    cohort_manifest: str,
    reports_db: str,
    outcomes: list[PublishOutcome],
    ctx: RunContext,
    require_full_workflow: bool = False,
) -> None:
    """Close each immutable cohort member with one typed WordPress outcome."""
    (
        validation_run_id,
        cohort_id,
        configuration_hash,
        policy_hash,
        members,
    ) = _load_validation_cohort_for_publish(cohort_manifest, ctx)
    outcomes_by_file_id = {
        str(outcome.file_id): outcome for outcome in outcomes if outcome.file_id
    }
    timestamp = datetime.now(timezone.utc).isoformat()
    for file_id, member in members.items():
        outcome = outcomes_by_file_id.get(file_id)
        source_identity_id = str(member.get("md5_checksum") or file_id)

        def record_stage(
            stage: str,
            *,
            terminal_outcome: str = "succeeded",
            failure_code: str = "",
            idempotency_state: str = "new",
            entity_terminal: bool = False,
            output_artifact_ids: tuple[str, ...] = (),
        ) -> None:
            record_validation_run_manifest_stage(
                ValidationRunManifestRecordRequest(
                    schema_version="1.0",
                    db_path=reports_db,
                    record=ValidationRunManifestStageRecord(
                        schema_version="1.0",
                        validation_run_id=validation_run_id,
                        cohort_id=cohort_id,
                        workflow_run_id=RunId(ctx.run_id),
                        entity_type="report",
                        publisher_id="unattributed",
                        report_id=file_id,
                        source_identity_id=source_identity_id,
                        stage=stage,
                        attempt_number=1,
                        parent_attempt_number=0,
                        input_artifact_ids=(file_id,),
                        output_artifact_ids=output_artifact_ids,
                        started_at_utc=timestamp,
                        completed_at_utc=timestamp,
                        terminal_outcome=terminal_outcome,
                        failure_code=failure_code,
                        retryable=False,
                        repair_disposition="not_required",
                        duplicate_disposition=(
                            "reused" if idempotency_state == "reused" else "none"
                        ),
                        supersession_state="current",
                        idempotency_state=idempotency_state,
                        configuration_hash=configuration_hash,
                        policy_hash=policy_hash,
                        producer_build_identity=ctx.producer_commit_sha or "workspace",
                        cohort_disposition="final_validation",
                        entity_terminal=entity_terminal,
                    ),
                ),
                ctx,
            )

        if outcome is None:
            record_stage(
                "publication_preflight",
                terminal_outcome="blocked",
                failure_code="wordpress_publish_not_attempted",
            )
            record_stage(
                "wordpress_lookup",
                terminal_outcome="blocked",
                failure_code="wordpress_publish_not_attempted",
            )
            record_stage(
                "wordpress_write",
                terminal_outcome="blocked",
                failure_code="wordpress_publish_not_attempted",
            )
            record_stage(
                "authenticated_readback",
                terminal_outcome="blocked",
                failure_code="wordpress_publish_not_attempted",
                entity_terminal=True,
            )
            record_stage(
                "repeat_publication",
                terminal_outcome="blocked",
                failure_code="wordpress_publish_not_attempted",
            )
            continue

        output_artifact_ids = tuple(
            value
            for value in (str(outcome.post_id or ""), str(outcome.post_url or ""))
            if value
        )
        preflight_outcome = "succeeded" if outcome.status != "error" else "blocked"
        failure_code = (
            ""
            if preflight_outcome == "succeeded"
            else str(outcome.error or "publication_preflight_failed")
        )
        record_stage(
            "publication_preflight",
            terminal_outcome=preflight_outcome,
            failure_code=failure_code,
            output_artifact_ids=output_artifact_ids,
        )
        verified = bool(outcome.authenticated_readback_verified)
        if outcome.publication_outcome == "existing_post_matched":
            record_stage(
                "wordpress_lookup",
                terminal_outcome="succeeded" if verified else "failed",
                failure_code=""
                if verified
                else str(outcome.error or "readback_failed"),
                idempotency_state="verified" if verified else "new",
                output_artifact_ids=output_artifact_ids,
            )
            record_stage(
                "wordpress_write",
                terminal_outcome="skipped",
                idempotency_state="reused" if verified else "new",
                output_artifact_ids=output_artifact_ids,
            )
            record_stage(
                "repeat_publication",
                terminal_outcome="succeeded" if verified else "failed",
                failure_code=""
                if verified
                else str(outcome.error or "readback_failed"),
                idempotency_state="reused" if verified else "new",
                output_artifact_ids=output_artifact_ids,
            )
        elif outcome.status == "published":
            record_stage(
                "wordpress_lookup",
                terminal_outcome="succeeded",
                output_artifact_ids=output_artifact_ids,
            )
            record_stage(
                "wordpress_write",
                terminal_outcome="succeeded",
                idempotency_state="new",
                output_artifact_ids=output_artifact_ids,
            )
        else:
            record_stage(
                "wordpress_lookup",
                terminal_outcome="failed",
                failure_code=str(outcome.error or "wordpress_transaction_failed"),
                output_artifact_ids=output_artifact_ids,
            )
            record_stage(
                "wordpress_write",
                terminal_outcome="blocked",
                failure_code=str(outcome.error or "wordpress_transaction_failed"),
                output_artifact_ids=output_artifact_ids,
            )
            record_stage(
                "repeat_publication",
                terminal_outcome="blocked",
                failure_code=str(outcome.error or "wordpress_transaction_failed"),
                output_artifact_ids=output_artifact_ids,
            )
        record_stage(
            "authenticated_readback",
            terminal_outcome="published_verified" if verified else "blocked",
            failure_code="" if verified else str(outcome.error or "readback_failed"),
            idempotency_state="verified" if verified else "new",
            entity_terminal=True,
            output_artifact_ids=output_artifact_ids,
        )
    audit = audit_validation_run_manifest(
        ValidationRunManifestAuditRequest(
            schema_version="1.0",
            db_path=reports_db,
            validation_run_id=validation_run_id,
            require_full_workflow=require_full_workflow,
        ),
        ctx,
    )
    if not audit.complete:
        raise AppError(
            code="validation_manifest_closure_incomplete",
            message="WordPress publication did not close every cohort member",
            retryable=False,
            context={
                "validation_run_id": str(validation_run_id),
                "incomplete_entity_count": len(audit.incomplete_entity_ids),
                "duplicate_current_entity_count": len(
                    audit.duplicate_current_entity_ids
                ),
                "missing_cohort_report_count": len(audit.missing_cohort_report_ids),
                "overlapping_current_report_count": len(
                    audit.overlapping_current_report_ids
                ),
                "duplicate_source_identity_count": len(
                    audit.duplicate_source_identity_ids
                ),
                "multiple_wordpress_post_report_count": len(
                    audit.multiple_wordpress_post_report_ids
                ),
                "totals_reconciled": audit.totals_reconciled,
                "missing_required_stage_count": len(
                    audit.missing_required_stage_entity_ids
                ),
            },
        )


def publish_cross_report_package(
    package: CrossReportPublishPackage,
    settings: PublishSettings | None,
    ctx: RunContext,
    *,
    dry_run: bool = False,
    publish_html_fn: Callable[
        [PublishRequest, PublishSettings, RunContext], PublishOutcome
    ] = publish_html,
    find_post_by_file_id_fn: Callable[
        [WordPressPostLookupRequest, RunContext], WordPressPostLookupResponse
    ] = find_post_by_file_id,
    ensure_taxonomy_terms_fn: Callable[
        [WordPressTaxonomyEnsureRequest, RunContext], WordPressTaxonomyEnsureResponse
    ] = ensure_taxonomy_terms,
    ensure_tags_fn: Callable[
        [WordPressTagEnsureRequest, RunContext], WordPressTagEnsureResponse
    ] = ensure_tags,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> CrossReportPublishResultSummary:
    validate_cross_report_contract(package)
    publication_mode = "publish_dry_run" if dry_run else "publish_live"
    route_post_type = _cross_report_post_type_for_target_route(package.target_route)
    classification = _cross_report_wordpress_classification(package, route_post_type)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cross_report_publish_start",
            module=logger.name,
            fields={
                "package_id": package.package_id,
                "publication_mode": publication_mode,
                "target_route": package.target_route,
                "target_post_type": classification.post_type,
                "target_slug": classification.slug,
                "selected_theme_id": package.selected_theme_id,
                "selected_report_ids": package.selected_report_ids,
                "validation_sha256": package.validation_sha256,
            },
        )
    )
    if dry_run:
        result = CrossReportPublishResultSummary(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            publication_mode="publish_dry_run",
            status="dry_run",
            target_route=package.target_route,
            idempotency_reused=False,
            **_cross_report_result_fields(classification),
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="cross_report_publish_complete",
                module=logger.name,
                fields={
                    "package_id": package.package_id,
                    "status": result.status,
                    "dry_run": True,
                },
            )
        )
        return result

    route_settings = _cross_report_settings_for_target_route(
        _require_publish_settings(settings), package.target_route
    )
    checksum = _cross_report_publish_checksum(package, route_settings)
    reused = _lookup_cross_report_publish_idempotency(
        package=package,
        settings=route_settings,
        checksum=checksum,
        ctx=ctx,
    )
    if reused is not None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="cross_report_publish_idempotency_reused",
                module=logger.name,
                fields={
                    "package_id": package.package_id,
                    "target_route": package.target_route,
                    "status": reused.status,
                    "post_id": reused.post_id or 0,
                },
            )
        )
        return reused

    base_url = route_settings.wp.site_url.rstrip("/")
    auth_header = build_auth_header(
        username=route_settings.wp.username,
        app_password=route_settings.wp.app_password,
        bearer_token=route_settings.wp.bearer_token,
    )

    def _publish_attempt() -> CrossReportPublishResultSummary:
        lookup = find_post_by_file_id_fn(
            WordPressPostLookupRequest(
                schema_version="1.0",
                base_url=base_url,
                auth_header=auth_header,
                file_id=package.file_id,
                ssl_verify=route_settings.wp.ssl_verify,
                ca_bundle_path=route_settings.wp.ca_bundle_path,
                post_type=route_settings.wp.post_type,
            ),
            ctx,
        )
        if lookup.found and lookup.post_id and lookup.link:
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="cross_report_publish_existing_post_checksum_mismatch",
                    module=logger.name,
                    fields={
                        "package_id": package.package_id,
                        "file_id": package.file_id,
                        "post_id": lookup.post_id,
                        "post_url": lookup.link,
                        "checksum": checksum,
                    },
                )
            )
            raise AppError(
                code="cross_report_publish_existing_post_checksum_mismatch",
                message=(
                    "WordPress already contains this cross-report file_id, but no "
                    "matching publish checksum was recorded for the current package."
                ),
                retryable=False,
                severity="error",
                context={
                    "package_id": package.package_id,
                    "file_id": package.file_id,
                    "post_id": lookup.post_id,
                    "post_url": lookup.link,
                    "checksum": checksum,
                },
            )
        resolved_terms = _resolve_cross_report_terms(
            classification=classification,
            settings=route_settings,
            base_url=base_url,
            auth_header=auth_header,
            ctx=ctx,
            ensure_taxonomy_terms_fn=ensure_taxonomy_terms_fn,
            ensure_tags_fn=ensure_tags_fn,
        )
        outcome = publish_html_fn(
            PublishRequest(
                schema_version="1.0",
                html_path=package.html_path,
                auth_header=auth_header,
                file_id=package.file_id,
                slug=classification.slug,
                html_snapshot=PublishHtmlSnapshot(
                    schema_version="1.0",
                    html_text=package.html_text,
                    file_id=package.file_id,
                    title=package.title,
                    body_html=package.body_html,
                    image_sources=[],
                    preview_image_src=None,
                    entity_metadata=_publish_entity_metadata_for_route(
                        source_artifact_id=package.file_id,
                        canonical_route_intent=package.target_route,
                    ),
                    briefing_card=package.briefing_card,
                    signal_card=package.signal_card,
                ),
                resolved_terms=resolved_terms,
            ),
            route_settings,
            ctx,
        )
        if (
            package.target_route == "wordpress:ml_briefing"
            and outcome.status == "published"
            and outcome.post_url
            and not _briefing_url_is_in_section(outcome.post_url)
        ):
            raise AppError(
                code="cross_report_briefing_url_mismatch",
                message="Published cross-report Briefing URL is outside /briefings/.",
                retryable=False,
                severity="error",
                context={
                    "package_id": package.package_id,
                    "post_id": outcome.post_id,
                    "post_url": outcome.post_url,
                    "target_route": package.target_route,
                    "target_post_type": classification.post_type,
                },
            )
        if (
            package.target_route == "wordpress:ml_signal"
            and outcome.status == "published"
            and outcome.post_url
            and not _signal_url_is_in_section(outcome.post_url)
        ):
            raise AppError(
                code="signal_publish_url_mismatch",
                message="Published Signal URL is outside /signals/.",
                retryable=False,
                severity="error",
                context={
                    "package_id": package.package_id,
                    "post_id": outcome.post_id,
                    "post_url": outcome.post_url,
                    "target_route": package.target_route,
                    "target_post_type": classification.post_type,
                },
            )
        return _cross_report_result_from_outcome(
            package=package,
            publication_mode="publish_live",
            outcome=outcome,
            idempotency_reused=False,
            classification=classification,
        )

    try:
        result = run_with_retry(
            step_name="publish_cross_report_package",
            operation=_publish_attempt,
            ctx=ctx,
            logger=logger,
            module_name=logger.name,
            policy=RetryPolicy(
                retries=2,
                base_delay_seconds=1.0,
                backoff_step_seconds=1.0,
                jitter_seconds=0.25,
            ),
            retry_event="cross_report_publish_retry",
            retry_fields_builder=lambda exc, attempt: {
                "package_id": package.package_id,
                "attempt": attempt + 1,
                "code": exc.code if isinstance(exc, AppError) else "",
            },
            on_terminal_failure=lambda exc, decision: record_workflow_failure(
                state_db=route_settings.state_db,
                workflow="publishing",
                stage="publish_cross_report_package",
                operation="publish_html",
                error=exc,
                ctx=ctx,
                retry_decision=decision,
                input_checksum=checksum,
                report_id=package.file_id,
                idempotency_keys=[
                    RemediationIdempotencyKey(
                        schema_version="1.0",
                        scope=_CROSS_REPORT_PUBLISH_IDEMPOTENCY_SCOPE,
                        key=_cross_report_publish_idempotency_key(package, checksum),
                        input_checksum=checksum,
                    )
                ],
            ),
            is_retryable=lambda exc: isinstance(exc, AppError) and exc.retryable,
            sleep_fn=sleep_fn,
        )
    except AppError as exc:
        result = CrossReportPublishResultSummary(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            publication_mode="publish_live",
            status="error",
            target_route=package.target_route,
            idempotency_reused=False,
            **_cross_report_result_fields(classification),
            error_code=exc.code,
            error_message=exc.message,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="cross_report_publish_error",
                module=logger.name,
                fields={
                    "package_id": package.package_id,
                    "code": exc.code,
                    "retryable": exc.retryable,
                    "error": exc.message,
                },
            )
        )
        return result

    if result.status in {"published", "skipped"}:
        _record_cross_report_publish_idempotency(
            package=package,
            settings=route_settings,
            result=result,
            checksum=checksum,
            ctx=ctx,
        )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cross_report_publish_complete",
            module=logger.name,
            fields={
                "package_id": package.package_id,
                "status": result.status,
                "post_id": result.post_id or 0,
                "post_url": result.post_url or "",
            },
        )
    )
    return result


def publish_signal_projection(
    projection: SignalPublishProjection,
    signal_card: dict[str, object],
    settings: PublishSettings,
    ctx: RunContext,
    *,
    dry_run: bool = False,
    publish_html_fn: Callable[
        [PublishRequest, PublishSettings, RunContext], PublishOutcome
    ] = publish_html,
    find_post_by_file_id_fn: Callable[
        [WordPressPostLookupRequest, RunContext], WordPressPostLookupResponse
    ] = find_post_by_file_id,
    ensure_taxonomy_terms_fn: Callable[
        [WordPressTaxonomyEnsureRequest, RunContext], WordPressTaxonomyEnsureResponse
    ] = ensure_taxonomy_terms,
    ensure_tags_fn: Callable[
        [WordPressTagEnsureRequest, RunContext], WordPressTagEnsureResponse
    ] = ensure_tags,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> CrossReportPublishResultSummary:
    if projection.validation_status != "approved":
        raise AppError(
            code="signal_publish_validation_status_invalid",
            message="Only approved Signal projections can be published.",
            retryable=False,
            severity="error",
            context={
                "slug": projection.slug,
                "validation_status": projection.validation_status,
            },
        )
    return publish_cross_report_package(
        _signal_projection_package(projection, signal_card),
        settings,
        ctx,
        dry_run=dry_run,
        publish_html_fn=publish_html_fn,
        find_post_by_file_id_fn=find_post_by_file_id_fn,
        ensure_taxonomy_terms_fn=ensure_taxonomy_terms_fn,
        ensure_tags_fn=ensure_tags_fn,
        sleep_fn=sleep_fn,
    )


def run_publish(
    settings: PublishSettings,
    *,
    limit: Optional[int] = None,
    html_paths: Optional[List[str]] = None,
    ctx: Optional[RunContext] = None,
    force_report_cards: bool = False,
    force_draft: bool = False,
    execution_plan_mode: str = "shadow",
    cohort_manifest: str | None = None,
    require_full_validation_manifest: bool = False,
) -> List[PublishOutcome]:
    root_ctx = ctx or new_run_context()
    cohort_member_file_ids: set[str] | None = None
    if cohort_manifest:
        (
            _validation_run_id,
            _cohort_id,
            _configuration_hash,
            _policy_hash,
            cohort_members,
        ) = _load_validation_cohort_for_publish(cohort_manifest, root_ctx)
        cohort_member_file_ids = set(cohort_members)
    publish_budget = build_publish_budget(settings, root_ctx)
    requested_post_status = str(settings.wp.post_status or "publish").strip().lower()
    effective_post_status = "draft" if force_draft else requested_post_status
    if requested_post_status != effective_post_status:
        settings = replace(
            settings,
            wp=replace(settings.wp, post_status=effective_post_status),
        )
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="publish_post_status_resolved",
                module=logger.name,
                fields={
                    "requested_post_status": requested_post_status,
                    "effective_post_status": effective_post_status,
                    "reason": "explicit_draft_requested",
                },
            )
        )
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="publish_start",
            module=logger.name,
            fields={
                "limit": limit,
                "explicit_html_paths": len(html_paths) if html_paths is not None else 0,
                "force_report_cards": force_report_cards,
                "force_draft": force_draft,
                "cohort_manifest": cohort_manifest or "",
                "post_status": settings.wp.post_status,
            },
        )
    )

    auto_discovery = html_paths is None
    normalized_plan_mode = str(execution_plan_mode or "shadow").strip().lower()
    if normalized_plan_mode not in {"shadow", "enforce", "disabled"}:
        raise AppError(
            code="minimal_execution_plan_mode_invalid",
            message="Execution planning mode must be shadow, enforce, or disabled",
            retryable=False,
        )
    if auto_discovery:
        list_resp = list_html(
            ListHtmlRequest(schema_version="1.0", root_dir=settings.output_dir),
            root_ctx,
        )
        discovered_html_paths = list_resp.html_paths
    else:
        discovered_html_paths = [str(path) for path in html_paths]  # type: ignore[union-attr]
    outcomes: List[PublishOutcome] = []
    attempted = 0
    published = 0
    base_url = settings.wp.site_url.rstrip("/")
    auth_header = build_auth_header(
        username=settings.wp.username,
        app_password=settings.wp.app_password,
        bearer_token=settings.wp.bearer_token,
    )
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="publish_auth_source",
            module=logger.name,
            fields={
                "source": "bearer_token" if settings.wp.bearer_token else "app_password"
            },
        )
    )
    html_file_id_map: dict[str, str] = {}
    metadata_by_file_id: dict[str, ReportMetadataGetResponse] = {}
    mapping_ctx = child_context(root_ctx, task_id="publish_preflight_metadata")
    try:
        html_file_id_map, metadata_by_file_id = _metadata_index(settings, mapping_ctx)
    except Exception as exc:
        logger.info(
            log_event(
                mapping_ctx,
                role="orchestrator",
                event="publish_preflight_metadata_failed",
                module=logger.name,
                fields={"reports_db": settings.reports_db, "error": str(exc)},
            )
        )
        html_file_id_map = {}
        metadata_by_file_id = {}

    if auto_discovery:
        selected_html_paths = _sort_auto_discovered_html_paths(
            discovered_html_paths,
            html_file_id_map=html_file_id_map,
            metadata_by_file_id=metadata_by_file_id,
        )
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="publish_auto_discovery_ordered",
                module=logger.name,
                fields={
                    "count": len(selected_html_paths),
                    "metadata_matched": sum(
                        1
                        for html_path in selected_html_paths
                        if html_file_id_map.get(canonicalize_html_path(html_path), "")
                        in metadata_by_file_id
                    ),
                },
            )
        )
    else:
        max_n = limit if limit is not None else len(discovered_html_paths)
        selected_html_paths = discovered_html_paths[:max_n]

    candidates = _resolve_publish_candidates(
        html_paths=selected_html_paths,
        html_file_id_map=html_file_id_map,
        ctx=root_ctx,
        skip_unowned_nonpublish_html=auto_discovery,
    )
    if cohort_member_file_ids is not None:
        candidates_before_cohort_filter = len(candidates)
        candidates = [
            candidate
            for candidate in candidates
            if str(candidate.file_id or "") in cohort_member_file_ids
        ]
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="publish_cohort_selection_applied",
                module=logger.name,
                fields={
                    "cohort_member_count": len(cohort_member_file_ids),
                    "candidates_before_filter": candidates_before_cohort_filter,
                    "selected_candidates": len(candidates),
                    "excluded_candidates": (
                        candidates_before_cohort_filter - len(candidates)
                    ),
                },
            )
        )
    if force_report_cards:
        candidates = [
            candidate
            for candidate in candidates
            if (
                file_exists(
                    FileExistsRequest(
                        schema_version="1.0",
                        path=str(
                            Path(candidate.html_path).with_suffix("")
                            / "report-card-manifest.json"
                        ),
                    ),
                    root_ctx,
                ).exists
                or bool(
                    candidate.html_snapshot and candidate.html_snapshot.briefing_card
                )
            )
        ]
    if auto_discovery and limit is not None:
        candidates = candidates[:limit]
    publication_plans: dict[str, MinimalExecutionPlan] = {}
    publication_plan_started_at: dict[str, float] = {}
    blocked_paths: set[str] = set()
    if normalized_plan_mode != "disabled":
        publication_target = f"{base_url}|{settings.wp.post_status}"
        for candidate in candidates:
            file_id = str(candidate.file_id or "").strip()
            if not file_id:
                continue
            plan = build_minimal_execution_plan(
                MinimalExecutionPlanBuildRequest(
                    schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                    db_path=settings.reports_db,
                    execution_input=MinimalExecutionPlanInput(
                        schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                        execution_intent="publication_repair",
                        report_id=file_id,
                        source_id="",
                        current_source_content_hashes={},
                        retained_graph=RetainedArtifactGraph(),
                        requested_output_families=["rendered_html"],
                        current_compatibility=ExecutionCompatibilityVersions(),
                        current_publication_state={"target": publication_target},
                    ),
                ),
                root_ctx,
            ).plan
            publication_plans[candidate.html_path] = plan
            publication_plan_started_at[candidate.html_path] = time.perf_counter()
            record_minimal_execution_plan(
                ExecutionPlanRecordRequest(
                    schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                    db_path=settings.reports_db,
                    plan=plan,
                    execution_mode=normalized_plan_mode,
                ),
                root_ctx,
            )
            if normalized_plan_mode == "enforce" and (
                plan.missing_lineage_blockers or plan.publication_prerequisites
            ):
                blocked_paths.add(candidate.html_path)
                outcomes.append(
                    PublishOutcome(
                        schema_version="1.0",
                        html_path=candidate.html_path,
                        file_id=file_id,
                        status="error",
                        error="publication_lineage_prerequisite_missing",
                    )
                )
        candidates = [
            candidate
            for candidate in candidates
            if candidate.html_path not in blocked_paths
        ]
    idempotent_term_skip_file_ids: set[str] = set()
    if not force_report_cards:
        for candidate in candidates:
            file_id = str(candidate.file_id or "").strip()
            entity_route = candidate.entity_route
            if (
                not file_id
                or entity_route is None
                or candidate.entity_error is not None
            ):
                continue
            file_ctx = child_context(root_ctx, task_id=candidate.html_path)
            state_row = state_get(
                StateGetRequest(
                    schema_version="1.0",
                    state_db=settings.state_db,
                    file_id=file_id,
                ),
                file_ctx,
            )
            if state_row is None or candidate.html_snapshot is None:
                continue
            validation_report = _load_validation_report(
                file_id=file_id,
                html_path=candidate.html_path,
                settings=settings,
                ctx=file_ctx,
            )
            validation_status = (
                validation_report.status if validation_report else "missing"
            )
            validation_issues = (
                [issue.message for issue in validation_report.issues]
                if validation_report
                else []
            )
            checksum = _publish_checksum(
                file_id=file_id,
                html_path=candidate.html_path,
                html_text=candidate.html_snapshot.html_text,
                post_type=entity_route.post_type,
                validation_status=validation_status,
                validation_issues=validation_issues,
            )
            if (
                _lookup_publish_idempotency(
                    settings=settings,
                    file_id=file_id,
                    post_type=entity_route.post_type,
                    checksum=checksum,
                    ctx=file_ctx,
                )
                is not None
            ):
                idempotent_term_skip_file_ids.add(file_id)

    preflight_entries = _build_publish_preflight_entries(
        settings=settings,
        candidates=candidates,
        metadata_by_file_id=metadata_by_file_id,
        base_url=base_url,
        auth_header=auth_header,
        ctx=root_ctx,
        skip_term_resolution_file_ids=idempotent_term_skip_file_ids,
    )

    for entry in preflight_entries:
        attempted += 1
        html_path = entry.candidate.html_path

        file_ctx = child_context(root_ctx, task_id=html_path)
        html_snapshot = entry.candidate.html_snapshot
        file_id = str(entry.candidate.file_id or "")
        entity_route = entry.candidate.entity_route
        state_row = entry.state_row
        validation_status = entry.validation_status
        validation_issues = list(entry.validation_issues)
        existing_post_lookup = entry.existing_post_lookup
        resolved_terms = entry.resolved_terms

        if entry.candidate.entity_error is not None:
            entity_error = entry.candidate.entity_error
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id or None,
                    status="error",
                    error=entity_error.code,
                )
            )
            continue
        if entity_route is None:
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id or None,
                    status="error",
                    error="publish_entity_metadata_missing",
                )
            )
            continue

        if existing_post_lookup and existing_post_lookup.error_code:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_preflight_lookup_blocked",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "code": existing_post_lookup.error_code,
                        "retryable": existing_post_lookup.retryable,
                    },
                )
            )
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id or None,
                    status="error",
                    error=existing_post_lookup.error_code,
                    publication_outcome="lookup_failed",
                    lookup_count=1,
                )
            )
            continue

        if not file_id:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_missing_file_id",
                    module=logger.name,
                    fields={"html_path": html_path},
                )
            )
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=None,
                    status="error",
                    error="missing_file_id",
                )
            )
            continue
        if not state_row:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_not_processed",
                    module=logger.name,
                    fields={"file_id": file_id},
                )
            )
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="error",
                    error="not_processed",
                )
            )
            continue
        if html_snapshot is None:
            html_text = read_text(
                ReadTextRequest(schema_version="1.0", path=html_path), file_ctx
            ).content
            html_snapshot = build_publish_html_snapshot(html_text)
        publish_checksum = _publish_checksum(
            file_id=file_id,
            html_path=html_path,
            html_text=html_snapshot.html_text,
            post_type=entity_route.post_type,
            validation_status=validation_status,
            validation_issues=validation_issues,
        )
        publish_idempotency_key = _publish_idempotency_key(
            file_id=file_id,
            post_type=entity_route.post_type,
        )
        recovery_checkpoint, recovery_artifacts = _publication_recovery_evidence(
            settings=settings,
            file_id=file_id,
            html_path=html_path,
            publish_checksum=publish_checksum,
            idempotency_key=publish_idempotency_key,
            post_type=entity_route.post_type,
            ctx=file_ctx,
        )

        def _record_publish_failure(
            exc: Exception,
            decision=None,
            *,
            _file_ctx: RunContext = file_ctx,
            _workflow_run_id: str = str(root_ctx.run_id),
            _input_checksum: str = publish_checksum,
            _report_id: str = file_id,
            _source_id: str = state_row.md5,
            _checkpoint: RemediationCheckpointReference | None = recovery_checkpoint,
            _artifacts: list[RemediationArtifactReference] = recovery_artifacts,
            _idempotency_key: str = publish_idempotency_key,
            _configuration_hash: str = str(file_ctx.configuration_hash or ""),
            _policy_hash: str = str(file_ctx.policy_hash or ""),
        ) -> None:
            record_workflow_failure(
                state_db=settings.state_db,
                workflow="publishing",
                stage="publish_html",
                operation="publish_html",
                error=exc,
                ctx=_file_ctx,
                retry_decision=decision,
                workflow_run_id=_workflow_run_id,
                input_checksum=_input_checksum,
                report_id=_report_id,
                source_id=_source_id,
                checkpoint=_checkpoint,
                reusable_artifacts=_artifacts,
                idempotency_keys=[
                    RemediationIdempotencyKey(
                        schema_version="1.0",
                        scope=_PUBLISH_IDEMPOTENCY_SCOPE,
                        key=_idempotency_key,
                        input_checksum=_input_checksum,
                    )
                ],
                budget=remediation_budget_summary(publish_budget),
                recovery_identity={
                    "configuration_hash": _configuration_hash,
                    "policy_hash": _policy_hash,
                },
            )

        reused_outcome = (
            None
            if force_report_cards
            else _lookup_publish_idempotency(
                settings=settings,
                file_id=file_id,
                post_type=entity_route.post_type,
                checksum=publish_checksum,
                ctx=file_ctx,
            )
        )
        if reused_outcome is not None:
            idempotency_readback: WordPressPostLookupResponse | None = (
                WordPressPostLookupResponse(
                    schema_version="1.0",
                    found=existing_post_lookup.found,
                    post_id=existing_post_lookup.post_id,
                    link=existing_post_lookup.link,
                )
                if existing_post_lookup is not None
                else None
            )
            if (
                idempotency_readback is not None
                and not idempotency_readback.found
                and reused_outcome.post_id
            ):
                idempotency_readback = read_post_by_id(
                    WordPressPostReadRequest(
                        schema_version="1.0",
                        base_url=base_url,
                        auth_header=auth_header,
                        post_id=reused_outcome.post_id or 0,
                        file_id=file_id,
                        ssl_verify=settings.wp.ssl_verify,
                        ca_bundle_path=settings.wp.ca_bundle_path,
                        post_type=entity_route.post_type,
                    ),
                    file_ctx,
                )
            if (
                idempotency_readback is None
                or not idempotency_readback.found
                or not idempotency_readback.post_id
                or not idempotency_readback.link
            ):
                _record_publish_failure(
                    AppError(
                        code="wordpress_idempotency_readback_missing",
                        message=(
                            "Idempotent publication could not be reconciled through "
                            "authenticated WordPress readback"
                        ),
                        retryable=False,
                    )
                )
                outcomes.append(
                    PublishOutcome(
                        schema_version="1.0",
                        html_path=html_path,
                        file_id=file_id,
                        status="error",
                        error="wordpress_idempotency_readback_missing",
                        validation_status=validation_status,
                        validation_issues=validation_issues,
                        publication_outcome="readback_failed",
                        requested_write_count=0,
                        actual_write_count=0,
                        lookup_count=1,
                    )
                )
                continue
            verified_outcome = replace(
                reused_outcome,
                status="skipped",
                post_id=idempotency_readback.post_id,
                post_url=idempotency_readback.link,
                error="already_exists",
                publication_outcome="existing_post_matched",
                requested_write_count=0,
                actual_write_count=0,
                lookup_count=1,
                authenticated_readback_verified=True,
                validation_status=validation_status,
                validation_issues=validation_issues,
            )
            state_record_publish(
                StatePublishRecordRequest(
                    schema_version="1.0",
                        state_db=settings.state_db,
                        file_id=file_id,
                        md5=state_row.md5,
                        wp_post_id=idempotency_readback.post_id,
                        wp_post_url=idempotency_readback.link,
                    post_type=entity_route.post_type,
                ),
                file_ctx,
            )
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_idempotency_reused",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "post_type": entity_route.post_type,
                        "status": verified_outcome.status,
                        "post_id": verified_outcome.post_id,
                    },
                )
            )
            outcomes.append(verified_outcome)
            if verified_outcome.status == "published":
                published += 1
            continue
        if settings.validation_policy == "block" and validation_status != "pass":
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_validation_blocked",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "validation_status": validation_status,
                        "issues": validation_issues,
                    },
                )
            )
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="error",
                    error="validation_failed",
                    validation_status=validation_status,
                    validation_issues=validation_issues,
                    publication_outcome="preflight_blocked",
                )
            )
            continue
        if validation_status != "pass":
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_validation_warning",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "validation_status": validation_status,
                        "issues": validation_issues,
                        "policy": settings.validation_policy,
                    },
                )
            )

        outcome: Optional[PublishOutcome] = None

        def _publish_attempt() -> PublishOutcome:
            nonlocal outcome
            lookup_resp: WordPressPostLookupBatchItem | WordPressPostLookupResponse
            route_settings = _publish_settings_for_post_type(
                settings,
                entity_route.post_type,
            )
            if existing_post_lookup is not None and not existing_post_lookup.error_code:
                lookup_resp = existing_post_lookup
            else:
                lookup_resp = find_post_by_file_id(
                    WordPressPostLookupRequest(
                        schema_version="1.0",
                        base_url=base_url,
                        auth_header=auth_header,
                        file_id=file_id,
                        ssl_verify=settings.wp.ssl_verify,
                        ca_bundle_path=settings.wp.ca_bundle_path,
                        post_type=entity_route.post_type,
                    ),
                    file_ctx,
                )
            if lookup_resp.found and lookup_resp.post_id and lookup_resp.link:
                if force_report_cards:
                    outcome = publish_html(
                        PublishRequest(
                            schema_version="1.0",
                            html_path=html_path,
                            auth_header=auth_header,
                            file_id=file_id,
                            html_snapshot=html_snapshot,
                            resolved_terms=resolved_terms,
                            existing_post_id=lookup_resp.post_id,
                            run_budget=publish_budget,
                            run_budget_usage=read_publish_budget_usage(
                                publish_budget, file_ctx
                            ),
                        ),
                        route_settings,
                        file_ctx,
                    )
                    outcome = _with_validation(
                        outcome,
                        validation_status,
                        validation_issues,
                    )
                    if outcome.status == "published" and outcome.post_url:
                        state_record_publish(
                            StatePublishRecordRequest(
                                schema_version="1.0",
                                state_db=settings.state_db,
                                file_id=file_id,
                                md5=state_row.md5,
                                wp_post_id=lookup_resp.post_id,
                                wp_post_url=outcome.post_url,
                                post_type=entity_route.post_type,
                            ),
                            file_ctx,
                        )
                        _record_publish_idempotency(
                            settings=settings,
                            outcome=outcome,
                            post_type=entity_route.post_type,
                            checksum=publish_checksum,
                            ctx=file_ctx,
                        )
                    return outcome
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="publish_existing_post",
                        module=logger.name,
                        fields={"file_id": file_id, "post_id": lookup_resp.post_id},
                    )
                )
                state_record_publish(
                    StatePublishRecordRequest(
                        schema_version="1.0",
                        state_db=settings.state_db,
                        file_id=file_id,
                        md5=state_row.md5,
                        wp_post_id=lookup_resp.post_id,
                        wp_post_url=lookup_resp.link,
                        post_type=entity_route.post_type,
                    ),
                    file_ctx,
                )
                outcome = PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="skipped",
                    post_id=lookup_resp.post_id,
                    post_url=lookup_resp.link,
                    error="already_exists",
                    publication_outcome="existing_post_matched",
                    lookup_count=1,
                    authenticated_readback_verified=True,
                )
                return _with_validation(outcome, validation_status, validation_issues)

            if force_report_cards:
                return PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="error",
                    error="report_card_backfill_post_missing",
                    validation_status=validation_status,
                    validation_issues=validation_issues,
                )

            outcome = publish_html(
                PublishRequest(
                    schema_version="1.0",
                    html_path=html_path,
                    auth_header=auth_header,
                    file_id=file_id,
                    html_snapshot=html_snapshot,
                    resolved_terms=resolved_terms,
                    run_budget=publish_budget,
                    run_budget_usage=read_publish_budget_usage(
                        publish_budget, file_ctx
                    ),
                ),
                route_settings,
                file_ctx,
            )
            outcome = _with_validation(outcome, validation_status, validation_issues)
            if outcome.status == "published" and cohort_manifest:
                created_post_readback = read_post_by_id(
                    WordPressPostReadRequest(
                        schema_version="1.0",
                        base_url=base_url,
                        auth_header=auth_header,
                        post_id=outcome.post_id or 0,
                        file_id=file_id,
                        ssl_verify=settings.wp.ssl_verify,
                        ca_bundle_path=settings.wp.ca_bundle_path,
                        post_type=entity_route.post_type,
                    ),
                    file_ctx,
                )
                if not (
                    created_post_readback.found
                    and created_post_readback.post_id
                    and created_post_readback.link
                ):
                    logger.info(
                        log_event(
                            file_ctx,
                            role="orchestrator",
                            event="publish_create_readback_missing",
                            module=logger.name,
                            fields={"file_id": file_id},
                        )
                    )
                    return replace(
                        outcome,
                        status="error",
                        error="wordpress_post_create_readback_missing",
                        publication_outcome="readback_failed",
                    )
                outcome = replace(
                    outcome,
                    post_id=created_post_readback.post_id,
                    post_url=created_post_readback.link,
                    lookup_count=outcome.lookup_count + 1,
                    authenticated_readback_verified=True,
                )
            if outcome.status == "published" and outcome.post_id and outcome.post_url:
                state_record_publish(
                    StatePublishRecordRequest(
                        schema_version="1.0",
                        state_db=settings.state_db,
                        file_id=file_id,
                        md5=state_row.md5,
                        wp_post_id=outcome.post_id,
                        wp_post_url=outcome.post_url,
                        post_type=entity_route.post_type,
                    ),
                    file_ctx,
                )
            if outcome.status in {"published", "skipped"}:
                _record_publish_idempotency(
                    settings=settings,
                    outcome=outcome,
                    post_type=entity_route.post_type,
                    checksum=publish_checksum,
                    ctx=file_ctx,
                )
            return outcome

        try:
            outcome = run_with_retry(
                step_name="publish_html",
                operation=_publish_attempt,
                ctx=file_ctx,
                logger=logger,
                module_name=logger.name,
                policy=RetryPolicy(
                    retries=2,
                    base_delay_seconds=1.0,
                    backoff_step_seconds=1.0,
                    jitter_seconds=0.25,
                ),
                retry_event="publish_retry",
                retry_fields_builder=lambda exc, attempt: {
                    "file_id": file_id,
                    "attempt": attempt + 1,
                    "code": exc.code if isinstance(exc, AppError) else "",
                },
                on_terminal_failure=_record_publish_failure,
                is_retryable=lambda exc: isinstance(exc, AppError) and exc.retryable,
                sleep_fn=time.sleep,
            )
        except AppError as exc:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_error",
                    module=logger.name,
                    fields={"file_id": file_id, "error": exc.message, "code": exc.code},
                )
            )
            outcome = PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=file_id,
                status="error",
                error=exc.message,
            )
            outcome = _with_validation(outcome, validation_status, validation_issues)
        except AppError:
            raise
        except Exception as exc:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_error",
                    module=logger.name,
                    fields={"file_id": file_id, "error": str(exc)},
                )
            )
            outcome = PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=file_id,
                status="error",
                error=str(exc),
            )
            outcome = _with_validation(outcome, validation_status, validation_issues)

        if outcome is not None:
            outcomes.append(outcome)
            if outcome.status == "published":
                published += 1
            continue
        logger.info(
            log_event(
                file_ctx,
                role="orchestrator",
                event="publish_error",
                module=logger.name,
                fields={"file_id": file_id, "error": "publish_failed"},
            )
        )
        outcomes.append(
            PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=file_id,
                status="error",
                error="publish_failed",
                validation_status=validation_status,
                validation_issues=validation_issues,
            )
        )

    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="publish_complete",
            module=logger.name,
            fields={"attempted": attempted, "published": published},
        )
    )
    for html_path, plan in publication_plans.items():
        outcome = next(
            (candidate for candidate in outcomes if candidate.html_path == html_path),
            None,
        )
        actual_stages = (
            ["publication_complete"]
            if outcome and outcome.status in {"published", "skipped"}
            else []
        )
        actual_calls = (
            ["wordpress_write"] if outcome and outcome.status == "published" else []
        )
        try:
            divergence = record_minimal_execution_plan_result(
                ExecutionPlanResultRequest(
                    schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                    db_path=settings.reports_db,
                    plan_hash=plan.plan_hash,
                    report_id=plan.report_id,
                    execution_intent=plan.execution_intent,
                    actual_stages=actual_stages,
                    actual_external_calls=actual_calls,
                    actual_side_effects=(
                        list(plan.expected_side_effects)
                        if outcome and outcome.status == "published"
                        else []
                    ),
                    duration_ms=int(
                        (
                            time.perf_counter()
                            - publication_plan_started_at.get(
                                html_path, time.perf_counter()
                            )
                        )
                        * 1000
                    ),
                    reusable_artifact_ids=list(plan.reusable_artifacts),
                    execution_status=outcome.status if outcome else "not_attempted",
                ),
                root_ctx,
            )
            if normalized_plan_mode == "enforce" and divergence:
                raise AppError(
                    code="minimal_execution_plan_diverged",
                    message="Actual publication work diverged from its enforced plan",
                    retryable=False,
                    context={"plan_hash": plan.plan_hash, "html_path": html_path},
                )
        except Exception as exc:
            logger.info(
                log_event(
                    root_ctx,
                    role="orchestrator",
                    event="minimal_execution_plan_result_record_failed",
                    module=logger.name,
                    fields={
                        "plan_hash": plan.plan_hash,
                        "html_path": html_path,
                        "error": str(exc),
                    },
                )
            )
    if cohort_manifest:
        _record_validation_cohort_publish_outcomes(
            cohort_manifest=cohort_manifest,
            reports_db=settings.reports_db,
            outcomes=outcomes,
            ctx=root_ctx,
            require_full_workflow=require_full_validation_manifest,
        )
    return outcomes
