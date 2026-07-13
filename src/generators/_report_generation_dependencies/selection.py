from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.contracts.crop_qa_escalation import (
    CropQaEscalationRequest,
    CropQaEscalationResponse,
)
from src.contracts.files import JsonObjectCacheReadRequest, ReadTextRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
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
    RankRequest,
)
from src.contracts.run_context import RunContext
from src.generators.crop_qa_escalation_generator import escalate_crop_qa
from src.services import report_analysis_store_service
from src.services.file_service import read_json_object_cache, read_text
from src.services.pdf_service import (
    apply_crop_refine_bbox as apply_crop_refine_bbox_service,
)
from src.services.pdf_service import (
    collect_candidates as collect_candidates_service,
)
from src.services.pdf_service import (
    crop_regions as crop_regions_service,
)
from src.services.pdf_service import (
    extract_best_figure as extract_best_figure_service,
)
from src.services.pdf_service import (
    render_page_for_crop_refine as render_page_for_crop_refine_service,
)
from src.services.prompt_service import load_prompt_set, render_prompt
from src.services.rank_service import (
    rank_candidates as rank_candidates_service,
)
from src.services.rank_service import (
    refine_candidate_crops as refine_candidate_crops_service,
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
    read_json_object_cache: Callable[[JsonObjectCacheReadRequest, RunContext], Any] = (
        read_json_object_cache
    )
    crop_qa_escalation: Callable[
        [CropQaEscalationRequest, RunContext], CropQaEscalationResponse
    ] = escalate_crop_qa

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
            read_json_object_cache=read_json_object_cache,
            crop_qa_escalation=escalate_crop_qa,
        )
