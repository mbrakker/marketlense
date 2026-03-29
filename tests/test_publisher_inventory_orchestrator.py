from __future__ import annotations

import json
import logging

import pytest

from src.contracts.drive import DriveDownloadResponse, DriveFile, DriveFolderFileListResponse, DriveUploadBytesResponse
from src.contracts.publisher_inventory import (
    PublisherInventoryBuildRequest,
    PublisherInventoryDiscoveryRequest,
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
    PublisherInventoryServiceResponse,
    PublisherInventorySettings,
)
from src.contracts.report_store import PublisherInventoryStateResponse
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


def test_run_publisher_inventory_discovery_first_run_uploads_snapshot_and_returns_diff(
    run_context,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
):
    uploads = []
    records = []

    deps = PublisherInventoryDependencies(
        discover_publisher_inventory=lambda req, ctx: _service_response(
            used_route_hint=False,
            new_url="https://www.activate.com/reports/new-report",
        ),
        build_publisher_inventory_snapshot=lambda req, ctx: __import__(
            "src.generators.publisher_inventory_generator",
            fromlist=["build_publisher_inventory_snapshot"],
        ).build_publisher_inventory_snapshot(req, ctx),
        parse_publisher_inventory_snapshot=lambda payload, source, ctx: __import__(
            "src.generators.publisher_inventory_generator",
            fromlist=["parse_publisher_inventory_snapshot"],
        ).parse_publisher_inventory_snapshot(payload, source=source, ctx=ctx),
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False, with_snapshot=False
        ),
        record_publisher_inventory_state=lambda req, ctx: records.append(req),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0", folder_id=req.folder_id, files=[]
        ),
        download_pdf=lambda req, ctx: (_ for _ in ()).throw(AssertionError("should not download snapshot")),
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

    deps = PublisherInventoryDependencies(
        discover_publisher_inventory=_discover,
        build_publisher_inventory_snapshot=lambda req, ctx: __import__(
            "src.generators.publisher_inventory_generator",
            fromlist=["build_publisher_inventory_snapshot"],
        ).build_publisher_inventory_snapshot(req, ctx),
        parse_publisher_inventory_snapshot=lambda payload, source, ctx: __import__(
            "src.generators.publisher_inventory_generator",
            fromlist=["parse_publisher_inventory_snapshot"],
        ).parse_publisher_inventory_snapshot(payload, source=source, ctx=ctx),
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=True, with_snapshot=False
        ),
        record_publisher_inventory_state=lambda req, ctx: None,
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0", folder_id=req.folder_id, files=[]
        ),
        download_pdf=lambda req, ctx: (_ for _ in ()).throw(AssertionError("should not download snapshot")),
        upload_bytes=lambda req, ctx: DriveUploadBytesResponse(
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
        deps = PublisherInventoryDependencies(
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
            build_publisher_inventory_snapshot=lambda req, ctx: __import__(
                "src.generators.publisher_inventory_generator",
                fromlist=["build_publisher_inventory_snapshot"],
            ).build_publisher_inventory_snapshot(req, ctx),
            parse_publisher_inventory_snapshot=lambda payload, source, ctx: __import__(
                "src.generators.publisher_inventory_generator",
                fromlist=["parse_publisher_inventory_snapshot"],
            ).parse_publisher_inventory_snapshot(payload, source=source, ctx=ctx),
            get_publisher_inventory_state=lambda req, ctx: _publisher_state(
                with_route=False, with_snapshot=True, snapshot_sha256=snapshot_sha256
            ),
            record_publisher_inventory_state=lambda req, ctx: None,
            list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
                schema_version="1.0", folder_id=req.folder_id, files=[]
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
    deps = PublisherInventoryDependencies(
        discover_publisher_inventory=lambda req, ctx: _service_response(
            used_route_hint=False,
            new_url="https://www.activate.com/reports/new-report",
        ),
        build_publisher_inventory_snapshot=lambda req, ctx: __import__(
            "src.generators.publisher_inventory_generator",
            fromlist=["build_publisher_inventory_snapshot"],
        ).build_publisher_inventory_snapshot(req, ctx),
        parse_publisher_inventory_snapshot=lambda payload, source, ctx: __import__(
            "src.generators.publisher_inventory_generator",
            fromlist=["parse_publisher_inventory_snapshot"],
        ).parse_publisher_inventory_snapshot(payload, source=source, ctx=ctx),
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False, with_snapshot=False, with_folder=False
        ),
        record_publisher_inventory_state=lambda req, ctx: None,
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0", folder_id=req.folder_id, files=[]
        ),
        download_pdf=lambda req, ctx: (_ for _ in ()).throw(AssertionError("should not download snapshot")),
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
