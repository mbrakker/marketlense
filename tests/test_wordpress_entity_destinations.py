from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "Wordpress" / "wp-content" / "plugins" / "marketlense-core"
THEME_TEMPLATES = REPO_ROOT / "Wordpress" / "wp-content" / "themes" / "marketlense" / "templates"
POST_TYPE_PATH = PLUGIN_ROOT / "includes" / "class-marketlense-core-post-type.php"
SHORTCODES_PATH = PLUGIN_ROOT / "includes" / "class-marketlense-core-shortcodes.php"
README_PATH = REPO_ROOT / "README.md"
GENERATOR_PATH = REPO_ROOT / "src" / "generators" / "cross_report_analysis_generator.py"
CONTRACT_PATH = REPO_ROOT / "src" / "contracts" / "cross_report_analysis.py"


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


def test_wordpress_templates_render_signal_and_briefing_archive_and_detail_surfaces() -> None:
    expected_templates = {
        "page-signals.html": "[ml_signal_archive",
        "page-briefings.html": "[ml_briefing_archive",
        "archive-ml_signal.html": "[ml_signal_archive",
        "archive-ml_briefing.html": "[ml_briefing_archive",
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


def test_cross_report_publish_defaults_to_briefing_route() -> None:
    generator_source = GENERATOR_PATH.read_text(encoding="utf-8")
    contract_source = CONTRACT_PATH.read_text(encoding="utf-8")
    readme_source = README_PATH.read_text(encoding="utf-8")

    assert 'target_route: str = "wordpress:ml_briefing"' in generator_source
    assert 'default="wordpress:ml_briefing"' in contract_source
    assert "`wordpress:ml_briefing`" in readme_source
