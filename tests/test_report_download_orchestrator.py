from __future__ import annotations

import json
import logging
import hashlib
import sqlite3
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
    DriveFolderFileListResponse,
    DriveUploadLocalFileResponse,
)
from src.contracts.files import FileHashResponse
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.contracts.report_store import (
    PublisherPrivateApiCandidateObservationRecordResponse,
    PublisherDownloadRouteResponse,
    ReportDownloadDriveFolderLookupResponse,
    ReportSourceRecordResponse,
)
from src.orchestrators.report_download_orchestrator import (
    ReportDownloadDependencies,
    run_report_download,
)
from src.orchestrators._report_download_orchestrator.route_planner import (
    plan_report_download_routes,
)
from src.services._browser_report_download import request as request_runtime
from src.services.report_store_service import (
    get_publisher_download_route,
    record_publisher_download_route,
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
        drive_upload_google_sa_path="/tmp/fake-sa.json",
        drive_upload_auth_mode="service_account",
        drive_upload_supports_all_drives=True,
        drive_upload_include_items_from_all_drives=True,
    )


def test_route_plan_recovery_classes_cover_allowed_blocked_and_deferred(
    run_context,
    caplog,
) -> None:
    caplog.set_level(
        logging.INFO,
        logger="market_lense.report_download_route_planner",
    )

    allowed = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://example.com/content/2026-ai-index-report",
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://example.com/content/2026-ai-index-report",
                title="2026 AI Market Report",
                discovered_on_page_number=1,
                source_page_urls=["https://example.com/research"],
                discovery_provenances=["browser_dom"],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.9,
            ),
            publisher_recommended_discovery_route_kind="browser_render",
        ),
        run_context,
    )
    assert [step.route_family for step in allowed.steps] == [
        "browser_pdf_click",
        "http_pdf_probe",
    ]
    assert allowed.steps[1].recovery_class == "browser_to_http_pdf_probe"
    assert allowed.steps[1].recovery_decision == "allowed"

    blocked = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://example.com/reports",
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://example.com/reports",
                title="Reports and insights",
                discovered_on_page_number=1,
                source_page_urls=["https://example.com/reports"],
                discovery_provenances=["browser_dom"],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.95,
            ),
            publisher_recommended_discovery_route_kind="browser_render",
        ),
        run_context,
    )
    assert [step.route_family for step in blocked.steps] == ["browser_listing_hub"]
    assert blocked.blocked_recovery_classes == [
        "browser_to_http_pdf_probe:blocked:terminal_browser_family:browser_listing_hub"
    ]

    deferred = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://example.com/content/ai-index-methodology",
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://example.com/content/ai-index-methodology",
                title="AI index methodology",
                discovered_on_page_number=1,
                source_page_urls=["https://example.com/research"],
                discovery_provenances=["browser_dom"],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.7,
            ),
            publisher_recommended_discovery_route_kind="browser_render",
        ),
        run_context,
    )
    assert [step.route_family for step in deferred.steps] == ["browser_pdf_click"]
    assert deferred.blocked_recovery_classes == [
        "browser_to_http_pdf_probe:deferred:browser_route_without_http_signal"
    ]

    route_plan_events = [
        event
        for event in _events(caplog, "market_lense.report_download_route_planner")
        if event.get("event") == "report_download_route_plan_complete"
    ]
    assert route_plan_events
    assert (
        "browser_to_http_pdf_probe"
        in route_plan_events[0]["fields"]["recovery_classes"]
    )
    blocked_events = [
        event
        for event in _events(caplog, "market_lense.report_download_route_planner")
        if event.get("event") == "report_download_recovery_policy_blocked"
    ]
    assert len(blocked_events) == 2


def test_run_report_download_rejects_mixed_content_hub_candidate(
    tmp_path: Path,
    caplog,
    run_context,
    assert_app_error,
) -> None:
    settings = _settings(tmp_path)

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("mixed-content hub should be rejected before acquisition")
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="unused",
        ),
        record_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not record rejected candidates")
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    with pytest.raises(AppError) as exc_info:
        run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/reports",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                candidate_trace=PublisherInventoryCandidateTrace(
                    schema_version="1.0",
                    canonical_url="https://example.com/reports",
                    title="Reports and insights",
                    discovered_on_page_number=1,
                    source_page_urls=["https://example.com/reports"],
                    discovery_provenances=["browser_dom"],
                    pdf_url=None,
                    published_at_text=None,
                    max_confidence=0.95,
                ),
                publisher_recommended_discovery_route_kind="browser_render",
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert_app_error(
        exc_info.value,
        code="report_download_candidate_rejected_mixed_content_hub",
        retryable=False,
        severity="error",
    )
    rejection_events = [
        event
        for event in _events(caplog, "market_lense.report_download_orchestrator")
        if event.get("event") == "report_download_readiness_rejected"
    ]
    assert rejection_events
    assert (
        rejection_events[-1]["fields"]["readiness_rejection_reason"]
        == "candidate_rejected_mixed_content_hub"
    )
    assert (
        "mixed_content_hub_candidate"
        in rejection_events[-1]["fields"]["readiness_signals"]
    )


def test_run_report_download_uses_memory_and_records_route(
    tmp_path: Path,
    caplog,
    run_context,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    settings = _settings(tmp_path)
    saved_records = []
    saved_sources = []

    def _download(req, ctx):
        assert req.route_hint == "Use the first Download report button."
        return _result(
            url="https://example.com/report",
            used_route_hint=True,
            path=str(Path(settings.output_dir) / "report.pdf"),
        )

    def _get_route(req, ctx):
        return PublisherDownloadRouteResponse(
            schema_version="1.0",
            normalized_url=req.normalized_url,
            source_url="https://example.com/report",
            route_kind="pdf_download",
            route_summary="Use the first Download report button.",
            outcome="downloaded",
            route_family="browser_pdf_click",
            route_status="verified",
            resolved_target_url="https://example.com/report/final",
            route_steps=[],
            confirmation_evidence=BrowserDownloadConfirmationEvidence(
                schema_version="1.0",
                url_changed=False,
                visible_confirmation_text="",
                submit_button_state="unchanged",
                form_disappeared=False,
                final_page_url="https://example.com/report/final",
            ),
            terminal_evidence=DownloadTerminalEvidence(
                schema_version="1.0",
                final_page_url="https://example.com/report/final",
                final_page_title="",
                terminal_text_excerpt="",
                artifact_url="https://example.com/report/final",
                artifact_kind="pdf",
                artifact_validation_status="verified",
                artifact_validation_detail="",
                confirmation_signal_count=0,
                traversed_page_urls=["https://example.com/report/final"],
            ),
            browser_had_structured_result=True,
            used_candidate_pdf_url=False,
            used_candidate_source_page=False,
            updated_at=1,
            candidate_pdf_url=None,
            candidate_source_page_urls=[],
            candidate_discovery_provenances=[],
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
            blocked_reason=None,
            blocked_reason_detail=None,
            last_downloaded_file_path=str(Path(settings.output_dir) / "report.pdf"),
            last_final_page_url="https://example.com/report/final",
            onsite_capture_path=None,
            onsite_capture_format=None,
            onsite_page_count=None,
            onsite_completeness_status=None,
            attempts=1,
            verified_successes=1,
            last_n_outcomes=["downloaded"],
            confidence_score=1.0,
        )

    def _record_route(req, ctx):
        saved_records.append(req)

    def _file_md5(req, ctx):
        return FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="abc123",
        )

    def _record_source(req, ctx):
        saved_sources.append(req)
        return ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        )

    def _upsert_identity(req, ctx):
        return type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )()

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=_get_route,
        record_publisher_download_route=_record_route,
        file_md5=_file_md5,
        record_report_source=_record_source,
        upsert_browser_download_identity_fields=_upsert_identity,
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.used_memory_route is True
    assert response.outcome == "downloaded"
    assert len(saved_records) == 1
    assert len(saved_sources) == 1
    assert saved_records[0].normalized_url == "https://example.com/report"
    assert saved_sources[0].source_domain == "example.com"
    assert saved_sources[0].report_name == "report"
    assert saved_sources[0].landing_page_url == "https://example.com/report"
    assert saved_sources[0].md5 == "abc123"
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(
        _events(caplog, "market_lense.report_download_orchestrator")
    )


def test_run_report_download_auto_promotes_private_api_after_threshold(
    tmp_path: Path,
    caplog,
    run_context,
) -> None:
    settings = replace(
        _settings(tmp_path),
        private_api_playbook_promotion_mode="write",
        private_api_playbook_min_success_count=3,
        private_api_playbook_min_distinct_source_urls=2,
    )
    downloaded_path = Path(settings.output_dir) / "report.pdf"
    downloaded_path.parent.mkdir(parents=True, exist_ok=True)
    downloaded_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    candidate = BrowserRoutePrivateApiPromotionCandidate(
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
    promoted_requests = []
    marked_promotions = []

    def _download(req, ctx):
        return replace(
            _result(
                url="https://example.com/research/report-2026",
                used_route_hint=False,
                path=str(downloaded_path),
            ),
            route_family="browser_pdf_click",
            browser_had_structured_result=True,
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="abc123",
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        detect_private_api_promotion_candidates=lambda req, ctx: (
            BrowserRoutePrivateApiAutoPromotionDetectionResponse(
                schema_version="1.0",
                candidate_count=1,
                candidates=[candidate],
                skipped_reason="",
            )
        ),
        record_publisher_private_api_candidate_observation=lambda req, ctx: (
            PublisherPrivateApiCandidateObservationRecordResponse(
                schema_version="1.0",
                fingerprint=req.fingerprint,
                success_count=3,
                distinct_source_url_count=2,
                eligible_for_promotion=True,
                already_promoted=False,
                promoted_playbook_id="",
            )
        ),
        promote_private_api_evidence_to_browser_playbook=lambda **kwargs: (
            promoted_requests.append(kwargs["request"])
            or BrowserRoutePlaybookPromotionResponse(
                schema_version="1.0",
                playbook_id="private-api-example-com-pdf-download",
                version="1.0.0",
                path=str(tmp_path / "playbooks/private_api/private-api.yaml"),
                status="created",
                review_diff="--- before\n+++ after\n",
            )
        ),
        mark_publisher_private_api_candidate_promoted=lambda req, ctx: (
            marked_promotions.append(req)
        ),
        sleep_fn=lambda seconds: None,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/research/report-2026",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.outcome == "downloaded"
    assert len(promoted_requests) == 1
    assert promoted_requests[0].endpoint_pattern == "/api/reports/{last_path_segment}"
    assert promoted_requests[0].validated_success_count == 3
    assert len(marked_promotions) == 1
    assert marked_promotions[0].fingerprint == "private-api-fp"
    events = [
        event
        for event in _events(caplog, "market_lense.report_download_orchestrator")
        if event.get("event") == "report_download_private_api_promotion_evaluated"
    ]
    assert events
    assert events[-1]["fields"]["promotion_status"] == "created"


def test_run_report_download_falls_back_after_memory_failure_and_retries(
    tmp_path: Path,
    caplog,
    run_context,
    assert_logs_have_required_fields,
) -> None:
    settings = _settings(tmp_path)
    attempts = {"memory": 0, "discovery": 0}
    sleep_calls: list[float] = []
    saved_records = []
    identity_updates = []
    saved_sources = []

    def _download(req, ctx):
        if req.route_hint:
            attempts["memory"] += 1
            raise AppError(
                code="browser_download_agent_failed",
                message="stored route stale",
                retryable=True,
            )
        attempts["discovery"] += 1
        if attempts["discovery"] == 1:
            raise AppError(
                code="browser_download_agent_failed",
                message="transient browser error",
                retryable=True,
            )
        return _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=str(Path(settings.output_dir) / "report.pdf"),
        )

    def _get_route(req, ctx):
        return PublisherDownloadRouteResponse(
            schema_version="1.0",
            normalized_url=req.normalized_url,
            source_url="https://example.com/report",
            route_kind="pdf_download",
            route_summary="Use the first Download report button.",
            outcome="downloaded",
            route_family="browser_pdf_click",
            route_status="verified",
            resolved_target_url="https://example.com/report/final",
            route_steps=[],
            confirmation_evidence=BrowserDownloadConfirmationEvidence(
                schema_version="1.0",
                url_changed=False,
                visible_confirmation_text="",
                submit_button_state="unchanged",
                form_disappeared=False,
                final_page_url="https://example.com/report/final",
            ),
            terminal_evidence=DownloadTerminalEvidence(
                schema_version="1.0",
                final_page_url="https://example.com/report/final",
                final_page_title="",
                terminal_text_excerpt="",
                artifact_url="https://example.com/report/final",
                artifact_kind="pdf",
                artifact_validation_status="verified",
                artifact_validation_detail="",
                confirmation_signal_count=0,
                traversed_page_urls=["https://example.com/report/final"],
            ),
            browser_had_structured_result=True,
            used_candidate_pdf_url=False,
            used_candidate_source_page=False,
            updated_at=1,
            candidate_pdf_url=None,
            candidate_source_page_urls=[],
            candidate_discovery_provenances=[],
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
            blocked_reason=None,
            blocked_reason_detail=None,
            last_downloaded_file_path=None,
            last_final_page_url=None,
            onsite_capture_path=None,
            onsite_capture_format=None,
            onsite_page_count=None,
            onsite_completeness_status=None,
            attempts=1,
            verified_successes=1,
            last_n_outcomes=["downloaded"],
            confidence_score=1.0,
        )

    def _record_route(req, ctx):
        saved_records.append(req)

    def _file_md5(req, ctx):
        return FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="def456",
        )

    def _record_source(req, ctx):
        saved_sources.append(req)
        return ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=2,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        )

    def _upsert_identity(req, ctx):
        identity_updates.append(req)
        return type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": ["name", "business"],
                "total_fields": len(settings.identity_profile.fields) + 2,
            },
        )()

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=_get_route,
        record_publisher_download_route=_record_route,
        file_md5=_file_md5,
        record_report_source=_record_source,
        upsert_browser_download_identity_fields=_upsert_identity,
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: sleep_calls.append(float(seconds)),
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert attempts["memory"] == 2
    assert attempts["discovery"] == 2
    assert sleep_calls == [0.1, 0.1]
    assert response.used_memory_route is False
    assert response.outcome == "downloaded"
    assert len(saved_records) == 1
    assert len(saved_sources) == 1
    assert identity_updates[0].encountered_form_fields == []
    assert_logs_have_required_fields(
        _events(caplog, "market_lense.report_download_orchestrator")
    )


def test_run_report_download_does_not_retry_timed_out_browser_step(
    tmp_path: Path,
    caplog,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    browser_calls: list[str] = []

    def _download(req, ctx):
        route_family = req.route_family_hint or ""
        if route_family == "http_pdf_probe":
            raise AppError(
                code="browser_download_http_probe_failed",
                message="The planned HTTP probe did not produce a valid PDF artifact",
                retryable=True,
                context={"normalized_url": req.url},
            )
        browser_calls.append(route_family)
        raise AppError(
            code="browser_download_agent_timeout",
            message="browser-use did not return within the configured execution budget",
            retryable=True,
            context={"normalized_url": req.url},
        )

    def _record_route(req, ctx):
        return None

    def _file_md5(req, ctx):
        return FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="abc123",
        )

    def _record_source(req, ctx):
        return ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        )

    def _upsert_identity(req, ctx):
        return type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )()

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=_record_route,
        file_md5=_file_md5,
        record_report_source=_record_source,
        upsert_browser_download_identity_fields=_upsert_identity,
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    with pytest.raises(AppError) as exc_info:
        run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert exc_info.value.code == "browser_download_agent_timeout"
    assert browser_calls == ["browser_pdf_click"]
    retry_events = [
        event
        for event in _events(caplog, "market_lense.report_download_orchestrator")
        if event.get("event") == "report_download_retry"
    ]
    failure_events = [
        event
        for event in _events(caplog, "market_lense.report_download_orchestrator")
        if event.get("event") == "report_download_attempt_failed"
    ]
    browser_retry_events = [
        event
        for event in retry_events
        if event.get("fields", {}).get("step") == "report_download_browser_candidate"
    ]
    assert browser_retry_events == []
    assert failure_events
    assert failure_events[-1]["fields"]["code"] == "browser_download_agent_timeout"
    assert failure_events[-1]["fields"]["retryable"] is False


def test_run_report_download_does_not_retry_failed_http_probe_before_browser_fallback(
    tmp_path: Path,
    caplog,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    calls: list[str] = []

    def _download(req, ctx):
        route_family = req.route_family_hint or ""
        calls.append(route_family)
        if route_family == "http_pdf_probe":
            raise AppError(
                code="browser_download_http_probe_failed",
                message="The planned HTTP probe did not produce a valid PDF artifact",
                retryable=True,
                context={"normalized_url": req.url},
            )
        return _result(
            url=req.url,
            used_route_hint=False,
            path=str(Path(settings.output_dir) / "report.pdf"),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="abc123",
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.outcome == "downloaded"
    assert calls == ["http_pdf_probe", "browser_pdf_click"]
    retry_events = [
        event
        for event in _events(caplog, "market_lense.report_download_orchestrator")
        if event.get("event") == "report_download_retry"
    ]
    assert retry_events == []


@pytest.mark.parametrize(
    ("failure_forensics_policy", "expected_retention_action"),
    [("copy_artifacts", "copied"), ("metadata_only", "metadata_only")],
)
def test_run_report_download_persists_failure_forensics_pack(
    tmp_path: Path,
    caplog,
    run_context,
    failure_forensics_policy: str,
    expected_retention_action: str,
) -> None:
    settings = replace(
        _settings(tmp_path),
        retry_retries=0,
        failure_forensics_enabled=True,
        failure_forensics_policy=failure_forensics_policy,
    )
    normalized_url = "https://example.com/report"
    download_dir = request_runtime.resolve_download_dir_path(
        root_dir=settings.output_dir,
        normalized_url=normalized_url,
    )
    download_dir.mkdir(parents=True, exist_ok=True)
    html_snapshot_path = download_dir / "terminal.html"
    screenshot_path = download_dir / "terminal.png"
    html_snapshot_path.write_text(
        "<html><body><h1>Report missing</h1></body></html>",
        encoding="utf-8",
    )
    screenshot_path.write_bytes(b"png-bytes")

    def _download(req, ctx):
        route_family = req.route_family_hint or ""
        if route_family == "http_pdf_probe":
            raise AppError(
                code="browser_download_http_probe_failed",
                message="The planned HTTP probe did not produce a valid PDF artifact",
                retryable=True,
                context={"normalized_url": req.url},
            )
        raise AppError(
            code="browser_download_report_not_found",
            message="browser-use reached a listing or search page where the target report was not found",
            retryable=False,
            context={
                "normalized_url": req.url,
                "execution_url": req.url,
                "final_page_url": f"{req.url}/missing",
                "final_page_title": "Missing report",
                "terminal_text_excerpt": "The requested report is no longer available.",
                "html_snapshot_path": str(html_snapshot_path),
                "screenshot_path": str(screenshot_path),
                "route_kind": "none",
                "network_events": [],
            },
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="abc123",
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    with pytest.raises(AppError) as exc_info:
        run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url=normalized_url,
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert exc_info.value.code == "browser_download_report_not_found"
    pack_path = Path(str(exc_info.value.context["failure_forensics_pack_path"]))
    assert pack_path.exists()
    pack_payload = json.loads(pack_path.read_text(encoding="utf-8"))
    assert pack_payload["route_family"] == "browser_pdf_click"
    assert pack_payload["error_class"] == "permanent_app_error"
    assert pack_payload["terminal_evidence"]["html_snapshot_path"] == str(
        html_snapshot_path
    )
    assert pack_payload["terminal_evidence"]["screenshot_path"] == str(screenshot_path)
    artifact_actions = {
        artifact["artifact_label"]: artifact["retention_action"]
        for artifact in pack_payload["artifacts"]
    }
    assert artifact_actions["terminal_html_snapshot"] == expected_retention_action
    assert artifact_actions["terminal_screenshot"] == expected_retention_action
    if failure_forensics_policy == "copy_artifacts":
        copied_paths = [
            artifact["persisted_path"]
            for artifact in pack_payload["artifacts"]
            if artifact["persisted_path"]
        ]
        assert copied_paths
        assert all(Path(path).exists() for path in copied_paths)
    else:
        assert all(
            artifact["persisted_path"] is None for artifact in pack_payload["artifacts"]
        )
    failure_events = [
        event
        for event in _events(caplog, "market_lense.report_download_orchestrator")
        if event.get("event") == "report_download_attempt_failed"
    ]
    step_failed_events = [
        event
        for event in _events(caplog, "market_lense.report_download_orchestrator")
        if event.get("event") == "report_download_step_failed"
    ]
    assert failure_events
    assert failure_events[-1]["fields"]["route_family"] == "browser_pdf_click"
    assert failure_events[-1]["fields"]["error_class"] == "permanent_app_error"
    assert failure_events[-1]["fields"]["failure_forensics_pack_path"] == str(pack_path)
    assert step_failed_events
    assert step_failed_events[-1]["fields"]["failure_forensics_pack_path"] == str(
        pack_path
    )
    assert (
        step_failed_events[-1]["fields"]["failure_forensics_artifact_policy"]
        == failure_forensics_policy
    )


def test_run_report_download_does_not_fallback_after_non_retryable_memory_browser_timeout(
    tmp_path: Path,
    caplog,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    calls: list[tuple[str, str | None, int]] = []

    def _download(req, ctx):
        calls.append(
            (
                req.route_family_hint or "",
                req.route_hint,
                len(req.route_step_hints),
            )
        )
        raise AppError(
            code="browser_download_agent_timeout",
            message="browser-use did not return within the configured execution budget",
            retryable=True,
            context={"normalized_url": req.url},
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: PublisherDownloadRouteResponse(
            schema_version="1.0",
            normalized_url=req.normalized_url,
            source_url=req.normalized_url,
            route_kind="onsite_report",
            route_summary="Accept cookies and extract the on-site report.",
            outcome="captured",
            route_family="browser_onsite_report",
            route_status="verified",
            resolved_target_url=req.normalized_url,
            route_steps=[
                BrowserDownloadRouteStep(
                    schema_version="1.0",
                    index=0,
                    action="click",
                    target_text="Allow all",
                    target_role="button",
                    target_url=req.normalized_url,
                    result="Accepted cookies",
                ),
                BrowserDownloadRouteStep(
                    schema_version="1.0",
                    index=1,
                    action="extract",
                    target_text="report article",
                    target_role="extract",
                    target_url=req.normalized_url,
                    result="Captured the on-site report body",
                ),
            ],
            confirmation_evidence=BrowserDownloadConfirmationEvidence(
                schema_version="1.0",
                url_changed=False,
                visible_confirmation_text="",
                submit_button_state="unchanged",
                form_disappeared=False,
                final_page_url=req.normalized_url,
            ),
            terminal_evidence=DownloadTerminalEvidence(
                schema_version="1.0",
                final_page_url=req.normalized_url,
                final_page_title="",
                terminal_text_excerpt="",
                artifact_url=req.normalized_url,
                artifact_kind="onsite_report",
                artifact_validation_status="verified",
                artifact_validation_detail="",
                confirmation_signal_count=0,
                traversed_page_urls=[req.normalized_url],
            ),
            browser_had_structured_result=True,
            used_candidate_pdf_url=False,
            used_candidate_source_page=False,
            updated_at=1,
            candidate_pdf_url=None,
            candidate_source_page_urls=[],
            candidate_discovery_provenances=[],
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
            blocked_reason=None,
            blocked_reason_detail=None,
            last_downloaded_file_path=None,
            last_final_page_url=req.normalized_url,
            onsite_capture_path="captured.html",
            onsite_capture_format="html",
            onsite_page_count=1,
            onsite_completeness_status="complete",
            attempts=2,
            verified_successes=2,
            last_n_outcomes=["captured", "captured"],
            confidence_score=1.0,
        ),
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="abc123",
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    with pytest.raises(AppError) as exc_info:
        run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert exc_info.value.code == "browser_download_agent_timeout"
    assert calls == [
        (
            "browser_onsite_report",
            "Accept cookies and extract the on-site report.",
            2,
        )
    ]
    step_failed_events = [
        event
        for event in _events(caplog, "market_lense.report_download_orchestrator")
        if event.get("event") == "report_download_step_failed"
    ]
    assert len(step_failed_events) == 1
    assert (
        step_failed_events[0]["fields"]["step_name"]
        == "report_download_with_memory_route"
    )
    assert step_failed_events[0]["fields"]["attempt_retryable"] is False
    assert step_failed_events[0]["fields"]["fallback_on_retryable_error"] is True


def test_run_report_download_does_not_retry_weak_browser_route_summary(
    tmp_path: Path,
    caplog,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    browser_calls: list[str] = []

    def _download(req, ctx):
        route_family = req.route_family_hint or ""
        if route_family == "http_pdf_probe":
            raise AppError(
                code="browser_download_http_probe_failed",
                message="The planned HTTP probe did not produce a valid PDF artifact",
                retryable=True,
                context={"normalized_url": req.url},
            )
        browser_calls.append(route_family)
        raise AppError(
            code="browser_download_route_summary_too_weak",
            message="The browser result did not provide enough route evidence",
            retryable=True,
            context={"normalized_url": req.url},
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="abc123",
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    with pytest.raises(AppError) as exc_info:
        run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert exc_info.value.code == "browser_download_route_summary_too_weak"
    assert browser_calls == ["browser_pdf_click"]
    retry_events = [
        event
        for event in _events(caplog, "market_lense.report_download_orchestrator")
        if event.get("event") == "report_download_retry"
    ]
    browser_retry_events = [
        event
        for event in retry_events
        if event.get("fields", {}).get("step") == "report_download_browser_candidate"
    ]
    assert browser_retry_events == []


def test_run_report_download_does_not_fallback_after_non_retryable_memory_failure(
    tmp_path: Path,
    run_context,
    assert_app_error,
) -> None:
    settings = _settings(tmp_path)
    attempts = {"memory": 0, "discovery": 0}

    def _download(req, ctx):
        if req.route_hint:
            attempts["memory"] += 1
            raise AppError(
                code="browser_download_route_summary_invalid",
                message="stored route is structurally invalid",
                retryable=False,
            )
        attempts["discovery"] += 1
        return _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=str(Path(settings.output_dir) / "report.pdf"),
        )

    def _get_route(req, ctx):
        return PublisherDownloadRouteResponse(
            schema_version="1.0",
            normalized_url=req.normalized_url,
            source_url="https://example.com/report",
            route_kind="pdf_download",
            route_summary="Use the first Download report button.",
            outcome="downloaded",
            route_family="browser_pdf_click",
            route_status="verified",
            resolved_target_url="https://example.com/report/final",
            route_steps=[],
            confirmation_evidence=BrowserDownloadConfirmationEvidence(
                schema_version="1.0",
                url_changed=False,
                visible_confirmation_text="",
                submit_button_state="unchanged",
                form_disappeared=False,
                final_page_url="https://example.com/report/final",
            ),
            terminal_evidence=DownloadTerminalEvidence(
                schema_version="1.0",
                final_page_url="https://example.com/report/final",
                final_page_title="",
                terminal_text_excerpt="",
                artifact_url="https://example.com/report/final",
                artifact_kind="pdf",
                artifact_validation_status="verified",
                artifact_validation_detail="",
                confirmation_signal_count=0,
                traversed_page_urls=["https://example.com/report/final"],
            ),
            browser_had_structured_result=True,
            used_candidate_pdf_url=False,
            used_candidate_source_page=False,
            updated_at=1,
            candidate_pdf_url=None,
            candidate_source_page_urls=[],
            candidate_discovery_provenances=[],
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
            blocked_reason=None,
            blocked_reason_detail=None,
            last_downloaded_file_path=None,
            last_final_page_url=None,
            onsite_capture_path=None,
            onsite_capture_format=None,
            onsite_page_count=None,
            onsite_completeness_status=None,
            attempts=1,
            verified_successes=1,
            last_n_outcomes=["downloaded"],
            confidence_score=1.0,
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=_get_route,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="unused",
        ),
        record_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not record sources")
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not update identity fields")
        ),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )

    with pytest.raises(AppError) as excinfo:
        run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert attempts["memory"] == 1
    assert attempts["discovery"] == 0
    assert_app_error(
        excinfo.value,
        code="browser_download_route_summary_invalid",
        retryable=False,
    )


def test_run_report_download_is_idempotent_for_route_memory(
    tmp_path: Path,
    run_context,
    idempotency_guard,
) -> None:
    settings = _settings(tmp_path)
    file_path = Path(settings.output_dir)
    file_path.mkdir(parents=True, exist_ok=True)
    pdf_path = file_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 idempotent")

    def _download(req, ctx):
        return _result(
            url="https://example.com/report",
            used_route_hint=bool(req.route_hint),
            path=str(pdf_path),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=get_publisher_download_route,
        record_publisher_download_route=record_publisher_download_route,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="idempotent-md5",
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )

    def _run_once():
        return run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=run_context,
            dependencies=deps,
        )

    def _route_count() -> int:
        conn = sqlite3.connect(settings.reports_db)
        try:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM publishers
                WHERE insights_url=?
                  AND download_route_summary IS NOT NULL
                """,
                ("https://example.com/report",),
            ).fetchone()
        finally:
            conn.close()
        return int(row[0] if row else 0)

    first, second = idempotency_guard(_run_once, side_effect_count=_route_count)
    assert first.outcome == "downloaded"
    assert second.outcome == "downloaded"


def test_run_report_download_reuses_idempotent_source_record_and_drive_upload(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    pdf_path = Path(settings.output_dir) / "report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7 idempotent upload")
    source_record_calls: list[object] = []
    upload_calls: list[object] = []

    def _record_source(req, ctx):
        source_record_calls.append(req)
        return ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=11,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        )

    def _upload_local_file(req, ctx):
        upload_calls.append(req)
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id="drive-file-1",
                name=req.file_name or Path(req.source_path).name,
                modified_time=None,
                md5_checksum="remote-md5",
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5="remote-md5",
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=str(pdf_path),
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=_record_source,
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        get_report_download_drive_folder=lambda req, ctx: (
            ReportDownloadDriveFolderLookupResponse(
                schema_version="1.0",
                publisher_name="Example",
                google_folder="folder123",
                resolution_source="publisher_insights_url",
            )
        ),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            files=[],
        ),
        upload_local_file=_upload_local_file,
    )

    first = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )
    second = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert first.outcome == "downloaded"
    assert second.outcome == "downloaded"
    assert len(source_record_calls) == 1
    assert len(upload_calls) == 1
    assert len(second.drive_uploads) == 1
    assert second.drive_uploads[0].status == "uploaded"
    assert second.drive_uploads[0].drive_file.file_id == "drive-file-1"


def test_run_report_download_drive_upload_idempotency_is_scoped_by_report_url(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    report_artifacts: dict[str, tuple[Path, Path, Path]] = {}
    for slug, payload in [("report-one", b"one"), ("report-two", b"two")]:
        artifact_dir = tmp_path / slug
        artifact_dir.mkdir(parents=True, exist_ok=True)
        onsite_path = artifact_dir / "onsite_capture.html"
        html_path = artifact_dir / "terminal_snapshot.html"
        screenshot_path = artifact_dir / "terminal_screenshot.png"
        onsite_path.write_bytes(b"<html>" + payload + b"</html>")
        html_path.write_bytes(b"<html>snapshot " + payload + b"</html>")
        screenshot_path.write_bytes(b"png-" + payload)
        report_artifacts[f"https://example.com/{slug}"] = (
            onsite_path,
            html_path,
            screenshot_path,
        )
    upload_calls: list[object] = []

    def _download(req, ctx):
        onsite_path, html_path, screenshot_path = report_artifacts[req.url]
        return _captured_result(
            url=req.url,
            onsite_path=str(onsite_path),
            html_snapshot_path=str(html_path),
            screenshot_path=str(screenshot_path),
        )

    def _upload_local_file(req, ctx):
        upload_calls.append(req)
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id=f"drive-file-{len(upload_calls)}",
                name=req.file_name or Path(req.source_path).name,
                modified_time=None,
                md5_checksum=_md5_for_path(Path(req.source_path)),
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5=_md5_for_path(Path(req.source_path)),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        get_report_download_drive_folder=lambda req, ctx: (
            ReportDownloadDriveFolderLookupResponse(
                schema_version="1.0",
                publisher_name="Example",
                google_folder="folder123",
                resolution_source="publisher_insights_url",
            )
        ),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            files=[],
        ),
        upload_local_file=_upload_local_file,
    )

    for url in report_artifacts:
        response = run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url=url,
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=run_context,
            dependencies=deps,
        )
        assert response.outcome == "captured"

    assert len(upload_calls) == 6
    assert [call.file_name for call in upload_calls].count(
        "terminal_screenshot.png"
    ) == 2


def test_run_report_download_idempotency_allows_changed_artifact_for_same_url(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    pdf_path = Path(settings.output_dir) / "report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    source_record_calls: list[object] = []
    upload_calls: list[object] = []

    def _record_source(req, ctx):
        source_record_calls.append(req)
        return ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=len(source_record_calls),
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        )

    def _upload_local_file(req, ctx):
        upload_calls.append(req)
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id=f"drive-file-{len(upload_calls)}",
                name=req.file_name or Path(req.source_path).name,
                modified_time=None,
                md5_checksum=_md5_for_path(Path(req.source_path)),
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5=_md5_for_path(Path(req.source_path)),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=str(pdf_path),
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=_record_source,
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        get_report_download_drive_folder=lambda req, ctx: (
            ReportDownloadDriveFolderLookupResponse(
                schema_version="1.0",
                publisher_name="Example",
                google_folder="folder123",
                resolution_source="publisher_insights_url",
            )
        ),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            files=[],
        ),
        upload_local_file=_upload_local_file,
    )

    for content in [b"%PDF-1.7 first", b"%PDF-1.7 second"]:
        pdf_path.write_bytes(content)
        response = run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=run_context,
            dependencies=deps,
        )
        assert response.outcome == "downloaded"

    assert len(source_record_calls) == 2
    assert len(upload_calls) == 2
    assert source_record_calls[0].md5 != source_record_calls[1].md5


def test_run_report_download_reuses_idempotent_route_record_and_identity_update(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    Path(settings.identity_config_path).write_text(
        "\n".join(
            [
                "schema_version: '1.0'",
                "fields:",
                "  - schema_version: '1.0'",
                "    key: work_email",
                "    label: Work email",
                "    value: ops@example.com",
                "    aliases:",
                "      - email",
                "delivery_emails: []",
                "publisher_overrides: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    route_record_calls: list[object] = []
    identity_update_calls: list[object] = []

    def _record_route(req, ctx):
        route_record_calls.append(req)
        return record_publisher_download_route(req, ctx)

    def _upsert_identity(req, ctx):
        identity_update_calls.append(req)
        return upsert_browser_download_identity_fields(req, ctx)

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=None,
        ),
        get_publisher_download_route=get_publisher_download_route,
        record_publisher_download_route=_record_route,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="unused-md5",
        ),
        record_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("email-required flow should not persist a report source")
        ),
        upsert_browser_download_identity_fields=_upsert_identity,
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )

    first = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )
    second = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert first.outcome == "email_required"
    assert second.outcome == "email_required"
    assert len(route_record_calls) == 1
    assert len(identity_update_calls) == 1

    with sqlite3.connect(settings.reports_db) as conn:
        publisher_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM publishers
            WHERE normalized_insights_url=?
              AND download_route_summary IS NOT NULL
            """,
            ("https://example.com/report",),
        ).fetchone()
        history_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM publisher_download_route_history
            WHERE normalized_url=?
            """,
            ("https://example.com/report",),
        ).fetchone()

    assert int(publisher_rows[0] if publisher_rows else 0) == 1
    assert int(history_rows[0] if history_rows else 0) == 1

    identity_yaml = Path(settings.identity_config_path).read_text(encoding="utf-8")
    assert "key: name" in identity_yaml
    assert "key: business" in identity_yaml


def test_run_report_download_does_not_record_source_for_email_outcome(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    source_record_calls: list[object] = []

    def _record_source(req, ctx):
        source_record_calls.append(req)
        return ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=None,
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="unused",
        ),
        record_report_source=_record_source,
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.outcome == "email_required"
    assert source_record_calls == []


def test_run_report_download_uploads_downloaded_pdf_to_publisher_drive_folder(
    tmp_path: Path,
    caplog,
    run_context,
    assert_logs_have_required_fields,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    pdf_path = Path(settings.output_dir) / "report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7 acquired")
    uploaded_requests = []

    def _upload_file(req, ctx):
        uploaded_requests.append(req)
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id="drive-file-1",
                name=req.file_name,
                modified_time="2026-04-22T00:00:00Z",
                md5_checksum=_md5_for_path(Path(req.source_path)),
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5=_md5_for_path(Path(req.source_path)),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=str(pdf_path),
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0", folder_id=req.folder_id, files=[]
        ),
        upload_local_file=_upload_file,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            publisher_google_folder="https://drive.google.com/drive/folders/folder123",
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.outcome == "downloaded"
    assert len(response.drive_uploads) == 1
    assert response.drive_uploads[0].folder_id == "folder123"
    assert response.drive_uploads[0].status == "uploaded"
    assert response.drive_uploads[0].drive_file.file_id == "drive-file-1"
    assert uploaded_requests[0].source_path == str(pdf_path)
    assert uploaded_requests[0].mime_type == "application/pdf"
    assert_logs_have_required_fields(
        _events(caplog, "market_lense.report_download_orchestrator")
    )


def test_run_report_download_uploads_all_captured_terminal_artifacts(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    artifact_dir = Path(settings.output_dir)
    onsite_path = artifact_dir / "onsite_capture.html"
    html_snapshot_path = artifact_dir / "terminal.html"
    screenshot_path = artifact_dir / "terminal.png"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    onsite_path.write_text("<html>onsite</html>", encoding="utf-8")
    html_snapshot_path.write_text("<html>terminal</html>", encoding="utf-8")
    screenshot_path.write_bytes(b"png-bytes")
    uploaded_paths: list[str] = []

    def _upload_file(req, ctx):
        uploaded_paths.append(req.source_path)
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id=f"drive-{Path(req.source_path).stem}",
                name=req.file_name,
                modified_time="2026-04-22T00:00:00Z",
                md5_checksum=_md5_for_path(Path(req.source_path)),
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5=_md5_for_path(Path(req.source_path)),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _captured_result(
            url="https://example.com/report",
            onsite_path=str(onsite_path),
            html_snapshot_path=str(html_snapshot_path),
            screenshot_path=str(screenshot_path),
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("captured reports should not record PDF sources")
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        get_report_download_drive_folder=lambda req, ctx: (
            ReportDownloadDriveFolderLookupResponse(
                schema_version="1.0",
                publisher_name="Example Publisher",
                google_folder="folder456",
                resolution_source="publisher_insights_url",
            )
        ),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0", folder_id=req.folder_id, files=[]
        ),
        upload_local_file=_upload_file,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            publisher_insights_url="https://example.com/insights",
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.outcome == "captured"
    assert uploaded_paths == [
        str(onsite_path),
        str(html_snapshot_path),
        str(screenshot_path),
    ]
    assert [item.status for item in response.drive_uploads] == [
        "uploaded",
        "uploaded",
        "uploaded",
    ]
    assert response.drive_uploads[0].mime_type == "text/html"
    assert response.drive_uploads[1].mime_type == "text/html"
    assert response.drive_uploads[2].mime_type == "image/png"


def test_run_report_download_deduplicates_equivalent_drive_artifact_paths(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    pdf_path = Path(settings.output_dir) / "report.pdf"
    redundant_dir = pdf_path.parent / "redundant"
    redundant_dir.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7 rendered onsite report")
    equivalent_pdf_path = redundant_dir / ".." / pdf_path.name
    uploaded_paths: list[str] = []

    def _upload_file(req, ctx):
        uploaded_paths.append(req.source_path)
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id="drive-report",
                name=req.file_name,
                modified_time="2026-04-22T00:00:00Z",
                md5_checksum=_md5_for_path(Path(req.source_path)),
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5=_md5_for_path(Path(req.source_path)),
        )

    def _download(req, ctx):
        return replace(
            _result(
                url="https://example.com/year-in-review",
                used_route_hint=False,
                path=str(pdf_path),
            ),
            onsite_capture_path=str(equivalent_pdf_path),
            onsite_capture_format="browser_rendered_pdf",
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        get_report_download_drive_folder=lambda req, ctx: (
            ReportDownloadDriveFolderLookupResponse(
                schema_version="1.0",
                publisher_name="Example Publisher",
                google_folder="folder456",
                resolution_source="publisher_insights_url",
            )
        ),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0", folder_id=req.folder_id, files=[]
        ),
        upload_local_file=_upload_file,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/year-in-review",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            publisher_insights_url="https://example.com/insights",
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert uploaded_paths == [str(pdf_path)]
    assert len(response.drive_uploads) == 1
    assert response.drive_uploads[0].file_name == "report.pdf"


def test_run_report_download_skips_duplicate_drive_file_by_name_and_md5(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    pdf_path = Path(settings.output_dir) / "report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7 duplicate")
    md5 = _md5_for_path(pdf_path)
    upload_calls: list[object] = []

    def _upload_file(req, ctx):
        upload_calls.append(req)
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id="unexpected-upload",
                name=req.file_name,
                modified_time="2026-04-22T00:00:00Z",
                md5_checksum=md5,
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5=md5,
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=str(pdf_path),
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0", path=req.path, md5=md5
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            files=[
                DriveFile(
                    schema_version="1.0",
                    file_id="existing-drive-file",
                    name="report.pdf",
                    modified_time="2026-04-22T00:00:00Z",
                    md5_checksum=md5,
                    mime_type="application/pdf",
                )
            ],
        ),
        upload_local_file=_upload_file,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            publisher_google_folder="folder123",
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert upload_calls == []
    assert response.drive_uploads[0].status == "skipped_duplicate"
    assert response.drive_uploads[0].drive_file.file_id == "existing-drive-file"


def test_run_report_download_requires_drive_folder_when_upload_enabled(
    tmp_path: Path,
    run_context,
    assert_app_error,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    pdf_path = Path(settings.output_dir) / "report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7 missing folder")
    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=str(pdf_path),
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        get_report_download_drive_folder=lambda req, ctx: None,
    )

    with pytest.raises(AppError) as excinfo:
        run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert_app_error(
        excinfo.value,
        code="report_download_drive_folder_missing",
        retryable=False,
    )


def test_run_report_download_retries_and_propagates_drive_upload_failure(
    tmp_path: Path,
    run_context,
    assert_app_error,
) -> None:
    settings = replace(
        _drive_enabled_settings(_settings(tmp_path)),
        retry_retries=1,
        retry_base_delay_seconds=0.1,
        retry_backoff_step_seconds=0.0,
        retry_jitter_seconds=0.0,
    )
    pdf_path = Path(settings.output_dir) / "report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7 upload failure")
    upload_attempts: list[str] = []
    sleep_calls: list[float] = []

    def _upload_file(req, ctx):
        upload_attempts.append(req.source_path)
        raise AppError(
            code="drive_upload_failed",
            message="Drive upload failed",
            retryable=True,
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=str(pdf_path),
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: sleep_calls.append(float(seconds)),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0", folder_id=req.folder_id, files=[]
        ),
        upload_local_file=_upload_file,
    )

    with pytest.raises(AppError) as excinfo:
        run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                publisher_google_folder="folder123",
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert upload_attempts == [str(pdf_path), str(pdf_path)]
    assert sleep_calls == [0.1]
    assert_app_error(excinfo.value, code="drive_upload_failed", retryable=True)


def test_run_report_download_prefers_candidate_pdf_before_generic_browser(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    requests_seen = []
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://example.com/report",
        title="Discovery PDF",
        discovered_on_page_number=1,
        source_page_urls=["https://example.com/insights"],
        discovery_provenances=["direct_pdf_source"],
        pdf_url="https://cdn.example.com/discovery-report.pdf",
        published_at_text=None,
        max_confidence=0.95,
    )

    def _download(req, ctx):
        requests_seen.append(req)
        return _result(
            url=req.url,
            used_route_hint=False,
            path=str(Path(settings.output_dir) / "report.pdf"),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="abc123",
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            candidate_trace=candidate_trace,
            publisher_discovery_route_kind="browser_render",
            publisher_recommended_discovery_route_kind="http_parse",
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.outcome == "downloaded"
    assert len(requests_seen) == 1
    assert (
        requests_seen[0].attempt_url == "https://cdn.example.com/discovery-report.pdf"
    )
    assert requests_seen[0].route_family_hint == "direct_pdf_probe"


def test_run_report_download_rejects_non_report_candidate_with_typed_reason(
    tmp_path: Path,
    caplog,
    run_context,
    assert_logs_have_required_fields,
    assert_app_error,
) -> None:
    settings = _settings(tmp_path)
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://example.com/support/customer-story",
        title="Customer Story",
        discovered_on_page_number=1,
        source_page_urls=["https://example.com/support"],
        discovery_provenances=["browser_dom"],
        pdf_url=None,
        published_at_text=None,
        max_confidence=0.2,
    )
    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should reject before browser execution")
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not hash files")
        ),
        record_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not record sources")
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not update identity")
        ),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    with pytest.raises(AppError) as excinfo:
        run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url=candidate_trace.canonical_url,
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                candidate_trace=candidate_trace,
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert_app_error(
        excinfo.value,
        code="report_download_candidate_rejected_non_report",
        retryable=False,
    )
    events = _events(caplog, "market_lense.report_download_orchestrator")
    assert_logs_have_required_fields(events)
    readiness_events = [
        event
        for event in events
        if event["event"] == "report_download_readiness_rejected"
    ]
    assert len(readiness_events) == 1
    assert (
        readiness_events[0]["fields"]["readiness_rejection_reason"]
        == "candidate_rejected_non_report"
    )
    assert readiness_events[0]["fields"]["download_readiness_score"] < 0.35


def test_run_report_download_allows_report_like_resource_candidates(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    candidates = [
        PublisherInventoryCandidateTrace(
            schema_version="1.0",
            canonical_url="https://www.centricsoftware.com/whitepapers/new-growth-playbook-swimwear-lingerie",
            title="New Growth Playbook",
            discovered_on_page_number=1,
            source_page_urls=["https://www.centricsoftware.com/learning-tools"],
            discovery_provenances=[],
            pdf_url=None,
            published_at_text=None,
            max_confidence=None,
        ),
        PublisherInventoryCandidateTrace(
            schema_version="1.0",
            canonical_url="https://impact.com/commerce-content/guide-to-building-a-high-performance-content-operation",
            title="The B2B Guide to Building a High-Performance Content Operations Workflow",
            discovered_on_page_number=18,
            source_page_urls=[
                "https://impact.com/search?ft%5B0%5D=infographic&ft%5B1%5D=report&pg=18"
            ],
            discovery_provenances=[],
            pdf_url=None,
            published_at_text=None,
            max_confidence=None,
        ),
        PublisherInventoryCandidateTrace(
            schema_version="1.0",
            canonical_url="https://business.adobe.com/resources/sdk/the-state-of-personalization-maturity-in-travel-and-dining.html",
            title="Digital-first travel brands drive more personalization",
            discovered_on_page_number=14,
            source_page_urls=[
                "https://business.adobe.com/resources/reports.html?page=14"
            ],
            discovery_provenances=[],
            pdf_url=None,
            published_at_text=None,
            max_confidence=None,
        ),
    ]
    seen_urls: list[str] = []

    def _download(req, ctx):
        seen_urls.append(req.url)
        return _result(
            url=req.url,
            used_route_hint=False,
            path=str(Path(settings.output_dir) / "report.pdf"),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="abc123",
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )

    for candidate_trace in candidates:
        response = run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url=candidate_trace.canonical_url,
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                candidate_trace=candidate_trace,
            ),
            ctx=run_context,
            dependencies=deps,
        )
        assert response.outcome == "downloaded"

    assert seen_urls == [candidate.canonical_url for candidate in candidates]


def test_run_report_download_allows_thin_candidate_when_pdf_url_is_present(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://example.com/landing",
        title="Landing page",
        discovered_on_page_number=1,
        source_page_urls=["https://example.com/resources"],
        discovery_provenances=["direct_pdf_source"],
        pdf_url="https://cdn.example.com/report.pdf",
        published_at_text=None,
        max_confidence=0.1,
    )
    seen_requests = []

    def _download(req, ctx):
        seen_requests.append(req)
        return _result(
            url=req.url,
            used_route_hint=False,
            path=str(Path(settings.output_dir) / "report.pdf"),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="abc123",
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url=candidate_trace.canonical_url,
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            candidate_trace=candidate_trace,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.outcome == "downloaded"
    assert seen_requests[0].attempt_url == candidate_trace.pdf_url
    assert seen_requests[0].candidate_trace == candidate_trace


def test_run_report_download_promotes_verified_browser_route_playbook_idempotently(
    tmp_path: Path,
    caplog,
    run_context,
    assert_logs_have_required_fields,
) -> None:
    playbook_dir = tmp_path / "playbooks"
    settings = replace(
        _settings(tmp_path),
        route_playbook_dir=str(playbook_dir),
        route_playbook_promotion_mode="write",
    )
    pdf_path = Path(settings.output_dir) / "browser-report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4\nbrowser route\n%%EOF")
    browser_result = replace(
        _result(
            url="https://example.com/reports/annual-market-report",
            used_route_hint=False,
            path=str(pdf_path),
        ),
        route_family="browser_pdf_click",
        browser_had_structured_result=True,
    )
    download_calls: list[str] = []

    def _download(req, ctx):
        download_calls.append(req.url)
        return browser_result

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=get_publisher_download_route,
        record_publisher_download_route=record_publisher_download_route,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    request = ReportDownloadOrchestratorRequest(
        schema_version="1.0",
        url=browser_result.source_url,
        settings=settings,
        state_db=settings.state_db,
        reports_db=settings.reports_db,
    )
    first = run_report_download(request, ctx=run_context, dependencies=deps)
    second = run_report_download(request, ctx=run_context, dependencies=deps)

    assert first.outcome == "downloaded"
    assert second.outcome == "downloaded"
    assert download_calls == [browser_result.source_url, browser_result.source_url]
    playbook_path = playbook_dir / "learned-example-com-browser-pdf-click.yaml"
    payload = yaml.safe_load(playbook_path.read_text(encoding="utf-8"))
    assert payload["version"] == "1.0.0"
    assert payload["route_family"] == "browser_pdf_click"
    assert payload["route_kind"] == "pdf_download"
    assert payload["steps"][0]["action"] == "open"
    assert len(payload["history"]) == 1

    events = _events(caplog, "market_lense.report_download_orchestrator")
    assert_logs_have_required_fields(events)
    promotion_events = [
        event
        for event in events
        if event["event"] == "report_download_route_playbook_promotion_evaluated"
    ]
    assert promotion_events[0]["fields"]["promotion_mode"] == "write"
    assert promotion_events[0]["fields"]["promotion_status"] == "created"
    assert promotion_events[0]["fields"]["review_diff_line_count"] > 0
    assert any(
        event["fields"].get("skip_reason") == "route_record_idempotency_reused"
        for event in promotion_events
    )


def test_run_report_download_skips_unverified_browser_route_playbook_promotion(
    tmp_path: Path,
    caplog,
    run_context,
) -> None:
    settings = replace(
        _settings(tmp_path),
        route_playbook_dir=str(tmp_path / "playbooks"),
        route_playbook_promotion_mode="write",
    )
    pdf_path = Path(settings.output_dir) / "browser-report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4\nunverified route\n%%EOF")
    unverified_result = replace(
        _result(
            url="https://example.com/reports/unverified",
            used_route_hint=False,
            path=str(pdf_path),
        ),
        route_family="browser_pdf_click",
        route_status="inferred",
        browser_had_structured_result=True,
    )
    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: unverified_result,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url=unverified_result.source_url,
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.outcome == "downloaded"
    assert not (
        Path(settings.route_playbook_dir) / "learned-example-com-browser-pdf-click.yaml"
    ).exists()
    events = _events(caplog, "market_lense.report_download_orchestrator")
    promotion_events = [
        event
        for event in events
        if event["event"] == "report_download_route_playbook_promotion_evaluated"
    ]
    assert promotion_events[-1]["fields"]["promotion_mode"] == "write"
    assert promotion_events[-1]["fields"]["skip_reason"] == "unverified_route_status"
