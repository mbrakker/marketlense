from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "Wordpress" / "wp-content" / "plugins" / "marketlense-core"
DIRECTORY = PLUGIN / "includes" / "class-marketlense-core-publisher-directory.php"
ARCHIVE = PLUGIN / "includes" / "class-marketlense-core-archive-browser.php"


def test_publisher_directory_reuses_report_filters_without_publisher_select() -> None:
    source = DIRECTORY.read_text(encoding="utf-8")
    assert "publisher_directory_context" in source
    assert 'name="ml_publisher"' not in source
    assert "render_publisher_directory_filters" in source
    assert "PUBLISHER_REPORT_VALUE_SCORE_META" in source
    assert "PUBLISHER_REPORT_VALUE_SAMPLE_SIZE_META" in source
    assert "ml-publisher-categories" in source


def test_unfiltered_publisher_directory_uses_every_content_backed_publisher() -> None:
    source = DIRECTORY.read_text(encoding="utf-8")

    assert "content_backed_terms(Taxonomies::PUBLISHER_TAXONOMY, 300)" in source
    assert "$context['has_active_filters']" in source
    assert "? $this->matching_publisher_items($context['post_ids'])" in source
    assert ": $this->all_publisher_items($context['post_ids']);" in source


def test_archive_browser_exposes_publisher_directory_report_context() -> None:
    source = ARCHIVE.read_text(encoding="utf-8")
    assert "public function publisher_directory_context" in source
    assert "public function render_publisher_directory_filters" in source
    assert "$filters['publisher'] = '';" in source
    assert "'has_active_filters'" in source
    assert "Meta::apply_report_card_query_constraints" in source
