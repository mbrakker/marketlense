# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_report_regeneration_generator.py"
)

from ._split_support_test_report_regeneration_generator import *  # noqa: F401,F403


@pytest.mark.parametrize(
    ("artifact_family", "issue_rule_id", "repair_action", "repair_strategy"),
    [
        ("summary", "artifact_quality", "REMOVE_CLAIM", "safe_removal"),
        ("expert_comment", "artifact_quality", "REMOVE_CLAIM", "safe_removal"),
        ("expert_comment", "grounding", "REGENERATE_ITEM", "current_evidence"),
        ("linkedin_post", "artifact_quality", "REMOVE_CLAIM", "safe_removal"),
    ],
)
def test_explicit_repair_action_changes_only_that_familys_soft_copy_provenance(
    tmp_path,
    artifact_family: str,
    issue_rule_id: str,
    repair_action: str,
    repair_strategy: str,
) -> None:
    current = _current_artifacts()
    evidence_packs = _evidence_packs()
    if artifact_family == "summary":
        current["summary"]["claim_evidence_map"][0].update(
            claim="Old TLDR.", evidence="Old TLDR."
        )
        evidence_packs["findings"]["findings"][0].update(
            text="Old TLDR.", evidence="Old TLDR."
        )
    if artifact_family == "expert_comment" and repair_action == "REGENERATE_ITEM":
        next(
            claim
            for claim in current["soft_copy_claim_provenance"]["claims"]
            if claim["artifact_family"] == artifact_family
        )["evidence_ids"] = ["f1"]
        _append_retained_soft_copy_sibling(current, artifact_family)
    current["topics_covered"] = [
        {
            "schema_version": "1.0",
            "topic_id": "untouched",
            "topic": "Untouched topic",
            "subtopics": [],
            "why_it_matters": "Retained unchanged topic summary.",
            "evidence_ids": ["retained-topic-evidence"],
            "pages": [1],
            "status": "source_backed",
        }
    ]
    current["claim_ledgers"] = [
        {
            "schema_version": "1.0",
            "canonical_claim_id": "untouched-claim",
            "claim_text": "An unchanged retained claim.",
            "artifact_section": "insights_final",
            "evidence_ids": ["retained-claim-evidence"],
            "support_type": "direct",
            "confidence": "high",
            "risk": "low",
        }
    ]
    original_claims = current["soft_copy_claim_provenance"]["claims"]
    repaired_claim = next(
        claim
        for claim in original_claims
        if claim["artifact_family"] == artifact_family
        and (
            artifact_family != "summary"
            or claim["text_hash"] == hashlib.sha256(b"Old summary").hexdigest()
        )
    )
    sibling_claims = [
        claim
        for claim in original_claims
        if claim["artifact_family"] != artifact_family
    ]
    sibling_copy = {
        family: soft_copy_public_text(family, current[family])
        for family in ("summary", "expert_comment", "linkedin_post")
        if family != artifact_family
    }
    openai_client = _FakeOpenAIClient()
    prompt_client = _FakePromptClient()

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=3,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section=artifact_family,
                        repair_action=repair_action,
                        repair_strategy=repair_strategy,
                        allowed_paths=[
                            (
                                "summary.executive_summary[claim_index=0]"
                                if artifact_family == "summary"
                                else f"{artifact_family}[claim_index=0]"
                            )
                        ],
                        issues=[
                            RegenerationIssue(
                                rule_id=issue_rule_id,
                                affected_section=(
                                    "summary.executive_summary"
                                    if artifact_family == "summary"
                                    else artifact_family
                                ),
                                message="Remove the failed soft-copy family.",
                                severity="error",
                                entity_id=repaired_claim["claim_id"],
                            )
                        ],
                    )
                ],
            ),
            current_artifacts=current,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    updated = response.updated_artifacts
    attempt_number_does_not_select_safe_removal = (
        artifact_family == "expert_comment"
        and issue_rule_id == "grounding"
        and repair_strategy == "current_evidence"
    )
    if attempt_number_does_not_select_safe_removal:
        assert updated[artifact_family].startswith("Retention and margin")
        assert openai_client.calls
        assert prompt_client.render_calls
    elif artifact_family == "summary":
        assert updated["summary"]["executive_summary"] == "Old TLDR."
        assert updated["summary"]["tldr"] == "Old TLDR."
        assert updated["summary"]["card_tldr_compact"] == "Old TLDR."
    else:
        assert updated[artifact_family] == ""
    if not attempt_number_does_not_select_safe_removal and artifact_family != "summary":
        assert not any(
            claim["artifact_family"] == artifact_family
            for claim in updated["soft_copy_claim_provenance"]["claims"]
        )
    if artifact_family == "summary":
        assert any(
            claim["artifact_family"] == "summary"
            for claim in updated["soft_copy_claim_provenance"]["claims"]
        )
    assert {
        family: soft_copy_public_text(family, updated[family])
        for family in sibling_copy
    } == sibling_copy
    if artifact_family in {"expert_comment", "linkedin_post"}:
        assert updated["topics_covered"] == current["topics_covered"]
        assert updated["claim_ledgers"] == current["claim_ledgers"]
    else:
        assert updated["topics_covered"] != current["topics_covered"]
        assert updated["claim_ledgers"] != current["claim_ledgers"]
    assert [
        claim
        for claim in updated["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != artifact_family
    ] == sibling_claims
    assert_retained_soft_copy_claims_match_public_copy(updated)
    candidate_integrity = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=updated,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )
    assert not any(
        issue.rule_id == "soft_copy_claim_provenance"
        for issue in candidate_integrity.issues
    )
    if not attempt_number_does_not_select_safe_removal:
        assert openai_client.calls == []
        assert prompt_client.render_calls == []


def test_regenerate_artifacts_insights_bundle_uses_targeted_steps_and_preserves_untouched_sections(
    tmp_path,
):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    current_artifacts = _current_artifacts()
    current_artifacts["insights_final"][0]["metric"]["value"] = "Unsupported value"
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="insights_bundle",
                        regenerate_steps=["insights_candidates", "insights_final"],
                        prompt_namespaces=[
                            "report_vs/artifacts/regenerate/insights_candidates",
                            "report_vs/artifacts/regenerate/insights_final",
                        ],
                        issues=[
                            RegenerationIssue(
                                rule_id="metrics",
                                affected_section="insights:insight-1.metric.value",
                                message="[metrics] Unsupported insight value",
                                severity="error",
                                evidence_ids=["f1"],
                                pages=[1],
                                entity_id="insight:insight-1:metric.value",
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
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

    assert response.regenerated_sections == ["insights_final"]
    prompts = response.updated_artifacts["_cache"]["prompts"]
    assert prompts["report_vs/artifacts/insights_final"] == {
        "prompt_content_hash": "c" * 64
    }
    assert prompts["report_vs/artifacts/regenerate/insights_final"][
        "execution_identity"
    ]
    assert (
        response.updated_artifacts["insights_candidates"]
        == current_artifacts["insights_candidates"]
    )
    assert len(response.updated_artifacts["insights_final"]) == 5
    assert (
        response.updated_artifacts["family_status"]["insights_bundle"]["status"]
        == "generated"
    )
    assert [call.path for call in response.updated_artifacts and []] == []
    assert response.artifacts_path == ""
    assert Path(response.candidate_artifacts_path).is_file()
    assert not (
        tmp_path / "out" / "report-1" / "report_analysis" / "artifacts.json"
    ).exists()

    rendered_paths = [call["path"] for call in prompt_client.render_calls]
    assert rendered_paths == [
        "report_vs/artifacts/regenerate/insights_final/system.yaml",
        "report_vs/artifacts/regenerate/insights_final/user.yaml",
    ]
    first_user_prompt = openai_client.calls[0].user_prompt
    assert "Unsupported insight value" in first_user_prompt
    assert "Evidence text" in first_user_prompt
    final_variables = prompt_client.render_calls[1]["variables"]
    assert final_variables["final_insight_target_count"] == 1


def test_insight_so_what_repair_changes_only_declared_leaf(tmp_path):
    current = _current_artifacts()
    current["insights_final"][0]["so_what"] = "The original implication is unsupported."
    current["insights_candidates"].append(
        {
            **deepcopy(current["insights_final"][0]),
            "text": "Candidate insight",
        }
    )
    original = deepcopy(current["insights_final"][0])
    issue = RegenerationIssue(
        rule_id="numbers",
        affected_section="insights:insight-1.so_what",
        entity_id="insight:insight-1:so_what",
        message="Unsupported number in the implication.",
        severity="error",
        evidence_ids=["f1"],
    )
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                schema_version="1.0",
                message=issue.message,
                severity="error",
                affected_section=issue.affected_section,
                rule_id=issue.rule_id,
                entity_id=issue.entity_id,
                evidence_ids=issue.evidence_ids,
            )
        ],
        artifacts=current,
        broad_retry_available=False,
    )
    assert plan.targets[0].allowed_paths == ["insights_final[item=insight-1].so_what"]
    openai_client = _MobileSoWhatOpenAIClient()

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=plan,
            current_artifacts=current,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    repaired = response.updated_artifacts["insights_final"][0]
    assert repaired["so_what"] == "The repaired implication is evidence-led."
    assert {key: value for key, value in repaired.items() if key != "so_what"} == {
        key: value for key, value in original.items() if key != "so_what"
    }
    assert len(openai_client.calls) == 1


@pytest.mark.parametrize(
    ("selected_evidence_id", "expect_rejection"),
    [("sec-1", True), ("repair-finding", False)],
)
def test_insight_evidence_rebind_requires_relevant_direct_source_with_page(
    tmp_path, selected_evidence_id: str, expect_rejection: bool
):
    current = _current_artifacts()
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": "Failed source finding.",
                    "evidence": "Failed source finding.",
                    "pages": [1],
                },
                {
                    "id": "repair-finding",
                    "text": "A separately retained direct source finding.",
                    "evidence": "A separately retained direct source finding.",
                    "pages": [7],
                },
            ]
        }
    }
    doc_map = {
        "doc_id": "doc-1",
        "sections": [
            {
                "id": "sec-1",
                "title": "Source section",
                "summary": "A section-level summary.",
                "pages": [1],
            }
        ],
    }
    target = RegenerationTarget(
        target_section="insights_bundle",
        regenerate_steps=["insights_candidates", "insights_final"],
        prompt_namespaces=[
            "report_vs/artifacts/regenerate/insights_candidates",
            "report_vs/artifacts/regenerate/insights_final",
        ],
        issues=[
            RegenerationIssue(
                rule_id="grounding",
                affected_section="insights:insight-1.text",
                message="Rebind the insight to retained alternative source evidence.",
                severity="error",
                evidence_ids=["f1"],
                excluded_evidence_ids=["f1"],
                pages=[1],
            )
        ],
        repair_action="REBIND_EVIDENCE",
        repair_strategy="alternative_evidence",
        allowed_paths=["insights_final[item=insight-1].evidence_id"],
    )
    request = ArtifactRegenerationRequest(
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
        doc_map=doc_map,
        evidence_packs=evidence_packs,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        source_status=current["source_status"],
        categories=["Category"],
        vector_store_id=None,
        md5="md5",
    )
    openai_client = _EvidenceRebindOpenAIClient(selected_evidence_id)

    if expect_rejection:
        with pytest.raises(AppError) as error:
            regenerate_artifacts(
                request,
                openai_client=openai_client,
                prompt_client=_FakePromptClient(),
            )
        assert error.value.code == "regeneration_evidence_rebind_unresolved"
        return

    response = regenerate_artifacts(
        request,
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    repaired = response.updated_artifacts["insights_final"][0]
    assert repaired["evidence_id"] == "repair-finding"
    assert repaired["pages"] == [7]
    assert repaired["evidence"] == "A separately retained direct source finding."
    assert repaired["evidence_spans"] == [
        {
            "evidence_id": "repair-finding",
            "source_pack": "findings",
            "page": 7,
            "text": "A separately retained direct source finding.",
        }
    ]


def test_canonical_metric_copy_changes_only_declared_metric_leaf(tmp_path):
    current = _current_artifacts()
    evidence_text = "Regional Attention index was 99-110 across APAC, EMEA, LATAM and North America."
    current["insights_final"][0]["evidence"] = evidence_text
    current["insights_final"][0]["metric"].update(
        {
            "label": "Regional Attention",
            "value": "",
            "unit": "index",
            "geography": "Global",
        }
    )
    current["insights_candidates"] = [
        {
            **deepcopy(current["insights_final"][0]),
            "metric": {
                **current["insights_final"][0]["metric"],
                "value": "99-110",
                "geography": "APAC, EMEA, LATAM, North America",
            },
            "evidence": evidence_text,
        }
    ]
    original_metric = deepcopy(current["insights_final"][0]["metric"])
    issue = ValidationIssue(
        schema_version="1.0",
        message="Retained metric value is unsupported.",
        severity="error",
        affected_section="insights:insight-1.metric",
        rule_id="retained_claim.protected_fact_value_consistency",
        entity_id="insight:insight-1:metric",
        evidence_ids=["f1"],
    )
    plan = _build_regeneration_plan(
        issues=[issue], artifacts=current, broad_retry_available=False
    )
    assert plan.targets[0].repair_action == "CORRECT_PROTECTED_FACT"
    assert plan.targets[0].allowed_paths == [
        "insights_final[item=insight-1].metric.value"
    ]
    openai_client = _FakeOpenAIClient()
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"][0].update(
        {"evidence": evidence_text, "text": evidence_text}
    )

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=plan,
            current_artifacts=current,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    repaired = next(
        item
        for item in response.updated_artifacts["insights_final"]
        if item["id"] == "insight-1"
    )
    updated_metric = repaired["metric"]
    assert updated_metric["value"] == "99-110", response.updated_artifacts[
        "insights_final"
    ]
    assert {key: value for key, value in updated_metric.items() if key != "value"} == {
        key: value for key, value in original_metric.items() if key != "value"
    }
    assert openai_client.calls == []


def test_noop_canonical_metric_copy_fails_before_provider_use(tmp_path):
    current = _current_artifacts()
    current["insights_final"][0]["metric"].update(
        {"label": "Regional Attention", "value": "99-110", "unit": "index"}
    )
    current["insights_candidates"] = [deepcopy(current["insights_final"][0])]
    target = RegenerationTarget(
        target_section="insights_bundle",
        regenerate_steps=["insights_candidates", "insights_final"],
        prompt_namespaces=["report_vs/artifacts/regenerate/insights_final"],
        issues=[
            RegenerationIssue(
                rule_id="retained_claim.protected_fact_value_consistency",
                affected_section="insights:insight-1.metric",
                entity_id="insight:insight-1:metric",
                message="Metric value does not match retained evidence.",
                severity="error",
                evidence_ids=["f1"],
            )
        ],
        repair_action="CORRECT_PROTECTED_FACT",
        repair_strategy="canonical_metric_copy",
        allowed_paths=["insights_final[item=insight-1].metric.value"],
    )
    openai_client = _FakeOpenAIClient()
    prompt_client = _FakePromptClient()

    with pytest.raises(AppError) as error:
        _regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=RegenerationPlan(
                    mode="targeted", targets=[target], unmappable_issues=[]
                ),
                current_artifacts=current,
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=current["source_status"],
                categories=["Category"],
            ),
            openai_client=openai_client,
            prompt_client=prompt_client,
        )

    assert error.value.code == "no_material_repair_available"
    assert openai_client.calls == []
    assert prompt_client.render_calls == []


def test_final_insight_reuses_same_id_candidate_evidence_when_model_omits_it() -> None:
    final_insights = [
        {
            "id": "insight-email-automation",
            "text": "The repaired wording remains specific to automation.",
            "evidence_id": "",
            "evidence": "",
            "evidence_spans": [],
            "pages": [],
            "metric": dict(METRIC),
        }
    ]
    candidates = [
        {
            "id": "insight-email-automation",
            "text": "Candidate wording.",
            "evidence_id": "finding-5",
            "evidence": "Automated messages drove the reported result.",
            "evidence_spans": [
                {
                    "evidence_id": "finding-5",
                    "source_pack": "findings",
                    "page": 8,
                    "text": "Automated messages drove the reported result.",
                }
            ],
            "pages": [8],
            "metric": dict(METRIC),
        }
    ]

    restored = _restore_final_insight_evidence_bindings(
        final_insights=final_insights,
        candidate_insights=candidates,
        prior_final_insights=[],
    )

    assert restored[0]["text"] == (
        "The repaired wording remains specific to automation."
    )
    assert restored[0]["evidence_id"] == "finding-5"
    assert restored[0]["evidence"] == "Automated messages drove the reported result."
    assert restored[0]["pages"] == [8]


def test_regeneration_keeps_unreplaced_insight_evidence_records() -> None:
    current = [
        {"id": "insight-one", "text": "Existing evidence one.", "evidence_id": "f1"},
        {"id": "insight-two", "text": "Existing evidence two.", "evidence_id": "f2"},
    ]
    regenerated = [
        {"id": "insight-one", "text": "Repaired evidence one.", "evidence_id": "f1"},
        {
            "id": "new-unstable-id",
            "text": "Unrelated replacement.",
            "evidence_id": "f3",
        },
    ]

    merged = _merge_regenerated_insights_by_stable_id(
        current_insights=current,
        regenerated_insights=regenerated,
        append_new=True,
    )

    assert [item["id"] for item in merged] == [
        "insight-one",
        "insight-two",
        "new-unstable-id",
    ]
    assert merged[0]["text"] == "Repaired evidence one."
    assert merged[1]["evidence_id"] == "f2"
