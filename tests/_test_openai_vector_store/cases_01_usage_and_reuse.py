# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


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


def test_openai_response_file_search_calls_reach_cost_and_usage_attribution(
    tmp_path, fake_openai
) -> None:
    fake_openai.add(
        "responses.create",
        SimpleNamespace(
            output_text='{"result":"ok"}',
            output=[
                {"type": "file_search_call", "id": "fs_1"},
                {"type": "file_search_call", "id": "fs_2"},
                {"type": "message", "content": []},
            ],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15),
            id="resp_file_search_accounting",
        ),
    )
    request = OpenAIResponseRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        vector_store_id="vs_report_123",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
        cost_ledger_path=str(tmp_path / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        usage_db_path=str(tmp_path / "usage.sqlite"),
        model_pricing={
            "gpt-4.1-mini": {
                "input_tokens_per_1k_usd": 0.0,
                "output_tokens_per_1k_usd": 0.0,
                "tool_call_usd": 0.25,
            }
        },
        report_id="report-123",
        workflow="report_analysis",
        stage="scope",
        artifact_family="scope",
        prompt_namespace="report_vs/scope",
        repair_attempt=1,
    )

    result = svc.openai_respond_with_vector_store(request, _ctx())

    assert result.tool_calls == 2
    with sqlite3.connect(request.usage_db_path) as connection:
        row = connection.execute(
            "SELECT report_id, workflow, stage, artifact_family, prompt_namespace, "
            "repair_attempt, tool_calls, estimated_cost_usd, metadata_json "
            "FROM llm_usage_events"
        ).fetchone()
    assert row is not None
    assert row[:8] == (
        "report-123",
        "report_analysis",
        "scope",
        "scope",
        "report_vs/scope",
        1,
        2,
        0.5,
    )
    metadata = json.loads(row[8])
    assert metadata["file_search_call_count"] == 2
    assert metadata["vector_store_id"] == "vs_report_123"


def test_cached_file_search_response_does_not_issue_another_provider_search(
    tmp_path, fake_openai
) -> None:
    fake_openai.add(
        "responses.create",
        SimpleNamespace(
            output_text='{"result":"cached"}',
            output=[{"type": "file_search_call", "id": "fs_cached"}],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15),
            id="resp_cached_file_search",
        ),
    )
    request = OpenAIResponseRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        vector_store_id="vs_cached",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
        response_cache_enabled=True,
        response_cache_dir=str(tmp_path / "cache"),
    )

    first = svc.openai_respond_with_vector_store(request, _ctx())
    second = svc.openai_respond_with_vector_store(request, _ctx())

    assert first.tool_calls == 1
    assert second.tool_calls == 1
    assert len(fake_openai.calls["responses.create"]) == 1


def test_doc_map_search_results_are_cached_with_the_vector_content_identity(
    tmp_path, fake_openai
) -> None:
    fake_openai.add(
        "responses.create",
        SimpleNamespace(
            output_text='{"title":"Report"}',
            output=[
                SimpleNamespace(
                    type="file_search_call",
                    queries=["Find the report methodology"],
                    results=[
                        SimpleNamespace(
                            file_id="file_report",
                            filename="report.pdf",
                            score=0.91,
                            content=[
                                SimpleNamespace(
                                    type="text",
                                    text="The study surveyed 1,200 consumers.",
                                )
                            ],
                        ),
                        SimpleNamespace(
                            file_id="file_report",
                            filename="report.pdf",
                            score=0.84,
                            text="Fieldwork took place in May 2025.",
                        ),
                    ],
                ),
                {"type": "message", "content": []},
            ],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15),
            id="resp_doc_map_results",
        ),
        SimpleNamespace(
            output_text='{"title":"Updated report"}',
            output=[
                SimpleNamespace(
                    type="file_search_call",
                    queries=["Find updated report methodology"],
                    results=[
                        SimpleNamespace(
                            file_id="file_report_v2",
                            filename="report-v2.pdf",
                            score=0.95,
                            content=[
                                SimpleNamespace(
                                    type="text",
                                    text="The updated study surveyed 1,500 consumers.",
                                )
                            ],
                        )
                    ],
                )
            ],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15),
            id="resp_doc_map_results_v2",
        ),
    )
    cache_dir = tmp_path / "cache"
    request_values = {
        "schema_version": "1.0",
        "system_prompt": "map the report",
        "user_prompt": "report content",
        "vector_store_id": "vs_report",
        "vector_store_content_hash": "sha256:report-content-v1",
        "model": "gpt-4.1-mini",
        "temperature": 0.1,
        "api_key": "key",
        "include_file_search_results": True,
        "response_cache_enabled": True,
        "response_cache_dir": str(cache_dir),
    }

    first = svc.openai_respond_with_vector_store(
        OpenAIResponseRequest(**request_values), _ctx()
    )
    # Model a workflow restart: reconstruct the request and context while using
    # the same report/vector-store identity and persistent semantic cache.
    second = svc.openai_respond_with_vector_store(
        OpenAIResponseRequest(**dict(request_values)), _ctx()
    )

    assert fake_openai.calls["responses.create"][0]["include"] == [
        "file_search_call.results"
    ]
    assert len(fake_openai.calls["responses.create"]) == 1
    assert len(first.file_search_results) == 2
    assert second.file_search_results == first.file_search_results
    assert second.file_search_results[0].queries == ["Find the report methodology"]
    assert second.file_search_results[0].filename == "report.pdf"
    assert second.file_search_results[1].text == "Fieldwork took place in May 2025."

    changed_source_request = OpenAIResponseRequest(
        **{
            **request_values,
            "vector_store_content_hash": "sha256:report-content-v2",
        }
    )
    changed_source = svc.openai_respond_with_vector_store(
        changed_source_request, _ctx()
    )

    assert len(fake_openai.calls["responses.create"]) == 2
    assert changed_source.file_search_results[0].filename == "report-v2.pdf"
    assert "1,500 consumers" in changed_source.file_search_results[0].text
    assert second.file_search_results[0].text == ("The study surveyed 1,200 consumers.")
