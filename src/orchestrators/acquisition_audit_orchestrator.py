from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.contracts.acquisition_audit import (
    AcquisitionAuditBatchRequest,
    AcquisitionAuditBatchResult,
    AcquisitionAuditCandidateResult,
    AcquisitionAuditPublisherSummary,
)
from src.contracts.browser_download import (
    ReportDownloadOrchestratorRequest,
    ReportDownloadOrchestratorResult,
)
from src.contracts.files import WriteBytesRequest, WriteBytesResponse
from src.contracts.publisher_inventory import (
    PublisherInventoryDiscoveryRequest,
    PublisherInventoryDiscoveryResult,
)
from src.contracts.report_store import (
    PublisherListItem,
    PublishersListRequest,
    PublishersListResponse,
)
from src.contracts.run_context import RunContext
from src.generators.acquisition_audit_generator import (
    build_acquisition_audit_candidate,
    build_acquisition_audit_publisher_summary,
    serialize_acquisition_audit_result,
)
from src.orchestrators.publisher_inventory_orchestrator import (
    run_publisher_inventory_discovery,
)
from src.orchestrators.report_download_orchestrator import run_report_download
from src.services.file_service import write_bytes
from src.services.report_store_service import list_publishers
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.acquisition_audit_orchestrator")


@dataclass(frozen=True)
class AcquisitionAuditDependencies:
    list_publishers: Callable[
        [PublishersListRequest, RunContext], PublishersListResponse
    ]
    run_publisher_inventory_discovery: Callable[
        [PublisherInventoryDiscoveryRequest, RunContext],
        PublisherInventoryDiscoveryResult,
    ]
    run_report_download: Callable[
        [ReportDownloadOrchestratorRequest, RunContext],
        ReportDownloadOrchestratorResult,
    ]
    write_bytes: Callable[[WriteBytesRequest, RunContext], WriteBytesResponse]

    @classmethod
    def default(cls) -> "AcquisitionAuditDependencies":
        return cls(
            list_publishers=list_publishers,
            run_publisher_inventory_discovery=lambda req, ctx: (
                run_publisher_inventory_discovery(
                    req,
                    ctx=ctx,
                )
            ),
            run_report_download=lambda req, ctx: run_report_download(req, ctx=ctx),
            write_bytes=write_bytes,
        )


def run_acquisition_audit(
    request: AcquisitionAuditBatchRequest,
    *,
    ctx: RunContext,
    dependencies: AcquisitionAuditDependencies | None = None,
) -> AcquisitionAuditBatchResult:
    deps = dependencies or AcquisitionAuditDependencies.default()
    generated_at_utc = _utc_now_iso()
    artifact_dir = _artifact_dir(request.output_dir, generated_at_utc)
    artifact_path = str(artifact_dir / "acquisition_audit.json")
    audit_reports_db = str(artifact_dir / "audit_report_download.sqlite")
    download_settings = replace(
        request.browser_download_settings,
        output_dir=str(artifact_dir / "downloads"),
        drive_upload_enabled=False,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="acquisition_audit_start",
            module=logger.name,
            fields={
                "reports_db": request.reports_db,
                "output_dir": request.output_dir,
                "artifact_path": artifact_path,
                "publisher_limit": request.publisher_limit,
                "candidate_limit_per_publisher": request.candidate_limit_per_publisher,
                "has_delivery_email": bool(request.delivery_email),
            },
        )
    )
    publisher_response = deps.list_publishers(
        PublishersListRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            limit=request.publisher_limit,
        ),
        ctx,
    )
    publisher_summaries: list[AcquisitionAuditPublisherSummary] = []
    candidate_results: list[AcquisitionAuditCandidateResult] = []
    for publisher in publisher_response.publishers:
        publisher_ctx = child_context(
            ctx, task_id=f"audit_{_safe_task_token(publisher.publisher_name)}"
        )
        publisher_candidate_results = _audit_publisher(
            publisher=publisher,
            request=request,
            download_settings=download_settings,
            audit_reports_db=audit_reports_db,
            dependencies=deps,
            publisher_summaries=publisher_summaries,
            ctx=publisher_ctx,
        )
        if publisher_candidate_results is not None:
            candidate_results.extend(publisher_candidate_results)
    result = AcquisitionAuditBatchResult(
        schema_version="1.0",
        generated_at_utc=generated_at_utc,
        output_path=artifact_path,
        publisher_count=len(publisher_summaries),
        candidate_count=len(candidate_results),
        publishers=publisher_summaries,
        candidates=candidate_results,
    )
    payload = serialize_acquisition_audit_result(result, ctx=ctx)
    deps.write_bytes(
        WriteBytesRequest(
            schema_version="1.0",
            path=artifact_path,
            content=payload.encode("utf-8"),
            make_parents=True,
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="acquisition_audit_complete",
            module=logger.name,
            fields={
                "artifact_path": result.output_path,
                "publisher_count": result.publisher_count,
                "candidate_count": result.candidate_count,
            },
        )
    )
    return result


def _audit_publisher(
    *,
    publisher: PublisherListItem,
    request: AcquisitionAuditBatchRequest,
    download_settings,
    audit_reports_db: str,
    dependencies: AcquisitionAuditDependencies,
    publisher_summaries: list[AcquisitionAuditPublisherSummary],
    ctx: RunContext,
):
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="acquisition_audit_publisher_start",
            module=logger.name,
            fields={
                "publisher_name": publisher.publisher_name,
                "insights_url": publisher.insights_url,
            },
        )
    )
    try:
        discovery_result = dependencies.run_publisher_inventory_discovery(
            PublisherInventoryDiscoveryRequest(
                schema_version="1.0",
                insights_url=publisher.insights_url,
                reports_db=request.reports_db,
                settings=request.publisher_inventory_settings,
            ),
            ctx,
        )
    except AppError as exc:
        summary = AcquisitionAuditPublisherSummary(
            schema_version="1.0",
            publisher_name=publisher.publisher_name,
            insights_url=publisher.insights_url,
            discovery_route_kind="failed",
            discovery_quality_band="error",
            recommended_discovery_route_kind="manual_review",
            recommended_publisher_flow="manual_review_required",
            recommendation_reason="Publisher discovery failed during the audit run.",
            current_candidate_count=0,
            downloaded_count=0,
            email_requested_count=0,
            email_required_count=0,
            failed_count=0,
            discovery_provenance_counts={},
            acquisition_route_counts={},
            acquisition_outcome_counts={},
            error_code=exc.code,
            error_message=exc.message,
        )
        publisher_summaries.append(summary)
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="acquisition_audit_publisher_discovery_failed",
                module=logger.name,
                fields={
                    "publisher_name": publisher.publisher_name,
                    "insights_url": publisher.insights_url,
                    "error_code": exc.code,
                    "error_message": exc.message,
                },
            )
        )
        return None

    limit = request.candidate_limit_per_publisher
    current_candidates = list(discovery_result.current_candidates)
    if limit is not None:
        current_candidates = current_candidates[:limit]
    publisher_candidate_results: list[AcquisitionAuditCandidateResult] = []
    for candidate in current_candidates:
        candidate_ctx = child_context(
            ctx,
            task_id=f"audit_{_safe_task_token(publisher.publisher_name)}_{_safe_task_token(candidate.title or candidate.canonical_url)}",
        )
        try:
            download_result = dependencies.run_report_download(
                ReportDownloadOrchestratorRequest(
                    schema_version="1.0",
                    url=candidate.canonical_url,
                    settings=download_settings,
                    state_db=download_settings.state_db,
                    reports_db=audit_reports_db,
                    delivery_email=request.delivery_email,
                    candidate_trace=candidate,
                    publisher_discovery_route_kind=discovery_result.run_quality_summary.route_kind,
                    publisher_recommended_discovery_route_kind=discovery_result.run_quality_summary.recommended_route_kind,
                ),
                candidate_ctx,
            )
            publisher_candidate_results.append(
                build_acquisition_audit_candidate(
                    publisher_name=publisher.publisher_name,
                    publisher_insights_url=publisher.insights_url,
                    publisher_discovery_route_kind=discovery_result.run_quality_summary.route_kind,
                    publisher_recommended_discovery_route_kind=discovery_result.run_quality_summary.recommended_route_kind,
                    candidate_trace=candidate,
                    acquisition_route_kind=download_result.route_kind,
                    acquisition_outcome=download_result.outcome,
                    acquisition_route_summary=download_result.route_summary,
                    acquisition_final_page_url=download_result.final_page_url,
                    encountered_form_fields=download_result.encountered_form_fields,
                    downloaded_file_path=download_result.downloaded_file_path,
                    error_code=None,
                    error_message=None,
                    ctx=candidate_ctx,
                )
            )
        except AppError as exc:
            publisher_candidate_results.append(
                build_acquisition_audit_candidate(
                    publisher_name=publisher.publisher_name,
                    publisher_insights_url=publisher.insights_url,
                    publisher_discovery_route_kind=discovery_result.run_quality_summary.route_kind,
                    publisher_recommended_discovery_route_kind=discovery_result.run_quality_summary.recommended_route_kind,
                    candidate_trace=candidate,
                    acquisition_route_kind=(
                        "failed_retryable" if exc.retryable else "failed_permanent"
                    ),
                    acquisition_outcome=(
                        "failed_retryable" if exc.retryable else "failed_permanent"
                    ),
                    acquisition_route_summary=None,
                    acquisition_final_page_url=None,
                    encountered_form_fields=[],
                    downloaded_file_path=None,
                    error_code=exc.code,
                    error_message=exc.message,
                    ctx=candidate_ctx,
                )
            )
    summary = build_acquisition_audit_publisher_summary(
        publisher_name=publisher.publisher_name,
        insights_url=publisher.insights_url,
        discovery_route_kind=discovery_result.run_quality_summary.route_kind,
        discovery_quality_band=discovery_result.run_quality_summary.quality_band,
        recommended_discovery_route_kind=discovery_result.run_quality_summary.recommended_route_kind,
        candidates=publisher_candidate_results,
        ctx=ctx,
    )
    publisher_summaries.append(summary)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="acquisition_audit_publisher_complete",
            module=logger.name,
            fields={
                "publisher_name": publisher.publisher_name,
                "candidate_count": len(publisher_candidate_results),
                "recommended_publisher_flow": summary.recommended_publisher_flow,
            },
        )
    )
    return publisher_candidate_results


def _artifact_dir(output_dir: str, generated_at_utc: str) -> Path:
    token = (
        generated_at_utc.replace("-", "")
        .replace(":", "")
        .replace("T", "__")
        .replace("Z", "")
    )
    return Path(output_dir) / "acquisition_audit" / token


def _safe_task_token(value: str) -> str:
    token = "".join(
        char.lower() if char.isalnum() else "_" for char in str(value or "").strip()
    )
    collapsed = "_".join(part for part in token.split("_") if part)
    return collapsed or "item"


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )
