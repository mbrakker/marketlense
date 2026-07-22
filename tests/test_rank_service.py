import json

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.report_assets import RankRequest
from src.contracts.run_budget import RunBudget
from src.contracts.run_context import RunContext
from src.services import rank_service
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _request(tmp_path, *, user_prompt: str = "[]") -> RankRequest:
    return RankRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt=user_prompt,
        prompt_system_sha256="sys",
        prompt_user_sha256="usr",
        model="gpt-5-mini",
        temperature=0.0,
        api_key="key",
        seed=7,
        candidate_count=1,
        timeout_seconds=5.0,
        cost_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
        cost_daily_path=str(tmp_path / "cost-daily.json"),
        model_pricing={},
    )


def _openai_chat_json_response(*, text: str, parsed_json: dict | None, captured=None):
    def _fake_openai_chat_json(req, ctx):
        if captured is not None:
            captured.append((req, ctx))
        return OpenAIResponseResult(
            schema_version="1.0",
            text=text,
            parsed_json=parsed_json,
            input_tokens=12,
            output_tokens=8,
            tool_calls=0,
            model=req.model,
            total_tokens=20,
            request_id="req_1",
        )

    return _fake_openai_chat_json


def test_rank_candidates_parses_extended_schema(tmp_path):
    payload = {
        "results": [
            {
                "id": "c1",
                "type": "chart",
                "score": 92,
                "quality_score": 90,
                "insight_score": 88,
                "data_score": 86,
                "keep": True,
                "reject_reason": "",
            }
        ]
    }
    captured = []
    fake_openai = _openai_chat_json_response(
        text=json.dumps(payload),
        parsed_json=payload,
        captured=captured,
    )
    budget = RunBudget(
        schema_version="1.0",
        run_id="r",
        publisher_name="",
        usage_db_path=str(tmp_path / "isolated-usage.sqlite"),
    )
    resp = rank_service.rank_candidates(
        RankRequest(**{**_request(tmp_path).__dict__, "run_budget": budget}),
        _ctx(),
        openai_chat_json_client=fake_openai,
    )

    assert len(resp.results) == 1
    row = resp.results[0]
    assert row.id == "c1"
    assert row.score == 92
    assert row.quality_score == 90
    assert row.insight_score == 88
    assert row.data_score == 86
    assert row.keep is True
    assert row.reject_reason == ""
    assert captured[0][0].run_budget == budget
    assert captured[0][0].usage_db_path == budget.usage_db_path


def test_rank_candidates_legacy_score_only_defaults_subscores(tmp_path):
    payload = [
        {
            "id": "legacy_1",
            "type": "table",
            "score": 83,
        }
    ]
    fake_openai = _openai_chat_json_response(
        text=json.dumps(payload),
        parsed_json=None,
    )
    resp = rank_service.rank_candidates(
        _request(tmp_path), _ctx(), openai_chat_json_client=fake_openai
    )

    assert len(resp.results) == 1
    row = resp.results[0]
    assert row.id == "legacy_1"
    assert row.score == 83
    assert row.quality_score == 83
    assert row.insight_score == 83
    assert row.data_score == 83
    assert row.keep is True


def test_rank_candidates_maps_openai_errors(tmp_path):
    def _raise_openai_error(req, ctx):
        raise AppError(
            code="openai_chat_failed",
            message="request failed",
            retryable=True,
            severity="warning",
        )

    with pytest.raises(AppError) as exc:
        rank_service.rank_candidates(
            _request(tmp_path),
            _ctx(),
            openai_chat_json_client=_raise_openai_error,
        )

    assert exc.value.code == "rank_request_failed"
    assert exc.value.retryable is True
    assert exc.value.severity == "warning"
