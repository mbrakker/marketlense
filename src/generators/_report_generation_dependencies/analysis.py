from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.contracts.context_category_fit import (
    ContextCategoryFitRequest,
    ContextCategoryFitResponse,
    ReportCategoryContext,
    ReportContextBuildRequest,
)
from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    ArtifactRegenerationResponse,
)
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.state import StateGetByMd5Request, StateGetRequest, StateRecordRequest
from src.contracts.taxonomy import TaxonomyExtractRequest
from src.contracts.validation import ValidationReport
from src.contracts.vector_store import (
    VectorStoreAttachFileRequest,
    VectorStoreCreateRequest,
    VectorStoreDeleteRequest,
    VectorStoreStatusRequest,
    VectorStoreUpdateMetadataRequest,
    VectorStoreUploadFileRequest,
)
from src.generators.artifact_generator import generate_artifacts
from src.generators.context_category_fit_generator import (
    fit_report_categories_from_context,
)
from src.generators.evidence_pack_generator import generate_evidence_packs
from src.generators.report_context_generator import build_report_category_context
from src.generators.report_regeneration_generator import regenerate_artifacts
from src.generators.taxonomy_generator import extract_taxonomy
from src.generators.validation_generator import validate_report as run_validation
from src.services import (
    report_analysis_store_service,
    state_service,
    vector_store_service,
)

from .figure_caption import FigureCaptionDependencies


@dataclass(frozen=True)
class ReportAnalysisDependencies:
    state_get: Callable[[StateGetRequest, RunContext], Any]
    state_get_by_md5: Callable[[StateGetByMd5Request, RunContext], Any]
    state_record: Callable[[StateRecordRequest, RunContext], Any]
    vector_store_get_status: Callable[[VectorStoreStatusRequest, RunContext], Any]
    vector_store_create: Callable[[VectorStoreCreateRequest, RunContext], Any]
    vector_store_upload_file: Callable[[VectorStoreUploadFileRequest, RunContext], Any]
    vector_store_attach_file: Callable[[VectorStoreAttachFileRequest, RunContext], Any]
    vector_store_delete: Callable[[VectorStoreDeleteRequest, RunContext], Any]
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
            state_get_by_md5=state_service.get_by_md5,
            state_record=state_service.record,
            vector_store_get_status=vector_store_service.get_vector_store_status,
            vector_store_create=vector_store_service.create_vector_store,
            vector_store_upload_file=vector_store_service.upload_file,
            vector_store_attach_file=vector_store_service.attach_file,
            vector_store_delete=vector_store_service.delete_vector_store,
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
