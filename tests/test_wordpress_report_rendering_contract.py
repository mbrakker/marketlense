from __future__ import annotations

from collections import Counter
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME_CSS = ROOT / "Wordpress/wp-content/themes/marketlense/assets/css/theme.css"
PLUGIN_BOOTSTRAP = (
    ROOT / "Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-plugin.php"
)
PLUGIN_MAIN = ROOT / "Wordpress/wp-content/plugins/marketlense-core/marketlense-core.php"
PLUGIN_FORMATTING = (
    ROOT
    / "Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-content-formatting.php"
)
REPORT_CSS_TEMPLATE = ROOT / "templates/report.css.j2"


def _parity_css(theme_css: str) -> str:
    start_marker = "/* BEGIN current ingest report parity */"
    end_marker = "/* END current ingest report parity */"
    assert theme_css.count(start_marker) == 1
    assert theme_css.count(end_marker) == 1
    return theme_css.split(start_marker, 1)[1].split(end_marker, 1)[0]


def _declarations(css: str) -> Counter[str]:
    declarations: Counter[str] = Counter()
    block_stack: list[list[str]] = []
    current: list[str] = []

    for character in re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL):
        if character == "{":
            block_stack.append(current)
            current = []
            continue
        if character == "}":
            block = "".join(current)
            for declaration in block.split(";"):
                normalized = re.sub(r"\s+", " ", declaration).strip()
                if re.match(r"^(?:--[\w-]+|[a-zA-Z-]+)\s*:", normalized):
                    declarations[normalized] += 1
            current = block_stack.pop() if block_stack else []
            continue
        current.append(character)

    return declarations


def test_theme_scopes_current_report_template_classes_for_wordpress_ingest() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")
    parity_css = _parity_css(css)

    required_selectors = [
        ".ml-ingest-report-content .report-document",
        ".ml-ingest-report-content .hero-inner",
        ".ml-ingest-report-content .summary-panel",
        ".ml-ingest-report-content .finding-card",
        ".ml-ingest-report-content .quote-board",
        ".ml-ingest-report-content .source-layout",
        ".ml-ingest-report-content .download-card",
    ]

    for selector in required_selectors:
        assert selector in parity_css

    assert "@layer" not in parity_css
    assert "@scope (.ml-ingest-report-content) to (.report-document)" in css
    assert _declarations(parity_css) == _declarations(
        REPORT_CSS_TEMPLATE.read_text(encoding="utf-8")
    )


def test_wordpress_plugin_preserves_ingested_report_html_without_wpautop() -> None:
    plugin_main = PLUGIN_MAIN.read_text(encoding="utf-8")
    bootstrap = PLUGIN_BOOTSTRAP.read_text(encoding="utf-8")
    formatting = PLUGIN_FORMATTING.read_text(encoding="utf-8")

    assert "class-marketlense-core-content-formatting.php" in plugin_main
    assert "Content_Formatting" in bootstrap
    assert re.search(r"remove_filter\(\s*'the_content'\s*,\s*'wpautop'", formatting)
    assert "Post_Type::report_post_types()" in formatting


def test_wordpress_plugin_emits_public_seo_and_social_metadata() -> None:
    plugin_source = PLUGIN_BOOTSTRAP.read_text(encoding="utf-8")
    main_source = PLUGIN_MAIN.read_text(encoding="utf-8")

    assert "Version: 1.6.9" in main_source
    assert "add_action('wp_head', [self::class, 'render_public_metadata'], 1)" in plugin_source
    assert 'meta name="description"' in plugin_source
    assert 'rel="canonical"' in plugin_source
    assert 'property="og:title"' in plugin_source
    assert 'name="twitter:card"' in plugin_source
    assert "post_public_description" in plugin_source
