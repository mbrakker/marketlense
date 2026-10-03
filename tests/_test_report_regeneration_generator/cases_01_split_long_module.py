# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_report_regeneration_generator.py"
)

from ._split_support_test_report_regeneration_generator import *  # noqa: F401,F403


def test_restore_missing_final_insight_roster_replaces_duplicate_model_id() -> None:
    prior = [
        {"id": "insight-1", "text": "Prior one", "evidence_id": "f1"},
        {"id": "insight-2", "text": "Prior two", "evidence_id": "f2"},
    ]
    selected = [
        {"id": "insight-2", "text": "Repaired two", "evidence_id": "f3"},
        {"id": "insight-2", "text": "Duplicate model ID", "evidence_id": "f4"},
    ]

    restored = _restore_missing_final_insight_roster(
        selected_insights=selected,
        prior_final_insights=prior,
    )

    assert [item["id"] for item in restored] == ["insight-2", "insight-1"]
    assert restored[0]["text"] == "Repaired two"
    assert restored[1] == prior[0]


def test_grounding_package_quarantines_failed_evidence_and_uses_replacements() -> None:
    target = RegenerationTarget(
        target_section="insights_bundle",
        issues=[
            RegenerationIssue(
                rule_id="grounding",
                affected_section="insights:attention.so_what",
                message="The claim adds an unsupported causal outcome.",
                severity="error",
                evidence_ids=["failed-evidence"],
                excluded_evidence_ids=["failed-evidence"],
            )
        ],
    )

    package = _build_grounding_package(
        target=target,
        prepared=SimpleNamespace(evidence_windows=[]),
        artifacts={"insights_final": []},
        evidence_packs={
            "findings": [
                {"id": "failed-evidence", "text": "Unsupported source angle."},
                {"id": "approved-evidence", "text": "Supported replacement angle."},
            ]
        },
        doc_map={},
    )

    assert package["quarantined_evidence_ids"] == ["failed-evidence"]
    assert package["evidence_ids"] == ["approved-evidence"]
    assert "failed-evidence" not in json.dumps(package["relevant_evidence"])


def test_grounding_package_selects_retained_evidence_for_soft_copy_without_issue_ids() -> (
    None
):
    package = _build_grounding_package(
        target=RegenerationTarget(
            target_section="expert_comment",
            issues=[
                RegenerationIssue(
                    rule_id="public_editorial_quality.support",
                    affected_section="expert_comment",
                    message="Unsupported operational benefit.",
                    severity="error",
                )
            ],
        ),
        prepared=SimpleNamespace(evidence_windows=[]),
        artifacts={
            "expert_comment": "The retention signal supports a planning choice.",
            "editorial_plan": {"themes": [{"evidence_ids": ["finding-2"]}]},
            "insights_final": [{"evidence_id": "finding-1"}],
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {"id": "finding-1", "text": "Retention improved in the cohort."},
                    {"id": "finding-2", "text": "Margin pressure remains visible."},
                ]
            }
        },
        doc_map={},
    )

    assert package["evidence_ids"] == ["finding-1", "finding-2"]


def test_handcrafted_incomplete_protected_field_complement_is_rejected() -> None:
    decision = RepairDecision(
        diagnosed_failure_class="grounding",
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        protected_fields=["expert_comment[claim_index=0]"],
    )

    assert not _repair_decision_protected_fields_are_complete(
        decision,
        [
            "expert_comment[claim_index=1]",
            "expert_comment[claim_index=2]",
        ],
    )
    assert _repair_decision_protected_fields_are_complete(
        decision,
        ["expert_comment[claim_index=0]"],
    )
    assert not _repair_decision_protected_fields_are_complete(decision, [])
    assert _repair_decision_protected_fields_are_complete(
        RepairDecision(
            diagnosed_failure_class="grounding",
            repair_action="REGENERATE_ITEM",
            repair_strategy="current_evidence",
        ),
        [],
    )


def test_family_soft_copy_repair_rebuilds_only_new_claim_bindings() -> None:
    sibling_text = "Unchanged sibling claim."
    sibling = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:sibling",
        text_hash=hashlib.sha256(sibling_text.encode()).hexdigest(),
        classification="interpretive",
        evidence_ids=("f1",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )

    bindings = _deterministic_family_soft_copy_bindings(
        artifact_family="expert_comment",
        text=f"{sibling_text} New factual sentence.",
        selected_evidence_ids=["f2"],
        existing_claims=[sibling],
    )

    assert bindings == [
        {
            "claim": "New factual sentence.",
            "classification": "factual",
            "evidence_ids": ["f2"],
        }
    ]
    assert (
        _deterministic_family_soft_copy_bindings(
            artifact_family="expert_comment",
            text="New unsupported sentence.",
            selected_evidence_ids=[],
            existing_claims=[sibling],
        )
        is None
    )


def test_soft_copy_claim_evidence_package_prefers_direct_retained_ids() -> None:
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(evidence_ids=("f2", "f1")),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        artifacts=_current_artifacts(),
        evidence_packs=_evidence_packs(),
        quarantined_evidence_ids=(),
    )

    assert package["evidence_ids"] == ["f2", "f1"]
    assert package["evidence_selection"]["strategy"] == "claim_evidence_ids"


def test_soft_copy_claim_evidence_package_resolves_direct_doc_map_section() -> None:
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(evidence_ids=("section-checkout",)),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        artifacts=_current_artifacts(),
        evidence_packs=_evidence_packs(),
        doc_map={
            "sections": [
                {
                    "id": "section-checkout",
                    "title": "Checkout behavior",
                    "summary": "Checkout friction remains material.",
                    "pages": [3, 4],
                }
            ]
        },
        quarantined_evidence_ids=(),
    )

    assert package["evidence_ids"] == ["section-checkout"]
    assert package["relevant_evidence"] == [
        {
            "pack_name": "doc_map",
            "id": "section-checkout",
            "title": "Checkout behavior",
            "summary": "Checkout friction remains material.",
            "pages": [3, 4],
        }
    ]
    assert package["evidence_selection"]["strategy"] == "claim_evidence_ids"


def test_soft_copy_claim_evidence_package_skips_quarantined_doc_map_section() -> None:
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(evidence_ids=("section-checkout",)),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        artifacts=_current_artifacts(),
        evidence_packs={},
        doc_map={
            "sections": [
                {
                    "id": "section-checkout",
                    "title": "Checkout behavior",
                    "summary": "Checkout friction remains material.",
                    "pages": [3, 4],
                }
            ]
        },
        quarantined_evidence_ids=("section-checkout",),
    )

    assert package["evidence_ids"] == []
    assert package["evidence_selection"]["strategy"] == "abstain"


def test_soft_copy_claim_evidence_hash_tracks_only_selected_canonical_content() -> None:
    inputs = {
        "claim": _soft_copy_claim(evidence_ids=("f1",)),
        "issue": RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        "artifacts": _current_artifacts(),
        "quarantined_evidence_ids": (),
    }
    original = _build_soft_copy_claim_evidence_package(
        **inputs,
        evidence_packs={
            "findings": [
                {"id": "f1", "text": "Selected evidence.", "pages": [1, 2]},
                {"id": "f2", "text": "Unselected evidence."},
            ]
        },
    )
    reordered = _build_soft_copy_claim_evidence_package(
        **inputs,
        evidence_packs={
            "findings": [
                {"text": "Unselected evidence.", "id": "f2"},
                {"pages": [2, 1], "text": "Selected evidence.", "id": "f1"},
            ]
        },
    )
    selected_changed = _build_soft_copy_claim_evidence_package(
        **inputs,
        evidence_packs={
            "findings": [
                {
                    "id": "f1",
                    "text": "Corrected selected evidence.",
                    "pages": [1, 2],
                },
                {"id": "f2", "text": "Unselected evidence."},
            ]
        },
    )
    unselected_changed = _build_soft_copy_claim_evidence_package(
        **inputs,
        evidence_packs={
            "findings": [
                {"id": "f1", "text": "Selected evidence.", "pages": [1, 2]},
                {"id": "f2", "text": "Changed but unselected evidence."},
            ]
        },
    )

    assert (
        original["evidence_selection"]["package_sha256"]
        == reordered["evidence_selection"]["package_sha256"]
    )
    assert (
        original["evidence_selection"]["package_sha256"]
        != selected_changed["evidence_selection"]["package_sha256"]
    )
    assert (
        original["evidence_selection"]["package_sha256"]
        == unselected_changed["evidence_selection"]["package_sha256"]
    )


def test_regeneration_state_restores_only_valid_private_evidence_selections() -> None:
    retained_selection = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(evidence_ids=("f1",)),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        artifacts=_current_artifacts(),
        evidence_packs={"findings": [{"id": "f1", "text": "Evidence."}]},
        quarantined_evidence_ids=(),
    )["evidence_selection"]
    mismatched_hash = {**retained_selection, "package_sha256": "a" * 64}
    retained_key = f"expert_comment:{retained_selection['claim_id']}"
    linked_selection = {
        **retained_selection,
        "repaired_claim_id": "soft_copy:expert_comment:repaired",
    }
    state = _build_regeneration_state(
        safe_artifacts={
            **_current_artifacts(),
            "_repair_evidence_selection": {
                retained_key: linked_selection,
                f"stale:{retained_selection['claim_id']}": mismatched_hash,
                "bad": {"arbitrary": "data"},
            },
        },
        fallback_toc_bundle={
            "toc_entries": [],
            "toc_topics": [],
            "toc_topics_expanded": [],
        },
        source_status={"not_available": False, "reason": ""},
    )

    assert state.soft_copy_evidence_selections == {retained_key: linked_selection}


def test_soft_copy_claim_evidence_package_uses_parent_insight_before_fallback() -> None:
    artifacts = _current_artifacts()
    artifacts["insights_final"] = [
        {
            "id": "insight-margin",
            "text": "Margin pressure is material.",
            "evidence_id": "f2",
        }
    ]
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(source_spans=({"insight_id": "insight-margin"},)),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        artifacts=artifacts,
        evidence_packs=_evidence_packs(),
        quarantined_evidence_ids=(),
    )

    assert package["evidence_ids"] == ["f2"]
    assert package["evidence_selection"]["strategy"] == "parent_insight_or_theme"


def test_soft_copy_claim_evidence_package_uses_text_matched_parent_theme() -> None:
    artifacts = _current_artifacts()
    artifacts["editorial_plan"] = {
        "themes": [
            {"theme": "Retention performance", "evidence_ids": ["f1"]},
            {"theme": "Margin pressure", "evidence_ids": ["f2"]},
        ]
    }
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Margin pressure claim is unsupported.",
            severity="error",
        ),
        artifacts=artifacts,
        evidence_packs=_evidence_packs(),
        quarantined_evidence_ids=(),
        claim_text="Margin pressure affects planning.",
    )

    assert package["evidence_ids"] == ["f2"]
    assert package["evidence_selection"]["strategy"] == "parent_insight_or_theme"


def test_soft_copy_claim_evidence_package_excludes_quarantined_entries() -> None:
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(evidence_ids=("f2",)),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        artifacts=_current_artifacts(),
        evidence_packs=_evidence_packs(),
        quarantined_evidence_ids=("f2",),
    )

    assert package["evidence_ids"] == []
    assert package["evidence_selection"]["strategy"] == "abstain"


def test_soft_copy_claim_evidence_package_uses_bounded_typed_compatibility_fallback() -> (
    None
):
    same_number_wrong_geography = {
        "id": "wrong-geography",
        "text": "US shoppers increased return rates by 34% in 2023.",
    }
    relevant_findings = [
        {"id": f"relevant-{index}", "text": "Retention planning signal."}
        for index in range(6)
    ]
    evidence_packs = {
        "findings": {
            "findings": [same_number_wrong_geography]
            + relevant_findings
            + [{"id": "irrelevant", "text": "Unrelated commodity price."}]
        }
    }
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Retention planning claim is unsupported.",
            severity="error",
        ),
        artifacts=_current_artifacts(),
        evidence_packs=evidence_packs,
        quarantined_evidence_ids=(),
    )

    assert package["evidence_ids"] == [
        "relevant-0",
        "relevant-1",
        "relevant-2",
        "relevant-3",
    ]
    assert package["evidence_selection"]["strategy"] == "typed_compatibility_fallback"
    assert valid_soft_copy_evidence_selection(
        f"expert_comment:{_soft_copy_claim().claim_id}",
        package["evidence_selection"],
        require_selected_evidence_entries=True,
    )


def test_soft_copy_claim_evidence_package_abstains_and_is_repeatable_without_support() -> (
    None
):
    inputs = {
        "claim": _soft_copy_claim(),
        "issue": RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        "artifacts": _current_artifacts(),
        "evidence_packs": {"findings": [{"id": "f1", "text": "Different topic."}]},
        "quarantined_evidence_ids": (),
    }

    first = _build_soft_copy_claim_evidence_package(**inputs)
    second = _build_soft_copy_claim_evidence_package(**inputs)

    assert first["evidence_ids"] == []
    assert first["evidence_selection"]["strategy"] == "abstain"
    assert first == second
    assert (
        first["evidence_selection"]["package_sha256"]
        == second["evidence_selection"]["package_sha256"]
    )


def test_safe_removal_abstains_linkedin_family_with_unmatched_quality_warning(
    tmp_path,
) -> None:
    current = _current_artifacts()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=3,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="linkedin_post",
                        repair_action="REMOVE_CLAIM",
                        repair_strategy="safe_removal",
                        issues=[
                            RegenerationIssue(
                                rule_id="numbers",
                                affected_section="linkedin_post",
                                message="Unsupported numeric claim.",
                                severity="error",
                                entity_id=current["soft_copy_claim_provenance"][
                                    "claims"
                                ][-1]["claim_id"],
                                evidence_ids=["f1"],
                            ),
                            RegenerationIssue(
                                rule_id="artifact_quality",
                                affected_section="linkedin_post",
                                message="The whole post needs review.",
                                severity="warning",
                                entity_id="linkedin_post",
                            ),
                        ],
                    )
                ],
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
        openai_client=_FakeOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["linkedin_post"] == ""
    assert not any(
        claim["artifact_family"] == "linkedin_post"
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    )
    assert_retained_soft_copy_claims_match_public_copy(response.updated_artifacts)
    assert Path(response.candidate_artifacts_path).is_file()


def test_safe_removal_abstains_only_unsupported_insight_implication(tmp_path) -> None:
    current = _current_artifacts()
    target = current["insights_final"][0]
    target["so_what"] = "The evidence changes planning."
    target["now_what"] = "Make an unsupported recommendation."
    original_text = target["text"]
    original_evidence_id = target["evidence_id"]
    issue = RegenerationIssue(
        rule_id="grounding",
        affected_section="insights:insight-1.now_what",
        message=(
            "[prescriptive_recommendation|unsupported_factual_claim] "
            "The recommendation is not traceable to linked evidence."
        ),
        severity="error",
        entity_id="insight:insight-1:now_what",
        evidence_ids=["f1"],
    )
    allowed_paths = _allowed_paths("insights_bundle", [issue], current, "REMOVE_CLAIM")
    assert allowed_paths == ["insights_final[item=insight-1].now_what"]

    client = _FakeOpenAIClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=3,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="insights_bundle",
                        repair_action="REMOVE_CLAIM",
                        repair_strategy="safe_removal",
                        allowed_paths=allowed_paths,
                        issues=[issue],
                    )
                ],
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
        openai_client=client,
        prompt_client=_FakePromptClient(),
    )

    repaired = next(
        item
        for item in response.updated_artifacts["insights_final"]
        if item["id"] == "insight-1"
    )
    assert client.calls == []
    assert repaired["now_what"] == ""
    assert repaired["so_what"] == "The evidence changes planning."
    assert repaired["text"] == original_text
    assert repaired["evidence_id"] == original_evidence_id


def test_safe_removal_of_multiple_linkedin_claims_keeps_sentence_paths_stable(
    tmp_path,
) -> None:
    current = _current_artifacts()
    linkedin_text = (
        "Unsupported claim 74%. Retained context stays first. "
        "Unsupported claim 71%. Retained context stays last."
    )
    current["linkedin_post"] = linkedin_text
    current_claims = [
        claim
        for claim in soft_copy_claim_provenance_from_payload(
            current["soft_copy_claim_provenance"]
        )
        if claim.artifact_family != "linkedin_post"
    ]
    linkedin_claims = build_soft_copy_claim_provenance(
        artifact_family="linkedin_post",
        text=linkedin_text,
        declared_claims=[
            {
                "claim": sentence,
                "classification": "factual",
                "evidence_ids": ["f1"],
            }
            for sentence in soft_copy_material_sentences(linkedin_text)
        ],
        evidence_span_index={},
        producing_prompt_identity={"namespace": "report_vs/artifacts/linkedin_post"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    current["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        [*current_claims, *linkedin_claims]
    )
    failed_claim_ids = {claim.text_hash: claim.claim_id for claim in linkedin_claims}
    issues = [
        RegenerationIssue(
            rule_id="grounding",
            affected_section="linkedin_post",
            message="This numeric claim has no retained support.",
            severity="error",
            entity_id=failed_claim_ids[
                hashlib.sha256(sentence.encode("utf-8")).hexdigest()
            ],
            evidence_ids=["f1"],
        )
        for sentence in ("Unsupported claim 74%.", "Unsupported claim 71%.")
    ]
    allowed_paths = _allowed_paths("linkedin_post", issues, current, "REMOVE_CLAIM")

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
                        repair_action="REMOVE_CLAIM",
                        repair_strategy="safe_removal",
                        allowed_paths=allowed_paths,
                        issues=issues,
                    )
                ],
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
        openai_client=_FakeOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["linkedin_post"] == (
        "Retained context stays first. Retained context stays last."
    )
    assert_retained_soft_copy_claims_match_public_copy(response.updated_artifacts)
