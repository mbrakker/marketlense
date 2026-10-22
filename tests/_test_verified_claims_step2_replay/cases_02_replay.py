from __future__ import annotations

import hashlib
import json

import pymupdf as fitz
import pytest

from scripts.quality.replay_verified_claims_step2 import (
    _editorial_duplicate_pairs,
    _editorial_duplicate_status,
    _editorial_quality_report,
    _shadow_quality_assessment,
    _shadow_replacement_selection,
    _targeted_replay_accounting,
    _usage_summary,
    _valid_supporting_pages,
    _verified_corrected_insight,
    replay_live_explicit_cohort,
)
from src.contracts.run_context import RunContext
from src.generators.verified_claims_recovery import build_verified_claims_shadow_request


def test_targeted_explicit_replay_does_not_dispatch_unknown_id(tmp_path):
    pdf_path = tmp_path / "source.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "A source-backed retained finding.")
    document.save(pdf_path)
    document.close()

    artifact_path = (
        tmp_path / "run" / "output" / "artifact" / "report_analysis" / "artifacts.json"
    )
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        json.dumps(
            {
                "insights_final": [
                    {
                        "id": "eligible-1",
                        "text": "A source-backed retained finding.",
                        "pages": [1],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    source_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    cohort_path = tmp_path / "cohort_result.json"
    cohort_path.write_text(
        json.dumps(
            {
                "reports": [
                    {
                        "publisher_id": "Targeted Report",
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
                    "Targeted Report": {
                        "path": str(pdf_path),
                        "sha256": source_hash,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = replay_live_explicit_cohort(
        cohort_result_path=cohort_path,
        source_manifest_path=manifest_path,
        output_root=tmp_path / "out",
        real_claim_ids={"unknown-1"},
    )

    assert result["provider_status"] == "not_dispatched"
    assert result["usage"]["provider_calls"] == 0
    assert result["claims"] == []
    assert result["real_shortlisted_set"]["selected_claim_count"] == 1
    assert result["targeted_replay"]["unknown_ids"] == ["unknown-1"]
    assert result["targeted_replay"]["dispatched_ids"] == []


def test_targeted_replay_accounting_keeps_full_roster_separate_from_subset() -> None:
    accounting = _targeted_replay_accounting(
        requested_ids={
            "valid-1",
            "valid-2",
            "duplicate-id",
            "unavailable-1",
            "unknown-1",
        },
        reports=[
            {
                "report": "Activate",
                "selected_count": 2,
                "eligible_claims": [{"candidate_id": "valid-1"}],
                "unavailable": [
                    {
                        "candidate_id": "unavailable-1",
                        "reason": "retained_claim_missing_id_text_or_pages",
                    }
                ],
            },
            {
                "report": "Bain & Company",
                "selected_count": 2,
                "eligible_claims": [
                    {"candidate_id": "valid-2"},
                    {"candidate_id": "duplicate-id"},
                ],
                "unavailable": [],
            },
            {
                "report": "Reuters Institute",
                "selected_count": 1,
                "eligible_claims": [{"candidate_id": "duplicate-id"}],
                "unavailable": [],
            },
        ],
    )

    assert accounting["subset_only"] is True
    assert accounting["requested_ids"] == sorted(
        {
            "valid-1",
            "valid-2",
            "duplicate-id",
            "unavailable-1",
            "unknown-1",
        }
    )
    assert accounting["matched_ids"] == ["valid-1", "valid-2"]
    assert accounting["dispatched_ids"] == ["valid-1", "valid-2"]
    assert accounting["ambiguous_ids"] == ["duplicate-id"]
    assert accounting["unavailable_ids"] == ["unavailable-1"]
    assert accounting["unknown_ids"] == ["unknown-1"]
    assert accounting["full_cohort"]["selected_count"] == 5
    assert accounting["full_cohort"]["eligible_count"] == 4
    assert accounting["full_cohort"]["unavailable_count"] == 1


def test_targeted_replay_accounting_reports_no_dispatch_for_invalid_ids() -> None:
    accounting = _targeted_replay_accounting(
        requested_ids={"unknown-1", "unavailable-1"},
        reports=[
            {
                "report": "Activate",
                "selected_count": 1,
                "eligible_claims": [],
                "unavailable": [
                    {"candidate_id": "unavailable-1", "reason": "source_unavailable"}
                ],
            }
        ],
    )

    assert accounting["matched_ids"] == []
    assert accounting["dispatched_ids"] == []
    assert accounting["status"] == "no_matched_eligible_ids"
    assert accounting["provider_calls"] == 0
    assert accounting["unavailable"][0]["reason"] == "source_unavailable"
    assert accounting["unknown"][0]["reason"] == (
        "requested_candidate_id_not_in_retained_roster"
    )


def test_unfiltered_replay_has_no_targeted_subset_accounting() -> None:
    assert (
        _targeted_replay_accounting(
            requested_ids=None,
            reports=[],
        )
        is None
    )


@pytest.mark.parametrize(
    "supporting_pages",
    [[3, "invalid"], [3, True], [3, 0], [3, 3]],
)
def test_valid_supporting_pages_rejects_malformed_complete_lists(
    supporting_pages: list[object],
) -> None:
    pages, reason = _valid_supporting_pages(
        {
            "inspected_physical_pages": [3, 4],
            "supporting_physical_pages": supporting_pages,
            "source_truth_notes_by_page": {
                str(page): "The page contains the supporting source finding."
                for page in supporting_pages
                if type(page) is int and page > 0
            },
        }
    )

    assert pages == []
    assert reason == "supporting_page_provenance_invalid"


def test_valid_supporting_pages_rejects_uninspected_page_in_complete_list() -> None:
    pages, reason = _valid_supporting_pages(
        {
            "inspected_physical_pages": [3],
            "supporting_physical_pages": [3, 4],
            "source_truth_notes_by_page": {
                "3": "Page 3 contains the supporting source finding.",
                "4": "Page 4 contains the supporting source finding.",
            },
        }
    )

    assert pages == []
    assert reason == "supporting_page_provenance_uninspected"


def test_valid_supporting_pages_accepts_inspected_multi_page_binding() -> None:
    pages, reason = _valid_supporting_pages(
        {
            "inspected_physical_pages": [3, 4],
            "supporting_physical_pages": [3, 4],
            "source_truth_notes_by_page": {
                "3": "Page 3 contains the first part of the source finding.",
                "4": "Page 4 contains the second part of the source finding.",
            },
        }
    )

    assert pages == [3, 4]
    assert reason == ""


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

    assert (
        _editorial_duplicate_status(left, right, {("candidate-1", "candidate-2")})
        == "distinct"
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
    assert insight["evidence"] == ("The source reports 73% adoption among video users.")
    assert insight["evidence_id"] == "provisional-page:candidate-1"
    assert insight["pages"] == [2]
    assert "metric" not in insight
    assert "old retained evidence" not in insight["evidence"]


def test_verified_corrected_insight_uses_explicit_unchanged_claim_binding() -> None:
    row = {
        "candidate_id": "candidate-1",
        "final_claim": "The source reports 61% adoption among video users.",
        "supporting_physical_pages": [5],
        "corrected_source_binding_status": "retained",
        "corrected_evidence_ids": ["adoption-61"],
        "corrected_evidence_spans": [
            {"evidence_id": "adoption-61", "page": 5, "text": "61% adoption"}
        ],
        "corrected_metric_binding": {
            "value": "61%",
            "unit": "%",
            "cohort": "Video users",
        },
    }

    insight = _verified_corrected_insight(row, {})

    assert insight is not None
    assert insight["evidence_id"] == "adoption-61"
    assert insight["evidence_ids"] == ["adoption-61"]
    assert insight["evidence_spans"] == row["corrected_evidence_spans"]
    assert insight["metric"] == row["corrected_metric_binding"]
    assert insight["evidence_status"] == "visual_verified_bound"


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


def test_shadow_selection_keeps_visually_verified_chart_fact_pending_text_quality() -> (
    None
):
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
    assert (
        "public_editorial_quality.unsupported_numeric_claim"
        in selected["editorial_quality_issues"]
    )


def test_visual_verification_defers_source_text_metric_relationship_checks() -> None:
    insight = {
        "id": "candidate-relationship",
        "text": "Q1 2025: 50%.",
        "evidence_id": "provisional-page:candidate-relationship",
        "evidence": "Q1 2025: 40%; Q2 2025: 50%.",
        "evidence_status": "visual_verified_provisional",
    }

    errors, blockers, status = _shadow_quality_assessment(
        "Report", insight, visually_verified=True
    )

    assert "public_editorial_quality.metric_label_relationship" in errors
    assert blockers == []
    assert status == "pending_visual_source_text"


@pytest.mark.parametrize(
    "metric",
    [
        {"label": "Adoption", "value": "40%", "cohort": "legacy cohort"},
        {"label": "Adoption"},
    ],
)
def test_stale_retained_metric_does_not_block_visual_claim(metric) -> None:
    insight = {
        "id": "candidate-authoritative-metric",
        "text": "Q1 2025: 50%.",
        "evidence_id": "retained-evidence",
        "evidence": "Q1 2025: 40%; Q2 2025: 50%.",
        "metric": metric,
        "evidence_status": "visual_verified_provisional",
    }

    errors, blockers, status = _shadow_quality_assessment(
        "Report", insight, visually_verified=True
    )

    assert "public_editorial_quality.metric_label_relationship" in errors
    assert blockers == []
    assert status == "pending_visual_source_text"


def test_unverified_input_does_not_receive_visual_source_exemption() -> None:
    insight = {
        "id": "candidate-unverified",
        "text": "Q1 2025: 50%.",
        "evidence_id": "retained-evidence",
        "evidence": "Q1 2025: 40%; Q2 2025: 50%.",
        "metric": {"label": "Adoption"},
        "evidence_status": "retained",
    }

    errors, blockers, status = _shadow_quality_assessment(
        "Report", insight, visually_verified=False
    )

    assert "public_editorial_quality.metric_label_relationship" in errors
    assert "public_editorial_quality.metric_label_relationship" in blockers
    assert status == "abstained"


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


def test_shadow_replacement_accepts_inspected_original_support_during_recovery() -> (
    None
):
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

    assert selection["selected_count"] == 1
    assert selection["selected"][0]["supporting_physical_pages"] == [5]


def test_shadow_replacement_keeps_source_supported_retained_page() -> None:
    row = {
        "candidate_id": "candidate-1",
        "original_claim": "Old direction",
        "source_identity": "report|pdf-sha256:" + "a" * 64,
        "evidence_ids": ["theme-a"],
        "evidence_spans": [],
        "outcome": "verified",
        "final_claim": "The source reports a 61% adoption result for video users.",
        "original_physical_pages": [5],
        "recovered_physical_pages": [7],
        "inspected_physical_pages": [5, 7],
        "supporting_physical_pages": [5],
        "source_truth_notes_by_page": {
            "5": "The page reports the 61% adoption result for video users."
        },
        "recovery_candidates": [{"physical_page": 7, "evidence_id": "finding-7"}],
    }

    selection = _shadow_replacement_selection(
        report="Report",
        baseline_insights=[
            {"id": "candidate-1", "text": "Old direction", "evidence_id": "theme-a"}
        ],
        retained_rows=[row],
        editorial_plan={
            "themes": [{"priority": 1, "theme": "Theme A", "evidence_ids": ["theme-a"]}]
        },
        source_page_text_by_page={
            5: "The source reports a 61% adoption result for video users.",
            7: "Methodology and definitions.",
        },
    )

    assert selection["selected_count"] == 1
    assert selection["selected"][0]["supporting_physical_pages"] == [5]


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
