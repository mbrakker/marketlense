# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


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
    saved_source_identity_observations = []

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
            updated_at=_fresh_route_memory_updated_at(),
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

    def _record_source_identity_observation(req, ctx):
        saved_source_identity_observations.append(req)
        return SimpleNamespace(
            created=True,
            resolution=SimpleNamespace(
                identity_status="complete",
                publication_date_status="unknown",
                source_metadata_hash="source-metadata-hash",
            ),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=_get_route,
        record_publisher_download_route=_record_route,
        file_md5=_file_md5,
        record_report_source=_record_source,
        upsert_browser_download_identity_fields=_upsert_identity,
        record_source_identity_observation=_record_source_identity_observation,
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
    assert len(saved_source_identity_observations) == 1
    observation = saved_source_identity_observations[0].observation
    assert observation.source_record_id == 1
    assert observation.acquisition_route == "pdf_download"
    assert observation.content_hash == "md5:abc123"
    assert observation.publication_date_status == "unknown"
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


def test_private_api_observation_app_error_does_not_abort_successful_download_side_path(
    tmp_path: Path,
    caplog,
    run_context,
) -> None:
    def _record_candidate(req, ctx):
        raise AppError(
            code="private_api_candidate_record_failed",
            message="fixture ledger failure",
            retryable=True,
            severity="error",
        )

    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")
    _evaluate_private_api_side_path(
        tmp_path,
        run_context,
        _private_api_promotion_dependencies(
            tmp_path,
            record_candidate=_record_candidate,
            mark_promoted=lambda req, ctx: None,
        ),
    )

    events = [
        event
        for event in _events(caplog, "market_lense.report_download_orchestrator")
        if event.get("event") == "report_download_private_api_promotion_evaluated"
    ]
    assert events[-1]["fields"]["skip_reason"] == "candidate_observation_app_error"
    assert events[-1]["fields"]["error_code"] == "private_api_candidate_record_failed"


def test_private_api_promotion_mark_app_error_does_not_abort_successful_download_side_path(
    tmp_path: Path,
    caplog,
    run_context,
) -> None:
    def _mark_promoted(req, ctx):
        raise AppError(
            code="private_api_candidate_mark_failed",
            message="fixture promotion marker failure",
            retryable=True,
            severity="error",
        )

    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")
    _evaluate_private_api_side_path(
        tmp_path,
        run_context,
        _private_api_promotion_dependencies(
            tmp_path,
            record_candidate=lambda req, ctx: (
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
            mark_promoted=_mark_promoted,
        ),
    )

    events = [
        event
        for event in _events(caplog, "market_lense.report_download_orchestrator")
        if event.get("event") == "report_download_private_api_promotion_evaluated"
    ]
    assert events[-1]["fields"]["skip_reason"] == "promotion_mark_app_error"
    assert events[-1]["fields"]["error_code"] == "private_api_candidate_mark_failed"


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


__all__ = [
    "test_route_plan_recovery_classes_cover_allowed_blocked_and_deferred",
    "test_run_report_download_rejects_mixed_content_hub_candidate",
    "test_run_report_download_uses_memory_and_records_route",
    "test_run_report_download_auto_promotes_private_api_after_threshold",
    "test_private_api_observation_app_error_does_not_abort_successful_download_side_path",
    "test_private_api_promotion_mark_app_error_does_not_abort_successful_download_side_path",
    "test_run_report_download_falls_back_after_memory_failure_and_retries",
]
