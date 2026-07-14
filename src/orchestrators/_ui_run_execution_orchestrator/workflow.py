from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

from typing import Any

from src.contracts.acquisition_audit import AcquisitionAuditBatchRequest
from src.contracts.browser_download import ReportDownloadOrchestratorRequest
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.cover_images import CoverImageOrchestratorRequest
from src.contracts.publisher_inventory import PublisherInventoryDiscoveryRequest
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId
from src.contracts.ui_run_control import UiRunWorkerRequest
from src.contracts.ui_run_payloads import (
    AcquisitionAuditUiRunPayload,
    CandidateExtractionUiRunPayload,
    CoverImagesUiRunPayload,
    CrossReportAnalysisUiRunPayload,
    IngestUiRunPayload,
    PublishUiRunPayload,
    PublisherDiscoveryUiRunPayload,
    ReportDownloadUiRunPayload,
    SignalCandidateExtractionUiRunPayload,
    SignalPostUiRunPayload,
    UiRunReplayUiRunPayload,
)
from src.contracts.ui_run_replay import UiRunExecutionResponse, UiRunReplayRequest
from src.orchestrators.acquisition_audit_orchestrator import run_acquisition_audit
from src.orchestrators.candidate_extraction_orchestrator import run_candidate_extraction
from src.orchestrators.cover_image_orchestrator import run_cover_image_generation
from src.orchestrators.cross_report_analysis_orchestrator import (
    run_cross_report_analysis,
)
from src.orchestrators.ingest_orchestrator import run_ingest
from src.orchestrators.publish_orchestrator import run_publish
from src.orchestrators.publisher_inventory_orchestrator import (
    run_publisher_inventory_discovery,
)
from src.orchestrators.report_download_orchestrator import run_report_download
from src.orchestrators.signal_candidate_orchestrator import (
    run_signal_candidate_extraction,
)
from src.orchestrators.signal_post_orchestrator import run_signal_post_workflow
from src.orchestrators import workflow_control_orchestrator as workflow_control
from src.services.config_service import (
    build_ingest_settings,
    load_browser_download_settings,
    load_publisher_inventory_settings,
    load_publish_settings,
    load_settings,
)
from src.services.run_registry_service import default_ui_run_registry_path
from src.utils.errors import AppError
from src.utils.logging import log_event

from .shared import *  # noqa: F401,F403
from .shared import PROMPT_TREE_ROOT, SOURCE_TREE_ROOT, logger
from .validation import _sanitize_snapshot, _validate_ui_run_payload
from .responses import _execution_response, _invalid_payload_config_snapshot
from .requests import (
    _cross_report_analysis_request,
    _signal_candidate_request,
    _signal_post_request,
)


def resolve_ui_run_config_snapshot(
    worker_request: UiRunWorkerRequest, ctx: RunContext
) -> dict[str, Any]:
    payload = worker_request.request_payload
    run_type = worker_request.run_type
    try:
        _validate_ui_run_payload(run_type=run_type, payload=payload)
    except AppError as exc:
        if exc.code.startswith("ui_run_payload_"):
            return _invalid_payload_config_snapshot(
                worker_request=worker_request,
                error=exc,
            )
        raise
    if run_type in {"ingest", "candidate_extraction"}:
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        ingest_settings = build_ingest_settings(
            IngestSettingsBuildRequest(schema_version="1.0", app_settings=app_settings),
            ctx,
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(ingest_settings)}
    if run_type == "cover_images":
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(app_settings)}
    if run_type == "publish":
        publish_settings = load_publish_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(publish_settings)}
    if run_type == "publisher_discovery":
        inventory_settings = load_publisher_inventory_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            ctx,
        )
        return {
            "run_type": run_type,
            "settings": _sanitize_snapshot(inventory_settings),
        }
    if run_type == "report_download":
        browser_settings = load_browser_download_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            ctx,
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(browser_settings)}
    if run_type == "acquisition_audit":
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        inventory_settings = load_publisher_inventory_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            ctx,
        )
        browser_settings = load_browser_download_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            ctx,
        )
        return {
            "run_type": run_type,
            "app_settings": _sanitize_snapshot(app_settings),
            "inventory_settings": _sanitize_snapshot(inventory_settings),
            "browser_settings": _sanitize_snapshot(browser_settings),
        }
    if run_type in {
        "cross_report_analysis",
        "signal_candidate_extraction",
        "signal_post",
    }:
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(app_settings)}
    if run_type == "ui_run_replay":
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        replay_payload = _validate_ui_run_payload(run_type=run_type, payload=payload)
        assert isinstance(replay_payload, UiRunReplayUiRunPayload)
        return {
            "run_type": run_type,
            "registry_path": replay_payload.registry_path
            or default_ui_run_registry_path(app_settings.state_db),
            "run_id": replay_payload.run_id,
        }
    raise AppError(
        code="ui_run_type_unknown",
        message=f"Unknown UI run type: {run_type}",
        retryable=False,
        context={"run_type": run_type, "payload_keys": sorted(payload.keys())},
    )


def _execute_ui_run_action(
    worker_request: UiRunWorkerRequest, ctx: RunContext
) -> UiRunExecutionResponse:
    payload = worker_request.request_payload
    run_type = worker_request.run_type
    config_snapshot: dict[str, Any] = {
        "run_type": run_type,
        "request_payload_keys": sorted(payload.keys()),
        "source_tree_root": str(SOURCE_TREE_ROOT),
        "prompt_tree_root": str(PROMPT_TREE_ROOT),
    }
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="ui_run_execute_start",
            module=logger.name,
            fields={
                "run_id": worker_request.run_id,
                "run_type": run_type,
                "payload_keys": sorted(payload.keys()),
            },
        )
    )
    try:
        validated_payload = _validate_ui_run_payload(run_type=run_type, payload=payload)
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="ui_run_payload_validated",
                module=logger.name,
                fields={
                    "run_id": worker_request.run_id,
                    "run_type": run_type,
                    "payload": _sanitize_snapshot(validated_payload),
                },
            )
        )
        if run_type == "ingest":
            assert isinstance(validated_payload, IngestUiRunPayload)
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            ingest_settings = build_ingest_settings(
                IngestSettingsBuildRequest(
                    schema_version="1.0", app_settings=app_settings
                ),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(ingest_settings),
            }
            ingest_outcomes = run_ingest(
                ingest_settings,
                folder_id=validated_payload.folder_id,
                limit=validated_payload.limit,
                ctx=ctx,
            )
            processed_count = len(
                [item for item in ingest_outcomes if item.status == "processed"]
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "processed_count": processed_count,
                    "total_count": len(ingest_outcomes),
                },
                artifact_paths=[
                    item.html_path for item in ingest_outcomes if item.html_path
                ],
                config_snapshot=config_snapshot,
            )
        elif run_type == "candidate_extraction":
            assert isinstance(validated_payload, CandidateExtractionUiRunPayload)
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            candidate_settings = build_ingest_settings(
                IngestSettingsBuildRequest(
                    schema_version="1.0", app_settings=app_settings
                ),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(candidate_settings),
            }
            candidate_outcomes = run_candidate_extraction(
                candidate_settings,
                folder_id=validated_payload.folder_id,
                limit=validated_payload.limit,
                file_id=validated_payload.file_id,
                pdf_path=validated_payload.pdf_path,
                report_id=validated_payload.report_id,
                ctx=ctx,
            )
            artifact_paths: list[str] = []
            for outcome in candidate_outcomes:
                if outcome.candidates_path:
                    artifact_paths.append(outcome.candidates_path)
                artifact_paths.extend(outcome.crop_paths[:5])
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "total_count": len(candidate_outcomes),
                    "candidate_count": sum(
                        item.candidate_count for item in candidate_outcomes
                    ),
                    "chart_count": sum(item.chart_count for item in candidate_outcomes),
                    "table_count": sum(item.table_count for item in candidate_outcomes),
                },
                artifact_paths=artifact_paths,
                config_snapshot=config_snapshot,
            )
        elif run_type == "cover_images":
            assert isinstance(validated_payload, CoverImagesUiRunPayload)
            cover_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(cover_settings),
            }
            cover_outcomes = run_cover_image_generation(
                CoverImageOrchestratorRequest(
                    schema_version="1.0",
                    reports_db=cover_settings.reports_db,
                    output_dir=cover_settings.output_dir,
                    style_config_path=validated_payload.style_config_path,
                    limit=validated_payload.limit,
                    file_id=validated_payload.file_id,
                ),
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "total_count": len(cover_outcomes),
                    "generated_count": len(
                        [item for item in cover_outcomes if item.status == "generated"]
                    ),
                },
                artifact_paths=[
                    asset.output_path
                    for item in cover_outcomes
                    if item.assets is not None
                    for asset in (
                        item.assets.small,
                        item.assets.medium,
                        item.assets.large,
                    )
                ],
                config_snapshot=config_snapshot,
            )
        elif run_type == "publish":
            assert isinstance(validated_payload, PublishUiRunPayload)
            publish_settings = load_publish_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(publish_settings),
            }
            publish_outcomes = run_publish(
                publish_settings,
                limit=validated_payload.limit,
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "total_count": len(publish_outcomes),
                    "published_count": len(
                        [
                            item
                            for item in publish_outcomes
                            if item.status == "published"
                        ]
                    ),
                },
                artifact_paths=[
                    item.html_path for item in publish_outcomes if item.html_path
                ],
                config_snapshot=config_snapshot,
            )
        elif run_type == "publisher_discovery":
            assert isinstance(validated_payload, PublisherDiscoveryUiRunPayload)
            inventory_settings = load_publisher_inventory_settings(
                ConfigLoadRequest(schema_version="1.0", path=""),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(inventory_settings),
            }
            discovery_result = run_publisher_inventory_discovery(
                PublisherInventoryDiscoveryRequest(
                    schema_version="1.0",
                    insights_url=validated_payload.insights_url,
                    reports_db=inventory_settings.reports_db,
                    settings=inventory_settings,
                ),
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "publisher_name": discovery_result.publisher_name,
                    "current_report_count": discovery_result.current_report_count,
                    "previous_report_count": discovery_result.previous_report_count,
                    "new_report_count": len(discovery_result.new_report_urls),
                    "quality_band": discovery_result.run_quality_summary.quality_band,
                    "recommended_route_kind": discovery_result.run_quality_summary.recommended_route_kind,
                },
                artifact_paths=[],
                config_snapshot=config_snapshot,
            )
        elif run_type == "report_download":
            assert isinstance(validated_payload, ReportDownloadUiRunPayload)
            browser_settings = load_browser_download_settings(
                ConfigLoadRequest(schema_version="1.0", path=""),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(browser_settings),
            }
            download_result = run_report_download(
                ReportDownloadOrchestratorRequest(
                    schema_version="1.0",
                    url=validated_payload.url,
                    settings=browser_settings,
                    state_db=browser_settings.state_db,
                    reports_db=browser_settings.reports_db,
                    delivery_email=validated_payload.delivery_email,
                    publisher_insights_url=validated_payload.publisher_insights_url,
                    publisher_google_folder=validated_payload.publisher_google_folder,
                ),
                ctx=ctx,
            )
            artifact_paths = [
                path
                for path in [
                    download_result.downloaded_file_path,
                    download_result.onsite_capture_path,
                ]
                if path
            ]
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "route_kind": download_result.route_kind,
                    "route_family": download_result.route_family,
                    "outcome": download_result.outcome,
                    "final_page_url": download_result.final_page_url,
                    "downloaded_file_name": download_result.downloaded_file_name or "",
                },
                artifact_paths=artifact_paths,
                config_snapshot=config_snapshot,
            )
        elif run_type == "acquisition_audit":
            assert isinstance(validated_payload, AcquisitionAuditUiRunPayload)
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            inventory_settings = load_publisher_inventory_settings(
                ConfigLoadRequest(schema_version="1.0", path=""),
                ctx,
            )
            browser_settings = load_browser_download_settings(
                ConfigLoadRequest(schema_version="1.0", path=""),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "app_settings": _sanitize_snapshot(app_settings),
                "inventory_settings": _sanitize_snapshot(inventory_settings),
                "browser_settings": _sanitize_snapshot(browser_settings),
            }
            audit_result = run_acquisition_audit(
                AcquisitionAuditBatchRequest(
                    schema_version="1.0",
                    reports_db=app_settings.reports_db,
                    publisher_inventory_settings=inventory_settings,
                    browser_download_settings=browser_settings,
                    output_dir=app_settings.output_dir,
                    delivery_email=validated_payload.delivery_email,
                    publisher_limit=validated_payload.publisher_limit,
                    candidate_limit_per_publisher=validated_payload.candidate_limit_per_publisher,
                ),
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "publisher_count": audit_result.publisher_count,
                    "candidate_count": audit_result.candidate_count,
                    "output_path": audit_result.output_path,
                },
                artifact_paths=[audit_result.output_path],
                config_snapshot=config_snapshot,
            )
        elif run_type == "cross_report_analysis":
            assert isinstance(validated_payload, CrossReportAnalysisUiRunPayload)
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            cross_report_request = _cross_report_analysis_request(
                validated_payload,
                app_settings,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(app_settings),
                "request": _sanitize_snapshot(cross_report_request),
            }
            publish_settings = None
            if validated_payload.publication_mode == "publish_live":
                publish_settings = load_publish_settings(
                    ConfigLoadRequest(schema_version="1.0", path=""),
                    ctx,
                )
            cross_report_outcome = run_cross_report_analysis(
                cross_report_request,
                app_settings,
                ctx,
                publish_settings=publish_settings,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "status": cross_report_outcome.status,
                    "request_id": cross_report_outcome.request.request_id,
                    "selected_theme": cross_report_outcome.generated_result.selected_theme.label,
                    "selected_report_count": len(
                        cross_report_outcome.generated_result.selected_sources
                    ),
                    "validation_status": cross_report_outcome.validation_result.status,
                    "publication_mode": cross_report_outcome.publish_result.publication_mode,
                    "publish_status": cross_report_outcome.publish_result.status,
                    "post_url": cross_report_outcome.publish_result.post_url or "",
                    "idempotency_reused": cross_report_outcome.idempotency_reused,
                },
                artifact_paths=[
                    path for path in [cross_report_outcome.artifact_path] if path
                ],
                config_snapshot=config_snapshot,
            )
        elif run_type == "signal_candidate_extraction":
            assert isinstance(
                validated_payload,
                SignalCandidateExtractionUiRunPayload,
            )
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            candidate_request = _signal_candidate_request(
                validated_payload,
                app_settings,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(app_settings),
                "request": _sanitize_snapshot(candidate_request),
            }
            signal_candidate_outcome = run_signal_candidate_extraction(
                candidate_request, ctx
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "status": signal_candidate_outcome.status,
                    "extraction_request_id": signal_candidate_outcome.extraction_request_id,
                    "candidate_count": signal_candidate_outcome.candidate_count,
                    "group_count": signal_candidate_outcome.group_count,
                    "stored_candidate_count": signal_candidate_outcome.stored_response.candidate_count,
                    "stored_group_count": signal_candidate_outcome.stored_response.group_count,
                },
                artifact_paths=[],
                config_snapshot=config_snapshot,
            )
        elif run_type == "signal_post":
            assert isinstance(validated_payload, SignalPostUiRunPayload)
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            signal_request = _signal_post_request(validated_payload, app_settings)
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(app_settings),
                "request": _sanitize_snapshot(signal_request),
            }
            publish_settings = None
            if validated_payload.publication_mode == "publish_live":
                publish_settings = load_publish_settings(
                    ConfigLoadRequest(schema_version="1.0", path=""),
                    ctx,
                )
            signal_post_result = run_signal_post_workflow(
                signal_request,
                ctx,
                publish_settings=publish_settings,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "request_id": signal_post_result.request_id,
                    "title": signal_post_result.projection.title,
                    "slug": signal_post_result.projection.slug,
                    "confidence": signal_post_result.projection.confidence,
                    "validation_status": signal_post_result.projection.validation_status,
                    "publish_status": signal_post_result.publish_result.status,
                    "target_route": signal_post_result.publish_result.target_route,
                    "post_url": signal_post_result.publish_result.post_url or "",
                },
                artifact_paths=[],
                config_snapshot=config_snapshot,
            )
        elif run_type == "ui_run_replay":
            assert isinstance(validated_payload, UiRunReplayUiRunPayload)
            from src.orchestrators.ui_run_replay_orchestrator import replay_ui_run

            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            registry_path = (
                validated_payload.registry_path
                or default_ui_run_registry_path(app_settings.state_db)
            )
            config_snapshot = {
                "run_type": run_type,
                "registry_path": registry_path,
                "run_id": validated_payload.run_id,
            }
            replay_result = replay_ui_run(
                request=UiRunReplayRequest(
                    schema_version="1.0",
                    registry_path=registry_path,
                    run_id=RunId(validated_payload.run_id),
                ),
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded" if replay_result.report.matched else "failed",
                result_summary={
                    "original_run_id": str(replay_result.original_record.run_id),
                    "original_run_type": replay_result.original_record.run_type,
                    "replay_status": replay_result.report.replay_status,
                    "matched": replay_result.report.matched,
                    "delta_count": len(replay_result.report.deltas),
                    "manifest_path": replay_result.manifest_path,
                    "report_path": replay_result.report_path,
                },
                artifact_paths=[replay_result.manifest_path, replay_result.report_path],
                config_snapshot=config_snapshot,
                error_code=""
                if replay_result.report.matched
                else "ui_run_replay_mismatch",
                error_message=""
                if replay_result.report.matched
                else "UI run replay completed with deltas.",
                error_retryable=False,
                error_severity="error",
            )
        else:
            raise AppError(
                code="ui_run_type_unknown",
                message=f"Unknown UI run type: {run_type}",
                retryable=False,
                context={"run_type": run_type},
            )
    except AppError as exc:
        if exc.code.startswith("ui_run_payload_"):
            config_snapshot = _invalid_payload_config_snapshot(
                worker_request=worker_request,
                error=exc,
            )
        response = _execution_response(
            worker_request=worker_request,
            status="failed",
            result_summary={
                "failure_context": _sanitize_snapshot(dict(exc.context or {})),
            },
            artifact_paths=[],
            config_snapshot=config_snapshot,
            error_code=exc.code,
            error_message=exc.message,
            error_retryable=exc.retryable,
            error_severity=exc.severity,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="ui_run_execute_failed",
                module=logger.name,
                fields={
                    "run_id": worker_request.run_id,
                    "run_type": run_type,
                    "error_code": exc.code,
                    "error_message": exc.message,
                },
            )
        )
        return response
    except Exception as exc:
        response = _execution_response(
            worker_request=worker_request,
            status="failed",
            result_summary={},
            artifact_paths=[],
            config_snapshot=config_snapshot,
            error_code="ui_run_worker_failed",
            error_message=str(exc),
            error_retryable=False,
            error_severity="error",
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="ui_run_execute_failed",
                module=logger.name,
                fields={
                    "run_id": worker_request.run_id,
                    "run_type": run_type,
                    "error_code": "ui_run_worker_failed",
                    "error_message": str(exc),
                },
            )
        )
        return response
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="ui_run_execute_complete",
            module=logger.name,
            fields={
                "run_id": worker_request.run_id,
                "run_type": run_type,
                "status": response.status,
                "artifact_count": len(response.artifact_paths),
                "result_summary": response.result_summary,
            },
        )
    )
    return response


def execute_ui_run(
    worker_request: UiRunWorkerRequest, ctx: RunContext
) -> UiRunExecutionResponse:
    """Run a validated UI action through the canonical supervisor dispatcher."""
    try:
        _validate_ui_run_payload(
            run_type=worker_request.run_type,
            payload=worker_request.request_payload,
        )
    except AppError:
        # Preserve the existing typed payload response and avoid creating a
        # control-plane observation for a request that was never executable.
        return _execute_ui_run_action(worker_request, ctx)

    app_settings = load_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )
    control_payload = worker_request.request_payload.get("workflow_control")
    control = control_payload if isinstance(control_payload, dict) else {}
    workflow_name = str(control.get("workflow") or worker_request.run_type).strip()
    health_gate = workflow_control.evaluate_run_health_gate(
        workflow_control.RunHealthGateInput(
            schema_version="1.0",
            workflow=workflow_name,
            scorecard={"run_id": str(worker_request.run_id), "warnings": []},
        ),
        ctx=ctx,
    )
    plan = workflow_control.plan_autonomous_run(
        workflow_control.AutonomousRunSupervisorInput(
            schema_version="1.0",
            workflow=workflow_name,
            run_id=str(worker_request.run_id),
            current_state="ready",
            latest_safe_checkpoint="",
            idempotency_scope="ui_run",
            idempotency_key=f"ui_run:{worker_request.run_id}",
            preflight_passed=str(control.get("status") or "resolved") != "blocked",
            validation_status="pass",
            health_gate=health_gate,
            blockers=list(control.get("blockers") or []),
            publish_allowed=worker_request.run_type in {"publish", "publish_wp"},
        ),
        ctx=ctx,
    )
    response_holder: dict[str, UiRunExecutionResponse] = {}

    def _run_action(_plan, action_ctx: RunContext) -> str:
        response = _execute_ui_run_action(worker_request, action_ctx)
        response_holder["response"] = response
        if response.status != "succeeded":
            raise AppError(
                code=response.error_code or "ui_run_execution_failed",
                message=response.error_message or "UI run execution failed",
                retryable=response.error_retryable,
                severity=response.error_severity,
            )
        return response.status

    action_handlers = {
        action: _run_action
        for action in {"start", "resume", "retry", "repair", "publish"}
    }
    if plan.selected_action not in action_handlers:
        response = _execution_response(
            worker_request=worker_request,
            status="failed",
            result_summary={"supervisor_action": plan.selected_action},
            artifact_paths=[],
            config_snapshot={
                "run_type": worker_request.run_type,
                "workflow": workflow_name,
                "supervisor_blockers": list(plan.blockers),
            },
            error_code=f"ui_run_supervisor_{plan.selected_action}",
            error_message="Workflow supervisor prevented UI run execution",
            error_retryable=False,
            error_severity="error",
        )
        response_holder["response"] = response
        action_handlers[plan.selected_action] = lambda _plan, _ctx: "blocked"
    execution = workflow_control.dispatch_autonomous_run(
        plan,
        state_db=app_settings.state_db,
        action_handlers=action_handlers,
        ctx=ctx,
    )
    if execution.status == "failed":
        return response_holder.get(
            "response",
            _execution_response(
                worker_request=worker_request,
                status="failed",
                result_summary={"supervisor_action": plan.selected_action},
                artifact_paths=[],
                config_snapshot={
                    "run_type": worker_request.run_type,
                    "workflow": workflow_name,
                },
                error_code=execution.error_code or "ui_run_supervisor_failed",
                error_message="Workflow supervisor dispatch failed",
                error_retryable=False,
                error_severity="error",
            ),
        )
    response = response_holder.get("response")
    if response is not None:
        return response
    return _execution_response(
        worker_request=worker_request,
        status="failed",
        result_summary={"supervisor_action": plan.selected_action},
        artifact_paths=[],
        config_snapshot={
            "run_type": worker_request.run_type,
            "workflow": workflow_name,
        },
        error_code="ui_run_supervisor_response_missing",
        error_message="Workflow supervisor completed without a UI run response",
        error_retryable=False,
        error_severity="error",
    )


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
