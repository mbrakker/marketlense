# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_artifact_normalization.py"
)

from copy import deepcopy
import pytest
from src.contracts.artifact_generation import ArtifactRenderTask
from src.contracts.run_context import RunContext
from src.generators._artifact_generator.family_policy import (
    build_artifact_family_status,
)
from src.generators._artifact_generator.generation import (
    _render_insights_candidates_or_defer_to_fallback,
)
from src.generators.artifact_normalization import (
    bind_artifact_evidence_spans,
    carry_soft_copy_binding_semantics_to_final_sentences,
    fallback_artifact_insights_from_evidence,
    fallback_artifact_insights_from_findings,
    normalize_artifact_insights,
    normalize_artifact_summary,
    preserve_public_source_displays,
    select_artifact_insights,
    strip_linkedin_inline_reference_ids,
)
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
)
from src.services.schema_validator_service import validate_output_schema
from src.utils.errors import AppError
from src.utils.structured_output import StructuredOutputFailure


__all__ = [name for name in globals() if not name.startswith("__")]
