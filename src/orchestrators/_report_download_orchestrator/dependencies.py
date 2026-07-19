from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from src.contracts.browser_download import (
    BrowserDownloadIdentityFieldUpsertRequest,
    BrowserDownloadIdentityFieldUpsertResponse,
    BrowserDownloadRequiredSelectOverrideRequest,
    BrowserDownloadRequiredSelectOverrideResponse,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    BrowserRoutePlaybookPromotionResponse,
    BrowserRoutePrivateApiAutoPromotionDetectionRequest,
    BrowserRoutePrivateApiAutoPromotionDetectionResponse,
)
from src.contracts.drive import (
    DriveFolderEnsureRequest,
    DriveFolderEnsureResponse,
    DriveFolderFileListRequest,
    DriveFolderFileListResponse,
    DriveUploadLocalFileRequest,
    DriveUploadLocalFileResponse,
    DriveWritePreflightRequest,
    DriveWritePreflightResponse,
)
from src.contracts.files import (
    FileHashRequest,
    FileHashResponse,
    FileStatRequest,
    FileStatResponse,
    ReadBytesRequest,
    ReadBytesResponse,
    WriteBytesRequest,
    WriteBytesResponse,
)
from src.contracts.mailbox_acquisition import MailboxSearchRequest, MailboxSearchResult
from src.contracts.report_store import (
    AcquisitionAttemptResourceRecordRequest,
    AcquisitionAttemptResourceRecordResponse,
    AcquisitionRouteSuppressionRequest,
    AcquisitionRouteSuppressionResponse,
    PublisherDownloadRouteGetRequest,
    PublisherDownloadRouteRecordRequest,
    PublisherDownloadRouteResponse,
    PublisherGoogleFolderUpdateRequest,
    PublisherGoogleFolderUpdateResponse,
    PublisherPrivateApiCandidateObservationRecordRequest,
    PublisherPrivateApiCandidateObservationRecordResponse,
    PublisherPrivateApiCandidatePromotedRequest,
    ReportDownloadDriveFolderLookupRequest,
    ReportDownloadDriveFolderLookupResponse,
    ReportSourceRecordRequest,
    ReportSourceRecordResponse,
    ReportValueScoreRecordRequest,
    ReportValueScoreRequest,
    ReportValueScoreResponse,
    SourceIdentityObservationRecordRequest,
    SourceIdentityObservationRecordResponse,
    SourcePublicationMetadataExtractionRequest,
    SourcePublicationMetadataExtractionResponse,
    SourcePublicationMetadataUpsertRequest,
    SourcePublicationMetadataUpsertResponse,
)
from src.contracts.run_context import RunContext
from src.contracts.state import (
    MailDeliveryRequestUpsertRequest,
    MailDeliveryRequestUpsertResponse,
    WorkflowControlObservationWriteRequest,
    WorkflowControlObservationWriteResponse,
)
from src.generators.report_value_generator import score_report_value
from src.services.browser_report_download_service import (
    detect_private_api_promotion_candidates,
    download_report_with_browser_use,
    extract_source_publication_metadata,
    promote_private_api_evidence_to_browser_playbook,
    promote_validated_browser_route_result_to_playbook,
)
from src.services.config_service import (
    upsert_browser_download_identity_fields,
    upsert_browser_download_required_select_overrides,
)
from src.services.drive_service import (
    ensure_folder,
    list_files_in_folder,
    preflight_drive_write_access,
    upload_local_file,
)
from src.services.file_service import file_md5, file_stat, read_bytes, write_bytes
from src.services.mailbox_acquisition_service import preflight_mailbox_search
from src.services.report_store_service import (
    evaluate_acquisition_route_suppression,
    get_publisher_download_route,
    get_report_download_drive_folder,
    mark_publisher_private_api_candidate_promoted,
    record_acquisition_attempt_resource,
    record_publisher_download_route,
    record_publisher_private_api_candidate_observation,
    record_report_source,
    record_report_value_score,
    record_source_identity_observation,
    update_publisher_google_folder,
    upsert_source_publication_metadata,
)
from src.services.state_service import (
    upsert_mail_delivery_request,
    write_workflow_control_observation,
)


@dataclass(frozen=True)
class ReportDownloadDependencies:
    download_report_with_browser_use: Callable[
        [BrowserReportDownloadRequest, RunContext],
        BrowserReportDownloadResult,
    ]
    get_publisher_download_route: Callable[
        [PublisherDownloadRouteGetRequest, RunContext],
        Optional[PublisherDownloadRouteResponse],
    ]
    record_publisher_download_route: Callable[
        [PublisherDownloadRouteRecordRequest, RunContext],
        None,
    ]
    file_md5: Callable[[FileHashRequest, RunContext], FileHashResponse]
    record_report_source: Callable[
        [ReportSourceRecordRequest, RunContext],
        ReportSourceRecordResponse,
    ]
    upsert_browser_download_identity_fields: Callable[
        [BrowserDownloadIdentityFieldUpsertRequest, RunContext],
        BrowserDownloadIdentityFieldUpsertResponse,
    ]
    sleep_fn: Callable[[float], None]
    evaluate_acquisition_route_suppression: Callable[
        [AcquisitionRouteSuppressionRequest, RunContext],
        AcquisitionRouteSuppressionResponse,
    ] = evaluate_acquisition_route_suppression
    record_acquisition_attempt_resource: Callable[
        [AcquisitionAttemptResourceRecordRequest, RunContext],
        AcquisitionAttemptResourceRecordResponse,
    ] = record_acquisition_attempt_resource
    upsert_browser_download_required_select_overrides: Callable[
        [BrowserDownloadRequiredSelectOverrideRequest, RunContext],
        BrowserDownloadRequiredSelectOverrideResponse,
    ] = upsert_browser_download_required_select_overrides
    file_stat: Callable[[FileStatRequest, RunContext], FileStatResponse] = file_stat
    promote_validated_browser_route_result_to_playbook: Callable[
        ..., BrowserRoutePlaybookPromotionResponse
    ] = promote_validated_browser_route_result_to_playbook
    detect_private_api_promotion_candidates: Callable[
        [BrowserRoutePrivateApiAutoPromotionDetectionRequest, RunContext],
        BrowserRoutePrivateApiAutoPromotionDetectionResponse,
    ] = detect_private_api_promotion_candidates
    record_publisher_private_api_candidate_observation: Callable[
        [PublisherPrivateApiCandidateObservationRecordRequest, RunContext],
        PublisherPrivateApiCandidateObservationRecordResponse,
    ] = record_publisher_private_api_candidate_observation
    promote_private_api_evidence_to_browser_playbook: Callable[
        ..., BrowserRoutePlaybookPromotionResponse
    ] = promote_private_api_evidence_to_browser_playbook
    mark_publisher_private_api_candidate_promoted: Callable[
        [PublisherPrivateApiCandidatePromotedRequest, RunContext],
        None,
    ] = mark_publisher_private_api_candidate_promoted
    score_report_value: Callable[
        [ReportValueScoreRequest, RunContext],
        ReportValueScoreResponse,
    ] = score_report_value
    record_report_value_score: Callable[
        [ReportValueScoreRecordRequest, RunContext],
        None,
    ] = record_report_value_score
    read_bytes: Callable[[ReadBytesRequest, RunContext], ReadBytesResponse] = read_bytes
    extract_source_publication_metadata: Callable[
        [SourcePublicationMetadataExtractionRequest, RunContext],
        SourcePublicationMetadataExtractionResponse,
    ] = extract_source_publication_metadata
    upsert_source_publication_metadata: Callable[
        [SourcePublicationMetadataUpsertRequest, RunContext],
        SourcePublicationMetadataUpsertResponse,
    ] = upsert_source_publication_metadata
    record_source_identity_observation: Optional[
        Callable[
            [SourceIdentityObservationRecordRequest, RunContext],
            SourceIdentityObservationRecordResponse,
        ]
    ] = None
    write_bytes: Callable[[WriteBytesRequest, RunContext], WriteBytesResponse] = (
        write_bytes
    )
    get_report_download_drive_folder: Callable[
        [ReportDownloadDriveFolderLookupRequest, RunContext],
        Optional[ReportDownloadDriveFolderLookupResponse],
    ] = get_report_download_drive_folder
    list_files_in_folder: Callable[
        [DriveFolderFileListRequest, RunContext],
        DriveFolderFileListResponse,
    ] = list_files_in_folder
    upload_local_file: Callable[
        [DriveUploadLocalFileRequest, RunContext],
        DriveUploadLocalFileResponse,
    ] = upload_local_file
    preflight_drive_write_access: Callable[
        [DriveWritePreflightRequest, RunContext],
        DriveWritePreflightResponse,
    ] = preflight_drive_write_access
    ensure_folder: Callable[
        [DriveFolderEnsureRequest, RunContext],
        DriveFolderEnsureResponse,
    ] = ensure_folder
    update_publisher_google_folder: Callable[
        [PublisherGoogleFolderUpdateRequest, RunContext],
        PublisherGoogleFolderUpdateResponse,
    ] = update_publisher_google_folder
    upsert_mail_delivery_request: Callable[
        [MailDeliveryRequestUpsertRequest, RunContext],
        MailDeliveryRequestUpsertResponse,
    ] = upsert_mail_delivery_request
    write_workflow_control_observation: Callable[
        [WorkflowControlObservationWriteRequest, RunContext],
        WorkflowControlObservationWriteResponse,
    ] = write_workflow_control_observation
    preflight_mailbox_search: Callable[
        [MailboxSearchRequest, RunContext],
        MailboxSearchResult,
    ] = preflight_mailbox_search

    @classmethod
    def default(cls) -> "ReportDownloadDependencies":
        return cls(
            download_report_with_browser_use=download_report_with_browser_use,
            get_publisher_download_route=get_publisher_download_route,
            record_publisher_download_route=record_publisher_download_route,
            evaluate_acquisition_route_suppression=(
                evaluate_acquisition_route_suppression
            ),
            record_acquisition_attempt_resource=(record_acquisition_attempt_resource),
            file_md5=file_md5,
            file_stat=file_stat,
            record_report_source=record_report_source,
            extract_source_publication_metadata=extract_source_publication_metadata,
            upsert_source_publication_metadata=upsert_source_publication_metadata,
            record_source_identity_observation=record_source_identity_observation,
            score_report_value=score_report_value,
            record_report_value_score=record_report_value_score,
            read_bytes=read_bytes,
            write_bytes=write_bytes,
            get_report_download_drive_folder=get_report_download_drive_folder,
            list_files_in_folder=list_files_in_folder,
            upload_local_file=upload_local_file,
            ensure_folder=ensure_folder,
            update_publisher_google_folder=update_publisher_google_folder,
            upsert_browser_download_identity_fields=upsert_browser_download_identity_fields,
            upsert_browser_download_required_select_overrides=(
                upsert_browser_download_required_select_overrides
            ),
            sleep_fn=time.sleep,
        )
