from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.quality.replay_verified_claims_step2 import _explicit_source_records
from scripts.quality.review_verified_claims_step2_editorial import (
    _acceptance_summary,
    _artifact_context,
    _base_record,
    _reconcile_source_pages,
    _record_summary,
    _validate_cohort_identity_coverage,
    _validate_result_binding,
    _validate_review_payload,
)

_DIMENSIONS = (
    "factual_fidelity",
    "analytical_validity",
    "specificity",
    "commercial_relevance",
    "editorial_quality",
    "selection_quality",
)


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "decision": "approved",
        "explanation": (
            "The final claim is specific, useful, and grounded in the supplied page."
        ),
        "source_grounded_explanation": (
            "Physical page 12 reports the observed cohort relationship and the "
            "stated period; "
            "that bounded pattern supports the commercial implication."
        ),
        "supporting_physical_pages": [12],
        "source_truth_notes_by_page": {
            "12": (
                "Physical page 12 reports the observed cohort relationship for "
                "the stated period."
            )
        },
        "defects": [],
        "suggested_correction": "",
    }
    payload.update(
        {
            dimension: {
                "rating": "strong",
                "explanation": "The claim passes this dimension.",
            }
            for dimension in _DIMENSIONS
        }
    )
    payload.update(overrides)
    return payload


def test_approved_review_requires_complete_source_grounding() -> None:
    validated = _validate_review_payload(_payload(), inspected_physical_pages=[12])

    assert validated["decision"] == "approved"
    assert validated["supporting_physical_pages"] == [12]
    assert validated["diagnostics"] == []


def test_approved_review_requires_substantive_source_grounding() -> None:
    validated = _validate_review_payload(
        _payload(source_grounded_explanation="Supported by the page."),
        inspected_physical_pages=[12],
    )

    assert validated["decision"] == "unresolved"
    assert "source_grounded_explanation_not_substantive" in validated["diagnostics"]
    assert "review_response_invalid" in validated["diagnostics"]


def test_material_factual_issue_cannot_be_approved() -> None:
    validated = _validate_review_payload(
        _payload(
            factual_fidelity={
                "rating": "material_issue",
                "explanation": "The denominator is not supported by the page.",
            }
        ),
        inspected_physical_pages=[12],
    )

    assert validated["decision"] != "approved"
    assert "material_factual_issue_blocks_approval" in validated["diagnostics"]


@pytest.mark.parametrize(
    "dimension",
    ["analytical_validity", "commercial_relevance", "editorial_quality"],
)
def test_approved_material_dimension_is_unresolved(dimension: str) -> None:
    validated = _validate_review_payload(
        _payload(
            **{
                dimension: {
                    "rating": "material_issue",
                    "explanation": "This dimension contains a material defect.",
                }
            }
        ),
        inspected_physical_pages=[12],
    )

    assert validated["decision"] == "unresolved"
    assert "review_decision_conflict" in validated["diagnostics"]


def test_approved_unresolved_dimension_is_unresolved() -> None:
    validated = _validate_review_payload(
        _payload(
            factual_fidelity={
                "rating": "unresolved",
                "explanation": "The page does not settle the factual relationship.",
            }
        ),
        inspected_physical_pages=[12],
    )

    assert validated["decision"] == "unresolved"
    assert "review_decision_conflict" in validated["diagnostics"]


def test_approved_material_defect_in_any_dimension_is_unresolved() -> None:
    validated = _validate_review_payload(
        _payload(
            defects=[
                {
                    "dimension": "specificity",
                    "severity": "material",
                    "description": "The claim is too broad for the cited page.",
                }
            ]
        ),
        inspected_physical_pages=[12],
    )

    assert validated["decision"] == "unresolved"
    assert "review_decision_conflict" in validated["diagnostics"]


def test_approved_adequate_and_minor_assessments_remain_eligible() -> None:
    validated = _validate_review_payload(
        _payload(
            analytical_validity={
                "rating": "adequate",
                "explanation": "The source supports the bounded interpretation.",
            },
            editorial_quality={
                "rating": "minor_issue",
                "explanation": "The wording could be more concise.",
            },
        ),
        inspected_physical_pages=[12],
    )

    assert validated["decision"] == "approved"
    assert validated["diagnostics"] == []


def test_material_issue_with_malformed_pages_is_unresolved_not_rejected() -> None:
    validated = _validate_review_payload(
        _payload(
            factual_fidelity={
                "rating": "material_issue",
                "explanation": "The denominator is not supported by the page.",
            },
            supporting_physical_pages=[13],
            source_truth_notes_by_page={"12": "The note is for another page."},
        ),
        inspected_physical_pages=[12],
    )

    assert validated["decision"] == "unresolved"
    assert "review_response_invalid" in validated["diagnostics"]
    assert "review_decision_conflict" in validated["diagnostics"]
    assert validated["decision"] != "rejected"


@pytest.mark.parametrize("decision", ["rejected", "revision_required"])
def test_structured_nonapproval_decisions_are_preserved(decision: str) -> None:
    validated = _validate_review_payload(
        _payload(
            decision=decision,
            factual_fidelity={
                "rating": "material_issue" if decision == "rejected" else "minor_issue",
                "explanation": (
                    "The response records the concrete source-grounded defect."
                ),
            },
            defects=(
                [
                    {
                        "dimension": "factual_fidelity",
                        "severity": "material" if decision == "rejected" else "minor",
                        "description": (
                            "The reported population is not the cited population."
                        ),
                    }
                ]
                if decision == "rejected"
                else []
            ),
        ),
        inspected_physical_pages=[12],
    )

    assert validated["decision"] == decision
    assert "review_response_invalid" not in validated["diagnostics"]


def test_material_issue_count_counts_each_affected_claim_once() -> None:
    summary = _record_summary(
        [
            {
                "decision": "unresolved",
                "dimensions": {"factual_fidelity": {"rating": "material_issue"}},
                "defects": [
                    {
                        "dimension": "factual_fidelity",
                        "severity": "material",
                        "description": "Same affected claim.",
                    }
                ],
            },
            {
                "decision": "revision_required",
                "dimensions": {"commercial_relevance": {"rating": "material_issue"}},
                "defects": [],
            },
        ]
    )

    assert summary["material_defect_count"] == 2


def test_malformed_review_response_fails_closed() -> None:
    validated = _validate_review_payload(
        {"decision": "approved", "explanation": "looks good"},
        inspected_physical_pages=[12],
    )

    assert validated["decision"] == "unresolved"
    assert "review_response_invalid" in validated["diagnostics"]


def test_review_pages_must_be_inspected_and_notes_must_match() -> None:
    validated = _validate_review_payload(
        _payload(
            supporting_physical_pages=[13],
            source_truth_notes_by_page={"12": "Wrong page note."},
        ),
        inspected_physical_pages=[12],
    )

    assert validated["decision"] == "unresolved"
    assert "supporting_pages_invalid" in validated["diagnostics"]


def test_provisional_recovery_pages_are_reviewable_without_promotion() -> None:
    pages, reason = _validate_result_binding(
        {
            "source_identity": "report|pdf-sha256:" + "a" * 64,
            "physical_pages": [],
            "original_physical_pages": [],
            "inspected_physical_pages": [12, 14],
            "source_binding_status": "provisional_recovered",
        },
        {
            "sha256_matches": True,
            "sha256_expected": "a" * 64,
            "page_count": 20,
        },
    )

    assert reason == ""
    assert pages == [12, 14]


def _additional_result(
    claims: list[dict[str, object]],
    *,
    unavailable: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "claims": claims,
        "real_shortlisted_set": {
            "selected_claim_count": 2,
            "eligible_claim_count": len(claims),
            "unavailable": unavailable or [],
        },
        "shortlist_inventory": [
            {
                "report": "Report A",
                "selected_count": 2,
                "eligible_candidate_ids": ["candidate-a", "candidate-b"],
                "unavailable": unavailable or [],
            }
        ],
    }


def _claim(candidate_id: str, *, report: str = "Report A") -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "evaluation_set": "real_shortlisted",
        "report_name": report,
        "final_claim": "A source-grounded final claim.",
    }


def _review_record(
    candidate_id: str,
    *,
    report: str = "Report A",
    availability: str = "eligible",
    cohort: str = "additional_five",
    decision: str = "approved",
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "report_name": report,
        "availability": availability,
        "cohort": cohort,
        "decision": decision,
        "review_invoked": availability != "unavailable",
    }


def test_cohort_coverage_rejects_missing_candidate() -> None:
    validation = _validate_cohort_identity_coverage(
        _additional_result([_claim("candidate-a")]), cohort="additional_five"
    )

    assert validation["coverage_status"] != "PASS"
    assert "missing_candidate_id" in validation["issue_codes"]


def test_cohort_coverage_rejects_duplicate_candidate() -> None:
    validation = _validate_cohort_identity_coverage(
        _additional_result([_claim("candidate-a"), _claim("candidate-a")]),
        cohort="additional_five",
    )

    assert validation["coverage_status"] != "PASS"
    assert "duplicate_candidate_id" in validation["issue_codes"]


def test_cohort_coverage_rejects_unknown_candidate() -> None:
    validation = _validate_cohort_identity_coverage(
        _additional_result([_claim("candidate-a"), _claim("unknown")]),
        cohort="additional_five",
    )

    assert validation["coverage_status"] != "PASS"
    assert "unexpected_candidate_id" in validation["issue_codes"]


def test_cohort_coverage_rejects_unknown_nonselected_row() -> None:
    row = _claim("unknown")
    row["evaluation_set"] = "reference"
    validation = _validate_cohort_identity_coverage(
        _additional_result([_claim("candidate-a"), row]),
        cohort="additional_five",
    )

    assert validation["coverage_status"] != "PASS"
    assert "unexpected_candidate_id" in validation["issue_codes"]


def test_reference_variants_are_accounted_for_outside_exact_cohort() -> None:
    result = _additional_result([_claim("candidate-a"), _claim("candidate-b")])
    result["claims"].append(
        {
            "candidate_id": "reference-variant",
            "evaluation_set": "reference_variant",
        }
    )
    result["reference_set"] = {"case_count": 1, "candidate_variant_count": 1}

    validation = _validate_cohort_identity_coverage(result, cohort="additional_five")

    assert validation["coverage_status"] == "PASS"
    assert validation["reference_variant_count"] == 1
    assert validation["reference_variant_ids"] == ["reference-variant"]


def test_reference_variants_require_reference_roster_metadata() -> None:
    result = _additional_result([_claim("candidate-a"), _claim("candidate-b")])
    result["claims"].append(  # type: ignore[union-attr]
        {"candidate_id": "reference-variant", "evaluation_set": "reference_variant"}
    )

    validation = _validate_cohort_identity_coverage(result, cohort="additional_five")

    assert validation["coverage_status"] != "PASS"
    assert "reference_roster_unavailable" in validation["issue_codes"]


def test_cohort_coverage_requires_unavailable_identity() -> None:
    unavailable = [
        {
            "candidate_id": "candidate-unavailable",
            "report": "Report A",
            "reason": "no safe physical page",
        }
    ]
    result = _additional_result(
        [_claim("candidate-a"), _claim("candidate-b")], unavailable=unavailable
    )
    result["shortlist_inventory"][0]["selected_count"] = 3  # type: ignore[index]
    result["real_shortlisted_set"]["unavailable"] = []  # type: ignore[index]
    validation = _validate_cohort_identity_coverage(result, cohort="additional_five")

    assert validation["coverage_status"] != "PASS"
    assert "missing_unavailable_record" in validation["issue_codes"]


def test_cohort_coverage_rejects_wrong_report_and_cohort_identity() -> None:
    row = _claim("candidate-a", report="Wrong report")
    row["cohort"] = "wrong_cohort"
    validation = _validate_cohort_identity_coverage(
        _additional_result([row, _claim("candidate-b")]),
        cohort="additional_five",
    )

    assert validation["coverage_status"] != "PASS"
    assert "wrong_report" in validation["issue_codes"]
    assert "wrong_cohort" in validation["issue_codes"]


def test_complete_cohort_coverage_is_exact() -> None:
    validation = _validate_cohort_identity_coverage(
        _additional_result([_claim("candidate-a"), _claim("candidate-b")]),
        cohort="additional_five",
    )

    assert validation["coverage_status"] == "PASS"
    assert validation["expected_count"] == 2
    assert validation["actual_count"] == 2


def test_acceptance_summary_separates_execution_coverage_and_editorial_status() -> None:
    validation = _validate_cohort_identity_coverage(
        _additional_result([_claim("candidate-a"), _claim("candidate-b")]),
        cohort="additional_five",
    )
    records = [
        _review_record("candidate-a"),
        _review_record("candidate-b", decision="revision_required"),
    ]

    summary = _acceptance_summary(records=records, cohort_validations=[validation])

    assert summary["execution_status"] == "PASS"
    assert summary["coverage_status"] == "PASS"
    assert summary["editorial_acceptance_status"] == "PARTIAL"
    assert "revision_required:1" in summary["reasons"]


def test_acceptance_summary_blocks_uninvoked_eligible_review() -> None:
    validation = _validate_cohort_identity_coverage(
        _additional_result([_claim("candidate-a"), _claim("candidate-b")]),
        cohort="additional_five",
    )
    records = [
        _review_record("candidate-a"),
        _review_record("candidate-b"),
    ]
    records[0]["review_invoked"] = False

    summary = _acceptance_summary(records=records, cohort_validations=[validation])

    assert summary["execution_status"] == "PARTIAL"
    assert "review_not_invoked:candidate-a" in summary["execution_reasons"]
    assert summary["editorial_acceptance_status"] == "PARTIAL"


def test_acceptance_summary_is_deterministic_for_retained_manifest() -> None:
    validation = _validate_cohort_identity_coverage(
        _additional_result([_claim("candidate-a"), _claim("candidate-b")]),
        cohort="additional_five",
    )
    records = [
        _review_record("candidate-a"),
        _review_record("candidate-b"),
    ]

    first = _acceptance_summary(records=records, cohort_validations=[validation])
    second = _acceptance_summary(records=records, cohort_validations=[validation])

    assert first == second


def test_artifact_context_excludes_generated_editorial_content(tmp_path) -> None:
    artifact_path = tmp_path / "artifacts.json"
    artifact_path.write_text(
        json.dumps(
            {
                "summary": {
                    "tldr": "GENERATED ANSWER THAT MUST NOT BE SHARED",
                    "executive_summary": "GENERATED EXECUTIVE ANSWER",
                },
                "topics_covered": [
                    {"topic": "GENERATED TOPIC", "why_it_matters": "GENERATED"}
                ],
                "categories": ["neutral category"],
            }
        ),
        encoding="utf-8",
    )

    context = _artifact_context(
        {
            "report_name": "Report A",
            "retained_artifact_path": str(artifact_path),
        }
    )

    serialized = json.dumps(context)
    assert context["report_title"] == "Report A"
    assert context["authority"] == "metadata_only_non_authoritative"
    assert "GENERATED" not in serialized


def test_source_records_accept_retained_expected_hash_key() -> None:
    records = _explicit_source_records(
        {
            "source_pdfs": {
                "Retained report": {
                    "path": "tmp/not-a-real-retained-report.pdf",
                    "sha256_expected": "a" * 64,
                }
            }
        }
    )

    assert records["Retained report"]["sha256_expected"] == "a" * 64
    assert records["Retained report"]["sha256_matches"] is False


def _frozen_reference_fixture(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[str, list[str]]]:
    reports = {
        "Capgemini Research Institute": [
            "cap-1",
            "cap-2",
            "cap-3",
            "cap-4",
            "cap-5",
        ],
        "Activate": [
            "act-1",
            "act-2",
            "act-3",
            "act-4",
            "act-5",
            "act-6",
            "act-7",
        ],
        "KPMG": ["kpmg-1", "kpmg-2", "kpmg-3", "kpmg-4", "kpmg-5"],
        "Reuters Institute": [
            "reuters-1",
            "reuters-2",
            "reuters-3",
            "reuters-4",
            "reuters-5",
            "reuters-6",
        ],
        "Adjust": [
            "adjust-1",
            "adjust-2",
            "adjust-3",
            "adjust-4",
            "adjust-5",
            "adjust-6",
        ],
    }
    digests: dict[str, dict[str, str]] = {}
    for index, (report, candidate_ids) in enumerate(reports.items()):
        artifact_path = (
            tmp_path / f"report-{index}" / "report_analysis" / "artifacts.json"
        )
        artifact_path.parent.mkdir(parents=True)
        artifact_path.write_text(
            json.dumps(
                {
                    "insights_final": [
                        {"id": candidate_id} for candidate_id in candidate_ids
                    ]
                }
            ),
            encoding="utf-8",
        )
        digests[report] = {
            "analysis_directory": str(artifact_path.parent.relative_to(tmp_path)),
            "artifacts_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        }
    reference = {
        "retained_run": {"isolated_output_root": str(tmp_path)},
        "report_artifact_digests": digests,
    }
    return reference, reports


def _frozen_result(reports: dict[str, list[str]]) -> dict[str, object]:
    claims = [
        {
            "candidate_id": candidate_id,
            "evaluation_set": "real_shortlisted",
            "report_name": report,
        }
        for report, candidate_ids in reports.items()
        for candidate_id in candidate_ids
    ]
    return {
        "claims": claims,
        "real_shortlisted_set": {
            "expected_claim_count": len(claims),
            "input_claim_count": len(claims),
        },
    }


def test_frozen_identity_coverage_uses_hash_verified_artifacts(tmp_path: Path) -> None:
    reference, reports = _frozen_reference_fixture(tmp_path)
    validation = _validate_cohort_identity_coverage(
        _frozen_result(reports),
        cohort="frozen_five",
        frozen_reference=reference,
    )

    assert validation["coverage_status"] == "PASS"
    assert validation["expected_count"] == 29
    assert validation["actual_count"] == 29


def test_frozen_identity_substitution_is_blocked_even_when_count_matches(
    tmp_path: Path,
) -> None:
    reference, reports = _frozen_reference_fixture(tmp_path)
    result = _frozen_result(reports)
    result["claims"][0]["candidate_id"] = "substituted-id"  # type: ignore[index]

    validation = _validate_cohort_identity_coverage(
        result, cohort="frozen_five", frozen_reference=reference
    )

    assert validation["coverage_status"] == "BLOCKED"
    assert "unexpected_candidate_id" in validation["issue_codes"]
    assert "missing_candidate_id" in validation["issue_codes"]


def test_frozen_identity_wrong_report_assignment_is_blocked(tmp_path: Path) -> None:
    reference, reports = _frozen_reference_fixture(tmp_path)
    result = _frozen_result(reports)
    result["claims"][0]["report_name"] = "Activate"  # type: ignore[index]

    validation = _validate_cohort_identity_coverage(
        result, cohort="frozen_five", frozen_reference=reference
    )

    assert validation["coverage_status"] == "BLOCKED"
    assert "wrong_report" in validation["issue_codes"]


@pytest.mark.parametrize("failure", ["missing", "hash", "malformed"])
def test_frozen_identity_authoritative_roster_failures_block_coverage(
    tmp_path: Path, failure: str
) -> None:
    reference, reports = _frozen_reference_fixture(tmp_path)
    if failure == "missing":
        artifact_path = tmp_path / "report-4" / "report_analysis" / "artifacts.json"
        artifact_path.unlink()
    elif failure == "hash":
        reference["report_artifact_digests"]["Adjust"]["artifacts_sha256"] = "0" * 64  # type: ignore[index]
    else:
        artifact_path = tmp_path / "report-4" / "report_analysis" / "artifacts.json"
        artifact_path.write_text(
            json.dumps({"insights_final": [{"bad": True}]}), encoding="utf-8"
        )

    validation = _validate_cohort_identity_coverage(
        _frozen_result(reports),
        cohort="frozen_five",
        frozen_reference=reference,
    )

    assert validation["coverage_status"] == "BLOCKED"
    assert any(
        code in validation["issue_codes"]
        for code in {
            "frozen_roster_artifact_missing",
            "frozen_roster_artifact_hash_mismatch",
            "frozen_roster_insights_invalid",
        }
    )


def test_reference_variants_remain_outside_frozen_identity_coverage(
    tmp_path: Path,
) -> None:
    reference, reports = _frozen_reference_fixture(tmp_path)
    result = _frozen_result(reports)
    result["claims"].append(  # type: ignore[union-attr]
        {"candidate_id": "variant-1", "evaluation_set": "reference_variant"}
    )
    result["reference_set"] = {"candidate_variant_count": 1}

    validation = _validate_cohort_identity_coverage(
        result, cohort="frozen_five", frozen_reference=reference
    )

    assert validation["coverage_status"] == "PASS"
    assert validation["expected_count"] == 29
    assert validation["reference_variant_count"] == 1


def _page_row(
    *, step2_pages: object = [12], step2_notes: object = None
) -> dict[str, object]:
    return {
        "candidate_id": "page-candidate",
        "report_name": "Report A",
        "original_claim": "Original claim.",
        "final_claim": "Final claim.",
        "source_identity": "Report A|pdf-sha256:" + "a" * 64,
        "supporting_physical_pages": step2_pages,
        "source_truth_notes_by_page": step2_notes
        if step2_notes is not None
        else {"12": "Step 2 source note for physical page 12."},
        "physical_pages": [12],
        "original_physical_pages": [12],
        "inspected_physical_pages": [12, 13],
        "source_binding_status": "retained",
    }


def _approved_record(
    row: dict[str, object], reviewer_pages: list[int]
) -> dict[str, object]:
    record = _base_record(
        cohort="frozen_five",
        row=row,
        source={"sha256_expected": "a" * 64, "sha256_actual": "a" * 64},
    )
    record.update(
        {
            "decision": "approved",
            "review_invoked": True,
            "supporting_physical_pages": reviewer_pages,
            "source_truth_notes_by_page": {
                str(page): f"Reviewer source note for physical page {page}."
                for page in reviewer_pages
            },
            "review_response_sha256": "review-hash",
        }
    )
    return record


def test_step2_provenance_is_preserved_and_matching_pages_are_accepted() -> None:
    row = _page_row()
    record = _approved_record(row, [12])

    _reconcile_source_pages(record, row)

    assert record["step2_supporting_physical_pages"] == [12]
    assert (
        record["step2_source_truth_notes_by_page"] == row["source_truth_notes_by_page"]
    )
    assert record["page_reconciliation"]["status"] == "matched"  # type: ignore[index]
    assert record["editorial_acceptance_status"] == "accepted"


@pytest.mark.parametrize(
    ("step2_pages", "reviewer_pages"),
    [([12], [10]), ([34, 35, 36, 37, 38], [35, 36, 37, 38])],
)
def test_page_disagreement_requires_adjudication(
    step2_pages: list[int], reviewer_pages: list[int]
) -> None:
    row = _page_row(
        step2_pages=step2_pages,
        step2_notes={str(page): f"Step 2 note {page}." for page in step2_pages},
    )
    record = _approved_record(row, reviewer_pages)

    _reconcile_source_pages(record, row)

    assert record["decision"] == "approved"
    assert (
        record["editorial_acceptance_status"] == "blocked_by_source_page_reconciliation"
    )
    assert "source_page_reconciliation_required" in record["diagnostics"]
    assert record["page_reconciliation"]["missing_from_reviewer"] == [  # type: ignore[index]
        page for page in step2_pages if page not in reviewer_pages
    ]


def test_page_adjudication_accepts_supported_alternative() -> None:
    row = _page_row(step2_pages=[12], step2_notes={"12": "Step 2 source note."})
    record = _approved_record(row, [13])
    adjudications = {
        "frozen_five:page-candidate": {
            "adjudication_id": "page-adjudication-1",
            "status": "accepted",
            "cohort": "frozen_five",
            "candidate_id": "page-candidate",
            "report_name": "Report A",
            "source_pdf_sha256": "a" * 64,
            "review_response_sha256": "review-hash",
            "step2_supporting_physical_pages": [12],
            "reviewer_supporting_physical_pages": [13],
            "adjudicated_physical_pages": [13],
            "source_grounded_explanation": (
                "Physical page 13 independently supplies the same source-grounded "
                "relationship as the retained page binding."
            ),
        }
    }

    _reconcile_source_pages(record, row, adjudications=adjudications)

    assert record["decision"] == "approved"
    assert record["editorial_acceptance_status"] == "accepted"
    assert record["page_reconciliation"]["status"] == "adjudicated"  # type: ignore[index]
    assert record["supporting_physical_pages"] == [13]


def test_failed_page_adjudication_keeps_approval_blocked() -> None:
    row = _page_row()
    record = _approved_record(row, [13])
    adjudications = {
        "frozen_five:page-candidate": {
            "adjudication_id": "page-adjudication-failed",
            "status": "unresolved",
            "candidate_id": "page-candidate",
            "report_name": "Report A",
            "source_pdf_sha256": "a" * 64,
            "review_response_sha256": "review-hash",
        }
    }

    _reconcile_source_pages(record, row, adjudications=adjudications)

    assert (
        record["editorial_acceptance_status"] == "blocked_by_source_page_reconciliation"
    )
    assert record["page_reconciliation"]["status"] == "requires_adjudication"  # type: ignore[index]


def test_malformed_step2_provenance_blocks_approval_without_rewriting_review() -> None:
    row = _page_row(step2_pages=None, step2_notes={})
    record = _approved_record(row, [12])

    _reconcile_source_pages(record, row)

    assert record["decision"] == "approved"
    assert (
        record["editorial_acceptance_status"] == "blocked_by_source_page_reconciliation"
    )
    assert record["page_reconciliation"]["status"] == "unresolved"  # type: ignore[index]


def test_acceptance_summary_counts_unresolved_page_reconciliation() -> None:
    validation = _validate_cohort_identity_coverage(
        _additional_result([_claim("candidate-a"), _claim("candidate-b")]),
        cohort="additional_five",
    )
    records = [
        _review_record("candidate-a"),
        _review_record("candidate-b"),
    ]
    records[0]["editorial_acceptance_status"] = "blocked_by_source_page_reconciliation"
    records[1]["editorial_acceptance_status"] = "accepted"

    summary = _acceptance_summary(records=records, cohort_validations=[validation])

    assert summary["editorial_acceptance_status"] == "PARTIAL"
    assert "source_page_reconciliation_required:candidate-a" in summary["reasons"]
