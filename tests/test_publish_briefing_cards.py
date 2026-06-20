from dataclasses import replace
from pathlib import Path

from PIL import Image
import pytest

from src.contracts.publish import PublishRequest
from src.generators import publish_generator as pg
from src.utils.errors import AppError
from src.utils.html_utils import build_publish_html_snapshot
from tests.support.fakes import FakeHttpResponse, RecordedHttpRequest


def _add_media_responses(wordpress_http) -> None:
    def _upload(call: RecordedHttpRequest) -> FakeHttpResponse:
        filename = call.files["file"][0]
        media_id = {
            "report-card-small.png": 301,
            "report-card-medium.png": 302,
            "report-card-large.png": 303,
        }[filename]
        return FakeHttpResponse.from_payload(
            status_code=201,
            payload={
                "id": media_id,
                "source_url": f"https://example.com/uploads/{filename}",
            },
        )

    wordpress_http.add(
        "POST", "https://example.com/wp-json/wp/v2/media", _upload
    )
    for media_id in (301, 302, 303):
        wordpress_http.add_json(
            "POST",
            f"https://example.com/wp-json/wp/v2/media/{media_id}",
            status_code=200,
            payload={"id": media_id},
        )


def _briefing_settings(publish_settings_factory):
    settings = publish_settings_factory(validation_policy="warn")
    return replace(settings, wp=replace(settings.wp, post_type="ml_briefing"))


def test_publish_html_updates_existing_briefing_card_post_in_place(
    publish_settings_factory,
    run_context,
    wordpress_http,
) -> None:
    settings = _briefing_settings(publish_settings_factory)
    html_path = Path(settings.output_dir) / "briefing" / "publish.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    covers = {}
    for size in ("small", "medium", "large"):
        path = html_path.parent / f"report-card-{size}.png"
        Image.new("RGB", (40, 40), color="#092b55").save(path)
        covers[size] = str(path)
    card = {
        "schema_version": "1.0",
        "summary_compact": "Compact briefing summary.",
        "summary_standard": "Standard briefing summary with verified context.",
        "decision_focus": "Prioritize the verified market signal.",
        "takeaways": ["First takeaway.", "Second takeaway."],
        "source_count": 4,
        "evidence_count": 32,
        "covers": covers,
    }
    html_text = (
        "<html><head><title>Briefing</title></head>"
        "<body>Drive fileId: cross-report:briefing</body></html>"
    )
    html_path.write_text(html_text, encoding="utf-8")
    snapshot = replace(build_publish_html_snapshot(html_text), briefing_card=card)
    _add_media_responses(wordpress_http)
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_briefing/42",
        status_code=200,
        payload={"id": 42, "link": "https://example.com/briefing/42"},
    )

    outcome = pg.publish_html(
        PublishRequest(
            schema_version="1.0",
            html_path=str(html_path),
            auth_header="Bearer token",
            file_id="cross-report:briefing",
            html_snapshot=snapshot,
            existing_post_id=42,
        ),
        settings,
        run_context,
    )

    update_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_briefing/42"
    )[0]
    assert outcome.status == "published"
    assert outcome.post_id == 42
    assert update_call.json_data["featured_media"] == 303
    assert update_call.json_data["meta"] == {
        "ml_briefing_card_schema_version": "1.0",
        "ml_briefing_card_summary_compact": "Compact briefing summary.",
        "ml_briefing_card_summary_standard": (
            "Standard briefing summary with verified context."
        ),
        "ml_briefing_card_decision_focus": "Prioritize the verified market signal.",
        "ml_briefing_card_takeaways": ["First takeaway.", "Second takeaway."],
        "ml_briefing_source_count": 4,
        "ml_briefing_evidence_count": 32,
        "ml_briefing_card_cover_small_id": 301,
        "ml_briefing_card_cover_medium_id": 302,
        "ml_briefing_card_cover_large_id": 303,
    }
    assert wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_briefing"
    ) == []


def test_existing_briefing_update_rejects_incomplete_cover_set_before_upload(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_app_error,
) -> None:
    settings = _briefing_settings(publish_settings_factory)
    html_path = Path(settings.output_dir) / "briefing" / "publish.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_text = "<html><body>Drive fileId: cross-report:briefing</body></html>"
    html_path.write_text(html_text, encoding="utf-8")
    snapshot = replace(
        build_publish_html_snapshot(html_text),
        briefing_card={
            "summary_compact": "Compact briefing summary.",
            "summary_standard": "Standard briefing summary.",
            "decision_focus": "Prioritize the verified signal.",
            "takeaways": ["First takeaway.", "Second takeaway."],
            "source_count": 4,
            "evidence_count": 32,
            "covers": {"small": "small.png", "medium": "medium.png"},
        },
    )

    with pytest.raises(AppError) as exc_info:
        pg.publish_html(
            PublishRequest(
                schema_version="1.0",
                html_path=str(html_path),
                auth_header="Bearer token",
                file_id="cross-report:briefing",
                html_snapshot=snapshot,
                existing_post_id=42,
            ),
            settings,
            run_context,
        )

    assert_app_error(
        exc_info.value, code="cover_asset_set_incomplete", retryable=False
    )
    assert wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/media"
    ) == []
