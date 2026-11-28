from types import SimpleNamespace

from src.orchestrators._report_analysis_orchestrator.validation import (
    _scope_validation_report,
)
from src.utils.artifact_diff import artifact_diff_paths


def test_multiple_exact_idless_removals_use_original_positions() -> None:
    before = {
        "summary": {
            "claim_evidence_map": [
                {"claim": "First", "evidence_id": "e1"},
                {"claim": "Remove one", "evidence_id": "e2"},
                {"claim": "Remove two", "evidence_id": "e3"},
                {"claim": "Last", "evidence_id": "e4"},
            ]
        }
    }
    after = {
        "summary": {
            "claim_evidence_map": [
                {"claim": "First", "evidence_id": "e1"},
                {"claim": "Last", "evidence_id": "e4"},
            ]
        }
    }
    paths = {"summary.claim_evidence_map[1]", "summary.claim_evidence_map[2]"}

    assert artifact_diff_paths(before, after) == paths
    scope = _scope_validation_report(
        before=before,
        after=after,
        plan=SimpleNamespace(targets=[SimpleNamespace(allowed_paths=sorted(paths))]),
    )
    assert scope.status == "pass"
    one_allowed = _scope_validation_report(
        before=before,
        after=after,
        plan=SimpleNamespace(
            targets=[SimpleNamespace(allowed_paths=["summary.claim_evidence_map[1]"])]
        ),
    )
    assert one_allowed.status == "fail"


def test_ambiguous_multiple_idless_removal_does_not_grant_scope() -> None:
    duplicate = {"claim": "Same", "evidence_id": "e1"}
    before = {
        "summary": {"claim_evidence_map": [duplicate, duplicate, {"claim": "Other"}]}
    }
    after = {"summary": {"claim_evidence_map": [duplicate]}}
    scope = _scope_validation_report(
        before=before,
        after=after,
        plan=SimpleNamespace(
            targets=[
                SimpleNamespace(
                    allowed_paths=[
                        "summary.claim_evidence_map[0]",
                        "summary.claim_evidence_map[2]",
                    ]
                )
            ]
        ),
    )
    assert scope.status == "fail"


def test_declared_summary_reconstruction_does_not_authorize_sibling_changes() -> None:
    before = {"summary": {"executive_summary": "First sentence. Second sentence."}}
    plan = SimpleNamespace(
        targets=[
            SimpleNamespace(
                target_section="summary",
                repair_action="REGENERATE_ITEM",
                allowed_paths=["summary.executive_summary[claim_index=1]"],
            )
        ]
    )
    repaired = {"summary": {"executive_summary": "First sentence. Improved second."}}
    tampered = {"summary": {"executive_summary": "Changed first. Improved second."}}
    assert (
        _scope_validation_report(
            before=before,
            after=repaired,
            plan=plan,
            deterministic_mutation_paths=["summary.executive_summary"],
        ).status
        == "pass"
    )
    assert (
        _scope_validation_report(
            before=before,
            after=tampered,
            plan=plan,
            deterministic_mutation_paths=["summary.executive_summary"],
        ).status
        == "fail"
    )
    malformed_before = {
        **before,
        "soft_copy_claim_provenance": {"claims": "not-a-claim-list"},
    }
    malformed_repaired = {
        **repaired,
        "soft_copy_claim_provenance": {"claims": "not-a-claim-list"},
    }
    assert (
        _scope_validation_report(
            before=malformed_before,
            after=malformed_repaired,
            plan=plan,
            deterministic_mutation_paths=["summary.executive_summary"],
        ).status
        == "fail"
    )
