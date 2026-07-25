"""Approved deferred-work recovery adapters shared by CLI and supervisor paths."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from src.contracts.config import ConfigLoadRequest
from src.contracts.deferred_work import (
    DeferredWorkItem,
    DeferredWorkReaperRequest,
    DeferredWorkResumePlan,
)
from src.contracts.drive import DriveFile
from src.contracts.files import PipelineCheckpointReadRequest
from src.contracts.ingest import IngestSettings
from src.contracts.remediation import RemediationReaperRequest, RemediationRecord
from src.contracts.report_store import PublishersListRequest
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId, TaskId
from src.contracts.wordpress import WordPressPostLookupRequest
from src.contracts.workflow_control import WorkflowControlSettings
from src.contracts.workflow_queue import (
    PublisherDiscoveryPayload,
    ReportAcquisitionPayload,
    WorkflowJobSubmission,
)
from src.orchestrators.deferred_work_orchestrator import (
    DeferredWorkReaperDependencies,
    run_bounded_deferred_work_reaper,
)
from src.orchestrators.failure_recovery_registry import recovery_rule_for
from src.orchestrators.remediation_orchestrator import (
    RemediationReaperDependencies,
    run_bounded_remediation_reaper,
)
from src.orchestrators.report_pipeline_orchestrator import (
    build_report_pipeline_deferred_work_plan,
    resume_deferred_report_pipeline,
)
from src.services import file_service
from src.services.config_service import load_publish_settings
from src.services.report_store_service import list_publishers
from src.services.wordpress_service import find_post_by_file_id
from src.services.workflow_queue_service import enqueue_workflow_job
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.wp_auth import build_auth_header


@dataclass(frozen=True)
class RecoveryAdapterRegistry:
    """Finite set of recovery handlers with retained-proof validation.

    Workflows without an entry intentionally flow to the canonical remediation
    handoff.  Registering a new adapter therefore requires its own proof and
    is not enabled merely by a workflow name arriving in durable state.
    """

    deferred_work_dependencies: DeferredWorkReaperDependencies
    remediation_dependencies: RemediationReaperDependencies
    supported_workflows: tuple[str, ...]


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _require_url(value: str, *, workflow: str) -> str:
    candidate = str(value or "").strip()
    if candidate.startswith(("https://", "http://")):
        return candidate
    raise AppError(
        code="deferred_work_retained_source_missing",
        message="Deferred acquisition recovery requires a retained canonical URL",
        retryable=False,
        context={"workflow": workflow},
    )


def _queue_plan(
    item: DeferredWorkItem, *, resume_stage: str, material: str
) -> DeferredWorkResumePlan:
    if not item.idempotency_key:
        raise AppError(
            code="deferred_work_idempotency_missing",
            message="Deferred recovery requires the original idempotency key",
            retryable=False,
            context={"workflow": item.workflow},
        )
    return DeferredWorkResumePlan(
        schema_version="1.0",
        plan_hash=_digest(
            "recovery-adapter-v1",
            item.workflow,
            item.work_key,
            item.idempotency_key,
            material,
            item.plan_hash,
        ),
        resume_stage=resume_stage,
        reusable_artifacts=list(item.reusable_artifacts),
    )


def build_recovery_adapter_registry(
    *,
    ingest_settings: IngestSettings,
    workflow_control_settings: WorkflowControlSettings,
) -> RecoveryAdapterRegistry:
    """Build the only currently approved, latest-safe recovery adapter set."""

    def build_report_plan(item, ctx):
        return build_report_pipeline_deferred_work_plan(item, ingest_settings, ctx)

    def resume_report_plan(item, plan, ctx):
        return resume_deferred_report_pipeline(
            item,
            plan,
            ingest_settings,
            ctx,
            workflow_control_settings=workflow_control_settings,
        )

    def build_download_plan(item: DeferredWorkItem, _ctx: RunContext):
        source_url = _require_url(item.source_id, workflow=item.workflow)
        return _queue_plan(
            item,
            resume_stage="queue_report_acquisition",
            material=f"{source_url}:{item.publisher_id}",
        )

    def resume_download_plan(
        item: DeferredWorkItem, plan: DeferredWorkResumePlan, ctx: RunContext
    ) -> str:
        source_url = _require_url(item.source_id, workflow=item.workflow)
        source_identity = _digest("source", source_url)
        enqueue_workflow_job(
            ingest_settings.state_db,
            WorkflowJobSubmission(
                schema_version="1.0",
                queue_name="report_acquisition",
                job_type="report_acquisition.v1",
                payload=ReportAcquisitionPayload(
                    source_identity_id=source_identity,
                    source_url=source_url,
                    publisher_id=item.publisher_id,
                    acquisition_policy_version="deferred-recovery.v1",
                    input_reference=source_url,
                    input_content_hash=source_identity,
                    processing_version="deferred-recovery.v1",
                    attributes={"deferred_work_key": item.work_key},
                ),
                idempotency_key=_digest(
                    "deferred-report-download", item.idempotency_key, plan.plan_hash
                ),
                deduplication_scope="deferred-report-download",
                root_workflow_id=item.run_id or f"deferred:{item.work_key}",
                trigger_event_id=f"deferred:{item.work_key}",
                correlation_id=item.run_id or item.work_key,
                publisher_id=item.publisher_id,
                source_identity_id=source_identity,
                report_id=item.report_id,
                budget_profile="browser_acquisition",
                execution_plan_hash=plan.plan_hash,
            ),
            ctx,
        )
        return "completed"

    def _publisher_url(item: DeferredWorkItem, ctx: RunContext) -> str:
        if str(item.source_id).startswith(("https://", "http://")):
            return str(item.source_id)
        publishers = list_publishers(
            PublishersListRequest(
                schema_version="1.0", db_path=ingest_settings.reports_db, limit=500
            ),
            ctx,
        ).publishers
        needle = item.publisher_id.strip().casefold()
        for publisher in publishers:
            if publisher.publisher_name.strip().casefold() == needle:
                return _require_url(publisher.insights_url, workflow=item.workflow)
        raise AppError(
            code="deferred_work_retained_publisher_missing",
            message=(
                "Deferred inventory recovery requires a retained publisher insights URL"
            ),
            retryable=False,
            context={"workflow": item.workflow},
        )

    def build_inventory_plan(item: DeferredWorkItem, ctx: RunContext):
        insights_url = _publisher_url(item, ctx)
        return _queue_plan(
            item,
            resume_stage="queue_publisher_discovery",
            material=f"{item.publisher_id}:{insights_url}",
        )

    def resume_inventory_plan(
        item: DeferredWorkItem, plan: DeferredWorkResumePlan, ctx: RunContext
    ) -> str:
        insights_url = _publisher_url(item, ctx)
        source_hash = _digest("publisher", item.publisher_id, insights_url)
        enqueue_workflow_job(
            ingest_settings.state_db,
            WorkflowJobSubmission(
                schema_version="1.0",
                queue_name="publisher_discovery",
                job_type="publisher_discovery.v1",
                payload=PublisherDiscoveryPayload(
                    publisher_id=item.publisher_id,
                    insights_url=insights_url,
                    discovery_policy_version="deferred-recovery.v1",
                    input_reference=insights_url,
                    input_content_hash=source_hash,
                    processing_version="deferred-recovery.v1",
                    attributes={"deferred_work_key": item.work_key},
                ),
                idempotency_key=_digest(
                    "deferred-publisher-inventory", item.idempotency_key, plan.plan_hash
                ),
                deduplication_scope="deferred-publisher-inventory",
                root_workflow_id=item.run_id or f"deferred:{item.work_key}",
                trigger_event_id=f"deferred:{item.work_key}",
                correlation_id=item.run_id or item.work_key,
                publisher_id=item.publisher_id,
                budget_profile="publisher_inventory",
                execution_plan_hash=plan.plan_hash,
            ),
            ctx,
        )
        return "completed"

    def validate_remediation_checkpoint(
        record: RemediationRecord, ctx: RunContext
    ) -> bool:
        rule = recovery_rule_for(record.workflow, record.error_code)
        checkpoint = record.checkpoint
        if rule is None or checkpoint is None:
            return False
        if record.workflow != "report_generation":
            response = file_service.read_pipeline_checkpoint(
                PipelineCheckpointReadRequest(
                    schema_version="1.0",
                    checkpoint_root=ingest_settings.output_dir,
                    pipeline_name="publishing",
                    file_id=record.report_id,
                    stage_name=rule.required_checkpoint,
                ),
                ctx,
            )
            observed = response.checkpoint
            lineage = observed.payload.get("artifact_lineage") if observed else None
            return bool(
                response.found
                and observed is not None
                and response.checkpoint_path == checkpoint.path
                and observed.stage_status == "completed"
                and observed.stage_name == rule.required_checkpoint
                and sha256_json(asdict(observed)) == checkpoint.checksum_sha256
                and isinstance(lineage, dict)
                and checkpoint.lineage_ref in {str(value) for value in lineage.values()}
            )
        response = file_service.read_pipeline_checkpoint(
            PipelineCheckpointReadRequest(
                schema_version="1.0",
                checkpoint_root=ingest_settings.output_dir,
                pipeline_name="report_generation",
                file_id=record.report_id,
                stage_name=rule.required_checkpoint,
            ),
            ctx,
        )
        observed = response.checkpoint
        if (
            not response.found
            or observed is None
            or response.checkpoint_path != checkpoint.path
            or observed.stage_status != "completed"
            or observed.stage_name != checkpoint.stage_name
            or sha256_json(asdict(observed)) != checkpoint.checksum_sha256
        ):
            return False
        lineage = observed.payload.get("artifact_lineage")
        return bool(
            isinstance(lineage, dict)
            and checkpoint.lineage_ref in {str(value) for value in lineage.values()}
        )

    def rerun_targeted_artifact_family(
        record: RemediationRecord, ctx: RunContext
    ) -> str:
        rule = recovery_rule_for(record.workflow, record.error_code)
        if rule is None or record.workflow != "report_generation":
            return "terminal"
        local_pdf_path = next(
            (
                item.reference
                for item in record.reusable_artifacts
                if item.name == "source_pdf" and item.reference
            ),
            next(
                (
                    item.reference
                    for item in record.reusable_artifacts
                    if item.name == "analysis_pdf" and item.reference
                ),
                "",
            ),
        )
        admission_hash = str(record.diagnostics.get("admission_decision_hash") or "")
        if not local_pdf_path or not admission_hash or not record.report_id:
            return "terminal"
        recovery_ctx = replace(
            ctx,
            run_id=RunId(record.run_id),
            task_id=TaskId(f"remediation:{record.remediation_id}"),
            report_id=record.report_id,
            source_identity_id=record.source_id,
            workflow="report_generation",
            stage=rule.retry_scope,
            artifact_family=rule.required_invalidations[0],
            admission_decision_hash=admission_hash,
            configuration_hash=str(record.diagnostics.get("configuration_hash") or ""),
            policy_hash=str(record.diagnostics.get("policy_hash") or ""),
            repair_attempt=record.attempt_count,
        )
        from src.orchestrators.report_pipeline_orchestrator import run_report_pipeline

        file = DriveFile(
            schema_version="1.0",
            file_id=record.report_id,
            name=Path(local_pdf_path).name or record.report_id,
            modified_time=None,
            md5_checksum=record.input_checksum or "",
        )
        if rule.retry_scope in {"rendering", "report_cards"}:
            outcome = run_report_pipeline(
                file,
                local_pdf_path,
                ingest_settings,
                record.input_checksum or None,
                recovery_ctx,
                retries=0,
                workflow_control_settings=workflow_control_settings,
                execution_plan_mode="enforce",
                recovery_execution_intent="render_repair",
                recovery_invalidations={"rendered_html": rule.error_code},
            )
        elif rule.retry_scope == "affected_claim_or_insight":
            outcome = run_report_pipeline(
                file,
                local_pdf_path,
                ingest_settings,
                record.input_checksum or None,
                recovery_ctx,
                retries=0,
                workflow_control_settings=workflow_control_settings,
                execution_plan_mode="enforce",
                recovery_execution_intent="targeted_repair",
                recovery_invalidations={
                    "report_vs/artifacts/insights_final": rule.error_code
                },
            )
        else:
            # Taxonomy/category recovery starts after the retained selection
            # checkpoint. The existing vector identifier is validated above;
            # source preparation and vector creation are never re-entered.
            outcome = run_report_pipeline(
                file,
                local_pdf_path,
                ingest_settings,
                record.input_checksum or None,
                recovery_ctx,
                retries=0,
                workflow_control_settings=workflow_control_settings,
                execution_plan_mode="disabled",
                resume_from_stage="selection_complete",
            )
        return (
            "succeeded"
            if outcome.status in {"processed", "checkpointed"}
            else "terminal"
        )

    def retry_wordpress_readback(
        record: RemediationRecord, readback_ctx: RunContext
    ) -> str:
        """Reconcile the original publication through a GET-only lookup."""

        if not record.report_id:
            return "terminal"
        publish = load_publish_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), readback_ctx
        )
        wp = publish.wp
        response = find_post_by_file_id(
            WordPressPostLookupRequest(
                schema_version="1.0",
                base_url=wp.site_url,
                auth_header=build_auth_header(
                    username=wp.username,
                    app_password=wp.app_password,
                    bearer_token=wp.bearer_token,
                ),
                file_id=record.report_id,
                ssl_verify=wp.ssl_verify,
                ca_bundle_path=wp.ca_bundle_path,
                post_type=wp.post_type,
            ),
            readback_ctx,
        )
        return "succeeded" if response.found else "terminal"

    return RecoveryAdapterRegistry(
        deferred_work_dependencies=DeferredWorkReaperDependencies(
            plan_builders={
                "report_generation": build_report_plan,
                "report_download": build_download_plan,
                "publisher_inventory": build_inventory_plan,
            },
            resumers={
                "report_generation": resume_report_plan,
                "report_download": resume_download_plan,
                "publisher_inventory": resume_inventory_plan,
            },
        ),
        remediation_dependencies=RemediationReaperDependencies(
            rerun_targeted_artifact_family=rerun_targeted_artifact_family,
            retry_idempotent_publication=retry_wordpress_readback,
            checkpoint_validator=validate_remediation_checkpoint,
            idempotency_check=lambda _record, _ctx: "safe_to_execute",
        ),
        supported_workflows=(
            "report_generation",
            "report_download",
            "publisher_inventory",
        ),
    )


def reap_deferred_work_from_supervisor(
    request,
    ctx: RunContext,
    *,
    registry: RecoveryAdapterRegistry,
    settings: WorkflowControlSettings,
) -> int:
    """Execute one bounded gated recovery pass for a supervisor invocation."""

    reaper = settings.deferred_work_reaper
    response = run_bounded_deferred_work_reaper(
        DeferredWorkReaperRequest(
            schema_version="1.0",
            usage_db_path=request.usage_db_path,
            state_db=request.state_db,
            worker_id=f"{request.worker_id}:deferred-work",
            now_utc=request.now_utc,
            execution_enabled=reaper.execution_enabled,
            limit=reaper.max_records_per_run,
            lease_seconds=reaper.lease_seconds,
            retry_delay_seconds=reaper.retry_delay_seconds,
        ),
        ctx,
        dependencies=registry.deferred_work_dependencies,
    )
    return response.inspected_count


def reap_remediation_from_supervisor(
    request,
    ctx: RunContext,
    *,
    registry: RecoveryAdapterRegistry,
    settings: WorkflowControlSettings,
) -> int:
    """Execute one bounded, feature-gated typed recovery pass."""

    reaper = settings.remediation_reaper
    response = run_bounded_remediation_reaper(
        RemediationReaperRequest(
            schema_version="1.0",
            state_db=request.state_db,
            worker_id=f"{request.worker_id}:remediation",
            now_utc=request.now_utc,
            execution_enabled=reaper.execution_enabled,
            limit=reaper.max_records_per_run,
            lease_seconds=reaper.lease_seconds,
        ),
        ctx,
        dependencies=registry.remediation_dependencies,
    )
    return response.inspected_count


__all__ = [
    "RecoveryAdapterRegistry",
    "build_recovery_adapter_registry",
    "reap_deferred_work_from_supervisor",
    "reap_remediation_from_supervisor",
]
