# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_generic_core_signal_warns_when_a_specific_retained_insight_exists(tmp_path):
    generic = "Market growth remains a central focus for brands."
    specific = "Gaming installs rose while sessions fell for casino apps in 2025."
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="quality-generic-core-with-specific-alternative",
            report=_report(),
            artifacts={
                "summary": {"claim_evidence_map": []},
                "insights_final": [
                    {
                        "id": "generic-lead",
                        "text": generic,
                        "evidence_id": "broad-topic",
                        "evidence": "The report discusses market growth and brand strategy.",
                    },
                    {
                        "id": "gaming-outcome",
                        "text": specific,
                        "evidence_id": "gaming-finding",
                        "evidence": specific,
                    },
                ],
            },
            evidence_packs={
                "findings": {
                    "findings": [
                        {
                            "id": "gaming-finding",
                            "text": specific,
                            "evidence": specific,
                        }
                    ]
                }
            },
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        _settings(tmp_path),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=None,
        analysis_store=FakeAnalysisStore(),
    )

    warning = next(
        issue
        for issue in result.issues
        if issue.rule_id == "artifact_quality"
        and issue.affected_section == "insights_final[0].text"
    )
    assert warning.severity == "warning"
    assert warning.entity_id == "insight:generic-lead:text"
    assert warning.evidence_ids == ["gaming-finding"]


@pytest.mark.parametrize(
    "lead",
    [
        "Activate forecasts $302B in consumer Internet and media revenue growth "
        "from 2017E to 2021E.",
        "Publishers lose search referrals when AI answer engines satisfy user "
        "queries directly.",
    ],
)
def test_specific_quantitative_and_qualitative_core_signals_are_not_flagged(
    tmp_path, lead
):
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="quality-specific-core-signal",
            report=_report(),
            artifacts={
                "summary": {"claim_evidence_map": []},
                "insights_final": [
                    {
                        "id": "specific-lead",
                        "text": lead,
                        "evidence_id": "specific-finding",
                        "evidence": lead,
                    }
                ],
            },
            evidence_packs={},
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        _settings(tmp_path),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=None,
        analysis_store=FakeAnalysisStore(),
    )

    assert not any(
        issue.rule_id == "artifact_quality"
        and issue.affected_section == "insights_final[0].text"
        for issue in result.issues
    )


def test_generic_core_signal_is_not_flagged_without_a_specific_retained_finding(
    tmp_path,
):
    lead = "Market growth remains a central focus for brands."
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="quality-generic-core-no-stronger-finding",
            report=_report(),
            artifacts={
                "summary": {"claim_evidence_map": []},
                "insights_final": [
                    {
                        "id": "generic-lead",
                        "text": lead,
                        "evidence_id": "broad-topic",
                        "evidence": "The report discusses market growth and brand strategy.",
                    }
                ],
            },
            evidence_packs={},
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        _settings(tmp_path),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=None,
        analysis_store=FakeAnalysisStore(),
    )

    assert not any(
        issue.rule_id == "artifact_quality"
        and issue.affected_section == "insights_final[0].text"
        for issue in result.issues
    )
