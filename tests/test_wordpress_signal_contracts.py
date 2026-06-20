from __future__ import annotations

from dataclasses import asdict

from src.contracts.report_cards import CoverFingerprint
from src.contracts.signal_cards import SignalCardContent
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPublishProjection,
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
        evidence_ids=["evidence-a", "evidence-b"],
        source_report_ids=["report-a", "report-b"],
        topic_ids=["checkout", "trust"],
        confidence=0.82,
        uncertainty="Publisher coverage is strongest in retail sources.",
        validation_status="approved",
        card_content=SignalCardContent(
            schema_version="1.0",
            summary="Trust signals diverged across checkout reports.",
            confidence=0.82,
            source_count=2,
            evidence_count=2,
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
        target_route="wordpress:ml_signal",
    )

    round_tripped = SignalPublishProjection.from_dict(asdict(projection))

    assert round_tripped == projection
    assert round_tripped.schema_version == "1.0"
    assert round_tripped.title
    assert round_tripped.slug
    assert round_tripped.evidence_ids == ["evidence-a", "evidence-b"]
    assert round_tripped.source_report_ids == ["report-a", "report-b"]
    assert round_tripped.topic_ids == ["checkout", "trust"]
    assert round_tripped.validation_status == "approved"
    assert round_tripped.target_route == "wordpress:ml_signal"
