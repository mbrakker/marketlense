from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
README_WORDPRESS = ROOT / "README_WORDPRESS.md"
AUDIT_SCRIPT = ROOT / "Wordpress" / "scripts" / "audit-report-card-contracts.php"
PLUGIN_BOOTSTRAP = (
    ROOT
    / "Wordpress"
    / "wp-content"
    / "plugins"
    / "marketlense-core"
    / "marketlense-core.php"
)
PLUGIN_README = (
    ROOT / "Wordpress" / "wp-content" / "plugins" / "marketlense-core" / "readme.txt"
)
PLUGIN = (
    ROOT
    / "Wordpress"
    / "wp-content"
    / "plugins"
    / "marketlense-core"
    / "includes"
    / "class-marketlense-core-plugin.php"
)
SHORTCODES = (
    ROOT
    / "Wordpress"
    / "wp-content"
    / "plugins"
    / "marketlense-core"
    / "includes"
    / "class-marketlense-core-shortcodes.php"
)
INTELLIGENCE_STATS = (
    ROOT
    / "Wordpress"
    / "wp-content"
    / "plugins"
    / "marketlense-core"
    / "includes"
    / "class-marketlense-core-intelligence-stats.php"
)
META = (
    ROOT
    / "Wordpress"
    / "wp-content"
    / "plugins"
    / "marketlense-core"
    / "includes"
    / "class-marketlense-core-meta.php"
)
THEME = ROOT / "Wordpress" / "wp-content" / "themes" / "marketlense"
THEME_CSS = THEME / "assets" / "css" / "theme.css"
THEME_STYLE = THEME / "style.css"
REPORT_GRID = THEME / "patterns" / "report-grid.php"
MUTATION_GATE = ROOT / "scripts" / "ci" / "run_mutation_gate.py"


def test_report_card_audit_script_checks_complete_published_contract() -> None:
    source = AUDIT_SCRIPT.read_text(encoding="utf-8")

    required_keys = (
        "ml_card_schema_version",
        "ml_card_title_scale",
        "ml_card_tldr_compact",
        "ml_card_tldr_standard",
        "ml_card_key_insights",
        "ml_card_geography_scope",
        "ml_card_cover_fingerprint",
        "ml_card_cover_small_id",
        "ml_card_cover_medium_id",
        "ml_card_cover_large_id",
    )
    for key in required_keys:
        assert f"'{key}'" in source
    assert "$required_keys" in source
    assert "wp_attachment_is_image" in source
    assert "post_id" in source
    assert "post_title" in source
    assert "0 invalid published reports" in source
    assert "exit(1)" in source


def _method_source(source: str, method: str, next_method: str) -> str:
    start = source.index(f"public function {method}")
    end = source.index(f"public function {next_method}", start)
    return source[start:end]


def test_plugin_injects_one_canonical_report_card_renderer() -> None:
    plugin = PLUGIN.read_text(encoding="utf-8")
    shortcodes = SHORTCODES.read_text(encoding="utf-8")

    assert "private Report_Card_Renderer $report_card_renderer;" in plugin
    assert "new Report_Card_Renderer" in plugin
    assert "$this->report_card_renderer = $report_card_renderer;" in shortcodes
    assert "private function render_report_card" not in shortcodes


def test_every_report_placement_delegates_to_an_approved_variant() -> None:
    source = SHORTCODES.read_text(encoding="utf-8")
    report_browser = _method_source(
        source,
        "render_report_browser",
        "render_latest_reports",
    )
    latest_reports = _method_source(
        source,
        "render_latest_reports",
        "render_home_metrics",
    )
    hero_snapshot = _method_source(
        source,
        "render_hero_snapshot",
        "render_hero_trust",
    )
    featured_digest = _method_source(
        source,
        "render_featured_digest",
        "render_featured_briefing",
    )

    assert "$this->report_card_renderer->render($report, 'small')" in report_browser
    assert "$this->report_card_renderer->render($report, $variant)" in latest_reports
    assert "$this->report_card_renderer->render($latest, 'medium')" in hero_snapshot
    assert "$this->report_card_renderer->render($report, 'large')" in featured_digest
    assert "ml-report-card" not in report_browser
    assert "ml-report-card" not in latest_reports
    assert "ml-hero-snapshot-card" not in hero_snapshot
    assert "ml-featured-digest-card" not in featured_digest


def test_report_placements_reject_invalid_contracts_before_rendering() -> None:
    source = SHORTCODES.read_text(encoding="utf-8")
    report_browser = _method_source(
        source,
        "render_report_browser",
        "render_latest_reports",
    )
    latest_reports = _method_source(
        source,
        "render_latest_reports",
        "render_home_metrics",
    )
    hero_snapshot = _method_source(
        source,
        "render_hero_snapshot",
        "render_hero_trust",
    )
    featured_digest = _method_source(
        source,
        "render_featured_digest",
        "render_featured_briefing",
    )

    for listing in (report_browser, latest_reports):
        validation = listing.index("card_contract_valid")
        rendering = listing.index("$this->report_card_renderer->render")
        assert validation < rendering
        assert "continue;" in listing[validation:rendering]

    for feature in (hero_snapshot, featured_digest):
        validation = feature.index("card_contract_valid")
        rendering = feature.index("$this->report_card_renderer->render")
        assert validation < rendering
        assert "return '';" in feature[validation:rendering]


def test_report_list_queries_paginate_only_canonical_card_contracts() -> None:
    shortcodes = SHORTCODES.read_text(encoding="utf-8")
    meta = META.read_text(encoding="utf-8")
    report_browser = _method_source(
        shortcodes,
        "render_report_browser",
        "render_latest_reports",
    )
    query_builder_start = shortcodes.index("private function report_browser_query_args")
    query_builder_end = shortcodes.index("private function report_facet_post_ids")
    report_browser_query_args = shortcodes[query_builder_start:query_builder_end]
    latest_reports = _method_source(
        shortcodes,
        "render_latest_reports",
        "render_home_metrics",
    )

    assert "public static function apply_report_card_query_constraints" in meta
    assert "self::META_CARD_SCHEMA_VERSION" in meta
    assert "'value' => '1.0'" in meta
    assert "report_browser_query_args" in report_browser
    assert (
        "Meta::apply_report_card_query_constraints($query_args)"
        in report_browser_query_args
    )
    assert "Meta::apply_report_card_query_constraints(" in latest_reports


def test_latest_report_selects_newest_valid_card_contract() -> None:
    source = INTELLIGENCE_STATS.read_text(encoding="utf-8")
    latest_report = _method_source(
        source,
        "latest_report",
        "homepage_metrics",
    )

    assert "$this->published_report_ids()" in latest_report
    assert "get_post($post_id)" in latest_report
    assert "$this->view_model_builder->build($post)" in latest_report
    assert "card_contract_valid" in latest_report
    assert "return $post;" in latest_report


def test_latest_reports_rejects_noncanonical_explicit_variant() -> None:
    source = SHORTCODES.read_text(encoding="utf-8")
    latest_reports = _method_source(
        source,
        "render_latest_reports",
        "render_home_metrics",
    )

    assert "'variant' => 'small'" in latest_reports
    assert "sanitize_key((string) $atts['variant'])" in latest_reports
    assert "['small', 'medium', 'large']" in latest_reports
    assert "throw new \\InvalidArgumentException" in latest_reports


def test_report_patterns_request_only_canonical_card_variants() -> None:
    report_grid = REPORT_GRID.read_text(encoding="utf-8")
    assert '[ml_latest_reports limit="6" variant="small"]' in report_grid

    report_surfaces = [
        THEME / "patterns" / "featured-digest.php",
        THEME / "patterns" / "hero-institutional.php",
        THEME / "templates" / "archive-ml_report.html",
        THEME / "templates" / "category.html",
        THEME / "templates" / "search.html",
        THEME / "templates" / "taxonomy-ml_publisher.html",
    ]
    for path in report_surfaces:
        source = path.read_text(encoding="utf-8")
        assert "<!-- wp:query {" not in source
        assert "ml-report-card" not in source


def test_canonical_card_css_preserves_all_semantic_text() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")
    start_marker = "/* BEGIN canonical report cards */"
    end_marker = "/* END canonical report cards */"
    assert start_marker in css
    assert end_marker in css
    canonical = css[css.index(start_marker) : css.index(end_marker)]

    for selector in (
        ".ml-card--small",
        ".ml-card--medium",
        ".ml-card--large",
        ".ml-card__title",
        ".ml-card__tldr",
        ".ml-card__facts",
        ".ml-card__insights",
    ):
        assert selector in canonical

    assert "-webkit-line-clamp" not in canonical
    assert "line-clamp" not in canonical
    assert "text-overflow: ellipsis" not in canonical
    assert "grid-template-rows:" in canonical
    assert "text-wrap: balance" in canonical
    assert "text-wrap: pretty" in canonical
    assert ":focus-visible" in canonical
    assert "prefers-reduced-motion: reduce" in canonical
    assert (
        ".ml-card--medium .ml-card__media {\n"
        "  align-self: stretch;\n"
        "  aspect-ratio: auto;"
    ) in canonical
    assert (
        ".ml-card--medium .ml-card__cover,\n"
        ".ml-card--large .ml-card__cover {\n"
        "  object-fit: contain;"
    ) in canonical
    assert "align-self: auto;\n    aspect-ratio: 16 / 10;" in canonical


def test_report_card_release_metadata_and_documentation_are_complete() -> None:
    plugin = PLUGIN_BOOTSTRAP.read_text(encoding="utf-8")
    plugin_readme = PLUGIN_README.read_text(encoding="utf-8")
    theme = THEME_STYLE.read_text(encoding="utf-8")
    docs = README.read_text(encoding="utf-8") + README_WORDPRESS.read_text(
        encoding="utf-8"
    )

    assert "Version: 1.7.0" in plugin
    assert "MARKETLENSE_CORE_VERSION', '1.7.0'" in plugin
    assert "Stable tag: 1.7.0" in plugin_readme
    assert "= 1.7.0 =" in plugin_readme
    assert "Version: 1.5.11" in theme

    for required_text in (
        "small",
        "medium",
        "large",
        "18 words",
        "45 words",
        "16 geometry families",
        "1600x900",
        "1200x1500",
        "1200x1600",
        "geometry_family",
        "seed",
        "less than 7 days",
        "globe",
        "locator",
        "audit-report-card-contracts.php",
        "build-plugin-zip.ps1",
        "build-theme-zip.sh",
        "build-theme-zip.ps1",
    ):
        assert required_text in docs


def test_report_card_decision_logic_is_covered_by_mutation_gate() -> None:
    source = MUTATION_GATE.read_text(encoding="utf-8")

    for module_name in (
        "report_card_projection.py",
        "cover_image_generator.py",
        "report_render_generator.py",
        "publish_generator.py",
    ):
        assert f'/ "{module_name}"' in source
