# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_report_regeneration_generator.py"
)

from ._split_support_test_report_regeneration_generator import *  # noqa: F401,F403


def test_regeneration_repairs_multiple_exact_claim_ids_without_churning_siblings(
    tmp_path,
) -> None:
    """Two precise failures are repaired independently and reconstructed in place."""
    current_artifacts = _current_artifacts()
    sentences = [
        "First sibling remains byte-identical.",
        "Bad second claim.",
        "Bad third claim.",
        "Last sibling remains byte-identical.",
    ]
    original_text = "  ".join(sentences)
    current_artifacts["expert_comment"] = original_text
    original_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:multi:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(original_claims)["claims"]
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].extend(
        [
            {"id": "f3", "evidence": "Third supported evidence."},
            {"id": "f4", "evidence": "Fourth supported evidence."},
        ]
    )
    openai_client = _MultiClaimScopedExpertOpenAIClient()

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported second claim.",
                                severity="error",
                                entity_id=original_claims[1].claim_id,
                                evidence_ids=["f2"],
                            ),
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported third claim.",
                                severity="error",
                                entity_id=original_claims[2].claim_id,
                                evidence_ids=["f3"],
                            ),
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["expert_comment"] == (
        "First sibling remains byte-identical.  Repaired second claim.  "
        "Repaired third claim.  Last sibling remains byte-identical."
    )
    assert len(openai_client.calls) == 2
    by_id = {
        claim["claim_id"]
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "expert_comment"
    }
    assert original_claims[0].claim_id in by_id
    assert original_claims[3].claim_id in by_id
    assert original_claims[1].claim_id not in by_id
    assert original_claims[2].claim_id not in by_id
    repaired_claims = [
        SoftCopyClaimProvenance(
            schema_version=item["schema_version"],
            artifact_family=item["artifact_family"],
            claim_id=item["claim_id"],
            text_hash=item["text_hash"],
            classification=item["classification"],
            evidence_ids=tuple(item["evidence_ids"]),
            source_spans=tuple(item["source_spans"]),
            producing_prompt_identity=item["producing_prompt_identity"],
            generation_attempt=item["generation_attempt"],
            regeneration_attempt=item["regeneration_attempt"],
        )
        for item in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
        if item["artifact_family"] == "expert_comment"
    ]
    assert retained_soft_copy_claims_cover_text(
        text=response.updated_artifacts["expert_comment"], claims=repaired_claims
    )


def test_multi_claim_regeneration_repairs_supported_claim_and_abstains_unsupported_one(
    tmp_path,
) -> None:
    sentences = [
        "First sibling.",
        "Bad second claim.",
        "Bad third claim.",
        "Last sibling.",
    ]
    current_artifacts = _current_artifacts()
    current_artifacts["expert_comment"] = " ".join(sentences)
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:mixed:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(claims)["claims"]
    evidence_packs = _evidence_packs()
    openai_client = _MultiClaimScopedExpertOpenAIClient()

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported second claim.",
                                severity="error",
                                entity_id=claims[1].claim_id,
                                evidence_ids=["f2"],
                            ),
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported third claim.",
                                severity="error",
                                entity_id=claims[2].claim_id,
                                evidence_ids=["f3"],
                            ),
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["expert_comment"] == (
        "First sibling. Repaired second claim. Last sibling."
    )
    assert len(openai_client.calls) == 1
    provenance_ids = {
        claim["claim_id"]
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    }
    assert claims[0].claim_id in provenance_ids
    assert claims[3].claim_id in provenance_ids
    assert claims[2].claim_id not in provenance_ids


def test_multi_claim_repair_keeps_quarantine_scoped_to_its_failed_claim(
    tmp_path,
) -> None:
    current_artifacts = _current_artifacts()
    sentences = ["Bad first claim.", "Bad second claim."]
    current_artifacts["expert_comment"] = " ".join(sentences)
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:quarantine:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(claims)["claims"]
    evidence_packs = _evidence_packs()

    prompt_client = _FakePromptClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported first claim.",
                                severity="error",
                                entity_id=claims[0].claim_id,
                                evidence_ids=["f1"],
                                excluded_evidence_ids=["f1"],
                            ),
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported second claim.",
                                severity="error",
                                entity_id=claims[1].claim_id,
                                evidence_ids=["f2"],
                            ),
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=_MultiClaimScopedExpertOpenAIClient(),
        prompt_client=prompt_client,
    )

    selections = response.updated_artifacts["_repair_evidence_selection"]
    first = selections[f"expert_comment:{claims[0].claim_id}"]
    second = selections[f"expert_comment:{claims[1].claim_id}"]
    assert first["selected_evidence_ids"] == []
    assert first["quarantined_evidence_ids"] == ["f1"]
    assert second["selected_evidence_ids"] == ["f2"]
    assert second["quarantined_evidence_ids"] == []
    scoped_prompt = next(
        call
        for call in prompt_client.render_calls
        if call["path"] == "report_vs/artifacts/regenerate/expert_comment/user.yaml"
    )
    assert (
        json.loads(scoped_prompt["variables"]["grounding_package_json"])[
            "quarantined_evidence_ids"
        ]
        == []
    )
    assert response.updated_artifacts["expert_comment"] == "Repaired second claim."


def test_sequential_claim_repairs_preserve_prior_selection_provenance(tmp_path) -> None:
    current_artifacts = _current_artifacts()
    sentences = [
        "First bad claim.",
        "Second bad claim.",
        "Third retained sibling.",
    ]
    current_artifacts["expert_comment"] = " ".join(sentences)
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:sequential:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(claims)["claims"]
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].append(
        {"id": "f3", "evidence": "Third repair evidence."}
    )
    openai_client = _MultiClaimScopedExpertOpenAIClient()

    def repair(artifacts: dict, claim: SoftCopyClaimProvenance, attempt: int):
        return regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=attempt,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[
                        RegenerationTarget(
                            target_section="expert_comment",
                            regenerate_steps=["expert_comment"],
                            issues=[
                                RegenerationIssue(
                                    rule_id="grounding",
                                    affected_section="expert_comment",
                                    message="Unsupported claim.",
                                    severity="error",
                                    entity_id=claim.claim_id,
                                    evidence_ids=list(claim.evidence_ids),
                                )
                            ],
                        )
                    ],
                    unmappable_issues=[],
                    broad_retry_allowed=False,
                ),
                current_artifacts=artifacts,
                doc_map=evidence_packs["doc_map"],
                evidence_packs=evidence_packs,
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=artifacts["source_status"],
                categories=["Category"],
            ),
            openai_client=openai_client,
            prompt_client=_FakePromptClient(),
        )

    first = repair(current_artifacts, claims[0], 1)
    first_selection = first.updated_artifacts["_repair_evidence_selection"][
        f"expert_comment:{claims[0].claim_id}"
    ]
    second = repair(first.updated_artifacts, claims[1], 2)

    selections = second.updated_artifacts["_repair_evidence_selection"]
    assert selections[f"expert_comment:{claims[0].claim_id}"] == first_selection
    assert selections[f"expert_comment:{claims[1].claim_id}"][
        "selected_evidence_ids"
    ] == ["f2"]


@pytest.mark.parametrize(
    ("family", "section", "expected", "field"),
    [
        (
            "linkedin_post",
            "linkedin_post",
            (
                "First linkedin_post claim. Repaired LinkedIn claim. "
                "Last linkedin_post claim."
            ),
            None,
        ),
        (
            "summary",
            "summary.executive_summary",
            "First summary claim. Repaired summary claim. Last summary claim.",
            "executive_summary",
        ),
    ],
)
def test_regeneration_claim_scope_preserves_unrelated_soft_copy_on_repeat(
    tmp_path, family: str, section: str, expected: str, field: str | None
) -> None:
    """A repeated isolated failure must not churn sibling copy or its provenance."""
    current_artifacts = _current_artifacts()
    sentences = [
        f"First {family} claim.",
        f"Bad {family} claim.",
        f"Last {family} claim.",
    ]
    if field is None:
        current_artifacts[family] = " ".join(sentences)
    else:
        current_artifacts["summary"][field] = " ".join(sentences)
    original_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family=family,
            claim_id=f"soft_copy:{family}:repeat:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=(),
            producing_prompt_identity={"namespace": f"report_vs/artifacts/{family}"},
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != family
    ] + (
        [
            claim
            for claim in _current_artifacts()["soft_copy_claim_provenance"]["claims"]
            if family == "summary"
            and claim["artifact_family"] == "summary"
            and claim["text_hash"] == hashlib.sha256(b"Old TLDR.").hexdigest()
        ]
        + soft_copy_claim_provenance_to_payload(original_claims)["claims"]
    )
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].append(
        {"id": "f3", "evidence": "Last supported evidence."}
    )

    def regenerate(current: dict, attempt_index: int):
        return regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=attempt_index,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[
                        RegenerationTarget(
                            target_section=family,
                            regenerate_steps=[family],
                            issues=[
                                RegenerationIssue(
                                    rule_id="grounding",
                                    affected_section=section,
                                    message="Unsupported middle claim.",
                                    severity="error",
                                    evidence_ids=["f2"],
                                )
                            ],
                        )
                    ],
                    unmappable_issues=[],
                    broad_retry_allowed=False,
                ),
                current_artifacts=current,
                doc_map=evidence_packs["doc_map"],
                evidence_packs=evidence_packs,
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=current["source_status"],
                categories=["Category"],
            ),
            openai_client=_ClaimScopedSoftCopyOpenAIClient(),
            prompt_client=_FakePromptClient(),
        )

    first = regenerate(current_artifacts, 1)
    second = regenerate(first.updated_artifacts, 2)
    value = (
        second.updated_artifacts[family]
        if field is None
        else second.updated_artifacts["summary"][field]
    )
    assert value == expected
    claims = {
        claim["claim_id"]: claim
        for claim in second.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    }
    for claim in (original_claims[0], original_claims[2]):
        assert (
            claims[claim.claim_id]
            == soft_copy_claim_provenance_to_payload([claim])["claims"][0]
        )
    first_claims = {
        claim["claim_id"]: claim
        for claim in first.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    }
    repaired = next(
        claim
        for claim in first_claims.values()
        if claim.get("repaired_from_claim_id") == original_claims[1].claim_id
    )
    selection = first.updated_artifacts["_repair_evidence_selection"][
        f"{family}:{original_claims[1].claim_id}"
    ]
    assert selection["repaired_claim_id"] == repaired["claim_id"]


def test_regenerate_artifacts_summary_only_keeps_other_sections_unchanged(tmp_path):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="summary",
                        regenerate_steps=["summary"],
                        prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="executive_summary",
                                message="[grounding] Unsupported summary claim",
                                severity="error",
                                evidence_ids=["f1"],
                                pages=[1],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
            ),
            current_artifacts=_current_artifacts(),
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=_current_artifacts()["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == ["summary"]
    assert (
        response.updated_artifacts["summary"]["executive_summary"]
        == "Repaired executive summary"
    )
    assert response.updated_artifacts["summary"]["tldr"] == "Old TLDR."
    assert response.updated_artifacts["summary"]["card_tldr_compact"] == "Old TLDR."
    assert (
        response.updated_artifacts["insights_final"][0]["text"] == "Old final insight"
    )
    assert response.updated_artifacts["quotes_final"][0]["text"] == "Old quote"
