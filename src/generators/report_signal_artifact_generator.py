from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportProjectedDataReadRequest,
)
from src.contracts.report_generation import ReportAnalysisState, ReportRuntimeState
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidateExtractionOutcome,
    SignalCandidateExtractionRequest,
)
from src.utils.cache_utils import sha256_json
from src.utils.slugify import slugify


SIGNAL_ARTIFACT_SCHEMA_VERSION = "1.0"
SIGNAL_ARTIFACT_PACK_NAME = "signals"


def resolve_signal_store_db(settings: object) -> str:
    configured = str(getattr(settings, "signal_store_db", "") or "").strip()
    if configured:
        return configured
    state_db = str(getattr(settings, "state_db", "") or "").strip()
    if state_db:
        return str(Path(state_db).parent / "signals.sqlite")
    return str(Path("state") / "signals.sqlite")


def planned_signal_artifact_path(
    runtime: ReportRuntimeState,
) -> str:
    slug = slugify(runtime.report_name or runtime.file.file_id) or "report"
    return str(
        Path(runtime.settings.output_dir)
        / slug
        / "report_analysis"
        / f"{SIGNAL_ARTIFACT_PACK_NAME}.json"
    )


def build_ingestion_signal_extraction_request(
    runtime: ReportRuntimeState,
    analysis: ReportAnalysisState,
) -> SignalCandidateExtractionRequest:
    payload = analysis.payload
    title = (payload.title or runtime.report_title or runtime.file_name).strip()
    categories = [item for item in payload.categories if str(item).strip()]
    category_labels = [item for item in analysis.category_labels if str(item).strip()]
    topic = (
        (category_labels[0] if category_labels else "")
        or (categories[0] if categories else "")
        or title
    )
    request_id = f"ingest-signal:{runtime.file.file_id}"
    return SignalCandidateExtractionRequest(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        extraction_request_id=request_id,
        analysis_request=CrossReportAnalysisRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            request_id=request_id,
            topic=topic,
            auto_theme=False,
            category_filters=[*categories, *category_labels],
            tag_filters=[item for item in payload.taxonomy if str(item).strip()],
            publisher_filters=[payload.publisher] if payload.publisher else [],
            date_range_start=None,
            date_range_end=None,
            max_source_reports=1,
            diagnostic=True,
            override_publishability=True,
            publication_mode="generate_only",
        ),
        projected_data_request=CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=runtime.settings.reports_db,
            publisher_filters=[payload.publisher] if payload.publisher else [],
            date_range_start=None,
            date_range_end=None,
            category_filters=[*categories, *category_labels],
            tag_filters=[item for item in payload.taxonomy if str(item).strip()],
            content_classes=["claim", "finding", "quote"],
            minimum_projection_status="projected",
        ),
        db_path=resolve_signal_store_db(runtime.settings),
        max_evidence_items=24,
        max_signals=6,
        generated_at_utc="",
    )


def build_ingestion_signal_artifact_payload(
    runtime: ReportRuntimeState,
    analysis: ReportAnalysisState,
    extraction: SignalCandidateExtractionOutcome,
    *,
    artifact_path: str,
) -> dict[str, Any]:
    base_payload: dict[str, Any] = {
        "schema_version": SIGNAL_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": SIGNAL_ARTIFACT_PACK_NAME,
        "source_report_id": runtime.file.file_id,
        "source_report_title": analysis.payload.title or runtime.report_title,
        "source_report_publisher": analysis.payload.publisher,
        "source_report_md5": runtime.md5 or "",
        "ingestion_run_id": runtime.ctx.run_id,
        "ingestion_task_id": runtime.ctx.task_id,
        "artifact_path": artifact_path,
        "reports_db": runtime.settings.reports_db,
        "signal_store_db": resolve_signal_store_db(runtime.settings),
        "extraction_request_id": extraction.extraction_request_id,
        "status": extraction.status,
        "candidate_count": extraction.candidate_count,
        "group_count": extraction.group_count,
        "support_levels": sorted(
            {candidate.support_level for candidate in extraction.batch.candidates}
        ),
        "accepted_signal_kinds": [
            "converging_trend",
            "emerging_theme",
            "contradiction",
            "acceleration",
            "strategic_implication",
            "blind_spot",
            "regional_divergence",
            "channel_shift",
            "capability_gap",
        ],
        "operating_rules": [
            "extract_evidence_not_benchmarks",
            "cluster_themes_not_numbers",
            "score_signal_strength_not_market_size",
            "preserve_source_traceability_and_caveats",
        ],
        "candidates": [asdict(candidate) for candidate in extraction.batch.candidates],
        "groups": [asdict(group) for group in extraction.batch.groups],
    }
    base_payload["artifact_sha256"] = sha256_json(base_payload)
    return base_payload
