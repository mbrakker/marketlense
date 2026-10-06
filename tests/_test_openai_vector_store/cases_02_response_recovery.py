# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


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


def test_openai_response_with_vector_store_returns_non_json_for_shared_recovery(
    fake_openai,
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

    result = svc.openai_respond_with_vector_store(req, _ctx())

    assert result.text == "not-json"
    assert result.parsed_json is None


def test_openai_response_with_vector_store_returns_json_arrays_for_shared_recovery(
    fake_openai,
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

    result = svc.openai_respond_with_vector_store(req, _ctx())

    assert result.text == json.dumps([{"result": "ok"}])
    assert result.parsed_json is None


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


def test_gpt6_responses_send_reasoning_without_sampling(tmp_path, fake_openai) -> None:
    fake_openai.queue_response_text('{"ok":true}')
    request = OpenAIResponseRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        vector_store_id="vs_123",
        model="gpt-6-luna",
        temperature=0.4,
        reasoning_effort="high",
        api_key="key",
        seed=42,
        cost_ledger_path=str(tmp_path / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        model_pricing={},
    )

    svc.openai_respond_with_vector_store(request, _ctx())

    call = fake_openai.calls["responses.create"][0]
    assert call["reasoning"] == {"effort": "high"}
    assert "temperature" not in call
    assert "seed" not in call


def test_gpt6_image_responses_send_reasoning_without_sampling(
    tmp_path, fake_openai
) -> None:
    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake-image")
    fake_openai.queue_response_text('{"ok":true}')
    request = OpenAIJSONImagePromptRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        model="gpt-6-luna",
        temperature=0.4,
        reasoning_effort="low",
        api_key="key",
        image_paths=[str(image_path)],
        seed=42,
        cost_ledger_path=str(tmp_path / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        model_pricing={},
    )

    svc.openai_chat_json_with_images(request, _ctx())

    call = fake_openai.calls["responses.create"][0]
    assert call["reasoning"] == {"effort": "low"}
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
