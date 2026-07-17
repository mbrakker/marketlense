# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_report_analysis_generator.py"
)

import json

import logging

import threading

import time

from dataclasses import replace

from pathlib import Path

from types import SimpleNamespace

import pytest

from src.contracts.context_category_fit import (
    CategoryFitCandidate,
    ContextCategoryFitResponse,
    ReportCategoryContext,
)

from src.contracts.artifact_generation import ArtifactRenderTask

from src.contracts.drive import DriveFile

from src.contracts.ingest import IngestSettings

from src.contracts.pdf_text import PdfTextExtractResponse

from src.contracts.pdf_utils import PdfInfoResponse

from src.contracts.regeneration import ArtifactRegenerationResponse

from src.contracts.report_generation import (
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)

from src.contracts.report_models import Figure, Quote, ReportPayload

from src.contracts.run_context import RunContext

from src.contracts.taxonomy import TaxonomyExtractResponse

from src.contracts.validation import ValidationIssue, ValidationReport

from src.generators.public_editorial_quality_generator import BLOCKING_RULE_IDS

from src.generators.report_analysis_generator import (
    start_vector_store_indexing,
    VectorStoreIndexingState,
)
from src.contracts.logging import MAX_LOG_EVENT_BYTES

from src.generators.report_generation_dependencies import (
    ReportAnalysisDependencies,
)

from src.generators.report_generation_shared import derive_title, report_slug

from src.orchestrators import retry_orchestrator as retry_orch

from src.orchestrators.report_analysis_orchestrator import run_report_analysis

from src.utils.errors import AppError


def _runtime(tmp_path: Path) -> ReportRuntimeState:
    file = DriveFile(
        schema_version="1.0",
        file_id="file-1",
        name="report.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    settings = IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-5-mini",
        batch_limit=1,
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path=str(tmp_path / "cats.yaml"),
        cover_style_path=str(tmp_path / "cover.yaml"),
        ingest_lock_path=str(tmp_path / "lock"),
        temperature=0.0,
        report_worker_limit=1,
        public_editorial_quality_disabled_rule_waivers={
            rule_id: "test-only non-public artifact fixture"
            for rule_id in BLOCKING_RULE_IDS
        },
    )
    ctx = RunContext(schema_version="1.0", run_id="run", task_id="task", span_id="span")
    return ReportRuntimeState(
        schema_version="1.0",
        file=file,
        local_pdf_path=str(tmp_path / "report.pdf"),
        settings=settings,
        md5="md5",
        ctx=ctx,
        file_name=file.name,
        report_name=report_slug(file.name, file.file_id),
        report_title=derive_title(file.name),
        analysis_mode="vector_store",
        analysis_modes=["vector_store"],
        report_worker_limit=1,
        parallel_within_file=False,
    )


def _payload() -> ReportPayload:
    return ReportPayload(
        schema_version="1.1",
        tldr="TLDR",
        title="Base Title",
        insights=["A", "B", "C", "D", "E"],
        quote=Quote(schema_version="1.0", text="Quote", author="Author"),
        figure=Figure(schema_version="1.0", title="Figure", evidence="Evidence"),
        commentary="Commentary",
        source="https://example.com",
        publisher="",
    )


def _artifacts(**overrides) -> dict:
    payload = {
        "schema_version": "1.0",
        "toc_topics": ["Topic"],
        "summary": {
            "tldr": "summary",
            "executive_summary": "Summary",
            "claim_evidence_map": [],
        },
        "insights_candidates": [
            {
                "id": "candidate-1",
                "text": "Candidate 1",
                "evidence_id": "f1",
                "evidence": "Evidence 1",
                "metric": {},
                "pages": [1],
                "score": 0.9,
            }
        ],
        "insights_final": [
            {
                "id": "insight-1",
                "text": "Insight 1",
                "evidence_id": "f1",
                "evidence": "Evidence 1",
                "metric": {},
                "pages": [1],
            },
            {
                "id": "insight-2",
                "text": "Insight 2",
                "evidence_id": "f2",
                "evidence": "Evidence 2",
                "metric": {},
                "pages": [2],
            },
            {
                "id": "insight-3",
                "text": "Insight 3",
                "evidence_id": "f3",
                "evidence": "Evidence 3",
                "metric": {},
                "pages": [3],
            },
            {
                "id": "insight-4",
                "text": "Insight 4",
                "evidence_id": "f4",
                "evidence": "Evidence 4",
                "metric": {},
                "pages": [4],
            },
            {
                "id": "insight-5",
                "text": "Insight 5",
                "evidence_id": "f5",
                "evidence": "Evidence 5",
                "metric": {},
                "pages": [5],
            },
        ],
        "quotes_final": [
            {
                "text": "Quote",
                "speaker": "Author",
                "citation": "p. 1",
                "page": 1,
                "evidence_id": "q1",
            }
        ],
        "expert_comment": "Expert comment",
        "linkedin_post": "LinkedIn post",
        "source_status": {
            "schema_version": "1.0",
            "not_available": False,
            "reason": "",
        },
    }
    payload.update(overrides)
    return payload


def _source(runtime: ReportRuntimeState) -> ReportSourceState:
    return ReportSourceState(
        schema_version="1.0",
        runtime=runtime,
        info_response=PdfInfoResponse(
            schema_version="1.0",
            path=runtime.local_pdf_path,
            page_count=2,
            metadata={},
        ),
        contents_page_number=0,
        contents_heading="",
        contents_image="",
        text_response=PdfTextExtractResponse(
            schema_version="1.0",
            text="body",
            pages_extracted=1,
            char_count=100,
            text_density=100.0,
        ),
        text_status={"schema_version": "1.0", "text_density": 100.0},
        text_validation_status="pass",
        text_validation_reason="",
        text_validation_pages=[1],
        payload=_payload(),
        pdf_context=None,
        pdf_context_for_tasks=None,
    )


def _selection(
    runtime: ReportRuntimeState, source: ReportSourceState
) -> ReportSelectionState:
    return ReportSelectionState(
        schema_version="1.0",
        runtime=runtime,
        source=source,
        payload=source.payload,
        rank_usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        candidate_count=0,
    )


def _fit_response(
    *,
    report_id: str = "file-1",
    categories: list[str] | None = None,
    category_labels: list[str] | None = None,
) -> ContextCategoryFitResponse:
    resolved_categories = list(categories or ["cat"])
    resolved_labels = list(category_labels or ["Category"])
    return ContextCategoryFitResponse(
        schema_version="1.0",
        report_id=report_id,
        categories=resolved_categories,
        category_labels=resolved_labels,
        fits=[
            CategoryFitCandidate(
                category_id=resolved_categories[0],
                label=resolved_labels[0],
                fit_score=0.9,
                decision="primary",
                why_fit="The report strongly aligns with this category.",
                why_not_fit="",
                evidence_sections=["Overview"],
            )
        ],
        request_id="req-1",
        model="gpt-5-mini",
        raw_response="{}",
    )


def _deps(
    *,
    figure_caption_overrides: dict | None = None,
    **overrides,
) -> ReportAnalysisDependencies:
    base = ReportAnalysisDependencies.default()
    figure_caption = replace(
        base.figure_caption,
        **(figure_caption_overrides or {}),
    )
    seeded = replace(
        replace(base, figure_caption=figure_caption),
        vector_store_get_status=lambda req, ctx: SimpleNamespace(
            status="completed",
            indexed_at_utc="2026-01-01T00:00:00Z",
            last_error=None,
        ),
        extract_taxonomy=lambda req, ctx: TaxonomyExtractResponse(
            schema_version="1.0",
            taxonomy=["tag"],
            region="US",
            time_period="2026",
        ),
        build_report_category_context=lambda req, ctx: ReportCategoryContext(
            schema_version="1.0",
            report_id="file-1",
            title="Base Title",
            publisher="",
            region="US",
            time_period="2026",
            overview="Context overview",
            methods=[],
            key_findings=[],
            limitations=[],
            sections=[],
        ),
        fit_report_categories_from_context=lambda req, ctx: _fit_response(),
        vector_store_update_metadata=lambda req, ctx: None,
    )
    return replace(seeded, **overrides)


def _orchestrator_events(caplog) -> list[dict]:
    parsed: list[dict] = []
    for record in caplog.records:
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if payload.get("module") == "market_lense.report_analysis_orchestrator":
            parsed.append(payload)
    return parsed


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
