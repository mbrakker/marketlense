"""Run a source-grounded Step 2 adversarial corpus through the shadow evaluator."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.quality.replay_verified_claims_step2 import (
    REPOSITORY_ROOT,
    _load_json,
    _resolve_repository_path,
    _safe_report_name,
    _valid_supporting_pages,
    replay_live_explicit_cohort,
)
from src.generators.verified_claims_recovery import source_pdf_sha256
from src.generators.verified_claims_visual_generator import _source_truth_notes_present

_POSITIVE_EXPECTATION = "verified_or_corrected"
_NEGATIVE_EXPECTATION = "unresolved_or_failed"
_VERIFIED_OUTCOMES = {"verified", "verified_after_retry"}
_FAILED_OUTCOMES = {"unresolved", "failed_verification"}
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_NON_GENUINE_REJECTION_MARKERS = (
    "verification_provider_error",
    "correction_provider_error",
    "verification_response_invalid",
    "verification_diagnostics_missing",
    "error_code:",
    "error_type:",
    "retryable:",
)
_NON_REJECTION_FAILURE_MARKERS = (
    "candidate_id_missing",
    "claim_text_missing",
    "physical_page_missing",
    "page_render_failed",
    "source_binding_conflict",
    "correction_",
    "verification_non_retryable",
)


def _acceptance_mismatch(
    *,
    code: str,
    detail: str,
    candidate_id: str = "",
    case_id: str = "",
) -> dict[str, str]:
    return {
        "code": code,
        "candidate_id": candidate_id,
        "case_id": case_id,
        "detail": detail,
    }


def _strict_page_list(value: Any) -> list[int] | None:
    if not isinstance(value, list):
        return None
    pages: list[int] = []
    for page in value:
        if type(page) is not int or page <= 0 or page in pages:
            return None
        pages.append(page)
    return pages


def _source_identity_is_valid(row: Mapping[str, Any]) -> tuple[bool, str]:
    source_identity = row.get("source_identity")
    if not isinstance(source_identity, str) or not source_identity.strip():
        return False, "source_identity is missing"

    expected_hash = row.get("source_pdf_sha256_expected")
    actual_hash = row.get("source_pdf_sha256_actual")
    if not isinstance(expected_hash, str) or not _SHA256_PATTERN.fullmatch(
        expected_hash.strip()
    ):
        return False, "expected source PDF hash is not a SHA-256 value"
    if not isinstance(actual_hash, str) or not _SHA256_PATTERN.fullmatch(
        actual_hash.strip()
    ):
        return False, "actual source PDF hash is not a SHA-256 value"
    expected = expected_hash.strip().lower()
    actual = actual_hash.strip().lower()
    if expected != actual:
        return False, "source PDF hash does not match expected identity"
    embedded = source_pdf_sha256(source_identity)
    if not embedded:
        return False, "source_identity does not contain one PDF SHA-256 value"
    if embedded != expected or embedded != actual:
        return False, "source_identity PDF hash does not match result hashes"
    return True, ""


def _source_provenance_is_valid(row: Mapping[str, Any]) -> tuple[bool, str]:
    identity_valid, identity_reason = _source_identity_is_valid(row)
    if not identity_valid:
        return False, identity_reason

    inspected = _strict_page_list(row.get("inspected_physical_pages"))
    if not inspected:
        return False, "inspected physical pages are invalid"

    pages, reason = _valid_supporting_pages(row)
    if not pages:
        return False, reason or "supporting physical pages are invalid"
    return True, ""


def _expected_physical_pages(case: Mapping[str, Any]) -> list[int] | None:
    raw_pages = case.get("physical_pages")
    return _strict_page_list(raw_pages) if raw_pages is not None else None


def _row_binding_matches_case(
    row: Mapping[str, Any], case: Mapping[str, Any]
) -> tuple[bool, str]:
    expected_pages = _expected_physical_pages(case)
    if expected_pages is None:
        return True, ""
    for field in ("physical_pages", "original_physical_pages"):
        actual_pages = _strict_page_list(row.get(field))
        if actual_pages != expected_pages:
            return False, f"{field} does not preserve the corpus physical pages"
    inspected = _strict_page_list(row.get("inspected_physical_pages"))
    if not inspected or not set(expected_pages).issubset(inspected):
        return False, "inspected physical pages omit the retained binding"
    return True, ""


def _bounded_attempts(
    row: Mapping[str, Any], field: str
) -> tuple[list[Mapping[str, Any]] | None, str]:
    raw_attempts = row.get(field)
    if not isinstance(raw_attempts, list) or not raw_attempts:
        return None, f"{field} are missing"
    if len(raw_attempts) > 2:
        return None, f"{field} exceed the two-attempt bound"
    attempts: list[Mapping[str, Any]] = []
    seen_numbers: set[int] = set()
    for raw_attempt in raw_attempts:
        if not isinstance(raw_attempt, Mapping):
            return None, f"{field} contain a malformed attempt"
        attempt_number = raw_attempt.get("attempt")
        if (
            type(attempt_number) is not int
            or attempt_number not in {1, 2}
            or attempt_number in seen_numbers
        ):
            return None, f"{field} contain an invalid or duplicate attempt number"
        seen_numbers.add(attempt_number)
        attempts.append(raw_attempt)
    return attempts, ""


def _matching_attempt(
    attempts: list[Mapping[str, Any]], attempt_number: int
) -> Mapping[str, Any] | None:
    return next(
        (attempt for attempt in attempts if attempt.get("attempt") == attempt_number),
        None,
    )


def _attempt_binding_is_valid(
    *,
    row: Mapping[str, Any],
    attempt: Mapping[str, Any],
    require_supporting_pages: bool,
) -> tuple[bool, str]:
    attempt_pages = attempt.get("supporting_physical_pages")
    attempt_notes = attempt.get("source_truth_notes_by_page")
    if not isinstance(attempt_pages, list) or not isinstance(attempt_notes, dict):
        return False, "verification attempt page evidence is malformed"
    if require_supporting_pages:
        attempt_row = {
            "inspected_physical_pages": row.get("inspected_physical_pages"),
            "supporting_physical_pages": attempt_pages,
            "source_truth_notes_by_page": attempt_notes,
        }
        pages, reason = _valid_supporting_pages(attempt_row)
        if not pages:
            return False, reason or "verification attempt supporting pages are invalid"
        if any(
            not isinstance(note, str) or not _source_truth_notes_present(note)
            for note in attempt_notes.values()
        ):
            return False, "verification attempt page notes are missing"
    elif attempt_pages or attempt_notes:
        return False, "negative verification attempt carries supporting pages"
    return True, ""


def _correction_matches_attempt(
    corrections: list[Mapping[str, Any]],
    attempt_number: int,
    expected_claim: str = "",
) -> tuple[bool, str]:
    correction = _matching_attempt(corrections, attempt_number)
    if correction is None or correction.get("status") != "corrected":
        return False, "verification attempt has no matching corrected claim"
    claim = correction.get("claim")
    if not isinstance(claim, str) or not claim.strip():
        return False, "matching correction attempt has no claim"
    if expected_claim and claim.strip() != expected_claim.strip():
        return False, "final claim does not match the successful correction attempt"
    return True, ""


def _genuine_rejection(
    *, row: Mapping[str, Any], attempt: Mapping[str, Any]
) -> tuple[bool, str]:
    if attempt.get("outcome") != "rejected":
        return False, "verification attempt did not reject the claim"
    diagnostics = attempt.get("diagnostics")
    if (
        not isinstance(diagnostics, list)
        or not diagnostics
        or any(not isinstance(item, str) or not item.strip() for item in diagnostics)
    ):
        return False, "verification rejection diagnostics are missing"
    normalized_diagnostics = [item.strip().casefold() for item in diagnostics]
    if any(
        any(marker in diagnostic for marker in _NON_GENUINE_REJECTION_MARKERS)
        for diagnostic in normalized_diagnostics
    ):
        return False, "verification rejection is only a provider or malformed response"
    source_truth_notes = attempt.get("source_truth_notes")
    if not isinstance(source_truth_notes, str) or not _source_truth_notes_present(
        source_truth_notes
    ):
        return False, "verification rejection has no source assessment"
    return _attempt_binding_is_valid(
        row=row, attempt=attempt, require_supporting_pages=False
    )


def _safe_correction_abstention(
    *, row: Mapping[str, Any], corrections: list[Mapping[str, Any]]
) -> tuple[bool, str]:
    """Accept a model's bounded source-mismatch abstention as a negative terminal.

    A correction can terminate before verification when Luna returns ``unresolved``
    twice because the retained page supports only a neighboring proposition.  This
    is a safe negative outcome, but malformed, provider, or generic failed
    corrections must not satisfy the adversarial acceptance gate.
    """

    if row.get("outcome") != "unresolved" or row.get("failure_reason") != (
        "correction_unresolved"
    ):
        return False, "terminal result is not a bounded correction abstention"
    if (
        row.get("final_claim")
        or row.get("supporting_physical_pages")
        or row.get("source_truth_notes_by_page")
    ):
        return False, "correction abstention retains accepted claim evidence"
    if len(corrections) != 2:
        return False, "correction abstention did not use two unresolved attempts"
    for correction in corrections:
        if correction.get("status") != "unresolved":
            return False, "correction abstention contains a non-unresolved attempt"
        issues = correction.get("issues")
        if (
            not isinstance(issues, list)
            or not issues
            or any(not isinstance(issue, str) or not issue.strip() for issue in issues)
        ):
            return False, "correction abstention has no source-based issue"
        normalized_issues = [issue.strip().casefold() for issue in issues]
        if any(
            any(marker in issue for marker in _NON_GENUINE_REJECTION_MARKERS)
            for issue in normalized_issues
        ):
            return (
                False,
                "correction abstention is only a provider or malformed response",
            )
    return True, ""


def compare_adversarial_outcomes(
    corpus: Mapping[str, Any], result: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare one replay result with the adversarial corpus contract.

    The comparator is deliberately independent of model scoring.  It checks
    only the terminal outcome contract, candidate identity cardinality, and
    the source provenance required before a positive result can be accepted.
    """

    mismatches: list[dict[str, str]] = []
    expected_by_id: dict[str, tuple[str, str, Mapping[str, Any]]] = {}
    raw_cases = corpus.get("cases")
    if not isinstance(raw_cases, list):
        mismatches.append(
            _acceptance_mismatch(
                code="malformed_expected_cases",
                detail="corpus cases must be a list",
            )
        )
        raw_cases = []

    expected_terminal_counts: dict[str, int] = defaultdict(int)
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            mismatches.append(
                _acceptance_mismatch(
                    code="malformed_expected_case",
                    detail="each corpus case must be an object",
                )
            )
            continue
        candidate_id = raw_case.get("candidate_id")
        case_id = raw_case.get("case_id")
        expected = raw_case.get("expected_terminal")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            mismatches.append(
                _acceptance_mismatch(
                    code="malformed_expected_identity",
                    detail="corpus candidate_id must be a non-empty string",
                    case_id=str(case_id or ""),
                )
            )
            continue
        candidate_id = candidate_id.strip()
        case_id = str(case_id or "")
        if candidate_id in expected_by_id:
            mismatches.append(
                _acceptance_mismatch(
                    code="duplicate_expected_identity",
                    detail="corpus contains more than one case for the candidate_id",
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )
            continue
        if expected not in {_POSITIVE_EXPECTATION, _NEGATIVE_EXPECTATION}:
            mismatches.append(
                _acceptance_mismatch(
                    code="malformed_expected_terminal",
                    detail=f"unsupported expected terminal {expected!r}",
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )
            continue
        expected_by_id[candidate_id] = (case_id, str(expected), raw_case)
        expected_terminal_counts[str(expected)] += 1

    raw_rows = result.get("claims")
    rows: list[Mapping[str, Any]] = []
    if not isinstance(raw_rows, list):
        mismatches.append(
            _acceptance_mismatch(
                code="malformed_result",
                detail="replay claims must be a list",
            )
        )
        raw_rows = []

    rows_by_id: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    actual_outcome_counts: dict[str, int] = defaultdict(int)
    for raw_row in raw_rows:
        if not isinstance(raw_row, Mapping):
            mismatches.append(
                _acceptance_mismatch(
                    code="malformed_result",
                    detail="each replay claim must be an object",
                )
            )
            continue
        rows.append(raw_row)
        candidate_id = raw_row.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            mismatches.append(
                _acceptance_mismatch(
                    code="malformed_result",
                    detail="replay candidate_id must be a non-empty string",
                )
            )
            continue
        candidate_id = candidate_id.strip()
        outcome = raw_row.get("outcome")
        if isinstance(outcome, str) and outcome:
            actual_outcome_counts[outcome] += 1
        if candidate_id not in expected_by_id:
            mismatches.append(
                _acceptance_mismatch(
                    code="unknown_result",
                    detail="replay returned a candidate absent from the corpus",
                    candidate_id=candidate_id,
                )
            )
            continue
        rows_by_id[candidate_id].append(raw_row)

    matched_count = 0
    for candidate_id, (case_id, expected, case) in expected_by_id.items():
        candidate_rows = rows_by_id.get(candidate_id, [])
        if not candidate_rows:
            mismatches.append(
                _acceptance_mismatch(
                    code="missing_result",
                    detail="corpus candidate has no replay result",
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )
            continue
        if len(candidate_rows) != 1:
            mismatches.append(
                _acceptance_mismatch(
                    code="duplicate_result",
                    detail="corpus candidate must have exactly one replay result",
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )
            continue

        matched_count += 1
        row = candidate_rows[0]
        outcome = row.get("outcome")
        allowed = (
            _VERIFIED_OUTCOMES
            if expected == _POSITIVE_EXPECTATION
            else _FAILED_OUTCOMES
        )
        if outcome not in allowed:
            mismatches.append(
                _acceptance_mismatch(
                    code="unexpected_outcome",
                    detail=(
                        f"expected {sorted(allowed)} for {expected}, got {outcome!r}"
                    ),
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )
            continue

        binding_matches, binding_reason = _row_binding_matches_case(row, case)
        if not binding_matches:
            mismatches.append(
                _acceptance_mismatch(
                    code="source_binding_mismatch",
                    detail=binding_reason,
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )

        identity_valid, identity_reason = _source_identity_is_valid(row)
        if not identity_valid:
            mismatches.append(
                _acceptance_mismatch(
                    code="invalid_source_provenance",
                    detail=identity_reason,
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )

        corrections, correction_reason = _bounded_attempts(row, "correction_attempts")
        verifications, verification_reason = _bounded_attempts(
            row, "verification_attempts"
        )
        if corrections is None:
            mismatches.append(
                _acceptance_mismatch(
                    code="missing_correction_attempts",
                    detail=correction_reason,
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )
        if corrections is None:
            if verifications is None:
                mismatches.append(
                    _acceptance_mismatch(
                        code=(
                            "missing_successful_verification_attempt"
                            if expected == _POSITIVE_EXPECTATION
                            else "missing_verification_rejection"
                        ),
                        detail=verification_reason,
                        candidate_id=candidate_id,
                        case_id=case_id,
                    )
                )
            continue

        if expected == _NEGATIVE_EXPECTATION and verifications is None:
            abstention_valid, abstention_reason = _safe_correction_abstention(
                row=row, corrections=corrections
            )
            if abstention_valid:
                continue
            mismatches.append(
                _acceptance_mismatch(
                    code="missing_verification_rejection",
                    detail=abstention_reason,
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )
            continue

        if verifications is None:
            mismatches.append(
                _acceptance_mismatch(
                    code=(
                        "missing_successful_verification_attempt"
                        if expected == _POSITIVE_EXPECTATION
                        else "missing_verification_rejection"
                    ),
                    detail=verification_reason,
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )
            continue

        if expected == _POSITIVE_EXPECTATION:
            final_claim = row.get("final_claim")
            if not isinstance(final_claim, str) or not final_claim.strip():
                mismatches.append(
                    _acceptance_mismatch(
                        code="missing_final_claim",
                        detail="positive terminal outcome has no final corrected claim",
                        candidate_id=candidate_id,
                        case_id=case_id,
                    )
                )
                continue
            provenance_valid, provenance_reason = _source_provenance_is_valid(row)
            if not provenance_valid:
                mismatches.append(
                    _acceptance_mismatch(
                        code="invalid_source_provenance",
                        detail=provenance_reason,
                        candidate_id=candidate_id,
                        case_id=case_id,
                    )
                )

            terminal_attempt_number = 1 if outcome == "verified" else 2
            verification = _matching_attempt(verifications, terminal_attempt_number)
            if verification is None or verification.get("outcome") != "verified":
                mismatches.append(
                    _acceptance_mismatch(
                        code="missing_successful_verification_attempt",
                        detail=(
                            "positive terminal outcome has no matching successful "
                            "verification attempt"
                        ),
                        candidate_id=candidate_id,
                        case_id=case_id,
                    )
                )
                continue
            if verification is not verifications[-1]:
                mismatches.append(
                    _acceptance_mismatch(
                        code="verification_attempt_sequence_mismatch",
                        detail=(
                            "a positive terminal result has a later verification "
                            "attempt"
                        ),
                        candidate_id=candidate_id,
                        case_id=case_id,
                    )
                )
            correction_matches, correction_reason = _correction_matches_attempt(
                corrections, terminal_attempt_number, final_claim
            )
            if not correction_matches:
                mismatches.append(
                    _acceptance_mismatch(
                        code="final_claim_attempt_mismatch",
                        detail=correction_reason,
                        candidate_id=candidate_id,
                        case_id=case_id,
                    )
                )
            attempt_binding_valid, attempt_binding_reason = _attempt_binding_is_valid(
                row=row, attempt=verification, require_supporting_pages=True
            )
            if not attempt_binding_valid:
                mismatches.append(
                    _acceptance_mismatch(
                        code="verification_binding_mismatch",
                        detail=attempt_binding_reason,
                        candidate_id=candidate_id,
                        case_id=case_id,
                    )
                )
            if row.get("supporting_physical_pages") != verification.get(
                "supporting_physical_pages"
            ) or row.get("source_truth_notes_by_page") != verification.get(
                "source_truth_notes_by_page"
            ):
                mismatches.append(
                    _acceptance_mismatch(
                        code="verification_binding_mismatch",
                        detail=(
                            "result supporting pages or page notes disagree with "
                            "the successful verification attempt"
                        ),
                        candidate_id=candidate_id,
                        case_id=case_id,
                    )
                )
            continue

        failure_reason = row.get("failure_reason")
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            mismatches.append(
                _acceptance_mismatch(
                    code="negative_failure_reason_missing",
                    detail="negative terminal outcome has no terminal failure reason",
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )
        elif any(
            marker in failure_reason.casefold()
            for marker in _NON_REJECTION_FAILURE_MARKERS
        ):
            mismatches.append(
                _acceptance_mismatch(
                    code="non_rejection_failure",
                    detail="negative terminal outcome is not a verification rejection",
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )

        if row.get("final_claim"):
            mismatches.append(
                _acceptance_mismatch(
                    code="negative_final_claim_present",
                    detail="negative terminal outcome must not retain a final claim",
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )
        if row.get("supporting_physical_pages") or row.get(
            "source_truth_notes_by_page"
        ):
            mismatches.append(
                _acceptance_mismatch(
                    code="negative_supporting_pages_present",
                    detail=(
                        "negative terminal outcome must not accept supporting pages "
                        "or page-specific support notes"
                    ),
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )

        last_verification = verifications[-1]
        if any(attempt.get("outcome") == "verified" for attempt in verifications):
            mismatches.append(
                _acceptance_mismatch(
                    code="negative_successful_verification_present",
                    detail=(
                        "negative terminal outcome contains a successful verification"
                    ),
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )
        rejection_valid, rejection_reason = _genuine_rejection(
            row=row, attempt=last_verification
        )
        if not rejection_valid:
            mismatches.append(
                _acceptance_mismatch(
                    code="missing_genuine_verification_rejection",
                    detail=rejection_reason,
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )
            continue
        last_attempt_number = last_verification.get("attempt")
        correction_matches, correction_reason = _correction_matches_attempt(
            corrections, last_attempt_number
        )
        if not correction_matches:
            mismatches.append(
                _acceptance_mismatch(
                    code="correction_only_failure",
                    detail=correction_reason,
                    candidate_id=candidate_id,
                    case_id=case_id,
                )
            )

        if case_id == "BIG-ADV-002":
            expected_pages = _expected_physical_pages(case)
            original_pages = _strict_page_list(row.get("original_physical_pages"))
            if expected_pages != [8] or original_pages != [8]:
                mismatches.append(
                    _acceptance_mismatch(
                        code="strict_original_binding_not_preserved",
                        detail="BIG-ADV-002 must retain original physical page [8]",
                        candidate_id=candidate_id,
                        case_id=case_id,
                    )
                )
            if 4 in (last_verification.get("supporting_physical_pages") or []):
                mismatches.append(
                    _acceptance_mismatch(
                        code="strict_original_binding_rescued",
                        detail="BIG-ADV-002 accepted an unrelated supporting page 4",
                        candidate_id=candidate_id,
                        case_id=case_id,
                    )
                )
            source_assessment = str(
                last_verification.get("source_truth_notes") or ""
            ).casefold()
            if not re.search(r"\bpage\s+8\b", source_assessment):
                mismatches.append(
                    _acceptance_mismatch(
                        code="strict_original_binding_not_assessed",
                        detail="BIG-ADV-002 rejection does not assess physical page 8",
                        candidate_id=candidate_id,
                        case_id=case_id,
                    )
                )

    return {
        "passed": not mismatches,
        "case_count": len(expected_by_id),
        "matched_count": matched_count,
        "expected_terminal_counts": dict(expected_terminal_counts),
        "actual_outcome_counts": dict(actual_outcome_counts),
        "mismatches": mismatches,
    }


def adversarial_acceptance_exit_code(report: Mapping[str, Any]) -> int:
    """Return the process status for the persisted adversarial acceptance report."""

    return 0 if report.get("passed") is True else 1


def _write_snapshot(
    *,
    corpus: dict[str, object],
    snapshot_root: Path,
) -> tuple[Path, dict[str, Path]]:
    cases_by_report: dict[str, list[dict[str, object]]] = defaultdict(list)
    for case in corpus.get("cases", []):
        if isinstance(case, dict):
            cases_by_report[str(case["report"])].append(case)

    artifact_paths: dict[str, Path] = {}
    report_entries: list[dict[str, object]] = []
    for report, cases in sorted(cases_by_report.items()):
        run_directory = snapshot_root / _safe_report_name(report)
        analysis_directory = run_directory / "output" / "report_analysis"
        analysis_directory.mkdir(parents=True, exist_ok=True)
        insights = []
        for case in cases:
            page = int(case["physical_pages"][0])
            insights.append(
                {
                    "id": case["candidate_id"],
                    "text": case["original_claim"],
                    "evidence_id": case["evidence_id"],
                    "evidence": case["source_anchor"],
                    "evidence_spans": [
                        {
                            "evidence_id": case["evidence_id"],
                            "source_pack": "findings",
                            "page": page,
                            "text": case["source_anchor"],
                        }
                    ],
                    "pages": list(case["physical_pages"]),
                    "_visual_replacement_policy": case["replacement_policy"],
                }
            )
        artifact_path = analysis_directory / "artifacts.json"
        artifact_path.write_text(
            json.dumps({"insights_final": insights}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        (analysis_directory / "doc_map.json").write_text(
            json.dumps({"sections": []}) + "\n", encoding="utf-8"
        )
        (analysis_directory / "findings.json").write_text(
            json.dumps({"findings": []}) + "\n", encoding="utf-8"
        )
        artifact_paths[report] = artifact_path
        report_entries.append(
            {
                "publisher_id": report,
                "git_sha": "adversarial-corpus",
                "run_directory": str(run_directory),
            }
        )

    cohort_path = snapshot_root / "cohort_result.json"
    cohort_path.write_text(
        json.dumps(
            {"git_sha": "adversarial-corpus", "reports": report_entries},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return cohort_path, artifact_paths


def replay_adversarial_corpus(
    *, corpus_path: Path, source_manifest_path: Path, output_path: Path
) -> dict[str, object]:
    corpus = _load_json(corpus_path)
    snapshot_root = output_path.parent / "input_snapshot"
    cohort_path, artifact_paths = _write_snapshot(
        corpus=corpus, snapshot_root=snapshot_root
    )
    result = replay_live_explicit_cohort(
        cohort_result_path=cohort_path,
        source_manifest_path=source_manifest_path,
        output_root=output_path.parent,
        artifact_paths=artifact_paths,
    )
    cases_by_id = {
        str(case["candidate_id"]): case
        for case in corpus.get("cases", [])
        if isinstance(case, dict)
    }
    for row in result.get("claims", []):
        if not isinstance(row, dict):
            continue
        case = cases_by_id.get(str(row.get("candidate_id") or ""))
        if case is None:
            continue
        row.update(
            {
                "adversarial_case_id": case["case_id"],
                "mutation": case["mutation"],
                "expected_terminal": case["expected_terminal"],
                "source_truth": case["source_truth"],
                "manual_factual_assessment": "pending_independent_review",
            }
        )
    acceptance = compare_adversarial_outcomes(corpus, result)
    result["adversarial_corpus"] = {
        "path": str(corpus_path),
        "case_count": len(cases_by_id),
        "expected_terminal_counts": {
            expected: sum(
                case["expected_terminal"] == expected for case in cases_by_id.values()
            )
            for expected in sorted(
                {case["expected_terminal"] for case in cases_by_id.values()}
            )
        },
        "manual_review_required": True,
        "canonical_mutation": False,
        "publication_write": False,
        "acceptance": acceptance,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=REPOSITORY_ROOT
        / "docs/quality/verified-claims-step2-adversarial-corpus-20261020.json",
    )
    parser.add_argument("--sources-manifest", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus = _load_json(_resolve_repository_path(args.corpus))
    manifest_path = args.sources_manifest or corpus["source_manifest"]
    result = replay_adversarial_corpus(
        corpus_path=_resolve_repository_path(args.corpus),
        source_manifest_path=_resolve_repository_path(manifest_path),
        output_path=_resolve_repository_path(args.output),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return adversarial_acceptance_exit_code(
        result.get("adversarial_corpus", {}).get("acceptance", {})
        if isinstance(result.get("adversarial_corpus"), Mapping)
        else {}
    )


if __name__ == "__main__":
    raise SystemExit(main())
