# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_soft_copy_claim_provenance.py"
)

import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import pytest
from src.contracts.files import (
    PipelineCheckpointReadRequest,
    PipelineCheckpointWriteRequest,
    PipelineStageCheckpoint,
)
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_bindings_cover_public_text,
    soft_copy_claim_provenance_from_payload,
    soft_copy_claim_provenance_to_payload,
)
from src.generators._artifact_generator.family_policy import (
    build_artifact_family_status,
)
from src.generators._artifact_generator.storage import assemble_artifacts_payload
from src.utils.errors import AppError


def _assemble_soft_copy(
    *,
    summary: dict[str, object] | None = None,
    expert_comment: str = "",
    linkedin_post: str = "",
    evidence_packs: dict[str, object] | None = None,
    insights_final: list[dict[str, object]] | None = None,
    doc_map: dict[str, object] | None = None,
    soft_copy_claim_bindings: dict[str, list[dict[str, object]]] | None = None,
    existing_soft_copy_claim_provenance: dict[str, object] | None = None,
    replaced_soft_copy_claim_ids: dict[str, list[str]] | None = None,
    soft_copy_repair_texts: dict[str, list[str]] | None = None,
    validate_references: bool = False,
) -> dict[str, object]:
    """Exercise the canonical artifact assembly boundary with no claim bindings."""
    resolved_summary = summary or {"claim_evidence_map": []}
    family_status = build_artifact_family_status(
        summary=resolved_summary,
        insights_candidates=[],
        insights_final=insights_final or [],
        quotes_final=[],
        expert_comment=expert_comment,
        linkedin_post=linkedin_post,
    )
    return assemble_artifacts_payload(
        report_id="soft-copy-provenance",
        report_name="Soft copy provenance",
        doc_map=doc_map or {"sections": []},
        evidence_packs=evidence_packs or {},
        toc_bundle={"toc_entries": []},
        editorial_plan={
            "report_thesis": "Retained evidence governs copy.",
            "themes": [
                {"theme": "Evidence", "priority": 1, "evidence_ids": ["f1"]},
                {"theme": "Planning", "priority": 2, "evidence_ids": ["f2"]},
            ],
        },
        summary=resolved_summary,
        cover_semantics={
            "evidence_shape": "trend",
            "direction": "rising",
            "geography_scope": "global",
            "evidence_density": "metric_rich",
            "domain_layer": "grid",
            "selection_reason": "Evidence supports the retained output.",
        },
        insights_candidates=[],
        insights_final=insights_final or [],
        quotes_final=[],
        expert_comment=expert_comment,
        linkedin_post=linkedin_post,
        source_status={"not_available": False, "reason": ""},
        family_status=family_status,
        ctx=RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
        soft_copy_claim_bindings=soft_copy_claim_bindings,
        existing_soft_copy_claim_provenance=existing_soft_copy_claim_provenance,
        replaced_soft_copy_claim_ids=replaced_soft_copy_claim_ids,
        soft_copy_repair_texts=soft_copy_repair_texts,
        validate_references=validate_references,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
