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
