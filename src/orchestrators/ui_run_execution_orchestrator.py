from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from src.contracts.acquisition_audit import AcquisitionAuditBatchRequest
from src.contracts.browser_download import ReportDownloadOrchestratorRequest
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.cover_images import CoverImageOrchestratorRequest
from src.contracts.publisher_inventory import PublisherInventoryDiscoveryRequest
from src.contracts.run_context import RunContext
from src.contracts.ui_run_control import UiRunWorkerRequest
from src.contracts.ui_run_replay import UiRunExecutionResponse
from src.orchestrators.acquisition_audit_orchestrator import run_acquisition_audit
from src.orchestrators.candidate_extraction_orchestrator import run_candidate_extraction
from src.orchestrators.cover_image_orchestrator import run_cover_image_generation
from src.orchestrators.ingest_orchestrator import run_ingest
from src.orchestrators.publish_orchestrator import run_publish
from src.orchestrators.publisher_inventory_orchestrator import (
    run_publisher_inventory_discovery,
)
from src.orchestrators.report_download_orchestrator import run_report_download
from src.services.config_service import (
    build_ingest_settings,
    load_browser_download_settings,
    load_publisher_inventory_settings,
    load_publish_settings,
    load_settings,
)
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.ui_run_execution_orchestrator")

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_TREE_ROOT = REPO_ROOT / "src"
PROMPT_TREE_ROOT = REPO_ROOT / "src" / "prompts"
SENSITIVE_KEY_TOKENS = ("api_key", "token", "password", "secret", "email")


def _sensitive_key(token: str) -> bool:
    lowered = str(token or "").strip().lower()
    return any(marker in lowered for marker in SENSITIVE_KEY_TOKENS)


def _stable_scalar_hash(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _sanitize_snapshot(value: Any, *, parent_hint: str = "") -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, dict):
        entity_key = str(value.get("key") or "").strip().lower()
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_name = str(key)
            should_hash = _sensitive_key(key_name) or (
                key_name == "value" and _sensitive_key(entity_key or parent_hint)
            )
            if should_hash:
                if item in (None, "", [], {}, ()):
                    sanitized[key_name] = item
                else:
                    sanitized[key_name] = f"redacted_sha256:{_stable_scalar_hash(item)}"
                continue
            sanitized[key_name] = _sanitize_snapshot(
                item,
                parent_hint=entity_key or key_name,
            )
        return sanitized
    if isinstance(value, list):
        return [_sanitize_snapshot(item, parent_hint=parent_hint) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_snapshot(item, parent_hint=parent_hint) for item in value]
    return value


def _execution_response(
    *,
    worker_request: UiRunWorkerRequest,
    status: str,
    result_summary: dict[str, Any],
    artifact_paths: list[str],
    config_snapshot: dict[str, Any],
    error_code: str = "",
    error_message: str = "",
) -> UiRunExecutionResponse:
    return UiRunExecutionResponse(
        schema_version="1.0",
        run_id=worker_request.run_id,
        run_type=worker_request.run_type,
        status=status,
        result_summary=result_summary,
        artifact_paths=artifact_paths,
        config_snapshot=config_snapshot,
        config_fingerprint=sha256_json(config_snapshot),
        error_code=error_code,
        error_message=error_message,
    )


def resolve_ui_run_config_snapshot(
    worker_request: UiRunWorkerRequest, ctx: RunContext
) -> dict[str, Any]:
    payload = worker_request.request_payload
    run_type = worker_request.run_type
    if run_type in {"ingest", "candidate_extraction"}:
        app_settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
        settings = build_ingest_settings(
            IngestSettingsBuildRequest(schema_version="1.0", app_settings=app_settings),
            ctx,
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(settings)}
    if run_type == "cover_images":
        settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
        return {"run_type": run_type, "settings": _sanitize_snapshot(settings)}
    if run_type == "publish":
        settings = load_publish_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(settings)}
    if run_type == "publisher_discovery":
        settings = load_publisher_inventory_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            ctx,
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(settings)}
    if run_type == "report_download":
        settings = load_browser_download_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            ctx,
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(settings)}
    if run_type == "acquisition_audit":
        app_settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
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
    raise AppError(
        code="ui_run_type_unknown",
        message=f"Unknown UI run type: {run_type}",
        retryable=False,
        context={"run_type": run_type, "payload_keys": sorted(payload.keys())},
    )


def execute_ui_run(
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
        if run_type == "ingest":
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            settings = build_ingest_settings(
                IngestSettingsBuildRequest(
                    schema_version="1.0", app_settings=app_settings
                ),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(settings),
            }
            outcomes = run_ingest(
                settings,
                folder_id=str(payload.get("folder_id") or "").strip() or None,
                limit=int(payload["limit"]) if payload.get("limit") is not None else None,
                ctx=ctx,
            )
            processed_count = len([item for item in outcomes if item.status == "processed"])
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "processed_count": processed_count,
                    "total_count": len(outcomes),
                },
                artifact_paths=[item.html_path for item in outcomes if item.html_path],
                config_snapshot=config_snapshot,
            )
        elif run_type == "candidate_extraction":
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            settings = build_ingest_settings(
                IngestSettingsBuildRequest(
                    schema_version="1.0", app_settings=app_settings
                ),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(settings),
            }
            outcomes = run_candidate_extraction(
                settings,
                folder_id=str(payload.get("folder_id") or "").strip() or None,
                limit=int(payload["limit"]) if payload.get("limit") is not None else None,
                file_id=str(payload.get("file_id") or "").strip() or None,
                pdf_path=str(payload.get("pdf_path") or "").strip() or None,
                report_id=str(payload.get("report_id") or "").strip() or None,
                ctx=ctx,
            )
            artifact_paths: list[str] = []
            for outcome in outcomes:
                if outcome.candidates_path:
                    artifact_paths.append(outcome.candidates_path)
                artifact_paths.extend(outcome.crop_paths[:5])
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "total_count": len(outcomes),
                    "candidate_count": sum(item.candidate_count for item in outcomes),
                    "chart_count": sum(item.chart_count for item in outcomes),
                    "table_count": sum(item.table_count for item in outcomes),
                },
                artifact_paths=artifact_paths,
                config_snapshot=config_snapshot,
            )
        elif run_type == "cover_images":
            settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(settings),
            }
            outcomes = run_cover_image_generation(
                CoverImageOrchestratorRequest(
                    schema_version="1.0",
                    reports_db=settings.reports_db,
                    output_dir=settings.output_dir,
                    style_config_path=str(payload.get("style_config_path") or "").strip(),
                    limit=int(payload["limit"])
                    if payload.get("limit") is not None
                    else None,
                    file_id=str(payload.get("file_id") or "").strip() or None,
                ),
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "total_count": len(outcomes),
                    "generated_count": len(
                        [item for item in outcomes if item.status == "generated"]
                    ),
                },
                artifact_paths=[item.output_path for item in outcomes if item.output_path],
                config_snapshot=config_snapshot,
            )
        elif run_type == "publish":
            settings = load_publish_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(settings),
            }
            outcomes = run_publish(
                settings,
                limit=int(payload["limit"]) if payload.get("limit") is not None else None,
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "total_count": len(outcomes),
                    "published_count": len(
                        [item for item in outcomes if item.status == "published"]
                    ),
                },
                artifact_paths=[item.html_path for item in outcomes if item.html_path],
                config_snapshot=config_snapshot,
            )
        elif run_type == "publisher_discovery":
            settings = load_publisher_inventory_settings(
                ConfigLoadRequest(schema_version="1.0", path=""),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(settings),
            }
            result = run_publisher_inventory_discovery(
                PublisherInventoryDiscoveryRequest(
                    schema_version="1.0",
                    insights_url=str(payload.get("insights_url") or "").strip(),
                    reports_db=settings.reports_db,
                    settings=settings,
                ),
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "publisher_name": result.publisher_name,
                    "current_report_count": result.current_report_count,
                    "previous_report_count": result.previous_report_count,
                    "new_report_count": len(result.new_report_urls),
                    "quality_band": result.run_quality_summary.quality_band,
                    "recommended_route_kind": result.run_quality_summary.recommended_route_kind,
                },
                artifact_paths=[],
                config_snapshot=config_snapshot,
            )
        elif run_type == "report_download":
            settings = load_browser_download_settings(
                ConfigLoadRequest(schema_version="1.0", path=""),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(settings),
            }
            result = run_report_download(
                ReportDownloadOrchestratorRequest(
                    schema_version="1.0",
                    url=str(payload.get("url") or "").strip(),
                    settings=settings,
                    state_db=settings.state_db,
                    reports_db=settings.reports_db,
                    delivery_email=str(payload.get("delivery_email") or "").strip()
                    or None,
                    publisher_insights_url=str(
                        payload.get("publisher_insights_url") or ""
                    ).strip()
                    or None,
                    publisher_google_folder=str(
                        payload.get("publisher_google_folder") or ""
                    ).strip()
                    or None,
                ),
                ctx=ctx,
            )
            artifact_paths = [
                path
                for path in [result.downloaded_file_path, result.onsite_capture_path]
                if path
            ]
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "route_kind": result.route_kind,
                    "route_family": result.route_family,
                    "outcome": result.outcome,
                    "final_page_url": result.final_page_url,
                    "downloaded_file_name": result.downloaded_file_name or "",
                },
                artifact_paths=artifact_paths,
                config_snapshot=config_snapshot,
            )
        elif run_type == "acquisition_audit":
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
            result = run_acquisition_audit(
                AcquisitionAuditBatchRequest(
                    schema_version="1.0",
                    reports_db=app_settings.reports_db,
                    publisher_inventory_settings=inventory_settings,
                    browser_download_settings=browser_settings,
                    output_dir=app_settings.output_dir,
                    delivery_email=str(payload.get("delivery_email") or "").strip()
                    or None,
                    publisher_limit=int(payload["publisher_limit"])
                    if payload.get("publisher_limit") is not None
                    else None,
                    candidate_limit_per_publisher=int(
                        payload["candidate_limit_per_publisher"]
                    )
                    if payload.get("candidate_limit_per_publisher") is not None
                    else None,
                ),
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "publisher_count": result.publisher_count,
                    "candidate_count": result.candidate_count,
                    "output_path": result.output_path,
                },
                artifact_paths=[result.output_path],
                config_snapshot=config_snapshot,
            )
        else:
            raise AppError(
                code="ui_run_type_unknown",
                message=f"Unknown UI run type: {run_type}",
                retryable=False,
                context={"run_type": run_type},
            )
    except AppError as exc:
        response = _execution_response(
            worker_request=worker_request,
            status="failed",
            result_summary={},
            artifact_paths=[],
            config_snapshot=config_snapshot,
            error_code=exc.code,
            error_message=exc.message,
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
