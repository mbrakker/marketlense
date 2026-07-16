from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

from src.contracts.openai import (
    OpenAIEmbeddingRequest,
    OpenAIJSONImagePromptRequest,
    OpenAIResponseRequest,
    OpenAIVectorStoreAttachFileRequest,
    OpenAIVectorStoreCreateRequest,
    OpenAIVectorStoreDeleteRequest,
    OpenAIVectorStoreFileUploadRequest,
    OpenAIVectorStoreStatusRequest,
    OpenAIVectorStoreUpdateMetadataRequest,
)
from src.contracts.run_context import RunContext
from src.services import llm_service as svc


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _events(caplog) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != "market_lense.llm_service.openai":
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events


@pytest.fixture(autouse=True)
def _isolate_relative_usage_artifacts(
    tmp_path, external_boundary_mocks_only
) -> None:
    """Keep default accounting artifacts isolated to the current test."""
    external_boundary_mocks_only.chdir(tmp_path)


def test_openai_response_with_vector_store_finalizes_compatibility_export(
    tmp_path, fake_openai
) -> None:
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
    assert ledger_path.is_file()
    assert daily_path.is_file()
    assert fake_openai.calls["responses.create"][0]["tools"][0]["vector_store_ids"] == [
        "vs_123"
    ]
    assert fake_openai.calls["responses.create"][0]["temperature"] == 0.1
    assert "seed" not in fake_openai.calls["responses.create"][0]
    assert fake_openai.client_kwargs[0]["max_retries"] == 0


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


def test_openai_response_with_vector_store_does_not_retry_unsupported_temperature(
    fake_openai,
    assert_app_error,
) -> None:
    fake_openai.add(
        "responses.create",
        RuntimeError(
            "Error code: 400 - {'error': {'message': \"Unsupported parameter: 'temperature' is not supported with this model.\", 'type': 'invalid_request_error', 'param': 'temperature', 'code': None}}"
        ),
    )
    req = OpenAIResponseRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        vector_store_id="vs_123",
        model="custom-vector-model",
        temperature=0.2,
        api_key="key",
        seed=None,
    )

    with pytest.raises(Exception) as exc_info:
        svc.openai_respond_with_vector_store(req, _ctx())

    assert_app_error(exc_info.value, code="openai_bad_request", retryable=False)
    assert len(fake_openai.calls["responses.create"]) == 1
    assert "temperature" in fake_openai.calls["responses.create"][0]


def test_openai_response_with_vector_store_preserves_prompt_text(fake_openai) -> None:
    fake_openai.queue_response_text(json.dumps({"result": "ok"}))
    req = OpenAIResponseRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="Return findings only.",
        vector_store_id="vs_123",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
    )

    svc.openai_respond_with_vector_store(req, _ctx())

    call = fake_openai.calls["responses.create"][0]
    assert call["instructions"] == "system"
    assert call["input"] == [{"role": "user", "content": "Return findings only."}]


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


def test_openai_chat_json_with_images_does_not_retry_unknown_unsupported_param(
    tmp_path,
    fake_openai,
    assert_app_error,
) -> None:
    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake-image")
    fake_openai.add(
        "responses.create",
        RuntimeError(
            "Error code: 400 - {'error': {'message': \"Unsupported parameter: 'temperature' is not supported with this model.\", 'type': 'invalid_request_error', 'param': 'temperature', 'code': None}}"
        ),
    )
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

    with pytest.raises(Exception) as exc_info:
        svc.openai_chat_json_with_images(req, _ctx())

    assert_app_error(exc_info.value, code="openai_bad_request", retryable=False)
    assert len(fake_openai.calls["responses.create"]) == 1
    assert "temperature" in fake_openai.calls["responses.create"][0]


@pytest.mark.parametrize(
    ("operation", "request_factory"),
    [
        (
            "vector_store",
            lambda tmp_path: (
                svc.openai_respond_with_vector_store,
                OpenAIResponseRequest(
                    schema_version="1.0",
                    system_prompt="system",
                    user_prompt="user",
                    vector_store_id="vs_123",
                    model="gpt-4.1-mini",
                    temperature=0.1,
                    api_key="",
                    cost_ledger_path=str(tmp_path / "ledger.jsonl"),
                    cost_daily_path=str(tmp_path / "daily.json"),
                    model_pricing={},
                ),
            ),
        ),
        (
            "images",
            lambda tmp_path: (
                svc.openai_chat_json_with_images,
                OpenAIJSONImagePromptRequest(
                    schema_version="1.0",
                    system_prompt="system",
                    user_prompt="user",
                    model="gpt-4.1-mini",
                    temperature=0.1,
                    api_key="",
                    image_paths=[str(tmp_path / "test.png")],
                    cost_ledger_path=str(tmp_path / "ledger.jsonl"),
                    cost_daily_path=str(tmp_path / "daily.json"),
                    model_pricing={},
                ),
            ),
        ),
    ],
)
def test_openai_responses_paths_require_api_key(
    tmp_path,
    fake_openai,
    operation,
    request_factory,
    assert_app_error,
) -> None:
    if operation == "images":
        (tmp_path / "test.png").write_bytes(b"fake-image")
    operation_fn, request = request_factory(tmp_path)

    with pytest.raises(Exception) as exc_info:
        operation_fn(request, _ctx())

    assert_app_error(
        exc_info.value,
        code="openai_missing_api_key",
        retryable=False,
    )
    assert fake_openai.client_kwargs == []
    assert fake_openai.calls["responses.create"] == []


@pytest.mark.parametrize(
    ("operation", "request_factory"),
    [
        (
            "vector_store",
            lambda tmp_path: (
                svc.openai_respond_with_vector_store,
                OpenAIResponseRequest(
                    schema_version="1.0",
                    system_prompt="system",
                    user_prompt="user",
                    vector_store_id="vs_123",
                    model="gpt-4.1-mini",
                    temperature=0.1,
                    api_key="key",
                    cost_ledger_path=str(tmp_path / "ledger.jsonl"),
                    cost_daily_path=str(tmp_path / "daily.json"),
                    model_pricing={},
                ),
            ),
        ),
        (
            "images",
            lambda tmp_path: (
                svc.openai_chat_json_with_images,
                OpenAIJSONImagePromptRequest(
                    schema_version="1.0",
                    system_prompt="system",
                    user_prompt="user",
                    model="gpt-4.1-mini",
                    temperature=0.1,
                    api_key="key",
                    image_paths=[str(tmp_path / "test.png")],
                    cost_ledger_path=str(tmp_path / "ledger.jsonl"),
                    cost_daily_path=str(tmp_path / "daily.json"),
                    model_pricing={},
                ),
            ),
        ),
    ],
)
def test_openai_responses_metadata_adapter_preserves_shared_fields(
    tmp_path,
    fake_openai,
    operation,
    request_factory,
) -> None:
    if operation == "images":
        (tmp_path / "test.png").write_bytes(b"fake-image")
    fake_openai.add(
        "responses.create",
        SimpleNamespace(
            output_text=None,
            output=[
                SimpleNamespace(
                    content=[SimpleNamespace(text='{"result":"ok"}')],
                )
            ],
            usage=SimpleNamespace(
                input_tokens=13,
                output_tokens=8,
                total_tokens=21,
            ),
            id="resp_nested_1",
        ),
    )
    operation_fn, request = request_factory(tmp_path)

    result = operation_fn(request, _ctx())

    assert result.text == '{"result":"ok"}'
    assert result.parsed_json == {"result": "ok"}
    assert result.request_id == "resp_nested_1"
    assert result.input_tokens == 13
    assert result.output_tokens == 8
    assert result.tool_calls == 0
    assert result.total_tokens == 21


def test_openai_response_with_vector_store_reads_later_text_blocks(fake_openai) -> None:
    fake_openai.add(
        "responses.create",
        SimpleNamespace(
            output_text=None,
            output=[
                SimpleNamespace(
                    content=[
                        SimpleNamespace(type="reasoning", summary="thinking"),
                        SimpleNamespace(text='{"result":"ok"}'),
                    ],
                )
            ],
            usage=SimpleNamespace(
                input_tokens=11,
                output_tokens=7,
                total_tokens=18,
            ),
            id="resp_multiblock_1",
        ),
    )
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

    assert result.text == '{"result":"ok"}'
    assert result.parsed_json == {"result": "ok"}
    assert result.request_id == "resp_multiblock_1"


def test_openai_response_with_vector_store_ignores_empty_output_text(
    fake_openai,
) -> None:
    fake_openai.add(
        "responses.create",
        SimpleNamespace(
            output_text="",
            output=[
                SimpleNamespace(
                    content=[
                        SimpleNamespace(text='{"result":"fallback"}'),
                    ],
                )
            ],
            usage=SimpleNamespace(
                input_tokens=11,
                output_tokens=7,
                total_tokens=18,
            ),
            id="resp_empty_output_text",
        ),
    )
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

    assert result.text == '{"result":"fallback"}'
    assert result.parsed_json == {"result": "fallback"}
    assert result.request_id == "resp_empty_output_text"


def test_openai_vector_store_create_success(
    fake_openai,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    fake_openai.add("vector_stores.create", {"id": "vs_123"})
    caplog.set_level(logging.INFO, logger="market_lense.llm_service.openai")

    resp = svc.openai_vector_store_create(
        OpenAIVectorStoreCreateRequest(
            schema_version="1.0",
            api_key="key",
            name="report",
            metadata={"report_id": "r1"},
            timeout_seconds=12.0,
        ),
        _ctx(),
    )

    assert resp.vector_store_id == "vs_123"
    assert_no_defaulted_required_fields(resp)
    assert fake_openai.client_kwargs == [
        {"api_key": "key", "max_retries": 0, "timeout": 12.0}
    ]
    assert fake_openai.calls["vector_stores.create"][0]["name"] == "report"
    assert_logs_have_required_fields(_events(caplog))


def test_openai_embedding_service_returns_vectors_and_metadata(
    fake_openai,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    fake_openai.add(
        "embeddings.create",
        SimpleNamespace(
            data=[
                SimpleNamespace(embedding=[0.1, 0.2, 0.3]),
                SimpleNamespace(embedding=[0.4, 0.5, 0.6]),
            ],
            model="text-embedding-3-small",
            usage=SimpleNamespace(prompt_tokens=9, total_tokens=9),
            id="emb_1",
        ),
    )
    caplog.set_level(logging.INFO, logger="market_lense.llm_service.openai")

    resp = svc.openai_create_embeddings(
        OpenAIEmbeddingRequest(
            schema_version="1.0",
            api_key="key",
            model="text-embedding-3-small",
            inputs=["first claim", "second claim"],
            timeout_seconds=8.0,
        ),
        _ctx(),
    )

    assert resp.embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert resp.dimensions == 3
    assert resp.model == "text-embedding-3-small"
    assert resp.request_id == "emb_1"
    assert resp.input_tokens == 9
    assert_no_defaulted_required_fields(resp)
    assert fake_openai.calls["embeddings.create"] == [
        {"model": "text-embedding-3-small", "input": ["first claim", "second claim"]}
    ]
    assert fake_openai.client_kwargs == [
        {"api_key": "key", "max_retries": 0, "timeout": 8.0}
    ]
    assert_logs_have_required_fields(_events(caplog))


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


def test_openai_vector_store_upload_unreadable_path(assert_app_error, tmp_path) -> None:
    try:
        svc.openai_vector_store_upload_file(
            OpenAIVectorStoreFileUploadRequest(
                schema_version="1.0",
                api_key="key",
                file_path=str(tmp_path),
            ),
            _ctx(),
        )
    except Exception as err:
        assert_app_error(err, code="openai_file_open_failed", retryable=False)
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


def test_openai_vector_store_delete_success(fake_openai) -> None:
    fake_openai.add("vector_stores.delete", {"id": "vs_123", "deleted": True})

    resp = svc.openai_vector_store_delete(
        OpenAIVectorStoreDeleteRequest(
            schema_version="1.0",
            api_key="key",
            vector_store_id="vs_123",
            timeout_seconds=7.0,
        ),
        _ctx(),
    )

    assert resp.vector_store_id == "vs_123"
    assert resp.deleted is True
    assert fake_openai.calls["vector_stores.delete"] == [{"vector_store_id": "vs_123"}]


def test_openai_vector_store_delete_uses_requested_id_when_response_omits_id(
    fake_openai,
) -> None:
    fake_openai.add("vector_stores.delete", {"deleted": True})

    resp = svc.openai_vector_store_delete(
        OpenAIVectorStoreDeleteRequest(
            schema_version="1.0",
            api_key="key",
            vector_store_id="vs_requested",
        ),
        _ctx(),
    )

    assert resp.vector_store_id == "vs_requested"
    assert resp.deleted is True


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


@pytest.mark.parametrize(
    ("operation", "request_factory", "expected_code", "expected_context"),
    [
        (
            "vector_stores.create",
            lambda: (
                svc.openai_vector_store_create,
                OpenAIVectorStoreCreateRequest(
                    schema_version="1.0",
                    api_key="key",
                    name="report",
                    metadata={"report_id": "r1"},
                ),
            ),
            "openai_vector_store_create_failed",
            {},
        ),
        (
            "vector_stores.files.create",
            lambda: (
                svc.openai_vector_store_attach_file,
                OpenAIVectorStoreAttachFileRequest(
                    schema_version="1.0",
                    api_key="key",
                    vector_store_id="vs_123",
                    openai_file_id="file_123",
                ),
            ),
            "openai_vector_store_attach_failed",
            {},
        ),
        (
            "vector_stores.retrieve",
            lambda: (
                svc.openai_vector_store_status,
                OpenAIVectorStoreStatusRequest(
                    schema_version="1.0",
                    api_key="key",
                    vector_store_id="vs_123",
                ),
            ),
            "openai_vector_store_status_failed",
            {"vector_store_id": "vs_123"},
        ),
        (
            "vector_stores.delete",
            lambda: (
                svc.openai_vector_store_delete,
                OpenAIVectorStoreDeleteRequest(
                    schema_version="1.0",
                    api_key="key",
                    vector_store_id="vs_123",
                ),
            ),
            "openai_vector_store_delete_failed",
            {"vector_store_id": "vs_123"},
        ),
        (
            "vector_stores.update",
            lambda: (
                svc.openai_vector_store_update_metadata,
                OpenAIVectorStoreUpdateMetadataRequest(
                    schema_version="1.0",
                    api_key="key",
                    vector_store_id="vs_123",
                    metadata={"report_id": "r1"},
                ),
            ),
            "openai_vector_store_update_metadata_failed",
            {"vector_store_id": "vs_123"},
        ),
    ],
)
def test_openai_vector_store_operations_map_request_failures(
    fake_openai,
    assert_app_error,
    operation,
    request_factory,
    expected_code,
    expected_context,
) -> None:
    fake_openai.add(operation, RuntimeError("provider boom"))
    operation_fn, request = request_factory()

    with pytest.raises(Exception) as exc_info:
        operation_fn(request, _ctx())

    assert_app_error(exc_info.value, code=expected_code, retryable=True)
    assert exc_info.value.context == expected_context


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
