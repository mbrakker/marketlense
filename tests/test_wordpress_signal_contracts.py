from __future__ import annotations

from dataclasses import asdict

import pytest

from src.contracts.report_cards import CoverFingerprint
from src.contracts.signal_cards import SignalCardContent
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPublishProjection,
    SignalSourceAttribution,
)


def test_signal_publish_projection_round_trips_without_default_required_fields() -> (
    None
):
    projection = SignalPublishProjection(
        schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
        title="Checkout trust is fragmenting",
        slug="checkout-trust-is-fragmenting",
        summary_html="<p>Trust signals diverged across checkout reports.</p>",
        body_html="<article><p>Evidence-backed signal body.</p></article>",
        evidence_ids=["evidence-a", "evidence-b", "evidence-c"],
        source_report_ids=["report-a", "report-b", "report-c"],
        topic_ids=["checkout", "trust"],
        confidence=0.82,
        uncertainty="Publisher coverage is strongest in retail sources.",
        validation_status="approved",
        card_content=SignalCardContent(
            schema_version="1.0",
            summary="Trust signals diverged across checkout reports.",
            confidence=0.82,
            source_count=3,
            evidence_count=3,
            uncertainty="Publisher coverage is strongest in retail sources.",
            fingerprint=CoverFingerprint(
                schema_version="1.0",
                geometry_family="signal_lattice",
                evidence_shape="system",
                direction="neutral",
                geography_scope="unknown",
                evidence_density="balanced",
                domain_layer="grid",
                seed=41,
                selection_reason="Signal card contract test.",
            ),
        ),
        source_attributions=[
            SignalSourceAttribution(report_id="report-a", publisher="Publisher A"),
            SignalSourceAttribution(report_id="report-b", publisher="Publisher B"),
            SignalSourceAttribution(report_id="report-c"),
        ],
        publisher_labels=["Publisher A", "Publisher B"],
        target_route="wordpress:ml_signal",
    )

    round_tripped = SignalPublishProjection.from_dict(asdict(projection))

    assert round_tripped == projection
    assert round_tripped.schema_version == "1.0"
    assert round_tripped.title
    assert round_tripped.slug
    assert round_tripped.evidence_ids == ["evidence-a", "evidence-b", "evidence-c"]
    assert round_tripped.source_report_ids == ["report-a", "report-b", "report-c"]
    assert round_tripped.source_attributions == projection.source_attributions
    assert round_tripped.topic_ids == ["checkout", "trust"]
    assert round_tripped.validation_status == "approved"
    assert round_tripped.target_route == "wordpress:ml_signal"


@pytest.mark.parametrize(
    "source_attributions",
    [
        ["malformed entry"],
        [{"report_id": "missing-report", "publisher": "Publisher X"}],
        [
            {"report_id": "report-a", "publisher": "Publisher A"},
            {"report_id": "report-a", "publisher": "Publisher B"},
        ],
    ],
)
def test_signal_publish_projection_rejects_invalid_source_attribution(
    source_attributions: list[object],
) -> None:
    projection = SignalPublishProjection(
        schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
        title="Signal",
        slug="signal",
        summary_html="<p>Summary</p>",
        body_html="<p>Evidence</p>",
        evidence_ids=["evidence-a"],
        source_report_ids=["report-a"],
        topic_ids=["checkout"],
        confidence=0.8,
        uncertainty="Limited coverage.",
        validation_status="approved",
        card_content=SignalCardContent(
            schema_version="1.0",
            summary="Summary",
            confidence=0.8,
            source_count=1,
            evidence_count=1,
            uncertainty="Limited coverage.",
            fingerprint=CoverFingerprint(
                schema_version="1.0",
                geometry_family="signal_lattice",
                evidence_shape="system",
                direction="neutral",
                geography_scope="unknown",
                evidence_density="balanced",
                domain_layer="grid",
                seed=41,
                selection_reason="Signal card contract test.",
            ),
        ),
    )
    payload = asdict(projection)
    payload["source_attributions"] = source_attributions
    with pytest.raises(ValueError):
        SignalPublishProjection.from_dict(payload)


def test_signal_source_attribution_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValueError, match="Unsupported Signal source attribution"):
        SignalSourceAttribution.from_dict(
            {"schema_version": "0.9", "report_id": "report-a", "publisher": "A"}
        )
