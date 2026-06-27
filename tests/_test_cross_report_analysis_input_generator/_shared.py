# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_cross_report_analysis_input_generator.py"
)

import json

import logging

from dataclasses import is_dataclass, replace

import pytest

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportEvidenceReference,
    CrossReportProjectedDataReadResponse,
    CrossReportRawMetricReference,
    CrossReportSelectedSourceReport,
    CrossReportSourceReportCandidate,
    CrossReportSourceSelectionResult,
    CrossReportValidationResult,
)

from src.contracts.files import (
    DirectoryEntry,
    ListDirectoryResponse,
    ReadTextFilesResponse,
    ReadTextResponse,
)

from src.generators import cross_report_analysis_input_generator as input_gen

from src.generators.cross_report_analysis_input_generator import (
    assemble_cross_report_analysis_inputs,
    group_cross_report_evidence_agreement,
    score_cross_report_signals,
    select_cross_report_theme,
    select_cross_report_source_reports,
    validate_cross_report_publishability,
)


def _request(
    *, max_source_reports: int = 2, diagnostic: bool = False
) -> CrossReportAnalysisRequest:
    return CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id="selection-request",
        topic="AI commerce",
        auto_theme=False,
        category_filters=[" Retail "],
        tag_filters=["AI"],
        publisher_filters=[],
        date_range_start="2026-05-01",
        date_range_end="2026-05-31",
        max_source_reports=max_source_reports,
        diagnostic=diagnostic,
        override_publishability=False,
        publication_mode="generate_only",
    )


def _candidate(
    report_id: str,
    *,
    publisher: str,
    report_date: str,
    evidence_count: int,
    tags: list[str] | None = None,
    categories: list[str] | None = None,
    projection_status: str = "projected",
) -> CrossReportSourceReportCandidate:
    return CrossReportSourceReportCandidate(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id=report_id,
        title=f"{report_id} AI Commerce Outlook",
        publisher=publisher,
        publisher_id=publisher.lower().replace(" ", "-"),
        report_date=report_date,
        projection_status=projection_status,
        content_hash=f"{report_id}-hash",
        category_labels=categories or ["Retail"],
        tags=tags or ["AI"],
        evidence_count=evidence_count,
        claim_count=max(evidence_count - 2, 0),
        finding_count=1,
        quote_count=1,
        metric_count=1,
        recency_score=0.0,
        relevance_score=0.0,
        diversity_score=0.0,
        density_score=0.0,
        total_score=0.0,
        selection_reasons=["projection_status:projected"],
        rejection_reasons=[],
    )


def _projected_data(
    candidates: list[CrossReportSourceReportCandidate],
) -> CrossReportProjectedDataReadResponse:
    return CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=candidates,
        evidence=[],
        raw_metrics=[],
        content_hashes={
            candidate.report_id: {candidate.report_id: candidate.content_hash}
            for candidate in candidates
        },
        excluded_report_counts={},
    )


def _events(caplog) -> list[dict]:
    return [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.cross_report_analysis_input_generator"
    ]


def _selected_source(
    report_id: str,
    *,
    publisher: str,
    report_date: str,
    evidence_count: int,
    tags: list[str],
    categories: list[str],
    rank: int = 1,
) -> CrossReportSelectedSourceReport:
    return CrossReportSelectedSourceReport(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id=report_id,
        title=f"{report_id} source report",
        publisher=publisher,
        publisher_id=publisher.lower().replace(" ", "-"),
        report_date=report_date,
        projection_status="projected",
        content_hash=f"{report_id}-hash",
        rank=rank,
        selection_reasons=["test_source"],
        evidence_count=evidence_count,
        category_labels=categories,
        tags=tags,
    )


def _source_selection(
    sources: list[CrossReportSelectedSourceReport],
) -> CrossReportSourceSelectionResult:
    return CrossReportSourceSelectionResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_sources=sources,
        ranked_candidates=[],
        rejected_candidates=[],
        cleaned_filters={"tag_filters": ["ai"], "category_filters": ["retail"]},
        excluded_report_counts={},
    )


def _evidence(
    evidence_id: str,
    *,
    report_id: str,
    content_class: str = "claim",
    text: str | None = None,
) -> CrossReportEvidenceReference:
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=evidence_id,
        report_id=report_id,
        publisher=f"{report_id} Publisher",
        title=f"{report_id} Title",
        source_table=f"report_{content_class}s",
        entity_uid=f"{report_id}:{content_class}:{evidence_id}",
        content_class=content_class,
        text=text or f"{content_class} text for {report_id}",
        source_metadata={"pages": [1], "quality": "fixture"},
    )


def _raw_metric(
    metric_id: str,
    *,
    report_id: str,
    raw_value: str,
    unit: str,
) -> CrossReportRawMetricReference:
    return CrossReportRawMetricReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        metric_id=metric_id,
        report_id=report_id,
        publisher=f"{report_id} Publisher",
        label="Adoption",
        raw_value=raw_value,
        unit=unit,
        context="Source-specific survey response",
        evidence_id=f"{report_id}-claim-1",
        source_metadata={"pages": [2], "raw_metric_reference": True},
    )


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
