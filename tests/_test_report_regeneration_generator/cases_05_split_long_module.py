# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_report_regeneration_generator.py"
)

from ._split_support_test_report_regeneration_generator import *  # noqa: F401,F403


def test_atomic_repair_rejects_selected_evidence_missing_from_retained_package(
    tmp_path,
) -> None:
    current = _current_artifacts()
    old_text = "Original factual Expert View sentence."
    old_claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:original-factual",
        text_hash=hashlib.sha256(old_text.encode()).hexdigest(),
        classification="factual",
        evidence_ids=("f2",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    current["expert_comment"] = old_text
    current["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload([old_claim])["claims"]
    evidence_packs = _evidence_packs()

    class _UnknownSelectedEvidenceClient:
        def openai_chat_json(self, req, ctx):
            del ctx
            variables = _parse_fixture_variables(req.user_prompt)
            assert variables is not None
            repair_context = json.loads(variables["repair_context_json"])
            path = repair_context["allowed_paths"][0]
            decision = {
                "schema_version": "1.0",
                "repair_action": repair_context["repair_action"],
                "repair_strategy": repair_context["repair_strategy"],
                "evidence_ids_used": ["missing-retained-evidence"],
                "changed_paths": [path],
                "minimal_patch": [
                    {
                        "op": "replace",
                        "path": path,
                        "value": "Repaired factual sentence.",
                    }
                ],
            }
            payload = {"repair_decision": decision}
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                request_id="req-unknown-selected-evidence",
            )

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
                message="Original factual claim is unsupported.",
                severity="error",
                entity_id=old_claim.claim_id,
                evidence_ids=["f2"],
            )
        ],
    )

    with pytest.raises(AppError) as captured:
        _regenerate_artifacts(
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
            ),
            openai_client=_UnknownSelectedEvidenceClient(),
            prompt_client=_FakePromptClient(),
        )

    assert captured.value.code == "regeneration_repair_decision_invalid"
    assert captured.value.context["reason"] == "evidence_not_retained_or_quarantined"


def test_linkedin_atomic_repair_rebuilds_only_the_changed_claim_provenance(
    tmp_path,
) -> None:
    current = _current_artifacts()
    original_text = "Original factual LinkedIn sentence."
    sibling_text = "Unchanged LinkedIn sentence."
    original_claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="linkedin_post",
        claim_id="soft_copy:linkedin_post:original-factual",
        text_hash=hashlib.sha256(original_text.encode()).hexdigest(),
        classification="factual",
        evidence_ids=("f2",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/linkedin_post"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    sibling_claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="linkedin_post",
        claim_id="soft_copy:linkedin_post:unchanged-sibling",
        text_hash=hashlib.sha256(sibling_text.encode()).hexdigest(),
        classification="interpretive",
        evidence_ids=("f2",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/linkedin_post"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    current["linkedin_post"] = f"{original_text} {sibling_text}"
    current["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "linkedin_post"
    ] + soft_copy_claim_provenance_to_payload([original_claim, sibling_claim])["claims"]
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].extend(
        {"id": f"f{index}", "evidence": f"Supporting finding {index}."}
        for index in (3, 4, 5)
    )
    target = RegenerationTarget(
        target_section="linkedin_post",
        regenerate_steps=["linkedin_post"],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        allowed_paths=["linkedin_post[claim_index=0]"],
        issues=[
            RegenerationIssue(
                rule_id="grounding",
                affected_section="linkedin_post",
                message="Original LinkedIn fact needs repair.",
                severity="error",
                entity_id=original_claim.claim_id,
                evidence_ids=["f2"],
            ),
            RegenerationIssue(
                rule_id="artifact_quality",
                affected_section="linkedin_post",
                entity_id="linkedin_post",
                message="Existing non-blocking LinkedIn quality warning.",
                severity="warning",
            ),
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
        ),
        openai_client=_ClaimScopedSoftCopyOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    claims = response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    repaired = next(
        claim
        for claim in claims
        if claim["artifact_family"] == "linkedin_post"
        and claim["text_hash"]
        == hashlib.sha256(b"Repaired LinkedIn claim.").hexdigest()
    )
    selection = response.updated_artifacts["_repair_evidence_selection"][
        f"linkedin_post:{original_claim.claim_id}"
    ]
    canonical_spans = artifact_evidence_span_index(
        doc_map=evidence_packs["doc_map"], evidence_packs=evidence_packs
    )

    assert response.updated_artifacts["linkedin_post"] == (
        "Repaired LinkedIn claim. Unchanged LinkedIn sentence."
    )
    assert repaired["classification"] == "factual"
    assert repaired["evidence_ids"] == ["f2"]
    assert repaired["source_spans"] == canonical_spans["f2"]
    assert repaired["repaired_from_claim_id"] == original_claim.claim_id
    assert selection["selected_evidence_ids"] == repaired["evidence_ids"]
    assert (
        next(claim for claim in claims if claim["claim_id"] == sibling_claim.claim_id)
        == soft_copy_claim_provenance_to_payload([sibling_claim])["claims"][0]
    )
    assert not hasattr(response.repair_decisions[0], "claim_provenance")
    candidate_integrity = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=response.updated_artifacts,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )
    assert candidate_integrity.passed, [
        (issue.affected_section, issue.message) for issue in candidate_integrity.issues
    ]


def test_provider_strategy_echo_cannot_override_the_planner_owned_repair(
    tmp_path,
) -> None:
    class _MismatchedPlannerEchoClient(_ClaimScopedSoftCopyOpenAIClient):
        def openai_chat_json(self, req, ctx):
            result = super().openai_chat_json(req, ctx)
            if "regeneration_repair_decision" not in (
                req.structured_output_schema_identity or ""
            ):
                return result
            payload = deepcopy(result.parsed_json)
            payload["repair_decision"]["repair_action"] = "REMOVE_CLAIM"
            payload["repair_decision"]["repair_strategy"] = "safe_removal"
            return OpenAIResponseResult(
                schema_version=result.schema_version,
                text=json.dumps(payload),
                parsed_json=payload,
                request_id="req-mismatched-planner-echo",
            )

    current = _current_artifacts()
    linkedin_claim = next(
        claim
        for claim in current["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "linkedin_post"
    )
    linkedin_claim["evidence_ids"] = ["f2"]
    target = RegenerationTarget(
        target_section="linkedin_post",
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        allowed_paths=["linkedin_post[claim_index=0]"],
        issues=[
            RegenerationIssue(
                rule_id="grounding",
                affected_section="linkedin_post",
                message="Repair this retained claim using its current evidence.",
                severity="error",
                entity_id=linkedin_claim["claim_id"],
                evidence_ids=["f2"],
            )
        ],
    )

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[target],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=_MismatchedPlannerEchoClient(),
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["linkedin_post"] == "Repaired LinkedIn claim."
    assert response.repair_decisions[0].repair_action == "REGENERATE_ITEM"
    assert response.repair_decisions[0].repair_strategy == "current_evidence"
    assert response.repair_decisions[0].changed_paths == [
        "linkedin_post[claim_index=0]"
    ]


def test_public_validator_to_plan_to_claim_repair_preserves_sibling_provenance(
    tmp_path,
) -> None:
    """Exercise retained claim ID propagation through the real deterministic path."""
    current_artifacts = _current_artifacts()
    sentences = [
        "First supported sibling.",
        "{{TODO}} failed middle claim.",
        "Last supported sibling.",
    ]
    current_artifacts["expert_comment"] = "  ".join(sentences)
    original_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:validator-flow:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=({"page": index},),
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
    validation_issues = validation_issues_from_public_editorial_quality(
        evaluate_public_editorial_quality(
            report_id="validator-flow", artifacts=current_artifacts
        )
    )
    failed_issue = next(
        issue
        for issue in validation_issues
        if issue.entity_id == original_claims[1].claim_id
    )
    warning_issue = ValidationIssue(
        schema_version="1.0",
        message="Existing non-blocking Expert View quality warning.",
        severity="warning",
        affected_section="expert_comment",
        rule_id="artifact_quality",
        entity_id="expert_comment",
    )
    plan = _build_regeneration_plan(
        issues=[failed_issue, warning_issue],
        artifacts=current_artifacts,
        broad_retry_available=False,
    )

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=plan,
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=_ClaimScopedExpertOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    assert failed_issue.entity_id == original_claims[1].claim_id
    assert plan.targets[0].issues[0].evidence_ids == ["f2"]
    assert any(
        issue.entity_id == original_claims[1].claim_id
        for issue in plan.targets[0].issues
    )
    assert any(
        issue.rule_id == "artifact_quality" and issue.severity == "warning"
        for issue in plan.targets[0].issues
    )
    assert response.updated_artifacts["expert_comment"] == (
        "First supported sibling.  Last supported sibling."
    )
    by_id = {
        claim["claim_id"]: claim
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    }
    for claim in (original_claims[0], original_claims[2]):
        assert (
            by_id[claim.claim_id]
            == soft_copy_claim_provenance_to_payload([claim])["claims"][0]
        )
    assert original_claims[1].claim_id not in by_id


def test_summary_claim_repair_skips_warning_outside_planned_paths(tmp_path) -> None:
    current_artifacts = _current_artifacts()
    sentences = [
        "Unsupported publisher detail.",
        "Retained supported context.",
        "Nonblocking summary warning.",
    ]
    current_artifacts["summary"]["executive_summary"] = " ".join(sentences)
    original_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="summary",
            claim_id=(
                "soft_copy:summary:"
                f"{hashlib.sha256(sentence.encode()).hexdigest()[:16]}"
            ),
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="factual",
            evidence_ids=(f"f{index}",),
            source_spans=(),
            producing_prompt_identity={"namespace": "report_vs/artifacts/summary"},
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["summary"]["claim_evidence_map"] = [
        {
            "claim": sentence,
            "evidence_id": f"f{index + 2}",
            "evidence": sentence,
            "evidence_spans": [
                {
                    "evidence_id": f"f{index + 2}",
                    "source_pack": "findings",
                    "text": sentence,
                }
            ],
        }
        for index, sentence in ((2, sentences[1]), (3, sentences[2]))
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "summary"
        or claim["text_hash"] == hashlib.sha256(b"Old TLDR.").hexdigest()
    ] + soft_copy_claim_provenance_to_payload(original_claims)["claims"]
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].extend(
        {
            "id": f"f{index}",
            "evidence": sentence,
            "text": sentence,
        }
        for index, sentence in ((4, sentences[1]), (5, sentences[2]))
    )
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                rule_id="grounding",
                affected_section="summary.executive_summary",
                message="The publisher attribution is unsupported.",
                severity="error",
                entity_id=original_claims[0].claim_id,
                evidence_ids=["f1"],
            ),
            ValidationIssue(
                rule_id="grounding",
                affected_section="summary.executive_summary",
                message="A nonblocking concern remains on another sentence.",
                severity="warning",
                entity_id=original_claims[2].claim_id,
                evidence_ids=["f3"],
            ),
        ],
        artifacts=current_artifacts,
        broad_retry_available=False,
    )
    assert plan.targets[0].allowed_paths == ["summary.executive_summary[claim_index=0]"]

    openai_client = _ClaimScopedSoftCopyOpenAIClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=plan,
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

    assert openai_client.calls == []
    assert response.updated_artifacts["summary"]["executive_summary"] == (
        "Retained supported context. Nonblocking summary warning."
    )
    assert original_claims[2].claim_id in {
        claim["claim_id"]
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    }


def test_ambiguous_soft_copy_issue_is_not_widened_to_family_regeneration(
    tmp_path,
) -> None:
    current_artifacts = _current_artifacts()
    sentences = ["First sibling.", "Second ambiguous claim.", "Third ambiguous claim."]
    current_artifacts["expert_comment"] = " ".join(sentences)
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:ambiguous:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=("f2" if index > 1 else "f1",),
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
    openai_client = _ClaimScopedExpertOpenAIClient()

    with pytest.raises(AppError) as error:
        regenerate_artifacts(
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
                                    message="Unsupported retained claim.",
                                    severity="error",
                                    evidence_ids=["f2"],
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
            openai_client=openai_client,
            prompt_client=_FakePromptClient(),
        )

    assert error.value.context["reason"] in {
        "atomic_repair_target_unresolved_or_ambiguous",
        "repair_scope_partition_invalid",
    }
    assert openai_client.calls == []


def test_regeneration_abstains_only_an_unsupported_expert_claim_without_model_call(
    tmp_path,
) -> None:
    """The unsupported claim is removed while valid prose and provenance remain."""
    current_artifacts = _current_artifacts()
    sentences = [
        "First supported sentence.",
        "Unsupported sentence.",
        "Last supported sentence.",
    ]
    current_artifacts["expert_comment"] = " ".join(sentences)
    original_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:unsupported:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="factual",
            evidence_ids=(evidence_id,),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, (sentence, evidence_id) in enumerate(
            zip(sentences, ("f1", "missing", "f2"), strict=True), start=1
        )
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(original_claims)["claims"]
    openai_client = _ClaimScopedExpertOpenAIClient()
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
                                message="Unsupported sentence.",
                                severity="error",
                                evidence_ids=["missing"],
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
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["expert_comment"] == (
        "First supported sentence. Last supported sentence."
    )
    assert openai_client.calls == []
    claim_ids = {
        claim["claim_id"]
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    }
    assert original_claims[0].claim_id in claim_ids
    assert original_claims[1].claim_id not in claim_ids
    assert original_claims[2].claim_id in claim_ids
    assert_retained_soft_copy_claims_match_public_copy(response.updated_artifacts)
