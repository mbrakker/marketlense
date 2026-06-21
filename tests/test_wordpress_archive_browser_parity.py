from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "Wordpress" / "wp-content" / "plugins" / "marketlense-core"
SHORTCODES = PLUGIN / "includes" / "class-marketlense-core-shortcodes.php"
ARCHIVE_BROWSER = PLUGIN / "includes" / "class-marketlense-core-archive-browser.php"
BOOTSTRAP = PLUGIN / "marketlense-core.php"
THEME_CSS = ROOT / "Wordpress" / "wp-content" / "themes" / "marketlense" / "assets" / "css" / "theme.css"


def test_archives_delegate_to_one_browser_owner() -> None:
    source = SHORTCODES.read_text(encoding="utf-8")

    assert ARCHIVE_BROWSER.exists()
    assert "new Archive_Browser(" in source
    assert "return $this->archive_browser->render($attrs, Archive_Browser::REPORTS);" in source
    assert "return $this->archive_browser->render($attrs, Archive_Browser::BRIEFINGS);" in source
    assert "return $this->archive_browser->render($attrs, Archive_Browser::SIGNALS);" in source
    assert "class-marketlense-core-archive-browser.php" in BOOTSTRAP.read_text(encoding="utf-8")


def test_shared_browser_exposes_controls_and_compact_cards() -> None:
    source = ARCHIVE_BROWSER.read_text(encoding="utf-8")

    assert 'class="ml-archive-browser-page ml-report-browser"' in source
    assert 'data-ml-live-filter-form' in source
    assert 'class="ml-report-browser-summary-value"' in source
    assert 'class="ml-report-sort-controls"' in source
    assert 'class="ml-report-browser-grid"' in source
    assert "$this->briefing_card_renderer->render($briefing, 'small')" in source
    assert "$this->signal_card_renderer->render($signal, 'small')" in source


def test_shared_archive_marker_receives_reports_geometry() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")

    assert ".ml-archive-browser-page .ml-report-browser-utility-bar" in css
    assert ".ml-archive-browser-page .ml-report-browser-sidebar" in css
    assert ".ml-archive-browser-page .ml-report-browser-head" in css
    assert ".ml-archive-browser-page .ml-briefing-card--small" in css
    assert ".ml-archive-browser-page .ml-signal-card--small" in css


def test_shared_archive_cards_use_the_reports_card_height_and_compact_copy() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")

    assert ".ml-archive-browser-page .ml-briefing-card--small," in css
    assert "block-size: 33.5rem;" in css
    assert ".ml-archive-browser-page .ml-briefing-card__summary," in css
    assert "-webkit-line-clamp: 4;" in css
