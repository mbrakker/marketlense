from __future__ import annotations

import hashlib
import json

import pymupdf as fitz
import pytest

from scripts.quality.replay_verified_claims_step2 import _load_explicit_cohort_inputs
from src.generators.verified_claims_visual_generator import evaluate_shortlisted_claims
from tests._test_verified_claims_visual_generator.cases_01_visual import (
    _claim,
    _ctx,
    _dependencies,
    _request,
    _settings,
)


def _evaluate_with_binding(
    tmp_path,
    *,
    original_pages: list[int],
    recovered_pages: list[int],
    supporting_pages: list[int],
):
    claim = _claim("binding-case", "Original analytical direction")
    claim["pages"] = original_pages
    claim["_visual_replacement_policy"] = "report_level_replacement_allowed"
    claim["evidence_spans"] = (
        [{"evidence_id": "f1", "page": original_pages[0]}] if original_pages else []
    )
    request = _request(tmp_path, [claim])
    request.recovery_enabled = bool(recovered_pages)
    request.recovery_candidates = {
        "binding-case": [
            {
                "physical_page": page,
                "source_identity": request.source_identity,
                "reason": "retained_page_is_section_divider",
            }
            for page in recovered_pages
        ]
    }
    response = iter(
        [
            {
                "claim": "Source-grounded corrected direction",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The cited page reports the corrected relationship for the "
                    "named population."
                ),
                "supporting_physical_pages": supporting_pages,
                "source_truth_notes_by_page": {
                    str(page): (
                        "The cited page reports the corrected relationship for the "
                        "named population."
                    )
                    for page in supporting_pages
                },
            },
        ]
    )
    return evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(response, [], []),
    ).claims[0]


@pytest.mark.parametrize(
    ("original_pages", "recovered_pages", "supporting_pages", "expected_status"),
    [
        ([5], [7], [5], "retained"),
        ([], [7], [7], "provisional_recovered"),
        ([5], [7], [5, 7], "provisional_recovered"),
    ],
)
def test_source_binding_status_is_derived_from_actual_supporting_pages(
    tmp_path,
    original_pages,
    recovered_pages,
    supporting_pages,
    expected_status,
):
    result = _evaluate_with_binding(
        tmp_path,
        original_pages=original_pages,
        recovered_pages=recovered_pages,
        supporting_pages=supporting_pages,
    )

    assert result.outcome == "verified"
    assert result.source_binding_status == expected_status
    assert result.original_physical_pages == original_pages
    assert result.supporting_physical_pages == supporting_pages


def test_initially_page_less_claim_without_recovery_remains_skipped(tmp_path):
    claim = _claim("page-less", "Original analytical direction")
    claim["pages"] = []
    claim["evidence_spans"] = []

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, [claim]),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(iter(()), [], []),
    ).claims[0]

    assert result.outcome == "skipped"
    assert result.failure_reason == "physical_page_missing"
    assert result.original_physical_pages == []
    assert result.source_binding_status == "retained"


def _explicit_snapshot(tmp_path, insight: dict[str, object], *, page_count: int = 1):
    pdf_path = tmp_path / "source.pdf"
    document = fitz.open()
    for page_number in range(page_count):
        page_text = (
            "A unique source passage on physical page one for inspection."
            if page_number == 0
            else f"Physical page {page_number + 1}."
        )
        document.new_page().insert_text((72, 72), page_text)
    document.save(pdf_path)
    document.close()
    artifact_path = (
        tmp_path / "run" / "output" / "artifact" / "report_analysis" / "artifacts.json"
    )
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        json.dumps({"insights_final": [insight]}), encoding="utf-8"
    )
    source_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    cohort_path = tmp_path / "cohort_result.json"
    cohort_path.write_text(
        json.dumps(
            {
                "reports": [
                    {
                        "publisher_id": "Test Report",
                        "git_sha": "producer-commit",
                        "run_directory": str(tmp_path / "run"),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_pdfs": {
                    "Test Report": {"path": str(pdf_path), "sha256": source_hash}
                }
            }
        ),
        encoding="utf-8",
    )
    return cohort_path, manifest_path


def test_explicit_input_preserves_page_less_binding_for_provisional_inspection(
    tmp_path,
):
    cohort_path, manifest_path = _explicit_snapshot(
        tmp_path,
        {
            "id": "page-less-exact",
            "text": "A source-backed finding from the first physical page.",
            "evidence_id": "quote-1",
            "evidence": "A unique source passage on physical page one for inspection.",
            "evidence_spans": [
                {
                    "evidence_id": "quote-1",
                    "text": (
                        "A unique source passage on physical page one for inspection."
                    ),
                }
            ],
            "pages": [],
        },
    )

    report = _load_explicit_cohort_inputs(cohort_path, manifest_path)["reports"][0]

    claim = report["eligible_claims"][0]
    assert claim["pages"] == []
    assert claim["_provisional_input_pages"] == [1]
    assert report["claim_metadata"]["page-less-exact"]["original_physical_pages"] == []


@pytest.mark.parametrize(
    "physical_fields",
    [
        {"physical_page": 1},
        {"evidence_spans": [{"evidence_id": "quote-1", "page": 1}]},
    ],
)
def test_explicit_input_accepts_independently_established_physical_pages(
    tmp_path, physical_fields
):
    insight = {
        "id": "explicit-page",
        "text": "A retained finding with an established physical page.",
        "evidence_id": "quote-1",
        "pages": [],
        **physical_fields,
    }
    cohort_path, manifest_path = _explicit_snapshot(tmp_path, insight)

    report = _load_explicit_cohort_inputs(cohort_path, manifest_path)["reports"][0]

    assert report["unavailable"] == []
    assert report["eligible_claims"][0]["pages"] == [1]
    assert report["claim_metadata"]["explicit-page"]["original_physical_pages"] == [1]


def test_explicit_input_preserves_strict_wrong_page_policy(tmp_path):
    cohort_path, manifest_path = _explicit_snapshot(
        tmp_path,
        {
            "id": "strict-page",
            "text": "A retained finding with a strict source page.",
            "evidence_id": "finding-1",
            "pages": [1],
            "_visual_replacement_policy": "strict_original_direction",
        },
    )

    report = _load_explicit_cohort_inputs(cohort_path, manifest_path)["reports"][0]

    assert report["eligible_claims"][0]["_visual_replacement_policy"] == (
        "strict_original_direction"
    )


@pytest.mark.parametrize(
    "insight",
    [
        {
            "id": "conflicting-pages",
            "text": "A retained finding.",
            "evidence_id": "finding-1",
            "pages": [1],
            "physical_page": 2,
        },
        {
            "id": "conflicting-span",
            "text": "A retained finding.",
            "evidence_id": "finding-1",
            "pages": [1],
            "evidence_spans": [{"evidence_id": "finding-1", "page": 2}],
        },
        {
            "id": "out-of-range-span",
            "text": "A retained finding.",
            "evidence_id": "finding-1",
            "pages": [],
            "evidence_spans": [{"evidence_id": "finding-1", "page": 2}],
        },
    ],
)
def test_explicit_input_fails_closed_on_conflicting_or_invalid_physical_pages(
    tmp_path, insight
):
    cohort_path, manifest_path = _explicit_snapshot(tmp_path, insight)

    report = _load_explicit_cohort_inputs(cohort_path, manifest_path)["reports"][0]

    assert report["eligible_claims"] == []
    assert report["unavailable"][0]["reason"] in {
        "retained_claim_physical_page_conflict",
        "retained_claim_page_out_of_range",
    }
