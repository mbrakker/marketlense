from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME_CSS = ROOT / "Wordpress" / "wp-content" / "themes" / "marketlense" / "assets" / "css" / "theme.css"


def test_publisher_report_strip_does_not_override_the_standard_report_card_presentation() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")

    assert ".ml-publishers-report-strip .ml-card__media" not in css
    assert ".ml-publishers-report-strip .ml-card--small .ml-card__body" not in css
