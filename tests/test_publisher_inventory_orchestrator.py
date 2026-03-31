from __future__ import annotations

import json
import logging

import pytest

from src.contracts.drive import DriveDownloadResponse, DriveFile, DriveFolderFileListResponse, DriveUploadBytesResponse
from src.contracts.publisher_inventory import (
    PublisherInventoryBuildRequest,
    PublisherInventoryCandidateQualityDecision,
    PublisherInventoryCandidateQualityResponse,
    PublisherInventoryCandidateScreeningDecision,
    PublisherInventoryCandidateScreeningItem,
    PublisherInventoryCandidateScreeningResponse,
    PublisherInventoryDiscoveryRequest,
    PublisherInventoryPage,
    PublisherInventoryQualifiedCandidateItem,
    PublisherInventoryRawCandidate,
    PublisherInventoryServiceResponse,
    PublisherInventorySettings,
)
from src.contracts.report_store import (
    PublisherInventoryStateResponse,
    ReportSourceDiscoveryRecordResponse,
)
from src.orchestrators.publisher_inventory_orchestrator import (
    PublisherInventoryDependencies,
    run_publisher_inventory_discovery,
)
from src.utils.errors import AppError


def _settings() -> PublisherInventorySettings:
    return PublisherInventorySettings(
        schema_version="1.0",
        openrouter_api_key="openrouter-key",
        model="openai/gpt-5-mini",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=5,
        output_dir="./out/publisher_inventory_discovery",
        reports_db="./state/reports.sqlite",
        google_sa_path="./sa.json",
        prompt_namespace="publisher_inventory/discovery",
        pagination_max_pages=5,
        http_timeout_seconds=10.0,
        openrouter_http_referer=None,
        headed=False,
        retry_retries=1,
        retry_base_delay_seconds=0.0,
        retry_backoff_step_seconds=0.0,
        retry_jitter_seconds=0.0,
        openai_api_key="openai-key",
        candidate_screening_enabled=True,
        candidate_screening_model="gpt-5-nano",
        candidate_screening_temperature=1.0,
        candidate_screening_timeout_seconds=30.0,
        candidate_screening_prompt_namespace="publisher_inventory/meaningful_candidate_screen",
    )


def _publisher_state(
    *,
    with_route: bool = False,
    with_snapshot: bool = False,
    with_folder: bool = True,
    snapshot_sha256: str = "old-sha",
):
    return PublisherInventoryStateResponse(
        schema_version="1.0",
        publisher_name="Activate Consulting",
        insights_url="https://www.activate.com/insights",
        normalized_url="https://www.activate.com/insights",
        google_folder="https://drive.google.com/drive/folders/folder123" if with_folder else None,
        discovery_test_status=None,
        inventory_route_kind="browser_render" if with_route else None,
        inventory_route_summary="Open page 1, click next, extract cards." if with_route else None,
        inventory_route_last_final_page_url="https://www.activate.com/insights?page=2" if with_route else None,
        inventory_route_updated_at=1 if with_route else None,
        inventory_snapshot_drive_file_id="snapshot-1" if with_snapshot else None,
        inventory_snapshot_drive_file_name="publisher_inventory_snapshot__20260328T000000Z.json" if with_snapshot else None,
        inventory_snapshot_sha256=snapshot_sha256 if with_snapshot else None,
        inventory_snapshot_updated_at=1 if with_snapshot else None,
    )


def _service_response(
    *, used_route_hint: bool, new_url: str, title: str = "New Report"
) -> PublisherInventoryServiceResponse:
    return PublisherInventoryServiceResponse(
        schema_version="1.0",
        source_url="https://www.activate.com/insights",
        normalized_url="https://www.activate.com/insights",
        route_kind="browser_render",
        route_summary="Open page 1, click next, extract cards.",
        final_page_url="https://www.activate.com/insights?page=2",
        used_route_hint=used_route_hint,
        pages=[
            PublisherInventoryPage(schema_version="1.0", page_number=1, page_url="https://www.activate.com/insights"),
            PublisherInventoryPage(schema_version="1.0", page_number=2, page_url="https://www.activate.com/insights?page=2"),
        ],
        candidates=[
            PublisherInventoryRawCandidate(
                schema_version="1.0",
                url=new_url,
                title=title,
                source_page_url="https://www.activate.com/insights?page=2",
                discovered_on_page_number=2,
            )
        ],
    )


def _screening_response(*, accepted_urls: set[str], request) -> PublisherInventoryCandidateScreeningResponse:
    approved_items = [
        candidate
        for candidate in request.candidates
        if candidate.canonical_url in accepted_urls
    ]
    rejected_items = [
        candidate
        for candidate in request.candidates
        if candidate.canonical_url not in accepted_urls
    ]
    decisions = [
        PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=candidate.canonical_url in accepted_urls,
            reason=(
                "meaningful report asset"
                if candidate.canonical_url in accepted_urls
                else "non-report candidate"
            ),
        )
        for candidate in request.candidates
    ]
    return PublisherInventoryCandidateScreeningResponse(
        schema_version="1.0",
        approved_items=approved_items,
        rejected_items=rejected_items,
        decisions=decisions,
        model="gpt-5-nano",
        request_id="req-screen-1",
        raw_response='{"decisions":[]}',
    )


def _quality_response(*, accepted_urls: set[str], request) -> PublisherInventoryCandidateQualityResponse:
    approved_items = []
    rejected_items = []
    decisions = []
    for candidate in request.candidates:
        accepted = candidate.canonical_url in accepted_urls
        title = "Resolved New Report" if accepted else candidate.title
        item = PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            title=title,
            discovered_on_page_number=candidate.discovered_on_page_number,
            source_page_url=candidate.source_page_url,
        )
        if accepted:
            approved_items.append(
                PublisherInventoryQualifiedCandidateItem(
                    schema_version="1.0",
                    canonical_url=item.canonical_url,
                    title=item.title,
                    discovered_on_page_number=item.discovered_on_page_number,
                    source_page_url=item.source_page_url,
                )
            )
        else:
            rejected_items.append(
                PublisherInventoryQualifiedCandidateItem(
                    schema_version="1.0",
                    canonical_url=item.canonical_url,
                    title=item.title,
                    discovered_on_page_number=item.discovered_on_page_number,
                    source_page_url=item.source_page_url,
                )
            )
        decisions.append(
            PublisherInventoryCandidateQualityDecision(
                schema_version="1.0",
                canonical_url=candidate.canonical_url,
                accepted=accepted,
                reason=(
                    "qualified_report_asset"
                    if accepted
                    else "editorial_article_page"
                ),
                resolved_title=title,
            )
        )
    return PublisherInventoryCandidateQualityResponse(
        schema_version="1.0",
        approved_items=approved_items,
        rejected_items=rejected_items,
        decisions=decisions,
    )


def _snapshot_json(url: str) -> str:
    payload = {
        "schema_version": "1.0",
        "publisher_name": "Activate Consulting",
        "insights_url": "https://www.activate.com/insights",
        "normalized_insights_url": "https://www.activate.com/insights",
        "discovered_at_utc": "2026-03-28T00:00:00Z",
        "route_kind": "browser_render",
        "route_summary": "Open page 1, click next, extract cards.",
        "final_page_url": "https://www.activate.com/insights?page=2",
        "pages": [
            {"schema_version": "1.0", "page_number": 1, "page_url": "https://www.activate.com/insights"},
        ],
        "items": [
            {
                "schema_version": "1.0",
                "canonical_url": url,
                "title": "Existing Report",
                "discovered_on_page_number": 1,
                "pdf_url": None,
                "published_at_text": None,
            }
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _snapshot_sha256(url: str, run_context) -> str:
    return __import__(
        "src.generators.publisher_inventory_generator",
        fromlist=["build_publisher_inventory_snapshot"],
    ).build_publisher_inventory_snapshot(
        PublisherInventoryBuildRequest(
            schema_version="1.0",
            publisher_name="Activate Consulting",
            insights_url="https://www.activate.com/insights",
            normalized_insights_url="https://www.activate.com/insights",
            discovered_at_utc="2026-03-28T00:00:00Z",
            route_kind="browser_render",
            route_summary="Open page 1, click next, extract cards.",
            final_page_url="https://www.activate.com/insights?page=2",
            pages=[
                PublisherInventoryPage(
                    schema_version="1.0",
                    page_number=1,
                    page_url="https://www.activate.com/insights",
                )
            ],
            candidates=[
                PublisherInventoryRawCandidate(
                    schema_version="1.0",
                    url=url,
                    title="Existing Report",
                    source_page_url="https://www.activate.com/insights",
                    discovered_on_page_number=1,
                )
            ],
        ),
        run_context,
    ).snapshot_sha256


def _events(caplog, logger_name: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != logger_name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _dependencies(**overrides) -> PublisherInventoryDependencies:
    defaults = {
        "discover_publisher_inventory": lambda req, ctx: _service_response(
            used_route_hint=False,
            new_url="https://www.activate.com/reports/new-report",
        ),
        "build_publisher_inventory_snapshot": lambda req, ctx: __import__(
            "src.generators.publisher_inventory_generator",
            fromlist=["build_publisher_inventory_snapshot"],
        ).build_publisher_inventory_snapshot(req, ctx),
        "parse_publisher_inventory_snapshot": lambda payload, source, ctx: __import__(
            "src.generators.publisher_inventory_generator",
            fromlist=["parse_publisher_inventory_snapshot"],
        ).parse_publisher_inventory_snapshot(payload, source=source, ctx=ctx),
        "screen_publisher_inventory_candidates": lambda req, ctx: _screening_response(
            accepted_urls={"https://www.activate.com/reports/new-report"},
            request=req,
        ),
        "qualify_publisher_inventory_candidates": lambda req, ctx: _quality_response(
            accepted_urls={"https://www.activate.com/reports/new-report"},
            request=req,
        ),
        "get_publisher_inventory_state": lambda req, ctx: _publisher_state(
            with_route=False, with_snapshot=False
        ),
        "record_publisher_inventory_state": lambda req, ctx: None,
        "record_publisher_inventory_test_status": lambda req, ctx: None,
        "record_discovered_report_source": lambda req, ctx: ReportSourceDiscoveryRecordResponse(
            schema_version="1.0",
            record_id=1,
            publisher_name=req.publisher_name,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            source_page_url=req.source_page_url,
            discovered_at_utc=req.discovered_at_utc,
            discovered_on_page_number=req.discovered_on_page_number,
            created_new=True,
        ),
        "list_files_in_folder": lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0", folder_id=req.folder_id, files=[]
        ),
        "download_pdf": lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not download snapshot")
        ),
        "upload_bytes": lambda req, ctx: DriveUploadBytesResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id="drive-file-1",
                name=req.file_name,
                modified_time=None,
                md5_checksum=None,
                mime_type="application/json",
            ),
            size=len(req.content),
            md5="abc123",
        ),
    }
    defaults.update(overrides)
    return PublisherInventoryDependencies(**defaults)


def test_run_publisher_inventory_discovery_first_run_uploads_snapshot_and_returns_diff(
    run_context,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
):
    uploads = []
    records = []
    status_records = []
    source_records = []

    deps = _dependencies(
        record_publisher_inventory_state=lambda req, ctx: records.append(req),
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(req),
        record_discovered_report_source=lambda req, ctx: (
            source_records.append(req)
            or ReportSourceDiscoveryRecordResponse(
                schema_version="1.0",
                record_id=1,
                publisher_name=req.publisher_name,
                source_domain=req.source_domain,
                report_name=req.report_name,
                landing_page_url=req.landing_page_url,
                source_page_url=req.source_page_url,
                discovered_at_utc=req.discovered_at_utc,
                discovered_on_page_number=req.discovered_on_page_number,
                created_new=True,
            )
        ),
        upload_bytes=lambda req, ctx: (
            uploads.append(req)
            or DriveUploadBytesResponse(
                schema_version="1.0",
                file=DriveFile(
                    schema_version="1.0",
                    file_id="drive-file-1",
                    name=req.file_name,
                    modified_time=None,
                    md5_checksum=None,
                    mime_type="application/json",
                ),
                size=len(req.content),
                md5="abc123",
            )
        ),
    )
    caplog.set_level(logging.INFO, logger="market_lense.publisher_inventory_orchestrator")

    result = run_publisher_inventory_discovery(
        PublisherInventoryDiscoveryRequest(
            schema_version="1.0",
            insights_url="https://www.activate.com/insights",
            reports_db="./state/reports.sqlite",
            settings=_settings(),
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.publisher_name == "Activate Consulting"
    assert result.snapshot_changed is True
    assert result.used_memory_route is False
    assert len(result.new_report_urls) == 1
    assert result.new_report_urls[0].discovered_on_page_number == 2
    assert len(uploads) == 1
    assert len(records) == 1
    assert [record.status for record in status_records] == ["passed"]
    assert len(source_records) == 1
    assert source_records[0].landing_page_url == "https://www.activate.com/reports/new-report"
    assert source_records[0].report_name == "Resolved New Report"
    assert source_records[0].source_page_url == "https://www.activate.com/insights?page=2"
    assert_no_defaulted_required_fields(result)
    assert_logs_have_required_fields(
        _events(caplog, "market_lense.publisher_inventory_orchestrator")
    )


def test_run_publisher_inventory_discovery_falls_back_after_memory_route_failure(
    run_context,
):
    attempts = {"memory": 0, "fresh": 0}

    def _discover(req, ctx):
        if req.route_hint:
            attempts["memory"] += 1
            raise AppError(
                code="publisher_inventory_browser_failed",
                message="stale route",
                retryable=True,
            )
        attempts["fresh"] += 1
        return _service_response(
            used_route_hint=False,
            new_url="https://www.activate.com/reports/new-report",
        )

    deps = _dependencies(
        discover_publisher_inventory=_discover,
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=True, with_snapshot=False
        ),
    )

    result = run_publisher_inventory_discovery(
        PublisherInventoryDiscoveryRequest(
            schema_version="1.0",
            insights_url="https://www.activate.com/insights",
            reports_db="./state/reports.sqlite",
            settings=_settings(),
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert attempts["memory"] >= 1
    assert attempts["fresh"] == 1
    assert result.used_memory_route is False


def test_run_publisher_inventory_discovery_records_failed_test_status(
    run_context,
):
    status_records = []

    deps = _dependencies(
        discover_publisher_inventory=lambda req, ctx: (_ for _ in ()).throw(
            AppError(
                code="publisher_inventory_browser_pagination_limit",
                message="deep archive limit reached",
                retryable=True,
            )
        ),
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(req),
    )

    with pytest.raises(AppError) as exc_info:
        run_publisher_inventory_discovery(
            PublisherInventoryDiscoveryRequest(
                schema_version="1.0",
                insights_url="https://www.activate.com/insights",
                reports_db="./state/reports.sqlite",
                settings=_settings(),
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert exc_info.value.code == "publisher_inventory_browser_pagination_limit"
    assert [record.status for record in status_records] == [
        "failed:publisher_inventory_browser_pagination_limit"
    ]


def test_run_publisher_inventory_discovery_unchanged_rerun_skips_upload(
    run_context,
    idempotency_guard,
):
    uploads = []
    snapshot_payload = _snapshot_json("https://www.activate.com/reports/report-one")
    snapshot_sha256 = _snapshot_sha256(
        "https://www.activate.com/reports/report-one",
        run_context,
    )

    def _run_once():
        deps = _dependencies(
            discover_publisher_inventory=lambda req, ctx: PublisherInventoryServiceResponse(
                schema_version="1.0",
                source_url="https://www.activate.com/insights",
                normalized_url="https://www.activate.com/insights",
                route_kind="browser_render",
                route_summary="Open page 1, click next, extract cards.",
                final_page_url="https://www.activate.com/insights?page=2",
                used_route_hint=False,
                pages=[
                    PublisherInventoryPage(
                        schema_version="1.0",
                        page_number=1,
                        page_url="https://www.activate.com/insights",
                    )
                ],
                candidates=[
                    PublisherInventoryRawCandidate(
                        schema_version="1.0",
                        url="https://www.activate.com/reports/report-one",
                        title="Existing Report",
                        source_page_url="https://www.activate.com/insights",
                        discovered_on_page_number=1,
                    )
                ],
            ),
            screen_publisher_inventory_candidates=lambda req, ctx: _screening_response(
                accepted_urls=set(),
                request=req,
            ),
            qualify_publisher_inventory_candidates=lambda req, ctx: _quality_response(
                accepted_urls=set(),
                request=req,
            ),
            get_publisher_inventory_state=lambda req, ctx: _publisher_state(
                with_route=False, with_snapshot=True, snapshot_sha256=snapshot_sha256
            ),
            record_discovered_report_source=lambda req, ctx: ReportSourceDiscoveryRecordResponse(
                schema_version="1.0",
                record_id=1,
                publisher_name=req.publisher_name,
                source_domain=req.source_domain,
                report_name=req.report_name,
                landing_page_url=req.landing_page_url,
                source_page_url=req.source_page_url,
                discovered_at_utc=req.discovered_at_utc,
                discovered_on_page_number=req.discovered_on_page_number,
                created_new=False,
            ),
            download_pdf=lambda req, ctx: DriveDownloadResponse(
                schema_version="1.0",
                file=req.file,
                content=snapshot_payload.encode("utf-8"),
                md5="md5",
                size=len(snapshot_payload),
            ),
            upload_bytes=lambda req, ctx: (
                uploads.append(req)
                or DriveUploadBytesResponse(
                    schema_version="1.0",
                    file=DriveFile(
                        schema_version="1.0",
                        file_id="drive-file-new",
                        name=req.file_name,
                        modified_time=None,
                        md5_checksum=None,
                        mime_type="application/json",
                    ),
                    size=len(req.content),
                    md5="abc123",
                )
            ),
        )
        return run_publisher_inventory_discovery(
            PublisherInventoryDiscoveryRequest(
                schema_version="1.0",
                insights_url="https://www.activate.com/insights",
                reports_db="./state/reports.sqlite",
                settings=_settings(),
            ),
            ctx=run_context,
            dependencies=deps,
        )

    first, second = idempotency_guard(_run_once, side_effect_count=lambda: len(uploads))
    assert first.snapshot_changed is False
    assert second.snapshot_changed is False
    assert first.new_report_urls == []
    assert second.new_report_urls == []
    assert uploads == []


def test_run_publisher_inventory_discovery_requires_google_folder(
    run_context,
    assert_app_error,
):
    deps = _dependencies(
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False, with_snapshot=False, with_folder=False
        ),
        record_discovered_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not record discovered sources")
        ),
        upload_bytes=lambda req, ctx: (_ for _ in ()).throw(AssertionError("should not upload snapshot")),
    )
    with pytest.raises(AppError) as err:
        run_publisher_inventory_discovery(
            PublisherInventoryDiscoveryRequest(
                schema_version="1.0",
                insights_url="https://www.activate.com/insights",
                reports_db="./state/reports.sqlite",
                settings=_settings(),
            ),
            ctx=run_context,
            dependencies=deps,
        )
    assert_app_error(err.value, code="publisher_inventory_google_folder_missing", retryable=False)


def test_run_publisher_inventory_discovery_rejects_non_meaningful_candidates_before_recording(
    run_context,
):
    source_records = []
    deps = _dependencies(
        screen_publisher_inventory_candidates=lambda req, ctx: _screening_response(
            accepted_urls=set(),
            request=req,
        ),
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False, with_snapshot=False
        ),
        record_discovered_report_source=lambda req, ctx: (
            source_records.append(req)
            or ReportSourceDiscoveryRecordResponse(
                schema_version="1.0",
                record_id=1,
                publisher_name=req.publisher_name,
                source_domain=req.source_domain,
                report_name=req.report_name,
                landing_page_url=req.landing_page_url,
                source_page_url=req.source_page_url,
                discovered_at_utc=req.discovered_at_utc,
                discovered_on_page_number=req.discovered_on_page_number,
                created_new=True,
            )
        ),
    )

    result = run_publisher_inventory_discovery(
        PublisherInventoryDiscoveryRequest(
            schema_version="1.0",
            insights_url="https://www.activate.com/insights",
            reports_db="./state/reports.sqlite",
            settings=_settings(),
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.new_report_urls == []
    assert source_records == []


def test_run_publisher_inventory_discovery_quality_rejects_editorial_pages_before_recording(
    run_context,
):
    source_records = []
    deps = _dependencies(
        qualify_publisher_inventory_candidates=lambda req, ctx: _quality_response(
            accepted_urls=set(),
            request=req,
        ),
        record_discovered_report_source=lambda req, ctx: (
            source_records.append(req)
            or ReportSourceDiscoveryRecordResponse(
                schema_version="1.0",
                record_id=1,
                publisher_name=req.publisher_name,
                source_domain=req.source_domain,
                report_name=req.report_name,
                landing_page_url=req.landing_page_url,
                source_page_url=req.source_page_url,
                discovered_at_utc=req.discovered_at_utc,
                discovered_on_page_number=req.discovered_on_page_number,
                created_new=True,
            )
        ),
    )

    result = run_publisher_inventory_discovery(
        PublisherInventoryDiscoveryRequest(
            schema_version="1.0",
            insights_url="https://www.activate.com/insights",
            reports_db="./state/reports.sqlite",
            settings=_settings(),
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.new_report_urls == []
    assert source_records == []


def test_run_publisher_inventory_discovery_screening_failure_does_not_commit_snapshot(
    run_context,
    assert_app_error,
):
    uploads = []
    state_records = []
    deps = _dependencies(
        screen_publisher_inventory_candidates=lambda req, ctx: (_ for _ in ()).throw(
            AppError(
                code="publisher_inventory_candidate_screen_invalid_json",
                message="invalid JSON",
                retryable=False,
            )
        ),
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False, with_snapshot=False
        ),
        record_publisher_inventory_state=lambda req, ctx: state_records.append(req),
        record_discovered_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not record discovered sources")
        ),
        upload_bytes=lambda req, ctx: (
            uploads.append(req)
            or DriveUploadBytesResponse(
                schema_version="1.0",
                file=DriveFile(
                    schema_version="1.0",
                    file_id="drive-file-1",
                    name=req.file_name,
                    modified_time=None,
                    md5_checksum=None,
                    mime_type="application/json",
                ),
                size=len(req.content),
                md5="abc123",
            )
        ),
    )

    with pytest.raises(AppError) as err:
        run_publisher_inventory_discovery(
            PublisherInventoryDiscoveryRequest(
                schema_version="1.0",
                insights_url="https://www.activate.com/insights",
                reports_db="./state/reports.sqlite",
                settings=_settings(),
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert_app_error(
        err.value,
        code="publisher_inventory_candidate_screen_invalid_json",
        retryable=False,
    )
    assert uploads == []
    assert state_records == []
