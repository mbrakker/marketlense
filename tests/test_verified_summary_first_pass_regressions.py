from __future__ import annotations

from src.contracts.report_cards import (
    CardCoverAsset,
    CardCoverAssetSet,
    CoverFingerprintProjectionRequest,
    ReportCardManifestRequest,
)
from src.generators.report_card_projection import (
    build_cover_fingerprint,
    build_report_card_manifest,
)
from tests.test_soft_copy_claim_provenance import _assemble_soft_copy


def test_summary_recovers_exact_direct_binding_before_abstention() -> None:
    sentence = "Repeat buyers reached 42% adoption in 2026."
    payload = _assemble_soft_copy(
        summary={
            "tldr": sentence,
            "card_tldr_compact": sentence,
            "executive_summary": sentence,
            "claim_evidence_map": [{"claim": sentence, "evidence_id": "finding-1"}],
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "finding-1",
                        "text": sentence,
                        "evidence": sentence,
                        "pages": [4],
                    }
                ]
            }
        },
    )

    assert payload["summary"]["tldr"] == sentence
    assert payload["summary"]["card_tldr_compact"] == sentence
    assert payload["family_status"]["summary"]["status"] == "generated"
    summary_claims = [
        claim
        for claim in payload["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "summary"
    ]
    assert len(summary_claims) == 1
    assert summary_claims[0]["evidence_ids"] == ["finding-1"]


def test_recovered_summary_reaches_report_card_manifest() -> None:
    sentence = "Repeat buyers reached 42% adoption in 2026."
    second_insight = "Mobile discovery remained the stronger acquisition path."
    payload = _assemble_soft_copy(
        summary={
            "tldr": sentence,
            "card_tldr_compact": sentence,
            "executive_summary": sentence,
            "claim_evidence_map": [{"claim": sentence, "evidence_id": "finding-1"}],
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "finding-1",
                        "text": sentence,
                        "evidence": sentence,
                        "pages": [4],
                    }
                ]
            }
        },
        insights_final=[
            {"id": "insight-1", "text": sentence, "evidence_id": "finding-1"},
            {
                "id": "insight-2",
                "text": second_insight,
                "evidence_id": "finding-2",
            },
        ],
    )
    fingerprint = build_cover_fingerprint(
        CoverFingerprintProjectionRequest(
            schema_version="1.0",
            file_id="report-card-summary",
            artifact_hash="artifact-hash",
            region="Global",
            cover_semantics={
                "evidence_shape": "trend",
                "direction": "rising",
                "geography_scope": "global",
                "evidence_density": "metric_rich",
                "domain_layer": "grid",
                "selection_reason": "The retained fact supports the card.",
            },
        )
    )
    covers = CardCoverAssetSet(
        schema_version="1.0",
        small=CardCoverAsset("1.0", "small", "small.png", 1600, 900),
        medium=CardCoverAsset("1.0", "medium", "medium.png", 1200, 1500),
        large=CardCoverAsset("1.0", "large", "large.png", 1200, 1600),
    )
    manifest = build_report_card_manifest(
        ReportCardManifestRequest(
            schema_version="1.0",
            title="Verified summary report",
            publisher="MarketLense",
            published_date="2026-11-13",
            region="Global",
            covered_period="2026",
            tldr_compact=payload["summary"]["card_tldr_compact"],
            tldr_standard=payload["summary"]["tldr"],
            insights_final=tuple(payload["insights_final"]),
            fingerprint=fingerprint,
            covers=covers,
            summary_abstained=(
                payload["family_status"]["summary"]["status"] == "abstained"
            ),
        )
    )

    assert payload["family_status"]["summary"]["status"] == "generated"
    assert manifest.key_insights[0] == sentence
    assert manifest.tldr_compact == sentence


def test_summary_still_abstains_when_exact_binding_cannot_be_recovered() -> None:
    payload = _assemble_soft_copy(
        summary={
            "tldr": "Unsupported expansion will double revenue.",
            "card_tldr_compact": "Unsupported expansion wins.",
            "executive_summary": "Unsupported expansion will double revenue.",
            "claim_evidence_map": [
                {"claim": "A different supported statement.", "evidence_id": "f1"}
            ],
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "A different supported statement.",
                        "evidence": "A different supported statement.",
                        "pages": [2],
                    }
                ]
            }
        },
    )

    assert payload["summary"] == {
        "tldr": "",
        "card_tldr_compact": "",
        "executive_summary": "",
        "claim_evidence_map": [],
    }
    assert payload["family_status"]["summary"]["status"] == "abstained"
