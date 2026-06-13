from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "Wordpress" / "scripts" / "audit-report-card-contracts.php"
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
