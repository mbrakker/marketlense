from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "Wordpress" / "wp-content" / "plugins" / "marketlense-core"
BOUNDARY = PLUGIN / "includes" / "class-marketlense-core-public-render-boundary.php"
SHORTCODES = PLUGIN / "includes" / "class-marketlense-core-shortcodes.php"
BOOTSTRAP = PLUGIN / "marketlense-core.php"
PLUGIN_BOOTSTRAP = PLUGIN / "includes" / "class-marketlense-core-plugin.php"
TAXONOMIES = PLUGIN / "includes" / "class-marketlense-core-taxonomies.php"
HARNESS = ROOT / "tests" / "wordpress_runtime" / "report_card_renderer_harness.php"


def _render_boundary(
    *, shortcode: str, route: str, throw: bool, html: str = ""
) -> dict[str, object]:
    php = shutil.which("php")
    if php is None:
        pytest.skip("PHP CLI is required for the WordPress runtime harness.")
    completed = subprocess.run(
        [php, str(HARNESS)],
        input=json.dumps(
            {
                "mode": "public_boundary",
                "shortcode": shortcode,
                "route": route,
                "throw": throw,
                "html": html,
                "message": r"Fatal error in C:\private\plugin.php on line 99",
            }
        ),
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


@pytest.mark.parametrize(
    ("shortcode", "route", "entity_type"),
    (
        ("ml_report_browser", "/reports/", "report"),
        ("ml_publisher_profile", "/publisher/not-extracted/", "publisher"),
        ("ml_signals_index", "/signals/", "archive"),
        ("ml_button_link", "/about/", "shortcode"),
    ),
)
def test_public_render_failures_are_branded_logged_and_path_safe(
    shortcode: str, route: str, entity_type: str
) -> None:
    result = _render_boundary(shortcode=shortcode, route=route, throw=True)
    html = str(result["html"])
    events = result["events"]

    assert result["status"] == 500
    assert 'data-marketlense-safe-error' in html
    assert "Market Bearing" in html
    assert re.search(r"ML-[a-f0-9-]{36}", html, flags=re.IGNORECASE)
    assert not re.search(
        r"Fatal error|Stack trace|C:\\\\private|plugin\.php on line",
        html,
        flags=re.IGNORECASE,
    )
    assert isinstance(events, list) and len(events) == 1
    event = events[0]
    assert isinstance(event, dict)
    assert event["event"] == "marketlense_public_render_failure"
    assert event["severity"] == "error"
    assert event["route"] == route
    assert event["entity_type"] == entity_type
    assert event["correlation_id"] in html
    assert event["exception_type"] == "RuntimeException"
    assert "C:\\private\\plugin.php" in event["exception_message"]
    assert event["run_id"] == event["correlation_id"]
    assert event["task_id"] == shortcode
    assert event["span_id"] == event["correlation_id"]
    assert event["role"] == "public_render_boundary"


def test_normal_shortcode_output_is_unchanged_and_does_not_log() -> None:
    result = _render_boundary(
        shortcode="ml_report_browser",
        route="/reports/",
        throw=False,
        html='<section class="ml-report-browser">Normal report output</section>',
    )

    assert result == {
        "html": '<section class="ml-report-browser">Normal report output</section>',
        "status": None,
        "events": [],
    }


def test_shortcode_registration_uses_the_single_public_render_boundary() -> None:
    source = SHORTCODES.read_text(encoding="utf-8")

    assert "private Public_Render_Boundary $public_render_boundary;" in source
    assert "$this->public_render_boundary = new Public_Render_Boundary();" in source
    assert "$this->public_render_boundary->render_shortcode(" in source
    assert "fn (): string => (string) $this->{$method}($attrs)" in source
    assert "add_shortcode($tag, [$this, $method]);" not in source
    assert "class-marketlense-core-public-render-boundary.php" in BOOTSTRAP.read_text(
        encoding="utf-8"
    )


def test_safe_markup_and_smoke_patterns_reject_common_public_diagnostic_signatures() -> None:
    boundary_source = BOUNDARY.read_text(encoding="utf-8")
    smoke_source = (ROOT / "Wordpress" / "scripts" / "smoke-test.sh").read_text(
        encoding="utf-8"
    )

    assert "exception_file" in boundary_source
    assert "exception_trace" in boundary_source
    assert "exception_message" not in boundary_source.split("private function safe_markup", 1)[1]
    for signature in ("Fatal error", "Uncaught", "Stack trace", "thrown in"):
        assert signature in smoke_source


def test_unextracted_publisher_projection_uses_the_existing_branded_404_path() -> None:
    taxonomy_source = TAXONOMIES.read_text(encoding="utf-8")
    plugin_source = PLUGIN_BOOTSTRAP.read_text(encoding="utf-8")

    assert "private const UNEXTRACTED_PUBLISHER_SLUGS = ['not-extracted'];" in taxonomy_source
    assert "public function render_not_found_for_unextracted_publisher(): void" in taxonomy_source
    assert "$wp_query->set_404();" in taxonomy_source
    assert "status_header(404);" in taxonomy_source
    assert "render_not_found_for_unextracted_publisher" in plugin_source
