from __future__ import annotations

import json
import logging
from dataclasses import replace

import pytest

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportEvidenceReference,
    CrossReportProjectedDataReadRequest,
    CrossReportProjectedDataReadResponse,
    CrossReportSourceReportCandidate,
)
from src.contracts.analytics_projection import (
    ClaimEmbeddingReadResponse,
    ClaimEmbeddingRecord,
)
from src.contracts.semantic_ids import EntityUid, ReportId
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidateExtractionRequest,
)
from src.contracts.remediation import RemediationListRequest
from src.orchestrators.signal_candidate_orchestrator import (
    run_signal_candidate_extraction,
)
from src.services.state_service import list_remediation_records
from src.utils.errors import AppError


def _analysis_request() -> CrossReportAnalysisRequest:
    return CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id="extract-ai-commerce",
        topic="AI commerce",
        auto_theme=False,
        category_filters=["Retail"],
        tag_filters=["AI"],
        publisher_filters=[],
        date_range_start="2026-05-01",
        date_range_end="2026-05-31",
        max_source_reports=2,
        diagnostic=False,
        override_publishability=True,
        publication_mode="generate_only",
    )


def _candidate(report_id: str, publisher: str) -> CrossReportSourceReportCandidate:
    return CrossReportSourceReportCandidate(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id=report_id,
        title=f"{publisher} AI Commerce Report",
        publisher=publisher,
        publisher_id=publisher.lower().replace(" ", "-"),
        report_date="2026-05-20",
        projection_status="projected",
        content_hash=f"{report_id}-hash",
        category_labels=["Retail"],
        tags=["AI"],
        evidence_count=2,
        claim_count=1,
        finding_count=1,
        quote_count=0,
        metric_count=0,
        recency_score=0.0,
        relevance_score=0.0,
        diversity_score=0.0,
        density_score=2.0,
        total_score=0.0,
        selection_reasons=["projection_status:projected"],
        rejection_reasons=[],
        category_ids=["retail"],
    )


def _evidence(
    evidence_id: str, report_id: str, publisher: str, text: str
) -> CrossReportEvidenceReference:
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=evidence_id,
        report_id=report_id,
        publisher=publisher,
        title=f"{publisher} AI Commerce Report",
        source_table="report_claims",
        entity_uid=f"{report_id}:claim:{evidence_id}",
        content_class="claim",
        text=text,
        source_metadata={"pages": [2], "evidence": "projected claim"},
    )


def _embedding(
    evidence: CrossReportEvidenceReference,
    *,
    content_hash: str,
    vector: list[float],
) -> ClaimEmbeddingRecord:
    return ClaimEmbeddingRecord(
        schema_version="1.0",
        embedding_uid=EntityUid(f"{evidence.entity_uid}:embedding:test"),
        claim_uid=EntityUid(evidence.entity_uid),
        entity_uid=EntityUid(evidence.entity_uid),
        report_id=ReportId(evidence.report_id),
        content_hash=content_hash,
        embedding_version="claim-embedding.test.v1",
        provider="openai",
        model="text-embedding-3-small",
        dimensions=len(vector),
        vector=vector,
        external_vector_id=f"local:claim_embeddings:{evidence.entity_uid}",
        metadata={"taxonomy": ["ai", "retail"]},
        status="embedded",
        generated_at_utc="2026-06-28T12:00:00Z",
        updated_at_utc="2026-06-28T12:00:00Z",
        attempt_count=1,
        error_code="",
        error_message="",
        error_retryable=False,
        error_severity="",
    )


def _projected_data() -> CrossReportProjectedDataReadResponse:
    report_a = _evidence(
        "report-a:claim:1",
        "report-a",
        "Publisher A",
        "AI commerce adoption is increasing.",
    )
    report_b = _evidence(
        "report-b:claim:1",
        "report-b",
        "Publisher B",
        "AI commerce adoption is accelerating.",
    )
    return CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[
            _candidate("report-a", "Publisher A"),
            _candidate("report-b", "Publisher B"),
        ],
        evidence=[
            report_a,
            report_b,
        ],
        raw_metrics=[],
        content_hashes={
            "report-a": {report_a.entity_uid: "hash-a"},
            "report-b": {report_b.entity_uid: "hash-b"},
        },
        excluded_report_counts={},
    )


def _request(tmp_path) -> SignalCandidateExtractionRequest:
    return SignalCandidateExtractionRequest(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        extraction_request_id="extract-ai-commerce",
        analysis_request=_analysis_request(),
        projected_data_request=CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=str(tmp_path / "reports.sqlite"),
            category_filters=["Retail"],
            tag_filters=["AI"],
            content_classes=["claim", "finding", "quote", "metric"],
            minimum_projection_status="projected",
        ),
        db_path=str(tmp_path / "reports.sqlite"),
        max_evidence_items=6,
        max_signals=4,
        generated_at_utc="2026-06-02T12:00:00Z",
    )


def test_signal_candidate_orchestrator_extracts_stores_and_clusters_candidates(
    tmp_path,
    run_context,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    read_calls = []

    def _read_projected_data(request, ctx):
        read_calls.append(request)
        return _projected_data()

    caplog.set_level(logging.INFO, logger="market_lense.signal_candidate_orchestrator")
    outcome = run_signal_candidate_extraction(
        _request(tmp_path),
        run_context,
        read_projected_data_fn=_read_projected_data,
    )
    repeat = run_signal_candidate_extraction(
        _request(tmp_path),
        run_context,
        read_projected_data_fn=_read_projected_data,
    )

    assert outcome.status == "stored"
    assert outcome.candidate_count == 2
    assert outcome.group_count == 2
    assert outcome.stored_response.candidate_count == 2
    assert repeat.candidate_count == 2
    assert {candidate.support_level for candidate in outcome.batch.candidates} == {
        "multi_report_convergent"
    }
    assert [candidate.candidate_id for candidate in outcome.batch.candidates] == [
        "signal-candidate:theme-explicit-ai-commerce:signal-ai",
        "signal-candidate:theme-explicit-ai-commerce:signal-retail",
    ]
    assert read_calls[0].db_path == str(tmp_path / "reports.sqlite")
    assert outcome.state_transitions == [
        "started",
        "projected_data_read",
        "source_selected",
        "theme_selected",
        "claim_embeddings_read",
        "evidence_assembled",
        "signals_scored",
        "agreement_grouped",
        "candidates_built",
        "candidates_stored",
        "completed",
    ]
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.signal_candidate_orchestrator"
    ]
    assert_logs_have_required_fields(events)
    assert {event["event"] for event in events} >= {
        "signal_candidate_extraction_start",
        "signal_candidate_extraction_complete",
    }


def test_signal_candidate_orchestrator_reads_claim_embeddings_for_preselection(
    tmp_path,
    run_context,
) -> None:
    projected_data = _projected_data()
    read_embedding_calls = []

    def _read_projected_data(request, ctx):
        return projected_data

    def _read_claim_embeddings(request, ctx):
        read_embedding_calls.append(request)
        evidence_by_id = {item.evidence_id: item for item in projected_data.evidence}
        return ClaimEmbeddingReadResponse(
            schema_version="1.0",
            embeddings=[
                _embedding(
                    evidence_by_id["report-a:claim:1"],
                    content_hash="hash-a",
                    vector=[0.0, 1.0],
                ),
                _embedding(
                    evidence_by_id["report-b:claim:1"],
                    content_hash="hash-b",
                    vector=[0.0, 1.0],
                ),
            ],
        )

    request = replace(_request(tmp_path), max_evidence_items=1)
    outcome = run_signal_candidate_extraction(
        request,
        run_context,
        read_projected_data_fn=_read_projected_data,
        read_claim_embeddings_fn=_read_claim_embeddings,
    )

    assert len(read_embedding_calls) == 1
    embedding_request = read_embedding_calls[0]
    assert embedding_request.db_path == str(tmp_path / "reports.sqlite")
    assert embedding_request.report_ids == ["report-a", "report-b"]
    assert embedding_request.topics == ["AI commerce", "ai_commerce", "Retail", "AI"]
    assert embedding_request.statuses == ["embedded"]
    assert embedding_request.limit == 4
    assert outcome.candidate_count >= 1


def test_signal_candidate_failure_creates_operator_held_remediation(
    tmp_path,
    run_context,
) -> None:
    request = replace(_request(tmp_path), state_db=str(tmp_path / "state.sqlite"))

    with pytest.raises(AppError, match="projection unavailable"):
        run_signal_candidate_extraction(
            request,
            run_context,
            read_projected_data_fn=lambda _request, _ctx: (_ for _ in ()).throw(
                AppError(
                    code="signal_candidate_projection_unavailable",
                    message="projection unavailable",
                    retryable=True,
                    severity="error",
                )
            ),
        )

    records = list_remediation_records(
        RemediationListRequest(
            schema_version="1.0",
            state_db=request.state_db,
            workflow="signal_candidate_extraction",
        ),
        run_context,
    ).records
    assert len(records) == 1
    assert records[0].error_code == "signal_candidate_projection_unavailable"
    assert records[0].status == "operator_action_required"
