# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_generate_cross_report_analysis_calls_services_and_returns_contract(
    tmp_path,
    run_context,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    prompt_client = FakePromptClient()
    openai_client = FakeOpenAIClient()
    caplog.set_level(
        logging.INFO, logger="market_lense.cross_report_analysis_generator"
    )

    result = generate_cross_report_analysis(
        _request(),
        evidence_inputs,
        signal_result,
        agreement_result,
        _settings(tmp_path),
        run_context,
        prompt_client=prompt_client,
        openai_client=openai_client,
    )

    assert is_dataclass(result)
    assert result.analysis_id == "analysis-ai-commerce"
    assert result.selected_theme.theme_id == "theme-tag-ai"
    assert [source.report_id for source in result.selected_sources] == [
        "report-a",
        "report-b",
    ]
    assert [score.signal_id for score in result.signal_scores] == ["signal-ai"]
    assert [metric.metric_id for metric in result.raw_metrics] == ["metric-a"]
    assert {section.heading for section in result.sections} >= {
        "Key cross-report signals",
        "Convergences",
        "Divergences",
        "Raw metric appendix",
    }
    assert "Source notes" not in {section.heading for section in result.sections}
    assert result.evidence_map["divergences"] == [
        "ev-report-a-claim-1",
        "ev-report-b-finding-1",
    ]
    assert result.prompt_hashes == {"system": "system-hash", "user": "user-hash"}
    assert result.cost_summary == {
        "input_tokens": 1000,
        "output_tokens": 250,
        "total_tokens": 1250,
        "request_id": "provider-request-1",
    }
    assert len(openai_client.requests) == 1
    assert openai_client.requests[0].model == "gpt-5-mini"
    assert openai_client.requests[0].temperature == 1.0
    rendered_variables = prompt_client.render_variables[-1]
    assert "full_report_text" not in rendered_variables
    assert "ev-report-a-claim-1" in rendered_variables["evidence_json"]
    assert "divergent" in rendered_variables["evidence_groups_json"]

    events = _events(caplog)
    assert_logs_have_required_fields(events)
    rendered = [
        event
        for event in events
        if event["event"] == "cross_report_analysis_prompt_rendered"
    ][0]
    assert rendered["fields"]["system_sha256"] == "system-hash"
    assert rendered["fields"]["rendered_user_prompt"]
    complete = [
        event
        for event in events
        if event["event"] == "cross_report_analysis_generation_complete"
    ][0]
    assert complete["fields"]["provider_request_id"] == "provider-request-1"
    assert complete["fields"]["section_count"] == 4

def test_generate_cross_report_analysis_rejects_unknown_evidence_id(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    bad_payload = {
        "analysis_id": "analysis-ai-commerce",
        "title": "AI Commerce Adoption Across Retail Reports",
        "slug": "ai-commerce-adoption-across-retail-reports",
        "executive_summary": "AI adoption is moving unevenly.",
        "sections": [
            {
                "section_id": "summary",
                "heading": "Summary",
                "body": "Unsupported claim.",
                "evidence_ids": ["missing-evidence"],
                "raw_metric_ids": [],
            }
        ],
        "evidence_map": {"summary": ["missing-evidence"]},
    }

    with pytest.raises(Exception) as exc:
        generate_cross_report_analysis(
            _request(),
            evidence_inputs,
            signal_result,
            agreement_result,
            _settings(tmp_path),
            run_context,
            prompt_client=FakePromptClient(),
            openai_client=FakeOpenAIClient(bad_payload),
        )

    assert_app_error(
        exc.value,
        code="cross_report_analysis_evidence_invalid",
        retryable=False,
        severity="error",
    )

def test_generate_cross_report_analysis_canonicalizes_projected_entity_uid_citations(
    tmp_path,
    run_context,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    canonical_evidence = replace(
        evidence_inputs.evidence[0],
        entity_uid="projected-entity-claim-a",
    )
    evidence_inputs = replace(
        evidence_inputs,
        evidence=[
            canonical_evidence,
            *evidence_inputs.evidence[1:],
        ],
    )
    payload = {
        "analysis_id": "analysis-ai-commerce",
        "title": "AI Commerce Adoption Across Retail Reports",
        "slug": "ai-commerce-adoption-across-retail-reports",
        "executive_summary": "AI adoption is moving unevenly.",
        "sections": [
            {
                "section_id": "summary",
                "heading": "Summary",
                "body": "Canonicalized claim.",
                "evidence_ids": ["projected-entity-claim-a"],
                "raw_metric_ids": [],
            }
        ],
        "evidence_map": {"summary": ["projected-entity-claim-a"]},
    }

    result = generate_cross_report_analysis(
        _request(),
        evidence_inputs,
        signal_result,
        agreement_result,
        _settings(tmp_path),
        run_context,
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAIClient(payload),
    )

    assert result.sections[0].evidence_ids == ["ev-report-a-claim-1"]
    assert result.evidence_map == {"summary": ["ev-report-a-claim-1"]}

def test_generate_cross_report_analysis_canonicalizes_unique_projected_finding_prefixes(
    tmp_path,
    run_context,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    canonical_evidence_id = "report-a:finding:F4_multi_signal_optimization"
    canonical_evidence = replace(
        evidence_inputs.evidence[0],
        evidence_id=canonical_evidence_id,
        entity_uid=canonical_evidence_id,
        source_table="report_findings",
        content_class="finding",
    )
    evidence_inputs = replace(
        evidence_inputs,
        evidence=[
            canonical_evidence,
            *evidence_inputs.evidence[1:],
        ],
        evidence_by_report_id={
            **evidence_inputs.evidence_by_report_id,
            "report-a": [canonical_evidence_id],
        },
    )
    payload = {
        "analysis_id": "analysis-ai-commerce",
        "title": "AI Commerce Adoption Across Retail Reports",
        "slug": "ai-commerce-adoption-across-retail-reports",
        "executive_summary": "AI adoption is moving unevenly.",
        "sections": [
            {
                "section_id": "summary",
                "heading": "Summary",
                "body": "Canonicalized finding prefix.",
                "evidence_ids": ["report-a:finding:F4"],
                "raw_metric_ids": [],
            }
        ],
        "evidence_map": {"summary": ["report-a:finding:F4"]},
    }

    result = generate_cross_report_analysis(
        _request(),
        evidence_inputs,
        signal_result,
        agreement_result,
        _settings(tmp_path),
        run_context,
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAIClient(payload),
    )

    assert result.sections[0].evidence_ids == [canonical_evidence_id]
    assert result.evidence_map == {"summary": [canonical_evidence_id]}

def test_generate_cross_report_analysis_allows_full_ids_when_projected_prefixes_collide(
    tmp_path,
    run_context,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    first_evidence_id = "report-a:claim:finding_01_marketplace_prevalence"
    second_evidence_id = "report-a:claim:finding_02_revenue_distribution"
    first_evidence = replace(
        evidence_inputs.evidence[0],
        evidence_id=first_evidence_id,
        entity_uid="report-a:claim:abc123",
    )
    second_evidence = replace(
        evidence_inputs.evidence[1],
        report_id="report-a",
        evidence_id=second_evidence_id,
        entity_uid="report-a:claim:def456",
    )
    evidence_inputs = replace(
        evidence_inputs,
        evidence=[
            first_evidence,
            second_evidence,
        ],
        evidence_by_report_id={"report-a": [first_evidence_id, second_evidence_id]},
    )
    payload = {
        "analysis_id": "analysis-ai-commerce",
        "title": "AI Commerce Adoption Across Retail Reports",
        "slug": "ai-commerce-adoption-across-retail-reports",
        "executive_summary": "AI adoption is moving unevenly.",
        "sections": [
            {
                "section_id": "summary",
                "heading": "Summary",
                "body": "Full projected finding ids remain unambiguous.",
                "evidence_ids": [first_evidence_id, second_evidence_id],
                "raw_metric_ids": [],
            }
        ],
        "evidence_map": {"summary": [first_evidence_id, second_evidence_id]},
    }

    result = generate_cross_report_analysis(
        _request(),
        evidence_inputs,
        signal_result,
        agreement_result,
        _settings(tmp_path),
        run_context,
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAIClient(payload),
    )

    assert result.sections[0].evidence_ids == [first_evidence_id, second_evidence_id]
    assert result.evidence_map == {"summary": [first_evidence_id, second_evidence_id]}

def test_generate_cross_report_analysis_rejects_ambiguous_projected_prefix_citations(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    first_evidence_id = "report-a:claim:finding_01_marketplace_prevalence"
    second_evidence_id = "report-a:claim:finding_02_revenue_distribution"
    evidence_inputs = replace(
        evidence_inputs,
        evidence=[
            replace(
                evidence_inputs.evidence[0],
                evidence_id=first_evidence_id,
                entity_uid="report-a:claim:abc123",
            ),
            replace(
                evidence_inputs.evidence[1],
                report_id="report-a",
                evidence_id=second_evidence_id,
                entity_uid="report-a:claim:def456",
            ),
        ],
        evidence_by_report_id={"report-a": [first_evidence_id, second_evidence_id]},
    )
    payload = {
        "analysis_id": "analysis-ai-commerce",
        "title": "AI Commerce Adoption Across Retail Reports",
        "slug": "ai-commerce-adoption-across-retail-reports",
        "executive_summary": "AI adoption is moving unevenly.",
        "sections": [
            {
                "section_id": "summary",
                "heading": "Summary",
                "body": "Ambiguous projected prefix should not be accepted.",
                "evidence_ids": ["report-a:claim:finding"],
                "raw_metric_ids": [],
            }
        ],
        "evidence_map": {"summary": ["report-a:claim:finding"]},
    }

    with pytest.raises(Exception) as exc:
        generate_cross_report_analysis(
            _request(),
            evidence_inputs,
            signal_result,
            agreement_result,
            _settings(tmp_path),
            run_context,
            prompt_client=FakePromptClient(),
            openai_client=FakeOpenAIClient(payload),
        )

    assert_app_error(
        exc.value,
        code="cross_report_analysis_evidence_invalid",
        retryable=False,
        severity="error",
    )
    assert exc.value.context["missing_evidence_ids"] == ["report-a:claim:finding"]

def test_generate_cross_report_analysis_rejects_colliding_evidence_aliases(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    evidence_inputs = replace(
        evidence_inputs,
        evidence=[
            replace(evidence_inputs.evidence[0], entity_uid="ev-report-b-finding-1"),
            evidence_inputs.evidence[1],
        ],
    )

    with pytest.raises(Exception) as exc:
        generate_cross_report_analysis(
            _request(),
            evidence_inputs,
            signal_result,
            agreement_result,
            _settings(tmp_path),
            run_context,
            prompt_client=FakePromptClient(),
            openai_client=FakeOpenAIClient(),
        )

    assert_app_error(
        exc.value,
        code="cross_report_analysis_evidence_alias_collision",
        retryable=False,
        severity="error",
    )
    assert exc.value.context["alias"] == "ev-report-b-finding-1"
    assert set(exc.value.context["conflicting_evidence_ids"]) == {
        "ev-report-a-claim-1",
        "ev-report-b-finding-1",
    }

def test_generate_cross_report_analysis_checks_rendered_prompt_budget_before_model(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    openai_client = FakeOpenAIClient()
    settings = _settings(tmp_path)
    settings.cross_report_analysis_max_prompt_chars = 10

    with pytest.raises(Exception) as exc:
        generate_cross_report_analysis(
            _request(),
            evidence_inputs,
            signal_result,
            agreement_result,
            settings,
            run_context,
            prompt_client=FakePromptClient(),
            openai_client=openai_client,
        )

    assert_app_error(
        exc.value,
        code="cross_report_prompt_budget_exceeded",
        retryable=False,
        severity="error",
    )
    assert openai_client.requests == []

def test_generate_cross_report_analysis_uses_request_prompt_budget_override(
    tmp_path,
    run_context,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    settings = _settings(tmp_path)
    settings.cross_report_analysis_max_prompt_chars = 10

    result = generate_cross_report_analysis(
        _request(),
        evidence_inputs,
        signal_result,
        agreement_result,
        settings,
        run_context,
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAIClient(),
        max_prompt_chars=80000,
    )

    assert result.analysis_id == "analysis-ai-commerce"

def test_generate_cross_report_analysis_omits_unsupported_source_notes(
    tmp_path,
    run_context,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    payload = {
        "analysis_id": "analysis-ai-commerce",
        "title": "AI Commerce Adoption Across Retail Reports",
        "slug": "ai-commerce-adoption-across-retail-reports",
        "executive_summary": "AI adoption is moving unevenly.",
        "sections": [
            {
                "section_id": "summary",
                "heading": "Summary",
                "body": "Grounded claim.",
                "evidence_ids": ["ev-report-a-claim-1"],
                "raw_metric_ids": [],
            }
        ],
        "evidence_map": {"summary": ["ev-report-a-claim-1"]},
        "source_notes": ["Unsupported note without cited evidence."],
    }

    result = generate_cross_report_analysis(
        _request(),
        evidence_inputs,
        signal_result,
        agreement_result,
        _settings(tmp_path),
        run_context,
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAIClient(payload),
    )

    assert [section.section_id for section in result.sections] == ["summary"]

def test_generate_cross_report_analysis_rejects_missing_json_payload(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()

    with pytest.raises(Exception) as exc:
        generate_cross_report_analysis(
            _request(),
            evidence_inputs,
            signal_result,
            agreement_result,
            _settings(tmp_path),
            run_context,
            prompt_client=FakePromptClient(),
            openai_client=FakeOpenAIClient(None),
        )

    assert_app_error(
        exc.value,
        code="cross_report_analysis_invalid_json",
        retryable=False,
        severity="error",
    )

def test_generate_cross_report_analysis_rejects_empty_sections(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    bad_payload = {
        "analysis_id": "analysis-ai-commerce",
        "title": "AI Commerce Adoption Across Retail Reports",
        "slug": "ai-commerce-adoption-across-retail-reports",
        "executive_summary": "AI adoption is moving unevenly.",
        "sections": [],
        "evidence_map": {"summary": ["ev-report-a-claim-1"]},
    }

    with pytest.raises(Exception) as exc:
        generate_cross_report_analysis(
            _request(),
            evidence_inputs,
            signal_result,
            agreement_result,
            _settings(tmp_path),
            run_context,
            prompt_client=FakePromptClient(),
            openai_client=FakeOpenAIClient(bad_payload),
        )

    assert_app_error(
        exc.value,
        code="cross_report_analysis_output_invalid",
        retryable=False,
        severity="error",
    )

def test_validate_cross_report_generated_analysis_accepts_grounded_artifact(
    tmp_path,
    run_context,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    generated = _generated_result(tmp_path, run_context)
    caplog.set_level(
        logging.INFO, logger="market_lense.cross_report_analysis_generator"
    )

    result = validate_cross_report_generated_analysis(
        generated,
        run_context,
        prompt_budget_chars=1200,
        max_prompt_chars=60000,
    )

    assert result.status == "pass"
    assert result.passed is True
    assert result.checked_evidence_ids == [
        "ev-report-a-claim-1",
        "ev-report-b-finding-1",
    ]
    assert result.missing_evidence_ids == []
    assert result.metric_normalization_violations == []
    assert result.prompt_budget_chars == 1200
    events = _events(caplog)
    assert_logs_have_required_fields(events)
    validation_event = [
        event
        for event in events
        if event["event"] == "cross_report_analysis_validation_complete"
    ][0]
    assert validation_event["fields"]["status"] == "pass"

def test_validate_cross_report_generated_analysis_rejects_missing_section_evidence(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    generated = _generated_result(tmp_path, run_context)
    invalid = replace(
        generated,
        sections=[
            replace(
                generated.sections[0],
                evidence_ids=[],
            )
        ],
    )

    with pytest.raises(Exception) as exc:
        validate_cross_report_generated_analysis(invalid, run_context)

    assert_app_error(
        exc.value,
        code="cross_report_analysis_validation_failed",
        retryable=False,
        severity="error",
    )
    assert (
        "section_missing_evidence:key-cross-report-signals"
        in exc.value.context["issues"]
    )

def test_validate_cross_report_generated_analysis_rejects_unknown_evidence(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    generated = _generated_result(tmp_path, run_context)
    invalid = replace(
        generated,
        evidence_map={"unsupported-claim": ["unknown-evidence"]},
    )

    with pytest.raises(Exception) as exc:
        validate_cross_report_generated_analysis(invalid, run_context)

    assert_app_error(
        exc.value,
        code="cross_report_analysis_validation_failed",
        retryable=False,
        severity="error",
    )
    assert exc.value.context["missing_evidence_ids"] == ["unknown-evidence"]

def test_validate_cross_report_generated_analysis_rejects_empty_required_sections(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    generated = _generated_result(tmp_path, run_context)
    invalid = replace(generated, sections=[])

    with pytest.raises(Exception) as exc:
        validate_cross_report_generated_analysis(invalid, run_context)

    assert_app_error(
        exc.value,
        code="cross_report_analysis_validation_failed",
        retryable=False,
        severity="error",
    )
    assert "sections_empty" in exc.value.context["issues"]

def test_validate_cross_report_generated_analysis_rejects_metric_normalization_language(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    generated = _generated_result(tmp_path, run_context)
    invalid = replace(
        generated,
        sections=[
            replace(
                generated.sections[0],
                body="The normalized average across publishers shows a comparable increase.",
            )
        ],
    )

    with pytest.raises(Exception) as exc:
        validate_cross_report_generated_analysis(invalid, run_context)

    assert_app_error(
        exc.value,
        code="cross_report_analysis_validation_failed",
        retryable=False,
        severity="error",
    )
    assert exc.value.context["metric_normalization_violations"] == [
        "normalized average",
        "average across publishers",
    ]

__all__ = [
    "test_generate_cross_report_analysis_calls_services_and_returns_contract",
    "test_generate_cross_report_analysis_rejects_unknown_evidence_id",
    "test_generate_cross_report_analysis_canonicalizes_projected_entity_uid_citations",
    "test_generate_cross_report_analysis_canonicalizes_unique_projected_finding_prefixes",
    "test_generate_cross_report_analysis_allows_full_ids_when_projected_prefixes_collide",
    "test_generate_cross_report_analysis_rejects_ambiguous_projected_prefix_citations",
    "test_generate_cross_report_analysis_rejects_colliding_evidence_aliases",
    "test_generate_cross_report_analysis_checks_rendered_prompt_budget_before_model",
    "test_generate_cross_report_analysis_uses_request_prompt_budget_override",
    "test_generate_cross_report_analysis_omits_unsupported_source_notes",
    "test_generate_cross_report_analysis_rejects_missing_json_payload",
    "test_generate_cross_report_analysis_rejects_empty_sections",
    "test_validate_cross_report_generated_analysis_accepts_grounded_artifact",
    "test_validate_cross_report_generated_analysis_rejects_missing_section_evidence",
    "test_validate_cross_report_generated_analysis_rejects_unknown_evidence",
    "test_validate_cross_report_generated_analysis_rejects_empty_required_sections",
    "test_validate_cross_report_generated_analysis_rejects_metric_normalization_language",
]
