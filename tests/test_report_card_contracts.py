from __future__ import annotations

from dataclasses import asdict

import pytest

from src.contracts.report_cards import (
    CardCoverAsset,
    CardCoverAssetSet,
    CoverFingerprint,
    CoverFingerprintProjectionRequest,
    ReportCardManifest,
    ReportCardManifestRequest,
    ReportCardManifestWriteRequest,
    ReportCardManifestWriteResponse,
)
from src.contracts.cover_images import CoverImageReport


def _fingerprint() -> CoverFingerprint:
    return CoverFingerprint(
        schema_version="1.0",
        geometry_family="ascending_trajectory",
        evidence_shape="trend",
        direction="rising",
        geography_scope="global",
        evidence_density="metric_rich",
        domain_layer="grid",
        seed=184221,
        selection_reason=(
            "Trend evidence with a rising direction dominates the report."
        ),
    )


def _covers() -> CardCoverAssetSet:
    return CardCoverAssetSet(
        schema_version="1.0",
        small=CardCoverAsset("1.0", "small", "assets/report-card-small.png", 1600, 900),
        medium=CardCoverAsset(
            "1.0", "medium", "assets/report-card-medium.png", 1200, 1500
        ),
        large=CardCoverAsset(
            "1.0", "large", "assets/report-card-large.png", 1200, 1600
        ),
    )


def _manifest() -> ReportCardManifest:
    return ReportCardManifest(
        schema_version="1.0",
        title="Global Economic Conditions Quarterly Update",
        title_scale="long",
        publisher="McKinsey & Company",
        published_date="2026-06-13",
        geography_label="Global",
        geography_scope="global",
        covered_period="Q2 2026",
        tldr_compact=(
            "Growth remains uneven as rates and trade pressure reshape investment decisions."
        ),
        tldr_standard=(
            "Growth remains uneven across markets as persistent rates, trade pressure, "
            "and weaker demand reshape investment decisions through the second quarter "
            "of 2026."
        ),
        key_insights=(
            "Investment remains concentrated in resilient service sectors.",
            "Trade pressure is widening the gap between regional outlooks.",
        ),
        fingerprint=_fingerprint(),
        covers=_covers(),
    )


def test_report_card_manifest_round_trip(
    assert_no_defaulted_required_fields,
) -> None:
    manifest = _manifest()

    rebuilt = ReportCardManifest.from_dict(asdict(manifest))

    assert rebuilt == manifest
    assert_no_defaulted_required_fields(rebuilt)


def test_report_card_support_contracts_are_complete(
    assert_no_defaulted_required_fields,
) -> None:
    projection = CoverFingerprintProjectionRequest(
        schema_version="1.0",
        file_id="drive-123",
        artifact_hash="abc123",
        region="Global",
        cover_semantics={
            "evidence_shape": "trend",
            "direction": "rising",
            "evidence_density": "metric_rich",
            "domain_layer": "grid",
            "selection_reason": "A rising trend dominates the evidence.",
        },
    )
    manifest_request = ReportCardManifestRequest(
        schema_version="1.0",
        title="Global Economic Conditions Quarterly Update",
        publisher="McKinsey & Company",
        published_date="2026-06-13",
        region="Global",
        covered_period="Q2 2026",
        tldr_compact="Growth remains uneven as rates reshape investment decisions.",
        tldr_standard=(
            "Growth remains uneven across markets as persistent rates reshape "
            "investment decisions through the second quarter of 2026."
        ),
        insights_final=(
            {"text": "Investment remains concentrated in resilient service sectors."},
            {"text": "Trade pressure is widening regional outlook gaps."},
        ),
        fingerprint=_fingerprint(),
        covers=_covers(),
    )
    write_request = ReportCardManifestWriteRequest(
        schema_version="1.0",
        output_dir="out/report-slug",
        manifest=_manifest(),
    )
    write_response = ReportCardManifestWriteResponse(
        schema_version="1.0",
        manifest_path="out/report-slug/report-card-manifest.json",
        bytes_written=2048,
    )

    for contract in (projection, manifest_request, write_request, write_response):
        assert_no_defaulted_required_fields(contract)


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    (
        (
            lambda payload: payload["covers"].__setitem__("large", None),
            "cover_asset_set_incomplete",
        ),
        (
            lambda payload: payload.__setitem__(
                "tldr_compact",
                "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen.",
            ),
            "card_tldr_compact_invalid",
        ),
        (
            lambda payload: payload.__setitem__("tldr_standard", "Incomplete"),
            "card_tldr_standard_invalid",
        ),
        (
            lambda payload: payload.__setitem__("key_insights", ["Only one."]),
            "card_key_insights_invalid",
        ),
        (
            lambda payload: payload.__setitem__("title_scale", "oversized"),
            "card_title_overflow",
        ),
        (
            lambda payload: payload["fingerprint"].__setitem__(
                "geometry_family", "generic_waves"
            ),
            "cover_fingerprint_invalid",
        ),
    ),
)
def test_report_card_manifest_rejects_invalid_payloads(
    mutate,
    error_code: str,
    assert_app_error,
) -> None:
    payload = asdict(_manifest())
    mutate(payload)

    with pytest.raises(Exception) as captured:
        ReportCardManifest.from_dict(payload)

    assert_app_error(captured.value, code=error_code, retryable=False)


def test_cover_asset_set_rejects_wrong_dimensions(assert_app_error) -> None:
    payload = asdict(_covers())
    payload["medium"]["width"] = 1600

    with pytest.raises(Exception) as captured:
        CardCoverAssetSet.from_dict(payload)

    assert_app_error(
        captured.value,
        code="cover_asset_set_incomplete",
        retryable=False,
    )


def test_cover_image_report_rejects_legacy_schema(assert_app_error) -> None:
    with pytest.raises(Exception) as captured:
        CoverImageReport.from_dict(
            {
                "schema_version": "1.0",
                "file_id": "drive-123",
                "title": "Global Economic Conditions Quarterly Update",
                "publisher": "McKinsey & Company",
            }
        )

    assert_app_error(
        captured.value,
        code="cover_contract_migration_required",
        retryable=False,
    )
