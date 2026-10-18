from __future__ import annotations

import json

from scripts.quality.replay_verified_claims_step2 import (
    REFERENCE_PATH,
    _load_json,
    _outcome_counts,
    _page_is_likely_divider,
    _recovery_candidates_for_claim,
    _reference_claims,
    _retained_claims,
    _shadow_replacement_selection,
    _usage_summary,
    replay_frozen_step2,
)


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
    counts = _outcome_counts(
        [
            {"outcome": "verified"},
            {"outcome": "verified_after_retry"},
            {"outcome": "unresolved"},
            {"outcome": "failed_verification"},
            {"outcome": "skipped"},
        ]
    )

    assert counts == {
        "verified_total": 2,
        "verified_first_pass": 1,
        "verified_after_retry": 1,
        "failed_verification": 1,
        "unresolved": 1,
        "skipped": 1,
    }


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

    candidates = _recovery_candidates_for_claim(
        reference, "Reuters Institute", claim
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
            "recovery_reason": "retained_page_is_section_divider",
            "recovery_candidates": [
                {
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
            "recovery_reason": "retained_page_is_section_divider",
            "recovery_candidates": [
                {
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
