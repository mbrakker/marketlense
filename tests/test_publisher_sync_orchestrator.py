from __future__ import annotations

import json
import logging

import pytest

from src.contracts.publisher_profiles import (
    PublisherProfileRecord,
    PublisherProfilesSnapshotLoadResponse,
    PublisherSyncRequest,
)
from src.contracts.report_store import PublishersReplaceResponse
from src.orchestrators.publisher_sync_orchestrator import (
    PublisherSyncDependencies,
    run_publisher_sync,
)
from src.utils.errors import AppError


def _events(caplog, logger_name: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != logger_name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def test_run_publisher_sync_loads_snapshot_and_replaces_publishers(
    caplog,
    run_context,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    load_calls: list[object] = []
    replace_calls: list[object] = []

    deps = PublisherSyncDependencies(
        load_publisher_profiles_snapshot=lambda req, ctx: (
            load_calls.append(req)
            or PublisherProfilesSnapshotLoadResponse(
                schema_version="1.0",
                snapshot_path=req.snapshot_path,
                source_page_url="https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d",
                publisher_count=1,
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
            )
        ),
        replace_publishers=lambda req, ctx: (
            replace_calls.append(req)
            or PublishersReplaceResponse(
                schema_version="1.0",
                db_path=req.db_path,
                source_page_url=req.source_page_url,
                previous_count=0,
                replaced_count=len(req.publishers),
            )
        ),
    )
    caplog.set_level(logging.INFO, logger="market_lense.publisher_sync_orchestrator")

    result = run_publisher_sync(
        PublisherSyncRequest(
            schema_version="1.0",
            snapshot_path="./Wordpress/config/publisher-profiles.json",
            reports_db="./state/reports.sqlite",
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert len(load_calls) == 1
    assert len(replace_calls) == 1
    assert replace_calls[0].db_path == "./state/reports.sqlite"
    assert replace_calls[0].source_page_url == "https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d"
    assert result.replaced_count == 1
    assert_no_defaulted_required_fields(result)
    assert_logs_have_required_fields(
        _events(caplog, "market_lense.publisher_sync_orchestrator")
    )


def test_run_publisher_sync_propagates_typed_errors(
    run_context,
    assert_app_error,
) -> None:
    deps = PublisherSyncDependencies(
        load_publisher_profiles_snapshot=lambda req, ctx: (_ for _ in ()).throw(
            AppError(
                code="publisher_snapshot_invalid_json",
                message="broken snapshot",
                retryable=False,
                severity="error",
            )
        ),
        replace_publishers=lambda req, ctx: PublishersReplaceResponse(
            schema_version="1.0",
            db_path=req.db_path,
            source_page_url=req.source_page_url,
            previous_count=0,
            replaced_count=0,
        ),
    )

    with pytest.raises(AppError) as exc_info:
        run_publisher_sync(
            PublisherSyncRequest(
                schema_version="1.0",
                snapshot_path="./Wordpress/config/publisher-profiles.json",
                reports_db="./state/reports.sqlite",
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert_app_error(
        exc_info.value,
        code="publisher_snapshot_invalid_json",
        retryable=False,
        severity="error",
    )
