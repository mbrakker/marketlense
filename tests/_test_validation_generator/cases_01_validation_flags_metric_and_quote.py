# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_validation_flags_metric_and_quote_mismatches(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Insight text",
                "evidence_id": "e1",
                "evidence": "Growth was 5%",
                "metric": {"value": "10", "unit": "%", "timeframe": "2024"},
            },
        ],
        "quotes_final": [{"text": "Outside quote", "speaker": "CEO", "citation": ""}],
    }
    fake_openai = FakeOpenAI({"unsupported": []})
    analysis_store = FakeAnalysisStore()
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r1",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=analysis_store,
    )
    assert result.status == "fail"
    assert result.severity == "error"
    assert any("Metric value" in issue.message for issue in result.issues)
    assert any("Quote not verbatim" in issue.message for issue in result.issues)
    assert analysis_store.stored and analysis_store.stored[0][2] == "validation"

def test_number_validation_ignores_soft_planning_timeframes():
    artifacts = {
        "linkedin_post": (
            "Actions for the next 12 months: integrate verification into "
            "product and marketing release cycles."
        )
    }

    issues = validate_new_numbers(
        artifacts=artifacts,
        insights=[],
        report=_report(),
        evidence_texts=[],
        evidence_windows=[],
    )

    assert not any(issue.rule_id == "numbers" for issue in issues)

def test_validation_accepts_paraphrased_metrics_and_quotes(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Revenue grew year over year",
                "evidence_id": "e1",
                "evidence": "The company reported ten percent year-over-year revenue growth.",
                "metric": {"value": "10%", "unit": "%", "timeframe": "2024"},
            },
        ],
        "quotes_final": [
            {
                "id": "q1",
                "text": "Revenue grew ten percent YoY",
                "speaker": "CEO",
                "citation": "The CEO noted a year-over-year increase of ten pct.",
                "is_paraphrase": True,
            },
        ],
    }
    semantic_payload = {
        "metrics": [
            {
                "id": "i1",
                "supported": True,
                "confidence": 0.82,
                "reason": "Paraphrase matches evidence",
            }
        ],
        "quotes": [
            {
                "id": "q1",
                "supported": True,
                "confidence": 0.81,
                "reason": "Meaning preserved",
            }
        ],
    }
    grounding_payload = {"unsupported": []}
    fake_openai = FakeOpenAI(
        semantic_payload=semantic_payload, grounding_payload=grounding_payload
    )
    analysis_store = FakeAnalysisStore()
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r1",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=analysis_store,
    )
    assert result.status == "pass"
    assert result.severity in {"info", "pass"}
    assert all(issue.severity != "error" for issue in result.issues)
    assert any("semantically supported" in issue.message for issue in result.issues)
    assert analysis_store.stored and analysis_store.stored[0][2] == "validation"

def test_validation_detects_new_numbers_and_grounding(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Insight 1",
                "evidence_id": "e1",
                "evidence": "Revenue up 5%",
                "metric": {"value": "5", "unit": "%", "timeframe": "2024"},
            }
        ],
        "expert_comment": "We expect revenue to reach 99 soon.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={
            "unsupported": [
                {
                    "section": "expert_comment",
                    "text": "We expect",
                    "reason": "No evidence",
                }
            ]
        },
    )
    analysis_store = FakeAnalysisStore()
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r2",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=analysis_store,
    )
    assert result.status == "fail"
    assert any(issue.affected_section == "expert_comment" for issue in result.issues)
    assert any("No evidence" in issue.message for issue in result.issues)
    assert any("Number" in issue.message for issue in result.issues)

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
            evidence_packs={},
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
            evidence_packs={},
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

def test_validation_number_check_ignores_units_and_matches_numeric_value(tmp_path):
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
    assert result.status == "pass"
    assert not any("Number" in issue.message for issue in result.issues)

def test_grounding_unsupported_number_is_downgraded_when_numeric_value_matches(
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
    assert result.status == "pass"
    assert any(
        "normalized_quantity_supported" in issue.message for issue in result.issues
    )
    assert not any(issue.severity == "error" for issue in result.issues)

def test_validation_warns_on_data_gap(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Insight text",
                "evidence_id": "e1",
                "evidence": "",
                "metric": {"value": "10", "unit": "%", "timeframe": "2024"},
            }
        ],
        "source_status": _low_text_status(),
    }
    fake_openai = FakeOpenAI({"unsupported": []})
    analysis_store = FakeAnalysisStore()
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="low_text_report",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=analysis_store,
    )
    assert result.status == "pass"
    assert result.severity == "warning"
    assert any(issue.severity == "warning" for issue in result.issues)

def test_validation_issue_order_preserved_with_parallel_checks(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Insight text",
                "evidence_id": "e1",
                "evidence": "Growth was 5%",
                "metric": {"value": "10", "unit": "%", "timeframe": "2024"},
            },
        ],
        "quotes_final": [
            {"id": "q1", "text": "Outside quote", "speaker": "CEO", "citation": ""}
        ],
        "expert_comment": "We expect revenue to reach 99 soon.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={
            "metrics": [
                {
                    "id": "i1",
                    "supported": False,
                    "confidence": 0.9,
                    "reason": "Not grounded",
                }
            ],
            "quotes": [
                {
                    "id": "q1",
                    "supported": False,
                    "confidence": 0.9,
                    "reason": "Not grounded",
                }
            ],
        },
        grounding_payload={
            "unsupported": [
                {
                    "section": "expert_comment",
                    "text": "We expect",
                    "reason": "No evidence",
                }
            ]
        },
    )
    analysis_store = FakeAnalysisStore()
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-order",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=analysis_store,
    )

    messages = [issue.message for issue in result.issues]
    idx_semantic_metric = next(
        i
        for i, message in enumerate(messages)
        if "Semantic check: metric for i1 not supported" in message
    )
    idx_metric_exact = next(
        i
        for i, message in enumerate(messages)
        if "Metric value '10' not found in evidence" in message
    )
    idx_quote_exact = next(
        i
        for i, message in enumerate(messages)
        if "Quote not verbatim in evidence" in message
    )
    idx_number = next(
        i
        for i, message in enumerate(messages)
        if "Number 99.0 not present in report or evidence" in message
    )
    idx_grounding = next(
        i for i, message in enumerate(messages) if "No evidence: We expect" in message
    )

    assert (
        idx_semantic_metric
        < idx_metric_exact
        < idx_quote_exact
        < idx_number
        < idx_grounding
    )
    assert len([req for req in fake_openai.requests if req[0] == "chat"]) == 2

def test_validation_grounding_uses_chat_path_when_flag_disabled(tmp_path):
    settings = _settings(tmp_path, validation_grounding_use_vector_store=False)
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-grounding-chat",
            report=_report(),
            artifacts={"insights_final": []},
            evidence_packs={},
            vector_store_id="vs_1",
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    grounding_calls = [
        req for req in fake_openai.requests if req[2].endswith(":grounding")
    ]
    assert grounding_calls
    assert grounding_calls[0][0] == "chat"

def test_validation_grounding_uses_vector_path_when_flag_enabled(tmp_path):
    settings = _settings(tmp_path, validation_grounding_use_vector_store=True)
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-grounding-vector",
            report=_report(),
            artifacts={"insights_final": []},
            evidence_packs={},
            vector_store_id="vs_1",
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    grounding_calls = [
        req for req in fake_openai.requests if req[2].endswith(":grounding")
    ]
    assert grounding_calls
    assert grounding_calls[0][0] == "vector"

def test_validation_cache_isolated_by_grounding_retrieval_mode(tmp_path):
    artifacts = {"insights_final": []}
    request = ValidationRequest(
        schema_version="1.0",
        report_id="r-cache-mode",
        report=_report(),
        artifacts=artifacts,
        evidence_packs={},
        vector_store_id="vs_1",
    )
    chat_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    validate_report(
        request,
        _settings(tmp_path, validation_grounding_use_vector_store=False),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=chat_openai,
        md5="md5-cache-mode",
        report_name="cache-mode-report",
    )
    chat_grounding_calls = [
        req for req in chat_openai.requests if req[2].endswith(":grounding")
    ]
    assert chat_grounding_calls
    assert chat_grounding_calls[0][0] == "chat"

    vector_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    validate_report(
        request,
        _settings(tmp_path, validation_grounding_use_vector_store=True),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=vector_openai,
        md5="md5-cache-mode",
        report_name="cache-mode-report",
    )
    vector_grounding_calls = [
        req for req in vector_openai.requests if req[2].endswith(":grounding")
    ]
    assert vector_grounding_calls
    assert vector_grounding_calls[0][0] == "vector"

__all__ = [
    "test_validation_flags_metric_and_quote_mismatches",
    "test_number_validation_ignores_soft_planning_timeframes",
    "test_validation_accepts_paraphrased_metrics_and_quotes",
    "test_validation_detects_new_numbers_and_grounding",
    "test_commentary_numbers_allowed_when_in_report_or_evidence",
    "test_validation_allows_interpretation_and_recommendation_in_allowed_sections",
    "test_validation_fails_on_report_directive_misattribution",
    "test_validation_number_matching_normalizes_percent_and_billions",
    "test_validation_number_check_ignores_units_and_matches_numeric_value",
    "test_grounding_unsupported_number_is_downgraded_when_numeric_value_matches",
    "test_validation_warns_on_data_gap",
    "test_validation_issue_order_preserved_with_parallel_checks",
    "test_validation_grounding_uses_chat_path_when_flag_disabled",
    "test_validation_grounding_uses_vector_path_when_flag_enabled",
    "test_validation_cache_isolated_by_grounding_retrieval_mode",
]
