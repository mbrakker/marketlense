# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_publisher_inventory_orchestrator.py"
)

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
from src.contracts.remediation import RemediationListRequest

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
from src.services.state_service import list_remediation_records

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
