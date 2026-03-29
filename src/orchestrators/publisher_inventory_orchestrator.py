from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from src.contracts.drive import (
    DriveDownloadRequest,
    DriveFile,
    DriveFolderFileListRequest,
    DriveFolderFileListResponse,
    DriveUploadBytesRequest,
    DriveUploadBytesResponse,
)
from src.contracts.publisher_inventory import (
    PublisherInventoryBuildRequest,
    PublisherInventoryBuildResponse,
    PublisherInventoryDiscoveryRequest,
    PublisherInventoryDiscoveryResult,
    PublisherInventoryServiceRequest,
    PublisherInventoryServiceResponse,
    PublisherInventorySnapshot,
)
from src.contracts.report_store import (
    PublisherInventoryStateGetRequest,
    PublisherInventoryStateRecordRequest,
    PublisherInventoryStateResponse,
)
from src.contracts.run_context import RunContext
from src.generators.publisher_inventory_generator import (
    build_publisher_inventory_snapshot,
    parse_publisher_inventory_snapshot,
)
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.services.drive_service import download_pdf, list_files_in_folder, upload_bytes
from src.services.publisher_inventory_service import discover_publisher_inventory
from src.services.report_store_service import (
    get_publisher_inventory_state,
    record_publisher_inventory_state,
)
from src.utils.drive_utils import extract_drive_folder_id
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.publisher_inventory_orchestrator")

_SNAPSHOT_PREFIX = "publisher_inventory_snapshot__"


@dataclass(frozen=True)
class PublisherInventoryDependencies:
    discover_publisher_inventory: Callable[
        [PublisherInventoryServiceRequest, RunContext],
        PublisherInventoryServiceResponse,
    ]
    build_publisher_inventory_snapshot: Callable[
        [PublisherInventoryBuildRequest, RunContext],
        PublisherInventoryBuildResponse,
    ]
    parse_publisher_inventory_snapshot: Callable[
        [str, str, RunContext],
        PublisherInventorySnapshot,
    ]
    get_publisher_inventory_state: Callable[
        [PublisherInventoryStateGetRequest, RunContext],
        Optional[PublisherInventoryStateResponse],
    ]
    record_publisher_inventory_state: Callable[
        [PublisherInventoryStateRecordRequest, RunContext],
        None,
    ]
    list_files_in_folder: Callable[
        [DriveFolderFileListRequest, RunContext],
        DriveFolderFileListResponse,
    ]
    download_pdf: Callable[[DriveDownloadRequest, RunContext], object]
    upload_bytes: Callable[[DriveUploadBytesRequest, RunContext], DriveUploadBytesResponse]

    @classmethod
    def default(cls) -> "PublisherInventoryDependencies":
        return cls(
            discover_publisher_inventory=discover_publisher_inventory,
            build_publisher_inventory_snapshot=build_publisher_inventory_snapshot,
            parse_publisher_inventory_snapshot=lambda snapshot_json, source, ctx: (
                parse_publisher_inventory_snapshot(snapshot_json, source=source, ctx=ctx)
            ),
            get_publisher_inventory_state=get_publisher_inventory_state,
            record_publisher_inventory_state=record_publisher_inventory_state,
            list_files_in_folder=list_files_in_folder,
            download_pdf=download_pdf,
            upload_bytes=upload_bytes,
        )


def run_publisher_inventory_discovery(
    request: PublisherInventoryDiscoveryRequest,
    *,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies | None = None,
) -> PublisherInventoryDiscoveryResult:
    deps = dependencies or PublisherInventoryDependencies.default()
    normalized_url = normalize_url(request.insights_url)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_start",
            module=logger.name,
            fields={
                "insights_url": request.insights_url,
                "normalized_url": normalized_url,
                "reports_db": request.reports_db,
            },
        )
    )
    publisher_state = deps.get_publisher_inventory_state(
        PublisherInventoryStateGetRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            normalized_url=normalized_url,
        ),
        ctx,
    )
    if publisher_state is None:
        raise AppError(
            code="publisher_inventory_publisher_not_found",
            message="Publisher insights URL was not found in the reports database",
            retryable=False,
            severity="error",
            context={"normalized_url": normalized_url},
        )
    folder_id = extract_drive_folder_id(publisher_state.google_folder or "")
    if not folder_id:
        raise AppError(
            code="publisher_inventory_google_folder_missing",
            message="Publisher discovery requires an existing publisher Drive folder",
            retryable=False,
            severity="error",
            context={
                "publisher_name": publisher_state.publisher_name,
                "normalized_url": normalized_url,
            },
        )
    previous_snapshot, previous_snapshot_file_id, previous_snapshot_file_name, previous_snapshot_sha256 = _load_previous_snapshot(
        publisher_state=publisher_state,
        folder_id=folder_id,
        settings=request.settings,
        ctx=ctx,
        dependencies=deps,
    )
    policy = RetryPolicy(
        retries=request.settings.retry_retries,
        base_delay_seconds=request.settings.retry_base_delay_seconds,
        backoff_step_seconds=request.settings.retry_backoff_step_seconds,
        jitter_seconds=request.settings.retry_jitter_seconds,
    )
    discovery_result: PublisherInventoryServiceResponse | None = None
    if publisher_state.inventory_route_summary:
        try:
            discovery_result = _run_discovery_attempt(
                request=request,
                ctx=ctx,
                policy=policy,
                dependencies=deps,
                route_hint=publisher_state.inventory_route_summary,
                route_kind_hint=publisher_state.inventory_route_kind,
                step_name="publisher_inventory_discovery_with_memory_route",
            )
        except Exception as exc:
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_memory_route_failed",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "route_kind": publisher_state.inventory_route_kind or "",
                        "error": str(exc),
                    },
                )
            )
    if discovery_result is None:
        discovery_result = _run_discovery_attempt(
            request=request,
            ctx=ctx,
            policy=policy,
            dependencies=deps,
            route_hint=None,
            route_kind_hint=None,
            step_name="publisher_inventory_discovery",
        )

    build_response = deps.build_publisher_inventory_snapshot(
        PublisherInventoryBuildRequest(
            schema_version="1.0",
            publisher_name=publisher_state.publisher_name,
            insights_url=publisher_state.insights_url,
            normalized_insights_url=normalized_url,
            discovered_at_utc=_utc_now_iso(),
            route_kind=discovery_result.route_kind,
            route_summary=discovery_result.route_summary,
            final_page_url=discovery_result.final_page_url,
            pages=discovery_result.pages,
            candidates=discovery_result.candidates,
            previous_snapshot=previous_snapshot,
        ),
        ctx,
    )
    snapshot_changed = build_response.snapshot_sha256 != (previous_snapshot_sha256 or "")
    snapshot_drive_file_id = previous_snapshot_file_id
    snapshot_drive_file_name = previous_snapshot_file_name
    snapshot_sha256 = previous_snapshot_sha256
    if snapshot_changed:
        upload_response = run_with_retry(
            step_name="publisher_inventory_snapshot_upload",
            operation=lambda: deps.upload_bytes(
                DriveUploadBytesRequest(
                    schema_version="1.0",
                    folder_id=folder_id,
                    service_account_path=request.settings.google_sa_path,
                    file_name=_snapshot_file_name(),
                    content=build_response.snapshot_json.encode("utf-8"),
                    mime_type="application/json",
                    supports_all_drives=True,
                ),
                ctx,
            ),
            ctx=ctx,
            logger=logger,
            module_name=logger.name,
            policy=policy,
            retry_event="publisher_inventory_snapshot_upload_retry",
            failure_event="publisher_inventory_snapshot_upload_failed",
        )
        snapshot_drive_file_id = upload_response.file.file_id
        snapshot_drive_file_name = upload_response.file.name
        snapshot_sha256 = build_response.snapshot_sha256
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_snapshot_uploaded",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "snapshot_drive_file_id": snapshot_drive_file_id,
                    "snapshot_drive_file_name": snapshot_drive_file_name or "",
                    "snapshot_sha256": snapshot_sha256,
                },
            )
        )
    deps.record_publisher_inventory_state(
        PublisherInventoryStateRecordRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            normalized_url=normalized_url,
            source_url=publisher_state.insights_url,
            route_kind=discovery_result.route_kind,
            route_summary=discovery_result.route_summary,
            last_final_page_url=discovery_result.final_page_url,
            snapshot_drive_file_id=snapshot_drive_file_id,
            snapshot_drive_file_name=snapshot_drive_file_name,
            snapshot_sha256=snapshot_sha256 or build_response.snapshot_sha256,
        ),
        ctx,
    )
    response = PublisherInventoryDiscoveryResult(
        schema_version="1.0",
        publisher_name=publisher_state.publisher_name,
        insights_url=publisher_state.insights_url,
        normalized_insights_url=normalized_url,
        new_report_urls=build_response.new_items,
        current_report_count=build_response.current_report_count,
        previous_report_count=build_response.previous_report_count,
        used_memory_route=discovery_result.used_route_hint,
        snapshot_changed=snapshot_changed,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_complete",
            module=logger.name,
            fields={
                "publisher_name": response.publisher_name,
                "normalized_url": response.normalized_insights_url,
                "current_report_count": response.current_report_count,
                "previous_report_count": response.previous_report_count,
                "new_report_count": len(response.new_report_urls),
                "used_memory_route": response.used_memory_route,
                "snapshot_changed": response.snapshot_changed,
            },
        )
    )
    return response


def _run_discovery_attempt(
    *,
    request: PublisherInventoryDiscoveryRequest,
    ctx: RunContext,
    policy: RetryPolicy,
    dependencies: PublisherInventoryDependencies,
    route_hint: str | None,
    route_kind_hint: str | None,
    step_name: str,
) -> PublisherInventoryServiceResponse:
    return run_with_retry(
        step_name=step_name,
        operation=lambda: dependencies.discover_publisher_inventory(
            PublisherInventoryServiceRequest(
                schema_version="1.0",
                insights_url=request.insights_url,
                settings=request.settings,
                route_hint=route_hint,
                route_kind_hint=route_kind_hint,
            ),
            ctx,
        ),
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        policy=policy,
        retry_event="publisher_inventory_discovery_retry",
        failure_event="publisher_inventory_discovery_failed",
    )


def _load_previous_snapshot(
    *,
    publisher_state: PublisherInventoryStateResponse,
    folder_id: str,
    settings,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> tuple[PublisherInventorySnapshot | None, str | None, str | None, str | None]:
    file_id = publisher_state.inventory_snapshot_drive_file_id
    file_name = publisher_state.inventory_snapshot_drive_file_name
    snapshot_sha256 = publisher_state.inventory_snapshot_sha256
    if not file_id:
        listed = dependencies.list_files_in_folder(
            DriveFolderFileListRequest(
                schema_version="1.0",
                folder_id=folder_id,
                service_account_path=settings.google_sa_path,
                name_prefix=_SNAPSHOT_PREFIX,
                order_by="modifiedTime desc",
                limit=1,
                supports_all_drives=True,
                include_items_from_all_drives=True,
            ),
            ctx,
        )
        if listed.files:
            file_id = listed.files[0].file_id
            file_name = listed.files[0].name
    if not file_id:
        return None, None, None, None
    download_response = dependencies.download_pdf(
        DriveDownloadRequest(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id=file_id,
                name=file_name,
                modified_time=None,
                md5_checksum=None,
                mime_type="application/json",
            ),
            service_account_path=settings.google_sa_path,
        ),
        ctx,
    )
    snapshot_payload = download_response.content.decode("utf-8")
    if not snapshot_sha256:
        snapshot_sha256 = hashlib.sha256(snapshot_payload.encode("utf-8")).hexdigest()
    snapshot = dependencies.parse_publisher_inventory_snapshot(
        snapshot_payload,
        f"drive:{file_id}",
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_previous_snapshot_loaded",
            module=logger.name,
            fields={
                "publisher_name": publisher_state.publisher_name,
                "snapshot_drive_file_id": file_id,
                "snapshot_drive_file_name": file_name or "",
                "snapshot_sha256": snapshot_sha256 or "",
                "item_count": len(snapshot.items),
            },
        )
    )
    return snapshot, file_id, file_name, snapshot_sha256


def _snapshot_file_name() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{_SNAPSHOT_PREFIX}{timestamp}.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
