from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


def test_entity_cards_share_the_report_card_size_contract() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")
    start = css.index("/* BEGIN unified entity-card size contract */")
    end = css.index("/* END unified entity-card size contract */", start)
    contract = css[start:end]

    assert ".ml-card--small .ml-card__media" in contract
    assert ".ml-briefing-card--small .ml-briefing-card__media" in contract
    assert ".ml-signal-card--small .ml-signal-card__media" in contract
    assert "aspect-ratio: 16 / 9" in contract
    assert ".ml-card__link > p:empty" in contract
    assert ".ml-briefing-card__link > p:empty" in contract
    assert ".ml-signal-card__link > p:empty" in contract
    assert "grid-template-columns: minmax(13rem, 36%) minmax(0, 1fr)" in contract
    assert "grid-template-columns: minmax(16rem, 40%) minmax(0, 1fr)" in contract
    assert "@container (min-width: 28rem)" in contract
    assert ".ml-briefing-card--large .ml-briefing-card__link" in contract
    assert "aspect-ratio: 16 / 10" in contract
    assert contract.count("object-fit: contain") == 1
