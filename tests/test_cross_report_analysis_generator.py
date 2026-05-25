from __future__ import annotations

import json
import logging
from dataclasses import is_dataclass, replace
from types import SimpleNamespace

import pytest

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportEvidenceAgreementGroup,
    CrossReportEvidenceAgreementResult,
    CrossReportEvidenceInputResult,
    CrossReportEvidenceReference,
    CrossReportRawMetricReference,
    CrossReportSelectedSourceReport,
    CrossReportSelectedTheme,
    CrossReportSignalScore,
    CrossReportSignalScoreResult,
)
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import PromptRenderResponse, PromptSet, PromptTemplate
from src.generators.cross_report_analysis_generator import (
    generate_cross_report_analysis,
    validate_cross_report_generated_analysis,
)


class FakePromptClient:
    def __init__(self) -> None:
        self.render_variables: list[dict] = []

    def load_prompt_set(self, request, ctx):
        return PromptSet(
            schema_version="1.0",
            system=PromptTemplate(
                schema_version="1.0",
                path="src/prompts/cross_report_analysis/synthesis/system.yaml",
                text="system prompt",
                sha256="system-hash",
            ),
            user=PromptTemplate(
                schema_version="1.0",
                path="src/prompts/cross_report_analysis/synthesis/user.yaml",
                text="user {{ request_json }} {{ evidence_json }}",
                sha256="user-hash",
            ),
        )

    def render_prompt(self, request, ctx):
        self.render_variables.append(dict(request.variables))
        text = request.template.text
        for key, value in request.variables.items():
            text = text.replace("{{ " + key + " }}", str(value))
        return PromptRenderResponse(schema_version="1.0", text=text)


_DEFAULT_PAYLOAD = object()


class FakeOpenAIClient:
    def __init__(self, payload: dict | None | object = _DEFAULT_PAYLOAD) -> None:
        self.requests = []
        self.payload = (
            payload
            if payload is not _DEFAULT_PAYLOAD
            else {
                "analysis_id": "analysis-ai-commerce",
                "title": "AI Commerce Adoption Across Retail Reports",
                "slug": "ai-commerce-adoption-across-retail-reports",
                "executive_summary": "AI adoption is moving unevenly across retail reports.",
                "sections": [
                    {
                        "section_id": "key-cross-report-signals",
                        "heading": "Key cross-report signals",
                        "body": "AI adoption appears in both reports, but direction differs.",
                        "evidence_ids": [
                            "ev-report-a-claim-1",
                            "ev-report-b-finding-1",
                        ],
                        "raw_metric_ids": [],
                    },
                    {
                        "section_id": "divergences",
                        "heading": "Divergences",
                        "body": "One source reports increasing adoption while another reports decline.",
                        "evidence_ids": [
                            "ev-report-a-claim-1",
                            "ev-report-b-finding-1",
                        ],
                        "raw_metric_ids": ["metric-a"],
                    },
                    {
                        "section_id": "convergences",
                        "heading": "Convergences",
                        "body": "Both selected reports discuss AI adoption as a retail priority.",
                        "evidence_ids": [
                            "ev-report-a-claim-1",
                            "ev-report-b-finding-1",
                        ],
                        "raw_metric_ids": [],
                    },
                    {
                        "section_id": "raw-metric-appendix",
                        "heading": "Raw metric appendix",
                        "body": "Metric values are cited as source-specific context only.",
                        "evidence_ids": ["ev-report-a-claim-1"],
                        "raw_metric_ids": ["metric-a"],
                    },
                ],
                "evidence_map": {
                    "key-cross-report-signals": [
                        "ev-report-a-claim-1",
                        "ev-report-b-finding-1",
                    ],
                    "divergences": ["ev-report-a-claim-1", "ev-report-b-finding-1"],
                },
                "source_notes": [
                    "Publisher coverage is limited to two projected reports."
                ],
            }
        )

    def openai_chat_json(self, request, ctx):
        self.requests.append(request)
        if self.payload is None:
            return OpenAIResponseResult(
                schema_version="1.0",
                text="not-json",
                parsed_json=None,
                input_tokens=1000,
                output_tokens=250,
                total_tokens=1250,
                model=request.model,
                request_id="provider-request-1",
            )
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(self.payload),
            parsed_json=self.payload,
            input_tokens=1000,
            output_tokens=250,
            total_tokens=1250,
            model=request.model,
            request_id="provider-request-1",
        )


def _events(caplog) -> list[dict]:
    return [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.cross_report_analysis_generator"
    ]


def _request() -> CrossReportAnalysisRequest:
    return CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id="analysis-request",
        topic="AI commerce adoption",
        auto_theme=True,
        category_filters=["Retail"],
        tag_filters=["AI"],
        publisher_filters=[],
        date_range_start="2026-05-01",
        date_range_end="2026-05-31",
        max_source_reports=2,
        diagnostic=False,
        override_publishability=False,
        publication_mode="generate_only",
    )


def _selected_theme() -> CrossReportSelectedTheme:
    return CrossReportSelectedTheme(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        theme_id="theme-tag-ai",
        label="AI commerce adoption",
        rationale="AI appears across selected retail reports.",
        matched_tags=["AI"],
        matched_categories=["Retail"],
        source_report_ids=["report-a", "report-b"],
        score_components={"density": 1.0, "diversity": 1.0},
        selection_reasons=["multi_report_theme"],
        rejection_risks=[],
    )


def _source(
    report_id: str, publisher: str, rank: int
) -> CrossReportSelectedSourceReport:
    return CrossReportSelectedSourceReport(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id=report_id,
        title=f"{report_id} title",
        publisher=publisher,
        publisher_id=publisher.lower().replace(" ", "-"),
        report_date="2026-05-01",
        projection_status="projected",
        content_hash=f"{report_id}-hash",
        rank=rank,
        selection_reasons=["test_source"],
        evidence_count=1,
        category_labels=["Retail"],
        tags=["AI"],
    )


def _evidence(
    evidence_id: str, report_id: str, text: str
) -> CrossReportEvidenceReference:
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=evidence_id,
        report_id=report_id,
        publisher=f"{report_id} Publisher",
        title=f"{report_id} title",
        source_table="report_claims",
        entity_uid=evidence_id,
        content_class="claim",
        text=text,
        source_metadata={"page": 1},
    )


def _metric() -> CrossReportRawMetricReference:
    return CrossReportRawMetricReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        metric_id="metric-a",
        report_id="report-a",
        publisher="Publisher A",
        label="AI pilot adoption",
        raw_value="42",
        unit="percent",
        context="Source-specific survey response.",
        evidence_id="ev-report-a-claim-1",
        source_metadata={"page": 4},
    )


def _analysis_inputs():
    selected_theme = _selected_theme()
    evidence = [
        _evidence("ev-report-a-claim-1", "report-a", "AI adoption is increasing."),
        _evidence("ev-report-b-finding-1", "report-b", "AI adoption is declining."),
    ]
    evidence_inputs = CrossReportEvidenceInputResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_sources=[
            _source("report-a", "Publisher A", 1),
            _source("report-b", "Publisher B", 2),
        ],
        evidence=evidence,
        raw_metrics=[_metric()],
        evidence_by_report_id={
            "report-a": ["ev-report-a-claim-1"],
            "report-b": ["ev-report-b-finding-1"],
        },
        dropped_evidence_counts={},
        prompt_input_chars=1200,
    )
    signal = CrossReportSignalScore(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        signal_id="signal-ai",
        label="AI",
        evidence_ids=["ev-report-a-claim-1", "ev-report-b-finding-1"],
        component_scores={"recurrence": 1.0, "diversity": 1.0},
        total_score=2.0,
        reasons=["raw_metric_magnitude_ignored"],
    )
    signal_result = CrossReportSignalScoreResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme=selected_theme,
        signal_scores=[signal],
        selected_signal_ids=["signal-ai"],
        score_weights={"recurrence": 1.0, "diversity": 1.0},
        raw_metric_policy="raw_metrics_preserved_without_normalization",
        dropped_signal_counts={},
    )
    group = CrossReportEvidenceAgreementGroup(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        group_id="group-signal-ai",
        label="AI",
        agreement_type="divergent",
        signal_ids=["signal-ai"],
        evidence_ids=["ev-report-a-claim-1", "ev-report-b-finding-1"],
        source_report_ids=["report-a", "report-b"],
        publisher_count=2,
        uncertainty_reasons=["opposed_directional_language"],
        prompt_input_label="divergent: AI",
    )
    agreement_result = CrossReportEvidenceAgreementResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme=selected_theme,
        evidence_groups=[group],
        prompt_uncertainty_inputs=[
            {
                "group_id": "group-signal-ai",
                "agreement_type": "divergent",
                "evidence_ids": ["ev-report-a-claim-1", "ev-report-b-finding-1"],
                "uncertainty_reasons": ["opposed_directional_language"],
            }
        ],
        agreement_counts={"divergent": 1},
    )
    return evidence_inputs, signal_result, agreement_result


def _settings(tmp_path):
    return SimpleNamespace(
        openai_api_key="test-key",
        openai_model="gpt-5-mini",
        openai_models={},
        openai_seed=42,
        cross_report_analysis_prompt_namespace="cross_report_analysis/synthesis",
        cross_report_analysis_model="gpt-5-mini",
        cross_report_analysis_temperature=1.0,
        cross_report_analysis_timeout_seconds=600.0,
        cross_report_analysis_cache_enabled=True,
        cache_dir=str(tmp_path / "cache"),
        cost_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
        cost_daily_path=str(tmp_path / "cost-daily.json"),
        model_pricing={},
    )


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
        "Source notes",
        "Raw metric appendix",
    }
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
    assert complete["fields"]["section_count"] == 5


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


def _generated_result(tmp_path, run_context):
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    return generate_cross_report_analysis(
        _request(),
        evidence_inputs,
        signal_result,
        agreement_result,
        _settings(tmp_path),
        run_context,
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAIClient(),
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
