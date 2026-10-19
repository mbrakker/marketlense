from __future__ import annotations

import hashlib
import json

import pymupdf as fitz
import pytest

from scripts.quality.replay_verified_claims_step2 import (
    REFERENCE_PATH,
    _assert_outcome_count_arithmetic,
    _editorial_duplicate_pairs,
    _editorial_duplicate_status,
    _editorial_quality_report,
    _editorially_duplicate,
    _load_json,
    _outcome_counts,
    _page_is_likely_divider,
    _recovery_candidates_for_claim,
    _reference_claims,
    _retained_claims,
    _shadow_replacement_selection,
    _usage_summary,
    _verified_corrected_insight,
    replay_frozen_step2,
)
from src.contracts.run_context import RunContext
from src.generators.verified_claims_recovery import build_verified_claims_shadow_request


def test_step2_replay_reports_provider_unavailable_without_fabricated_claims():
    report = replay_frozen_step2(provider_available=False)

    assert report["provider_status"] == "skipped_unavailable"
    assert report["fabricated_fixture_substitution"] is False
    assert report["reference_set"]["case_count"] == 15
    assert report["reference_set"]["candidate_variant_count"] == 39
    assert report["reports"] == [
        "Capgemini Research Institute",
        "Activate",
        "KPMG",
        "Reuters Institute",
        "Adjust",
    ]
    assert all(
        case["visual_assessment"] == "skipped_provider_unavailable"
        for case in report["cases"]
    )


def test_live_reference_claim_assembly_preserves_fixture_page_override():
    reference = _load_json(REFERENCE_PATH)

    claims, metadata = _reference_claims(reference, "Activate")

    wrong_page = next(
        claim for claim in claims if claim["candidate_id"] == "ACT-004-wrong-page"
    )
    assert wrong_page["pages"] == [15]
    assert wrong_page["_visual_replacement_policy"] == "strict_original_direction"
    assert metadata["ACT-004-wrong-page"]["source_pages"] == [15]


def test_retained_shortlist_replay_assembles_exact_frozen_five_claims():
    reference = _load_json(REFERENCE_PATH)
    expected_counts = {
        "Capgemini Research Institute": 5,
        "Activate": 7,
        "KPMG": 5,
        "Reuters Institute": 6,
        "Adjust": 6,
    }
    total = 0
    for report, expected_count in expected_counts.items():
        claims, metadata, unavailable = _retained_claims(reference, report)
        assert len(claims) == expected_count
        assert len(metadata) == expected_count
        assert unavailable == []
        assert all(claim["candidate_id"] == claim["id"] for claim in claims)
        assert all(claim["pages"] for claim in claims)
        assert all(
            claim["_visual_replacement_policy"] == "report_level_replacement_allowed"
            for claim in claims
        )
        total += len(claims)
    assert total == 29


def test_retained_replay_keeps_doc_map_pages_as_provisional_source_context() -> None:
    reference = _load_json(REFERENCE_PATH)

    claims, metadata, unavailable = _retained_claims(reference, "Reuters Institute")

    assert unavailable == []
    newsroom_claim = next(
        claim
        for claim in claims
        if claim["candidate_id"] == "newsroom-ai-uses-and-oversight"
    )
    assert newsroom_claim["evidence_id"] == "latest-tales-ai-newsroom"
    assert newsroom_claim["pages"] == [30]
    assert (
        metadata["newsroom-ai-uses-and-oversight"]["source_binding_resolution"]
        == "provisional_page_inspection"
    )
    assert metadata["newsroom-ai-uses-and-oversight"]["source_binding_before"] == {
        "evidence_id": "latest-tales-ai-newsroom",
        "pages": [30],
    }
    assert metadata["newsroom-ai-uses-and-oversight"]["source_binding_after"] == {
        "evidence_id": "latest-tales-ai-newsroom",
        "pages": [30],
        "source_packs": ["doc_map"],
        "canonical_promotion": False,
    }

    activate_claims, activate_metadata, _ = _retained_claims(reference, "Activate")
    assistant_claim = next(
        claim
        for claim in activate_claims
        if claim["candidate_id"] == "activate-digital-assistant-access-forecast"
    )
    assert assistant_claim["evidence_id"] == "s4"
    assert (
        activate_metadata["activate-digital-assistant-access-forecast"][
            "source_binding_resolution"
        ]
        == "provisional_page_inspection"
    )


def test_step2_outcome_counts_make_retry_successes_mutually_exclusive() -> None:
    rows = [
        {"outcome": "verified"},
        {"outcome": "verified_after_retry"},
        {"outcome": "unresolved"},
        {"outcome": "failed_verification"},
        {"outcome": "skipped"},
    ]
    counts = _outcome_counts(rows)
    _assert_outcome_count_arithmetic(rows, counts)

    assert counts == {
        "verified_total": 2,
        "verified_first_pass": 1,
        "verified_after_retry": 1,
        "failed_verification": 1,
        "unresolved": 1,
        "skipped": 1,
    }


def test_step2_outcome_count_arithmetic_rejects_unknown_terminal_outcome() -> None:
    rows = [{"outcome": "verified"}, {"outcome": "provider_unknown"}]

    try:
        _assert_outcome_count_arithmetic(rows, _outcome_counts(rows))
    except RuntimeError as error:
        assert "terminal outcome counts" in str(error)
    else:
        raise AssertionError("unknown outcomes must fail closed")


def test_recovery_resolver_maps_divider_to_substantive_finding_pages() -> None:
    reference = _load_json(REFERENCE_PATH)
    claims, _, unavailable = _retained_claims(reference, "Capgemini Research Institute")
    assert unavailable == []
    claim = next(
        item for item in claims if item["candidate_id"] == "consumer-control-of-ai"
    )

    candidates = _recovery_candidates_for_claim(
        reference, "Capgemini Research Institute", claim
    )

    pages = [item["physical_page"] for item in candidates]
    assert 35 in pages
    assert 36 in pages
    assert all(item["physical_page"] != 30 for item in candidates)
    assert all(
        item["source_identity"].startswith("Capgemini Research Institute|")
        for item in candidates
    )


def test_recovery_resolver_rejects_unrelated_page_text() -> None:
    claim = {
        "candidate_id": "candidate-1",
        "text": "A finding about quantum satellites",
        "evidence_id": "missing-section",
        "evidence": "A finding about quantum satellites",
        "pages": [5],
    }

    assert (
        _recovery_candidates_for_claim(
            {
                "source_pdfs": {},
                "retained_run": {},
                "report_artifact_digests": {},
            },
            "Unknown report",
            claim,
        )
        == []
    )


def test_recovery_resolver_treats_contents_listing_as_navigation() -> None:
    contents_page = """
    1 Contents About the Author 2 Acknowledgements 2 Executive Summary 3
    1. Pressures on Journalism Mount 7
    2. Answer Engines and the Implications for Traffic 10
    3. Content Strategies Shift towards Distinctiveness 15
    4. Social Media's Mid-Life Crisis 18
    """

    assert _page_is_likely_divider(contents_page, "business models")


def test_recovery_resolver_does_not_offer_reuters_contents_page() -> None:
    reference = _load_json(REFERENCE_PATH)
    claims, _, unavailable = _retained_claims(reference, "Reuters Institute")
    assert unavailable == []
    claim = next(
        item
        for item in claims
        if item["candidate_id"] == "subscription-membership-priority"
    )

    candidates = _recovery_candidates_for_claim(reference, "Reuters Institute", claim)

    assert 38 in [item["physical_page"] for item in candidates]
    assert 3 not in [item["physical_page"] for item in candidates]


def test_shadow_replacement_selection_rejects_duplicate_and_keeps_specific() -> None:
    rows = [
        {
            "candidate_id": "candidate-1",
            "original_claim": "Old direction",
            "source_identity": "report|pdf-sha256:" + "a" * 64,
            "evidence_ids": ["old-evidence"],
            "evidence_spans": [],
            "outcome": "verified",
            "final_claim": (
                "A distinct 73% adoption result supports a focused commercial action."
            ),
            "recovered_physical_pages": [7],
            "inspected_physical_pages": [5, 7],
            "supporting_physical_pages": [7],
            "source_truth_notes_by_page": {
                "7": "Page 7 reports the 73% adoption result for the named cohort."
            },
            "recovery_reason": "retained_page_is_section_divider",
            "recovery_candidates": [
                {
                    "physical_page": 7,
                    "evidence_id": "theme-a",
                    "source_pack": "findings",
                    "score": 80,
                }
            ],
        },
        {
            "candidate_id": "candidate-2",
            "original_claim": "Another direction",
            "source_identity": "report|pdf-sha256:" + "a" * 64,
            "evidence_ids": ["old-evidence-2"],
            "evidence_spans": [],
            "outcome": "verified",
            "final_claim": (
                "A distinct 73% adoption result supports a focused commercial action."
            ),
            "recovered_physical_pages": [8],
            "inspected_physical_pages": [5, 8],
            "supporting_physical_pages": [8],
            "source_truth_notes_by_page": {
                "8": "Page 8 reports the 73% adoption result for the named cohort."
            },
            "recovery_reason": "retained_page_is_section_divider",
            "recovery_candidates": [
                {
                    "physical_page": 8,
                    "evidence_id": "theme-a",
                    "source_pack": "findings",
                    "score": 70,
                }
            ],
        },
    ]
    selection = _shadow_replacement_selection(
        report="Report",
        baseline_insights=[
            {
                "id": "baseline",
                "text": "Existing unrelated insight",
                "evidence_id": "other",
            }
        ],
        retained_rows=rows,
        editorial_plan={
            "themes": [{"priority": 1, "theme": "Theme A", "evidence_ids": ["theme-a"]}]
        },
    )

    assert selection["selected_count"] == 1
    assert selection["selected"][0]["candidate_id"] == "candidate-1"
    assert (
        selection["rejected_or_abstained"][0]["selection_reason"]
        == "duplicate_of:candidate-1"
    )


def test_shadow_selection_keeps_unstructured_scope_near_duplicates_for_review() -> None:
    def row(candidate_id: str, claim: str, page: int, score: int) -> dict:
        return {
            "candidate_id": candidate_id,
            "original_claim": "Original direction",
            "source_identity": "report|pdf-sha256:" + "a" * 64,
            "evidence_ids": [f"old-{candidate_id}"],
            "evidence_spans": [],
            "outcome": "verified",
            "final_claim": claim,
            "recovered_physical_pages": [page],
            "inspected_physical_pages": [page],
            "supporting_physical_pages": [page],
            "source_truth_notes_by_page": {
                str(page): (
                    "The page supports the report-specific finding and its scope."
                )
            },
            "recovery_candidates": [
                {
                    "physical_page": page,
                    "evidence_id": f"theme-{candidate_id}",
                    "source_pack": "findings",
                    "score": score,
                }
            ],
        }

    selection = _shadow_replacement_selection(
        report="Report",
        baseline_insights=[],
        retained_rows=[
            row(
                "candidate-1",
                "Global app installs fell 10% while sessions rose 5% in 2025.",
                7,
                80,
            ),
            row(
                "candidate-2",
                "Regional app installs fell 10% while sessions rose 5% in 2025.",
                8,
                70,
            ),
        ],
        editorial_plan={
            "themes": [
                {
                    "priority": 1,
                    "theme": "Theme A",
                    "evidence_ids": ["theme-candidate-1", "theme-candidate-2"],
                }
            ]
        },
    )

    assert selection["selected_count"] == 2
    assert selection["rejected_or_abstained"] == []
    assert selection["ambiguous_duplicate_pairs"] == [["candidate-1", "candidate-2"]]


def test_exact_corrected_duplicate_is_detected_before_metric_conflicts() -> None:
    left = {
        "id": "candidate-1",
        "text": "The same final source-grounded conclusion.",
        "metric": {"value": "12", "cohort": "legacy cohort"},
    }
    right = {
        "id": "candidate-2",
        "text": "The same final source-grounded conclusion.",
        "metric": {"value": "73", "cohort": "current cohort"},
    }

    assert _editorially_duplicate(left, right, set()) is True


def test_same_id_provenance_repair_is_not_rejected_as_self_duplicate() -> None:
    row = {
        "candidate_id": "candidate-1",
        "original_claim": "The same final source-grounded conclusion.",
        "source_identity": "Report|pdf-sha256:" + "a" * 64,
        "evidence_ids": ["old-evidence"],
        "outcome": "verified",
        "final_claim": "The same final source-grounded conclusion.",
        "recovered_physical_pages": [7],
        "inspected_physical_pages": [5, 7],
        "supporting_physical_pages": [7],
        "source_truth_notes_by_page": {
            "7": "Page 7 contains the source relationship supporting the conclusion."
        },
        "recovery_candidates": [
            {
                "physical_page": 7,
                "evidence_id": "replacement-evidence",
                "source_pack": "findings",
                "score": 80,
            }
        ],
    }

    selection = _shadow_replacement_selection(
        report="Report",
        baseline_insights=[
            {
                "id": "candidate-1",
                "text": row["final_claim"],
                "evidence_id": "old-evidence",
                "evidence": "The retained source relationship.",
            }
        ],
        retained_rows=[row],
        editorial_plan={
            "themes": [
                {
                    "priority": 1,
                    "theme": "Theme A",
                    "evidence_ids": ["old-evidence"],
                }
            ]
        },
        source_page_text_by_page={
            7: "Page 7 contains the source relationship supporting the conclusion."
        },
    )

    assert selection["selected_count"] == 1
    assert selection["selected"][0]["candidate_id"] == "candidate-1"


def test_near_duplicate_propositions_are_removed_across_provisional_evidence_ids(
) -> None:
    left = {
        "id": "candidate-1",
        "text": (
            "Dealmakers prioritize transactions that deepen capabilities and "
            "strengthen strategic position in 2026."
        ),
        "evidence_id": "provisional-page:candidate-1",
    }
    right = {
        "id": "candidate-2",
        "text": (
            "Dealmakers increasingly prioritize transactions deepening capabilities "
            "and strengthening strategic position during 2026."
        ),
        "evidence_id": "provisional-page:candidate-2",
    }

    assert _editorially_duplicate(left, right, {("candidate-1", "candidate-2")})


def test_near_duplicate_guard_preserves_distinct_metric_bindings() -> None:
    left = {
        "id": "candidate-1",
        "text": "The APAC pipeline outlook is higher than lower in 2026.",
        "evidence_id": "provisional-page:candidate-1",
        "metric": {"value": "62", "geography": "APAC"},
    }
    right = {
        "id": "candidate-2",
        "text": "The Americas pipeline outlook is higher than lower in 2026.",
        "evidence_id": "provisional-page:candidate-2",
        "metric": {"value": "58", "geography": "Americas"},
    }

    assert not _editorially_duplicate(
        left, right, {("candidate-1", "candidate-2")}
    )


@pytest.mark.parametrize(
    ("left_text", "right_text"),
    [
        (
            "Among enterprise users, adoption rose 20% in 2025.",
            "Among consumer users, adoption rose 20% in 2025.",
        ),
        (
            "Revenue rose 20% while users rose 5% in 2025.",
            "Sessions rose 20% while users rose 5% in 2025.",
        ),
        (
            "In 2025, global app installs fell 10% while sessions rose 5%.",
            "In 2024, global app installs fell 10% while sessions rose 5%.",
        ),
    ],
)
def test_unstructured_material_propositions_are_not_proven_equivalent(
    left_text: str, right_text: str
) -> None:
    left = {"id": "candidate-1", "text": left_text}
    right = {"id": "candidate-2", "text": right_text}
    quality = _editorial_quality_report("Report", [left, right])
    duplicate_pairs = _editorial_duplicate_pairs(quality)

    assert ("candidate-1", "candidate-2") in duplicate_pairs
    assert _editorial_duplicate_status(left, right, duplicate_pairs) in {
        "distinct",
        "ambiguous",
    }


def test_verified_corrected_insight_uses_replacement_page_not_retained_facts() -> None:
    row = {
        "candidate_id": "candidate-1",
        "final_claim": "The source reports 73% adoption among video users.",
        "evidence_ids": ["old-evidence"],
        "evidence_spans": [{"source_pack": "doc_map", "page": 1}],
        "original_physical_pages": [1],
        "supporting_physical_pages": [2],
        "source_truth_notes_by_page": {
            "2": "The verifier explains that page 2 supports the replacement."
        },
    }
    baseline = {
        "candidate-1": {
            "id": "candidate-1",
            "text": "The retained claim reports 12% legacy adoption.",
            "evidence_id": "old-evidence",
            "evidence": "The old retained evidence reports 12%.",
            "metric": {"value": "12", "cohort": "legacy cohort"},
            "pages": [1],
        }
    }

    insight = _verified_corrected_insight(
        row,
        baseline,
        source_page_text_by_page={
            2: "The source reports 73% adoption among video users."
        },
    )

    assert insight is not None
    assert insight["text"] == row["final_claim"]
    assert insight["evidence"] == (
        "The source reports 73% adoption among video users."
    )
    assert insight["evidence_id"] == "provisional-page:candidate-1"
    assert insight["pages"] == [2]
    assert "metric" not in insight
    assert "old retained evidence" not in insight["evidence"]


def test_shadow_selection_keeps_visual_replacement_pending_canonical_approval() -> None:
    row = {
        "candidate_id": "candidate-1",
        "original_claim": "The retained claim reports 12% legacy adoption.",
        "source_identity": "Report|pdf-sha256:" + "a" * 64,
        "evidence_ids": ["old-evidence"],
        "evidence_spans": [{"source_pack": "doc_map", "page": 1}],
        "outcome": "verified",
        "final_claim": "The source reports 73% adoption among video users.",
        "recovered_physical_pages": [2],
        "inspected_physical_pages": [2],
        "supporting_physical_pages": [2],
        "source_truth_notes_by_page": {
            "2": "The verifier explains that page 2 supports the replacement."
        },
        "recovery_candidates": [
            {
                "physical_page": 2,
                "evidence_id": "replacement-finding",
                "source_pack": "findings",
                "score": 80,
            }
        ],
    }

    selection = _shadow_replacement_selection(
        report="Report",
        baseline_insights=[
            {
                "id": "candidate-1",
                "text": row["original_claim"],
                "evidence_id": "old-evidence",
                "evidence": "The old retained evidence reports 12%.",
                "metric": {"value": "12", "cohort": "legacy cohort"},
            }
        ],
        retained_rows=[row],
        editorial_plan={
            "themes": [
                {
                    "priority": 1,
                    "theme": "Theme A",
                    "evidence_ids": ["old-evidence"],
                }
            ]
        },
        source_page_text_by_page={
            2: "The source reports 73% adoption among video users."
        },
    )

    assert selection["selected_count"] == 1
    selected = selection["selected"][0]
    assert selected["final_claim"] == row["final_claim"]
    assert selected["editorial_quality_status"] == "pass"
    assert selected["source_binding_status"] == "provisional_recovered"
    assert selected["canonical_approval_status"] == "not_approved"


def test_shadow_selection_keeps_visually_verified_chart_fact_pending_text_quality(
) -> None:
    row = {
        "candidate_id": "candidate-chart",
        "original_claim": "The report discusses newsroom priorities.",
        "source_identity": "Report|pdf-sha256:" + "b" * 64,
        "evidence_ids": ["theme-chart"],
        "outcome": "verified",
        "final_claim": (
            "Among Q13 respondents (base 264), the net balance was +91 percentage "
            "points for original investigations, +82 for contextual analysis, "
            "+76 for community-building, +72 for human stories, and +63 for "
            "fact-checking and verification; opinion/commentary was also +55 points."
        ),
        "recovered_physical_pages": [17],
        "inspected_physical_pages": [17],
        "supporting_physical_pages": [17],
        "source_truth_notes_by_page": {
            "17": "The verifier confirms the chart value and survey base on page 17."
        },
        "recovery_candidates": [
            {
                "physical_page": 17,
                "evidence_id": "theme-chart",
                "source_pack": "findings",
                "score": 80,
            }
        ],
    }

    selection = _shadow_replacement_selection(
        report="Report",
        baseline_insights=[],
        retained_rows=[row],
        editorial_plan={
            "themes": [
                {"priority": 1, "theme": "Theme chart", "evidence_ids": ["theme-chart"]}
            ]
        },
        source_page_text_by_page={
            17: (
                "Publisher perceptions. Original investigations/on-the-ground "
                "reporting +91. Contextual analysis +82. Community building +76. "
                "Human stories +72. Fact-checking/verification +63. Base = 264."
            )
        },
    )

    assert selection["selected_count"] == 1
    selected = selection["selected"][0]
    assert selected["editorial_quality_status"] == "pending_visual_source_text"
    assert selected["editorial_quality_blockers"] == []
    assert "public_editorial_quality.unsupported_numeric_claim" in selected[
        "editorial_quality_issues"
    ]


def test_usage_summary_isolated_to_current_replay_run(tmp_path) -> None:
    ledger = tmp_path / "cost-ledger.jsonl"
    ledger.write_text(
        "\n".join(
            json.dumps(
                {
                    "run_id": run_id,
                    "input_tokens": tokens,
                    "output_tokens": 2,
                    "total_tokens": tokens + 2,
                    "estimated_cost_usd": 0.1,
                }
            )
            for run_id, tokens in (("old", 99), ("current", 7))
        ),
        encoding="utf-8",
    )

    summary = _usage_summary(ledger, run_id="current")

    assert summary["provider_calls"] == 1
    assert summary["input_tokens"] == 7
    assert summary["output_tokens"] == 2
    assert summary["ledger_rows_seen"] == 2
    assert summary["ledger_rows_selected"] == 1


def test_shadow_replacement_uses_independently_verified_support_page() -> None:
    row = {
        "candidate_id": "candidate-1",
        "original_claim": "Old direction",
        "source_identity": "report|pdf-sha256:" + "a" * 64,
        "evidence_ids": ["theme-a"],
        "evidence_spans": [],
        "outcome": "verified",
        "final_claim": (
            "A distinct 73% adoption result supports a focused commercial action."
        ),
        "recovered_physical_pages": [7, 8],
        "inspected_physical_pages": [5, 7, 8],
        "supporting_physical_pages": [8],
        "source_truth_notes_by_page": {
            "8": "Page 8 reports the 73% adoption result for the named cohort."
        },
        "recovery_candidates": [
            {
                "physical_page": 7,
                "evidence_id": "wrong-high-score",
                "source_pack": "findings",
                "score": 100,
            },
            {
                "physical_page": 8,
                "evidence_id": "verified-page",
                "source_pack": "findings",
                "score": 1,
            },
        ],
    }

    selection = _shadow_replacement_selection(
        report="Report",
        baseline_insights=[],
        retained_rows=[row],
        editorial_plan={
            "themes": [{"priority": 1, "theme": "Theme A", "evidence_ids": ["theme-a"]}]
        },
    )

    selected = selection["selected"][0]
    assert selected["supporting_physical_pages"] == [8]
    assert selected["source_truth_notes_by_page"] == row["source_truth_notes_by_page"]
    assert selected["provisional_recovery_evidence_ids"] == ["verified-page"]
    assert selected["canonical_approval_status"] == "not_approved"
    assert "evidence_id" not in selected


def test_shadow_replacement_rejects_support_outside_recovery_candidates() -> None:
    row = {
        "candidate_id": "candidate-1",
        "original_claim": "Old direction",
        "source_identity": "report|pdf-sha256:" + "a" * 64,
        "evidence_ids": ["theme-a"],
        "evidence_spans": [],
        "outcome": "verified",
        "final_claim": "A distinct result supports a focused commercial action.",
        "recovered_physical_pages": [7],
        "inspected_physical_pages": [5, 7],
        "supporting_physical_pages": [5],
        "source_truth_notes_by_page": {
            "5": "Page 5 reports the result for the named cohort and period."
        },
        "recovery_candidates": [{"physical_page": 7, "evidence_id": "finding-7"}],
    }

    selection = _shadow_replacement_selection(
        report="Report",
        baseline_insights=[],
        retained_rows=[row],
        editorial_plan={
            "themes": [{"priority": 1, "theme": "Theme A", "evidence_ids": ["theme-a"]}]
        },
    )

    assert selection["selected_count"] == 0
    assert selection["rejected_or_abstained"][0]["selection_reason"] == (
        "supporting_page_not_recovery_candidate"
    )


def test_shadow_replacement_checks_complete_verified_set_without_metadata() -> None:
    rows = [
        {
            "candidate_id": "candidate-1",
            "original_claim": "Old direction",
            "source_identity": "report|pdf-sha256:" + "a" * 64,
            "evidence_ids": ["theme-a"],
            "evidence_spans": [],
            "outcome": "verified",
            "final_claim": (
                "A distinct 73% adoption result supports a focused commercial action."
            ),
            "recovered_physical_pages": [7],
            "inspected_physical_pages": [5, 7],
            "supporting_physical_pages": [7],
            "source_truth_notes_by_page": {
                "7": "Page 7 reports the 73% adoption result for the named cohort."
            },
            "recovery_candidates": [
                {"physical_page": 7, "evidence_id": "theme-a", "score": 1}
            ],
        },
        {
            "candidate_id": "candidate-2",
            "original_claim": "Another direction",
            "source_identity": "report|pdf-sha256:" + "a" * 64,
            "evidence_ids": ["theme-b"],
            "evidence_spans": [],
            "outcome": "verified",
            "final_claim": (
                "A distinct 73% adoption result supports a focused commercial action."
            ),
            "supporting_physical_pages": [8],
            "inspected_physical_pages": [5, 8],
            "source_truth_notes_by_page": {
                "8": "Page 8 reports the 73% adoption result for the named cohort."
            },
            "recovery_candidates": [],
        },
    ]

    selection = _shadow_replacement_selection(
        report="Report",
        baseline_insights=[],
        retained_rows=rows,
        editorial_plan={
            "themes": [
                {"priority": 1, "theme": "Theme A", "evidence_ids": ["theme-a"]},
                {"priority": 2, "theme": "Theme B", "evidence_ids": ["theme-b"]},
            ]
        },
    )

    assert selection["selected_count"] == 0
    assert selection["rejected_or_abstained"][0]["selection_reason"] == (
        "duplicate_of:candidate-2"
    )


def test_reusable_shadow_boundary_discovers_provisional_pages_without_mutation(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "source.pdf"
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Business models")
    document.new_page().insert_text(
        (72, 72),
        "The source reports a 73% adoption result for video users. "
        "This finding supports a focused commercial action.",
    )
    document.save(pdf_path)
    document.close()
    pdf_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    claim = {
        "id": "candidate-1",
        "text": "Original direction",
        "evidence_id": "finding-1",
        "pages": [1],
        "_visual_replacement_policy": "report_level_replacement_allowed",
    }

    request, audit = build_verified_claims_shadow_request(
        source_identity=f"Report|pdf-sha256:{pdf_sha}",
        pdf_path=str(pdf_path),
        output_dir=str(tmp_path),
        report_name="report",
        evidence_packs={
            "doc_map": {
                "sections": [
                    {"id": "section-1", "title": "Business models", "pages": [1]}
                ]
            },
            "findings": {
                "findings": [
                    {
                        "id": "finding-1",
                        "section_id": "section-1",
                        "text": (
                            "The source reports a 73% adoption result for video users."
                        ),
                        "evidence": (
                            "The source reports a 73% adoption result for video users."
                        ),
                        "pages": [2],
                    }
                ]
            },
        },
        shortlisted_insights=[claim],
        ctx=RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
        recovery_enabled=True,
    )

    assert request.recovery_enabled is True
    assert request.recovery_candidates["candidate-1"][0]["physical_page"] == 2
    assert audit["canonical_mutation"] is False
    assert audit["publication_write"] is False
    assert claim["pages"] == [1]
