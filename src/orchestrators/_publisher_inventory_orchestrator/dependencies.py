from __future__ import annotations

"""Dependency wiring for publisher-inventory orchestration.

This module owns the orchestrator dependency contract and default bindings to
services and generators. It does not execute the workflow.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from src.contracts.drive import (
    DriveDownloadRequest,
    DriveDownloadResponse,
    DriveFolderFileListRequest,
    DriveFolderFileListResponse,
    DriveUploadBytesRequest,
    DriveUploadBytesResponse,
)
from src.contracts.publisher_inventory import (
    PublisherInventoryBuildRequest,
    PublisherInventoryBuildResponse,
    PublisherInventoryCandidateQualityRequest,
    PublisherInventoryCandidateQualityResponse,
    PublisherInventoryCandidateScreeningRequest,
    PublisherInventoryCandidateScreeningResponse,
    PublisherInventoryCoverageValidationRequest,
    PublisherInventoryCoverageValidationResponse,
    PublisherInventoryRecoveryRecord,
    PublisherInventoryRunQualityEvaluationRequest,
    PublisherInventoryRunQualitySummary,
    PublisherInventoryServiceRequest,
    PublisherInventoryServiceResponse,
    PublisherInventorySnapshot,
)
from src.contracts.report_store import (
    PublisherInventoryRecoveryCacheGetRequest,
    PublisherInventoryRecoveryCacheRecordRequest,
    PublisherInventoryRunQualityRecordRequest,
    PublisherInventoryStateGetRequest,
    PublisherInventoryStateRecordRequest,
    PublisherInventoryStateResponse,
    PublisherInventoryTestStatusRecordRequest,
    PublisherResourceRankingRequest,
    PublisherResourceRankingResponse,
    ReportSourceDiscoveryRecordRequest,
    ReportSourceDiscoveryRecordResponse,
    ReportSourceQualityHistoryRequest,
    ReportSourceQualityHistoryResponse,
)
from src.contracts.run_context import RunContext
from src.generators.publisher_inventory_candidate_quality_generator import (
    qualify_publisher_inventory_candidates,
)
from src.generators.publisher_inventory_candidate_screening_generator import (
    screen_publisher_inventory_candidates,
)
from src.generators.publisher_inventory_coverage_generator import (
    validate_publisher_inventory_coverage,
)
from src.generators.publisher_inventory_generator import (
    build_publisher_inventory_snapshot,
    parse_publisher_inventory_snapshot,
)
from src.generators.publisher_inventory_run_quality_generator import (
    evaluate_publisher_inventory_run_quality,
)
from src.generators.report_value_generator import rank_publisher_resources
from src.services.drive_service import download_pdf, list_files_in_folder, upload_bytes
from src.services.publisher_inventory_service import discover_publisher_inventory
from src.services.report_store_service import (
    get_publisher_inventory_recovery_cache_record,
    get_publisher_inventory_state,
    list_report_source_quality_history,
    record_discovered_report_source,
    record_publisher_inventory_recovery_cache_record,
    record_publisher_inventory_run_quality,
    record_publisher_inventory_state,
    record_publisher_inventory_test_status,
)


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
    validate_publisher_inventory_coverage: Callable[
        [PublisherInventoryCoverageValidationRequest, RunContext],
        PublisherInventoryCoverageValidationResponse,
    ]
    evaluate_publisher_inventory_run_quality: Callable[
        [PublisherInventoryRunQualityEvaluationRequest, RunContext],
        PublisherInventoryRunQualitySummary,
    ]
    parse_publisher_inventory_snapshot: Callable[
        [str, str, RunContext],
        PublisherInventorySnapshot,
    ]
    screen_publisher_inventory_candidates: Callable[
        [PublisherInventoryCandidateScreeningRequest, RunContext],
        PublisherInventoryCandidateScreeningResponse,
    ]
    qualify_publisher_inventory_candidates: Callable[
        [PublisherInventoryCandidateQualityRequest, RunContext],
        PublisherInventoryCandidateQualityResponse,
    ]
    get_publisher_inventory_state: Callable[
        [PublisherInventoryStateGetRequest, RunContext],
        Optional[PublisherInventoryStateResponse],
    ]
    get_publisher_inventory_recovery_cache_record: Callable[
        [PublisherInventoryRecoveryCacheGetRequest, RunContext],
        Optional[PublisherInventoryRecoveryRecord],
    ]
    record_publisher_inventory_run_quality: Callable[
        [PublisherInventoryRunQualityRecordRequest, RunContext],
        None,
    ]
    record_publisher_inventory_recovery_cache_record: Callable[
        [PublisherInventoryRecoveryCacheRecordRequest, RunContext],
        None,
    ]
    record_publisher_inventory_state: Callable[
        [PublisherInventoryStateRecordRequest, RunContext],
        None,
    ]
    record_publisher_inventory_test_status: Callable[
        [PublisherInventoryTestStatusRecordRequest, RunContext],
        None,
    ]
    record_discovered_report_source: Callable[
        [ReportSourceDiscoveryRecordRequest, RunContext],
        ReportSourceDiscoveryRecordResponse,
    ]
    list_report_source_quality_history: Callable[
        [ReportSourceQualityHistoryRequest, RunContext],
        ReportSourceQualityHistoryResponse,
    ]
    rank_publisher_resources: Callable[
        [PublisherResourceRankingRequest, RunContext],
        PublisherResourceRankingResponse,
    ]
    list_files_in_folder: Callable[
        [DriveFolderFileListRequest, RunContext],
        DriveFolderFileListResponse,
    ]
    download_pdf: Callable[[DriveDownloadRequest, RunContext], DriveDownloadResponse]
    upload_bytes: Callable[
        [DriveUploadBytesRequest, RunContext], DriveUploadBytesResponse
    ]

    @classmethod
    def default(cls) -> "PublisherInventoryDependencies":
        return cls(
            discover_publisher_inventory=discover_publisher_inventory,
            build_publisher_inventory_snapshot=build_publisher_inventory_snapshot,
            validate_publisher_inventory_coverage=validate_publisher_inventory_coverage,
            evaluate_publisher_inventory_run_quality=evaluate_publisher_inventory_run_quality,
            parse_publisher_inventory_snapshot=lambda snapshot_json, source, ctx: (
                parse_publisher_inventory_snapshot(
                    snapshot_json, source=source, ctx=ctx
                )
            ),
            screen_publisher_inventory_candidates=screen_publisher_inventory_candidates,
            qualify_publisher_inventory_candidates=qualify_publisher_inventory_candidates,
            get_publisher_inventory_state=get_publisher_inventory_state,
            get_publisher_inventory_recovery_cache_record=get_publisher_inventory_recovery_cache_record,
            record_publisher_inventory_run_quality=record_publisher_inventory_run_quality,
            record_publisher_inventory_recovery_cache_record=record_publisher_inventory_recovery_cache_record,
            record_publisher_inventory_state=record_publisher_inventory_state,
            record_publisher_inventory_test_status=record_publisher_inventory_test_status,
            record_discovered_report_source=record_discovered_report_source,
            list_report_source_quality_history=list_report_source_quality_history,
            rank_publisher_resources=rank_publisher_resources,
            list_files_in_folder=list_files_in_folder,
            download_pdf=download_pdf,
            upload_bytes=upload_bytes,
        )


__all__ = [name for name in globals() if not name.startswith("__")]
