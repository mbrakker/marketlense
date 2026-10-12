# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_atomic_regeneration_contract.py"
)

from ._split_support_test_atomic_regeneration_contract import *  # noqa: F401,F403


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


def test_changed_paths_are_derived_from_authorized_patch_operations() -> None:
    artifacts = _insight_artifacts()
    issue = _insight_issue("text")
    path = "insights_final[item=insight-1].text"
    target = _target([path], [issue])
    payload = _decision_payload(
        target=target,
        artifacts=artifacts,
        patches=[(path, "A source-backed replacement.")],
        evidence_ids=["retained-evidence"],
    )
    payload["changed_paths"] = ["insights_final[item=insight-1].so_what"]

    decision = _validated_repair_decision(
        payload,
        execution=_execution(target),
        current_artifacts=artifacts,
        grounding_package={"evidence_ids": ["retained-evidence"]},
    )

    assert decision.changed_paths == [path]
    assert decision.minimal_patch[0].path == path
    patched = _apply_repair_decision_patch(
        current_artifacts=artifacts,
        decision=decision,
    )
    assert patched["insights_final"][0]["text"] == "A source-backed replacement."
    assert patched["insights_final"][0]["so_what"] == "Original implication."


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
        grounding_package={},
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
        grounding_package={},
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
