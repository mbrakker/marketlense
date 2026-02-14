import json
from types import SimpleNamespace

from src.contracts.report_assets import RankRequest
from src.contracts.run_context import RunContext
from src.services import rank_service


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


def _patch_openai(monkeypatch, payload: object) -> None:
    response = SimpleNamespace(
        id="req_1",
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8, total_tokens=20),
    )

    class _FakeCompletions:
        def create(self, **kwargs):
            return response

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr(rank_service, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(rank_service, "append_cost_entry", lambda req, ctx: None)
    monkeypatch.setattr(rank_service, "rollup_daily", lambda req, ctx: None)


def test_rank_candidates_parses_extended_schema(monkeypatch, tmp_path):
    _patch_openai(
        monkeypatch,
        {
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
        },
    )
    resp = rank_service.rank_candidates(_request(tmp_path), _ctx())

    assert len(resp.results) == 1
    row = resp.results[0]
    assert row.id == "c1"
    assert row.score == 92
    assert row.quality_score == 90
    assert row.insight_score == 88
    assert row.data_score == 86
    assert row.keep is True
    assert row.reject_reason == ""


def test_rank_candidates_legacy_score_only_defaults_subscores(monkeypatch, tmp_path):
    _patch_openai(
        monkeypatch,
        [
            {
                "id": "legacy_1",
                "type": "table",
                "score": 83,
            }
        ],
    )
    resp = rank_service.rank_candidates(_request(tmp_path), _ctx())

    assert len(resp.results) == 1
    row = resp.results[0]
    assert row.id == "legacy_1"
    assert row.score == 83
    assert row.quality_score == 83
    assert row.insight_score == 83
    assert row.data_score == 83
    assert row.keep is True
