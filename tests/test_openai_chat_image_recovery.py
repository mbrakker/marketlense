from __future__ import annotations

from types import SimpleNamespace

from src.contracts.openai import OpenAIJSONImagePromptRequest
from src.contracts.run_context import RunContext
from src.services import llm_service as svc


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_openai_chat_json_with_images_recovers_first_json_object(
    external_boundary_mocks_only, tmp_path
) -> None:
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"page")

    captured_kwargs = {}

    class _Responses:
        def create(self, **kwargs):
            captured_kwargs.update(kwargs)
            return SimpleNamespace(
                id="resp_concatenated_json",
                output_text='{"outcome":"verified"}{"duplicate":true}',
                usage=SimpleNamespace(input_tokens=3, output_tokens=2, total_tokens=5),
            )

    class _Client:
        def __init__(self, **_kwargs):
            self.responses = _Responses()

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", _Client)
    request = OpenAIJSONImagePromptRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
        image_paths=[str(image_path)],
        cost_ledger_path=str(tmp_path / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        usage_db_path=str(tmp_path / "usage.sqlite"),
    )

    result = svc.openai_chat_json_with_images(request, _ctx())

    assert result.parsed_json == {"outcome": "verified"}
    assert captured_kwargs["text"] == {"format": {"type": "json_object"}}


def test_openai_chat_json_with_images_rejects_provider_incomplete_response(
    external_boundary_mocks_only, tmp_path
) -> None:
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"page")

    class _Responses:
        def create(self, **_kwargs):
            return SimpleNamespace(
                id="resp_incomplete_json",
                status="incomplete",
                incomplete_details=SimpleNamespace(reason="max_output_tokens"),
                output_text='{"outcome":"verified"}',
                usage=SimpleNamespace(input_tokens=3, output_tokens=2, total_tokens=5),
            )

    class _Client:
        def __init__(self, **_kwargs):
            self.responses = _Responses()

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", _Client)
    request = OpenAIJSONImagePromptRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
        image_paths=[str(image_path)],
        cost_ledger_path=str(tmp_path / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        usage_db_path=str(tmp_path / "usage.sqlite"),
    )

    result = svc.openai_chat_json_with_images(request, _ctx())

    assert result.parsed_json is None
