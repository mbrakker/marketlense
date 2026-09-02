from __future__ import annotations

import pytest

from src.contracts.validation import ValidationRequest
from src.generators.validation.grounding import grounding_payload, run_grounding_check
from tests._test_validation_generator._shared import (
    FakeOpenAI,
    FakePromptClient,
    _ctx,
    _report,
    _settings,
)


def _artifacts_for(section: str, text: str) -> dict:
    artifacts = {
        "insights_final": [
            {
                "id": "insight-1",
                "text": "Wallet adoption rose among surveyed consumers.",
                "evidence_id": "evidence-1",
                "evidence": "Wallet adoption rose among surveyed consumers.",
                "so_what": "This makes wallet coverage a more important journey consideration.",
                "now_what": "Brands should reconsider treating wallet coverage as experimental.",
            }
        ],
        "expert_comment": "The shift makes wallet coverage a more important journey consideration.",
        "linkedin_post": "Brands should reconsider treating wallet coverage as experimental.",
    }
    if section == "expert_comment":
        artifacts["expert_comment"] = text
    elif section == "linkedin_post":
        artifacts["linkedin_post"] = text
    elif section.endswith(".so_what"):
        artifacts["insights_final"][0]["so_what"] = text
    elif section.endswith(".now_what"):
        artifacts["insights_final"][0]["now_what"] = text
    return artifacts


def _issues(tmp_path, *, section: str, entry: dict | None = None):
    text = (
        entry["text"]
        if entry is not None
        else "Brands should reconsider treating wallet coverage as experimental."
    )
    return run_grounding_check(
        request=ValidationRequest(
            schema_version="1.0",
            report_id="editorial-grounding",
            report=_report(),
            artifacts=_artifacts_for(section, text),
            evidence_packs={},
            vector_store_id=None,
        ),
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=["Wallet adoption rose among surveyed consumers."],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            grounding_payload={"unsupported": [entry] if entry else [], "checks": []}
        ),
        ctx=_ctx(),
    )


def test_grounding_payload_retains_final_insight_implications() -> None:
    payload = grounding_payload(
        ValidationRequest(
            schema_version="1.0",
            report_id="editorial-grounding",
            report=_report(),
            artifacts=_artifacts_for("expert_comment", "Expert comment."),
            evidence_packs={},
            vector_store_id=None,
        ),
        _artifacts_for("expert_comment", "Expert comment."),
    )

    assert payload["insights_final"][0]["so_what"]
    assert payload["insights_final"][0]["now_what"]


@pytest.mark.parametrize(
    "section",
    (
        "expert_comment",
        "linkedin_post",
        "insights_final[0].so_what",
        "insights_final[0].now_what",
    ),
)
def test_grounding_accepts_evidence_traceable_editorial_interpretation(
    tmp_path, section: str
) -> None:
    assert _issues(tmp_path, section=section) == []


@pytest.mark.parametrize(
    ("section", "classification", "violation_type", "text"),
    (
        (
            "expert_comment",
            "analyst_interpretation",
            "unsupported_causal_outcome",
            "Wallet coverage will cause conversion to rise.",
        ),
        (
            "linkedin_post",
            "prescriptive_recommendation",
            "unsupported_operational_or_financial_benefit",
            "Prioritising wallets will reduce CAC by 20%.",
        ),
        (
            "insights_final[0].so_what",
            "analyst_interpretation",
            "unsupported_certainty",
            "Wallet coverage will certainly determine conversion.",
        ),
        (
            "insights_final[0].now_what",
            "prescriptive_recommendation",
            "report_directive_misattribution",
            "The report recommends prioritising wallet coverage.",
        ),
    ),
)
def test_grounding_blocks_unsupported_editorial_outcomes(
    tmp_path, section: str, classification: str, violation_type: str, text: str
) -> None:
    issues = _issues(
        tmp_path,
        section=section,
        entry={
            "section": section,
            "text": text,
            "classification": classification,
            "violation_type": violation_type,
            "reason": "The sentence adds an unsupported material outcome.",
        },
    )

    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert f"[{classification}|{violation_type}]" in issues[0].message


def test_grounding_keeps_factual_sentence_in_creative_paragraph_strict(tmp_path) -> None:
    issues = _issues(
        tmp_path,
        section="linkedin_post",
        entry={
            "section": "linkedin_post",
            "text": "The market grew by 40% last year.",
            "classification": "factual_claim",
            "entailment_outcome": "not_established",
            "reason": "The retained evidence does not establish this growth rate.",
        },
    )

    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "[factual_claim|unsupported_factual_claim]" in issues[0].message


@pytest.mark.parametrize(
    "entry",
    (
        {
            "section": "expert_comment",
            "text": "The market grew by 40% last year.",
            "reason": "The retained evidence does not support this sentence.",
        },
        {
            "section": "linkedin_post",
            "text": "This will certainly reduce acquisition costs.",
            "classification": "analyst_interpretation",
            "reason": "The retained evidence does not support this sentence.",
        },
    ),
)
def test_grounding_fails_closed_for_underspecified_editorial_rejections(
    tmp_path, entry: dict
) -> None:
    issues = _issues(tmp_path, section=entry["section"], entry=entry)

    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "unsupported_factual_claim" in issues[0].message
