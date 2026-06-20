from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RENDERER = (
    ROOT
    / "Wordpress"
    / "wp-content"
    / "plugins"
    / "marketlense-core"
    / "includes"
    / "class-marketlense-core-briefing-card-renderer.php"
)
THEME_CSS = (
    ROOT
    / "Wordpress"
    / "wp-content"
    / "themes"
    / "marketlense"
    / "assets"
    / "css"
    / "theme.css"
)
COVER_STYLES = ROOT / "src" / "config" / "cover-styles.yaml"
SHORTCODES = (
    ROOT
    / "Wordpress"
    / "wp-content"
    / "plugins"
    / "marketlense-core"
    / "includes"
    / "class-marketlense-core-shortcodes.php"
)


def test_briefing_title_is_centered_over_every_variant_cover() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")
    config = yaml.safe_load(COVER_STYLES.read_text(encoding="utf-8"))

    media_start = renderer.index('<div class="ml-briefing-card__media">')
    media_end = renderer.index('<div class="ml-briefing-card__body">')
    media = renderer[media_start:media_end]
    assert 'class="ml-briefing-card__cover"' in media
    layouts = config["profiles"]["briefing"]["layouts"]
    for layout in layouts.values():
        _, title_y, _, title_height = layout["title_rect"]
        assert title_y + title_height / 2 == layout["height"] / 2


def test_briefing_counters_have_source_and_evidence_icons() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")

    counters_start = renderer.index('<ul class="ml-briefing-card__counters">')
    counters_end = renderer.index("</ul>", counters_start)
    counters = renderer[counters_start:counters_end]
    assert counters.count('aria-hidden="true"') == 2
    assert "source report" in counters
    assert "evidence item" in counters


def test_briefing_archive_uses_one_shared_card_grid() -> None:
    source = SHORTCODES.read_text(encoding="utf-8")
    start = source.index("public function render_briefings_index")
    end = source.index("public function render_briefing_archive", start)
    method = source[start:end]

    assert method.count('<div class="ml-report-browser-grid">') == 1
    assert "$cards[] = $this->briefing_card_renderer->render" in method
