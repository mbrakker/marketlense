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
