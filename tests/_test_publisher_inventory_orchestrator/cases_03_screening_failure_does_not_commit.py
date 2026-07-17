# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_run_publisher_inventory_discovery_screening_failure_does_not_commit_snapshot(
    tmp_path,
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
            replace(_request(settings), state_db=str(tmp_path / "state.sqlite")),
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
    records = list_remediation_records(
        RemediationListRequest(
            schema_version="1.0",
            state_db=str(tmp_path / "state.sqlite"),
            workflow="publisher_inventory_discovery",
        ),
        run_context,
    ).records
    assert len(records) == 1
    assert records[0].error_code == "publisher_inventory_candidate_screen_invalid_json"
    assert records[0].status == "operator_action_required"


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


__all__ = [
    "test_run_publisher_inventory_discovery_screening_failure_does_not_commit_snapshot",
    "test_run_publisher_inventory_discovery_fails_when_all_screened_candidates_are_unreachable",
    "test_run_publisher_inventory_discovery_tolerates_unreachable_delta_when_previous_snapshot_exists",
]
