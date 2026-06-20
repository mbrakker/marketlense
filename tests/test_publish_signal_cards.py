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
            "signal-card-small.png": 401,
            "signal-card-medium.png": 402,
            "signal-card-large.png": 403,
        }[filename]
        return FakeHttpResponse.from_payload(
            status_code=201,
            payload={
                "id": media_id,
                "source_url": f"https://example.com/uploads/{filename}",
            },
        )

    wordpress_http.add("POST", "https://example.com/wp-json/wp/v2/media", _upload)
    for media_id in (401, 402, 403):
        wordpress_http.add_json(
            "POST",
            f"https://example.com/wp-json/wp/v2/media/{media_id}",
            status_code=200,
            payload={"id": media_id},
        )


def _signal_settings(publish_settings_factory):
    settings = publish_settings_factory(validation_policy="warn")
    return replace(settings, wp=replace(settings.wp, post_type="ml_signal"))


def _signal_card(html_path: Path) -> dict[str, object]:
    covers = {}
    for size in ("small", "medium", "large"):
        path = html_path.parent / f"signal-card-{size}.png"
        Image.new("RGB", (40, 40), color="#062a42").save(path)
        covers[size] = str(path)
    return {
        "schema_version": "1.0",
        "summary": "Checkout trust is becoming a conversion condition.",
        "confidence": 0.84,
        "source_count": 5,
        "evidence_count": 14,
        "uncertainty": "Coverage is strongest in retail and technology publishers.",
        "covers": covers,
    }


def test_publish_html_updates_existing_signal_card_post_in_place(
    publish_settings_factory,
    run_context,
    wordpress_http,
) -> None:
    settings = _signal_settings(publish_settings_factory)
    html_path = Path(settings.output_dir) / "signal" / "publish.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_text = "<html><body>Drive fileId: signal:checkout-trust</body></html>"
    html_path.write_text(html_text, encoding="utf-8")
    snapshot = replace(
        build_publish_html_snapshot(html_text), signal_card=_signal_card(html_path)
    )
    _add_media_responses(wordpress_http)
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_signal/52",
        status_code=200,
        payload={"id": 52, "link": "https://example.com/signals/52"},
    )

    outcome = pg.publish_html(
        PublishRequest(
            schema_version="1.0",
            html_path=str(html_path),
            auth_header="Bearer token",
            file_id="signal:checkout-trust",
            html_snapshot=snapshot,
            existing_post_id=52,
        ),
        settings,
        run_context,
    )

    update_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_signal/52"
    )[0]
    assert outcome.status == "published"
    assert outcome.post_id == 52
    assert update_call.json_data["featured_media"] == 403
    assert update_call.json_data["meta"] == {
        "ml_signal_card_schema_version": "1.0",
        "ml_signal_card_summary": "Checkout trust is becoming a conversion condition.",
        "ml_signal_card_uncertainty": (
            "Coverage is strongest in retail and technology publishers."
        ),
        "ml_signal_card_confidence": 0.84,
        "ml_signal_source_count": 5,
        "ml_signal_evidence_count": 14,
        "ml_signal_card_cover_small_id": 401,
        "ml_signal_card_cover_medium_id": 402,
        "ml_signal_card_cover_large_id": 403,
    }


def test_signal_card_rejects_incomplete_cover_set_before_upload(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_app_error,
) -> None:
    settings = _signal_settings(publish_settings_factory)
    html_path = Path(settings.output_dir) / "signal" / "publish.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_text = "<html><body>Drive fileId: signal:checkout-trust</body></html>"
    html_path.write_text(html_text, encoding="utf-8")
    snapshot = replace(
        build_publish_html_snapshot(html_text),
        signal_card={
            "summary": "Checkout trust is becoming a conversion condition.",
            "confidence": 0.84,
            "source_count": 5,
            "evidence_count": 14,
            "uncertainty": "Coverage is strongest in retail and technology publishers.",
            "covers": {"small": "small.png", "medium": "medium.png"},
        },
    )

    with pytest.raises(AppError) as exc_info:
        pg.publish_html(
            PublishRequest(
                schema_version="1.0",
                html_path=str(html_path),
                auth_header="Bearer token",
                file_id="signal:checkout-trust",
                html_snapshot=snapshot,
                existing_post_id=52,
            ),
            settings,
            run_context,
        )

    assert_app_error(exc_info.value, code="cover_asset_set_incomplete", retryable=False)
    assert (
        wordpress_http.calls_for("POST", "https://example.com/wp-json/wp/v2/media")
        == []
    )
