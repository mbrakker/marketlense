from __future__ import annotations

import json

import pytest

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportEvidenceAgreementGroup,
    CrossReportEvidenceAgreementResult,
    CrossReportEvidenceInputResult,
    CrossReportEvidenceReference,
    CrossReportSelectedSourceReport,
    CrossReportSelectedTheme,
    CrossReportSignalScore,
    CrossReportSignalScoreResult,
)
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidate,
    validate_signal_candidate_contract,
)
from src.generators.signal_candidate_generator import build_signal_candidate_batch
from src.utils.errors import AppError


def _request() -> CrossReportAnalysisRequest:
    return CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id="signal-candidate-request",
        topic="AI commerce",
        auto_theme=False,
        category_filters=["Retail"],
        tag_filters=["AI"],
        publisher_filters=[],
        date_range_start="2026-05-01",
        date_range_end="2026-05-31",
        max_source_reports=3,
        diagnostic=False,
        override_publishability=False,
        publication_mode="generate_only",
    )


def _source(
    report_id: str, publisher: str, rank: int
) -> CrossReportSelectedSourceReport:
    return CrossReportSelectedSourceReport(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id=report_id,
        title=f"{publisher} AI Commerce Report",
        publisher=publisher,
        publisher_id=publisher.lower().replace(" ", "-"),
        report_date="2026-05-20",
        projection_status="projected",
        content_hash=f"{report_id}-hash",
        rank=rank,
        selection_reasons=["test"],
        evidence_count=2,
        category_labels=["Retail"],
        tags=["AI"],
        category_ids=["retail"],
    )


def _evidence(
    evidence_id: str,
    *,
    report_id: str,
    publisher: str,
    content_class: str = "claim",
    text: str,
    pages: list[int] | None = None,
) -> CrossReportEvidenceReference:
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=evidence_id,
        report_id=report_id,
        publisher=publisher,
        title=f"{publisher} AI Commerce Report",
        source_table=f"report_{content_class}s",
        entity_uid=f"{report_id}:{content_class}:{evidence_id}",
        content_class=content_class,
        text=text,
        source_metadata={"pages": pages or [2], "source_note": "projected"},
    )


def _theme() -> CrossReportSelectedTheme:
    return CrossReportSelectedTheme(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        theme_id="theme-explicit-ai-commerce",
        label="AI commerce",
        rationale="Operator selected topic.",
        matched_tags=["AI"],
        matched_categories=["Retail"],
        source_report_ids=["report-a", "report-b"],
        score_components={"operator": 1.0},
        selection_reasons=["explicit_topic"],
        rejection_risks=[],
    )


def _batch_inputs(
    *,
    evidence: list[CrossReportEvidenceReference],
    sources: list[CrossReportSelectedSourceReport],
    agreement_type: str,
    uncertainty_reasons: list[str],
) -> tuple[
    CrossReportEvidenceInputResult,
    CrossReportSignalScoreResult,
    CrossReportEvidenceAgreementResult,
]:
    theme = _theme()
    signal = CrossReportSignalScore(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        signal_id="signal-ai",
        label="AI",
        evidence_ids=[item.evidence_id for item in evidence],
        component_scores={
            "contradiction": 1.0 if agreement_type == "divergent" else 0.0,
            "diversity": 1.0,
            "recency": 0.5,
            "recurrence": min(len(evidence) / 3, 1.0),
            "support": 1.0,
            "taxonomy_fit": 1.0,
        },
        total_score=4.5,
        reasons=["evidence_recurrence:2", "raw_metric_magnitude_ignored"],
    )
    group = CrossReportEvidenceAgreementGroup(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        group_id="group-signal-ai",
        label="AI",
        agreement_type=agreement_type,
        signal_ids=["signal-ai"],
        evidence_ids=[item.evidence_id for item in evidence],
        source_report_ids=sorted({item.report_id for item in evidence}),
        publisher_count=len({item.publisher.casefold() for item in evidence}),
        uncertainty_reasons=uncertainty_reasons,
        prompt_input_label=f"{agreement_type}: AI",
    )
    evidence_inputs = CrossReportEvidenceInputResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_sources=sources,
        evidence=evidence,
        raw_metrics=[],
        evidence_by_report_id={
            source.report_id: [
                item.evidence_id
                for item in evidence
                if item.report_id == source.report_id
            ]
            for source in sources
        },
        dropped_evidence_counts={},
        prompt_input_chars=1200,
    )
    signal_result = CrossReportSignalScoreResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme=theme,
        signal_scores=[signal],
        selected_signal_ids=["signal-ai"],
        score_weights={"diversity": 1.0, "recurrence": 1.0},
        raw_metric_policy="raw_metrics_preserved_without_normalization",
        dropped_signal_counts={},
    )
    agreement_result = CrossReportEvidenceAgreementResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme=theme,
        evidence_groups=[group],
        prompt_uncertainty_inputs=[
            {
                "group_id": group.group_id,
                "agreement_type": agreement_type,
                "evidence_ids": group.evidence_ids,
                "uncertainty_reasons": group.uncertainty_reasons,
            }
        ],
        agreement_counts={agreement_type: 1},
    )
    return evidence_inputs, signal_result, agreement_result


def test_signal_candidate_batch_captures_single_report_support_and_lineage(
    run_context,
    assert_no_defaulted_required_fields,
) -> None:
    source = _source("report-a", "Publisher A", 1)
    evidence = [
        _evidence(
            "report-a:claim:1",
            report_id="report-a",
            publisher="Publisher A",
            text="AI commerce adoption is accelerating in checkout.",
        )
    ]
    evidence_inputs, signal_result, agreement_result = _batch_inputs(
        evidence=evidence,
        sources=[source],
        agreement_type="thin_coverage",
        uncertainty_reasons=["single_report_coverage"],
    )

    batch = build_signal_candidate_batch(
        _request(),
        evidence_inputs,
        signal_result,
        agreement_result,
        run_context,
        generated_at_utc="2026-06-02T12:00:00Z",
    )

    assert batch.schema_version == SIGNAL_CANDIDATE_SCHEMA_VERSION
    assert batch.extraction_request_id == "signal-candidate-request"
    assert len(batch.candidates) == 1
    candidate = batch.candidates[0]
    assert isinstance(candidate, SignalCandidate)
    assert_no_defaulted_required_fields(candidate)
    validate_signal_candidate_contract(candidate)
    assert (
        candidate.candidate_id
        == "signal-candidate:theme-explicit-ai-commerce:signal-ai"
    )
    assert candidate.candidate_type == "weak_signal"
    assert candidate.title == "AI"
    assert candidate.support_level == "single_report"
    assert candidate.validation_status == "approved"
    assert candidate.source_report_ids == ["report-a"]
    assert candidate.evidence_ids == ["report-a:claim:1"]
    assert candidate.source_refs[0].source_table == "report_claims"
    assert candidate.source_refs[0].page_refs == [2]
    assert "single_report_coverage" in candidate.caveats
    assert candidate.raw_source_context["signal_score"]["total_score"] == 4.5
    assert batch.groups[0].candidate_ids == [candidate.candidate_id]


def test_signal_candidate_batch_preserves_divergent_caveats_and_raw_context(
    run_context,
) -> None:
    sources = [
        _source("report-a", "Publisher A", 1),
        _source("report-b", "Publisher B", 2),
    ]
    evidence = [
        _evidence(
            "report-a:claim:1",
            report_id="report-a",
            publisher="Publisher A",
            text="AI commerce adoption is increasing.",
        ),
        _evidence(
            "report-b:finding:1",
            report_id="report-b",
            publisher="Publisher B",
            content_class="finding",
            text="AI commerce adoption is declining for budget-constrained teams.",
        ),
    ]
    evidence_inputs, signal_result, agreement_result = _batch_inputs(
        evidence=evidence,
        sources=sources,
        agreement_type="divergent",
        uncertainty_reasons=["opposed_directional_language"],
    )

    batch = build_signal_candidate_batch(
        _request(),
        evidence_inputs,
        signal_result,
        agreement_result,
        run_context,
        generated_at_utc="2026-06-02T12:00:00Z",
    )

    candidate = batch.candidates[0]
    assert candidate.support_level == "multi_report_divergent"
    assert candidate.source_report_ids == ["report-a", "report-b"]
    assert candidate.source_refs[1].content_class == "finding"
    assert "opposed_directional_language" in candidate.caveats
    encoded = json.dumps(candidate.raw_source_context, sort_keys=True)
    assert "AI commerce adoption is declining" in encoded
    assert "raw_metrics_preserved_without_normalization" in encoded


def test_signal_candidate_batch_rejects_unsupported_signal_without_evidence(
    run_context,
    assert_app_error,
) -> None:
    source = _source("report-a", "Publisher A", 1)
    evidence = [
        _evidence(
            "report-a:claim:1",
            report_id="report-a",
            publisher="Publisher A",
            text="AI commerce adoption is increasing.",
        )
    ]
    evidence_inputs, signal_result, agreement_result = _batch_inputs(
        evidence=evidence,
        sources=[source],
        agreement_type="thin_coverage",
        uncertainty_reasons=["single_report_coverage"],
    )
    broken_signal = CrossReportSignalScore(
        **{
            **signal_result.signal_scores[0].__dict__,
            "evidence_ids": ["missing-evidence"],
        }
    )
    signal_result = CrossReportSignalScoreResult(
        **{**signal_result.__dict__, "signal_scores": [broken_signal]}
    )

    with pytest.raises(AppError) as exc:
        build_signal_candidate_batch(
            _request(),
            evidence_inputs,
            signal_result,
            agreement_result,
            run_context,
            generated_at_utc="2026-06-02T12:00:00Z",
        )

    assert_app_error(
        exc.value,
        code="signal_candidate_unsupported",
        retryable=False,
        severity="error",
    )


def test_signal_candidate_batch_allows_source_refs_without_page_metadata(
    run_context,
) -> None:
    source = _source("report-a", "Publisher A", 1)
    evidence = [
        CrossReportEvidenceReference(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            evidence_id="report-a:claim:no-page",
            report_id="report-a",
            publisher="Publisher A",
            title="Publisher A AI Commerce Report",
            source_table="report_claims",
            entity_uid="report-a:claim:no-page",
            content_class="claim",
            text="AI commerce adoption is accelerating without page metadata.",
            source_metadata={"evidence": "projected claim"},
        )
    ]
    evidence_inputs, signal_result, agreement_result = _batch_inputs(
        evidence=evidence,
        sources=[source],
        agreement_type="thin_coverage",
        uncertainty_reasons=["single_report_coverage"],
    )

    batch = build_signal_candidate_batch(
        _request(),
        evidence_inputs,
        signal_result,
        agreement_result,
        run_context,
        generated_at_utc="2026-06-02T12:00:00Z",
    )

    assert batch.candidates[0].source_refs[0].page_refs == []
