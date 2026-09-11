from __future__ import annotations

from dataclasses import asdict

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
) -> dict[str, object]:
    """Exercise the canonical artifact assembly boundary with no claim bindings."""
    resolved_summary = summary or {"claim_evidence_map": []}
    family_status = build_artifact_family_status(
        summary=resolved_summary,
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        expert_comment=expert_comment,
        linkedin_post=linkedin_post,
    )
    return assemble_artifacts_payload(
        report_id="soft-copy-provenance",
        report_name="Soft copy provenance",
        doc_map={"sections": []},
        evidence_packs={},
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
        insights_final=[],
        quotes_final=[],
        expert_comment=expert_comment,
        linkedin_post=linkedin_post,
        source_status={"not_available": False, "reason": ""},
        family_status=family_status,
        ctx=RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
        validate_references=False,
    )


def test_declared_soft_copy_claims_keep_exact_evidence_and_interpretive_type() -> None:
    from src.generators.soft_copy_claim_provenance import (
        build_soft_copy_claim_provenance,
    )

    claims = build_soft_copy_claim_provenance(
        artifact_family="expert_comment",
        text="Revenue grew by 12%. This suggests leaders should protect retention investment.",
        declared_claims=[
            {
                "claim": "Revenue grew by 12%.",
                "classification": "factual",
                "evidence_ids": ["finding-7"],
            },
            {
                "claim": "This suggests leaders should protect retention investment.",
                "classification": "interpretive",
                "evidence_ids": ["finding-7", "quote-3"],
            },
        ],
        evidence_span_index={
            "finding-7": [
                {
                    "evidence_id": "finding-7",
                    "source_pack": "findings",
                    "page": 12,
                    "start_offset": 44,
                    "end_offset": 91,
                }
            ],
            "quote-3": [
                {
                    "evidence_id": "quote-3",
                    "source_pack": "quote_candidates",
                    "page": 13,
                }
            ],
        },
        producing_prompt_identity={
            "namespace": "report_vs/artifacts/expert_comment",
            "prompt_content_hash": "b" * 64,
        },
        generation_attempt=1,
        regeneration_attempt=0,
    )

    assert claims[0].evidence_ids == ("finding-7",)
    assert claims[0].source_spans[0]["page"] == 12
    assert claims[1].classification == "interpretive"
    assert claims[1].evidence_ids == ("finding-7", "quote-3")


def test_material_soft_copy_sentence_without_declared_binding_is_rejected() -> None:
    from src.generators.soft_copy_claim_provenance import (
        build_soft_copy_claim_provenance,
    )

    with pytest.raises(AppError, match="every material sentence"):
        build_soft_copy_claim_provenance(
            artifact_family="linkedin_post",
            text="Revenue grew by 12%. Leaders should protect retention investment.",
            declared_claims=[
                {
                    "claim": "Revenue grew by 12%.",
                    "classification": "factual",
                    "evidence_ids": ["finding-7"],
                }
            ],
            evidence_span_index={},
            producing_prompt_identity={"namespace": "linkedin"},
            generation_attempt=1,
            regeneration_attempt=0,
        )


@pytest.mark.parametrize(
    ("summary", "expert_comment", "linkedin_post"),
    [
        (None, "Expert guidance relies on retained evidence.", ""),
        (None, "", "LinkedIn guidance relies on retained evidence."),
        (
            {
                "tldr": "The retained evidence changes the planning outlook.",
                "card_tldr_compact": "Evidence changes planning.",
                "executive_summary": "Leaders should act on the retained evidence.",
                "claim_evidence_map": [],
            },
            "",
            "",
        ),
    ],
)
def test_artifact_assembly_rejects_material_soft_copy_without_bindings(
    summary: dict[str, object] | None,
    expert_comment: str,
    linkedin_post: str,
) -> None:
    """Removing the fail-closed branch must make this assertion fail."""
    with pytest.raises(AppError) as captured:
        _assemble_soft_copy(
            summary=summary,
            expert_comment=expert_comment,
            linkedin_post=linkedin_post,
        )

    assert captured.value.code == "soft_copy_claim_provenance_bindings_missing"


def test_artifact_assembly_allows_empty_soft_copy_without_claims() -> None:
    payload = _assemble_soft_copy()

    assert payload["soft_copy_claim_provenance"] == {
        "schema_version": "1.0",
        "claims": [],
    }


def test_soft_copy_claim_provenance_round_trips_exact_evidence_and_source_span() -> (
    None
):
    claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:1a2b3c4d",
        text_hash="a" * 64,
        classification="factual",
        evidence_ids=("finding-7", "quote-3"),
        source_spans=(
            {
                "evidence_id": "finding-7",
                "source_pack": "findings",
                "page": 12,
                "start_offset": 44,
                "end_offset": 91,
            },
        ),
        producing_prompt_identity={
            "namespace": "report_vs/artifacts/expert_comment",
            "prompt_content_hash": "b" * 64,
        },
        generation_attempt=1,
        regeneration_attempt=0,
        repaired_from_claim_id="soft_copy:expert_comment:original",
    )

    payload = soft_copy_claim_provenance_to_payload([claim])

    assert payload["claims"][0]["evidence_ids"] == ["finding-7", "quote-3"]
    assert payload["claims"][0]["repaired_from_claim_id"] == (
        "soft_copy:expert_comment:original"
    )
    assert soft_copy_claim_provenance_from_payload(payload) == [claim]


def test_soft_copy_claim_provenance_rejects_unknown_classification() -> None:
    with pytest.raises(AppError, match="classification"):
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="linkedin_post",
            claim_id="soft_copy:linkedin_post:1a2b3c4d",
            text_hash="a" * 64,
            classification="unsupported",
            evidence_ids=(),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/linkedin_post"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        ).validate()


def test_checkpoint_round_trip_preserves_private_soft_copy_provenance(tmp_path) -> None:
    from src.services.file_service import (
        read_pipeline_checkpoint,
        write_pipeline_checkpoint,
    )

    provenance = soft_copy_claim_provenance_to_payload(
        [
            SoftCopyClaimProvenance(
                schema_version="1.0",
                artifact_family="expert_comment",
                claim_id="soft_copy:expert_comment:1a2b3c4d",
                text_hash="a" * 64,
                classification="factual",
                evidence_ids=("finding-7",),
                source_spans=({"evidence_id": "finding-7", "page": 12},),
                producing_prompt_identity={"namespace": "expert"},
                generation_attempt=1,
                regeneration_attempt=0,
            )
        ]
    )
    checkpoint = PipelineStageCheckpoint(
        schema_version="1.0",
        pipeline_name="report_generation",
        file_id="file-1",
        report_slug="report-1",
        stage_name="analysis_complete",
        stage_status="completed",
        artifact_refs={},
        payload={
            "analysis": {
                "artifacts_payload": {"soft_copy_claim_provenance": provenance}
            }
        },
        completed_at_utc="2026-09-11T00:00:00+00:00",
        source_run_id="run-1",
        source_task_id="task-1",
    )
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

    write_pipeline_checkpoint(
        PipelineCheckpointWriteRequest(
            schema_version="1.0", checkpoint_root=str(tmp_path), checkpoint=checkpoint
        ),
        ctx,
    )
    restored = read_pipeline_checkpoint(
        PipelineCheckpointReadRequest(
            schema_version="1.0",
            checkpoint_root=str(tmp_path),
            pipeline_name="report_generation",
            file_id="file-1",
            stage_name="analysis_complete",
        ),
        ctx,
    )

    assert restored.checkpoint is not None
    assert restored.checkpoint.payload == checkpoint.payload


def test_public_report_payload_excludes_private_soft_copy_provenance() -> None:
    from src.generators.report_generation_shared import merge_artifacts_into_payload

    payload = ReportPayload(
        tldr="",
        title="Report",
        insights=[],
        quote=Quote(text=""),
        figure=Figure(title="", evidence=""),
        commentary="",
        source="",
    )
    public_payload = merge_artifacts_into_payload(
        payload,
        {
            "summary": {
                "tldr": "Public summary.",
                "executive_summary": "Public prose.",
            },
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    {"claim_id": "internal-only", "evidence_ids": ["finding-7"]}
                    | {"repaired_from_claim_id": "soft_copy:expert_comment:old"}
                ],
            },
            "_repair_evidence_selection": {
                "expert_comment:internal-only": {
                    "claim_id": "internal-only",
                    "selected_evidence_ids": ["finding-8"],
                }
            },
        },
    )

    assert "soft_copy_claim_provenance" not in asdict(public_payload)
    assert "finding-7" not in str(asdict(public_payload))
    assert "soft_copy:expert_comment:old" not in str(asdict(public_payload))
    assert "_repair_evidence_selection" not in asdict(public_payload)
    assert "finding-8" not in str(asdict(public_payload))
