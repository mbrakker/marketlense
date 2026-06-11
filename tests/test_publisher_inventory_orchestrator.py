from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from src.contracts.drive import (
    DriveDownloadResponse,
    DriveFile,
    DriveFolderEnsureResponse,
    DriveFolderFileListResponse,
    DriveUploadBytesResponse,
)
from src.contracts.publisher_inventory import (
    PublisherInventoryBuildRequest,
    PublisherInventoryCandidateQualityDecision,
    PublisherInventoryCandidateQualityResponse,
    PublisherInventoryRecoveryRecipe,
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
    PublisherGoogleFolderUpdateResponse,
    PublisherResourceRankingItem,
    PublisherResourceRankingResponse,
    PublisherInventoryStateResponse,
    PublishersReplaceRequest,
    ReportSourceQualityHistoryResponse,
    ReportSourceDiscoveryRecordResponse,
)
from src.contracts.publisher_profiles import PublisherProfileRecord
from src.orchestrators.publisher_inventory_orchestrator import (
    PublisherInventoryDependencies,
    run_publisher_inventory_discovery,
)
from src.services.report_store_service import (
    record_publisher_inventory_recovery_cache_record,
    record_publisher_inventory_run_quality,
    record_publisher_inventory_state,
    record_publisher_inventory_test_status,
    replace_publishers,
)
from src.utils.errors import AppError


def _settings() -> PublisherInventorySettings:
    reports_db = str(
        Path(tempfile.mkdtemp(prefix="publisher_inventory_test_")) / "reports.sqlite"
    )
    return PublisherInventorySettings(
        schema_version="1.0",
        openrouter_api_key="openrouter-key",
        model="openai/gpt-5-mini",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=5,
        output_dir="./out/publisher_inventory_discovery",
        reports_db=reports_db,
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
        google_folder="https://drive.google.com/drive/folders/folder123"
        if with_folder
        else None,
        discovery_test_status=None,
        inventory_route_kind="browser_render" if with_route else None,
        inventory_route_summary="Open page 1, click next, extract cards."
        if with_route
        else None,
        inventory_route_last_final_page_url="https://www.activate.com/insights?page=2"
        if with_route
        else None,
        inventory_route_updated_at=1 if with_route else None,
        inventory_snapshot_drive_file_id="snapshot-1" if with_snapshot else None,
        inventory_snapshot_drive_file_name="publisher_inventory_snapshot__20260328T000000Z.json"
        if with_snapshot
        else None,
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
            PublisherInventoryPage(
                schema_version="1.0",
                page_number=1,
                page_url="https://www.activate.com/insights",
            ),
            PublisherInventoryPage(
                schema_version="1.0",
                page_number=2,
                page_url="https://www.activate.com/insights?page=2",
            ),
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


def _screening_response(
    *, accepted_urls: set[str], request
) -> PublisherInventoryCandidateScreeningResponse:
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


def _quality_response(
    *, accepted_urls: set[str], request
) -> PublisherInventoryCandidateQualityResponse:
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
                    "qualified_report_asset" if accepted else "editorial_article_page"
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
    return _snapshot_json_for_urls([url])


def _snapshot_json_for_urls(urls: list[str]) -> str:
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
            {
                "schema_version": "1.0",
                "page_number": 1,
                "page_url": "https://www.activate.com/insights",
            },
        ],
        "items": [
            {
                "schema_version": "1.0",
                "canonical_url": item_url,
                "title": f"Existing Report {index}",
                "discovered_on_page_number": 1,
                "pdf_url": None,
                "published_at_text": None,
            }
            for index, item_url in enumerate(urls, start=1)
        ],
    }
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _snapshot_sha256(url: str, run_context) -> str:
    return (
        __import__(
            "src.generators.publisher_inventory_generator",
            fromlist=["build_publisher_inventory_snapshot"],
        )
        .build_publisher_inventory_snapshot(
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
        )
        .snapshot_sha256
    )


def _snapshot_sha256_for_urls(urls: list[str], run_context) -> str:
    candidates = [
        PublisherInventoryRawCandidate(
            schema_version="1.0",
            url=item_url,
            title=f"Existing Report {index}",
            source_page_url="https://www.activate.com/insights",
            discovered_on_page_number=1,
        )
        for index, item_url in enumerate(urls, start=1)
    ]
    return (
        __import__(
            "src.generators.publisher_inventory_generator",
            fromlist=["build_publisher_inventory_snapshot"],
        )
        .build_publisher_inventory_snapshot(
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
                candidates=candidates,
            ),
            run_context,
        )
        .snapshot_sha256
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
        "validate_publisher_inventory_coverage": lambda req, ctx: __import__(
            "src.generators.publisher_inventory_coverage_generator",
            fromlist=["validate_publisher_inventory_coverage"],
        ).validate_publisher_inventory_coverage(req, ctx),
        "evaluate_publisher_inventory_run_quality": lambda req, ctx: __import__(
            "src.generators.publisher_inventory_run_quality_generator",
            fromlist=["evaluate_publisher_inventory_run_quality"],
        ).evaluate_publisher_inventory_run_quality(req, ctx),
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
        "get_publisher_inventory_recovery_cache_record": lambda req, ctx: None,
        "record_publisher_inventory_run_quality": lambda req, ctx: None,
        "record_publisher_inventory_recovery_cache_record": lambda req, ctx: None,
        "record_publisher_inventory_state": lambda req, ctx: None,
        "record_publisher_inventory_test_status": lambda req, ctx: None,
        "record_discovered_report_source": lambda req, ctx: (
            ReportSourceDiscoveryRecordResponse(
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
        "list_report_source_quality_history": lambda req, ctx: (
            ReportSourceQualityHistoryResponse(
                schema_version="1.0",
                publisher_name=req.publisher_name,
                items=[],
            )
        ),
        "rank_publisher_resources": lambda req, ctx: PublisherResourceRankingResponse(
            schema_version="1.0",
            publisher_name=req.publisher_name,
            items=[
                PublisherResourceRankingItem(
                    schema_version="1.0",
                    resource_url=url,
                    sample_size=0,
                    score_window_size=req.policy.score_window_size,
                    average_value_score=0.0,
                    latest_value_score=0.0,
                    consistency_score=0.0,
                    confidence=0.0,
                    rank_score=0.0,
                    demotion_reason="insufficient_history",
                )
                for url in req.candidate_source_page_urls
            ],
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
        "ensure_folder": lambda req, ctx: DriveFolderEnsureResponse(
            schema_version="1.0",
            folder=DriveFile(
                schema_version="1.0",
                file_id="created-publisher-folder",
                name=req.folder_name,
                modified_time=None,
                md5_checksum=None,
                mime_type="application/vnd.google-apps.folder",
            ),
            parent_folder_id=req.parent_folder_id,
            created=True,
        ),
        "update_publisher_google_folder": lambda req, ctx: (
            PublisherGoogleFolderUpdateResponse(
                schema_version="1.0",
                publisher_name=req.publisher_name,
                google_folder=req.google_folder,
                updated_count=1,
                resolution_source="publisher_insights_url",
            )
        ),
    }
    defaults.update(overrides)
    return PublisherInventoryDependencies(**defaults)


def _request(
    settings: PublisherInventorySettings | None = None,
) -> PublisherInventoryDiscoveryRequest:
    resolved_settings = settings or _settings()
    return PublisherInventoryDiscoveryRequest(
        schema_version="1.0",
        insights_url="https://www.activate.com/insights",
        reports_db=resolved_settings.reports_db,
        settings=resolved_settings,
    )


def test_run_publisher_inventory_discovery_first_run_uploads_snapshot_and_returns_diff(
    run_context,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
):
    settings = _settings()
    uploads = []
    records = []
    status_records = []
    source_records = []

    deps = _dependencies(
        record_publisher_inventory_state=lambda req, ctx: records.append(req),
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
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
    caplog.set_level(
        logging.INFO, logger="market_lense.publisher_inventory_orchestrator"
    )

    result = run_publisher_inventory_discovery(
        _request(settings), ctx=run_context, dependencies=deps
    )

    assert result.publisher_name == "Activate Consulting"
    assert result.snapshot_changed is True
    assert result.used_memory_route is False
    assert len(result.new_report_urls) == 1
    assert len(result.current_candidates) == 1
    assert (
        result.current_candidates[0].canonical_url
        == "https://www.activate.com/reports/new-report"
    )
    assert result.current_candidates[0].discovery_provenances == []
    assert result.new_report_urls[0].discovered_on_page_number == 2
    assert len(uploads) == 1
    assert len(records) == 1
    assert [record.status for record in status_records] == ["passed"]
    assert len(source_records) == 1
    assert (
        source_records[0].landing_page_url
        == "https://www.activate.com/reports/new-report"
    )
    assert source_records[0].report_name == "Resolved New Report"
    assert (
        source_records[0].source_page_url == "https://www.activate.com/insights?page=2"
    )
    assert_no_defaulted_required_fields(result)
    assert_logs_have_required_fields(
        _events(caplog, "market_lense.publisher_inventory_orchestrator")
    )


def test_run_publisher_inventory_discovery_falls_back_after_memory_route_failure(
    run_context,
):
    settings = _settings()
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
        _request(settings), ctx=run_context, dependencies=deps
    )

    assert attempts["memory"] >= 1
    assert attempts["fresh"] == 1
    assert result.used_memory_route is False


def test_run_publisher_inventory_discovery_falls_back_after_http_empty(
    run_context,
):
    settings = _settings()
    attempts: list[str] = []

    def _discover(req, ctx):
        attempts.append(req.route_kind_hint or "")
        if req.route_kind_hint == "http_parse":
            raise AppError(
                code="publisher_inventory_http_empty",
                message="Direct HTTP parsing found no valid report inventory items",
                retryable=False,
            )
        return _service_response(
            used_route_hint=False,
            new_url="https://www.activate.com/reports/new-report",
        )

    deps = _dependencies(discover_publisher_inventory=_discover)

    result = run_publisher_inventory_discovery(
        _request(settings), ctx=run_context, dependencies=deps
    )

    assert attempts == ["http_parse", "browser_render"]
    assert result.new_report_urls[0].canonical_url == (
        "https://www.activate.com/reports/new-report"
    )


def test_run_publisher_inventory_discovery_skips_invalid_drive_snapshot(
    run_context,
    caplog,
):
    settings = _settings()
    source_records = []
    downloads = []

    def _download_snapshot(req, ctx):
        downloads.append(req.file.file_id)
        return DriveDownloadResponse(
            schema_version="1.0",
            file=req.file,
            content=b'{"schema_version":"1.0","publisher_name":"Integration Publisher"}',
            md5="bad-md5",
            size=65,
        )

    deps = _dependencies(
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            files=[
                DriveFile(
                    schema_version="1.0",
                    file_id="invalid-snapshot",
                    name="publisher_inventory_snapshot__20260422T202421Z.json",
                    modified_time="2026-04-22T20:24:21Z",
                    md5_checksum="bad-md5",
                    mime_type="application/json",
                )
            ],
        ),
        download_pdf=_download_snapshot,
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
    caplog.set_level(
        logging.INFO, logger="market_lense.publisher_inventory_orchestrator"
    )

    result = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )

    assert downloads == ["invalid-snapshot"]
    assert result.snapshot_changed is True
    assert [item.landing_page_url for item in source_records] == [
        "https://www.activate.com/reports/new-report"
    ]
    events = _events(caplog, "market_lense.publisher_inventory_orchestrator")
    assert any(
        event["event"] == "publisher_inventory_previous_snapshot_skipped"
        and event["fields"]["snapshot_drive_file_id"] == "invalid-snapshot"
        for event in events
    )


def test_run_publisher_inventory_discovery_skips_mismatched_drive_snapshot(
    run_context,
    caplog,
):
    settings = _settings()
    source_records = []

    deps = _dependencies(
        get_publisher_inventory_state=lambda req, ctx: PublisherInventoryStateResponse(
            schema_version="1.0",
            publisher_name="Algolia",
            insights_url="https://resources.algolia.com/reports",
            normalized_url="https://resources.algolia.com/reports",
            google_folder="https://drive.google.com/drive/folders/folder123",
            discovery_test_status=None,
        ),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            files=[
                DriveFile(
                    schema_version="1.0",
                    file_id="activate-snapshot",
                    name="publisher_inventory_snapshot__20260501T195807Z.json",
                    modified_time="2026-05-01T19:58:07Z",
                    md5_checksum="activate-md5",
                    mime_type="application/json",
                )
            ],
        ),
        download_pdf=lambda req, ctx: DriveDownloadResponse(
            schema_version="1.0",
            file=req.file,
            content=_snapshot_json(
                "https://www.activate.com/reports/old-report"
            ).encode("utf-8"),
            md5="activate-md5",
            size=100,
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
    caplog.set_level(
        logging.INFO, logger="market_lense.publisher_inventory_orchestrator"
    )

    result = run_publisher_inventory_discovery(
        PublisherInventoryDiscoveryRequest(
            schema_version="1.0",
            insights_url="https://resources.algolia.com/reports",
            reports_db=settings.reports_db,
            settings=settings,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.previous_report_count == 0
    assert [item.landing_page_url for item in source_records] == [
        "https://www.activate.com/reports/new-report"
    ]
    events = _events(caplog, "market_lense.publisher_inventory_orchestrator")
    assert any(
        event["event"] == "publisher_inventory_previous_snapshot_skipped"
        and event["fields"]["code"] == "publisher_inventory_snapshot_publisher_mismatch"
        for event in events
    )


def test_run_publisher_inventory_discovery_does_not_fallback_after_non_retryable_memory_failure(
    run_context,
    assert_app_error,
):
    settings = _settings()
    attempts = {"memory": 0, "fresh": 0}

    def _discover(req, ctx):
        if req.route_hint:
            attempts["memory"] += 1
            raise AppError(
                code="publisher_inventory_route_summary_invalid",
                message="stored route is structurally invalid",
                retryable=False,
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

    with pytest.raises(AppError) as err:
        run_publisher_inventory_discovery(
            _request(settings), ctx=run_context, dependencies=deps
        )

    assert attempts["memory"] == 1
    assert attempts["fresh"] == 0
    assert_app_error(
        err.value,
        code="publisher_inventory_route_summary_invalid",
        retryable=False,
    )


def test_run_publisher_inventory_discovery_applies_remaining_time_budget_to_step_settings(
    run_context,
):
    captured_discovery_timeouts = []
    captured_screening_timeouts = []
    captured_quality_timeouts = []
    settings = PublisherInventorySettings(
        **{
            **_settings().__dict__,
            "timeout_seconds": 30.0,
            "candidate_screening_timeout_seconds": 30.0,
            "candidate_quality_check_timeout_seconds": 15.0,
            "command_time_budget_seconds": 4.0,
        }
    )
    deps = _dependencies(
        discover_publisher_inventory=lambda req, ctx: (
            captured_discovery_timeouts.append(req.settings.timeout_seconds)
            or _service_response(
                used_route_hint=False,
                new_url="https://www.activate.com/reports/new-report",
            )
        ),
        screen_publisher_inventory_candidates=lambda req, ctx: (
            captured_screening_timeouts.append(
                req.settings.candidate_screening_timeout_seconds
            )
            or _screening_response(
                accepted_urls={"https://www.activate.com/reports/new-report"},
                request=req,
            )
        ),
        qualify_publisher_inventory_candidates=lambda req, ctx: (
            captured_quality_timeouts.append(
                req.settings.candidate_quality_check_timeout_seconds
            )
            or _quality_response(
                accepted_urls={"https://www.activate.com/reports/new-report"},
                request=req,
            )
        ),
    )

    with patch(
        "time.monotonic",
        side_effect=[
            100.0,
            100.5,
            100.75,
            101.0,
            101.25,
            101.5,
            101.75,
            102.0,
            102.25,
            102.5,
            102.75,
            103.0,
        ],
    ):
        run_publisher_inventory_discovery(
            _request(settings),
            ctx=run_context,
            dependencies=deps,
        )

    assert len(captured_discovery_timeouts) == 1
    assert len(captured_screening_timeouts) == 1
    assert len(captured_quality_timeouts) == 1
    assert 1.0 <= captured_discovery_timeouts[0] < settings.timeout_seconds
    assert (
        1.0
        <= captured_screening_timeouts[0]
        < settings.candidate_screening_timeout_seconds
    )
    assert (
        1.0
        <= captured_quality_timeouts[0]
        <= settings.candidate_quality_check_timeout_seconds
    )
    assert captured_discovery_timeouts[0] >= captured_screening_timeouts[0]
    assert captured_screening_timeouts[0] >= captured_quality_timeouts[0]


def test_run_publisher_inventory_discovery_records_failed_test_status(
    run_context,
):
    settings = _settings()
    status_records = []

    deps = _dependencies(
        discover_publisher_inventory=lambda req, ctx: (_ for _ in ()).throw(
            AppError(
                code="publisher_inventory_browser_pagination_limit",
                message="deep archive limit reached",
                retryable=False,
            )
        ),
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
        ),
    )

    with pytest.raises(AppError) as exc_info:
        run_publisher_inventory_discovery(
            _request(settings),
            ctx=run_context,
            dependencies=deps,
        )

    assert exc_info.value.code == "publisher_inventory_browser_pagination_limit"
    assert [record.status for record in status_records] == [
        "bounded:publisher_inventory_browser_pagination_limit"
    ]


def test_run_publisher_inventory_discovery_records_time_budget_failure_before_discovery(
    run_context,
):
    status_records = []
    discover_calls = []
    settings = PublisherInventorySettings(
        **{**_settings().__dict__, "command_time_budget_seconds": 1.0}
    )
    deps = _dependencies(
        discover_publisher_inventory=lambda req, ctx: (
            discover_calls.append(req)
            or _service_response(
                used_route_hint=False,
                new_url="https://www.activate.com/reports/new-report",
            )
        ),
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
        ),
    )

    with patch(
        "time.monotonic",
        side_effect=[100.0, 101.5],
    ):
        with pytest.raises(AppError) as exc_info:
            run_publisher_inventory_discovery(
                _request(settings),
                ctx=run_context,
                dependencies=deps,
            )

    assert exc_info.value.code == "publisher_inventory_time_budget_exceeded"
    assert discover_calls == []
    assert [record.status for record in status_records] == [
        "failed:publisher_inventory_time_budget_exceeded"
    ]


def test_run_publisher_inventory_discovery_does_not_retry_or_fallback_on_pagination_limit(
    run_context,
):
    settings = _settings()
    attempts = {"memory": 0, "fresh": 0}

    def _discover(req, ctx):
        if req.route_hint:
            attempts["memory"] += 1
        else:
            attempts["fresh"] += 1
        raise AppError(
            code="publisher_inventory_browser_pagination_limit",
            message="deep archive limit reached",
            retryable=False,
        )

    deps = _dependencies(
        discover_publisher_inventory=_discover,
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=True,
            with_snapshot=False,
        ),
    )

    with pytest.raises(AppError) as exc_info:
        run_publisher_inventory_discovery(
            _request(settings), ctx=run_context, dependencies=deps
        )

    assert exc_info.value.code == "publisher_inventory_browser_pagination_limit"
    assert attempts == {"memory": 1, "fresh": 0}


def test_run_publisher_inventory_discovery_unchanged_rerun_skips_upload(
    run_context,
    idempotency_guard,
):
    settings = _settings()
    uploads = []
    snapshot_payload = _snapshot_json("https://www.activate.com/reports/report-one")
    snapshot_sha256 = _snapshot_sha256(
        "https://www.activate.com/reports/report-one",
        run_context,
    )

    def _run_once():
        deps = _dependencies(
            discover_publisher_inventory=lambda req, ctx: (
                PublisherInventoryServiceResponse(
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
                )
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
            record_discovered_report_source=lambda req, ctx: (
                ReportSourceDiscoveryRecordResponse(
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
                )
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
            _request(settings),
            ctx=run_context,
            dependencies=deps,
        )

    first, second = idempotency_guard(_run_once, side_effect_count=lambda: len(uploads))
    assert first.snapshot_changed is False
    assert second.snapshot_changed is False
    assert first.new_report_urls == []
    assert second.new_report_urls == []
    assert uploads == []


def test_run_publisher_inventory_discovery_reuses_idempotent_snapshot_and_source_steps(
    tmp_path,
    run_context,
) -> None:
    uploads = []
    source_records = []
    settings = _settings()
    settings = PublisherInventorySettings(
        **{**settings.__dict__, "reports_db": str(tmp_path / "reports.sqlite")}
    )

    deps = _dependencies(
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

    first = run_publisher_inventory_discovery(
        PublisherInventoryDiscoveryRequest(
            schema_version="1.0",
            insights_url="https://www.activate.com/insights",
            reports_db=settings.reports_db,
            settings=settings,
        ),
        ctx=run_context,
        dependencies=deps,
    )
    second = run_publisher_inventory_discovery(
        PublisherInventoryDiscoveryRequest(
            schema_version="1.0",
            insights_url="https://www.activate.com/insights",
            reports_db=settings.reports_db,
            settings=settings,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert first.snapshot_changed is True
    assert second.snapshot_changed is True
    assert len(uploads) == 1
    assert len(source_records) == 1
    assert (
        second.new_report_urls[0].canonical_url
        == first.new_report_urls[0].canonical_url
    )


def test_run_publisher_inventory_discovery_reuses_idempotent_auxiliary_writes(
    tmp_path,
    run_context,
    caplog,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    current_url = "https://www.activate.com/reports/new-report"
    run_quality_calls: list[object] = []
    recovery_cache_calls: list[object] = []
    state_calls: list[object] = []
    status_calls: list[object] = []

    replace_publishers(
        PublishersReplaceRequest(
            schema_version="1.0",
            db_path=reports_db,
            source_page_url="https://www.notion.so/source",
            publishers=[
                PublisherProfileRecord(
                    schema_version="1.0",
                    notion_page_id="page-1",
                    notion_page_url="https://www.notion.so/page-1",
                    name="Activate Consulting",
                    homepage="https://www.activate.com/",
                    self_presentation="Activate description",
                    insights_url="https://www.activate.com/insights",
                    icon_source="https://cdn.example.com/activate.png",
                )
            ],
        ),
        run_context,
    )

    def _record_run_quality(req, ctx):
        run_quality_calls.append(req)
        return record_publisher_inventory_run_quality(req, ctx)

    def _record_recovery_cache(req, ctx):
        recovery_cache_calls.append(req)
        return record_publisher_inventory_recovery_cache_record(req, ctx)

    def _record_state(req, ctx):
        state_calls.append(req)
        return record_publisher_inventory_state(req, ctx)

    def _record_status(req, ctx):
        status_calls.append(req)
        return record_publisher_inventory_test_status(req, ctx)

    def _quality_with_recovery(req, ctx):
        candidate = req.candidates[0]
        rejected = PublisherInventoryQualifiedCandidateItem(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            title=candidate.title,
            discovered_on_page_number=candidate.discovered_on_page_number,
            source_page_url=candidate.source_page_url,
        )
        return PublisherInventoryCandidateQualityResponse(
            schema_version="1.0",
            approved_items=[],
            rejected_items=[rejected],
            decisions=[
                PublisherInventoryCandidateQualityDecision(
                    schema_version="1.0",
                    canonical_url=candidate.canonical_url,
                    accepted=False,
                    reason="protected_document_probe_required",
                    resolved_title=candidate.title,
                    source_surface_class="report_detail",
                    recovery_recipe=PublisherInventoryRecoveryRecipe(
                        schema_version="1.0",
                        verification_class="protected_document",
                        source_surface_class="report_detail",
                        recovery_action="protected_document_probe",
                        reason="retry with deferred protected-document probe",
                    ),
                )
            ],
        )

    settings = PublisherInventorySettings(
        **{**_settings().__dict__, "reports_db": reports_db}
    )
    deps = _dependencies(
        discover_publisher_inventory=lambda req, ctx: _service_response(
            used_route_hint=False,
            new_url=current_url,
            title="Existing Report 1",
        ),
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False,
            with_snapshot=False,
            with_folder=True,
            snapshot_sha256="",
        ),
        get_publisher_inventory_recovery_cache_record=lambda req, ctx: None,
        qualify_publisher_inventory_candidates=_quality_with_recovery,
        record_publisher_inventory_run_quality=_record_run_quality,
        record_publisher_inventory_recovery_cache_record=_record_recovery_cache,
        record_publisher_inventory_state=_record_state,
        record_publisher_inventory_test_status=_record_status,
        record_discovered_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("no qualified candidates should be recorded in this flow")
        ),
        upload_bytes=lambda req, ctx: DriveUploadBytesResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id="drive-file-aux",
                name=req.file_name,
                modified_time=None,
                md5_checksum=None,
                mime_type="application/json",
            ),
            size=len(req.content),
            md5="abc123",
        ),
    )
    caplog.set_level(
        logging.INFO, logger="market_lense.publisher_inventory_orchestrator"
    )

    first = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )
    second = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )

    assert first.snapshot_changed is False
    assert second.snapshot_changed is False
    assert first.new_report_urls == []
    assert second.new_report_urls == []
    assert len(run_quality_calls) == 1
    assert len(recovery_cache_calls) == 1
    assert len(state_calls) == 1
    assert len(status_calls) == 1

    with sqlite3.connect(reports_db) as conn:
        run_quality_history = conn.execute(
            """
            SELECT COUNT(*)
            FROM publisher_inventory_route_history
            WHERE normalized_url=?
            """,
            ("https://www.activate.com/insights",),
        ).fetchone()
        recovery_cache_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM publisher_inventory_candidate_recovery_cache
            WHERE normalized_url=?
            """,
            ("https://www.activate.com/insights",),
        ).fetchone()
        publisher_row = conn.execute(
            """
            SELECT discovery_test_status, inventory_snapshot_sha256
            FROM publishers
            WHERE normalized_insights_url=?
            """,
            ("https://www.activate.com/insights",),
        ).fetchone()

    assert int(run_quality_history[0] if run_quality_history else 0) == 1
    assert int(recovery_cache_rows[0] if recovery_cache_rows else 0) == 1
    assert publisher_row is not None
    assert str(publisher_row[0] or "") == "passed:no_report_assets"
    assert len(str(publisher_row[1] or "")) == 64
    guardrail_events = [
        event
        for event in _events(caplog, "market_lense.publisher_inventory_orchestrator")
        if event["event"] == "publisher_inventory_rollout_guardrails_evaluated"
    ]
    assert guardrail_events
    guardrail_fields = guardrail_events[0]["fields"]
    assert guardrail_fields["rollout_flags"] == {
        "enable_deferred_candidate_recovery": True,
        "enable_structured_route_reuse": True,
        "enable_preflight_classifier_and_direct_detail": True,
    }
    assert guardrail_fields["deferred_recovery_scheduled_count"] == 1
    assert guardrail_fields["run_quality_requires_review"] is False
    assert guardrail_fields["kpi_guardrail_status"] == "pass"


def test_run_publisher_inventory_discovery_does_not_commit_raw_only_snapshot_drift(
    tmp_path,
    run_context,
):
    settings = PublisherInventorySettings(
        **{**_settings().__dict__, "reports_db": str(tmp_path / "reports.sqlite")}
    )
    uploads = []
    state_records = []
    snapshot_payload = _snapshot_json("https://www.activate.com/reports/report-one")
    snapshot_sha256 = _snapshot_sha256(
        "https://www.activate.com/reports/report-one", run_context
    )
    deps = _dependencies(
        discover_publisher_inventory=lambda req, ctx: _service_response(
            used_route_hint=True,
            new_url="https://www.activate.com/reports/noisy-hub",
            title="Resources",
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
            with_route=True,
            with_snapshot=True,
            snapshot_sha256=snapshot_sha256,
        ),
        record_publisher_inventory_state=lambda req, ctx: state_records.append(req),
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
        record_discovered_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not record discovered sources")
        ),
    )

    result = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.snapshot_changed is False
    assert result.new_report_urls == []
    assert uploads == []
    assert len(state_records) == 1
    assert state_records[0].snapshot_drive_file_id == "snapshot-1"
    assert state_records[0].snapshot_sha256 == snapshot_sha256
    assert state_records[0].route_kind == "browser_render"


def test_run_publisher_inventory_discovery_creates_missing_google_folder(
    run_context,
):
    settings = replace(_settings(), drive_parent_folder_id="parent-folder")
    ensured = []
    folder_updates = []
    deps = _dependencies(
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False, with_snapshot=False, with_folder=False
        ),
        ensure_folder=lambda req, ctx: (
            ensured.append(req)
            or DriveFolderEnsureResponse(
                schema_version="1.0",
                folder=DriveFile(
                    schema_version="1.0",
                    file_id="created-publisher-folder",
                    name=req.folder_name,
                    modified_time=None,
                    md5_checksum=None,
                    mime_type="application/vnd.google-apps.folder",
                ),
                parent_folder_id=req.parent_folder_id,
                created=True,
            )
        ),
        update_publisher_google_folder=lambda req, ctx: (
            folder_updates.append(req)
            or PublisherGoogleFolderUpdateResponse(
                schema_version="1.0",
                publisher_name=req.publisher_name,
                google_folder=req.google_folder,
                updated_count=1,
                resolution_source="publisher_insights_url",
            )
        ),
    )

    result = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.publisher_name == "Activate Consulting"
    assert ensured[0].parent_folder_id == "parent-folder"
    assert ensured[0].folder_name == "Activate Consulting"
    assert folder_updates[0].google_folder.endswith("/created-publisher-folder")


def test_run_publisher_inventory_discovery_requires_parent_for_missing_google_folder(
    run_context,
    assert_app_error,
):
    settings = _settings()
    deps = _dependencies(
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False, with_snapshot=False, with_folder=False
        ),
        record_discovered_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not record discovered sources")
        ),
        upload_bytes=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not upload snapshot")
        ),
    )
    with pytest.raises(AppError) as err:
        run_publisher_inventory_discovery(
            _request(settings),
            ctx=run_context,
            dependencies=deps,
        )
    assert_app_error(
        err.value,
        code="publisher_inventory_google_folder_parent_missing",
        retryable=False,
    )


def test_run_publisher_inventory_discovery_rejects_non_meaningful_candidates_before_recording(
    run_context,
):
    settings = _settings()
    source_records = []
    uploads = []
    status_records = []
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
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
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

    result = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.new_report_urls == []
    assert source_records == []
    assert result.snapshot_changed is False
    assert uploads == []
    assert [record.status for record in status_records] == ["passed:no_report_assets"]


def test_run_publisher_inventory_discovery_quality_rejects_editorial_pages_before_recording(
    tmp_path,
    run_context,
):
    settings = PublisherInventorySettings(
        **{**_settings().__dict__, "reports_db": str(tmp_path / "reports.sqlite")}
    )
    source_records = []
    uploads = []
    status_records = []
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
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
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

    result = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.new_report_urls == []
    assert source_records == []
    assert result.snapshot_changed is False
    assert uploads == []
    assert [record.status for record in status_records] == ["passed:no_report_assets"]


def test_run_publisher_inventory_discovery_rejects_material_shrinkage_without_new_assets(
    run_context,
    assert_app_error,
):
    settings = _settings()
    previous_urls = [
        f"https://www.activate.com/reports/report-{index}" for index in range(1, 11)
    ]
    current_urls = previous_urls[:5]
    snapshot_payload = _snapshot_json_for_urls(previous_urls)
    snapshot_sha256 = _snapshot_sha256_for_urls(previous_urls, run_context)
    uploads = []
    state_records = []
    status_records = []

    deps = _dependencies(
        discover_publisher_inventory=lambda req, ctx: PublisherInventoryServiceResponse(
            schema_version="1.0",
            source_url="https://www.activate.com/insights",
            normalized_url="https://www.activate.com/insights",
            route_kind="browser_render",
            route_summary="Open page 1, click next, extract cards.",
            final_page_url="https://www.activate.com/insights?page=2",
            used_route_hint=True,
            pages=[
                PublisherInventoryPage(
                    schema_version="1.0",
                    page_number=1,
                    page_url="https://www.activate.com/insights",
                ),
                PublisherInventoryPage(
                    schema_version="1.0",
                    page_number=2,
                    page_url="https://www.activate.com/insights?page=2",
                ),
            ],
            candidates=[
                PublisherInventoryRawCandidate(
                    schema_version="1.0",
                    url=item_url,
                    title=f"Existing Report {index}",
                    source_page_url=(
                        "https://www.activate.com/insights"
                        if index <= 3
                        else "https://www.activate.com/insights?page=2"
                    ),
                    discovered_on_page_number=1 if index <= 3 else 2,
                )
                for index, item_url in enumerate(current_urls, start=1)
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
            with_route=True,
            with_snapshot=True,
            snapshot_sha256=snapshot_sha256,
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
        record_publisher_inventory_state=lambda req, ctx: state_records.append(req),
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
        ),
        record_discovered_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not record discovered sources")
        ),
    )

    with pytest.raises(AppError) as err:
        run_publisher_inventory_discovery(
            _request(settings),
            ctx=run_context,
            dependencies=deps,
        )

    assert_app_error(
        err.value,
        code="publisher_inventory_browser_incomplete",
        retryable=False,
    )
    assert uploads == []
    assert state_records == []
    assert [record.status for record in status_records] == [
        "failed:publisher_inventory_browser_incomplete"
    ]


def test_run_publisher_inventory_discovery_screening_failure_does_not_commit_snapshot(
    run_context,
    assert_app_error,
):
    settings = _settings()
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
            _request(settings),
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


def test_run_publisher_inventory_discovery_fails_when_all_screened_candidates_are_unreachable(
    run_context,
    assert_app_error,
):
    settings = _settings()
    uploads = []
    state_records = []
    status_records = []
    deps = _dependencies(
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False, with_snapshot=False
        ),
        qualify_publisher_inventory_candidates=lambda req, ctx: (
            PublisherInventoryCandidateQualityResponse(
                schema_version="1.0",
                approved_items=[],
                rejected_items=[
                    PublisherInventoryQualifiedCandidateItem(
                        schema_version="1.0",
                        canonical_url=candidate.canonical_url,
                        title=candidate.title,
                        discovered_on_page_number=candidate.discovered_on_page_number,
                        source_page_url=candidate.source_page_url,
                    )
                    for candidate in req.candidates
                ],
                decisions=[
                    PublisherInventoryCandidateQualityDecision(
                        schema_version="1.0",
                        canonical_url=candidate.canonical_url,
                        accepted=False,
                        reason="dead_or_unreachable_landing_page",
                        resolved_title=candidate.title,
                    )
                    for candidate in req.candidates
                ],
            )
        ),
        record_publisher_inventory_state=lambda req, ctx: state_records.append(req),
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
        ),
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
            _request(settings),
            ctx=run_context,
            dependencies=deps,
        )

    assert_app_error(
        err.value,
        code="publisher_inventory_candidate_quality_unreachable_archive",
        retryable=False,
    )
    assert uploads == []
    assert state_records == []
    assert [record.status for record in status_records] == [
        "failed:publisher_inventory_candidate_quality_unreachable_archive"
    ]


def test_run_publisher_inventory_discovery_tolerates_unreachable_delta_when_previous_snapshot_exists(
    tmp_path,
    run_context,
):
    settings = PublisherInventorySettings(
        **{**_settings().__dict__, "reports_db": str(tmp_path / "reports.sqlite")}
    )
    previous_urls = ["https://www.activate.com/reports/existing-report"]
    snapshot_payload = _snapshot_json_for_urls(previous_urls)
    snapshot_sha256 = _snapshot_sha256_for_urls(previous_urls, run_context)
    uploads = []
    state_records = []
    status_records = []

    deps = _dependencies(
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False,
            with_snapshot=True,
            snapshot_sha256=snapshot_sha256,
        ),
        download_pdf=lambda req, ctx: DriveDownloadResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id=req.file.file_id,
                name="publisher_inventory_snapshot__20260328T000000Z.json",
                modified_time="2026-03-28T00:00:00Z",
                md5_checksum="md5",
                mime_type="application/json",
            ),
            content=snapshot_payload.encode("utf-8"),
            size=len(snapshot_payload.encode("utf-8")),
            md5="md5",
        ),
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
                    url=previous_urls[0],
                    title="Existing Report",
                    source_page_url="https://www.activate.com/insights",
                    discovered_on_page_number=1,
                ),
                PublisherInventoryRawCandidate(
                    schema_version="1.0",
                    url="https://www.activate.com/reports/dead-delta-report",
                    title="Dead Delta Report",
                    source_page_url="https://www.activate.com/insights",
                    discovered_on_page_number=1,
                ),
            ],
        ),
        screen_publisher_inventory_candidates=lambda req, ctx: _screening_response(
            accepted_urls={"https://www.activate.com/reports/dead-delta-report"},
            request=req,
        ),
        qualify_publisher_inventory_candidates=lambda req, ctx: (
            PublisherInventoryCandidateQualityResponse(
                schema_version="1.0",
                approved_items=[],
                rejected_items=[
                    PublisherInventoryQualifiedCandidateItem(
                        schema_version="1.0",
                        canonical_url=candidate.canonical_url,
                        title=candidate.title,
                        discovered_on_page_number=candidate.discovered_on_page_number,
                        source_page_url=candidate.source_page_url,
                    )
                    for candidate in req.candidates
                ],
                decisions=[
                    PublisherInventoryCandidateQualityDecision(
                        schema_version="1.0",
                        canonical_url=candidate.canonical_url,
                        accepted=False,
                        reason="dead_or_unreachable_landing_page",
                        resolved_title=candidate.title,
                    )
                    for candidate in req.candidates
                ],
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
        record_publisher_inventory_state=lambda req, ctx: state_records.append(req),
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
        ),
        record_discovered_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not record discovered sources")
        ),
    )

    result = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.new_report_urls == []
    assert result.snapshot_changed is False
    assert uploads == []
    assert len(state_records) == 1
    assert state_records[0].snapshot_drive_file_id == "snapshot-1"
    assert [record.status for record in status_records] == ["passed"]
