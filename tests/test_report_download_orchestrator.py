from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import pytest

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadRouteStep,
    BrowserDownloadSettings,
    BrowserReportDownloadResult,
    DownloadTerminalEvidence,
    ReportDownloadOrchestratorRequest,
)
from src.contracts.files import FileHashResponse
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.contracts.report_store import (
    PublisherDownloadRouteResponse,
    ReportSourceRecordResponse,
)
from src.orchestrators.report_download_orchestrator import (
    ReportDownloadDependencies,
    run_report_download,
)
from src.services.report_store_service import (
    get_publisher_download_route,
    record_publisher_download_route,
)
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


def _events(caplog, logger_name: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != logger_name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


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


def test_run_report_download_does_not_record_source_for_email_outcome(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    source_record_calls: list[object] = []

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
        record_report_source=lambda req, ctx: source_record_calls.append(req),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
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
    assert requests_seen[0].attempt_url == "https://cdn.example.com/discovery-report.pdf"
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
        event for event in events if event["event"] == "report_download_readiness_rejected"
    ]
    assert len(readiness_events) == 1
    assert readiness_events[0]["fields"]["readiness_rejection_reason"] == "candidate_rejected_non_report"
    assert readiness_events[0]["fields"]["download_readiness_score"] < 0.35


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
    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: seen_requests.append(req)
        or _result(
            url=req.url,
            used_route_hint=False,
            path=str(Path(settings.output_dir) / "report.pdf"),
        ),
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
