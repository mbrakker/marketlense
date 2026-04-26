from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.contracts.context_category_fit import (
    ContextCategoryFitRequest,
    ContextCategoryFitResponse,
    ReportCategoryContext,
    ReportContextBuildRequest,
)
from src.contracts.cover_images import CoverImageGenerationRequest
from src.contracts.files import FileStatRequest, ReadTextRequest, WriteBytesRequest
from src.contracts.openai import (
    OpenAIJSONImagePromptRequest,
    OpenAIPdfOcrRequest,
    OpenAIPdfOcrResponse,
)
from src.contracts.pdf_contents import (
    PdfContentsDetectionRequest,
    PdfContentsDetectionResponse,
)
from src.contracts.pdf_context import PdfContextBuildRequest
from src.contracts.pdf_ocr import (
    PdfOcrSplitRequest,
    PdfOcrSplitResponse,
    PdfTextRenderRequest,
    PdfTextRenderResponse,
)
from src.contracts.pdf_text import (
    PdfTextExtractRequest,
    PdfTextExtractResponse,
    PdfTextSampleRequest,
)
from src.contracts.pdf_utils import PdfInfoRequest, PdfInfoResponse
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    ArtifactRegenerationResponse,
)
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.report_assets import (
    CropRefineBBoxApplyRequest,
    CropRefinePageRenderRequest,
    CropRefineRequest,
    CropRequest,
    ExtractCandidatesRequest,
    FigureExtractRequest,
    PreviewRequest,
    RankRequest,
    RenderRequest,
    RenderResponse,
)
from src.contracts.report_store import (
    ReportMetadataGetRequest,
    ReportMetadataUpsertRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.state import StateGetRequest, StateRecordRequest
from src.contracts.taxonomy import TaxonomyExtractRequest
from src.contracts.validation import ValidationReport
from src.contracts.vector_store import (
    VectorStoreAttachFileRequest,
    VectorStoreCreateRequest,
    VectorStoreStatusRequest,
    VectorStoreUpdateMetadataRequest,
    VectorStoreUploadFileRequest,
)
from src.generators.artifact_generator import generate_artifacts
from src.generators.context_category_fit_generator import (
    fit_report_categories_from_context,
)
from src.generators.cover_image_generator import generate_cover_images
from src.generators.evidence_pack_generator import generate_evidence_packs
from src.generators.report_context_generator import build_report_category_context
from src.generators.report_regeneration_generator import regenerate_artifacts
from src.generators.taxonomy_generator import extract_taxonomy
from src.generators.validation_generator import validate_report as run_validation
from src.services import (
    llm_service,
    report_analysis_store_service,
    state_service,
    vector_store_service,
)
from src.services.file_service import file_stat, read_text, write_bytes
from src.services.pdf_service import (
    apply_crop_refine_bbox as apply_crop_refine_bbox_service,
    build_pdf_context,
    collect_candidates as collect_candidates_service,
    crop_regions as crop_regions_service,
    detect_contents_page as detect_contents_page_service,
    extract_best_figure as extract_best_figure_service,
    extract_pdf_info,
    extract_pdf_text,
    render_page_for_crop_refine as render_page_for_crop_refine_service,
    render_preview as render_preview_service,
    render_text_pdf,
    sample_pdf_text,
    split_pdf_for_ocr,
)
from src.services.prompt_service import load_prompt_set, render_prompt
from src.services.rank_service import (
    rank_candidates as rank_candidates_service,
    refine_candidate_crops as refine_candidate_crops_service,
)
from src.services.render_service import render_report as render_report_service
from src.services.report_store_service import (
    get_metadata as get_report_metadata,
    upsert_metadata as upsert_report_metadata,
)


@dataclass(frozen=True)
class ReportSourceDependencies:
    build_pdf_context: Callable[[PdfContextBuildRequest, RunContext], Any]
    extract_pdf_info: Callable[[PdfInfoRequest, RunContext], PdfInfoResponse]
    detect_contents_page: Callable[
        [PdfContentsDetectionRequest, RunContext], PdfContentsDetectionResponse
    ]
    render_preview: Callable[[PreviewRequest, RunContext], Any]
    render_text_pdf: Callable[[PdfTextRenderRequest, RunContext], PdfTextRenderResponse]
    split_pdf_for_ocr: Callable[[PdfOcrSplitRequest, RunContext], PdfOcrSplitResponse]
    extract_pdf_text: Callable[
        [PdfTextExtractRequest, RunContext], PdfTextExtractResponse
    ]
    sample_pdf_text: Callable[[PdfTextSampleRequest, RunContext], Any]
    load_prompt_set: Callable[[PromptLoadRequest, RunContext], Any]
    render_prompt: Callable[[PromptRenderRequest, RunContext], Any]
    openai_ocr_pdf: Callable[[OpenAIPdfOcrRequest, RunContext], OpenAIPdfOcrResponse]
    file_stat: Callable[[FileStatRequest, RunContext], Any]
    read_text: Callable[[ReadTextRequest, RunContext], Any]
    write_bytes: Callable[[WriteBytesRequest, RunContext], Any]

    @classmethod
    def default(cls) -> "ReportSourceDependencies":
        return cls(
            build_pdf_context=build_pdf_context,
            extract_pdf_info=extract_pdf_info,
            detect_contents_page=detect_contents_page_service,
            render_preview=render_preview_service,
            render_text_pdf=render_text_pdf,
            split_pdf_for_ocr=split_pdf_for_ocr,
            extract_pdf_text=extract_pdf_text,
            sample_pdf_text=sample_pdf_text,
            load_prompt_set=load_prompt_set,
            render_prompt=render_prompt,
            openai_ocr_pdf=llm_service.openai_ocr_pdf,
            file_stat=file_stat,
            read_text=read_text,
            write_bytes=write_bytes,
        )


@dataclass(frozen=True)
class ReportSelectionDependencies:
    extract_best_figure: Callable[[FigureExtractRequest, RunContext], Any]
    collect_candidates: Callable[[ExtractCandidatesRequest, RunContext], Any]
    crop_regions: Callable[[CropRequest, RunContext], Any]
    render_page_for_crop_refine: Callable[
        [CropRefinePageRenderRequest, RunContext], Any
    ]
    apply_crop_refine_bbox: Callable[[CropRefineBBoxApplyRequest, RunContext], Any]
    rank_candidates: Callable[[RankRequest, RunContext], Any]
    refine_candidate_crops: Callable[[CropRefineRequest, RunContext], Any]
    load_prompt_set: Callable[[PromptLoadRequest, RunContext], Any]
    render_prompt: Callable[[PromptRenderRequest, RunContext], Any]
    analysis_pack_path: Callable[[AnalysisPackPathRequest, RunContext], Any]
    analysis_store_pack: Callable[[AnalysisStorePackRequest, RunContext], Any]
    read_text: Callable[[ReadTextRequest, RunContext], Any]

    @classmethod
    def default(cls) -> "ReportSelectionDependencies":
        return cls(
            extract_best_figure=extract_best_figure_service,
            collect_candidates=collect_candidates_service,
            crop_regions=crop_regions_service,
            render_page_for_crop_refine=render_page_for_crop_refine_service,
            apply_crop_refine_bbox=apply_crop_refine_bbox_service,
            rank_candidates=rank_candidates_service,
            refine_candidate_crops=refine_candidate_crops_service,
            load_prompt_set=load_prompt_set,
            render_prompt=render_prompt,
            analysis_pack_path=report_analysis_store_service.pack_path,
            analysis_store_pack=report_analysis_store_service.store_pack,
            read_text=read_text,
        )


@dataclass(frozen=True)
class FigureCaptionDependencies:
    load_prompt_set: Callable[[PromptLoadRequest, RunContext], Any]
    render_prompt: Callable[[PromptRenderRequest, RunContext], Any]
    openai_chat_json_with_images: Callable[
        [OpenAIJSONImagePromptRequest, RunContext], Any
    ]
    analysis_store_pack: Callable[[AnalysisStorePackRequest, RunContext], Any]

    @classmethod
    def default(cls) -> "FigureCaptionDependencies":
        return cls(
            load_prompt_set=load_prompt_set,
            render_prompt=render_prompt,
            openai_chat_json_with_images=llm_service.openai_chat_json_with_images,
            analysis_store_pack=report_analysis_store_service.store_pack,
        )


@dataclass(frozen=True)
class ReportAnalysisDependencies:
    state_get: Callable[[StateGetRequest, RunContext], Any]
    state_record: Callable[[StateRecordRequest, RunContext], Any]
    vector_store_get_status: Callable[[VectorStoreStatusRequest, RunContext], Any]
    vector_store_create: Callable[[VectorStoreCreateRequest, RunContext], Any]
    vector_store_upload_file: Callable[[VectorStoreUploadFileRequest, RunContext], Any]
    vector_store_attach_file: Callable[[VectorStoreAttachFileRequest, RunContext], Any]
    vector_store_update_metadata: Callable[
        [VectorStoreUpdateMetadataRequest, RunContext], Any
    ]
    extract_taxonomy: Callable[[TaxonomyExtractRequest, RunContext], Any]
    build_report_category_context: Callable[
        [ReportContextBuildRequest, RunContext], ReportCategoryContext
    ]
    fit_report_categories_from_context: Callable[
        [ContextCategoryFitRequest, RunContext], ContextCategoryFitResponse
    ]
    generate_evidence_packs: Callable[..., dict[str, dict]]
    generate_artifacts: Callable[..., dict[str, Any]]
    regenerate_artifacts: Callable[
        [ArtifactRegenerationRequest], ArtifactRegenerationResponse
    ]
    run_validation: Callable[..., ValidationReport]
    analysis_pack_path: Callable[[AnalysisPackPathRequest, RunContext], Any]
    analysis_store_pack: Callable[[AnalysisStorePackRequest, RunContext], Any]
    figure_caption: FigureCaptionDependencies

    @classmethod
    def default(cls) -> "ReportAnalysisDependencies":
        return cls(
            state_get=state_service.get,
            state_record=state_service.record,
            vector_store_get_status=vector_store_service.get_vector_store_status,
            vector_store_create=vector_store_service.create_vector_store,
            vector_store_upload_file=vector_store_service.upload_file,
            vector_store_attach_file=vector_store_service.attach_file,
            vector_store_update_metadata=vector_store_service.update_metadata,
            extract_taxonomy=extract_taxonomy,
            build_report_category_context=build_report_category_context,
            fit_report_categories_from_context=fit_report_categories_from_context,
            generate_evidence_packs=generate_evidence_packs,
            generate_artifacts=generate_artifacts,
            regenerate_artifacts=regenerate_artifacts,
            run_validation=run_validation,
            analysis_pack_path=report_analysis_store_service.pack_path,
            analysis_store_pack=report_analysis_store_service.store_pack,
            figure_caption=FigureCaptionDependencies.default(),
        )


@dataclass(frozen=True)
class ReportRenderDependencies:
    render_preview: Callable[[PreviewRequest, RunContext], Any]
    upsert_report_metadata: Callable[[ReportMetadataUpsertRequest, RunContext], Any]
    get_report_metadata: Callable[[ReportMetadataGetRequest, RunContext], Any]
    render_report: Callable[[RenderRequest, RunContext], RenderResponse]
    generate_cover_images: Callable[[CoverImageGenerationRequest, RunContext], Any]
    file_stat: Callable[[FileStatRequest, RunContext], Any]
    read_text: Callable[[ReadTextRequest, RunContext], Any]
    write_bytes: Callable[[WriteBytesRequest, RunContext], Any]

    @classmethod
    def default(cls) -> "ReportRenderDependencies":
        return cls(
            render_preview=render_preview_service,
            upsert_report_metadata=upsert_report_metadata,
            get_report_metadata=get_report_metadata,
            render_report=render_report_service,
            generate_cover_images=generate_cover_images,
            file_stat=file_stat,
            read_text=read_text,
            write_bytes=write_bytes,
        )


@dataclass(frozen=True)
class ReportGenerationDependencies:
    source: ReportSourceDependencies
    selection: ReportSelectionDependencies
    analysis: ReportAnalysisDependencies
    render: ReportRenderDependencies

    @classmethod
    def default(cls) -> "ReportGenerationDependencies":
        return cls(
            source=ReportSourceDependencies.default(),
            selection=ReportSelectionDependencies.default(),
            analysis=ReportAnalysisDependencies.default(),
            render=ReportRenderDependencies.default(),
        )
