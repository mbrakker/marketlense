from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "Wordpress" / "wp-content" / "themes" / "marketlense"
PLUGIN = ROOT / "Wordpress" / "wp-content" / "plugins" / "marketlense-core"
FRONT_PAGE = THEME / "templates" / "front-page.html"
HEADER = THEME / "parts" / "header.html"
FOOTER = THEME / "parts" / "footer.html"
HERO = THEME / "patterns" / "hero-institutional.php"
SHORTCODES = PLUGIN / "includes" / "class-marketlense-core-shortcodes.php"
REPORT_FILTERS_JS = PLUGIN / "assets" / "js" / "report-filters.js"
VIEW_MODEL = (
    PLUGIN / "includes" / "class-marketlense-core-report-view-model-builder.php"
)
STATS = PLUGIN / "includes" / "class-marketlense-core-intelligence-stats.php"
PLUGIN_BOOTSTRAP = PLUGIN / "includes" / "class-marketlense-core-plugin.php"
THEME_BOOTSTRAP = THEME / "functions.php"
THEME_CSS = THEME / "assets" / "css" / "theme.css"
THEME_JSON = THEME / "theme.json"
HEADER_NAV = THEME / "parts" / "header.html"
CONTENT_FORMATTING = (
    PLUGIN / "includes" / "class-marketlense-core-content-formatting.php"
)
REPORT_ARCHIVE = THEME / "templates" / "archive-ml_report.html"
GENERIC_ARCHIVE = THEME / "templates" / "archive.html"
SIGNAL_ARCHIVE = THEME / "templates" / "archive-ml_signal.html"
BRIEFING_ARCHIVE = THEME / "templates" / "archive-ml_briefing.html"
TOPICS_PAGE = THEME / "templates" / "page-topics-directory.html"
PUBLISHERS_PAGE = THEME / "templates" / "page-publishers-directory.html"


def _editorial_ledger_css_rule(css: str, selector: str) -> str:
    marker = "/* Homepage Editorial Ledger refresh: approved 2026-06-12. */"
    assert marker in css
    scoped_css = css[css.index(marker) :]
    match = re.search(
        rf"{re.escape(selector)}\s*\{{(?P<body>[^}}]*)\}}",
        scoped_css,
        flags=re.DOTALL,
    )
    assert match, f"Missing CSS rule for {selector}"
    return match.group("body")


def test_market_bearing_brand_is_reused_in_header_and_footer() -> None:
    header = HEADER.read_text(encoding="utf-8")
    footer = FOOTER.read_text(encoding="utf-8")
    shortcodes = SHORTCODES.read_text(encoding="utf-8")

    assert "[ml_brand_logo]" in header
    assert '[ml_brand_logo mode="footer"]' in footer
    assert "ml-report-card-spacing-fix" not in header
    assert "'ml_brand_logo' => 'render_brand_logo'" in shortcodes
    assert "Market<span>Bearing</span>" in shortcodes
    assert "home_url('/')" in shortcodes


def test_homepage_preserves_the_approved_dynamic_module_sequence() -> None:
    front_page = FRONT_PAGE.read_text(encoding="utf-8")
    expected = [
        "marketlense/hero-institutional",
        "marketlense/featured-digest",
        "marketlense/featured-briefing",
        "marketlense/this-week-intelligence",
        "marketlense/report-grid",
        "marketlense/strategic-themes",
        "marketlense/publisher-authority",
        "marketlense/how-it-works",
        "marketlense/newsletter-cta",
    ]

    positions = [front_page.index(marker) for marker in expected]
    assert positions == sorted(positions)
    assert "marketlense/latest-signals" not in front_page


def test_homepage_positioning_uses_market_bearing_value_language() -> None:
    hero = HERO.read_text(encoding="utf-8")

    assert "Governed market intelligence" in hero
    assert "Published research," in hero
    assert "made decision-ready." in hero
    assert "Market Bearing is the governed intelligence layer" in hero
    assert "Source-traceable" in hero
    assert "Evidence-governed" in hero


def test_report_artifact_counts_drive_trust_and_card_citations() -> None:
    view_model = VIEW_MODEL.read_text(encoding="utf-8")
    stats = STATS.read_text(encoding="utf-8")
    shortcodes = SHORTCODES.read_text(encoding="utf-8")
    bootstrap = PLUGIN_BOOTSTRAP.read_text(encoding="utf-8")
    renderer = (
        PLUGIN / "includes" / "class-marketlense-core-report-card-renderer.php"
    ).read_text(encoding="utf-8")

    assert "'citations_count' => $counts['citations']" in view_model
    assert "'citations' =>" in view_model
    assert "'citation_count' =>" in stats
    assert "'briefing_count' =>" in stats
    assert "'signal_count' =>" in stats
    assert "new Intelligence_Stats($this->view_model_builder)" in bootstrap
    assert "Citations & evidence links" in shortcodes
    assert "citations_count" not in renderer
    assert "quotes_count" not in renderer
    assert "topics_count" not in renderer
    assert "Read report" in renderer


def test_dynamic_posting_routes_remain_native_wordpress_archives() -> None:
    shortcodes = SHORTCODES.read_text(encoding="utf-8")

    assert "'post_type' => Post_Type::BRIEFING_POST_TYPE" in shortcodes
    assert "Post_Type::SIGNAL_POST_TYPE" in shortcodes
    assert "get_post_type_archive_link(Post_Type::POST_TYPE)" in shortcodes
    assert "'post_status' => 'publish'" in shortcodes
    assert "The Leaky Bucket" not in shortcodes
    assert "M.CAST" not in shortcodes


def test_legacy_site_editor_header_is_migrated_to_the_canonical_wordmark() -> None:
    theme_bootstrap = THEME_BOOTSTRAP.read_text(encoding="utf-8")
    plugin_bootstrap = PLUGIN_BOOTSTRAP.read_text(encoding="utf-8")

    assert "marketlense_refresh_legacy_header_override" in theme_bootstrap
    assert "wp_template_part" in theme_bootstrap
    assert "wp:site-title" in theme_bootstrap
    assert "wp_delete_post" in theme_bootstrap
    assert "Market Bearing" in plugin_bootstrap
    assert "update_option('blogname'" in plugin_bootstrap


def test_navigation_covers_every_primary_prototype_destination() -> None:
    shortcodes = SHORTCODES.read_text(encoding="utf-8")
    primary_nav = shortcodes[
        shortcodes.index("public function render_primary_nav") : shortcodes.index(
            "public function render_footer_nav"
        )
    ]
    expected_order = [
        "'reports'",
        "'topics-directory'",
        "'publishers-directory'",
        "'signals'",
        "'briefings'",
        "'methodology'",
    ]

    positions = [primary_nav.index(marker) for marker in expected_order]
    assert positions == sorted(positions)
    assert "['label' => __('Signals'" in shortcodes
    assert "['label' => __('Briefings'" in shortcodes


def test_archive_templates_use_editorial_heroes_with_dynamic_counts() -> None:
    templates = {
        REPORT_ARCHIVE: 'entity="reports"',
        GENERIC_ARCHIVE: 'entity="reports"',
        SIGNAL_ARCHIVE: 'entity="signals"',
        BRIEFING_ARCHIVE: 'entity="briefings"',
        TOPICS_PAGE: 'entity="topics"',
        PUBLISHERS_PAGE: 'entity="publishers"',
    }

    for template, counter_contract in templates.items():
        content = template.read_text(encoding="utf-8")
        assert "ml-directory-hero" in content
        assert "[ml_archive_metric" in content
        assert counter_contract in content

    report_archive = REPORT_ARCHIVE.read_text(encoding="utf-8")
    generic_archive = GENERIC_ARCHIVE.read_text(encoding="utf-8")
    assert 'entity="regions"' in report_archive
    assert 'icon="regions"' in report_archive
    assert "ml-reports-archive-page" in generic_archive
    assert "ml-reports-hero-stats" in generic_archive
    assert 'entity="regions"' in generic_archive


def test_report_archive_exposes_real_live_search_region_and_period_filters() -> None:
    shortcodes = SHORTCODES.read_text(encoding="utf-8")
    stats = STATS.read_text(encoding="utf-8")
    filter_js = REPORT_FILTERS_JS.read_text(encoding="utf-8")

    assert "ml_report_search" in shortcodes
    assert "data-ml-live-filter-form" in shortcodes
    assert "data-ml-live-filter-input" in shortcodes
    assert "marketlense-core-report-filters" in shortcodes
    assert "ml_period_filter" in shortcodes
    assert 'name="ml_period"' in shortcodes
    assert "ml_region_filter" in shortcodes
    assert 'name="ml_region"' in shortcodes
    assert "ml-report-browser-utility-bar" in shortcodes
    assert "ml-report-search-form" in shortcodes
    assert "ml-report-search-field" in shortcodes
    assert shortcodes.index("ml-report-browser-utility-bar") < shortcodes.index("ml-report-browser-layout")
    assert "Meta::META_TIME_PERIOD" in shortcodes
    assert "Meta::META_REGION" in shortcodes
    assert "report_periods()" in shortcodes
    assert "report_regions()" in shortcodes
    assert "public function report_regions()" in stats
    assert "Apply filters" not in shortcodes
    assert "form.submit()" in filter_js
    assert "change" in filter_js
    assert "input" in filter_js


def test_taxonomy_directories_only_render_content_backed_entities() -> None:
    stats = STATS.read_text(encoding="utf-8")
    shortcodes = SHORTCODES.read_text(encoding="utf-8")

    assert "content_backed_terms" in stats
    assert "'reports' =>" in stats
    assert "'briefings' =>" in stats
    assert "'signals' =>" in stats
    assert "$this->stats->content_backed_terms" in shortcodes
    assert "$this->stats->all_terms" not in shortcodes


def test_signal_archive_reuses_published_report_artifacts_when_needed() -> None:
    shortcodes = SHORTCODES.read_text(encoding="utf-8")

    assert "render_report_signal_archive" in shortcodes
    assert "Report signal" in shortcodes
    assert "Review source context" in shortcodes
    assert "full_key_metrics" in shortcodes


def test_legacy_metadata_sentinels_are_not_rendered_as_real_content() -> None:
    view_model = VIEW_MODEL.read_text(encoding="utf-8")
    stats = STATS.read_text(encoding="utf-8")

    assert "is_missing_metadata_value" in view_model
    assert "'Not extracted'" in view_model
    assert "is_placeholder_term" in stats
    assert "'...'" in stats


def test_legacy_brand_wording_is_normalized_on_rendered_archive_cards() -> None:
    view_model = VIEW_MODEL.read_text(encoding="utf-8")
    shortcodes = SHORTCODES.read_text(encoding="utf-8")

    assert "normalize_brand_name" in view_model
    assert "Market Bearing" in view_model
    assert "$record['archive_excerpt']" in shortcodes


def test_mobile_navigation_and_report_artifacts_do_not_force_page_overflow() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")

    assert ".ml-ingest-report-content .page-grid > *" in css
    assert ".ml-ingest-report-content .content > *" in css
    assert ".ml-header-actions > *" in css
    assert "min-width: 0;" in css
    assert ".ml-primary-nav .wp-block-navigation__container" in css
    assert "flex-wrap: nowrap;" in css
    assert "overflow-x: auto;" in css
    assert "min-height: 44px;" in css


def test_editorial_language_prefers_reports_and_report_briefs() -> None:
    shortcodes = SHORTCODES.read_text(encoding="utf-8")
    templates = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            THEME / "templates" / "home.html",
            THEME / "templates" / "page-about.html",
            THEME / "templates" / "page-methodology.html",
            THEME / "templates" / "page-submit-a-report.html",
            THEME / "templates" / "page-terms.html",
        )
    )

    assert "Featured Report Brief" in shortcodes
    assert "Read report brief" in shortcodes
    assert "_n('%d report', '%d reports'" in shortcodes
    assert " digest" not in templates.lower()


def test_homepage_uses_compact_deep_blue_briefing_and_source_backed_signals() -> None:
    shortcodes = SHORTCODES.read_text(encoding="utf-8")
    css = THEME_CSS.read_text(encoding="utf-8")
    theme_json = THEME_JSON.read_text(encoding="utf-8")

    assert "source_backed_signals" in shortcodes
    assert "wp_rand" in shortcodes
    assert "ml-source-signal-strip" in shortcodes
    assert ".ml-featured-briefing-card" in css
    assert "max-height:" in css
    assert '"slug": "support-blue"' in theme_json
    assert '"color": "#082b54"' in theme_json


def test_report_filters_use_a_compact_sticky_disclosure_rail() -> None:
    shortcodes = SHORTCODES.read_text(encoding="utf-8")
    css = THEME_CSS.read_text(encoding="utf-8")

    assert '<details class="ml-report-filter-panel" open>' in shortcodes
    assert "ml-report-filter-summary" in shortcodes
    assert "ml-report-filter-header" in shortcodes
    assert "ml-filter-chip-clear" in shortcodes
    assert "render_active_filter_chips" in shortcodes
    assert "report_facet_terms" in shortcodes
    assert "report_facet_meta_values" in shortcodes
    assert "ml_sort_filter" not in shortcodes
    assert "render_report_sort_controls" in shortcodes
    assert "ml-report-sort-controls" in shortcodes
    assert ".ml-report-browser-sidebar" in css
    assert ".ml-report-browser-sidebar-card" in css
    assert ".ml-report-browser-utility-bar" in css
    assert ".ml-report-sort-controls" in css
    assert ".ml-report-sort-icon--latest" in css
    assert "width: 100%;" in css
    assert "grid-template-columns: minmax(0, 1fr);" in css
    assert "min-height: 2.22rem;" in css
    assert "height: 1.95rem;" in css
    assert "align-self: start;" in css
    assert "position: sticky;" in css
    assert "max-height: calc(100dvh" in css
    assert "overflow-y: auto;" in css
    assert ".ml-archive-metric-icon--regions" in css
    assert "grid-template-columns: 2.6rem minmax(0, 1fr);" in css
    assert "min-height: 2.08rem;" in css


def test_topic_archives_fall_back_to_published_briefings_when_no_reports_exist() -> (
    None
):
    shortcodes = SHORTCODES.read_text(encoding="utf-8")

    assert "topic_entity_fallback_query" in shortcodes
    assert "Post_Type::BRIEFING_POST_TYPE" in shortcodes
    assert "Report briefs in this topic" in shortcodes


def test_briefing_output_removes_internal_ids_and_collapses_appendices() -> None:
    formatting = CONTENT_FORMATTING.read_text(encoding="utf-8")
    css = THEME_CSS.read_text(encoding="utf-8")

    assert "format_briefing_for_readers" in formatting
    assert "DOMDocument" in formatting
    assert "ml-briefing-appendix" in formatting
    assert "source evidence" in formatting
    assert ".ml-briefing-appendix" in css


def test_public_pages_enable_indexing_and_core_sitemaps() -> None:
    plugin = PLUGIN_BOOTSTRAP.read_text(encoding="utf-8")

    assert "migrate_public_discovery" in plugin
    assert "update_option('blog_public', '1')" in plugin
    assert "wp_sitemaps_enabled" in plugin


def test_header_exposes_search_and_a_mobile_menu_without_horizontal_discovery() -> None:
    header = HEADER_NAV.read_text(encoding="utf-8")
    shortcodes = SHORTCODES.read_text(encoding="utf-8")
    css = THEME_CSS.read_text(encoding="utf-8")

    assert "ml-header-search" in header
    assert "ml-mobile-nav" in shortcodes
    assert "<summary" in shortcodes
    assert ".ml-mobile-nav" in css


def test_hero_places_latest_brief_below_search_and_trust_metrics_on_the_right() -> None:
    hero = HERO.read_text(encoding="utf-8")
    shortcodes = SHORTCODES.read_text(encoding="utf-8")
    css = THEME_CSS.read_text(encoding="utf-8")

    search_position = hero.index('"className":"ml-hero-search"')
    latest_position = hero.index("[ml_hero_snapshot]")
    trust_position = hero.index("[ml_hero_trust]")

    assert search_position < latest_position < trust_position
    assert "ml-hero-latest-row" in hero
    assert "ml-hero-trust-panel" in hero
    assert "ml-hero-metrics" not in hero
    assert "'ml_hero_trust' => 'render_hero_trust'" in shortcodes
    assert "$this->stats->publisher_authority(5)" in shortcodes
    assert "Top publishers" in shortcodes
    assert (
        "Signal of the moment"
        not in shortcodes[
            shortcodes.index("public function render_hero_snapshot") : shortcodes.index(
                "public function render_hero_trust"
            )
        ]
    )
    assert ".ml-hero-latest-row" in css
    assert ".ml-hero-trust-panel" in css
    assert "container-type: inline-size;" in css


def test_desktop_header_uses_centered_sticky_navigation_with_brand_indicator() -> None:
    header = HEADER.read_text(encoding="utf-8")
    css = THEME_CSS.read_text(encoding="utf-8")

    nav_position = header.index('template-part {"slug":"nav"')
    search_position = header.index('"className":"ml-header-search"')

    assert "ml-header-navigation-stack" in header
    assert nav_position < search_position
    assert '"placeholder":"Report, publisher, topic or signal"' in header
    assert "position: sticky;" in css
    assert "top: 0;" in css
    assert ".ml-header-navigation-stack" in css
    assert ".ml-primary-nav .wp-block-navigation-item__content::before" in css
    assert ".ml-primary-nav .wp-block-navigation-item__content::after" in css
    assert "border-radius: 50%;" in css


def test_homepage_uses_tighter_editorial_spacing_and_close_section_signals() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")
    home_shell = _editorial_ledger_css_rule(css, ".ml-home-shell")
    section_heading = _editorial_ledger_css_rule(
        css, ".ml-home-shell .ml-section-heading"
    )
    section_title = _editorial_ledger_css_rule(css, ".ml-home-shell .ml-section-title")
    section_rule = _editorial_ledger_css_rule(css, ".ml-home-shell .ml-section-rule")

    assert "--ml-home-section-gap: clamp(3.5rem, 5vw, 4.5rem);" in home_shell
    assert "--ml-home-band-padding: clamp(3rem, 4.5vw, 4rem);" in home_shell
    assert "row-gap: 0;" in section_heading
    assert "margin-bottom: 0;" in section_title
    assert "margin: 0.375rem 0 1rem;" in section_rule


def test_discovery_band_uses_the_approved_editorial_ledger_surface() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")
    discovery = _editorial_ledger_css_rule(css, ".ml-home-band-frame-discovery")
    heading_row = _editorial_ledger_css_rule(
        css, ".ml-home-band-discovery .ml-section-heading-row"
    )
    themes = _editorial_ledger_css_rule(css, ".ml-home-band-discovery .ml-theme-list")

    assert "border: 1px solid var(--ml-border-subtle);" in discovery
    assert "border-radius: 0.875rem;" in discovery
    assert "box-shadow: 0 1.25rem 3.75rem rgba(8, 43, 84, 0.12);" in discovery
    assert "grid-template-columns: minmax(0, 1fr) auto;" in heading_row
    assert "counter-reset: ml-theme;" in themes
    assert ".ml-home-band-discovery .ml-authority-item" in css


def test_discovery_heading_stacks_cleanly_on_mobile() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")
    ledger_css = css.split(
        "/* Homepage Editorial Ledger refresh: approved 2026-06-12. */", 1
    )[1]

    assert re.search(
        r"@media \(max-width: 640px\).*?"
        r"\.ml-home-band-discovery \.ml-section-heading-row\s*\{[^}]*"
        r"grid-template-columns: 1fr;",
        ledger_css,
        re.DOTALL,
    )
    assert re.search(
        r"@media \(max-width: 640px\).*?"
        r"\.ml-home-band-discovery \.ml-inline-link\s*\{[^}]*"
        r"justify-self: start;",
        ledger_css,
        re.DOTALL,
    )


def test_desktop_header_aligns_controls_and_uses_signal_blue_nav_indicator() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")
    header_top = _editorial_ledger_css_rule(css, ".ml-header-top")
    header_actions = _editorial_ledger_css_rule(css, ".ml-header-actions")
    nav_stack = _editorial_ledger_css_rule(css, ".ml-header-navigation-stack")
    nav_container = _editorial_ledger_css_rule(
        css, ".ml-primary-nav .wp-block-navigation__container"
    )
    header_search = _editorial_ledger_css_rule(css, ".ml-header-search")
    nav_line = _editorial_ledger_css_rule(
        css, ".ml-primary-nav .wp-block-navigation-item__content::before"
    )

    assert "grid-template-columns: max-content minmax(0, 1fr);" in header_top
    assert (
        "grid-template-columns: minmax(0, 1fr) minmax(12rem, 14rem) max-content;"
        in header_actions
    )
    assert "margin: 0;" in header_actions
    assert "grid-template-columns: minmax(0, 1fr) minmax(12rem, 14rem);" in nav_stack
    assert "flex-wrap: nowrap;" in nav_container
    assert "margin: 0;" in header_search
    assert "background: var(--ml-signal-blue);" in nav_line
    assert "background: transparent !important;" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
