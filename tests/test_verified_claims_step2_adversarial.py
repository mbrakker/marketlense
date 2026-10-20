from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pymupdf as fitz
import pytest

from scripts.quality.replay_verified_claims_step2_adversarial import (
    adversarial_acceptance_exit_code,
    compare_adversarial_outcomes,
)
from src.utils.text_normalization import normalize_for_lookup

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = (
    REPOSITORY_ROOT
    / "docs/quality/verified-claims-step2-adversarial-corpus-20261020.json"
)
_SOURCE_HASH = "a" * 64


def _corpus() -> dict[str, object]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def _acceptance_corpus() -> dict[str, object]:
    return {
        "cases": [
            {
                "case_id": "positive-case",
                "candidate_id": "candidate-positive",
                "expected_terminal": "verified_or_corrected",
                "physical_pages": [3],
            },
            {
                "case_id": "negative-case",
                "candidate_id": "candidate-negative",
                "expected_terminal": "unresolved_or_failed",
                "physical_pages": [4],
            },
        ]
    }


def _accepted_positive_row() -> dict[str, object]:
    final_claim = "The source reports a 42% metric for the surveyed population."
    page_note = "Physical page 3 reports the 42% metric for the surveyed population."
    return {
        "candidate_id": "candidate-positive",
        "outcome": "verified",
        "final_claim": final_claim,
        "source_identity": f"Synthetic source|pdf-sha256:{_SOURCE_HASH}",
        "source_pdf_sha256_expected": _SOURCE_HASH,
        "source_pdf_sha256_actual": _SOURCE_HASH,
        "physical_page": 3,
        "physical_pages": [3],
        "original_physical_pages": [3],
        "inspected_physical_pages": [3],
        "supporting_physical_pages": [3],
        "source_truth_notes_by_page": {"3": page_note},
        "correction_attempts": [
            {
                "attempt": 1,
                "claim": final_claim,
                "status": "corrected",
                "issues": [],
            }
        ],
        "verification_attempts": [
            {
                "attempt": 1,
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": page_note,
                "supporting_physical_pages": [3],
                "source_truth_notes_by_page": {"3": page_note},
            }
        ],
    }


def _accepted_negative_row() -> dict[str, object]:
    rejection_note = (
        "Physical page 4 reports a different metric and does not support the "
        "retained claim proposition."
    )
    return {
        "candidate_id": "candidate-negative",
        "outcome": "unresolved",
        "final_claim": "",
        "failure_reason": "verification_failed_twice",
        "source_identity": f"Synthetic source|pdf-sha256:{_SOURCE_HASH}",
        "source_pdf_sha256_expected": _SOURCE_HASH,
        "source_pdf_sha256_actual": _SOURCE_HASH,
        "physical_page": 4,
        "physical_pages": [4],
        "original_physical_pages": [4],
        "inspected_physical_pages": [4],
        "supporting_physical_pages": [],
        "source_truth_notes_by_page": {},
        "correction_attempts": [
            {
                "attempt": 1,
                "claim": "The retained claim is not supported by the source page.",
                "status": "corrected",
                "issues": [],
            },
            {
                "attempt": 2,
                "claim": "The retained claim is not supported by the source page.",
                "status": "corrected",
                "issues": [],
            },
        ],
        "verification_attempts": [
            {
                "attempt": 1,
                "outcome": "rejected",
                "diagnostics": ["source_binding_rejected"],
                "source_truth_notes": rejection_note,
                "supporting_physical_pages": [],
                "source_truth_notes_by_page": {},
            },
            {
                "attempt": 2,
                "outcome": "rejected",
                "diagnostics": ["source_binding_rejected"],
                "source_truth_notes": rejection_note,
                "supporting_physical_pages": [],
                "source_truth_notes_by_page": {},
            },
        ],
    }


def _safe_abstention_row(
    candidate_id: str = "candidate-safe-abstention",
) -> dict[str, object]:
    row = _accepted_negative_row()
    row.update(
        {
            "candidate_id": candidate_id,
            "outcome": "unresolved",
            "failure_reason": "correction_unresolved",
            "verification_attempts": [],
            "correction_attempts": [
                {
                    "attempt": 1,
                    "claim": "",
                    "status": "unresolved",
                    "issues": ["The retained locator is not sufficient for the claim."],
                },
                {
                    "attempt": 2,
                    "claim": "",
                    "status": "unresolved",
                    "issues": ["The retained locator is not sufficient for the claim."],
                },
            ],
        }
    )
    return row


def test_adversarial_acceptance_comparator_accepts_exact_terminal_outcomes() -> None:
    result = {"claims": [_accepted_positive_row(), _accepted_negative_row()]}

    report = compare_adversarial_outcomes(_acceptance_corpus(), result)

    assert report["passed"] is True
    assert report["mismatches"] == []
    assert adversarial_acceptance_exit_code(report) == 0


@pytest.mark.parametrize(
    ("result", "diagnostic_code"),
    [
        (
            {"claims": [_accepted_negative_row()]},
            "missing_result",
        ),
        (
            {
                "claims": [
                    _accepted_positive_row(),
                    _accepted_positive_row(),
                    _accepted_negative_row(),
                ]
            },
            "duplicate_result",
        ),
        (
            {
                "claims": [
                    _accepted_positive_row(),
                    _accepted_negative_row(),
                    {"candidate_id": "unknown", "outcome": "unresolved"},
                ]
            },
            "unknown_result",
        ),
        (
            {
                "claims": [
                    _accepted_positive_row(),
                    _accepted_negative_row(),
                    "malformed-row",
                ]
            },
            "malformed_result",
        ),
    ],
)
def test_adversarial_acceptance_comparator_rejects_identity_contract_violations(
    result: dict[str, object], diagnostic_code: str
) -> None:
    report = compare_adversarial_outcomes(_acceptance_corpus(), result)

    assert report["passed"] is False
    assert diagnostic_code in {item["code"] for item in report["mismatches"]}
    assert adversarial_acceptance_exit_code(report) == 1


@pytest.mark.parametrize(
    ("positive_row", "negative_row", "diagnostic_code"),
    [
        (
            {
                **_accepted_positive_row(),
                "outcome": "unresolved",
            },
            _accepted_negative_row(),
            "unexpected_outcome",
        ),
        (
            {
                **_accepted_positive_row(),
                "supporting_physical_pages": [],
            },
            _accepted_negative_row(),
            "invalid_source_provenance",
        ),
        (
            _accepted_positive_row(),
            {
                **_accepted_negative_row(),
                "outcome": "verified",
            },
            "unexpected_outcome",
        ),
        (
            {
                **_accepted_positive_row(),
                "outcome": "skipped",
            },
            _accepted_negative_row(),
            "unexpected_outcome",
        ),
    ],
)
def test_adversarial_acceptance_comparator_rejects_bad_terminal_or_provenance(
    positive_row: dict[str, object],
    negative_row: dict[str, object],
    diagnostic_code: str,
) -> None:
    report = compare_adversarial_outcomes(
        _acceptance_corpus(), {"claims": [positive_row, negative_row]}
    )

    assert report["passed"] is False
    assert diagnostic_code in {item["code"] for item in report["mismatches"]}
    assert adversarial_acceptance_exit_code(report) == 1


def _diagnostic_codes(report: dict[str, object]) -> set[str]:
    return {item["code"] for item in report["mismatches"]}


def test_adversarial_acceptance_requires_a_successful_verification_attempt() -> None:
    positive = _accepted_positive_row()
    positive["verification_attempts"] = [
        {
            "attempt": 1,
            "outcome": "rejected",
            "diagnostics": ["source_binding_rejected"],
            "source_truth_notes": (
                "Physical page 3 does not support the corrected metric claim."
            ),
            "supporting_physical_pages": [],
            "source_truth_notes_by_page": {},
        }
    ]

    report = compare_adversarial_outcomes(
        _acceptance_corpus(),
        {"claims": [positive, _accepted_negative_row()]},
    )

    assert report["passed"] is False
    assert "missing_successful_verification_attempt" in _diagnostic_codes(report)


def test_adversarial_acceptance_rejects_negative_without_verification_attempt() -> None:
    negative = _accepted_negative_row()
    negative.pop("verification_attempts")

    report = compare_adversarial_outcomes(
        _acceptance_corpus(),
        {"claims": [_accepted_positive_row(), negative]},
    )

    assert report["passed"] is False
    assert "missing_verification_rejection" in _diagnostic_codes(report)


def test_adversarial_acceptance_accepts_bounded_source_mismatch_abstention() -> None:
    negative = _safe_abstention_row("candidate-negative")

    report = compare_adversarial_outcomes(
        _acceptance_corpus(),
        {"claims": [_accepted_positive_row(), negative]},
    )

    assert report["passed"] is True
    assert report["mismatches"] == []


def test_adversarial_acceptance_reports_negative_terminal_categories() -> None:
    safe = _safe_abstention_row()
    corpus = {
        "cases": [
            {
                "case_id": "positive-case",
                "candidate_id": "candidate-positive",
                "expected_terminal": "verified_or_corrected",
                "physical_pages": [3],
            },
            {
                "case_id": "verified-rejection-case",
                "candidate_id": "candidate-negative",
                "expected_terminal": "unresolved_or_failed",
                "physical_pages": [4],
            },
            {
                "case_id": "safe-abstention-case",
                "candidate_id": "candidate-safe-abstention",
                "expected_terminal": "unresolved_or_failed",
                "physical_pages": [4],
            },
        ]
    }

    report = compare_adversarial_outcomes(
        corpus,
        {
            "claims": [
                _accepted_positive_row(),
                _accepted_negative_row(),
                safe,
            ]
        },
    )

    assert report["passed"] is True
    assert report["negative_acceptance_categories"] == {
        "independently_verified_rejection": {
            "count": 1,
            "candidate_ids": ["candidate-negative"],
        },
        "safe_correction_abstention": {
            "count": 1,
            "candidate_ids": ["candidate-safe-abstention"],
        },
    }


def test_adversarial_acceptance_rejects_provider_failure_as_negative_evidence() -> None:
    negative = _accepted_negative_row()
    negative["failure_reason"] = "verification_non_retryable"
    negative["verification_attempts"] = [
        {
            "attempt": 1,
            "outcome": "rejected",
            "diagnostics": [
                "verification_provider_error",
                "error_code:provider_timeout",
                "retryable:false",
            ],
            "source_truth_notes": "",
            "supporting_physical_pages": [],
            "source_truth_notes_by_page": {},
        }
    ]

    report = compare_adversarial_outcomes(
        _acceptance_corpus(),
        {"claims": [_accepted_positive_row(), negative]},
    )

    assert report["passed"] is False
    assert "missing_genuine_verification_rejection" in _diagnostic_codes(report)


def test_adversarial_acceptance_rejects_malformed_correction_abstention() -> None:
    negative = _safe_abstention_row("candidate-negative")
    negative["correction_attempts"][0]["status"] = "failed"

    report = compare_adversarial_outcomes(
        _acceptance_corpus(),
        {"claims": [_accepted_positive_row(), negative]},
    )

    assert report["passed"] is False
    assert "missing_verification_rejection" in _diagnostic_codes(report)


def test_adversarial_acceptance_rejects_provider_correction_as_abstention() -> None:
    negative = _safe_abstention_row("candidate-negative")
    negative["correction_attempts"][1]["issues"] = [
        "correction_provider_error",
        "error_code:provider_timeout",
        "retryable:false",
    ]

    report = compare_adversarial_outcomes(
        _acceptance_corpus(),
        {"claims": [_accepted_positive_row(), negative]},
    )

    assert report["passed"] is False
    assert "missing_verification_rejection" in _diagnostic_codes(report)


def test_adversarial_acceptance_requires_ordered_correction_abstention() -> None:
    negative = _safe_abstention_row("candidate-negative")
    negative["correction_attempts"] = list(reversed(negative["correction_attempts"]))

    report = compare_adversarial_outcomes(
        _acceptance_corpus(),
        {"claims": [_accepted_positive_row(), negative]},
    )

    assert report["passed"] is False
    assert "missing_correction_attempts" in _diagnostic_codes(report)


def test_adversarial_acceptance_rejects_conflicting_verification_trail() -> None:
    negative = _safe_abstention_row("candidate-negative")
    negative["verification_attempts"] = [
        {
            "attempt": 1,
            "outcome": "verified",
            "diagnostics": [],
            "source_truth_notes": "The page supports a different claim.",
            "supporting_physical_pages": [],
            "source_truth_notes_by_page": {},
        }
    ]

    report = compare_adversarial_outcomes(
        _acceptance_corpus(),
        {"claims": [_accepted_positive_row(), negative]},
    )

    assert report["passed"] is False
    assert "missing_genuine_verification_rejection" in _diagnostic_codes(report)


def test_adversarial_acceptance_rejects_strict_page_four_recovery_for_abstention() -> (
    None
):
    corpus = {
        "cases": [
            {
                "case_id": "BIG-ADV-002",
                "candidate_id": "candidate-safe-abstention",
                "expected_terminal": "unresolved_or_failed",
                "physical_pages": [8],
            }
        ]
    }
    negative = _safe_abstention_row()
    negative.update(
        {
            "physical_page": 8,
            "physical_pages": [8],
            "original_physical_pages": [8],
            "inspected_physical_pages": [8, 4],
            "recovered_physical_pages": [4],
        }
    )

    report = compare_adversarial_outcomes(corpus, {"claims": [negative]})

    assert report["passed"] is False
    assert {
        "strict_inspected_binding_not_preserved",
        "strict_recovery_binding_present",
    }.issubset(_diagnostic_codes(report))


def test_adversarial_acceptance_rejects_strict_wrong_page_rescued_by_page_four() -> (
    None
):
    corpus = {
        "cases": [
            {
                "case_id": "BIG-ADV-002",
                "candidate_id": "candidate-negative",
                "expected_terminal": "unresolved_or_failed",
                "physical_pages": [8],
            }
        ]
    }
    negative = _accepted_negative_row()
    negative.update(
        {
            "physical_page": 8,
            "physical_pages": [8],
            "original_physical_pages": [8],
            "inspected_physical_pages": [8, 4],
            "supporting_physical_pages": [4],
            "source_truth_notes_by_page": {
                "4": "Physical page 4 contains the preferred-wallet finding."
            },
        }
    )
    for attempt in negative["verification_attempts"]:
        attempt.update(
            {
                "source_truth_notes": (
                    "Physical page 8 was assessed, but page 4 supports the claim."
                ),
                "supporting_physical_pages": [4],
                "source_truth_notes_by_page": {
                    "4": "Physical page 4 contains the preferred-wallet finding."
                },
            }
        )

    report = compare_adversarial_outcomes(corpus, {"claims": [negative]})

    assert report["passed"] is False
    assert "negative_supporting_pages_present" in _diagnostic_codes(report)


def test_adversarial_acceptance_requires_positive_pages_to_match_attempt() -> None:
    positive = _accepted_positive_row()
    positive["inspected_physical_pages"] = [3, 4]
    positive["verification_attempts"][0].update(
        {
            "supporting_physical_pages": [4],
            "source_truth_notes_by_page": {
                "4": (
                    "Physical page 4 reports the 42% metric for the "
                    "surveyed population."
                )
            },
        }
    )

    report = compare_adversarial_outcomes(
        _acceptance_corpus(),
        {"claims": [positive, _accepted_negative_row()]},
    )

    assert report["passed"] is False
    assert "verification_binding_mismatch" in _diagnostic_codes(report)


@pytest.mark.parametrize(
    "field_update",
    [
        {"source_pdf_sha256_expected": "not-a-sha256"},
        {"source_pdf_sha256_actual": "b" * 64},
        {"source_identity": f"Synthetic source|pdf-sha256:{'b' * 64}"},
    ],
)
def test_adversarial_acceptance_rejects_invalid_source_hash_identity(
    field_update: dict[str, object],
) -> None:
    positive = _accepted_positive_row()
    positive.update(field_update)

    report = compare_adversarial_outcomes(
        _acceptance_corpus(),
        {"claims": [positive, _accepted_negative_row()]},
    )

    assert report["passed"] is False
    assert "invalid_source_provenance" in _diagnostic_codes(report)


def _provider_free_corpus_row(case: dict[str, object]) -> dict[str, object]:
    pages = list(case["physical_pages"])
    report = str(case["report"])
    candidate_id = str(case["candidate_id"])
    case_hash = hashlib.sha256(report.encode("utf-8")).hexdigest()
    source_identity = f"{report}|pdf-sha256:{case_hash}"
    if case["expected_terminal"] == "unresolved_or_failed":
        rejection_note = (
            f"Physical page {pages[0]} was assessed and does not support the "
            f"retained source binding: {case['source_truth']}"
        )
        attempts = [
            {
                "attempt": attempt,
                "outcome": "rejected",
                "diagnostics": ["source_binding_rejected"],
                "source_truth_notes": rejection_note,
                "supporting_physical_pages": [],
                "source_truth_notes_by_page": {},
            }
            for attempt in (1, 2)
        ]
        correction_attempts = [
            {
                "attempt": attempt,
                "claim": (
                    "The retained claim is not supported by the bound source page."
                ),
                "status": "corrected",
                "issues": [],
            }
            for attempt in (1, 2)
        ]
        return {
            "candidate_id": candidate_id,
            "outcome": "failed_verification",
            "final_claim": "",
            "failure_reason": "verification_failed_twice",
            "source_identity": source_identity,
            "source_pdf_sha256_expected": case_hash,
            "source_pdf_sha256_actual": case_hash,
            "physical_page": pages[0],
            "physical_pages": pages,
            "original_physical_pages": pages,
            "inspected_physical_pages": pages,
            "supporting_physical_pages": [],
            "source_truth_notes_by_page": {},
            "correction_attempts": correction_attempts,
            "verification_attempts": attempts,
        }

    final_claim = str(case["source_truth"])
    page_note = f"Physical page {pages[0]} reports the source finding: {final_claim}"
    return {
        "candidate_id": candidate_id,
        "outcome": "verified",
        "final_claim": final_claim,
        "source_identity": source_identity,
        "source_pdf_sha256_expected": case_hash,
        "source_pdf_sha256_actual": case_hash,
        "physical_page": pages[0],
        "physical_pages": pages,
        "original_physical_pages": pages,
        "inspected_physical_pages": pages,
        "supporting_physical_pages": pages,
        "source_truth_notes_by_page": {
            str(page): f"Physical page {page} reports the source finding: {final_claim}"
            for page in pages
        },
        "correction_attempts": [
            {
                "attempt": 1,
                "claim": final_claim,
                "status": "corrected",
                "issues": [],
            }
        ],
        "verification_attempts": [
            {
                "attempt": 1,
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": page_note,
                "supporting_physical_pages": pages,
                "source_truth_notes_by_page": {
                    str(
                        page
                    ): f"Physical page {page} reports the source finding: {final_claim}"
                    for page in pages
                },
            }
        ],
    }


def test_provider_free_comparator_covers_all_nine_corpus_identities() -> None:
    corpus = _corpus()
    cases = corpus["cases"]
    rows = [_provider_free_corpus_row(case) for case in cases]

    report = compare_adversarial_outcomes(corpus, {"claims": rows})

    assert report["passed"] is True
    assert report["case_count"] == 9
    assert report["matched_count"] == 9

    corrupted_rows = deepcopy(rows)
    corrupted = next(
        row for row in corrupted_rows if row["candidate_id"] == "big-adv-wrong-page"
    )
    corrupted["outcome"] = "unresolved"
    corrupted["supporting_physical_pages"] = [4]
    corrupted["source_truth_notes_by_page"] = {
        "4": "Physical page 4 contains the preferred-wallet finding."
    }
    for attempt in corrupted["verification_attempts"]:
        attempt["supporting_physical_pages"] = [4]
        attempt["source_truth_notes_by_page"] = {
            "4": "Physical page 4 contains the preferred-wallet finding."
        }

    corrupted_report = compare_adversarial_outcomes(corpus, {"claims": corrupted_rows})

    assert corrupted_report["passed"] is False
    assert "negative_supporting_pages_present" in _diagnostic_codes(corrupted_report)


def test_adversarial_corpus_covers_each_required_mutation_boundary() -> None:
    corpus = _corpus()
    cases = corpus.get("cases")
    assert isinstance(cases, list)
    assert len(cases) == 9
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert {case["mutation"] for case in cases} >= {
        "metric_unit",
        "metric_label_relationship",
        "cohort_denominator",
        "geography",
        "forecast_observation_status",
        "reporting_period",
        "physical_source_page",
        "unsupported_causal_interpretation",
        "conflicting_chart_total",
    }
    for case in cases:
        assert case["report"]
        assert case["candidate_id"]
        assert case["original_claim"]
        assert case["evidence_id"]
        assert case["physical_pages"]
        assert case["source_anchor"]
        assert case["source_truth"]
        assert case["replacement_policy"] in {
            "report_level_replacement_allowed",
            "strict_original_direction",
        }
        assert case["expected_terminal"] in {
            "verified_or_corrected",
            "unresolved_or_failed",
        }


@pytest.mark.integration
def test_adversarial_corpus_binds_to_hash_matched_actual_pdfs() -> None:
    corpus = _corpus()
    manifest_path = REPOSITORY_ROOT / str(corpus["source_manifest"])
    if not manifest_path.is_file():
        pytest.skip("retained second-cohort source manifest is not available locally")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_records = manifest.get("source_pdfs")
    assert isinstance(source_records, dict)

    for case in corpus["cases"]:
        source = source_records[case["report"]]
        pdf_path = Path(str(source["path"]))
        if not pdf_path.is_absolute():
            pdf_path = REPOSITORY_ROOT / pdf_path
        if not pdf_path.is_file():
            pytest.skip(f"source PDF unavailable locally: {case['report']}")
        actual_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        assert actual_hash == str(source["sha256"]).lower()
        with fitz.open(pdf_path) as document:
            page_count = document.page_count
            for page_number in case["physical_pages"]:
                assert 1 <= page_number <= page_count
                page_text = normalize_for_lookup(document[page_number - 1].get_text())
                assert page_text
        assert len(normalize_for_lookup(case["source_truth"])) >= 24
