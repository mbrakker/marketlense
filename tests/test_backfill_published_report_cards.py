from __future__ import annotations

from Wordpress.scripts.admin.backfill_published_report_cards import (
    PublishedReportTarget,
    _card_needs_legacy_refresh,
    legacy_cover_semantics,
    legacy_card_content,
    limit_targets,
    skip_targets_from_env,
    targets_from_posts,
)


def test_targets_from_posts_keeps_every_published_post_for_a_shared_source() -> None:
    targets = targets_from_posts(
        "post",
        [
            {"id": 844, "meta": {"ml_file_id": "shared-drive-file"}},
            {"id": 845, "meta": {"ml_file_id": ""}},
        ],
    ) + targets_from_posts(
        "ml_report",
        [{"id": 887, "meta": {"ml_file_id": "shared-drive-file"}}],
    )

    assert [(target.post_type, target.post_id, target.file_id) for target in targets] == [
        ("post", 844, "shared-drive-file"),
        ("ml_report", 887, "shared-drive-file"),
    ]


def test_legacy_card_content_uses_published_report_copy_and_taxonomy() -> None:
    card = legacy_card_content(
        {
            "title": {"raw": "Retail outlook 2026"},
            "date": "2026-06-01T10:00:00",
            "meta": {"ml_time_period": "2026", "ml_region": "United Kingdom"},
            "ml_publisher": [15],
            "categories": [8],
            "content": {
                "raw": """
                <article><p class='hero-thesis'>Retail demand is becoming more selective as household budgets tighten.</p>
                <ul class='key-insights'>
                    <li>Retailers are concentrating investment on value, convenience, and measurable loyalty programmes.</li>
                    <li>Consumers compare prices across more channels before committing to discretionary purchases.</li>
                </ul></article>
                """
            },
        },
        publisher_names={15: "Example Research"},
        category_names={8: "Consumer Behaviour"},
    )

    assert card.publisher == "Example Research"
    assert card.covered_period == "2026"
    assert card.region == "United Kingdom"
    assert card.key_insights[0].startswith("Retailers are concentrating")
    assert card.tldr_standard.endswith(".")


def test_legacy_card_content_normalizes_filename_like_titles_for_cover_layout() -> None:
    card = legacy_card_content(
        {
            "title": {"raw": "CM_AgencyFactSheet_updated_12.4.2024-1"},
            "date": "2026-06-01T10:00:00",
            "meta": {"ml_time_period": "2024", "ml_region": "Global"},
            "ml_publisher": [15],
            "categories": [8],
            "content": {
                "raw": """
                <article><p class='hero-thesis'>Agency fact sheets summarize market conditions for client planning.</p>
                <ul class='key-insights'>
                    <li>Agency leaders are aligning service models with measurable commercial outcomes and client trust.</li>
                    <li>Marketing teams are prioritising evidence-backed planning inputs for campaign investment decisions.</li>
                </ul></article>
                """
            },
        },
        publisher_names={15: "Example Research"},
        category_names={8: "Advertising Strategy"},
    )

    assert card.title == "CM Agency Fact Sheet updated 12.4.2024-1"


def test_legacy_cover_semantics_reflects_published_report_content() -> None:
    forecast = legacy_cover_semantics(
        "The outlook forecasts rising consumer spending and strong growth through 2027."
    )
    survey = legacy_cover_semantics(
        "The survey compares responses across five consumer groups and regions."
    )

    assert forecast["evidence_shape"] == "trend"
    assert forecast["direction"] == "rising"
    assert forecast["domain_layer"] == "forecast"
    assert survey["evidence_shape"] == "comparison"


def test_legacy_cover_semantics_uses_title_and_categories_for_sparse_reports() -> None:
    semantics = legacy_cover_semantics(
        "This report summarizes implications for planning.",
        title="2026 Global M&A Outlook",
        categories=("Business Performance & Growth", "Financial Services"),
    )

    assert semantics["evidence_shape"] == "flow"
    assert semantics["direction"] == "rising"
    assert semantics["domain_layer"] == "forecast"


def test_legacy_cover_semantics_maps_digital_market_reports_to_distribution() -> None:
    semantics = legacy_cover_semantics(
        "Internet penetration reached 44.5% while social media penetration reached 30.4%. "
        "The report compares platform ad reach estimates across channels.",
        title="DIGITAL 2024: BANGLADESH",
        categories=("Advertising Strategy & Media", "Social, Short Video & Creator"),
    )

    assert semantics["evidence_shape"] == "distribution"


def test_legacy_cover_semantics_avoids_generic_system_for_titled_legacy_reports() -> None:
    semantics = legacy_cover_semantics(
        "This report summarizes implications for brand leaders.",
        title="2026 State of Brand: Branding at the Edge",
        categories=("Brand Strategy & Positioning",),
    )

    assert semantics["evidence_shape"] != "system"


def test_card_needs_legacy_refresh_when_cover_media_ids_are_missing() -> None:
    assert _card_needs_legacy_refresh(
        {
            "meta": {
                "ml_card_schema_version": "1.0",
                "ml_card_cover_fingerprint": {"geometry_family": "forecast_horizon"},
                "ml_card_cover_small_id": "12",
                "ml_card_cover_medium_id": "0",
                "ml_card_cover_large_id": "14",
            }
        }
    )


def test_limit_targets_keeps_first_allowed_targets() -> None:
    targets = [
        PublishedReportTarget("1.0", "ml_report", 1, "file-1"),
        PublishedReportTarget("1.0", "ml_report", 2, "file-2"),
    ]

    assert limit_targets(targets, 1) == targets[:1]
    assert limit_targets(targets, None) == targets


def test_skip_targets_from_env_removes_numeric_and_typed_ids() -> None:
    targets = [
        PublishedReportTarget("1.0", "ml_report", 971, "file-971"),
        PublishedReportTarget("1.0", "post", 844, "file-844"),
        PublishedReportTarget("1.0", "ml_report", 965, "file-965"),
    ]

    assert skip_targets_from_env(targets, "ml_report:971,844") == targets[2:]
