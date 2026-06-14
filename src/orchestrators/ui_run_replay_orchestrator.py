from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId
from src.contracts.ui_run_control import UiRunRecordGetRequest, UiRunWorkerRequest
from src.contracts.ui_run_replay import (
    UiRunArtifactFingerprintRequest,
    UiRunExecutionResponse,
    UiRunReplayDelta,
    UiRunReplayReport,
    UiRunReplayReportWriteRequest,
    UiRunReplayRequest,
    UiRunReplayResponse,
    UiRunReplayReadRequest,
    UiRunWorkspaceFingerprintRequest,
)
from src.orchestrators.ui_run_execution_orchestrator import (
    PROMPT_TREE_ROOT,
    SOURCE_TREE_ROOT,
    execute_ui_run,
    resolve_ui_run_config_snapshot,
)
from src.services.run_registry_service import get_ui_run_record
from src.services.ui_run_replay_service import (
    fingerprint_ui_run_artifacts,
    fingerprint_ui_run_workspace,
    read_ui_run_replay_manifest,
    write_ui_run_replay_report,
)
from src.utils.cache_utils import sha256_json
from src.utils.clock import utc_now_iso as _utc_now
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.ui_run_replay_orchestrator")


def _delta(field_name: str, original_value: Any, replay_value: Any) -> UiRunReplayDelta:
    return UiRunReplayDelta(
        schema_version="1.0",
        field_name=field_name,
        matches=original_value == replay_value,
        original_value=original_value,
        replay_value=replay_value,
    )


def _artifact_payload(items: list[Any]) -> list[dict[str, Any]]:
    return [asdict(item) for item in items]


def _build_report(
    *,
    run_id: str,
    replay_status: str,
    source_fingerprint_match: bool,
    prompt_fingerprint_match: bool,
    config_fingerprint_match: bool,
    deltas: list[UiRunReplayDelta],
) -> UiRunReplayReport:
    return UiRunReplayReport(
        schema_version="1.0",
        run_id=RunId(run_id),
        replayed_at_utc=_utc_now(),
        replay_status=replay_status,
        source_fingerprint_match=source_fingerprint_match,
        prompt_fingerprint_match=prompt_fingerprint_match,
        config_fingerprint_match=config_fingerprint_match,
        deltas=deltas,
        matched=all(item.matches for item in deltas)
        and source_fingerprint_match
        and prompt_fingerprint_match
        and config_fingerprint_match,
    )


def _write_report(
    *,
    registry_path: str,
    run_id: str,
    report: UiRunReplayReport,
    ctx: RunContext,
) -> str:
    return write_ui_run_replay_report(
        UiRunReplayReportWriteRequest(
            schema_version="1.0",
            registry_path=registry_path,
            run_id=RunId(run_id),
            report=report,
        ),
        ctx,
    ).report_path


def replay_ui_run(request: UiRunReplayRequest, ctx: RunContext) -> UiRunReplayResponse:
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="ui_run_replay_start",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.run_id,
            },
        )
    )
    original_record = get_ui_run_record(
        UiRunRecordGetRequest(
            schema_version="1.0",
            registry_path=request.registry_path,
            run_id=request.run_id,
        ),
        ctx,
    ).record
    if original_record is None:
        raise AppError(
            code="ui_run_not_found",
            message=f"UI run not found: {request.run_id}",
            retryable=False,
            context={"registry_path": request.registry_path, "run_id": request.run_id},
        )
    manifest_response = read_ui_run_replay_manifest(
        UiRunReplayReadRequest(
            schema_version="1.0",
            registry_path=request.registry_path,
            run_id=request.run_id,
        ),
        ctx,
    )
    worker_request = UiRunWorkerRequest(
        schema_version="1.0",
        registry_path=request.registry_path,
        run_id=original_record.run_id,
        run_type=manifest_response.manifest.run_type,
        request_payload=manifest_response.manifest.request_payload,
    )
    current_config_snapshot = resolve_ui_run_config_snapshot(worker_request, ctx)
    current_config_fingerprint = sha256_json(current_config_snapshot)
    workspace = fingerprint_ui_run_workspace(
        UiRunWorkspaceFingerprintRequest(
            schema_version="1.0",
            run_id=request.run_id,
            source_tree_root=manifest_response.manifest.source_tree_root
            or str(SOURCE_TREE_ROOT),
            prompt_tree_root=manifest_response.manifest.prompt_tree_root
            or str(PROMPT_TREE_ROOT),
        ),
        ctx,
    )
    source_match = (
        manifest_response.manifest.source_tree_fingerprint
        == workspace.source_tree_fingerprint
    )
    prompt_match = (
        manifest_response.manifest.prompt_tree_fingerprint
        == workspace.prompt_tree_fingerprint
    )
    config_match = (
        manifest_response.manifest.config_fingerprint == current_config_fingerprint
    )
    if not source_match or not prompt_match or not config_match:
        deltas = [
            _delta(
                "source_tree_fingerprint",
                manifest_response.manifest.source_tree_fingerprint,
                workspace.source_tree_fingerprint,
            ),
            _delta(
                "prompt_tree_fingerprint",
                manifest_response.manifest.prompt_tree_fingerprint,
                workspace.prompt_tree_fingerprint,
            ),
            _delta(
                "config_fingerprint",
                manifest_response.manifest.config_fingerprint,
                current_config_fingerprint,
            ),
        ]
        report = _build_report(
            run_id=request.run_id,
            replay_status="blocked_drift",
            source_fingerprint_match=source_match,
            prompt_fingerprint_match=prompt_match,
            config_fingerprint_match=config_match,
            deltas=deltas,
        )
        report_path = _write_report(
            registry_path=request.registry_path,
            run_id=request.run_id,
            report=report,
            ctx=ctx,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="ui_run_replay_drift_detected",
                module=logger.name,
                fields={
                    "run_id": request.run_id,
                    "source_fingerprint_match": source_match,
                    "prompt_fingerprint_match": prompt_match,
                    "config_fingerprint_match": config_match,
                    "report_path": report_path,
                },
            )
        )
        return UiRunReplayResponse(
            schema_version="1.0",
            original_record=original_record,
            manifest_path=manifest_response.manifest_path,
            report_path=report_path,
            report=report,
        )
    execution: UiRunExecutionResponse = execute_ui_run(worker_request, ctx)
    replay_artifacts = fingerprint_ui_run_artifacts(
        UiRunArtifactFingerprintRequest(
            schema_version="1.0",
            run_id=request.run_id,
            artifact_paths=execution.artifact_paths,
        ),
        ctx,
    )
    deltas = [
        _delta("status", manifest_response.manifest.status, execution.status),
        _delta(
            "error_code", manifest_response.manifest.error_code, execution.error_code
        ),
        _delta(
            "error_message",
            manifest_response.manifest.error_message,
            execution.error_message,
        ),
        _delta(
            "result_summary",
            manifest_response.manifest.result_summary,
            execution.result_summary,
        ),
        _delta(
            "artifact_fingerprints",
            _artifact_payload(manifest_response.manifest.artifact_fingerprints),
            _artifact_payload(replay_artifacts.artifact_fingerprints),
        ),
    ]
    report = _build_report(
        run_id=request.run_id,
        replay_status=execution.status,
        source_fingerprint_match=source_match,
        prompt_fingerprint_match=prompt_match,
        config_fingerprint_match=config_match,
        deltas=deltas,
    )
    report_path = _write_report(
        registry_path=request.registry_path,
        run_id=request.run_id,
        report=report,
        ctx=ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="ui_run_replay_complete",
            module=logger.name,
            fields={
                "run_id": request.run_id,
                "report_path": report_path,
                "replay_status": report.replay_status,
                "matched": report.matched,
                "delta_count": len(report.deltas),
            },
        )
    )
    return UiRunReplayResponse(
        schema_version="1.0",
        original_record=original_record,
        manifest_path=manifest_response.manifest_path,
        report_path=report_path,
        report=report,
    )
