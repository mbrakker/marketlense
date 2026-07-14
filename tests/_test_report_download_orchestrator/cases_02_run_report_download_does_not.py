# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_run_report_download_retries_timed_out_browser_step(
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
    assert browser_calls == ["browser_pdf_click", "browser_pdf_click"]
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
    assert len(browser_retry_events) == 1
    assert browser_retry_events[0]["fields"]["error_retryable"] is True
    assert failure_events
    assert failure_events[-1]["fields"]["code"] == "browser_download_agent_timeout"
    assert failure_events[-1]["fields"]["retryable"] is True


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


def test_run_report_download_retries_then_falls_back_after_memory_browser_timeout(
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
            updated_at=_fresh_route_memory_updated_at(),
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
        ),
        (
            "browser_onsite_report",
            "Accept cookies and extract the on-site report.",
            2,
        ),
        ("http_pdf_probe", None, 0),
        ("http_pdf_probe", None, 0),
        ("browser_pdf_click", None, 0),
        ("browser_pdf_click", None, 0),
    ]
    step_failed_events = [
        event
        for event in _events(caplog, "market_lense.report_download_orchestrator")
        if event.get("event") == "report_download_step_failed"
    ]
    assert len(step_failed_events) == 3
    assert (
        step_failed_events[0]["fields"]["step_name"]
        == "report_download_with_memory_route"
    )
    assert step_failed_events[0]["fields"]["attempt_retryable"] is True
    assert step_failed_events[0]["fields"]["fallback_on_retryable_error"] is True
    assert (
        step_failed_events[-1]["fields"]["step_name"]
        == "report_download_browser_candidate"
    )
    assert step_failed_events[-1]["fields"]["attempt_retryable"] is True
    assert step_failed_events[-1]["fields"]["fallback_on_retryable_error"] is False


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
            updated_at=_fresh_route_memory_updated_at(),
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


__all__ = [
    "test_run_report_download_retries_timed_out_browser_step",
    "test_run_report_download_does_not_retry_failed_http_probe_before_browser_fallback",
    "test_run_report_download_persists_failure_forensics_pack",
    "test_run_report_download_retries_then_falls_back_after_memory_browser_timeout",
    "test_run_report_download_does_not_retry_weak_browser_route_summary",
    "test_run_report_download_does_not_fallback_after_non_retryable_memory_failure",
]
