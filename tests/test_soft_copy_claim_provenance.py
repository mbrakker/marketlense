from __future__ import annotations

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
        validate_references=validate_references,
    )


def test_declared_soft_copy_claims_keep_exact_evidence_and_interpretive_type() -> None:
    from src.generators.soft_copy_claim_provenance import (
        build_soft_copy_claim_provenance,
    )

    claims = build_soft_copy_claim_provenance(
        artifact_family="expert_comment",
        text=(
            "Revenue grew by 12%. This suggests leaders should protect retention "
            "investment."
        ),
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


def test_builder_resolves_varied_quotes_to_identical_retained_records() -> None:
    """Mechanical quote variance must not change the retained provenance bytes."""

    from src.generators.soft_copy_claim_provenance import (
        build_soft_copy_claim_provenance,
    )

    text = "Revenue grew by 12%. This suggests leaders should protect retention investment."
    span_index = {
        "finding-7": [
            {"evidence_id": "finding-7", "source_pack": "findings", "page": 12}
        ],
        "quote-3": [
            {"evidence_id": "quote-3", "source_pack": "quote_candidates", "page": 13}
        ],
    }
    identity = {"namespace": "report_vs/artifacts/expert_comment"}
    exact_claims = build_soft_copy_claim_provenance(
        artifact_family="expert_comment",
        text=text,
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
        evidence_span_index=span_index,
        producing_prompt_identity=identity,
        generation_attempt=1,
        regeneration_attempt=0,
    )
    varied_claims = build_soft_copy_claim_provenance(
        artifact_family="expert_comment",
        text=text,
        declared_claims=[
            {
                "claim": "revenue grew by 12%",
                "classification": "factual",
                "evidence_ids": ["finding-7"],
            },
            {
                "claim": "suggests leaders should protect retention investment",
                "classification": "interpretive",
                "evidence_ids": ["finding-7", "quote-3"],
            },
        ],
        evidence_span_index=span_index,
        producing_prompt_identity=identity,
        generation_attempt=1,
        regeneration_attempt=0,
    )
    assert [
        (claim.claim_id, claim.text_hash, claim.evidence_ids, claim.source_spans)
        for claim in exact_claims
    ] == [
        (claim.claim_id, claim.text_hash, claim.evidence_ids, claim.source_spans)
        for claim in varied_claims
    ]


def test_builder_reports_uncovered_sentences_with_actionable_context() -> None:
    from src.generators.soft_copy_claim_provenance import (
        build_soft_copy_claim_provenance,
    )

    with pytest.raises(AppError) as exc_info:
        build_soft_copy_claim_provenance(
            artifact_family="linkedin_post",
            text="Revenue grew by 12%. Leaders should protect retention investment.",
            declared_claims=[
                {
                    "claim": "Revenue grew by twelve percent.",
                    "classification": "factual",
                    "evidence_ids": ["finding-7"],
                }
            ],
            evidence_span_index={},
            producing_prompt_identity={"namespace": "linkedin"},
            generation_attempt=1,
            regeneration_attempt=0,
        )
    assert exc_info.value.code == "soft_copy_claim_provenance_bindings_incomplete"
    assert exc_info.value.context["missing_claim_count"] == 2


def test_builder_still_rejects_factual_claim_without_evidence() -> None:
    from src.generators.soft_copy_claim_provenance import (
        build_soft_copy_claim_provenance,
    )

    with pytest.raises(AppError, match="requires declared evidence IDs"):
        build_soft_copy_claim_provenance(
            artifact_family="linkedin_post",
            text="Revenue grew by 12%.",
            declared_claims=[
                {
                    "claim": "revenue grew by 12%",
                    "classification": "factual",
                    "evidence_ids": [],
                }
            ],
            evidence_span_index={},
            producing_prompt_identity={"namespace": "linkedin"},
            generation_attempt=1,
            regeneration_attempt=0,
        )


def test_ias_summary_claim_bindings_cover_uk_abbreviation_sentences() -> None:
    """The IAS canary's valid provider shape must not split ``U.K.`` in two."""
    summary = {
        "tldr": (
            "U.K. media experts prioritise digital video and display over the "
            "next 12 months."
        ),
        "card_tldr_compact": ("U.K. experts prioritise digital video and display."),
        "executive_summary": (
            "U.K. media experts prioritise digital video and display over the "
            "next 12 months."
        ),
        "claim_evidence_map": [
            {
                "claim": (
                    "U.K. media experts prioritise digital video and display "
                    "over the next 12 months."
                ),
                "evidence_id": "finding-2",
                "evidence": "Digital video and display lead the stated priorities.",
            }
        ],
    }
    claim_bindings = [
        {
            "claim": summary["tldr"],
            "classification": "factual",
            "evidence_ids": ["finding-2"],
        },
        {
            "claim": summary["card_tldr_compact"],
            "classification": "factual",
            "evidence_ids": ["finding-2"],
        },
    ]

    assert soft_copy_claim_bindings_cover_public_text(
        artifact_family="summary",
        public_output=summary,
        claim_bindings=claim_bindings,
    )


def test_retained_ias_artifact_remains_immutable_before_state_evidence() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = (
        root
        / "tests/fixtures/docpacks/golden/ias-industry-pulse-report-2026-acig-pdf"
        / "report_analysis/artifacts.json"
    )
    evidence_manifest = json.loads(
        (
            root
            / "docs/CTO_evidence/step10_ias_retained_regression_20260912_876c602c"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    artifact_bytes = artifact_path.read_bytes()
    canonical_artifact_bytes = artifact_bytes.replace(b"\r\n", b"\n")
    artifacts = json.loads(artifact_bytes)

    assert (
        sha256(canonical_artifact_bytes).hexdigest()
        == evidence_manifest["fixture"]["historical_artifacts_sha256"]
    )
    assert "soft_copy_claim_provenance" not in artifacts
    assert "retained/ias/" not in artifact_bytes.decode("utf-8")


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


def test_artifact_assembly_canonicalizes_soft_copy_aliases_before_strict_validation() -> (
    None
):
    payload = _assemble_soft_copy(
        expert_comment="Revenue grew by 12%.",
        evidence_packs={
            "findings": {
                "findings": [
                    {"id": "f1", "evidence": "Evidence context.", "pages": [1]},
                    {
                        "id": "finding-7",
                        "evidence": "Revenue grew by 12%.",
                        "pages": [12],
                    },
                    {"id": "f2", "evidence": "Planning context.", "pages": [2]},
                ]
            }
        },
        soft_copy_claim_bindings={
            "expert_comment": [
                {
                    "claim": "Revenue grew by 12%.",
                    "classification": "factual",
                    "evidence_ids": ["evidence:findings:finding-7"],
                }
            ]
        },
        validate_references=True,
    )

    claim = next(
        item
        for item in payload["soft_copy_claim_provenance"]["claims"]
        if item["artifact_family"] == "expert_comment"
    )
    assert claim["evidence_ids"] == ["finding-7"]
    assert claim["source_spans"] == [
        {
            "evidence_id": "finding-7",
            "source_pack": "findings",
            "page": 12,
            "text": "Revenue grew by 12%.",
        }
    ]


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


def test_hashtag_only_closing_line_is_not_a_material_sentence() -> None:
    from src.contracts.soft_copy_claim_provenance import (
        soft_copy_material_sentences,
        soft_copy_uncovered_sentences,
    )

    post = (
        "Advertisers are rethinking authenticity in an AI-made media world. "
        "Trust now decides attention. #AI #MediaTrust"
    )
    sentences = soft_copy_material_sentences(post)
    assert sentences == [
        "Advertisers are rethinking authenticity in an AI-made media world.",
        "Trust now decides attention.",
    ]
    declared = [
        {
            "claim": sentences[0],
            "classification": "factual",
            "evidence_ids": ["f1"],
        },
        {
            "claim": sentences[1],
            "classification": "interpretive",
            "evidence_ids": ["f2"],
        },
    ]
    assert (
        soft_copy_uncovered_sentences(
            artifact_family="linkedin_post",
            public_output=post,
            claim_bindings=declared,
        )
        == []
    )


def test_align_bindings_splits_paragraph_claims_onto_sentence_grid() -> None:
    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
        soft_copy_claim_bindings_cover_public_text,
    )

    post = "First supported point. Second supported point. Third supported point."
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[
            {
                "claim": "First supported point. Second supported point.",
                "classification": "factual",
                "evidence_ids": ["f1"],
            },
            {
                "claim": "Third supported point.",
                "classification": "interpretive",
                "evidence_ids": ["f2"],
            },
        ],
    )
    assert [binding["claim"] for binding in aligned] == [
        "First supported point.",
        "Second supported point.",
        "Third supported point.",
    ]
    assert all(binding["evidence_ids"] == ["f1"] for binding in aligned[:2])
    assert aligned[2]["evidence_ids"] == ["f2"]
    assert aligned[2]["classification"] == "interpretive"
    assert soft_copy_claim_bindings_cover_public_text(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=aligned,
    )


def test_align_bindings_keeps_exact_and_unmatched_bindings() -> None:
    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
    )

    post = "Exact sentence here. Unrelated off-grid model phrasing about weather."
    exact_binding = {
        "claim": "Exact sentence here.",
        "classification": "factual",
        "evidence_ids": ["f1"],
    }
    unmatched_binding = {
        "claim": "The forecast looks cloudy for marketers worldwide.",
        "classification": "interpretive",
        "evidence_ids": ["f2"],
    }
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[exact_binding, unmatched_binding],
    )
    assert aligned[0] == exact_binding
    assert aligned[1] == unmatched_binding


def test_align_bindings_resolves_punctuation_and_case_variance() -> None:
    """Mechanically equivalent quotes bind without a model repair attempt."""

    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
        soft_copy_claim_bindings_cover_public_text,
    )

    post = (
        "Marketers plan to raise budgets by 12% in 2026. Leaders remain "
        "cautious about attribution spend."
    )
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[
            {
                "claim": "marketers plan to raise budgets by 12% in 2026",
                "classification": "factual",
                "evidence_ids": ["f1"],
            },
            {
                "claim": "Leaders remain cautious about attribution spend",
                "classification": "interpretive",
                "evidence_ids": ["f2"],
            },
        ],
    )
    assert [binding["claim"] for binding in aligned] == [
        "Marketers plan to raise budgets by 12% in 2026.",
        "Leaders remain cautious about attribution spend.",
    ]
    assert soft_copy_claim_bindings_cover_public_text(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=aligned,
    )


def test_align_bindings_resolves_quoted_clause_within_unique_sentence() -> None:
    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
        soft_copy_uncovered_sentences,
    )

    post = (
        "Retail media networks now capture the majority of new brand budgets "
        "across every measured region this year."
    )
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[
            {
                "claim": "Retail media networks now capture",
                "classification": "factual",
                "evidence_ids": ["f1"],
            }
        ],
    )
    assert [binding["claim"] for binding in aligned] == [
        post,
    ]
    assert (
        soft_copy_uncovered_sentences(
            artifact_family="linkedin_post",
            public_output=post,
            claim_bindings=aligned,
        )
        == []
    )


def test_align_bindings_resolves_sentence_quoted_with_extra_words() -> None:
    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
    )

    post = "Attribution windows keep shrinking for performance teams."
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[
            {
                "claim": (
                    "Key insight: attribution windows keep shrinking for "
                    "performance teams overall"
                ),
                "classification": "interpretive",
                "evidence_ids": ["f2"],
            }
        ],
    )
    assert [binding["claim"] for binding in aligned] == [post]
    assert aligned[0]["evidence_ids"] == ["f2"]


def test_align_bindings_leaves_ambiguous_clause_unmatched() -> None:
    """An ambiguous quote stays unmatched so coverage still fails closed."""

    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
        soft_copy_uncovered_sentences,
    )

    post = "First generic growth signal appeared early. Second generic growth signal appeared late."
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[
            {
                "claim": "generic growth signal appeared",
                "classification": "factual",
                "evidence_ids": ["f1"],
            }
        ],
    )
    assert (
        soft_copy_uncovered_sentences(
            artifact_family="linkedin_post",
            public_output=post,
            claim_bindings=aligned,
        )
        != []
    )


def test_align_bindings_drops_noise_once_coverage_is_complete() -> None:
    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
        soft_copy_claim_bindings_cover_public_text,
    )

    post = "Exact sentence here."
    exact_binding = {
        "claim": "Exact sentence here.",
        "classification": "factual",
        "evidence_ids": ["f1"],
    }
    stray_binding = {
        "claim": "stray model noise",
        "classification": "interpretive",
        "evidence_ids": [],
    }
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[exact_binding, stray_binding],
    )
    assert aligned == [exact_binding]
    assert soft_copy_claim_bindings_cover_public_text(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=aligned,
    )


def test_align_bindings_dedupes_sentences_keeping_first_declaration() -> None:
    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
    )

    post = "Repeated sentence here."
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[
            {
                "claim": "Repeated sentence here.",
                "classification": "factual",
                "evidence_ids": ["f1"],
            },
            {
                "claim": "Repeated sentence here.",
                "classification": "interpretive",
                "evidence_ids": ["f2"],
            },
        ],
    )
    assert len(aligned) == 1
    assert aligned[0]["evidence_ids"] == ["f1"]
