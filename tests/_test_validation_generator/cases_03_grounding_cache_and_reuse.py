# ruff: noqa: F401,F403,F405
from __future__ import annotations

from dataclasses import replace

from src.contracts.validation import ValidationIssue, ValidationReport
from src.generators.validation.cache import validation_report_from_payload
from src.generators.validation.semantic import run_semantic_validation
from src.generators.validation.shared import downgrade_issues_for_data_gap

from ._shared import *  # noqa: F401,F403


def test_validation_keeps_unsupported_number_and_quote_errors_with_data_gap(tmp_path):
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
    assert result.status == "fail"
    assert result.severity == "error"
    assert {issue.rule_id for issue in result.issues if issue.severity == "error"} == {
        "metrics",
        "quotes",
    }


def test_validation_allows_structured_retrieval_failure_under_data_gap_policy(
    tmp_path,
):
    settings = _settings(tmp_path, validation_data_gap_policy="warn")
    report = replace(
        _report(),
        insights=[],
        quote=Quote(text="", author=""),
        figure=Figure(title="", evidence=""),
        commentary="",
    )
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={
            "unsupported": [
                {
                    "section": "summary",
                    "text": "The market expanded.",
                    "violation_type": "evidence_retrieval_failure",
                    "reason": "retrieval failed; no relevant evidence was available",
                }
            ]
        },
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="low_text_retrieval_report",
            report=report,
            artifacts={"source_status": _low_text_status()},
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
    assert result.severity == "warning"
    retrieval = next(issue for issue in result.issues if issue.rule_id == "grounding")
    assert "evidence_retrieval_failure" in retrieval.message
    assert retrieval.violation_type == "evidence_retrieval_failure"
    assert retrieval.severity == "warning"


def test_structured_retrieval_failure_without_data_gap_remains_blocking(tmp_path):
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="retrieval_without_gap_report",
            report=replace(
                _report(),
                insights=[],
                quote=Quote(text="", author=""),
                figure=Figure(title="", evidence=""),
                commentary="",
            ),
            artifacts={},
            evidence_packs={},
            vector_store_id=None,
        ),
        _settings(tmp_path, validation_data_gap_policy="warn"),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            semantic_payload={"metrics": [], "quotes": []},
            grounding_payload={
                "unsupported": [
                    {
                        "section": "summary",
                        "text": "The market expanded.",
                        "violation_type": "evidence_retrieval_failure",
                        "reason": "source context could not be accessed",
                    }
                ]
            },
        ),
        analysis_store=FakeAnalysisStore(),
    )

    retrieval = next(issue for issue in result.issues if issue.rule_id == "grounding")
    assert result.status == "fail"
    assert retrieval.severity == "error"


def test_blocking_data_gap_policy_keeps_retrieval_failure_blocking(tmp_path):
    report = replace(
        _report(),
        insights=[],
        quote=Quote(text="", author=""),
        figure=Figure(title="", evidence=""),
        commentary="",
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="retrieval_block_policy_report",
            report=report,
            artifacts={"source_status": _low_text_status()},
            evidence_packs={},
            vector_store_id=None,
        ),
        _settings(tmp_path, validation_data_gap_policy="block"),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            semantic_payload={"metrics": [], "quotes": []},
            grounding_payload={
                "unsupported": [
                    {
                        "section": "summary",
                        "text": "The market expanded.",
                        "violation_type": "evidence_retrieval_failure",
                        "reason": "source context could not be accessed",
                    }
                ]
            },
        ),
        analysis_store=FakeAnalysisStore(),
    )

    retrieval = next(issue for issue in result.issues if issue.rule_id == "grounding")
    assert result.status == "fail"
    assert retrieval.severity == "error"


def test_data_gap_downgrades_only_structured_retrieval_failures():
    issues = [
        ValidationIssue(
            schema_version="1.0",
            rule_id="grounding",
            message="[grounding] Evidence was unavailable.",
            severity="error",
            affected_section="summary",
            violation_type="evidence_retrieval_failure",
        ),
        ValidationIssue(
            schema_version="1.0",
            rule_id="grounding",
            message=(
                "[grounding] [factual_claim|evidence_retrieval_failure] "
                "Evidence was unavailable."
            ),
            severity="error",
            affected_section="summary",
        ),
        ValidationIssue(
            schema_version="1.0",
            rule_id="grounding",
            message=(
                "[grounding] [factual_claim|unsupported_number] "
                "Unsupported value: 42%."
            ),
            severity="error",
            affected_section="summary",
        ),
        ValidationIssue(
            schema_version="1.0",
            rule_id="grounding",
            message=(
                "[grounding] [factual_claim|contradicted] "
                "Source reports a decline."
            ),
            severity="error",
            affected_section="summary",
        ),
        ValidationIssue(
            schema_version="1.0",
            rule_id="report_identity",
            message="[report_identity] Identity mismatch.",
            severity="error",
            affected_section="report",
        ),
    ]

    downgraded = downgrade_issues_for_data_gap(issues)

    assert [item.severity for item in downgraded] == [
        "warning",
        "error",
        "error",
        "error",
        "error",
    ]
    serialized = ValidationReport(
        schema_version="1.1",
        status="pass",
        severity="warning",
        issues=[downgraded[0]],
    ).to_dict()
    assert serialized["issues"][0]["violation_type"] == "evidence_retrieval_failure"
    assert (
        validation_report_from_payload(serialized, "").issues[0].violation_type
        == "evidence_retrieval_failure"
    )


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


def test_validation_reuses_retained_primary_model_rules_before_provider_call(tmp_path):
    settings = _settings(tmp_path, validation_grounding_use_vector_store=False)
    request = ValidationRequest(
        schema_version="1.0",
        report_id="r-validation-reuse",
        report=_report(),
        artifacts={"insights_final": [], "quotes_final": []},
        evidence_packs={},
        source_id="md5:validation-reuse",
    )
    first_client = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    first = validate_report(
        request,
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=first_client,
        report_name="validation-reuse",
    )
    replay_client = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    replay = validate_report(
        request,
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=replay_client,
        report_name="validation-reuse",
    )

    assert first.status == replay.status
    assert first.issues == replay.issues
    assert first_client.requests
    assert replay_client.requests == []


def test_semantic_validation_reuses_retained_result_without_recovery_state(tmp_path):
    reused = SimpleNamespace(
        reusable=True,
        reason="compatible_retained_output",
        output_payload={"metrics": [], "quotes": []},
    )
    client = FakeOpenAI(semantic_payload={"metrics": [], "quotes": []})

    outcome = run_semantic_validation(
        insights=[
            {
                "id": "insight_1",
                "text": "Revenue reached $1.3T.",
                "metric": {"value": "$1.3T", "unit": "", "timeframe": "2024"},
            }
        ],
        quotes=[],
        evidence_texts=["Revenue reached $1.3T in 2024."],
        settings=_settings(tmp_path),
        prompt_client=FakePromptClient(),
        openai_client=client,
        ctx=_ctx(),
        report_id="semantic-reuse",
        source_id="source:semantic-reuse",
        prompt_family_reuse_reader=lambda _request, _ctx: reused,
        prompt_family_materializer=lambda _request, _ctx: None,
    )

    assert outcome.issues == []
    assert client.requests == []


__all__ = [
    "test_validation_keeps_unsupported_number_and_quote_errors_with_data_gap",
    "test_validation_allows_structured_retrieval_failure_under_data_gap_policy",
    "test_structured_retrieval_failure_without_data_gap_remains_blocking",
    "test_blocking_data_gap_policy_keeps_retrieval_failure_blocking",
    "test_data_gap_downgrades_only_structured_retrieval_failures",
    "test_validation_issue_order_preserved_with_parallel_checks",
    "test_validation_grounding_uses_chat_path_when_flag_disabled",
    "test_validation_grounding_uses_vector_path_when_flag_enabled",
    "test_validation_cache_isolated_by_grounding_retrieval_mode",
    "test_validation_reuses_retained_primary_model_rules_before_provider_call",
    "test_semantic_validation_reuses_retained_result_without_recovery_state",
]
