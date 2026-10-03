# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent / "cases_01_render_output_and_cards.py"
)

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.contracts.claim_validation import CLAIM_GROUNDING_VALIDATOR_VERSION
from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestSettings
from src.contracts.pdf_text import PdfTextExtractResponse
from src.contracts.pdf_utils import PdfInfoResponse
from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.report_cards import (
    CardCoverAsset,
    CardCoverAssetSet,
    ReportCardManifestWriteResponse,
)
from src.contracts.report_generation import (
    ReportAnalysisState,
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.report_identity import ReportTitleResolution
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.report_store import (
    ReportMetadataGetResponse,
)
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import ReportId
from src.contracts.validation import ValidationReport
from src.generators.claim_validation_generator import (
    attach_claim_validation_execution_identity,
    claim_validation_package_hash_valid,
    validate_retained_claims,
)
from src.generators.report_generation_dependencies import ReportRenderDependencies
from src.generators.report_generation_shared import (
    derive_title,
    html_cache_key,
    report_slug,
)
from src.generators.report_render_generator import (
    _public_source_note,
    _resolved_public_publisher,
    _resolved_report_title,
    render_preview_asset,
    render_report_output,
)
from src.services.report_analysis_store_service import store_pack
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.publication_projection import publication_projection_hash


def _template_bundle_sha(template_contents: dict[str, str]) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "templates": {
                name: hashlib.sha256(content.encode("utf-8")).hexdigest()
                for name, content in template_contents.items()
            },
        }
    )


def _runtime(tmp_path: Path, *, md5: str | None) -> ReportRuntimeState:
    file = DriveFile(
        schema_version="1.0",
        file_id="file-1",
        name="report.pdf",
        modified_time="2026-06-10T08:30:00Z",
        md5_checksum=md5,
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
    )
    ctx = RunContext(schema_version="1.0", run_id="run", task_id="task", span_id="span")
    return ReportRuntimeState(
        schema_version="1.0",
        file=file,
        local_pdf_path=str(tmp_path / "report.pdf"),
        settings=settings,
        md5=md5,
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
        title="Doc Title",
        insights=["A", "B", "C", "D", "E"],
        quote=Quote(schema_version="1.0", text="Quote", author="Author"),
        figure=Figure(schema_version="1.0", title="Figure", evidence="Evidence"),
        commentary="Commentary",
        source="https://example.com",
        publisher="Doc Publisher",
        categories=["cat"],
        taxonomy=["tag"],
        region="US",
        time_period="2026",
    )


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
        candidate_count=1,
    )


def _analysis(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    selection: ReportSelectionState,
) -> ReportAnalysisState:
    return ReportAnalysisState(
        schema_version="1.0",
        runtime=runtime,
        source=source,
        selection=selection,
        payload=source.payload,
        normalized_payload=source.payload,
        data_dict={
            "title": source.payload.title,
            "publisher": source.payload.publisher,
            "time_period": source.payload.time_period,
            "_figure_section_enabled": False,
            "_figure_gallery": [],
            "_figure_top": "",
        },
        evidence_paths={"doc_map": "doc_map.json"},
        evidence_packs={"doc_map": {"title": source.payload.title}},
        artifacts_payload={
            "summary": {
                "tldr": (
                    "A complete standard summary explains the report's strategic "
                    "finding."
                ),
                "card_tldr_compact": (
                    "Strategic demand is shifting toward more efficient channels."
                ),
            },
            "cover_semantics": {
                "evidence_shape": "trend",
                "direction": "rising",
                "evidence_density": "balanced",
                "domain_layer": "grid",
                "selection_reason": (
                    "The report presents a sustained upward market trend."
                ),
            },
            "insights_final": [
                {"text": "Channel efficiency improved across the measured period."},
                {"text": "Investment shifted toward higher-return customer segments."},
            ],
            "publication_date": "2026-06-09",
        },
        validation_report=ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path="validation.json",
        ),
        category_labels=["Category"],
        vector_store_id="vs_1",
        vector_store_status="completed",
        indexed_at_utc="2026-01-01T00:00:00Z",
        openai_file_id="file_1",
        last_error=None,
    )


def _card_cover_assets(asset_dir: Path) -> CardCoverAssetSet:
    return CardCoverAssetSet(
        "1.0",
        CardCoverAsset(
            "1.0", "small", str(asset_dir / "report-card-small.png"), 1600, 900
        ),
        CardCoverAsset(
            "1.0", "medium", str(asset_dir / "report-card-medium.png"), 1200, 1500
        ),
        CardCoverAsset(
            "1.0", "large", str(asset_dir / "report-card-large.png"), 1200, 1600
        ),
    )


def _deps(**overrides) -> ReportRenderDependencies:
    base = ReportRenderDependencies.default()

    def _generated_covers(req, ctx):
        del ctx
        report = req.reports[0]
        return [
            SimpleNamespace(
                schema_version="2.0",
                file_id=report.file_id,
                title=report.title,
                status="generated",
                assets=_card_cover_assets(
                    Path(req.output_dir) / report.report_slug / "assets"
                ),
                error=None,
            )
        ]

    seeded = replace(
        base,
        render_preview=lambda req, ctx: SimpleNamespace(
            schema_version="1.1", image_path="preview.png", page_number=0
        ),
        upsert_report_metadata=lambda req, ctx: None,
        get_report_metadata=lambda req, ctx: ReportMetadataGetResponse(
            schema_version="1.1",
            file_id="file-1",
            title="DB Title",
            created_at=1,
            updated_at=2,
            file_name="report.pdf",
            publisher="DB Publisher",
            taxonomy=["tag"],
            categories=["cat"],
            region="US",
            time_period="Q1 2026",
            source_url=None,
            html_path=None,
            md5="md5",
            page_count=2,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id="vs_1",
            evidence_pack_paths={"doc_map": "doc_map.json"},
        ),
        generate_cover_images=_generated_covers,
        write_report_card_manifest=lambda req, ctx: ReportCardManifestWriteResponse(
            schema_version="1.0",
            manifest_path=str(Path(req.output_dir) / "report-card-manifest.json"),
            bytes_written=1024,
        ),
    )
    return replace(seeded, **overrides)


def _cover_assets(runtime: ReportRuntimeState) -> CardCoverAssetSet:
    return _card_cover_assets(
        Path(runtime.settings.output_dir) / runtime.report_name / "assets"
    )


__all__ = [name for name in globals() if not name.startswith("__")]
