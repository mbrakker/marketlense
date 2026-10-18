from __future__ import annotations

from scripts.quality.replay_verified_claims_step2 import (
    REFERENCE_PATH,
    _load_json,
    _outcome_counts,
    _reference_claims,
    _retained_claims,
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
        total += len(claims)
    assert total == 29


def test_retained_replay_keeps_doc_map_pages_as_provisional_source_context() -> None:
    reference = _load_json(REFERENCE_PATH)

    claims, metadata, unavailable = _retained_claims(
        reference, "Reuters Institute"
    )

    assert unavailable == []
    newsroom_claim = next(
        claim
        for claim in claims
        if claim["candidate_id"] == "newsroom-ai-uses-and-oversight"
    )
    assert newsroom_claim["evidence_id"] == "latest-tales-ai-newsroom"
    assert newsroom_claim["pages"] == [30]
    assert metadata["newsroom-ai-uses-and-oversight"][
        "source_binding_resolution"
    ] == "provisional_page_inspection"
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
    assert activate_metadata["activate-digital-assistant-access-forecast"][
        "source_binding_resolution"
    ] == "provisional_page_inspection"


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
