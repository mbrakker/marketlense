from copy import deepcopy
from types import SimpleNamespace

from src.generators.validation.regeneration_candidate import (
    validate_regeneration_candidate,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _scope_validation_report,
    _verified_dependent_paths,
)
from tests._test_regeneration_candidate._shared import (
    _baseline_retained_claim_warnings,
    _claim_for_family,
    _complete_repair_selection,
    _ctx,
    _soft_copy_artifacts,
    _soft_copy_claim,
)


def _candidate():
    current, candidate, evidence = _soft_copy_artifacts()
    original = _claim_for_family(current, "linkedin_post")
    candidate["linkedin_post"] = "Generation Q developed in digital spaces."
    repaired = _soft_copy_claim(
        family="linkedin_post", text=candidate["linkedin_post"], regeneration_attempt=1
    )
    repaired["repaired_from_claim_id"] = original["claim_id"]
    candidate["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in candidate["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "linkedin_post"
    ] + [repaired]
    candidate["_repair_evidence_selection"] = {
        f"linkedin_post:{original['claim_id']}": _complete_repair_selection(
            original_claim_id=str(original["claim_id"]),
            repaired_claim_id=str(repaired["claim_id"]),
        )
    }
    return current, candidate, evidence


def _evaluate(current, candidate, evidence):
    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence,
        ctx=_ctx(),
        baseline_retained_claim_severities=_baseline_retained_claim_warnings(
            current, evidence
        ),
    )
    plan = SimpleNamespace(
        targets=[SimpleNamespace(allowed_paths=["linkedin_post[claim_index=0]"])]
    )
    scope = _scope_validation_report(
        before=current,
        after=candidate,
        plan=plan,
        verified_derived_roots=result.verified_derived_roots,
    )
    audited = _verified_dependent_paths(
        before=current,
        after=candidate,
        plan=plan,
        verified_derived_roots=result.verified_derived_roots,
    )
    return result, scope, audited


def test_invalid_sibling_provenance_does_not_authorize_scoped_rows():
    current, candidate, evidence = _candidate()
    expert = _claim_for_family(candidate, "expert_comment")
    candidate["_repair_evidence_selection"][f"expert_comment:{expert['claim_id']}"] = {
        "quarantined_evidence_ids": ["qc_001"]
    }
    result, scope, audited = _evaluate(current, candidate, evidence)
    assert not result.passed
    assert any("quarantined" in issue.message for issue in result.issues)
    assert any(
        issue.affected_section.startswith("soft_copy_claim_provenance")
        for issue in scope.issues
    )
    assert (
        len([path for path in audited if path.startswith("soft_copy_claim_provenance")])
        == 0
    )


def test_scoped_repair_rejects_unscoped_sibling_binding_in_scope_and_audit():
    current, candidate, evidence = _candidate()
    sibling = _soft_copy_claim(family="summary", text="A summary sentence.")
    current["soft_copy_claim_provenance"]["claims"].append(sibling)
    candidate["soft_copy_claim_provenance"]["claims"].append(deepcopy(sibling))
    changed = _claim_for_family(candidate, "summary")
    changed["evidence_ids"] = ["qc_002"]
    changed["source_spans"][0]["evidence_id"] = "qc_002"
    result, scope, audited = _evaluate(current, candidate, evidence)
    assert result.passed
    prefix = f"soft_copy_claim_provenance.claims[item={sibling['claim_id']}]"
    assert any(issue.affected_section.startswith(prefix) for issue in scope.issues)
    assert not any(path.startswith(prefix) for path in audited)


def test_explicit_family_repair_accepts_verified_changed_claim_rows():
    current, candidate, evidence = _candidate()
    result, _, _ = _evaluate(current, candidate, evidence)
    assert result.passed
    scope = _scope_validation_report(
        before=current,
        after=candidate,
        plan=SimpleNamespace(
            targets=[SimpleNamespace(allowed_paths=["linkedin_post"])]
        ),
        verified_derived_roots=result.verified_derived_roots,
        declared_family_roots=frozenset({"linkedin_post"}),
    )
    assert scope.status == "pass"


def test_duplicate_claim_identity_fails_closed():
    current, candidate, evidence = _candidate()
    candidate["soft_copy_claim_provenance"]["claims"].append(
        deepcopy(_claim_for_family(candidate, "linkedin_post"))
    )
    _, scope, audited = _evaluate(current, candidate, evidence)
    assert any(
        issue.affected_section.startswith("soft_copy_claim_provenance")
        for issue in scope.issues
    )
    assert not any(path.startswith("soft_copy_claim_provenance") for path in audited)


def test_unscoped_sibling_in_same_family_is_not_authorized():
    current, candidate, evidence = _candidate()
    sibling_text = "A separate sentence remains unchanged."
    sibling = _soft_copy_claim(family="linkedin_post", text=sibling_text)
    current["linkedin_post"] += " " + sibling_text
    candidate["linkedin_post"] += " " + sibling_text
    current["soft_copy_claim_provenance"]["claims"].append(sibling)
    candidate["soft_copy_claim_provenance"]["claims"].append(deepcopy(sibling))
    changed = candidate["soft_copy_claim_provenance"]["claims"][-1]
    changed["evidence_ids"] = ["qc_002"]
    changed["source_spans"][0]["evidence_id"] = "qc_002"

    _, scope, audited = _evaluate(current, candidate, evidence)
    prefix = f"soft_copy_claim_provenance.claims[item={sibling['claim_id']}]"
    assert any(issue.affected_section.startswith(prefix) for issue in scope.issues)
    assert not any(path.startswith(prefix) for path in audited)
