from __future__ import annotations

import logging

import pytest

from src.contracts.publisher_inventory import (
    PublisherInventoryBuildRequest,
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
)
from src.generators.publisher_inventory_generator import (
    build_publisher_inventory_snapshot,
    parse_publisher_inventory_snapshot,
)
from src.utils.errors import AppError


def _events(caplog, logger_name: str) -> list[dict[str, object]]:
    import json

    rows: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != logger_name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def test_build_publisher_inventory_snapshot_normalizes_dedupes_and_diffs(
    run_context,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
):
    previous = build_publisher_inventory_snapshot(
        PublisherInventoryBuildRequest(
            schema_version="1.0",
            publisher_name="Activate Consulting",
            insights_url="https://www.activate.com/insights",
            normalized_insights_url="https://www.activate.com/insights",
            discovered_at_utc="2026-03-28T00:00:00Z",
            route_kind="http_parse",
            route_summary="Fetched HTML directly.",
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
                    url="/reports/existing-report",
                    title="Existing Report",
                    source_page_url="https://www.activate.com/insights",
                    discovered_on_page_number=1,
                )
            ],
        ),
        run_context,
    ).snapshot

    caplog.set_level(logging.INFO, logger="market_lense.publisher_inventory_generator")
    response = build_publisher_inventory_snapshot(
        PublisherInventoryBuildRequest(
            schema_version="1.0",
            publisher_name="Activate Consulting",
            insights_url="https://www.activate.com/insights",
            normalized_insights_url="https://www.activate.com/insights",
            discovered_at_utc="2026-03-29T00:00:00Z",
            route_kind="http_parse",
            route_summary="Fetched HTML directly and traversed 2 pages.",
            final_page_url="https://www.activate.com/insights?page=2",
            pages=[
                PublisherInventoryPage(
                    schema_version="1.0",
                    page_number=2,
                    page_url="https://www.activate.com/insights?page=2",
                ),
                PublisherInventoryPage(
                    schema_version="1.0",
                    page_number=1,
                    page_url="https://www.activate.com/insights",
                ),
            ],
            candidates=[
                PublisherInventoryRawCandidate(
                    schema_version="1.0",
                    url="/reports/new-report",
                    title="New Report 2026",
                    source_page_url="https://www.activate.com/insights?page=2",
                    discovered_on_page_number=2,
                ),
                PublisherInventoryRawCandidate(
                    schema_version="1.0",
                    url="https://www.activate.com/reports/new-report",
                    title="New Report 2026",
                    source_page_url="https://www.activate.com/insights?page=2",
                    discovered_on_page_number=2,
                ),
                PublisherInventoryRawCandidate(
                    schema_version="1.0",
                    url="/reports/existing-report",
                    title="Existing Report",
                    source_page_url="https://www.activate.com/insights",
                    discovered_on_page_number=1,
                ),
            ],
            previous_snapshot=previous,
        ),
        run_context,
    )

    assert response.current_report_count == 2
    assert response.previous_report_count == 1
    assert len(response.new_items) == 1
    assert (
        response.new_items[0].canonical_url
        == "https://www.activate.com/reports/new-report"
    )
    assert response.new_items[0].discovered_on_page_number == 2
    assert (
        response.snapshot.items[0].canonical_url
        == "https://www.activate.com/reports/existing-report"
    )
    assert (
        response.snapshot.items[1].canonical_url
        == "https://www.activate.com/reports/new-report"
    )
    assert response.snapshot.pages[0].page_number == 1
    assert_no_defaulted_required_fields(response.snapshot)
    parsed = parse_publisher_inventory_snapshot(
        response.snapshot_json,
        source="memory",
        ctx=run_context,
    )
    assert parsed == response.snapshot
    assert_logs_have_required_fields(
        _events(caplog, "market_lense.publisher_inventory_generator")
    )


def test_build_publisher_inventory_snapshot_rejects_empty_inventory(
    run_context,
    assert_app_error,
):
    with pytest.raises(AppError) as err:
        build_publisher_inventory_snapshot(
            PublisherInventoryBuildRequest(
                schema_version="1.0",
                publisher_name="Activate Consulting",
                insights_url="https://www.activate.com/insights",
                normalized_insights_url="https://www.activate.com/insights",
                discovered_at_utc="2026-03-29T00:00:00Z",
                route_kind="http_parse",
                route_summary="Fetched HTML directly.",
                final_page_url="https://www.activate.com/insights",
                pages=[],
                candidates=[],
                previous_snapshot=None,
            ),
            run_context,
        )
    assert_app_error(err.value, code="publisher_inventory_empty", retryable=False)


def test_build_publisher_inventory_snapshot_hash_ignores_volatile_run_metadata(
    run_context,
):
    first = build_publisher_inventory_snapshot(
        PublisherInventoryBuildRequest(
            schema_version="1.0",
            publisher_name="Activate Consulting",
            insights_url="https://www.activate.com/insights",
            normalized_insights_url="https://www.activate.com/insights",
            discovered_at_utc="2026-03-28T00:00:00Z",
            route_kind="http_parse",
            route_summary="Fetched HTML directly.",
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
                    url="/reports/existing-report",
                    title="Existing Report",
                    source_page_url="https://www.activate.com/insights",
                    discovered_on_page_number=1,
                )
            ],
        ),
        run_context,
    )
    second = build_publisher_inventory_snapshot(
        PublisherInventoryBuildRequest(
            schema_version="1.0",
            publisher_name="Activate Consulting",
            insights_url="https://www.activate.com/insights",
            normalized_insights_url="https://www.activate.com/insights",
            discovered_at_utc="2026-03-29T12:34:56Z",
            route_kind="browser_render",
            route_summary="Open the page and extract the same cards.",
            final_page_url="https://www.activate.com/insights?page=99",
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
                    url="https://www.activate.com/reports/existing-report",
                    title="Existing Report",
                    source_page_url="https://www.activate.com/insights",
                    discovered_on_page_number=1,
                )
            ],
        ),
        run_context,
    )

    assert first.snapshot_sha256 == second.snapshot_sha256


def test_build_publisher_inventory_snapshot_replaces_placeholder_title_with_url_slug(
    run_context,
) -> None:
    response = build_publisher_inventory_snapshot(
        PublisherInventoryBuildRequest(
            schema_version="1.0",
            publisher_name="Marmind",
            insights_url="https://www.marmind.com/guides-whitepapers",
            normalized_insights_url="https://www.marmind.com/guides-whitepapers",
            discovered_at_utc="2026-04-04T00:00:00Z",
            route_kind="browser_render",
            route_summary="Rendered archive page.",
            final_page_url="https://www.marmind.com/guides-whitepapers",
            pages=[
                PublisherInventoryPage(
                    schema_version="1.0",
                    page_number=1,
                    page_url="https://www.marmind.com/guides-whitepapers",
                )
            ],
            candidates=[
                PublisherInventoryRawCandidate(
                    schema_version="1.0",
                    url="https://www.marmind.com/guides-whitepapers/buyers-guide-marketing-resource-management",
                    title="feature-img",
                    source_page_url="https://www.marmind.com/guides-whitepapers",
                    discovered_on_page_number=1,
                )
            ],
            previous_snapshot=None,
        ),
        run_context,
    )

    assert (
        response.snapshot.items[0].title == "buyers guide marketing resource management"
    )
