import pytest

from src.generators.artifact_generator import render_artifact_json_model
from src.services.schema_validator_service import validate_output_schema
from src.utils.errors import AppError
from tests._test_artifact_generator._shared import (
    FakeOpenAI,
    FakePromptClient,
    _ctx,
    _settings,
)


def _validate(payload):
    validate_output_schema(
        payload=payload,
        schema_name="editorial_coverage_challenge_output",
        root_key="",
        ctx=_ctx(),
    )


def test_challenge_schema_accepts_exact_bound_refutation():
    _validate(
        {
            "verdicts": [
                {
                    "gap_index": 0,
                    "verdict": "refuted",
                    "explanation": "The qualification is present.",
                    "supporting_insight_id": "insight-1",
                    "supporting_quote": "includes the stated population",
                }
            ]
        }
    )


@pytest.mark.parametrize("bad_value", ["maybe", "approved", ""])
def test_challenge_schema_rejects_unknown_verdict(bad_value):
    with pytest.raises(AppError):
        _validate(
            {
                "verdicts": [
                    {
                        "gap_index": 0,
                        "verdict": bad_value,
                        "explanation": "The qualification is present.",
                        "supporting_insight_id": "insight-1",
                        "supporting_quote": "includes the stated population",
                    }
                ]
            }
        )


def test_existing_artifact_renderer_accepts_challenge_contract(tmp_path):
    response = {
        "verdicts": [
            {
                "gap_index": 0,
                "verdict": "refuted",
                "explanation": "The qualification is present.",
                "supporting_insight_id": "insight-1",
                "supporting_quote": "includes the stated population",
            }
        ]
    }
    result = render_artifact_json_model(
        namespace="report_vs/artifacts/editorial_coverage_challenge",
        variables={},
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI([response]),
        prompt_client=FakePromptClient(),
        allow_vector_store=False,
        vector_store_id=None,
        response_contract_name="editorial_coverage_challenge_output",
    )
    assert result["verdicts"] == response["verdicts"]
