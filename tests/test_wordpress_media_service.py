from __future__ import annotations

from io import BytesIO
import json
import logging

from PIL import Image

from src.contracts.run_context import RunContext
from src.contracts.wordpress import WordPressMediaPrepareRequest
from src.services import wordpress_service


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_prepare_media_upload_optimizes_large_image_and_preserves_non_image() -> None:
    large_buffer = BytesIO()
    Image.effect_noise((2200, 1600), 90).convert("RGB").save(
        large_buffer,
        format="PNG",
    )
    large_data = large_buffer.getvalue()

    optimized = wordpress_service.prepare_media_upload(
        WordPressMediaPrepareRequest(
            schema_version="1.0",
            filename="large-cover.png",
            mime_type="image/png",
            data=large_data,
        ),
        _ctx(),
    )
    preserved = wordpress_service.prepare_media_upload(
        WordPressMediaPrepareRequest(
            schema_version="1.0",
            filename="note.txt",
            mime_type="text/plain",
            data=b"plain text",
        ),
        _ctx(),
    )

    assert optimized.optimized is True
    assert optimized.filename == "large-cover.jpg"
    assert optimized.mime_type == "image/jpeg"
    assert optimized.data.startswith(b"\xff\xd8")
    assert len(optimized.data) < len(large_data)
    assert optimized.original_size_bytes == len(large_data)
    assert preserved.optimized is False
    assert preserved.filename == "note.txt"
    assert preserved.data == b"plain text"
    assert preserved.reason == "not_image"


def test_prepare_media_upload_returns_decode_failure_without_data_loss() -> None:
    response = wordpress_service.prepare_media_upload(
        WordPressMediaPrepareRequest(
            schema_version="1.0",
            filename="broken.png",
            mime_type="image/png",
            data=b"not an image",
        ),
        _ctx(),
    )

    assert response.optimized is False
    assert response.data == b"not an image"
    assert response.reason == "image_decode_failed"


def test_prepare_media_upload_logs_when_optimized_payload_is_not_smaller(
    caplog,
) -> None:
    image_buffer = BytesIO()
    Image.new("RGB", (2000, 1), "white").save(image_buffer, format="PNG")
    original = image_buffer.getvalue()

    with caplog.at_level(logging.INFO):
        response = wordpress_service.prepare_media_upload(
            WordPressMediaPrepareRequest(
                schema_version="1.0",
                filename="wide.png",
                mime_type="image/png",
                data=original,
            ),
            _ctx(),
        )

    assert response.reason == "optimized_not_smaller"
    assert response.data == original
    events = [
        json.loads(record.message)
        for record in caplog.records
        if "publish_media_optimization_skipped" in record.message
    ]
    assert len(events) == 1
    assert events[0]["fields"]["reason"] == "optimized_not_smaller"
