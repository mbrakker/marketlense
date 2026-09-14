import json
from pathlib import Path
from typing import Any

from src.generators.artifact_normalization import normalize_artifact_evidence_ids


_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "a21_bfab37bb_evidence_closure.json"
)


def _closure_fixture() -> dict[str, Any]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _evidence_packs_for(reference: dict[str, str]) -> dict[str, Any]:
    canonical_id = reference["canonical_id"]
    if reference["source_pack"] == "findings":
        return {"findings": {"findings": [{"id": canonical_id}]}}
    return {"quote_candidates": {"quote_candidates": [{"id": canonical_id}]}}


def test_retained_a21_editorial_plan_reference_aliases_are_canonicalized() -> None:
    """Fails if editorial-plan references bypass the strict alias boundary."""
    fixture = _closure_fixture()

    for case in fixture["schema_reference_missing"]:
        for reference in case["retained_reference_aliases"]:
            editorial_plan = {"themes": [{"evidence_ids": [reference["alias"]]}]}

            stats = normalize_artifact_evidence_ids(
                summary={},
                editorial_plan=editorial_plan,
                insights_candidates=[],
                insights_final=[],
                quotes_final=[],
                doc_map={},
                evidence_packs=_evidence_packs_for(reference),
            )

            assert editorial_plan["themes"][0]["evidence_ids"] == [
                reference["canonical_id"]
            ]
            assert stats["normalized_count"] == 1
            assert stats["unresolved_count"] == 0


def test_retained_a21_queue_wrapper_classification_is_explicit_about_gaps() -> None:
    fixture = _closure_fixture()
    cases = fixture["workflow_queue_report_stage_failed"]

    recovered = [case for case in cases if case["recovery_status"] == "recovered"]
    unresolved = [case for case in cases if case["recovery_status"] == "unresolved"]

    assert [case["underlying_error_code"] for case in recovered] == [
        "publish_readiness_failed",
        "publish_readiness_failed",
    ]
    assert all(case["retained_rule_ids"] for case in recovered)
    assert len(unresolved) == 3
    assert all("underlying_error_code" not in case for case in unresolved)
    assert all(case["unresolved_reason"] for case in unresolved)
