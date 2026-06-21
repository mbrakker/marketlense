from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "Wordpress" / "wp-content" / "themes" / "marketlense" / "templates" / "page-publishers-directory.html"


def test_publisher_directory_uses_standard_medium_report_cards_for_latest_reports() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")

    assert '[ml_report_browser per_page="6" show_filters="0" show_pagination="0" context="latest" card_size="medium"]' in template
