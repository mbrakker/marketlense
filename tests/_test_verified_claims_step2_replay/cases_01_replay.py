from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf as fitz
import pytest

from scripts.quality import replay_verified_claims_step2 as replay_step2
from scripts.quality.replay_verified_claims_step2 import (
    REFERENCE_PATH,
    _assert_outcome_count_arithmetic,
    _editorial_duplicate_status,
    _load_explicit_cohort_inputs,
    _load_json,
    _outcome_counts,
    _page_is_likely_divider,
    _recovery_candidates_for_claim,
    _reference_claims,
    _retained_claims,
    _shadow_replacement_selection,
    replay_frozen_step2,
)


def _portable_retained_reference(
    tmp_path: Path,
    report: str,
    insights: list[dict[str, object]],
) -> dict[str, object]:
    """Build the smallest retained artifact needed by replay assembly tests."""

    output_root = tmp_path / "retained-output"
    analysis_directory = output_root / "analysis" / "report_analysis"
    analysis_directory.mkdir(parents=True)
    (analysis_directory / "artifacts.json").write_text(
        json.dumps({"insights_final": insights}), encoding="utf-8"
    )
    return {
        "retained_run": {"isolated_output_root": "retained-output"},
        "report_artifact_digests": {
            report: {"analysis_directory": "analysis/report_analysis"}
        },
    }


def _portable_recovery_context(
    *,
    source_identity: str,
    pages: list[dict[str, object]],
    section: dict[str, object],
    findings: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "available": True,
        "source_identity": source_identity,
        "pages": pages,
        "doc_map": {"sections": [section]},
        "findings": {"findings": findings},
    }


def test_replay_uses_explicit_duplicate_status_without_boolean_alias() -> None:
    assert not hasattr(replay_step2, "_editorially_duplicate")


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


def test_retained_shortlist_replay_assembles_compact_five_report_fixture(
    tmp_path, monkeypatch
):
    expected_counts = {
        "Capgemini Research Institute": 5,
        "Activate": 7,
        "KPMG": 5,
        "Reuters Institute": 6,
        "Adjust": 6,
    }
    total = 0
    for report, expected_count in expected_counts.items():
        insights = [
            {
                "id": f"{report.lower().replace(' ', '-')}-{index}",
                "text": f"A retained finding for {report}, item {index}.",
                "pages": [index + 1],
            }
            for index in range(expected_count)
        ]
        reference = _portable_retained_reference(
            tmp_path / report.replace(" ", "-"), report, insights
        )
        monkeypatch.setattr(
            replay_step2, "REPOSITORY_ROOT", tmp_path / report.replace(" ", "-")
        )
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


def test_explicit_cohort_inventory_preserves_page_less_selected_insights(tmp_path):
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
                        "evidence_id": "finding-1",
                        "evidence_spans": [{"page": 1, "source_pack": "findings"}],
                        "pages": [1],
                    },
                    {
                        "id": "page-less-1",
                        "text": "A selected finding without a physical page.",
                        "evidence_id": "finding-2",
                        "evidence_spans": [{"source_pack": "findings"}],
                        "pages": [],
                    },
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
                "git_sha": "cohort-commit",
                "reports": [
                    {
                        "publisher_id": "Test Report",
                        "git_sha": "producer-commit",
                        "run_directory": str(tmp_path / "run"),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_pdfs": {
                    "Test Report": {
                        "path": str(pdf_path),
                        "sha256": source_hash,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    loaded = _load_explicit_cohort_inputs(cohort_path, manifest_path)

    report = loaded["reports"][0]
    assert report["producer_commit"] == "producer-commit"
    assert report["source"]["sha256_matches"] is True
    assert report["artifact"]["sha256"]
    assert [claim["candidate_id"] for claim in report["eligible_claims"]] == [
        "eligible-1"
    ]
    assert report["unavailable"] == [
        {
            "candidate_id": "page-less-1",
            "evidence_id": "finding-2",
            "evidence_spans": [{"source_pack": "findings"}],
            "pages": [],
            "position": 1,
            "reason": "retained_claim_missing_id_text_or_pages",
            "report": "Test Report",
        }
    ]


def test_explicit_cohort_inventory_allows_exact_provisional_binding(
    tmp_path,
):
    pdf_path = tmp_path / "one-page.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "An exact one-page source passage for inspection.")
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
                        "id": "page-less-exact-1",
                        "text": "The passage supports an operating implication.",
                        "evidence_id": "quote-1",
                        "evidence": "An exact one-page source passage for inspection.",
                        "evidence_spans": [
                            {
                                "evidence_id": "quote-1",
                                "text": (
                                    "An exact one-page source passage for inspection."
                                ),
                            }
                        ],
                        "pages": [],
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
                "git_sha": "cohort-commit",
                "reports": [
                    {
                        "publisher_id": "One Page Report",
                        "git_sha": "producer-commit",
                        "run_directory": str(tmp_path / "run"),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_pdfs": {
                    "One Page Report": {
                        "path": str(pdf_path),
                        "sha256": source_hash,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    loaded = _load_explicit_cohort_inputs(cohort_path, manifest_path)

    report = loaded["reports"][0]
    assert [claim["candidate_id"] for claim in report["eligible_claims"]] == [
        "page-less-exact-1"
    ]
    claim = report["eligible_claims"][0]
    assert claim["pages"] == []
    assert claim["_provisional_input_pages"] == [1]
    metadata = report["claim_metadata"]["page-less-exact-1"]
    assert metadata["original_physical_pages"] == []
    assert metadata["provisional_input_pages"] == [1]
    assert metadata["source_binding_resolution"] == "bounded_exact_evidence_page_match"


def test_explicit_cohort_inventory_resolves_unique_exact_evidence_page(tmp_path):
    pdf_path = tmp_path / "multi-page.pdf"
    document = fitz.open()
    document.new_page().insert_text((72, 72), "An unrelated page.")
    document.new_page().insert_text((72, 72), "A unique retained evidence passage.")
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
                        "id": "page-less-exact-2",
                        "text": "A source-backed finding.",
                        "evidence_id": "quote-2",
                        "evidence_spans": [
                            {
                                "evidence_id": "quote-2",
                                "text": "A unique retained evidence passage.",
                            }
                        ],
                        "pages": [],
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
                        "publisher_id": "Multi Page Report",
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
                    "Multi Page Report": {
                        "path": str(pdf_path),
                        "sha256": source_hash,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    report = _load_explicit_cohort_inputs(cohort_path, manifest_path)["reports"][0]

    assert [claim["candidate_id"] for claim in report["eligible_claims"]] == [
        "page-less-exact-2"
    ]
    assert report["eligible_claims"][0]["pages"] == []
    assert report["eligible_claims"][0]["_provisional_input_pages"] == [2]


def test_retained_replay_keeps_doc_map_pages_as_provisional_source_context(
    tmp_path, monkeypatch
) -> None:
    report = "Reuters Institute"
    reference = _portable_retained_reference(
        tmp_path,
        report,
        [
            {
                "id": "newsroom-ai-uses-and-oversight",
                "text": "Newsrooms are adding AI uses alongside human oversight.",
                "evidence_id": "latest-tales-ai-newsroom",
                "evidence_spans": [{"source_pack": "doc_map"}],
                "pages": [30],
            },
            {
                "id": "activate-digital-assistant-access-forecast",
                "text": "Digital assistant access is expected to expand.",
                "evidence_id": "s4",
                "evidence_spans": [{"source_pack": "doc_map"}],
                "pages": [15],
            },
        ],
    )
    monkeypatch.setattr(replay_step2, "REPOSITORY_ROOT", tmp_path)

    claims, metadata, unavailable = _retained_claims(reference, report)

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

    assistant_claim = next(
        claim
        for claim in claims
        if claim["candidate_id"] == "activate-digital-assistant-access-forecast"
    )
    assert assistant_claim["evidence_id"] == "s4"
    assert (
        metadata["activate-digital-assistant-access-forecast"][
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
    claim = {
        "candidate_id": "consumer-control-of-ai",
        "text": "Consumers want more control over how AI uses their data.",
        "evidence_id": "consumer-control-of-ai",
        "pages": [30],
    }
    candidates = _recovery_candidates_for_claim(
        {},
        "Capgemini Research Institute",
        claim,
        context=_portable_recovery_context(
            source_identity="Capgemini Research Institute|pdf-sha256:" + "a" * 64,
            pages=[
                {"page_number": 30, "text": "Consumer control of AI 30"},
                {
                    "page_number": 35,
                    "text": (
                        "Consumers want more control over how AI uses their data. "
                        "Survey respondents reported concerns about control and "
                        "data use."
                    ),
                },
                {
                    "page_number": 36,
                    "text": (
                        "Consumers want more control over how AI uses their data. "
                        "Survey respondents described the finding in detail, with "
                        "implications for trustworthy commercial design and useful "
                        "decision support across products, services, and "
                        "customer journeys."
                    ),
                },
            ],
            section={
                "id": "consumer-control-of-ai",
                "title": "Consumer control",
                "pages": [30],
            },
            findings=[
                {
                    "id": "consumer-control-of-ai",
                    "section_id": "consumer-control-of-ai",
                    "pages": [35, 36],
                    "text": "Consumers want more control over how AI uses their data.",
                }
            ],
        ),
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
    claim = {
        "candidate_id": "subscription-membership-priority",
        "text": "Publishers continue to prioritize subscription and membership models.",
        "evidence_id": "business-models",
        "pages": [3],
    }
    candidates = _recovery_candidates_for_claim(
        {},
        "Reuters Institute",
        claim,
        context=_portable_recovery_context(
            source_identity="Reuters Institute|pdf-sha256:" + "b" * 64,
            pages=[
                {
                    "page_number": 3,
                    "text": (
                        "Contents About the Author 2 Acknowledgements 2 Executive "
                        "Summary 3 "
                        "1. Pressures on Journalism Mount 7 2. Business models 38 "
                        "3. Content strategies 42"
                    ),
                },
                {
                    "page_number": 38,
                    "text": (
                        "Publishers continue to prioritize subscription and membership "
                        "models. "
                        "Business models remain central to sustainable journalism. "
                        "Survey evidence describes how publishers evaluate recurring "
                        "revenue, audience relationships, retention, and the "
                        "commercial "
                        "tradeoffs "
                        "between subscription and membership strategies."
                    ),
                },
            ],
            section={
                "id": "business-models",
                "title": "Business models",
                "pages": [3],
            },
            findings=[
                {
                    "id": "business-models",
                    "section_id": "business-models",
                    "pages": [38],
                    "text": (
                        "Publishers continue to prioritize subscription and membership "
                        "models."
                    ),
                }
            ],
        ),
    )

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

    assert _editorial_duplicate_status(left, right, set()) == "duplicate"


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


def test_bigcommerce_real_pdf_retains_supported_wallet_page_during_recovery() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    source_pdf = repository_root / (
        "out/browser_downloads/www.bigcommerce.com/e72f39fe19e5/"
        "ebook_0225_future_commerce_new_modes_guide_en_us.pdf"
    )
    retained_artifact = repository_root / (
        "tmp/verified-claims-premerge-20261019/"
        "frozen-reliability-rwum7m8u/members/"
        "cohort-0a019f840c3f89ad0a96/ias-first-attempt-l36ozkkv/"
        "output/e-997cc1cccd6a/report_analysis/artifacts.json"
    )
    if not source_pdf.is_file() or not retained_artifact.is_file():
        pytest.skip("retained BigCommerce PDF/artifact is unavailable")

    with fitz.open(source_pdf) as document:
        page_four_text = document[3].get_text()
    artifact = _load_json(retained_artifact)
    claim = next(
        item
        for item in artifact["insights_final"]
        if item.get("id") == "mobile-wallet-cart-abandonment"
    )
    row = {
        "candidate_id": claim["id"],
        "original_claim": claim["text"],
        "final_claim": claim["text"],
        "source_identity": "BigCommerce|pdf-sha256:" + "a" * 64,
        "evidence_ids": [claim["evidence_id"]],
        "evidence_spans": claim["evidence_spans"],
        "outcome": "verified",
        "original_physical_pages": [4],
        "inspected_physical_pages": [4, 2],
        "recovered_physical_pages": [2],
        "supporting_physical_pages": [4],
        "source_truth_notes_by_page": {
            "4": (
                "Page 4 reports 40% cart abandonment when the preferred wallet "
                "method is unavailable."
            )
        },
        "recovery_candidates": [
            {
                "physical_page": 2,
                "evidence_id": "provisional-methodology",
                "source_pack": "findings",
                "score": 90,
            }
        ],
    }

    selection = _shadow_replacement_selection(
        report="BigCommerce",
        baseline_insights=[claim],
        retained_rows=[row],
        editorial_plan={
            "themes": [
                {
                    "priority": 1,
                    "theme": "Digital payments and wallets",
                    "evidence_ids": ["f11"],
                }
            ]
        },
        source_page_text_by_page={4: page_four_text},
    )

    assert selection["selected_count"] == 1
    assert selection["selected"][0]["candidate_id"] == "mobile-wallet-cart-abandonment"
    assert selection["selected"][0]["supporting_physical_pages"] == [4]


def test_unbound_near_duplicate_propositions_remain_ambiguous() -> None:
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

    assert (
        _editorial_duplicate_status(left, right, {("candidate-1", "candidate-2")})
        == "ambiguous"
    )
