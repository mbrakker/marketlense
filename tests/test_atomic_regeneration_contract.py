from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.contracts.regeneration import RegenerationIssue, RegenerationTarget
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.contracts.validation import ValidationIssue
from src.generators.report_regeneration_generator import (
    _apply_repair_decision_patch,
    _render_regeneration_model,
    _required_repair_protected_fields,
    _validated_repair_decision,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _allowed_paths,
    _build_regeneration_plan,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _scope_validation_report,
)
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
                "metric": {"value": "40%", "subject": "sibling fact"},
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
    protected_fields: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "repair_action": target.repair_action,
        "repair_strategy": target.repair_strategy,
        "evidence_ids_used": evidence_ids or [],
        "protected_fields": (
            protected_fields
            if protected_fields is not None
            else _required_repair_protected_fields(artifacts, target)
        ),
        "changed_paths": [path for path, _ in patches],
        "minimal_patch": [
            {
                "op": "replace",
                "path": path,
                "value_json": json.dumps(value, ensure_ascii=False),
            }
            for path, value in patches
        ],
        "claim_provenance": [],
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

    paths = _allowed_paths(
        "expert_comment", [issue], artifacts, "REGENERATE_ITEM"
    )
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
        for index, sentence in enumerate(
            ("First claim.", "Second claim."), start=1
        )
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
        _allowed_paths("insights_bundle", [issue], artifacts, "REGENERATE_ITEM")
        == []
    )
    assert _required_repair_protected_fields(artifacts, target) == []

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

    assert error.value.context["reason"] == "repair_scope_partition_invalid"


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
        patched["insights_final"][0]["text"]
        == artifacts["insights_final"][0]["text"]
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
        patches=[(path, {"id": "changed", "text": "over-broad"})],
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


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("insights_final[item=insight-1]", {"id": "changed"}),
        ("insights_final", [{"id": "changed"}]),
    ],
)
def test_declared_item_or_family_container_is_still_not_atomic(
    path: str, value: object
) -> None:
    artifacts = _insight_artifacts()
    issue = _insight_issue("so_what")
    target = _target([path], [issue])
    payload = _decision_payload(
        target=target,
        artifacts=artifacts,
        patches=[(path, value)],
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
