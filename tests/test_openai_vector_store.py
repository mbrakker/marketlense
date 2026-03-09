from __future__ import annotations

import json

from src.contracts.openai import (
    OpenAIJSONImagePromptRequest,
    OpenAIResponseRequest,
    OpenAIVectorStoreCreateRequest,
    OpenAIVectorStoreFileUploadRequest,
    OpenAIVectorStoreStatusRequest,
    OpenAIVectorStoreUpdateMetadataRequest,
)
from src.contracts.run_context import RunContext
from src.services import openai_service as svc


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_openai_response_with_vector_store_writes_ledger(tmp_path, fake_openai) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    daily_path = tmp_path / "daily.json"
    fake_openai.queue_response_text(json.dumps({"result": "ok"}))
    req = OpenAIResponseRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        vector_store_id="vs_123",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
        seed=123,
        timeout_seconds=5.0,
        cost_ledger_path=str(ledger_path),
        cost_daily_path=str(daily_path),
        model_pricing={
            "gpt-4.1-mini": {
                "input_tokens_per_1k_usd": 0.003,
                "output_tokens_per_1k_usd": 0.006,
                "tool_call_usd": 0.0,
            }
        },
    )

    resp = svc.openai_respond_with_vector_store(req, _ctx())

    assert resp.text
    assert resp.parsed_json == {"result": "ok"}
    assert resp.request_id == "resp_1"
    assert resp.total_tokens == 30
    assert ledger_path.exists()
    assert daily_path.exists()
    ledger_lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert ledger_lines and json.loads(ledger_lines[0])["model"] == "gpt-4.1-mini"
    assert fake_openai.calls["responses.create"][0]["tools"][0]["vector_store_ids"] == [
        "vs_123"
    ]


def test_openai_response_with_vector_store_requires_vector_store_id(
    assert_app_error,
) -> None:
    req = OpenAIResponseRequest(
        schema_version="1.0",
        system_prompt="s",
        user_prompt="u",
        vector_store_id="",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
    )

    try:
        svc.openai_respond_with_vector_store(req, _ctx())
    except Exception as err:
        assert_app_error(err, code="vector_store_missing", retryable=False)
    else:  # pragma: no cover
        raise AssertionError("expected AppError")


def test_openai_response_with_vector_store_rejects_non_json(
    fake_openai, assert_app_error
) -> None:
    fake_openai.queue_response_text("not-json")
    req = OpenAIResponseRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        vector_store_id="vs_123",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
    )

    try:
        svc.openai_respond_with_vector_store(req, _ctx())
    except Exception as err:
        assert_app_error(err, code="openai_response_invalid_json", retryable=False)
    else:  # pragma: no cover
        raise AssertionError("expected AppError")


def test_openai_response_with_vector_store_rejects_json_arrays(
    fake_openai, assert_app_error
) -> None:
    fake_openai.queue_response_text(json.dumps([{"result": "ok"}]))
    req = OpenAIResponseRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        vector_store_id="vs_123",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
    )

    try:
        svc.openai_respond_with_vector_store(req, _ctx())
    except Exception as err:
        assert_app_error(err, code="openai_response_json_type_invalid", retryable=False)
    else:  # pragma: no cover
        raise AssertionError("expected AppError")


def test_openai_response_with_vector_store_parses_fenced_json(fake_openai) -> None:
    fake_openai.queue_response_text('```json\n{"result":"ok"}\n```')
    req = OpenAIResponseRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        vector_store_id="vs_123",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
    )

    result = svc.openai_respond_with_vector_store(req, _ctx())

    assert result.parsed_json == {"result": "ok"}


def test_openai_chat_json_with_images_skips_known_unsupported_params(
    tmp_path, fake_openai
) -> None:
    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake-image")
    fake_openai.queue_response_text(json.dumps({"results": []}))
    req = OpenAIJSONImagePromptRequest(
        schema_version="1.0",
        system_prompt="return json",
        user_prompt="return json",
        model="gpt-5-mini",
        temperature=0.0,
        api_key="key",
        image_paths=[str(image_path)],
        seed=123,
        timeout_seconds=5.0,
        cost_ledger_path=str(tmp_path / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        model_pricing={},
    )

    result = svc.openai_chat_json_with_images(req, _ctx())

    call = fake_openai.calls["responses.create"][0]
    assert result.parsed_json == {"results": []}
    assert "temperature" not in call
    assert "seed" not in call


def test_openai_chat_json_with_images_retries_unknown_unsupported_param(
    tmp_path, fake_openai
) -> None:
    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake-image")
    fake_openai.add(
        "responses.create",
        Exception(
            "Error code: 400 - {'error': {'message': \"Unsupported parameter: 'temperature' is not supported with this model.\", 'type': 'invalid_request_error', 'param': 'temperature', 'code': None}}"
        ),
    )
    fake_openai.queue_response_text(json.dumps({"results": []}))
    req = OpenAIJSONImagePromptRequest(
        schema_version="1.0",
        system_prompt="return json",
        user_prompt="return json",
        model="custom-image-model",
        temperature=0.0,
        api_key="key",
        image_paths=[str(image_path)],
        seed=None,
        timeout_seconds=5.0,
        cost_ledger_path=str(tmp_path / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        model_pricing={},
    )

    result = svc.openai_chat_json_with_images(req, _ctx())

    first_call, second_call = fake_openai.calls["responses.create"]
    assert result.parsed_json == {"results": []}
    assert "temperature" in first_call
    assert "temperature" not in second_call


def test_openai_vector_store_create_success(fake_openai) -> None:
    fake_openai.add("vector_stores.create", {"id": "vs_123"})

    resp = svc.openai_vector_store_create(
        OpenAIVectorStoreCreateRequest(
            schema_version="1.0",
            api_key="key",
            name="report",
            metadata={"report_id": "r1"},
        ),
        _ctx(),
    )

    assert resp.vector_store_id == "vs_123"
    assert fake_openai.calls["vector_stores.create"][0]["name"] == "report"


def test_openai_vector_store_upload_missing_file(assert_app_error, tmp_path) -> None:
    try:
        svc.openai_vector_store_upload_file(
            OpenAIVectorStoreFileUploadRequest(
                schema_version="1.0",
                api_key="key",
                file_path=str(tmp_path / "missing.pdf"),
            ),
            _ctx(),
        )
    except Exception as err:
        assert_app_error(err, code="openai_file_missing", retryable=False)
    else:  # pragma: no cover
        raise AssertionError("expected AppError")


def test_openai_vector_store_status_reads_dict_response(fake_openai) -> None:
    fake_openai.add(
        "vector_stores.retrieve",
        {
            "status": "completed",
            "created_at": "2026-01-07T00:00:00Z",
            "last_error": None,
        },
    )

    resp = svc.openai_vector_store_status(
        OpenAIVectorStoreStatusRequest(
            schema_version="1.0",
            api_key="key",
            vector_store_id="vs_123",
        ),
        _ctx(),
    )

    assert resp.status == "completed"
    assert resp.indexed_at_utc == "2026-01-07T00:00:00Z"


def test_openai_vector_store_update_metadata_missing_id(
    fake_openai, assert_app_error
) -> None:
    fake_openai.add("vector_stores.update", {})

    try:
        svc.openai_vector_store_update_metadata(
            OpenAIVectorStoreUpdateMetadataRequest(
                schema_version="1.0",
                api_key="key",
                vector_store_id="vs_123",
                metadata={"report_id": "r1"},
            ),
            _ctx(),
        )
    except Exception as err:
        assert_app_error(
            err, code="openai_vector_store_update_metadata_failed", retryable=True
        )
    else:  # pragma: no cover
        raise AssertionError("expected AppError")


def test_image_path_to_data_url_defaults_png_for_unknown_extension(tmp_path) -> None:
    image_path = tmp_path / "raw-image"
    image_path.write_bytes(b"png-bytes")

    data_url = svc._image_path_to_data_url(str(image_path))

    assert data_url.startswith("data:image/png;base64,")


def test_openai_strip_json_fence_requires_closing_fence() -> None:
    raw = '```json\n{"key":1}\n'
    assert svc._strip_json_fence(raw) == raw.strip()


def test_openai_strip_json_fence_strips_allowed_json_fence() -> None:
    raw = '```json\n{"key":1}\n```'
    assert svc._strip_json_fence(raw) == '{"key":1}'
