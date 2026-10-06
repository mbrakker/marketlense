# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


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


def test_openai_vector_store_success_reconciles_one_actual_provider_call(
    fake_openai, tmp_path
) -> None:
    fake_openai.add("vector_stores.retrieve", {"status": "completed"})
    budget = RunBudget(
        schema_version="1.0",
        run_id="r",
        publisher_name="",
        usage_db_path=str(tmp_path / "vector-usage.sqlite"),
        max_calls=2,
    )

    response = svc.openai_vector_store_status(
        OpenAIVectorStoreStatusRequest(
            schema_version="1.0",
            api_key="key",
            vector_store_id="vs_123",
            run_budget=budget,
        ),
        _ctx(),
    )
    usage = read_run_budget_usage(
        RunBudgetUsageReadRequest(schema_version="1.0", budget=budget), _ctx()
    ).usage

    assert response.status == "completed"
    assert usage.calls == 1


def test_openai_vector_store_pre_provider_failure_reconciles_zero_actual_calls(
    assert_app_error, tmp_path
) -> None:
    budget = RunBudget(
        schema_version="1.0",
        run_id="r",
        publisher_name="",
        usage_db_path=str(tmp_path / "vector-usage.sqlite"),
        max_calls=2,
    )

    try:
        svc.openai_vector_store_status(
            OpenAIVectorStoreStatusRequest(
                schema_version="1.0",
                api_key="",
                vector_store_id="vs_123",
                run_budget=budget,
            ),
            _ctx(),
        )
    except Exception as err:
        assert_app_error(err, code="openai_missing_api_key", retryable=False)
    else:  # pragma: no cover
        raise AssertionError("expected AppError")

    usage = read_run_budget_usage(
        RunBudgetUsageReadRequest(schema_version="1.0", budget=budget), _ctx()
    ).usage

    assert usage.calls == 0


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
                SimpleNamespace(embedding=[0.1] * 1024),
                SimpleNamespace(embedding=[0.2] * 1024),
            ],
            model="text-embedding-3-large",
            usage=SimpleNamespace(prompt_tokens=9, total_tokens=9),
            id="emb_1",
        ),
    )
    caplog.set_level(logging.INFO, logger="market_lense.llm_service.openai")

    resp = svc.openai_create_embeddings(
        OpenAIEmbeddingRequest(
            schema_version="1.0",
            api_key="key",
            model="text-embedding-3-large",
            inputs=["first claim", "second claim"],
            dimensions=1024,
            timeout_seconds=8.0,
        ),
        _ctx(),
    )

    assert resp.embeddings == [[0.1] * 1024, [0.2] * 1024]
    assert resp.dimensions == 1024
    assert resp.model == "text-embedding-3-large"
    assert resp.request_id == "emb_1"
    assert resp.input_tokens == 9
    assert_no_defaulted_required_fields(resp)
    assert fake_openai.calls["embeddings.create"] == [
        {
            "model": "text-embedding-3-large",
            "input": ["first claim", "second claim"],
            "dimensions": 1024,
        }
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
