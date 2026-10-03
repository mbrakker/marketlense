# ruff: noqa: F401,F403,F405
from __future__ import annotations
from ._split_support_cases_01_validation_flags_metric_and_quote import *  # noqa: F401,F403


def test_commentary_numbers_allowed_when_in_report_or_evidence(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "summary": {
            "tldr": "TLDR",
            "executive_summary": "Exec 42%",
            "claim_evidence_map": [],
        },
        "insights_final": [],
        "quotes_final": [
            {
                "text": "Revenue grew 42% year over year",
                "speaker": "CEO",
                "citation": "Revenue grew 42% year over year",
                "evidence_id": "f1",
            }
        ],
        "expert_comment": "We expect revenue to stay around 42% growth.",
        "linkedin_post": "Analysts noted 42% expansion.",
    }
    evidence_packs = {
        "findings": {
            "findings": [{"id": "f1", "evidence": "Revenue grew 42% year over year"}]
        }
    }
    _set_test_soft_copy_provenance(
        artifacts,
        {
            "summary": ("factual", ["f1"]),
            "expert_comment": ("factual", ["f1"]),
            "linkedin_post": ("factual", ["f1"]),
        },
    )
    evidence_packs = {
        "pack": {
            "findings": [{"id": "f1", "evidence": "Revenue grew 42% year over year"}]
        }
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    analysis_store = FakeAnalysisStore()
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r3",
            report=_report(),
            artifacts=artifacts,
            evidence_packs=evidence_packs,
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=analysis_store,
    )
    assert result.status == "pass"
    assert not any("Number" in issue.message for issue in result.issues)


def test_validation_allows_interpretation_and_recommendation_in_allowed_sections(
    tmp_path,
):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Evidence baseline 42%",
                "evidence_id": "e1",
                "evidence": "Baseline metric is 42%",
            }
        ],
        "quotes_final": [
            {
                "id": "q1",
                "text": "Baseline metric is 42%",
                "speaker": "Analyst",
                "citation": "Baseline metric is 42%",
                "evidence_id": "e1",
            }
        ],
        "expert_comment": "This likely indicates teams should prioritize cross-platform governance.",
        "linkedin_post": "Recommendation: focus on governance and phased rollout.",
    }
    _set_test_soft_copy_provenance(
        artifacts,
        {
            "expert_comment": ("recommendation", []),
            "linkedin_post": ("recommendation", []),
        },
    )
    evidence_packs = {
        "findings": {"findings": [{"id": "e1", "evidence": "Baseline metric is 42%"}]}
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={
            "unsupported": [
                {
                    "section": "expert_comment",
                    "text": "This likely indicates teams should prioritize cross-platform governance.",
                    "classification": "prescriptive_recommendation",
                    "violation_type": "non_fatal_interpretation",
                    "reason": "Recommendation extends beyond evidence details.",
                }
            ]
        },
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-interpret",
            report=_report(),
            artifacts=artifacts,
            evidence_packs=evidence_packs,
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    assert result.status == "pass"
    assert not any(issue.severity == "error" for issue in result.issues)
    assert any(issue.affected_section == "expert_comment" for issue in result.issues)


def test_validation_fails_on_report_directive_misattribution(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Evidence baseline 42%",
                "evidence_id": "e1",
                "evidence": "Baseline metric is 42%",
            }
        ],
        "expert_comment": "The report instructs brands to double investment immediately.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={
            "unsupported": [
                {
                    "section": "expert_comment",
                    "text": "The report instructs brands to double investment immediately.",
                    "reason": "No directive exists in source report.",
                }
            ]
        },
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-directive",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    assert result.status == "fail"
    assert any(
        "report_directive_misattribution" in issue.message for issue in result.issues
    )
    assert any(issue.severity == "error" for issue in result.issues)


def test_validation_number_matching_normalizes_percent_and_billions(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Context says revenue is more than $10B and conversion is 37%.",
                "evidence_id": "e1",
                "evidence": "Revenue is more than $10B while conversion reached 37%.",
            }
        ],
        "quotes_final": [
            {
                "id": "q1",
                "text": "Revenue is more than $10B while conversion reached 37%.",
                "speaker": "Analyst",
                "citation": "Revenue is more than $10B while conversion reached 37%.",
                "evidence_id": "e1",
            }
        ],
        "expert_comment": "Market size is >10 in annual USD billions and conversion reached 37.0.",
        "linkedin_post": "Leaders should plan around >10 USD bn scale and a 37.0 conversion baseline.",
    }
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "e1",
                    "evidence": "Revenue is more than $10B while conversion reached 37%.",
                }
            ]
        }
    }
    _set_test_soft_copy_provenance(
        artifacts,
        {
            "expert_comment": ("factual", ["e1"]),
            "linkedin_post": ("factual", ["e1"]),
        },
    )
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-numbers",
            report=_report(),
            artifacts=artifacts,
            evidence_packs=evidence_packs,
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    assert result.status == "pass"
    assert not any("Number" in issue.message for issue in result.issues)


def test_validation_number_check_rejects_changed_explicit_units(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Conversion reached 37%.",
                "evidence_id": "e1",
                "evidence": "Conversion reached 37%.",
            }
        ],
        "quotes_final": [
            {
                "id": "q1",
                "text": "Conversion reached 37%.",
                "speaker": "Analyst",
                "citation": "Conversion reached 37%.",
                "evidence_id": "e1",
            }
        ],
        "expert_comment": "The figure remains 37 USD in planning discussions.",
        "linkedin_post": "Leaders can use 37 EUR as a simple shorthand figure.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-units-ignore",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    assert result.status == "fail"
    assert any("Number" in issue.message for issue in result.issues)


def test_grounding_unsupported_number_with_unit_mismatch_is_blocking(
    tmp_path,
):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Adoption reached 37%.",
                "evidence_id": "e1",
                "evidence": "Adoption reached 37%.",
            }
        ],
        "quotes_final": [
            {
                "id": "q1",
                "text": "Adoption reached 37%.",
                "speaker": "Analyst",
                "citation": "Adoption reached 37%.",
                "evidence_id": "e1",
            }
        ],
        "expert_comment": "Adoption reached 37 USD by segment.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={
            "unsupported": [
                {
                    "section": "expert_comment",
                    "text": "Adoption reached 37 USD by segment.",
                    "classification": "factual_claim",
                    "violation_type": "unsupported_number",
                    "reason": "No matching metric in evidence.",
                }
            ]
        },
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-grounding-units-ignore",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    assert result.status == "fail"
    assert any("unsupported_number" in issue.message for issue in result.issues)
    assert any(issue.severity == "error" for issue in result.issues)
