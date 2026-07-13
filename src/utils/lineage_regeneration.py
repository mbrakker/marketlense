"""Pure compatibility policy for minimum safe checkpoint regeneration."""

from __future__ import annotations

from src.contracts.regeneration import LineageRegenerationPlan
from src.utils.errors import AppError

_PLANS: dict[str, tuple[str, bool, list[str], list[str], list[str]]] = {
    "source": (
        "",
        True,
        [],
        [
            "source_prepared",
            "selection_complete",
            "analysis_complete",
            "render_complete",
        ],
        [],
    ),
    "prompt": (
        "selection_complete",
        False,
        ["source_prepared", "selection_complete"],
        ["analysis_complete", "render_complete"],
        ["pdf_text", "ocr", "candidate_extraction", "crop_rendering"],
    ),
    "template": (
        "analysis_complete",
        False,
        ["source_prepared", "selection_complete", "analysis_complete"],
        ["render_complete"],
        [
            "pdf_text",
            "ocr",
            "candidate_extraction",
            "crop_rendering",
            "model_generation",
        ],
    ),
    "crop": (
        "source_prepared",
        False,
        ["source_prepared"],
        ["selection_complete", "analysis_complete", "render_complete"],
        ["pdf_text", "ocr"],
    ),
    "validator": (
        "selection_complete",
        False,
        ["source_prepared", "selection_complete"],
        ["analysis_complete", "render_complete"],
        ["pdf_text", "ocr", "candidate_extraction", "crop_rendering"],
    ),
}


def plan_lineage_regeneration(
    *, change_kind: str, lineage_available: bool
) -> LineageRegenerationPlan:
    normalized_kind = str(change_kind or "").strip().lower()
    if normalized_kind not in _PLANS:
        raise AppError(
            code="lineage_regeneration_change_kind_invalid",
            message="Lineage regeneration requires a supported change kind",
            retryable=False,
            context={"change_kind": normalized_kind},
        )
    if not lineage_available:
        raise AppError(
            code="lineage_regeneration_lineage_missing",
            message="Selective regeneration requires complete valid artifact lineage",
            retryable=False,
            context={"change_kind": normalized_kind},
        )
    (
        resume_from_stage,
        full_regeneration_required,
        reused,
        regenerated,
        avoided,
    ) = _PLANS[normalized_kind]
    return LineageRegenerationPlan(
        schema_version="1.0",
        change_kind=normalized_kind,
        resume_from_stage=resume_from_stage,
        full_regeneration_required=full_regeneration_required,
        reused_stages=list(reused),
        regenerated_stages=list(regenerated),
        avoided_work=list(avoided),
    )


__all__ = ["plan_lineage_regeneration"]
