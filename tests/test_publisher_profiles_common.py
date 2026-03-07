from __future__ import annotations

import json
from pathlib import Path

import pytest

from Wordpress.scripts.publisher_profiles_common import (
    build_term_payload,
    load_profile_rows,
    resolve_icon_download_url,
    split_multiline_urls,
)


def test_load_profile_rows_normalizes_urls_and_builds_term_payload(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "publisher-profiles.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "publishers": [
                    {
                        "notion_page_id": "157290cc-00d3-80c8-9980-e347ba67fc62",
                        "notion_page_url": "https://www.notion.so/157290cc00d380c89980e347ba67fc62",
                        "name": "Impact",
                        "homepage": "Impact.com",
                        "self_presentation": "Insights to Own the FutureOur research informs client growth.",
                        "insights_url": "https://example.com/report-one, https://example.com/report-two",
                        "icon_source": "data:image/png;base64,AAAA",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    rows = load_profile_rows(config_path)

    assert len(rows) == 1
    row = rows[0]
    assert row.slug == "impact"
    assert row.homepage == "https://Impact.com"
    assert row.self_presentation == "Insights to Own the Future Our research informs client growth."
    assert split_multiline_urls(row.insights_url) == [
        "https://example.com/report-one",
        "https://example.com/report-two",
    ]
    assert row.icon_source == "data:image/png;base64,AAAA"

    payload = build_term_payload(row)

    assert payload["description"] == row.self_presentation
    assert payload["meta"] == {
        "ml_publisher_homepage": "https://Impact.com",
        "ml_publisher_insights_url": "https://example.com/report-one\nhttps://example.com/report-two",
        "ml_publisher_icon_source": "data:image/png;base64,AAAA",
        "ml_publisher_notion_page_id": "157290cc-00d3-80c8-9980-e347ba67fc62",
        "ml_publisher_notion_page_url": "https://www.notion.so/157290cc00d380c89980e347ba67fc62",
    }


def test_load_profile_rows_rejects_missing_name(tmp_path: Path) -> None:
    config_path = tmp_path / "publisher-profiles.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "publishers": [
                    {
                        "notion_page_id": "157290cc-00d3-80c8-9980-e347ba67fc62",
                        "notion_page_url": "https://www.notion.so/157290cc00d380c89980e347ba67fc62",
                        "name": "",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="missing a name"):
        load_profile_rows(config_path)


def test_resolve_icon_download_url_prefers_public_override(tmp_path: Path) -> None:
    config_path = tmp_path / "publisher-profiles.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "publishers": [
                    {
                        "notion_page_id": "157290cc-00d3-80c8-9980-e347ba67fc62",
                        "notion_page_url": "https://www.notion.so/157290cc00d380c89980e347ba67fc62",
                        "name": "Activate Consulting",
                        "icon_source": "https://prod-files-secure.s3.us-west-2.amazonaws.com/private-icon.png",
                    },
                    {
                        "notion_page_id": "102290cc-00d3-802e-9715-dfd8f7acba65",
                        "notion_page_url": "https://www.notion.so/102290cc00d3802e9715dfd8f7acba65",
                        "name": "Cross Border Commerce",
                        "icon_source": "https://www.cbcommerce.eu/icon.png",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    rows = load_profile_rows(config_path)

    assert resolve_icon_download_url(rows[0]) == "https://www.activate.com/assets/icon-light.png"
    assert resolve_icon_download_url(rows[1]) == "https://www.cbcommerce.eu/icon.png"
