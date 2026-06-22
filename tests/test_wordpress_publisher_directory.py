from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "Wordpress" / "wp-content" / "plugins" / "marketlense-core"
DIRECTORY = PLUGIN / "includes" / "class-marketlense-core-publisher-directory.php"
ARCHIVE = PLUGIN / "includes" / "class-marketlense-core-archive-browser.php"


def test_publisher_directory_uses_the_report_archive_layout_without_a_publisher_select() -> None:
    source = DIRECTORY.read_text(encoding="utf-8")
    assert "publisher_directory_context" in source
    assert 'name="ml_publisher"' not in source
    assert 'class="ml-archive-browser-page ml-reports-archive-page ml-publisher-browser ml-report-browser"' in source
    assert 'class="ml-report-browser-layout"' in source
    assert "render_publisher_directory_utility_bar" in source
    assert "render_publisher_directory_filter_sidebar" in source
    assert "PUBLISHER_REPORT_VALUE_SCORE_META" in source
    assert "PUBLISHER_REPORT_VALUE_SAMPLE_SIZE_META" in source
    assert "ml-publisher-categories" in source
    assert "ml-publisher-directory-eyebrow" in source
    assert "ml-publisher-directory-card__footer" in source


def test_unfiltered_publisher_directory_uses_every_content_backed_publisher() -> None:
    source = DIRECTORY.read_text(encoding="utf-8")

    assert "content_backed_terms(Taxonomies::PUBLISHER_TAXONOMY, 300)" in source
    assert "$context['has_active_filters']" in source
    assert "? $this->matching_publisher_items($context['post_ids'])" in source
    assert ": $this->all_publisher_items($context['post_ids']);" in source


def test_archive_browser_exposes_publisher_directory_report_context() -> None:
    source = ARCHIVE.read_text(encoding="utf-8")
    assert "public function publisher_directory_context" in source
    assert "public function render_publisher_directory_utility_bar" in source
    assert "public function render_publisher_directory_filter_sidebar" in source
    assert "private function selected_publisher_directory_filters" in source
    assert "ml_publisher_topic" in source
    assert "ml_publisher_search" in source
    assert "$filters['publisher'] = '';" in source
    assert "'has_active_filters'" in source
    assert "Meta::apply_report_card_query_constraints" in source


def test_publisher_directory_context_reads_only_its_namespaced_filter_parameters() -> None:
    source = ARCHIVE.read_text(encoding="utf-8")
    start = source.index("public function publisher_directory_context")
    end = source.index("public function render_publisher_directory_utility_bar", start)
    context = source[start:end]

    assert "$this->selected_publisher_directory_filters()" in context
    assert "$this->selected_filters()" not in context
