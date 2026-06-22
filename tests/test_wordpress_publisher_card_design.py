from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME_CSS = ROOT / "Wordpress" / "wp-content" / "themes" / "marketlense" / "assets" / "css" / "theme.css"


def test_publisher_cards_have_a_distinct_institutional_identity_and_footer() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")

    assert ".ml-publisher-directory-eyebrow" in css
    assert ".ml-publisher-directory-card__footer" in css
    assert ".ml-publisher-quality__label" in css
    assert "minmax(min(100%, 19rem), 1fr)" in css
