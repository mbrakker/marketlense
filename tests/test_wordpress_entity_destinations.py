from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "Wordpress" / "wp-content" / "plugins" / "marketlense-core"
THEME_TEMPLATES = (
    REPO_ROOT / "Wordpress" / "wp-content" / "themes" / "marketlense" / "templates"
)
POST_TYPE_PATH = PLUGIN_ROOT / "includes" / "class-marketlense-core-post-type.php"
SHORTCODES_PATH = PLUGIN_ROOT / "includes" / "class-marketlense-core-shortcodes.php"
TAXONOMIES_PATH = PLUGIN_ROOT / "includes" / "class-marketlense-core-taxonomies.php"
README_PATH = REPO_ROOT / "README.md"
README_WORDPRESS_PATH = REPO_ROOT / "README_WORDPRESS.md"
APP_CONFIG_PATH = REPO_ROOT / "src" / "config" / "app.yaml"
APP_EXAMPLE_CONFIG_PATH = REPO_ROOT / "src" / "config" / "app.example.yaml"
GENERATOR_PATH = REPO_ROOT / "src" / "generators" / "cross_report_analysis_generator.py"
CROSS_REPORT_REQUEST_CONTRACT_PATH = (
    REPO_ROOT / "src" / "contracts" / "_cross_report_analysis" / "requests.py"
)


def test_wordpress_registers_signal_and_briefing_destinations() -> None:
    source = POST_TYPE_PATH.read_text(encoding="utf-8")

    assert "public const SIGNAL_POST_TYPE = 'ml_signal';" in source
    assert "public const BRIEFING_POST_TYPE = 'ml_briefing';" in source
    assert re.search(r"register_post_type\(\s*self::SIGNAL_POST_TYPE", source)
    assert re.search(r"register_post_type\(\s*self::BRIEFING_POST_TYPE", source)
    assert re.search(r"'rest_base'\s*=>\s*self::SIGNAL_POST_TYPE", source)
    assert re.search(r"'rest_base'\s*=>\s*self::BRIEFING_POST_TYPE", source)
    assert re.search(r"'slug'\s*=>\s*'signals'", source)
    assert re.search(r"'slug'\s*=>\s*'briefings'", source)


def test_report_publish_contract_uses_ml_report_as_canonical_type() -> None:
    post_type_source = POST_TYPE_PATH.read_text(encoding="utf-8")
    readme_source = README_PATH.read_text(encoding="utf-8")
    app_config_source = APP_CONFIG_PATH.read_text(encoding="utf-8")
    app_example_source = APP_EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8")

    assert 'post_type: "ml_report"' in app_config_source
    assert 'post_type: "ml_report"' in app_example_source
    assert "public const POST_TYPE = 'ml_report';" in post_type_source
    assert "public const CORE_POST_TYPE = 'post';" in post_type_source
    assert re.search(r"register_post_type\(\s*self::POST_TYPE", post_type_source)
    assert re.search(r"'rest_base'\s*=>\s*self::POST_TYPE", post_type_source)
    assert re.search(r"'slug'\s*=>\s*'reports'", post_type_source)
    assert "Canonical report post type: `ml_report`" in readme_source
    assert "New report publishing must not target core `post`" in readme_source
    assert "publish.wp.post_type=posts" not in readme_source


def test_public_report_copy_uses_report_not_report_brief() -> None:
    sources = {
        "README.md": README_PATH.read_text(encoding="utf-8"),
        "README_WORDPRESS.md": README_WORDPRESS_PATH.read_text(encoding="utf-8"),
        "shortcodes": SHORTCODES_PATH.read_text(encoding="utf-8"),
    }

    for source in sources.values():
        assert "Featured Report Brief" not in source
        assert "Report Brief" not in source
        assert "Report briefs" not in source
        assert "Featured report brief" not in source

    assert "Featured Report" in sources["shortcodes"]


def test_wordpress_templates_render_canonical_signal_and_briefing_surfaces() -> None:
    expected_templates = {
        "page-signals.html": "[ml_signals_index",
        "page-briefings.html": "[ml_briefings_index",
        "archive-ml_signal.html": "[ml_signals_index",
        "archive-ml_briefing.html": "[ml_briefings_index",
        "single-ml_signal.html": "single-content",
        "single-ml_briefing.html": "single-content",
    }

    for template_name, required_marker in expected_templates.items():
        source = (THEME_TEMPLATES / template_name).read_text(encoding="utf-8")
        assert required_marker in source


def test_wordpress_shortcodes_expose_signal_and_briefing_archives() -> None:
    source = SHORTCODES_PATH.read_text(encoding="utf-8")

    assert "'ml_signal_archive' => 'render_signal_archive'" in source
    assert "'ml_briefing_archive' => 'render_briefing_archive'" in source
    assert "Post_Type::SIGNAL_POST_TYPE" in source
    assert "Post_Type::BRIEFING_POST_TYPE" in source


def test_native_categories_are_governed_topic_surface() -> None:
    shortcode_source = SHORTCODES_PATH.read_text(encoding="utf-8")
    taxonomy_source = TAXONOMIES_PATH.read_text(encoding="utf-8")
    category_template = (THEME_TEMPLATES / "category.html").read_text(encoding="utf-8")

    assert "public const CATEGORY_TAXONOMY = 'category';" in taxonomy_source
    assert "TOPIC_DEFINITION_META = 'ml_topic_definition'" in taxonomy_source
    assert "TOPIC_INCLUDE_WHEN_META = 'ml_topic_include_when'" in taxonomy_source
    assert "TOPIC_EXCLUDE_WHEN_META = 'ml_topic_exclude_when'" in taxonomy_source
    assert "register_term_meta(\n            self::CATEGORY_TAXONOMY" in taxonomy_source
    assert (
        "'ml_topic_semantics' => 'render_current_topic_semantics'" in shortcode_source
    )
    assert "Taxonomies::TOPIC_DEFINITION_META" in shortcode_source
    assert "[ml_topic_semantics]" in category_template


def test_publisher_taxonomy_assigns_to_signal_and_briefing_destinations() -> None:
    source = TAXONOMIES_PATH.read_text(encoding="utf-8")

    assert "Post_Type::SIGNAL_POST_TYPE" in source
    assert "Post_Type::BRIEFING_POST_TYPE" in source
    assert re.search(
        r"register_taxonomy\(\s*self::PUBLISHER_TAXONOMY,\s*\[.*?Post_Type::SIGNAL_POST_TYPE.*?Post_Type::BRIEFING_POST_TYPE",
        source,
        re.DOTALL,
    )


def test_cross_report_publish_defaults_to_briefing_route() -> None:
    generator_source = GENERATOR_PATH.read_text(encoding="utf-8")
    contract_source = CROSS_REPORT_REQUEST_CONTRACT_PATH.read_text(encoding="utf-8")
    readme_source = README_PATH.read_text(encoding="utf-8")

    assert 'target_route: str = "wordpress:ml_briefing"' in generator_source
    assert 'default="wordpress:ml_briefing"' in contract_source
    assert "`wordpress:ml_briefing`" in readme_source
