# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_report_download_orchestrator.py"
)

import json

import logging

import hashlib

import sqlite3

import time

from dataclasses import replace

from pathlib import Path

from typing import Any

import pytest

import yaml

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadRouteStep,
    BrowserDownloadSettings,
    BrowserReportDownloadResult,
    BrowserRoutePrivateApiAutoPromotionDetectionResponse,
    BrowserRoutePrivateApiPromotionCandidate,
    BrowserRoutePlaybookPromotionResponse,
    DownloadTerminalEvidence,
    ReportDownloadOrchestratorRequest,
    ReportDownloadRoutePlanRequest,
)

from src.contracts.drive import (
    DriveFile,
    DriveFolderEnsureResponse,
    DriveFolderFileListResponse,
    DriveWritePreflightResponse,
    DriveUploadLocalFileResponse,
)

from src.contracts.files import FileHashResponse

from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.contracts.mailbox_acquisition import (
    MailboxAcquisitionSettings,
    MailboxSearchResult,
)

from src.contracts.report_store import (
    PublisherPrivateApiCandidateObservationRecordResponse,
    PublisherDownloadRouteResponse,
    ReportDownloadDriveFolderLookupResponse,
    ReportSourceRecordResponse,
    PublisherGoogleFolderUpdateResponse,
)

from src.orchestrators.report_download_orchestrator import (
    ReportDownloadDependencies,
    run_report_download,
)

from src.orchestrators._report_download_orchestrator.promotions import (
    evaluate_private_api_playbook_auto_promotion,
)

from src.orchestrators._report_download_orchestrator.route_planner import (
    plan_report_download_routes,
)

from src.services._browser_report_download import request as request_runtime

from src.services.report_store_service import (
    get_publisher_download_route,
    record_publisher_download_route,
)
from src.contracts.state import (
    MailDeliveryRequestListDueRequest,
    WorkflowControlObservationListRequest,
)

from src.services.state_service import (
    list_due_mail_delivery_requests,
    list_workflow_control_observations,
)

from src.services.config_service import upsert_browser_download_identity_fields

from src.utils.errors import AppError


def _settings(tmp_path: Path) -> BrowserDownloadSettings:
    return BrowserDownloadSettings(
        schema_version="1.0",
        openrouter_api_key="openrouter-key",
        model="openai/gpt-5-mini",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=5,
        output_dir=str(tmp_path / "downloads"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        identity_config_path=str(tmp_path / "browser_download_identity.yaml"),
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="work_email",
                    label="Work email",
                    value="ops@example.com",
                    aliases=["email"],
                )
            ],
        ),
        openrouter_http_referer="https://marketlense.local",
        headed=False,
        retry_retries=1,
        retry_base_delay_seconds=0.1,
        retry_backoff_step_seconds=0.0,
        retry_jitter_seconds=0.0,
    )


def _fresh_route_memory_updated_at() -> int:
    return int(time.time())


def _result(
    *, url: str, used_route_hint: bool, path: str | None
) -> BrowserReportDownloadResult:
    final_page_url = f"{url}/final"
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=url,
        normalized_url=url,
        route_kind="pdf_download" if path else "email_delivery",
        route_family="direct_pdf_probe" if path else "browser_email_form",
        route_status="verified" if path else "inferred",
        outcome="downloaded" if path else "email_required",
        route_summary="Click the report CTA and wait for completion.",
        final_page_url=final_page_url,
        resolved_target_url=final_page_url,
        used_route_hint=used_route_hint,
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="open",
                target_text=url,
                target_role="url",
                target_url=url,
                result="downloaded" if path else "completed",
            )
        ],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=False,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=final_page_url,
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=final_page_url,
            final_page_title="",
            terminal_text_excerpt="",
            artifact_url=final_page_url,
            artifact_kind="pdf" if path else "email_delivery",
            artifact_validation_status="verified" if path else "blocked",
            artifact_validation_detail="",
            confirmation_signal_count=0,
            traversed_page_urls=[url, final_page_url],
        ),
        browser_had_structured_result=not path,
        used_candidate_pdf_url=False,
        used_candidate_source_page=False,
        encountered_form_fields=["Name", "Business"] if not path else [],
        blocked_reason="blocked_missing_identity_field" if not path else None,
        blocked_reason_detail="missing identity values" if not path else None,
        downloaded_file_path=path,
        downloaded_file_name=Path(path).name if path else None,
        downloaded_mime_type="application/pdf" if path else None,
        downloaded_size_bytes=128 if path else None,
        onsite_capture_path=None,
        onsite_capture_format=None,
        onsite_page_count=None,
        onsite_completeness_status=None,
    )


def _captured_result(
    *,
    url: str,
    onsite_path: str,
    html_snapshot_path: str,
    screenshot_path: str,
) -> BrowserReportDownloadResult:
    final_page_url = f"{url}/final"
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=url,
        normalized_url=url,
        route_kind="onsite_report",
        route_family="browser_onsite_report",
        route_status="verified",
        outcome="captured",
        route_summary="Capture the readable on-site report.",
        final_page_url=final_page_url,
        resolved_target_url=final_page_url,
        used_route_hint=False,
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="open",
                target_text=url,
                target_role="url",
                target_url=url,
                result="captured",
            )
        ],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=False,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=final_page_url,
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=final_page_url,
            final_page_title="On-site report",
            terminal_text_excerpt="Readable report",
            artifact_url=final_page_url,
            artifact_kind="onsite_report",
            artifact_validation_status="captured",
            artifact_validation_detail="Captured local terminal artifacts",
            confirmation_signal_count=1,
            traversed_page_urls=[url, final_page_url],
            html_snapshot_path=html_snapshot_path,
            screenshot_path=screenshot_path,
        ),
        browser_had_structured_result=True,
        used_candidate_pdf_url=False,
        used_candidate_source_page=False,
        encountered_form_fields=[],
        blocked_reason=None,
        blocked_reason_detail=None,
        downloaded_file_path=None,
        downloaded_file_name=None,
        downloaded_mime_type=None,
        downloaded_size_bytes=None,
        onsite_capture_path=onsite_path,
        onsite_capture_format="html",
        onsite_page_count=1,
        onsite_completeness_status="complete",
    )


def _events(caplog, logger_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in caplog.records:
        if record.name != logger_name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _md5_for_path(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _drive_enabled_settings(
    settings: BrowserDownloadSettings,
) -> BrowserDownloadSettings:
    return replace(
        settings,
        drive_upload_enabled=True,
        drive_upload_required=True,
        drive_upload_parent_folder_id="root-folder",
        drive_upload_google_sa_path="/tmp/fake-sa.json",
        drive_upload_auth_mode="service_account",
        drive_upload_supports_all_drives=True,
        drive_upload_include_items_from_all_drives=True,
    )


def _successful_drive_preflight(req, ctx) -> DriveWritePreflightResponse:
    return DriveWritePreflightResponse(
        schema_version="1.0",
        folder_id=req.folder_id,
        auth_mode=req.auth_mode,
        credentials_refreshed=False,
        scopes_verified=True,
        folder_access_verified=True,
        write_access_verified=True,
    )


def _private_api_promotion_candidate() -> BrowserRoutePrivateApiPromotionCandidate:
    return BrowserRoutePrivateApiPromotionCandidate(
        schema_version="1.0",
        fingerprint="private-api-fp",
        source_url="https://example.com/research/report-2026",
        publisher_host="example.com",
        endpoint_pattern="/api/reports/{last_path_segment}",
        endpoint_url="https://example.com/api/reports/report-2026",
        method="GET",
        request_shape_summary="GET without cookies or auth headers.",
        response_pdf_url_json_pointer="/asset/pdfUrl",
        selected_pdf_url="https://example.com/files/report-2026.pdf",
        expected_status_codes=[200],
        required_response_markers=["pdfUrl"],
        fallback_route_family="browser_pdf_click",
        route_family="browser_pdf_click",
        route_kind="pdf_download",
        evidence_labels=["browser_network_private_api"],
    )


def _private_api_promotion_dependencies(
    tmp_path: Path,
    *,
    record_candidate,
    mark_promoted,
) -> ReportDownloadDependencies:
    def _unused(*args, **kwargs):
        raise AssertionError("unused dependency called")

    return ReportDownloadDependencies(
        download_report_with_browser_use=_unused,
        get_publisher_download_route=_unused,
        record_publisher_download_route=_unused,
        file_md5=_unused,
        record_report_source=_unused,
        upsert_browser_download_identity_fields=_unused,
        record_report_value_score=_unused,
        detect_private_api_promotion_candidates=lambda req, ctx: (
            BrowserRoutePrivateApiAutoPromotionDetectionResponse(
                schema_version="1.0",
                candidate_count=1,
                candidates=[_private_api_promotion_candidate()],
                skipped_reason="",
            )
        ),
        record_publisher_private_api_candidate_observation=record_candidate,
        promote_private_api_evidence_to_browser_playbook=lambda **kwargs: (
            BrowserRoutePlaybookPromotionResponse(
                schema_version="1.0",
                playbook_id="private-api-example-com-pdf-download",
                version="1.0.0",
                path=str(tmp_path / "playbooks/private_api/private-api.yaml"),
                status="created",
                review_diff="--- before\n+++ after\n",
            )
        ),
        mark_publisher_private_api_candidate_promoted=mark_promoted,
        sleep_fn=lambda seconds: None,
    )


def _evaluate_private_api_side_path(
    tmp_path: Path,
    run_context,
    dependencies: ReportDownloadDependencies,
) -> None:
    settings = replace(
        _settings(tmp_path),
        private_api_playbook_promotion_mode="write",
        private_api_playbook_min_success_count=3,
        private_api_playbook_min_distinct_source_urls=2,
    )
    evaluate_private_api_playbook_auto_promotion(
        request=ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/research/report-2026",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        result=replace(
            _result(
                url="https://example.com/research/report-2026",
                used_route_hint=False,
                path=str(tmp_path / "report.pdf"),
            ),
            route_family="browser_pdf_click",
            browser_had_structured_result=True,
        ),
        ctx=run_context,
        dependencies=dependencies,
        route_record_reused=False,
    )


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
