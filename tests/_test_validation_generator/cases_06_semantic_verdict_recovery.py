# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.generators.validation.semantic import run_semantic_validation

from ._shared import *  # noqa: F401,F403


def test_semantic_verdict_coverage_failure_enters_bounded_recovery(tmp_path) -> None:
    class SequencedSemanticOpenAI(FakeOpenAI):
        def __init__(self, *semantic_payloads):
            super().__init__(grounding_payload={"unsupported": []})
            self.semantic_payloads = list(semantic_payloads)

        def openai_chat_json(self, req, ctx):
            task_id = str(getattr(ctx, "task_id", ""))
            if task_id.endswith(":semantic"):
                payload = self.semantic_payloads.pop(0)
                with self._lock:
                    self.requests.append(("chat", req.model, task_id))
                return OpenAIResponseResult(
                    schema_version="1.0",
                    text=json.dumps(payload),
                    parsed_json=payload,
                    input_tokens=0,
                    output_tokens=0,
                    tool_calls=0,
                    model=req.model,
                )
            return super().openai_chat_json(req, ctx)

    materialized = []
    client = SequencedSemanticOpenAI(
        {
            "metrics": [
                {
                    "id": "metric-1",
                    "supported": True,
                    "confidence": 0.9,
                    "reason": "Supported by evidence",
                }
            ],
            "quotes": [],
        },
        {
            "metrics": [
                {
                    "id": "metric-1",
                    "supported": True,
                    "confidence": 0.9,
                    "reason": "Supported by evidence",
                }
            ],
            "quotes": [
                {
                    "id": "quote-1",
                    "supported": True,
                    "confidence": 0.9,
                    "reason": "Supported by evidence",
                }
            ],
        },
    )

    outcome = run_semantic_validation(
        insights=[
            {"id": "metric-1", "text": "Revenue grew", "metric": {"value": "10%"}}
        ],
        quotes=[{"id": "quote-1", "text": "We grew", "speaker": "CEO"}],
        evidence_texts=["Revenue grew by 10%. CEO: We grew."],
        settings=_settings(tmp_path),
        prompt_client=FakePromptClient(),
        openai_client=client,
        ctx=_ctx(),
        report_id="semantic-coverage-recovery",
        source_id="source:semantic-coverage-recovery",
        prompt_family_reuse_reader=lambda _request, _ctx: SimpleNamespace(
            reusable=False, reason="no_retained_result"
        ),
        prompt_family_materializer=lambda request, _ctx: materialized.append(request),
    )

    assert outcome.issues == []
    assert set(outcome.metric_support) == {"metric-1"}
    assert set(outcome.quote_support) == {"quote-1"}
    assert len(client.requests) == 2
    assert materialized == []
