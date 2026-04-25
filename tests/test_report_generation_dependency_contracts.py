from src.generators.report_generation_dependencies import (
    FigureCaptionDependencies,
    ReportAnalysisDependencies,
    ReportGenerationDependencies,
    ReportRenderDependencies,
    ReportSelectionDependencies,
    ReportSourceDependencies,
)


def test_report_generation_stage_dependencies_are_capability_scoped() -> None:
    source_fields = set(ReportSourceDependencies.__dataclass_fields__)
    selection_fields = set(ReportSelectionDependencies.__dataclass_fields__)
    analysis_fields = set(ReportAnalysisDependencies.__dataclass_fields__)
    render_fields = set(ReportRenderDependencies.__dataclass_fields__)
    figure_caption_fields = set(FigureCaptionDependencies.__dataclass_fields__)
    root_fields = set(ReportGenerationDependencies.__dataclass_fields__)

    assert "vector_store_create" not in source_fields
    assert "generate_evidence_packs" not in source_fields
    assert "render_report" not in source_fields

    assert "vector_store_create" not in selection_fields
    assert "generate_evidence_packs" not in selection_fields
    assert "render_report" not in selection_fields

    assert "extract_best_figure" not in analysis_fields
    assert "collect_candidates" not in analysis_fields
    assert "render_report" not in analysis_fields

    assert "extract_best_figure" not in render_fields
    assert "vector_store_create" not in render_fields
    assert "generate_evidence_packs" not in render_fields

    assert "collect_candidates" not in figure_caption_fields
    assert "vector_store_create" not in figure_caption_fields
    assert "render_report" not in figure_caption_fields

    assert root_fields == {"source", "selection", "analysis", "render"}
