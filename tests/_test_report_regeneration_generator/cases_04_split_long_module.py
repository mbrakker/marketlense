# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_report_regeneration_generator.py"
)

from ._split_support_test_report_regeneration_generator import *  # noqa: F401,F403


def test_regenerate_artifacts_dispatches_summary_via_target_section_registry(tmp_path):
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
                        prompt_namespaces=["report_vs/artifacts/regenerate/wrong"],
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
    assert response.prompt_namespaces == ["report_vs/artifacts/regenerate/summary"]
    assert [call["path"] for call in prompt_client.render_calls] == [
        "report_vs/artifacts/regenerate/summary/system.yaml",
        "report_vs/artifacts/regenerate/summary/user.yaml",
    ]


def test_regenerate_artifacts_refreshes_cover_semantics_from_retained_analysis(
    tmp_path,
):
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
                        target_section="cover_semantics",
                        regenerate_steps=["cover_semantics"],
                        prompt_namespaces=["report_vs/artifacts/cover_semantics"],
                        issues=[],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
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

    assert response.regenerated_sections == ["cover_semantics"]
    assert response.updated_artifacts["cover_semantics"]["selection_reason"] == (
        "A rising time series is the strongest visual story."
    )
    assert response.prompt_namespaces == ["report_vs/artifacts/cover_semantics"]


def test_regenerate_artifacts_expert_comment_uses_grounded_synthesis_context(
    tmp_path,
):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    current_artifacts = _current_artifacts()
    next(
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "expert_comment"
    )["evidence_ids"] = ["f1"]
    _append_retained_soft_copy_sibling(current_artifacts, "expert_comment")
    current_artifacts["insights_final"][0]["so_what"] = (
        "The primary finding changes the operating tradeoff."
    )
    current_artifacts["insights_final"][1]["coverage_role"] = "counter_signal"
    evidence_packs = _evidence_packs()
    evidence_packs["limitations"] = {
        "limitations": [
            {
                "description": "The report does not compare segments.",
                "evidence_id": "f1",
            }
        ]
    }

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        prompt_namespaces=[
                            "report_vs/artifacts/regenerate/expert_comment"
                        ],
                        issues=[],
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
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.prompt_namespaces == [
        "report_vs/artifacts/regenerate/expert_comment"
    ]
    variables = prompt_client.render_calls[0]["variables"]
    assert "summary_json" not in variables
    context = json.loads(variables["expert_synthesis_context_json"])
    assert [theme["theme"] for theme in context["themes"]] == ["Primary evidence"]
    assert context["insight_implications"] == [
        {
            "evidence_id": "f1",
            "so_what": "The primary finding changes the operating tradeoff.",
        }
    ]
    assert context["limitations"] == [
        {"evidence_id": "f1", "text": "The report does not compare segments."}
    ]


def test_regenerate_artifacts_linkedin_post_receives_editorial_plan(tmp_path):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    current_artifacts = _current_artifacts()
    next(
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "linkedin_post"
    )["evidence_ids"] = ["f1"]
    _append_retained_soft_copy_sibling(current_artifacts, "linkedin_post")

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="linkedin_post",
                        regenerate_steps=["linkedin_post"],
                        prompt_namespaces=[
                            "report_vs/artifacts/regenerate/linkedin_post"
                        ],
                        issues=[],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.prompt_namespaces == [
        "report_vs/artifacts/regenerate/linkedin_post"
    ]
    assert json.loads(
        prompt_client.render_calls[0]["variables"]["editorial_plan_json"]
    ) == {
        "report_thesis": "The report's retained evidence changes planning.",
        "themes": [
            {"theme": "Primary evidence", "priority": 1, "evidence_ids": ["f1"]}
        ],
    }


def test_regenerated_soft_copy_claim_gets_new_provenance_and_untouched_claim_is_retained(
    tmp_path,
) -> None:
    current_artifacts = _current_artifacts()
    next(
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "expert_comment"
    )["evidence_ids"] = ["f1"]
    _append_retained_soft_copy_sibling(current_artifacts, "expert_comment")
    retained_linkedin_claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="linkedin_post",
        claim_id="soft_copy:linkedin_post:retained",
        text_hash=hashlib.sha256(b"Old linkedin").hexdigest(),
        classification="interpretive",
        evidence_ids=("f1",),
        source_spans=(),
        producing_prompt_identity={"namespace": "old/linkedin"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "linkedin_post"
    ] + soft_copy_claim_provenance_to_payload([retained_linkedin_claim])["claims"]

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
                        issues=[],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=_FakeOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    claims = response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    repaired_text = response.repair_decisions[0].minimal_patch[0].value
    repaired_hash = hashlib.sha256(
        " ".join(str(repaired_text).split()).encode("utf-8")
    ).hexdigest()
    regenerated = next(
        item
        for item in claims
        if item["artifact_family"] == "expert_comment"
        and item["text_hash"] == repaired_hash
    )
    retained = next(
        item for item in claims if item["artifact_family"] == "linkedin_post"
    )
    assert regenerated["classification"] == "interpretive"
    assert regenerated["evidence_ids"] == ["f1"]
    assert response.repair_decisions[0].evidence_ids_used == ["f1"]
    assert regenerated["regeneration_attempt"] == 2
    assert regenerated["producing_prompt_identity"]["namespace"] == (
        "report_vs/artifacts/regenerate/expert_comment"
    )
    assert (
        retained
        == soft_copy_claim_provenance_to_payload([retained_linkedin_claim])["claims"][0]
    )


@pytest.mark.parametrize(
    "client_type",
    (_ClaimScopedExpertOpenAIClient, _PunctuationClaimScopedExpertOpenAIClient),
)
@pytest.mark.parametrize("issue_count", (1, 2, 4))
def test_regeneration_repairs_only_the_failed_expert_claim_and_retains_sibling_provenance(
    tmp_path,
    client_type,
    issue_count,
) -> None:
    """Removing claim-scoped reconstruction makes this assertion fail."""
    current_artifacts = _current_artifacts()
    sentences = [
        "First supported U.S. sentence stays.",
        "Bad sentence needs repair.",
        "Third supported sentence stays.",
    ]
    current_artifacts["expert_comment"] = "  ".join(sentences)
    original_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:{index}",
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
    evidence_packs["findings"]["findings"].append(
        {"id": "f3", "evidence": "Third supported evidence."}
    )
    current_artifacts["_repair_evidence_selection"] = {
        f"expert_comment:{original_claims[1].claim_id}": {
            "schema_version": "1.0",
            "claim_id": original_claims[1].claim_id,
            "strategy": "claim_evidence_ids",
            "direct_evidence_ids": ["f1"],
            "parent_evidence_ids": [],
            "quarantined_evidence_ids": [],
            "selected_evidence_ids": ["f1"],
            "package_sha256": "a" * 64,
        }
    }

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
                                message=f"Unsupported middle sentence: issue {index}.",
                                severity="error",
                                evidence_ids=["f2"],
                            )
                            for index in range(issue_count)
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
        openai_client=client_type(),
        prompt_client=prompt_client,
    )

    assert response.updated_artifacts["expert_comment"] == (
        "First supported U.S. sentence stays.  Repaired middle claim.  "
        "Third supported sentence stays."
    )
    failure_reasons = json.loads(
        prompt_client.render_calls[0]["variables"]["failure_reasons_json"]
    )
    assert len(failure_reasons) == issue_count
    selection = response.updated_artifacts["_repair_evidence_selection"][
        f"expert_comment:{original_claims[1].claim_id}"
    ]
    assert selection["strategy"] == "claim_evidence_ids"
    assert selection["selected_evidence_ids"] == ["f2"]
    assert len(selection["package_sha256"]) == 64
    assert selection["package_sha256"] != "a" * 64
    claims = response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    by_id = {claim["claim_id"]: claim for claim in claims}
    assert (
        by_id[original_claims[0].claim_id]
        == soft_copy_claim_provenance_to_payload([original_claims[0]])["claims"][0]
    )
    assert (
        by_id[original_claims[2].claim_id]
        == soft_copy_claim_provenance_to_payload([original_claims[2]])["claims"][0]
    )
    repaired = next(
        claim
        for claim in claims
        if claim["text_hash"] == hashlib.sha256(b"Repaired middle claim.").hexdigest()
    )
    assert repaired["regeneration_attempt"] == 2
    assert repaired["producing_prompt_identity"]["namespace"] == (
        "report_vs/artifacts/regenerate/expert_comment"
    )


def test_claim_repair_rejects_multisentence_model_output_and_preserves_sibling(
    tmp_path,
) -> None:
    current_artifacts = _current_artifacts()
    supported = "Supported sibling remains."
    unsupported = "Unsupported claim needs repair."
    current_artifacts["expert_comment"] = f"{supported} {unsupported}"
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:{index}",
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
        for index, sentence in enumerate((supported, unsupported), start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(claims)["claims"]
    evidence_packs = _evidence_packs()

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
                                message="Unsupported claim needs repair.",
                                severity="error",
                                entity_id=claims[1].claim_id,
                            )
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
        openai_client=_OverlongClaimScopedExpertOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["expert_comment"] == supported
    retained = [
        claim
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "expert_comment"
    ]
    assert [claim["claim_id"] for claim in retained] == [claims[0].claim_id]


def test_claim_scoped_repair_bridges_quarantine_to_rewritten_factual_claim(
    tmp_path,
) -> None:
    """A rewritten claim must keep the exact selection that scoped its repair."""
    current_artifacts = _current_artifacts()
    original_text = "Original factual claim."
    sibling_text = "Unchanged sibling interpretation."
    original_claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:original-factual",
        text_hash=hashlib.sha256(original_text.encode()).hexdigest(),
        classification="factual",
        evidence_ids=("f2",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    sibling_claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:unchanged-sibling",
        text_hash=hashlib.sha256(sibling_text.encode()).hexdigest(),
        classification="interpretive",
        evidence_ids=("f2",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    current_artifacts["expert_comment"] = f"{original_text} {sibling_text}"
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload([original_claim, sibling_claim])["claims"]
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].extend(
        {"id": f"f{index}", "evidence": f"Supporting finding {index}."}
        for index in (3, 4, 5)
    )

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
                                message="Original factual claim is unsupported.",
                                severity="error",
                                entity_id=original_claim.claim_id,
                                evidence_ids=["f2"],
                                excluded_evidence_ids=["f1"],
                            )
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
        openai_client=_FactualClaimScopedExpertOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    repaired = next(
        claim
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["text_hash"] == hashlib.sha256(b"Repaired middle claim.").hexdigest()
    )
    selection = response.updated_artifacts["_repair_evidence_selection"][
        f"expert_comment:{original_claim.claim_id}"
    ]
    canonical_spans = artifact_evidence_span_index(
        doc_map=evidence_packs["doc_map"], evidence_packs=evidence_packs
    )

    assert repaired["claim_id"] != original_claim.claim_id
    assert repaired["repaired_from_claim_id"] == original_claim.claim_id
    assert repaired["classification"] == original_claim.classification
    assert repaired["evidence_ids"] == selection["selected_evidence_ids"]
    assert repaired["source_spans"] == canonical_spans["f2"]
    assert selection["repaired_claim_id"] == repaired["claim_id"]
    assert valid_soft_copy_evidence_selection(
        f"expert_comment:{original_claim.claim_id}",
        selection,
        require_selected_evidence_entries=True,
    )
    assert response.repair_decisions[0].changed_paths == [
        "expert_comment[claim_index=0]"
    ]
    assert response.repair_decisions[0].minimal_patch[0].value == (
        "Repaired middle claim."
    )
    assert isinstance(response.repair_decisions[0].minimal_patch[0].value, str)
    assert response.updated_artifacts["expert_comment"] == (
        "Repaired middle claim. Unchanged sibling interpretation."
    )
    assert [
        item["entry"]["id"] for item in selection["selected_evidence_entries"]
    ] == selection["selected_evidence_ids"]
    retained_sibling = next(
        claim
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["claim_id"] == sibling_claim.claim_id
    )
    assert (
        retained_sibling
        == soft_copy_claim_provenance_to_payload([sibling_claim])["claims"][0]
    )
    assert "claim_ledgers" not in response.updated_artifacts
    assert "topics_covered" not in response.updated_artifacts
    candidate_integrity = validate_regeneration_candidate(
        current_artifacts=current_artifacts,
        candidate_artifacts=response.updated_artifacts,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )
    assert candidate_integrity.passed, [
        (issue.affected_section, issue.message) for issue in candidate_integrity.issues
    ]

    quarantined_candidate = deepcopy(response.updated_artifacts)
    rewritten_claim = next(
        claim
        for claim in quarantined_candidate["soft_copy_claim_provenance"]["claims"]
        if claim["claim_id"] == repaired["claim_id"]
    )
    rewritten_claim["evidence_ids"] = ["f1"]
    rewritten_claim["source_spans"] = [{"evidence_id": "f1", "source_pack": "findings"}]

    result = validate_regeneration_candidate(
        current_artifacts=current_artifacts,
        candidate_artifacts=quarantined_candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any("quarantined" in issue.message for issue in result.issues)


def test_expert_claim_repair_keeps_final_source_display_and_provenance_aligned(
    tmp_path,
) -> None:
    current = _current_artifacts()
    old_text = "The prior share claim is unsupported."
    sibling_text = "A separate interpretation stays in place."
    repaired_text = "The share was 45.30% in 2025."
    canonical_text = "The share was 45.3% in 2025."
    current["expert_comment"] = f"{old_text} {sibling_text}"
    current["summary"]["claim_evidence_map"] = [
        {
            "claim": canonical_text,
            "evidence_id": "f1",
            "evidence": canonical_text,
            "pages": [1],
        }
    ]
    old_claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:old-share-claim",
        text_hash=hashlib.sha256(old_text.encode()).hexdigest(),
        classification="factual",
        evidence_ids=("f1",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    sibling_claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:sibling-interpretation",
        text_hash=hashlib.sha256(sibling_text.encode()).hexdigest(),
        classification="interpretive",
        evidence_ids=(),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    current["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload([old_claim, sibling_claim])["claims"]

    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"][0] = {
        "id": "f1",
        "text": canonical_text,
        "evidence": canonical_text,
        "page": 1,
        "pages": [1],
    }

    class _SourceDisplayRepairClient(_ClaimScopedExpertOpenAIClient):
        def _legacy_chat_json(self, req, ctx):
            if (
                "system::report_vs/artifacts/regenerate/expert_comment"
                in req.system_prompt
            ):
                self.calls.append(req)
                payload = {"expert_comment": repaired_text}
                return OpenAIResponseResult(
                    schema_version="1.0",
                    text=json.dumps(payload),
                    parsed_json=payload,
                    request_id="req-expert-source-display-repair",
                )
            return super()._legacy_chat_json(req, ctx)

    target = RegenerationTarget(
        target_section="expert_comment",
        regenerate_steps=["expert_comment"],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        allowed_paths=["expert_comment[claim_index=0]"],
        issues=[
            RegenerationIssue(
                rule_id="grounding",
                affected_section="expert_comment",
                message="The generated share precision differs from its evidence.",
                severity="error",
                entity_id=old_claim.claim_id,
                evidence_ids=["f1"],
            )
        ],
    )

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[target],
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
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=_SourceDisplayRepairClient(),
        prompt_client=_FakePromptClient(),
    )

    final_text = response.updated_artifacts["expert_comment"]
    assert final_text == f"{canonical_text} {sibling_text}"
    final_claims = [
        claim
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "expert_comment"
    ]
    assert {claim["text_hash"] for claim in final_claims} == {
        hashlib.sha256(canonical_text.encode()).hexdigest(),
        hashlib.sha256(sibling_text.encode()).hexdigest(),
    }
    assert_retained_soft_copy_claims_match_public_copy(response.updated_artifacts)
