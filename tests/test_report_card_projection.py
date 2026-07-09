from __future__ import annotations

import pytest

from src.contracts.report_cards import (
    CardCoverAsset,
    CardCoverAssetSet,
    CoverFingerprintProjectionRequest,
    ReportCardManifestRequest,
)
from src.generators.report_card_projection import (
    build_cover_fingerprint,
    build_report_card_manifest,
    classify_geography,
    validate_public_metadata_governance,
    select_title_scale,
    stable_cover_seed,
)
from src.utils.errors import AppError


def _semantics(**overrides: str) -> dict[str, object]:
    values: dict[str, object] = {
        "evidence_shape": "trend",
        "direction": "rising",
        "geography_scope": "global",
        "evidence_density": "metric_rich",
        "domain_layer": "grid",
        "selection_reason": "Rising time-series evidence dominates the report.",
    }
    values.update(overrides)
    return values


def _covers() -> CardCoverAssetSet:
    return CardCoverAssetSet(
        schema_version="1.0",
        small=CardCoverAsset("1.0", "small", "small.png", 1600, 900),
        medium=CardCoverAsset("1.0", "medium", "medium.png", 1200, 1500),
        large=CardCoverAsset("1.0", "large", "large.png", 1200, 1600),
    )


def _fingerprint(region: str = "Global"):
    return build_cover_fingerprint(
        CoverFingerprintProjectionRequest(
            schema_version="1.0",
            file_id="drive-123",
            artifact_hash="artifact-abc",
            region=region,
            cover_semantics=_semantics(),
        )
    )


def _title_with_length(count: int) -> str:
    parts: list[str] = []
    remaining = count
    while remaining > 0:
        separator = 1 if parts else 0
        token_length = min(10, remaining - separator)
        parts.append("A" * token_length)
        remaining -= token_length + separator
    return " ".join(parts)


def _manifest_request(**overrides):
    values = {
        "schema_version": "1.0",
        "title": "Global Economic Conditions Quarterly Update",
        "publisher": "McKinsey & Company",
        "published_date": "2026-06-13",
        "region": "Global",
        "covered_period": "Q2 2026",
        "tldr_compact": "Rates and trade pressure reshape investment decisions.",
        "tldr_standard": (
            "Persistent rates and trade pressure are reshaping investment decisions "
            "across global markets through the second quarter of 2026."
        ),
        "insights_final": (
            {
                "text": (
                    "Investment remains concentrated in resilient service sectors "
                    "despite tighter financing conditions."
                )
            },
            {
                "text": (
                    "Trade pressure is widening the gap between regional outlooks "
                    "and capital plans."
                )
            },
            {"text": "This third insight must not enter the card manifest."},
        ),
        "fingerprint": _fingerprint(),
        "covers": _covers(),
    }
    values.update(overrides)
    return ReportCardManifestRequest(**values)


def test_stable_cover_seed_uses_file_id_and_artifact_hash() -> None:
    assert stable_cover_seed(" drive-123 ", " artifact-abc ") == 1344902748
    assert stable_cover_seed("drive-123", "artifact-abc") == 1344902748
    assert stable_cover_seed("drive-124", "artifact-abc") != 1344902748


@pytest.mark.parametrize(
    ("region", "expected_label", "expected_scope"),
    (
        ("Global", "Global", "global"),
        ("France, Germany", "France, Germany", "global"),
        ("Asia Pacific", "Asia Pacific", "regional"),
        ("France", "France", "country"),
        ("  ", "", "unknown"),
    ),
)
def test_classify_geography_distinguishes_card_pictogram_scope(
    region: str,
    expected_label: str,
    expected_scope: str,
) -> None:
    assert classify_geography(region) == (expected_label, expected_scope)


def test_build_cover_fingerprint_is_stable_and_selects_geometry() -> None:
    fingerprint = build_cover_fingerprint(
        CoverFingerprintProjectionRequest(
            schema_version="1.0",
            file_id="drive-123",
            artifact_hash="artifact-abc",
            region="Europe",
            cover_semantics=_semantics(
                evidence_shape="comparison",
                direction="diverging",
                evidence_density="balanced",
            ),
        )
    )

    assert fingerprint.seed == 1344902748
    assert fingerprint.geometry_family == "divergence_fan"
    assert fingerprint.geography_scope == "regional"
    assert fingerprint.selection_reason == (
        "Rising time-series evidence dominates the report."
    )


@pytest.mark.parametrize(
    ("character_count", "expected"),
    (
        (42, "short"),
        (43, "medium"),
        (65, "long"),
        (89, "xlong"),
    ),
)
def test_select_title_scale_uses_fixed_character_bands(
    character_count: int, expected: str
) -> None:
    title = _title_with_length(character_count)
    assert len(title) == character_count
    assert select_title_scale(title) == expected


def test_select_title_scale_accepts_breakable_hyphenated_title() -> None:
    title = "Activate-Technology-and-Media-Outlook-2019"

    assert len(title) == 42
    assert select_title_scale(title) == "short"


@pytest.mark.parametrize(
    "title",
    (
        "A complete report title " + ("x " * 60),
        "A title with SupercalifragilisticexpialidociousToken overflow",
    ),
)
def test_select_title_scale_rejects_overflow(title: str, assert_app_error) -> None:
    with pytest.raises(AppError) as captured:
        select_title_scale(title)

    assert_app_error(captured.value, code="card_title_overflow", retryable=False)


def test_build_manifest_preserves_full_text_and_first_two_insights() -> None:
    request = _manifest_request()

    manifest = build_report_card_manifest(request)

    assert manifest.title == request.title
    assert manifest.tldr_compact == request.tldr_compact
    assert manifest.tldr_standard == request.tldr_standard
    assert manifest.key_insights == (
        request.insights_final[0]["text"],
        request.insights_final[1]["text"],
    )
    assert manifest.geography_scope == "global"
    assert manifest.covers == request.covers


@pytest.mark.parametrize(
    ("field_name", "value", "error_code"),
    (
        ("tldr_compact", "", "card_tldr_compact_invalid"),
        ("tldr_standard", "", "card_tldr_standard_invalid"),
        (
            "insights_final",
            ({"text": "Only one complete insight."},),
            "card_key_insights_invalid",
        ),
    ),
)
def test_build_manifest_rejects_incomplete_card_content(
    field_name: str,
    value,
    error_code: str,
    assert_app_error,
) -> None:
    with pytest.raises(AppError) as captured:
        build_report_card_manifest(_manifest_request(**{field_name: value}))

    assert_app_error(captured.value, code=error_code, retryable=False)


def test_public_metadata_governance_rejects_placeholder_and_leaked_labels(
    assert_app_error,
) -> None:
    with pytest.raises(AppError) as captured:
        validate_public_metadata_governance(
            {
                "publisher": "Not extracted",
                "region": "Region: Europe",
                "covered_period": "This report discusses a long period sentence.",
                "category": "Category: Payments",
            }
        )

    assert_app_error(
        captured.value,
        code="public_metadata_governance_blocked",
        retryable=False,
    )
    assert set(captured.value.context["blocked_fields"]) == {
        "publisher",
        "region",
        "covered_period",
        "category",
    }


def test_public_metadata_governance_rejects_raw_extraction_fragments(
    assert_app_error,
) -> None:
    with pytest.raises(AppError) as captured:
        validate_public_metadata_governance(
            {
                "publisher": "OCR text block 17",
                "region": "Table 4 row: Europe",
                "covered_period": "raw_page_text: 2025 outlook",
                "archive_facet": "cell_2_3",
            }
        )

    assert_app_error(
        captured.value,
        code="public_metadata_governance_blocked",
        retryable=False,
    )
    assert set(captured.value.context["blocked_fields"]) == {
        "archive_facet",
        "covered_period",
        "publisher",
        "region",
    }


def test_report_card_manifest_applies_public_metadata_governance(
    assert_app_error,
) -> None:
    with pytest.raises(AppError) as captured:
        build_report_card_manifest(_manifest_request(publisher="YouGov Year: 2024"))

    assert_app_error(
        captured.value,
        code="public_metadata_governance_blocked",
        retryable=False,
    )
