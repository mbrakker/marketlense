from __future__ import annotations

import hashlib
from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.contracts.regeneration import RegenerationIssue, RegenerationTarget
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.contracts.validation import ValidationIssue
from src.generators.report_regeneration_generator import (
    _apply_repair_decision_patch,
    _read_repair_path,
    _render_regeneration_model,
    _required_repair_protected_fields,
    _validate_model_writable_paths,
    _validated_repair_decision,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _allowed_paths,
    _build_regeneration_plan,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _scope_validation_report,
)
from src.services.schema_validator_service import validate_schema
from src.utils.errors import AppError


def _insight_artifacts() -> dict[str, object]:
    return {
        "insights_final": [
            {
                "id": "insight-1",
                "text": "Original insight.",
                "so_what": "Original implication.",
                "now_what": "Original action.",
                "evidence_id": "evidence-1",
                "evidence": "Retained source excerpt.",
                "evidence_spans": [{"start": 1, "end": 2}],
                "pages": [1],
                "metric": {
                    "value": "25%",
                    "unit": "",
                    "label": "Existing metric",
                    "subject": "protected subject",
                    "cohort": "protected cohort",
                    "denominator": "protected denominator",
                    "observation_status": "observed",
                },
            },
            {
                "id": "insight-2",
                "text": "Unrelated sibling insight.",
                "so_what": "Unrelated sibling implication.",
                "now_what": "Unrelated sibling action.",
                "evidence_id": "evidence-2",
                "metric": {
                    "value": "40%",
                    "unit": "sibling unit",
                    "subject": "sibling fact",
                },
            },
        ]
    }


def _insight_issue(field: str, *, insight_id: str = "insight-1") -> RegenerationIssue:
    return RegenerationIssue(
        rule_id="grounding",
        affected_section=f"insights:{insight_id}.{field}",
        entity_id=f"insight:{insight_id}:{field}",
        message="The retained field needs a grounded repair.",
        severity="error",
        evidence_ids=["retained-evidence"],
    )


def _execution(target: RegenerationTarget) -> SimpleNamespace:
    return SimpleNamespace(
        target=target,
        runtime=SimpleNamespace(request=SimpleNamespace(report_id="report-1")),
    )


def _decision_payload(
    *,
    target: RegenerationTarget,
    artifacts: dict[str, object],
    patches: list[tuple[str, object]],
    evidence_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "repair_action": target.repair_action,
        "repair_strategy": target.repair_strategy,
        "evidence_ids_used": evidence_ids or [],
        "changed_paths": [path for path, _ in patches],
        "minimal_patch": [
            {
                "op": "replace",
                "path": path,
                "value": value,
            }
            for path, value in patches
        ],
    }


def _target(paths: list[str], issues: list[RegenerationIssue]) -> RegenerationTarget:
    return RegenerationTarget(
        target_section="insights_bundle",
        regenerate_steps=["insights_final"],
        prompt_namespaces=[],
        issues=issues,
        repair_action="CORRECT_PROTECTED_FACT",
        repair_strategy="retained_evidence",
        allowed_paths=paths,
    )


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


def test_metric_protected_facts_remain_immutable_unless_exactly_targeted() -> None:
    artifacts = _insight_artifacts()
    value_path = "insights_final[item=insight-1].metric.value"
    value_issue = _insight_issue("metric.value")
    value_target = _target([value_path], [value_issue])
    protected = _required_repair_protected_fields(artifacts, value_target)

    assert "insights_final[item=insight-1].metric.subject" in protected
    assert "insights_final[item=insight-1].metric.cohort" in protected
    assert "insights_final[item=insight-1].metric.denominator" in protected
    assert "insights_final[item=insight-1].metric.observation_status" in protected

    subject_issue = _insight_issue("metric.subject")
    subject_path = "insights_final[item=insight-1].metric.subject"
    subject_target = _target([subject_path], [subject_issue])
    subject_protected = _required_repair_protected_fields(artifacts, subject_target)

    assert subject_path not in subject_protected
    assert value_path in subject_protected


def _soft_copy_claim(family: str, claim_id: str, text: str) -> SoftCopyClaimProvenance:
    return SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family=family,
        claim_id=claim_id,
        text_hash=hashlib.sha256(" ".join(text.split()).encode()).hexdigest(),
        classification="interpretive",
        evidence_ids=("retained-evidence",),
        source_spans=(),
        producing_prompt_identity={"namespace": f"report_vs/artifacts/{family}"},
        generation_attempt=1,
        regeneration_attempt=0,
    )


def _model_repair_path_case(case_id: str) -> dict[str, object]:
    artifacts: dict[str, object] = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "summary-claim-1",
                    "claim": "Original summary map claim.",
                    "evidence_id": "retained-evidence",
                    "evidence": "Retained source excerpt.",
                },
                {
                    "id": "summary-claim-2",
                    "claim": "Unchanged summary map sibling.",
                    "evidence_id": "sibling-evidence",
                    "evidence": "Other retained source excerpt.",
                },
            ],
            "executive_summary": "Original summary claim. Unchanged summary sibling.",
            "tldr": "Original TLDR claim. Unchanged TLDR sibling.",
            "card_tldr_compact": "Compact summary.",
        },
        **_insight_artifacts(),
        "insights_candidates": [
            {
                "id": "candidate-1",
                "text": "Original candidate insight.",
                "evidence_id": "retained-evidence",
                "metric": {"value": "15%", "unit": "percent"},
            },
            {
                "id": "candidate-2",
                "text": "Unchanged candidate sibling.",
                "evidence_id": "sibling-evidence",
                "metric": {"value": "20%", "unit": "points"},
            },
        ],
        "quotes_final": [
            {
                "id": "quote-1",
                "text": "Original quote text.",
                "evidence_id": "retained-evidence",
            },
            {
                "id": "quote-2",
                "text": "Unchanged quote sibling.",
                "evidence_id": "sibling-evidence",
            },
        ],
        "expert_comment": "Original expert claim. Unchanged expert sibling.",
        "linkedin_post": "Original LinkedIn claim. Unchanged LinkedIn sibling.",
    }
    provenance = [
        _soft_copy_claim(
            "summary", "soft_copy:summary:executive-claim", "Original summary claim."
        ),
        _soft_copy_claim(
            "summary", "soft_copy:summary:tldr-claim", "Original TLDR claim."
        ),
        _soft_copy_claim(
            "expert_comment",
            "soft_copy:expert_comment:claim-1",
            "Original expert claim.",
        ),
        _soft_copy_claim(
            "expert_comment",
            "soft_copy:expert_comment:claim-2",
            "Unchanged expert sibling.",
        ),
        _soft_copy_claim(
            "linkedin_post",
            "soft_copy:linkedin_post:claim-1",
            "Original LinkedIn claim.",
        ),
        _soft_copy_claim(
            "linkedin_post",
            "soft_copy:linkedin_post:claim-2",
            "Unchanged LinkedIn sibling.",
        ),
    ]
    artifacts["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        provenance
    )

    if case_id == "summary_claim":
        family = "summary"
        issue = RegenerationIssue(
            rule_id="retained_claim.number_value_unit_match",
            affected_section="summary.claim_evidence_map:summary-claim-1.claim",
            entity_id="summary_claim:summary-claim-1",
            message="The summary map claim needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = "summary.claim_evidence_map[item=summary-claim-1].claim"
        sibling = "summary.claim_evidence_map[item=summary-claim-2].claim"
        parent = "summary.claim_evidence_map[item=summary-claim-1]"
    elif case_id == "summary_tldr":
        family = "summary"
        issue = RegenerationIssue(
            rule_id="grounding",
            affected_section="summary.tldr",
            entity_id="soft_copy:summary:tldr-claim",
            message="The TLDR claim needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = "summary.tldr[claim_index=0]"
        sibling = "summary.tldr[claim_index=1]"
        parent = "summary.tldr"
    elif case_id == "summary_executive":
        family = "summary"
        issue = RegenerationIssue(
            rule_id="grounding",
            affected_section="summary.executive_summary",
            entity_id="soft_copy:summary:executive-claim",
            message="The executive summary claim needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = "summary.executive_summary[claim_index=0]"
        sibling = "summary.executive_summary[claim_index=1]"
        parent = "summary.executive_summary"
    elif case_id in {
        "insight_text",
        "insight_so_what",
        "insight_metric_value",
        "insight_metric_unit",
        "candidate_text",
        "candidate_metric_value",
        "candidate_metric_unit",
    }:
        family = "insights_bundle"
        field, rule_id = {
            "insight_text": ("text", "grounding"),
            "insight_so_what": ("so_what", "grounding"),
            "insight_metric_value": (
                "metric.value",
                "retained_claim.protected_fact_value_consistency",
            ),
            "insight_metric_unit": (
                "metric.unit",
                "retained_claim.protected_fact_unit_currency_consistency",
            ),
            "candidate_text": ("text", "grounding"),
            "candidate_metric_value": (
                "metric.value",
                "retained_claim.protected_fact_value_consistency",
            ),
            "candidate_metric_unit": (
                "metric.unit",
                "retained_claim.protected_fact_unit_currency_consistency",
            ),
        }[case_id]
        root, identity = (
            ("insights_candidates", "candidate-1")
            if case_id.startswith("candidate_")
            else ("insights_final", "insight-1")
        )
        issue = RegenerationIssue(
            rule_id=rule_id,
            affected_section=f"insights:{identity}.{field}",
            entity_id=f"insight:{identity}:{field}",
            message="The insight leaf needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = f"{root}[item={identity}].{field}"
        sibling_identity = (
            "candidate-2" if root == "insights_candidates" else "insight-2"
        )
        sibling = f"{root}[item={sibling_identity}].{field}"
        parent = f"{root}[item={identity}]"
    elif case_id == "quote_text":
        family = "quotes"
        issue = RegenerationIssue(
            rule_id="grounding",
            affected_section="quotes_final[0].text",
            entity_id="quote:quote-1:text",
            message="The quote text needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = "quotes_final[item=quote-1].text"
        sibling = "quotes_final[item=quote-2].text"
        parent = "quotes_final[item=quote-1]"
    elif case_id == "expert_claim":
        family = "expert_comment"
        issue = RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            entity_id="soft_copy:expert_comment:claim-1",
            message="The Expert View claim needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = "expert_comment[claim_index=0]"
        sibling = "expert_comment[claim_index=1]"
        parent = "expert_comment"
    else:
        family = "linkedin_post"
        issue = RegenerationIssue(
            rule_id="grounding",
            affected_section="linkedin_post",
            entity_id="soft_copy:linkedin_post:claim-1",
            message="The LinkedIn claim needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = "linkedin_post[claim_index=0]"
        sibling = "linkedin_post[claim_index=1]"
        parent = "linkedin_post"
    return {
        "artifacts": artifacts,
        "family": family,
        "issue": issue,
        "expected": expected,
        "sibling": sibling,
        "parent": parent,
    }


@pytest.mark.parametrize(
    "case_id",
    [
        "summary_claim",
        "summary_tldr",
        "summary_executive",
        "insight_text",
        "insight_so_what",
        "insight_metric_value",
        "insight_metric_unit",
        "candidate_text",
        "candidate_metric_value",
        "candidate_metric_unit",
        "quote_text",
        "expert_claim",
        "linkedin_claim",
    ],
)
def test_model_repair_contract_is_string_atomic_for_every_model_family(
    case_id: str,
) -> None:
    case = _model_repair_path_case(case_id)
    artifacts = case["artifacts"]
    issue = case["issue"]
    family = str(case["family"])
    expected = str(case["expected"])
    sibling = str(case["sibling"])
    parent = str(case["parent"])
    paths = _allowed_paths(family, [issue], artifacts, "REGENERATE_ITEM")
    assert paths == [expected]
    target = RegenerationTarget(
        target_section=family,
        regenerate_steps=[family],
        prompt_namespaces=[],
        issues=[issue],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        allowed_paths=paths,
    )
    _validate_model_writable_paths(
        execution=_execution(target),
        target=target,
        current_artifacts=artifacts,
    )

    replacement = "Repaired scalar claim."
    payload = _decision_payload(
        target=target,
        artifacts=artifacts,
        patches=[(expected, replacement)],
        evidence_ids=["retained-evidence"],
    )
    _validate_repair_schema(payload)
    before_found, before_sibling = _read_repair_path(artifacts, sibling)
    assert before_found
    decision = _validated_repair_decision(
        payload,
        execution=_execution(target),
        current_artifacts=artifacts,
        grounding_package={"evidence_ids": ["retained-evidence"]},
    )
    patched = _apply_repair_decision_patch(
        current_artifacts=artifacts, decision=decision
    )
    found, applied = _read_repair_path(patched, expected)
    after_found, after_sibling = _read_repair_path(patched, sibling)
    assert found and applied == replacement
    assert after_found and after_sibling == before_sibling
    assert decision.changed_paths == [expected]
    assert decision.minimal_patch[0].value == replacement
    assert (
        _scope_validation_report(
            before=artifacts,
            after=patched,
            plan=SimpleNamespace(targets=[target]),
        ).status
        == "pass"
    )

    for rejected_value in ({"claim": "over-broad"}, ["over-broad"]):
        invalid_payload = _decision_payload(
            target=target,
            artifacts=artifacts,
            patches=[(expected, rejected_value)],
            evidence_ids=["retained-evidence"],
        )
        with pytest.raises(AppError):
            _validate_repair_schema(invalid_payload)
        with pytest.raises(AppError) as error:
            _validated_repair_decision(
                invalid_payload,
                execution=_execution(target),
                current_artifacts=artifacts,
                grounding_package={"evidence_ids": ["retained-evidence"]},
            )
        assert error.value.context["reason"] == "decision_contract_invalid"

    for out_of_scope_path in (parent, sibling):
        invalid_payload = _decision_payload(
            target=target,
            artifacts=artifacts,
            patches=[(out_of_scope_path, "Out-of-scope replacement.")],
            evidence_ids=["retained-evidence"],
        )
        with pytest.raises(AppError) as error:
            _validated_repair_decision(
                invalid_payload,
                execution=_execution(target),
                current_artifacts=artifacts,
                grounding_package={"evidence_ids": ["retained-evidence"]},
            )
        assert error.value.context["reason"] == "changed_path_outside_allowed_paths"


def _validate_repair_schema(decision: dict[str, object]) -> None:
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0",
            payload={"repair_decision": decision},
            schema_name="regeneration_repair_decision",
        ),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )


def test_coupled_insight_metric_leaves_remain_explicitly_repairable_together() -> None:
    artifacts = _insight_artifacts()
    issue = RegenerationIssue(
        rule_id="metrics",
        affected_section="insights:insight-1.metric",
        entity_id="insight:insight-1:metric",
        message="The retained metric value and unit require a coupled repair.",
        severity="error",
        evidence_ids=["retained-evidence"],
    )
    paths = _allowed_paths("insights_bundle", [issue], artifacts, "REGENERATE_ITEM")
    expected = [
        "insights_final[item=insight-1].metric.unit",
        "insights_final[item=insight-1].metric.value",
    ]
    assert paths == expected
    target = _target(paths, [issue])
    replacements = [
        (paths[0], "percentage points"),
        (paths[1], "30%"),
    ]
    payload = _decision_payload(
        target=target,
        artifacts=artifacts,
        patches=replacements,
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

    assert decision.changed_paths == expected
    assert patched["insights_final"][0]["metric"]["unit"] == "percentage points"
    assert patched["insights_final"][0]["metric"]["value"] == "30%"
    assert (
        patched["insights_final"][0]["text"] == artifacts["insights_final"][0]["text"]
    )
    assert patched["insights_final"][1] == artifacts["insights_final"][1]


def test_model_writable_path_preflight_fails_before_provider_for_non_string_leaf() -> (
    None
):
    artifacts = {
        "insights_final": [
            {"id": "insight-1", "text": "Claim.", "metric": {"score": 1.5}}
        ]
    }
    issue = _insight_issue("metric.score")
    target = _target(["insights_final[item=insight-1].metric.score"], [issue])
    state = SimpleNamespace(
        summary={},
        insights_candidates=[],
        insights_final=artifacts["insights_final"],
        quotes_final=[],
        expert_comment="",
        linkedin_post="",
    )
    execution = SimpleNamespace(
        runtime=SimpleNamespace(
            request=SimpleNamespace(report_id="report-1"),
            openai_client=None,
        ),
        state=state,
        target=target,
    )

    with pytest.raises(AppError) as error:
        _render_regeneration_model(
            execution=execution,
            namespace="report_vs/artifacts/regenerate/insights_final",
            variables={},
            ctx=None,
        )

    assert error.value.context["reason"] == "model_writable_path_not_string"
    assert error.value.context["path"] == "insights_final[item=insight-1].metric.score"


def test_model_writable_path_preflight_rejects_ambiguous_and_duplicate_paths() -> None:
    artifacts = {
        "insights_final": [
            {"id": "duplicate", "text": "First."},
            {"id": "duplicate", "text": "Second."},
        ]
    }
    issue = _insight_issue("text")
    path = "insights_final[item=duplicate].text"
    ambiguous = _target([path], [issue])
    state = SimpleNamespace(
        summary={},
        insights_candidates=[],
        insights_final=artifacts["insights_final"],
        quotes_final=[],
        expert_comment="",
        linkedin_post="",
    )
    execution = SimpleNamespace(
        runtime=SimpleNamespace(
            request=SimpleNamespace(report_id="report-1"), openai_client=None
        ),
        state=state,
        target=ambiguous,
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

    duplicate_paths = _target(["insights_final[0].text"] * 2, [issue])
    execution.target = duplicate_paths
    with pytest.raises(AppError) as duplicate_error:
        _render_regeneration_model(
            execution=execution,
            namespace="report_vs/artifacts/regenerate/insights_final",
            variables={},
            ctx=None,
        )
    assert duplicate_error.value.context["reason"] == "model_writable_paths_not_unique"


def test_quarantined_evidence_remains_rejected_for_an_allowed_leaf() -> None:
    artifacts = _insight_artifacts()
    issue = _insight_issue("so_what")
    target = _target(["insights_final[item=insight-1].so_what"], [issue])
    target = RegenerationTarget(
        **{
            **target.__dict__,
            "quarantined_evidence_ids": ["quarantined-evidence"],
        }
    )
    payload = _decision_payload(
        target=target,
        artifacts=artifacts,
        patches=[("insights_final[item=insight-1].so_what", "Unsupported claim.")],
        evidence_ids=["quarantined-evidence"],
    )

    with pytest.raises(AppError) as error:
        _validated_repair_decision(
            payload,
            execution=_execution(target),
            current_artifacts=artifacts,
            grounding_package={
                "evidence_ids": ["quarantined-evidence"],
                "quarantined_evidence_ids": ["quarantined-evidence"],
            },
        )

    assert error.value.context["reason"] == "evidence_not_retained_or_quarantined"
