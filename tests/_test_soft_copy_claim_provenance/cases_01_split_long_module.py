# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_soft_copy_claim_provenance.py"
)

from ._split_support_test_soft_copy_claim_provenance import *  # noqa: F401,F403


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
    assert "linkedin_post" in exc_info.value.message


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


def test_repaired_summary_recovers_only_exact_direct_claim_map_bindings() -> None:
    sentences = [
        "The report identifies digital media trends.",
        "Advertisers report short video adoption.",
        "Leaders track channel performance.",
    ]
    summary = {
        "tldr": sentences[0],
        "card_tldr_compact": sentences[1],
        "executive_summary": sentences[2],
        "claim_evidence_map": [
            {
                "claim": sentence,
                "evidence_id": f"finding-{index}",
                "evidence": sentence,
            }
            for index, sentence in enumerate(sentences, start=1)
        ],
    }
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": f"finding-{index}",
                    "evidence": sentence,
                    "pages": [index],
                }
                for index, sentence in enumerate(sentences, start=1)
            ]
        }
    }

    payload = _assemble_soft_copy(
        summary=summary,
        evidence_packs=evidence_packs,
        soft_copy_claim_bindings={
            "summary": [
                {
                    "claim": sentences[0],
                    "classification": "factual",
                    "evidence_ids": ["finding-1"],
                }
            ]
        },
        soft_copy_repair_texts={"summary": [" ".join(sentences)]},
    )

    retained = [
        claim
        for claim in payload["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "summary"
    ]
    assert [claim["text_hash"] for claim in retained] == [
        sha256(sentence.encode("utf-8")).hexdigest() for sentence in sentences
    ]
    assert [claim["evidence_ids"] for claim in retained] == [
        [f"finding-{index}"] for index in range(1, 4)
    ]
    assert [claim["source_spans"][0]["page"] for claim in retained] == [1, 2, 3]


def test_repaired_summary_does_not_infer_binding_from_paraphrased_direct_claim() -> (
    None
):
    with pytest.raises(AppError) as captured:
        _assemble_soft_copy(
            summary={
                "tldr": "The report identifies digital media trends.",
                "card_tldr_compact": "The report identifies digital media trends.",
                "executive_summary": "The report identifies digital media trends.",
                "claim_evidence_map": [
                    {
                        "claim": "The report identifies media trends.",
                        "evidence_id": "finding-1",
                        "evidence": "The report identifies media trends.",
                    }
                ],
            },
            evidence_packs={
                "findings": {
                    "findings": [
                        {
                            "id": "finding-1",
                            "evidence": "The report identifies media trends.",
                            "pages": [1],
                        }
                    ]
                }
            },
            soft_copy_repair_texts={
                "summary": ["The report identifies digital media trends."]
            },
        )

    assert captured.value.code == "soft_copy_claim_provenance_bindings_incomplete"


def test_repaired_summary_does_not_choose_between_direct_claim_evidence_rows() -> None:
    sentence = "The report identifies digital media trends."
    with pytest.raises(AppError) as captured:
        _assemble_soft_copy(
            summary={
                "tldr": sentence,
                "card_tldr_compact": sentence,
                "executive_summary": sentence,
                "claim_evidence_map": [
                    {
                        "claim": sentence,
                        "evidence_id": "finding-1",
                        "evidence": "Digital media trends appear in the report.",
                    },
                    {
                        "claim": sentence,
                        "evidence_id": "finding-2",
                        "evidence": "The report also covers digital media trends.",
                    },
                ],
            },
            evidence_packs={
                "findings": {
                    "findings": [
                        {
                            "id": "finding-1",
                            "evidence": "Digital media trends appear in the report.",
                            "pages": [1],
                        },
                        {
                            "id": "finding-2",
                            "evidence": "The report also covers digital media trends.",
                            "pages": [2],
                        },
                    ]
                }
            },
            soft_copy_repair_texts={"summary": [sentence]},
        )

    assert captured.value.code == "soft_copy_claim_provenance_bindings_incomplete"


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
