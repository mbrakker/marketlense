from __future__ import annotations

from scripts.quality.replay_verified_claims_step2 import (
    REFERENCE_PATH,
    _load_json,
    _reference_claims,
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
