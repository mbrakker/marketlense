# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

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
        preflight_drive_write_access=_successful_drive_preflight,
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

__all__ = [
    "test_run_report_download_requires_drive_folder_when_upload_enabled",
    "test_run_report_download_retries_and_propagates_drive_upload_failure",
    "test_run_report_download_prefers_candidate_pdf_before_generic_browser",
    "test_run_report_download_rejects_non_report_candidate_with_typed_reason",
    "test_run_report_download_allows_report_like_resource_candidates",
    "test_run_report_download_allows_thin_candidate_when_pdf_url_is_present",
    "test_run_report_download_promotes_verified_browser_route_playbook_idempotently",
    "test_run_report_download_skips_unverified_browser_route_playbook_promotion",
]
