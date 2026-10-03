# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_atomic_regeneration_contract.py"
)

from ._split_support_test_atomic_regeneration_contract import *  # noqa: F401,F403


@pytest.mark.parametrize(
    ("case_id", "affected", "entity_id", "expected_path"),
    [
        (
            "ebook-0225-fut-997cc1cccd6a",
            "insights_final[3].text",
            "insights_final[3].text",
            "insights_final[item=insight-1].text",
        ),
        (
            "g0-ec-trends-r-41f8ffd78145",
            "insights:insight-1.so_what",
            "insight:insight-1:so_what",
            "insights_final[item=insight-1].so_what",
        ),
        (
            "public-editorial-linkedin-mobile-app",
            "insights_final[0].text",
            "insights_final[0].text",
            "insights_final[item=insight-1].text",
        ),
    ],
)
def test_observed_protected_field_cases_resolve_the_failed_leaf(
    case_id: str, affected: str, entity_id: str, expected_path: str
) -> None:
    del case_id  # The parameter ties this regression to the frozen case record.
    artifacts = _insight_artifacts()
    index = 3 if affected == "insights_final[3].text" else 0
    while len(artifacts["insights_final"]) <= index:
        artifacts["insights_final"].append(
            {"id": f"insight-{len(artifacts['insights_final']) + 1}", "text": ""}
        )
    if index == 3:
        artifacts["insights_final"][0]["id"] = "sibling-one"
    artifacts["insights_final"][index]["id"] = "insight-1"
    issue = RegenerationIssue(
        rule_id="grounding",
        affected_section=affected,
        entity_id=entity_id,
        message="Frozen benchmark issue.",
        severity="error",
    )

    paths = _allowed_paths(
        "insights_bundle", [issue], artifacts, "CORRECT_PROTECTED_FACT"
    )
    target = _target(paths, [issue])
    protected = _required_repair_protected_fields(artifacts, target)

    assert paths == [expected_path]
    assert expected_path not in protected
    decision = _validated_repair_decision(
        _decision_payload(
            target=target,
            artifacts=artifacts,
            patches=[(expected_path, "Patched retained field.")],
        ),
        execution=_execution(target),
        current_artifacts=artifacts,
        grounding_package={"evidence_ids": []},
    )
    assert decision.changed_paths == [expected_path]


def test_observed_protected_metric_case_abstains_without_a_leaf_target() -> None:
    artifacts = _insight_artifacts()
    issue = RegenerationIssue(
        rule_id="metrics",
        affected_section="insights:insight-1",
        message="The metric relationship is invalid.",
        severity="error",
    )

    assert (
        _allowed_paths("insights_bundle", [issue], artifacts, "CORRECT_PROTECTED_FACT")
        == []
    )


def test_doubleverify_protected_case_targets_only_the_supported_expert_claim() -> None:
    # Frozen case: doubleverify-linkedin-public-editorial-hard-failure.
    first_claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:dv-first",
        text_hash=hashlib.sha256(b"Failed expert claim.").hexdigest(),
        classification="interpretive",
        evidence_ids=("s3", "s8"),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    sibling = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:dv-sibling",
        text_hash=hashlib.sha256(b"Retained expert sibling.").hexdigest(),
        classification="interpretive",
        evidence_ids=("s9",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    artifacts = {
        "expert_comment": "Failed expert claim. Retained expert sibling.",
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
            [first_claim, sibling]
        ),
    }
    issue = RegenerationIssue(
        rule_id="public_editorial_quality.metric_label_relationship",
        affected_section="expert_comment",
        entity_id=first_claim.claim_id,
        message="Frozen DoubleVerify expert claim failure.",
        severity="error",
        evidence_ids=["s3", "s8"],
    )

    paths = _allowed_paths("expert_comment", [issue], artifacts, "REGENERATE_ITEM")
    target = RegenerationTarget(
        target_section="expert_comment",
        issues=[issue],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        allowed_paths=paths,
    )

    assert paths == ["expert_comment[claim_index=0]"]
    assert _required_repair_protected_fields(artifacts, target) == [
        "expert_comment[claim_index=1]"
    ]


def test_planner_abstains_when_provenance_evidence_identifies_multiple_claims() -> None:
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:ambiguous-{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=("shared-evidence",),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(("First claim.", "Second claim."), start=1)
    ]
    artifacts = {
        **_insight_artifacts(),
        "expert_comment": "First claim. Second claim.",
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(claims),
    }

    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                message="A retained soft-copy claim lost evidence alignment.",
                severity="error",
                affected_section="expert_comment",
                rule_id="grounding",
                repair_target="expert_comment",
                evidence_ids=["shared-evidence"],
            )
        ],
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert plan.mode == "skip"
    assert plan.targets == []
    assert plan.broad_retry_allowed is False


def test_planner_skips_an_insight_failure_without_a_resolved_leaf() -> None:
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                message="A metric issue without a field-level target.",
                severity="error",
                affected_section="insights:insight-1",
                rule_id="metrics",
                repair_target="insights_bundle",
            )
        ],
        artifacts=_insight_artifacts(),
        broad_retry_available=True,
    )

    assert plan.mode == "skip"
    assert plan.targets == []
    assert plan.broad_retry_allowed is False


def test_derived_key_figure_failure_routes_to_its_source_insight() -> None:
    artifacts = _insight_artifacts()
    artifacts["key_figures"] = [
        {
            "schema_version": "1.0",
            "figure_id": "insight-1",
            "figure": "25%",
            "label": "Existing metric",
            "why_it_matters": "Original insight.",
            "evidence_id": "evidence-1",
        }
    ]
    issue = ValidationIssue(
        message=(
            "[grounding] [factual_claim|evidence_retrieval_failure] "
            "The numeric source evidence could not be retrieved."
        ),
        severity="error",
        affected_section="key_figures:1.figure",
        rule_id="grounding",
        violation_type="evidence_retrieval_failure",
        entity_id="key_figure:1:figure",
    )

    plan = _build_regeneration_plan(
        issues=[issue], artifacts=artifacts, broad_retry_available=True
    )

    assert plan.mode == "targeted"
    assert len(plan.targets) == 1
    assert plan.targets[0].target_section == "insights_bundle"
    assert plan.targets[0].allowed_paths == [
        "insights_final[item=insight-1].evidence_id"
    ]


def test_planner_abstains_when_any_issue_in_an_atomic_target_is_unresolved() -> None:
    artifacts = _insight_artifacts()
    issues = [
        ValidationIssue(
            message="A retained field has an exact target.",
            severity="error",
            affected_section="insights:insight-1.text",
            rule_id="grounding",
            repair_target="insights_bundle",
            entity_id="insight:insight-1:text",
        ),
        ValidationIssue(
            message="A family-level issue has no item identity.",
            severity="error",
            affected_section="insights_final",
            rule_id="artifact_quality",
            repair_target="insights_bundle",
        ),
    ]

    assert _allowed_paths("insights_bundle", issues, artifacts, "REGENERATE_ITEM") == []
    plan = _build_regeneration_plan(
        issues=issues,
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert plan.mode == "skip"
    assert plan.targets == []
    assert plan.broad_retry_allowed is False


def test_ambiguous_writable_path_abstains_before_provider_is_required() -> None:
    artifacts = _insight_artifacts()
    artifacts["insights_final"][1]["id"] = "insight-1"
    issue = _insight_issue("so_what")
    target = _target(["insights_final[item=insight-1].so_what"], [issue])

    assert (
        _allowed_paths("insights_bundle", [issue], artifacts, "REGENERATE_ITEM") == []
    )
    assert _required_repair_protected_fields(artifacts, target) is None

    execution = SimpleNamespace(
        runtime=SimpleNamespace(
            request=SimpleNamespace(report_id="report-1"), openai_client=None
        ),
        target=target,
        state=SimpleNamespace(
            summary={},
            insights_candidates=[],
            insights_final=artifacts["insights_final"],
            quotes_final=[],
            expert_comment="",
            linkedin_post="",
        ),
    )
    with pytest.raises(AppError) as error:
        _render_regeneration_model(
            execution=execution,
            namespace="report_vs/artifacts/regenerate/insights_final",
            variables={},
            ctx=None,
        )

    assert (
        error.value.context["reason"] == "model_writable_path_unresolved_or_ambiguous"
    )


def test_multiple_required_insight_leaves_are_writable_and_siblings_protected() -> None:
    artifacts = _insight_artifacts()
    issues = [_insight_issue("so_what"), _insight_issue("now_what")]
    paths = _allowed_paths(
        "insights_bundle", issues, artifacts, "CORRECT_PROTECTED_FACT"
    )
    target = _target(paths, issues)
    protected = _required_repair_protected_fields(artifacts, target)
    item_prefix = "insights_final[item=insight-1]."

    assert paths == [item_prefix + "now_what", item_prefix + "so_what"]
    assert item_prefix + "now_what" not in protected
    assert item_prefix + "so_what" not in protected
    assert item_prefix + "text" in protected
    assert item_prefix + "metric.subject" in protected
    assert "insights_final[item=insight-2].text" in protected

    payload = _decision_payload(
        target=target,
        artifacts=artifacts,
        patches=[
            (item_prefix + "so_what", "Grounded implication."),
            (item_prefix + "now_what", "Grounded action."),
        ],
        evidence_ids=["retained-evidence"],
    )
    decision = _validated_repair_decision(
        payload,
        execution=_execution(target),
        current_artifacts=artifacts,
        grounding_package={"evidence_ids": ["retained-evidence"]},
    )
    patched = _apply_repair_decision_patch(
        current_artifacts=artifacts, decision=decision
    )

    assert patched["insights_final"][0]["so_what"] == "Grounded implication."
    assert patched["insights_final"][0]["now_what"] == "Grounded action."
    assert (
        patched["insights_final"][0]["text"] == artifacts["insights_final"][0]["text"]
    )
    assert (
        patched["insights_final"][0]["metric"]
        == artifacts["insights_final"][0]["metric"]
    )
    assert patched["insights_final"][1] == artifacts["insights_final"][1]

    scope = _scope_validation_report(
        before=artifacts,
        after=patched,
        plan=SimpleNamespace(targets=[target]),
    )
    assert scope.status == "pass"

    unauthorized = deepcopy(patched)
    unauthorized["insights_final"][0]["metric"]["subject"] = "changed fact"
    scope = _scope_validation_report(
        before=artifacts,
        after=unauthorized,
        plan=SimpleNamespace(targets=[target]),
    )
    assert [issue.affected_section for issue in scope.issues] == [
        "insights_final[item=insight-1].metric.subject"
    ]


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        (
            "insights_final[item=insight-1]",
            "changed_path_outside_allowed_paths",
        ),
        (
            "insights_final[item=insight-1].metric.subject",
            "changed_path_outside_allowed_paths",
        ),
        (
            "key_figures[0].figure",
            "changed_path_outside_allowed_paths",
        ),
    ],
)
def test_model_cannot_replace_an_item_or_write_an_undeclared_path(
    path: str, reason: str
) -> None:
    artifacts = _insight_artifacts()
    issue = _insight_issue("so_what")
    target = _target(["insights_final[item=insight-1].so_what"], [issue])
    payload = _decision_payload(
        target=target,
        artifacts=artifacts,
        patches=[(path, "Out-of-scope replacement.")],
        evidence_ids=["retained-evidence"],
    )

    with pytest.raises(AppError) as error:
        _validated_repair_decision(
            payload,
            execution=_execution(target),
            current_artifacts=artifacts,
            grounding_package={"evidence_ids": ["retained-evidence"]},
        )

    assert error.value.context["reason"] == reason


def test_summary_claim_map_and_public_copy_failures_plan_as_separate_targets() -> None:
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "claim-one",
                    "claim": "The unsupported metric reached 25%.",
                    "evidence_id": "retained-evidence",
                }
            ],
            "executive_summary": "First public claim. Second public claim.",
        }
    }
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                message="The retained summary claim does not match its evidence.",
                severity="error",
                affected_section="summary.claim_evidence_map:claim-one.claim",
                rule_id="retained_claim.number_value_unit_match",
                entity_id="summary_claim:claim-one",
                evidence_ids=["retained-evidence"],
            ),
            ValidationIssue(
                message="The executive summary contains a failed retained claim.",
                severity="error",
                affected_section="summary.executive_summary",
                rule_id="retained_claim.soft_copy_provenance_integrity",
                evidence_ids=["retained-evidence"],
            ),
        ],
        artifacts=artifacts,
        broad_retry_available=False,
    )

    assert plan.mode == "targeted"
    assert len(plan.targets) == 2
    claim_target, copy_target = plan.targets
    assert claim_target.target_section == copy_target.target_section == "summary"
    assert [issue.rule_id for issue in claim_target.issues] == [
        "retained_claim.number_value_unit_match"
    ]
    assert claim_target.allowed_paths == [
        "summary.claim_evidence_map[item=claim-one].claim"
    ]
    assert [issue.rule_id for issue in copy_target.issues] == [
        "retained_claim.soft_copy_provenance_integrity"
    ]
    assert copy_target.allowed_paths == [
        "summary.executive_summary[claim_index=0]",
        "summary.executive_summary[claim_index=1]",
    ]


def test_summary_safe_removal_declares_the_claim_map_item_root() -> None:
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {"claim": "First retained claim."},
                {"claim": "Unsupported middle claim."},
                {"claim": "Last retained claim."},
            ]
        }
    }
    issue = RegenerationIssue(
        rule_id="grounding",
        affected_section="summary.claim_evidence_map:2.claim",
        message="The claim is not supported by retained evidence.",
        severity="error",
        entity_id="summary_claim:2",
    )

    assert _allowed_paths("summary", [issue], artifacts, "REMOVE_CLAIM") == [
        "summary.claim_evidence_map[1]"
    ]


def test_artifact_diff_identifies_one_removed_idless_claim_map_item() -> None:
    before = {
        "summary": {
            "claim_evidence_map": [
                {"claim": "First claim.", "evidence_id": "e1"},
                {"claim": "Removed claim.", "evidence_id": "e2"},
                {"claim": "Last claim.", "evidence_id": "e1"},
            ]
        }
    }
    after = {
        "summary": {
            "claim_evidence_map": [
                before["summary"]["claim_evidence_map"][0],
                before["summary"]["claim_evidence_map"][2],
            ]
        }
    }

    assert artifact_diff_paths(before, after) == {"summary.claim_evidence_map[1]"}
    scope = _scope_validation_report(
        before=before,
        after=after,
        plan=SimpleNamespace(
            targets=[SimpleNamespace(allowed_paths=["summary.claim_evidence_map[1]"])]
        ),
    )
    assert scope.status == "pass"


def test_artifact_diff_keeps_ambiguous_duplicate_removal_blocked() -> None:
    duplicate = {"claim": "Repeated claim.", "evidence_id": "e1"}
    before = {"summary": {"claim_evidence_map": [duplicate, duplicate]}}
    after = {"summary": {"claim_evidence_map": [duplicate]}}

    assert artifact_diff_paths(before, after) != {"summary.claim_evidence_map[0]"}
    scope = _scope_validation_report(
        before=before,
        after=after,
        plan=SimpleNamespace(
            targets=[SimpleNamespace(allowed_paths=["summary.claim_evidence_map[0]"])]
        ),
    )
    assert scope.status == "fail"


def test_explicit_summary_leaf_set_accepts_all_declared_paths_only() -> None:
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "claim-one",
                    "claim": "Original source claim.",
                    "evidence_id": "retained-evidence",
                },
                {
                    "id": "claim-two",
                    "claim": "Unchanged map sibling.",
                    "evidence_id": "other-evidence",
                },
            ],
            "executive_summary": "Original public claim. Unchanged public sibling.",
            "tldr": "Unchanged TLDR.",
            "card_tldr_compact": "Compact summary.",
        }
    }
    allowed_paths = [
        "summary.claim_evidence_map[item=claim-one].claim",
        "summary.executive_summary[claim_index=0]",
    ]
    target = RegenerationTarget(
        target_section="summary",
        regenerate_steps=["summary"],
        prompt_namespaces=[],
        issues=[
            RegenerationIssue(
                rule_id="retained_claim.number_value_unit_match",
                affected_section="summary.claim_evidence_map:claim-one.claim",
                message="The summary claim requires a synchronized public copy update.",
                severity="error",
                entity_id="summary_claim:claim-one",
                evidence_ids=["retained-evidence"],
            )
        ],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        allowed_paths=allowed_paths,
    )
    payload = _decision_payload(
        target=target,
        artifacts=artifacts,
        patches=[
            (allowed_paths[0], "Repaired source claim."),
            (allowed_paths[1], "Repaired public claim."),
        ],
        evidence_ids=["retained-evidence"],
    )

    decision = _validated_repair_decision(
        payload,
        execution=_execution(target),
        current_artifacts=artifacts,
        grounding_package={"evidence_ids": ["retained-evidence"]},
    )
    patched = _apply_repair_decision_patch(
        current_artifacts=artifacts,
        decision=decision,
    )

    assert decision.changed_paths == allowed_paths
    assert patched["summary"]["claim_evidence_map"][0]["claim"] == (
        "Repaired source claim."
    )
    assert (
        patched["summary"]["claim_evidence_map"][1]
        == artifacts["summary"]["claim_evidence_map"][1]
    )
    assert patched["summary"]["executive_summary"] == (
        "Repaired public claim. Unchanged public sibling."
    )
    assert patched["summary"]["tldr"] == artifacts["summary"]["tldr"]
    assert (
        patched["summary"]["card_tldr_compact"]
        == artifacts["summary"]["card_tldr_compact"]
    )
    scope = _scope_validation_report(
        before=artifacts,
        after=patched,
        plan=SimpleNamespace(targets=[target]),
    )
    assert scope.status == "pass"


def test_atomic_summary_plan_rejects_whole_family_replacement() -> None:
    artifacts = {
        "summary": {
            "claim_evidence_map": [{"id": "claim-one", "claim": "Original claim."}],
            "executive_summary": "Original executive summary.",
            "tldr": "Original TLDR.",
            "card_tldr_compact": "Compact sentence.",
        }
    }
    issue = RegenerationIssue(
        rule_id="retained_claim.number_value_unit_match",
        affected_section="summary.claim_evidence_map:claim-one.claim",
        message="The retained summary claim is unsupported.",
        severity="error",
        entity_id="summary_claim:claim-one",
    )
    target = RegenerationTarget(
        target_section="summary",
        regenerate_steps=["summary"],
        prompt_namespaces=[],
        issues=[issue],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        allowed_paths=["summary.claim_evidence_map[item=claim-one].claim"],
    )
    payload = _decision_payload(
        target=target,
        artifacts=artifacts,
        patches=[("summary", "Whole-family replacement.")],
    )

    with pytest.raises(AppError) as error:
        _validated_repair_decision(
            payload,
            execution=_execution(target),
            current_artifacts=artifacts,
            grounding_package={"evidence_ids": []},
        )

    assert error.value.context["reason"] == "changed_path_outside_allowed_paths"


@pytest.mark.parametrize(
    "path",
    ["insights_final[item=insight-1]", "insights_final"],
)
def test_declared_item_or_family_container_is_still_not_atomic(path: str) -> None:
    artifacts = _insight_artifacts()
    issue = _insight_issue("so_what")
    target = _target([path], [issue])
    payload = _decision_payload(
        target=target,
        artifacts=artifacts,
        patches=[(path, "Not an atomic leaf replacement.")],
        evidence_ids=["retained-evidence"],
    )

    with pytest.raises(AppError) as error:
        _validated_repair_decision(
            payload,
            execution=_execution(target),
            current_artifacts=artifacts,
            grounding_package={"evidence_ids": ["retained-evidence"]},
        )

    assert error.value.context["reason"] == "patch_target_not_atomic"
