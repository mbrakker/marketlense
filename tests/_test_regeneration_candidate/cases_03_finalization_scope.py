# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_scope_rejects_canonical_projection_when_its_source_did_not_change() -> None:
    insight = {
        "id": "one",
        "text": "Retail media adoption reached 42% among merchants.",
        "evidence_id": "f1",
        "metric": {
            "label": "Retail media adoption",
            "value": "42%",
            "confidence": "high",
        },
    }
    before = {"insights_final": [insight], "metric_spine": []}
    candidate = deepcopy(before)
    candidate["metric_spine"] = derive_metric_spine_from_insights([insight])
    plan = SimpleNamespace(
        targets=[
            SimpleNamespace(allowed_paths=["insights_final[item=one].metric.value"])
        ]
    )

    verified_roots, issues = _verify_derived_artifact_roots(
        current_artifacts=before,
        candidate_artifacts=candidate,
        evidence_packs={},
    )
    assert not issues
    assert "metric_spine" in verified_roots

    scope = _scope_validation_report(
        before=before,
        after=candidate,
        plan=plan,
        verified_derived_roots=verified_roots,
    )

    assert scope.status == "fail"
    assert scope.issues
    assert all(
        issue.affected_section.startswith("metric_spine") for issue in scope.issues
    )


def test_soft_copy_repair_allows_rebuilt_family_status_with_preserved_summary() -> None:
    summary = {"executive_summary": "A retained report overview."}
    insights = [{"id": "insight-1", "text": "A source-backed finding."}]
    before = {
        "summary": summary,
        "insights_candidates": [],
        "insights_final": insights,
        "quotes_final": [],
        "expert_comment": "Original expert comment.",
        "linkedin_post": "Original LinkedIn post.",
    }
    before["family_status"] = build_artifact_family_status(
        summary=summary,
        insights_candidates=[],
        insights_final=insights,
        quotes_final=[],
        expert_comment=before["expert_comment"],
        linkedin_post=before["linkedin_post"],
    )
    # Legacy report status is intentionally retained while summary is unchanged.
    before["family_status"]["summary"] = {
        "schema_version": "1.0",
        "family": "summary",
        "source": "artifact",
        "status": "abstained",
        "confidence_score": 1.0,
        "policy_action": "abstain",
        "reason": "summary_no_short_direct_claim",
    }
    before["family_status"]["expert_comment"]["confidence_score"] = 1.0
    before["family_status"]["linkedin_post"]["confidence_score"] = 1.0

    candidate = deepcopy(before)
    candidate["expert_comment"] = "Repaired expert comment."
    candidate["family_status"] = build_artifact_family_status(
        summary=summary,
        insights_candidates=[],
        insights_final=insights,
        quotes_final=[],
        expert_comment=candidate["expert_comment"],
        linkedin_post=candidate["linkedin_post"],
    )
    candidate["family_status"]["summary"] = before["family_status"]["summary"]

    verified_roots, issues = _verify_derived_artifact_roots(
        current_artifacts=before,
        candidate_artifacts=candidate,
        evidence_packs={},
    )

    assert not issues
    assert "family_status" in verified_roots
    scope = _scope_validation_report(
        before=before,
        after=candidate,
        plan=SimpleNamespace(
            targets=[SimpleNamespace(allowed_paths=["expert_comment[claim_index=0]"])]
        ),
        verified_derived_roots=verified_roots,
    )
    assert scope.status == "pass"


def test_scope_allows_transitive_projection_from_changed_editorial_plan() -> None:
    from src.generators._artifact_generator.storage import (
        build_canonical_regeneration_derived_artifacts,
    )

    insights = [
        {
            "id": "retail-media-adoption",
            "text": "Retail media adoption reached 42% among merchants.",
            "evidence": "Retail media adoption reached 42% among merchants.",
            "evidence_id": "f1",
            "pages": [7],
            "metric": {
                "label": "Retail media adoption",
                "value": "42%",
                "confidence": "high",
                "segment": "merchants",
            },
        },
        {
            "id": "commerce-budget-shift",
            "text": "Commerce media budgets reached 27% among retailers.",
            "evidence": "Commerce media budgets reached 27% among retailers.",
            "evidence_id": "f2",
            "pages": [9],
            "metric": {
                "label": "Commerce media budgets",
                "value": "27%",
                "confidence": "high",
                "segment": "retailers",
            },
        },
    ]
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": insights[0]["evidence"],
                    "pages": [7],
                },
                {
                    "id": "f2",
                    "text": insights[1]["evidence"],
                    "pages": [9],
                },
            ]
        }
    }
    roots = {"metric_spine", "key_figures", "chart_insight_cards"}
    before = {
        "summary": {},
        "insights_final": insights,
        "editorial_plan": {
            "themes": [
                {"priority": 1, "evidence_ids": ["f1"]},
                {"priority": 2, "evidence_ids": ["f2"]},
            ]
        },
        "quotes_final": [],
    }
    before.update(
        build_canonical_regeneration_derived_artifacts(
            artifacts=before, evidence_packs=evidence_packs, roots=roots
        )
    )
    candidate = deepcopy(before)
    candidate["editorial_plan"]["themes"][0]["priority"] = 5
    candidate["editorial_plan"]["themes"][1]["priority"] = 1
    candidate.update(
        build_canonical_regeneration_derived_artifacts(
            artifacts=candidate, evidence_packs=evidence_packs, roots=roots
        )
    )
    plan = SimpleNamespace(
        targets=[
            SimpleNamespace(
                allowed_paths=[
                    "editorial_plan.themes[0].priority",
                    "editorial_plan.themes[1].priority",
                ]
            )
        ]
    )

    verified_roots, issues = _verify_derived_artifact_roots(
        current_artifacts=before,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
    )
    assert not issues
    assert {"metric_spine", "key_figures", "chart_insight_cards"}.issubset(
        verified_roots
    )
    assert before["chart_insight_cards"] != candidate["chart_insight_cards"]

    scope = _scope_validation_report(
        before=before,
        after=candidate,
        plan=plan,
        verified_derived_roots=verified_roots,
    )

    assert scope.status == "pass"

    candidate["chart_insight_cards"][0]["caption"] = "Tampered projection"
    verified_roots, issues = _verify_derived_artifact_roots(
        current_artifacts=before,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
    )
    assert any(
        issue.rule_id == "regeneration_derived_projection"
        and issue.affected_section == "chart_insight_cards"
        for issue in issues
    )
    assert "chart_insight_cards" not in verified_roots
    assert (
        _scope_validation_report(
            before=before,
            after=candidate,
            plan=plan,
            verified_derived_roots=verified_roots,
        ).status
        == "fail"
    )
