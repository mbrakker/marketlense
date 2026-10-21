from __future__ import annotations

from scripts.quality.review_verified_claims_step2_editorial import (
    _acceptance_summary,
    _base_record,
    _valid_page_adjudication,
    _validate_cohort_identity_coverage,
    _validate_review_record_coverage,
    _validate_review_record_source_binding,
)


def _claim(candidate_id: str, *, report: str = "Report A") -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "evaluation_set": "real_shortlisted",
        "report_name": report,
        "final_claim": "A source-grounded final claim.",
    }


def _additional_result(
    claims: list[dict[str, object]],
    *,
    unavailable: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    unavailable_rows = unavailable or []
    return {
        "claims": claims,
        "real_shortlisted_set": {
            "selected_claim_count": 2,
            "eligible_claim_count": len(claims),
            "unavailable": unavailable_rows,
        },
        "shortlist_inventory": [
            {
                "report": "Report A",
                "selected_count": 2,
                "eligible_candidate_ids": ["candidate-a", "candidate-b"],
                "unavailable": unavailable_rows,
            }
        ],
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


def test_review_record_coverage_requires_every_expected_identity() -> None:
    validation = _validate_cohort_identity_coverage(
        _additional_result([_claim("candidate-a"), _claim("candidate-b")]),
        cohort="additional_five",
    )

    coverage = _validate_review_record_coverage(
        [_review_record("candidate-a")], [validation]
    )

    assert coverage["coverage_status"] == "BLOCKED"
    assert "review_record_missing" in coverage["issue_codes"]


def test_review_record_coverage_rejects_duplicate_and_substituted_identity() -> None:
    validation = _validate_cohort_identity_coverage(
        _additional_result([_claim("candidate-a"), _claim("candidate-b")]),
        cohort="additional_five",
    )

    duplicate = _validate_review_record_coverage(
        [_review_record("candidate-a"), _review_record("candidate-a")], [validation]
    )
    substituted = _validate_review_record_coverage(
        [_review_record("candidate-a"), _review_record("unknown")], [validation]
    )

    assert duplicate["coverage_status"] == "BLOCKED"
    assert "review_record_duplicate" in duplicate["issue_codes"]
    assert substituted["coverage_status"] == "BLOCKED"
    assert "review_record_unexpected" in substituted["issue_codes"]


def test_review_record_coverage_requires_explicit_unavailable_identity() -> None:
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
    result["real_shortlisted_set"]["selected_claim_count"] = 3  # type: ignore[index]
    result["real_shortlisted_set"]["eligible_claim_count"] = 2  # type: ignore[index]
    validation = _validate_cohort_identity_coverage(result, cohort="additional_five")

    coverage = _validate_review_record_coverage(
        [_review_record("candidate-a"), _review_record("candidate-b")], [validation]
    )

    assert coverage["coverage_status"] == "BLOCKED"
    assert "review_record_missing" in coverage["issue_codes"]
    assert any(
        item["candidate_id"] == "candidate-unavailable" for item in coverage["missing"]
    )


def test_review_record_coverage_rejects_malformed_record() -> None:
    validation = _validate_cohort_identity_coverage(
        _additional_result([_claim("candidate-a"), _claim("candidate-b")]),
        cohort="additional_five",
    )

    coverage = _validate_review_record_coverage(
        [_review_record("candidate-a"), {"candidate_id": "candidate-b"}],
        [validation],
    )

    assert coverage["coverage_status"] == "BLOCKED"
    assert "review_record_malformed" in coverage["issue_codes"]


def test_acceptance_summary_blocks_missing_review_record_coverage() -> None:
    validation = _validate_cohort_identity_coverage(
        _additional_result([_claim("candidate-a"), _claim("candidate-b")]),
        cohort="additional_five",
    )
    records = [_review_record("candidate-a")]
    review_coverage = _validate_review_record_coverage(records, [validation])

    summary = _acceptance_summary(
        records=records,
        cohort_validations=[validation],
        review_record_coverage=review_coverage,
    )

    assert summary["coverage_status"] == "BLOCKED"
    assert summary["editorial_acceptance_status"] == "FAIL"


def test_page_adjudication_requires_original_page_sets_to_match() -> None:
    row = _page_row(step2_pages=[12], step2_notes={"12": "Step 2 source note."})
    record = _approved_record(row, [13])
    adjudication = {
        "adjudication_id": "page-adjudication-1",
        "status": "accepted",
        "cohort": "frozen_five",
        "candidate_id": "page-candidate",
        "report_name": "Report A",
        "source_pdf_sha256": "a" * 64,
        "review_response_sha256": "review-hash",
        "step2_supporting_physical_pages": [99],
        "reviewer_supporting_physical_pages": [13],
        "adjudicated_physical_pages": [13],
        "source_grounded_explanation": (
            "Physical page 13 independently supplies the same source-grounded "
            "relationship as the retained page binding."
        ),
    }

    valid, _pages, reason = _valid_page_adjudication(record, adjudication)

    assert not valid
    assert reason == "page_adjudication_step2_pages_mismatch"


def test_page_adjudication_rejects_changed_reviewer_page_set() -> None:
    row = _page_row(step2_pages=[12], step2_notes={"12": "Step 2 source note."})
    record = _approved_record(row, [13])
    adjudication = {
        "adjudication_id": "page-adjudication-1",
        "status": "accepted",
        "cohort": "frozen_five",
        "candidate_id": "page-candidate",
        "report_name": "Report A",
        "source_pdf_sha256": "a" * 64,
        "review_response_sha256": "review-hash",
        "step2_supporting_physical_pages": [12],
        "reviewer_supporting_physical_pages": [14],
        "adjudicated_physical_pages": [13],
        "source_grounded_explanation": (
            "Physical page 13 independently supplies the same source-grounded "
            "relationship as the retained page binding."
        ),
    }

    valid, _pages, reason = _valid_page_adjudication(record, adjudication)

    assert not valid
    assert reason == "page_adjudication_reviewer_pages_mismatch"


def test_page_adjudication_accepts_reordered_original_page_sets() -> None:
    row = _page_row(
        step2_pages=[12, 13],
        step2_notes={"12": "Step 2 page 12 note.", "13": "Step 2 page 13 note."},
    )
    record = _approved_record(row, [13, 12])
    adjudication = {
        "adjudication_id": "page-adjudication-ordered",
        "status": "accepted",
        "cohort": "frozen_five",
        "candidate_id": "page-candidate",
        "report_name": "Report A",
        "source_pdf_sha256": "a" * 64,
        "review_response_sha256": "review-hash",
        "step2_supporting_physical_pages": [13, 12],
        "reviewer_supporting_physical_pages": [12, 13],
        "adjudicated_physical_pages": [13, 12],
        "source_grounded_explanation": (
            "Physical pages 12 and 13 independently supply the same "
            "source-grounded relationship as the retained page binding."
        ),
    }

    valid, pages, reason = _valid_page_adjudication(record, adjudication)

    assert valid
    assert pages == [13, 12]
    assert reason == ""


def test_changed_final_claim_invalidates_historical_review_binding() -> None:
    row = _page_row()
    record = _approved_record(row, [12])
    source = {"sha256_expected": "a" * 64, "sha256_actual": "a" * 64}
    record["final_claim"] = "A changed historical claim."

    diagnostics = _validate_review_record_source_binding(record, row, source)

    assert "stale_review_final_claim" in diagnostics
    assert "stale_review_source_binding" in diagnostics
