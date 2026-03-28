from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contracts.publisher_profiles import PublisherProfilesSnapshotLoadRequest
from src.generators.publisher_profiles_generator import (
    load_publisher_profiles_snapshot,
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


def test_load_publisher_profiles_snapshot_returns_validated_rows(
    tmp_path: Path,
    caplog,
    run_context,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    snapshot_path = tmp_path / "publisher-profiles.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source_page_url": "https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d",
                "publisher_count": 2,
                "publishers": [
                    {
                        "schema_version": "1.0",
                        "notion_page_id": "page-1",
                        "notion_page_url": "https://www.notion.so/page-1",
                        "name": "Activate Consulting",
                        "homepage": "https://www.activate.com/",
                        "self_presentation": "Activate description",
                        "insights_url": "https://www.activate.com/insights",
                        "icon_source": "https://cdn.example.com/activate.png",
                    },
                    {
                        "schema_version": "1.0",
                        "notion_page_id": "page-2",
                        "notion_page_url": "https://www.notion.so/page-2",
                        "name": "Criteo",
                        "homepage": "https://www.criteo.com/",
                        "self_presentation": "Criteo description",
                        "insights_url": "https://www.criteo.com/resources/",
                        "icon_source": "https://cdn.example.com/criteo.png",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = load_publisher_profiles_snapshot(
        PublisherProfilesSnapshotLoadRequest(
            schema_version="1.0",
            snapshot_path=str(snapshot_path),
        ),
        run_context,
    )

    assert result.publisher_count == 2
    assert result.source_page_url == "https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d"
    assert result.publishers[0].name == "Activate Consulting"
    assert_no_defaulted_required_fields(result)
    assert_logs_have_required_fields(
        _events(caplog, "market_lense.publisher_profiles_generator")
    )


def test_load_publisher_profiles_snapshot_rejects_count_mismatch(
    tmp_path: Path,
    run_context,
    assert_app_error,
) -> None:
    snapshot_path = tmp_path / "publisher-profiles.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source_page_url": "https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d",
                "publisher_count": 2,
                "publishers": [
                    {
                        "schema_version": "1.0",
                        "notion_page_id": "page-1",
                        "notion_page_url": "https://www.notion.so/page-1",
                        "name": "Activate Consulting",
                        "homepage": "https://www.activate.com/",
                        "self_presentation": "Activate description",
                        "insights_url": "https://www.activate.com/insights",
                        "icon_source": "https://cdn.example.com/activate.png",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AppError) as exc_info:
        load_publisher_profiles_snapshot(
            PublisherProfilesSnapshotLoadRequest(
                schema_version="1.0",
                snapshot_path=str(snapshot_path),
            ),
            run_context,
        )

    assert_app_error(
        exc_info.value,
        code="publisher_snapshot_count_mismatch",
        retryable=False,
        severity="error",
    )
