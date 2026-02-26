#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THEME_SLUG="marketlense"
THEME_DIR="$ROOT_DIR/wp-content/themes/$THEME_SLUG"
PLUGIN_SLUG="marketlense-core"
WP_CLI_BIN="${WP_CLI_BIN:-wp}"
WP_CLI_FLAGS="${WP_CLI_FLAGS:-}"
read -r -a WP_CLI_FLAGS_ARR <<< "$WP_CLI_FLAGS"

wp_cli() {
  "$WP_CLI_BIN" "${WP_CLI_FLAGS_ARR[@]}" "$@"
}

require_http_200() {
  local php_expr="$1"
  local check_name="$2"
  local status
  status="$(wp_cli eval "$php_expr" | tr -d '[:space:]')"
  if [[ "$status" != "200" ]]; then
    echo "$check_name failed: expected HTTP 200, got '$status'" >&2
    exit 1
  fi
  echo "$check_name passed (HTTP 200)."
}

if ! command -v "$WP_CLI_BIN" >/dev/null 2>&1; then
  echo "wp-cli is not available; skipping smoke test."
  exit 0
fi

if [[ ! -d "$THEME_DIR" ]]; then
  echo "Theme directory missing: $THEME_DIR" >&2
  exit 1
fi

echo "Checking theme installation..."
wp_cli theme is-installed "$THEME_SLUG" >/dev/null
echo "Checking plugin installation..."
if wp_cli plugin is-installed "$PLUGIN_SLUG" >/dev/null 2>&1; then
  wp_cli plugin activate "$PLUGIN_SLUG" >/dev/null
  echo "Plugin '$PLUGIN_SLUG' activated."
else
  echo "Plugin '$PLUGIN_SLUG' is not installed in this WordPress environment." >&2
  echo "Install it first (Plugins -> Add New -> Upload Plugin)." >&2
  exit 1
fi
echo "Activating theme..."
wp_cli theme activate "$THEME_SLUG" >/dev/null

echo "Checking required templates in theme source..."
required_templates=(
  "index.html"
  "front-page.html"
  "single-ml_report.html"
  "archive-ml_report.html"
  "taxonomy-ml_topic.html"
  "taxonomy-ml_publisher.html"
  "search.html"
  "page.html"
  "404.html"
)

for template in "${required_templates[@]}"; do
  if [[ ! -f "$THEME_DIR/templates/$template" ]]; then
    echo "Missing template: $THEME_DIR/templates/$template" >&2
    exit 1
  fi
done
echo "Template presence checks passed."

require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( home_url('/') ) );" "Front page request"

echo "Checking ml_report post type..."
post_type_exists="$(wp_cli eval "echo post_type_exists('ml_report') ? '1' : '0';" | tr -d '[:space:]')"
if [[ "$post_type_exists" != "1" ]]; then
  echo "Post type 'ml_report' is not registered after plugin activation." >&2
  exit 1
fi

report_id="$(wp_cli post list --post_type=ml_report --post_status=publish --posts_per_page=1 --field=ID | head -n 1 || true)"
if [[ -z "$report_id" ]]; then
  echo "No published ml_report found; creating seed post for smoke test..."
  report_id="$(wp_cli post create \
    --post_type=ml_report \
    --post_status=publish \
    --post_title="Smoke Test Report" \
    --post_name="smoke-test-report" \
    --post_content="<article id='digest-content'><section class='panel' id='section-summary' data-section><h2>TL;DR</h2><p>Smoke test report content for Market Lense theme validation.</p></section></article>" \
    --porcelain)"
fi

if [[ -z "$report_id" ]]; then
  echo "Unable to resolve a report ID for ml_report smoke validation." >&2
  exit 1
fi

require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( get_permalink(${report_id}) ) );" "Single ml_report request"

echo "Smoke test passed."
