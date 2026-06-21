#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THEME_SLUG="marketlense"
THEME_DIR="$ROOT_DIR/wp-content/themes/$THEME_SLUG"
PLUGIN_SLUG="marketlense-core"
WP_CLI_BIN="${WP_CLI_BIN:-wp}"
WP_CLI_FLAGS="${WP_CLI_FLAGS:-}"
WP_PATH="${WP_PATH:-}"
PROVISION_STRUCTURE="${PROVISION_STRUCTURE:-1}"
SEED_PUBLISHERS="${SEED_PUBLISHERS:-1}"
read -r -a WP_CLI_FLAGS_ARR <<< "$WP_CLI_FLAGS"

wp_cli() {
  local args=("$WP_CLI_BIN")
  if [[ -n "$WP_PATH" ]]; then
    args+=("--path=$WP_PATH")
  fi
  args+=("${WP_CLI_FLAGS_ARR[@]}" "$@")
  "${args[@]}"
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

require_php_true() {
  local php_expr="$1"
  local check_name="$2"
  local result
  result="$(wp_cli eval "$php_expr" | tr -d '[:space:]')"
  if [[ "$result" != "1" ]]; then
    echo "$check_name failed: expected truthy php expression, got '$result'" >&2
    exit 1
  fi
  echo "$check_name passed."
}

require_php_false() {
  local php_expr="$1"
  local check_name="$2"
  local result
  result="$(wp_cli eval "$php_expr" | tr -d '[:space:]')"
  if [[ "$result" != "0" ]]; then
    echo "$check_name failed: expected falsy php expression, got '$result'" >&2
    exit 1
  fi
  echo "$check_name passed."
}

require_file_sequence() {
  local file_path="$1"
  shift
  local previous_pos=-1
  local token
  local token_pos

  if [[ ! -f "$file_path" ]]; then
    echo "File not found for sequence check: $file_path" >&2
    exit 1
  fi

  for token in "$@"; do
    token_pos="$(grep -b -F -o "$token" "$file_path" | head -n 1 | cut -d: -f1 || true)"
    if [[ -z "$token_pos" ]]; then
      echo "Sequence check failed: token '$token' not found in $file_path" >&2
      exit 1
    fi
    if (( token_pos <= previous_pos )); then
      echo "Sequence check failed: token '$token' appears out of order in $file_path" >&2
      exit 1
    fi
    previous_pos="$token_pos"
  done

  echo "Sequence check passed for $file_path."
}

ensure_term() {
  local taxonomy="$1"
  local name="$2"
  local slug="$3"
  local term_id
  term_id="$(wp_cli eval " \$term = get_term_by('slug', '${slug}', '${taxonomy}'); echo (\$term instanceof WP_Term) ? (string) \$term->term_id : ''; " | tr -d '[:space:]')"
  if [[ -z "$term_id" ]]; then
    term_id="$(wp_cli term create "$taxonomy" "$name" --slug="$slug" --porcelain)"
  fi
  printf "%s" "$term_id"
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

if [[ "$PROVISION_STRUCTURE" == "1" ]] && [[ -f "$ROOT_DIR/scripts/provision-site-structure.sh" ]]; then
  echo "Running site structure provisioning..."
  bash "$ROOT_DIR/scripts/provision-site-structure.sh"
fi

if [[ "$SEED_PUBLISHERS" == "1" ]] && [[ -f "$ROOT_DIR/scripts/seed-publisher-homepages.sh" ]]; then
  echo "Running publisher homepage seeding..."
  bash "$ROOT_DIR/scripts/seed-publisher-homepages.sh"
fi

echo "Checking required templates in theme source..."
required_templates=(
  "index.html"
  "front-page.html"
  "single-ml_report.html"
  "archive-ml_report.html"
  "page-signals.html"
  "page-briefings.html"
  "single-ml_signal.html"
  "archive-ml_signal.html"
  "single-ml_briefing.html"
  "archive-ml_briefing.html"
  "taxonomy-ml_publisher.html"
  "page-about.html"
  "page-methodology.html"
  "page-topics-directory.html"
  "page-publishers-directory.html"
  "page-submit-a-report.html"
  "page-contact.html"
  "page-privacy.html"
  "page-terms.html"
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
require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( rest_url('wp/v2/types/ml_report') ) );" "REST type ml_report"
require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( rest_url('wp/v2/types/ml_signal') ) );" "REST type ml_signal"
require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( rest_url('wp/v2/types/ml_briefing') ) );" "REST type ml_briefing"
require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( rest_url('wp/v2/taxonomies/ml_publisher') ) );" "REST taxonomy ml_publisher"

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

echo "Ensuring taxonomy terms exist for filter checks..."
topic_id="$(ensure_term "category" "Smoke Topic" "smoke-topic")"
publisher_id="$(ensure_term "ml_publisher" "Smoke Publisher" "smoke-publisher")"
wp_cli term meta update "$publisher_id" ml_publisher_homepage "https://example.com" >/dev/null
wp_cli post term set "$report_id" category "$topic_id" >/dev/null
wp_cli post term set "$report_id" ml_publisher "$publisher_id" >/dev/null

require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( get_permalink(${report_id}) ) );" "Single ml_report request"
require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( get_post_type_archive_link('ml_report') ) );" "Reports archive request"
require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( add_query_arg(array('category' => 'smoke-topic'), get_post_type_archive_link('ml_report')) ) );" "Reports topic filter request"
require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( add_query_arg(array('ml_publisher' => 'smoke-publisher'), get_post_type_archive_link('ml_report')) ) );" "Reports publisher filter request"
require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( add_query_arg(array('category' => 'smoke-topic', 'ml_publisher' => 'smoke-publisher'), get_post_type_archive_link('ml_report')) ) );" "Reports combined filter request"
require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( get_post_type_archive_link('ml_signal') ) );" "Signals archive request"
require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( get_post_type_archive_link('ml_briefing') ) );" "Briefings archive request"

required_pages=(
  "about"
  "methodology"
  "topics-directory"
  "signals"
  "briefings"
  "publishers-directory"
  "submit-a-report"
  "contact"
  "privacy"
  "terms"
)

for page_slug in "${required_pages[@]}"; do
  require_http_200 "echo wp_remote_retrieve_response_code( wp_remote_get( home_url('/${page_slug}/') ) );" "Page /${page_slug}/ request"
done

require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(get_post_type_archive_link('ml_report'))), 'ml-report-filter-form') !== false ? '1' : '0';" "Browse reports filter UI rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/topics-directory/'))), 'ml-directory-list') !== false ? '1' : '0';" "Topics directory shortcode rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/signals/'))), 'ml-archive-browser-page') !== false ? '1' : '0';" "Signals shared archive browser rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/signals/'))), 'ml-report-filter-form') !== false ? '1' : '0';" "Signals archive filter UI rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/signals/'))), 'ml-report-browser-summary-value') !== false ? '1' : '0';" "Signals archive count rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/briefings/'))), 'ml-archive-browser-page') !== false ? '1' : '0';" "Briefings shared archive browser rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/briefings/'))), 'ml-report-filter-form') !== false ? '1' : '0';" "Briefings archive filter UI rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/briefings/'))), 'ml-report-browser-summary-value') !== false ? '1' : '0';" "Briefings archive count rendered"
require_php_true "echo strpos((string) do_shortcode('[ml_featured_briefing]'), 'ml-featured-briefing') !== false ? '1' : '0';" "Featured Briefing shortcode rendered"
require_php_true "echo strpos((string) do_shortcode('[ml_briefings_index per_page=\"12\"]'), 'ml-entity-archive') !== false ? '1' : '0';" "Briefings index shortcode rendered"
require_php_true "echo strpos((string) do_shortcode('[ml_signals_index per_page=\"12\"]'), 'ml-entity-archive') !== false ? '1' : '0';" "Signals index shortcode rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/publishers-directory/'))), 'Publisher homepage') !== false ? '1' : '0';" "Publishers directory homepage CTA rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/'))), '/reports/') !== false ? '1' : '0';" "Navigation includes reports link"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/'))), '/topics-directory/') !== false ? '1' : '0';" "Navigation includes topics link"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/'))), '/signals/') !== false ? '1' : '0';" "Navigation includes signals link"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/'))), '/briefings/') !== false ? '1' : '0';" "Navigation includes briefings link"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/'))), '/publishers-directory/') !== false ? '1' : '0';" "Navigation includes publishers link"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/'))), 'Request briefing') !== false ? '1' : '0';" "Front page includes briefing CTA"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/'))), 'Featured Digest') !== false ? '1' : '0';" "Front page includes featured digest section"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/'))), 'This Week in Intelligence') !== false ? '1' : '0';" "Front page includes signals section"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/'))), 'Weekly Executive Intelligence Briefing') !== false ? '1' : '0';" "Front page includes executive briefing section"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/'))), 'Search the archive') !== false ? '1' : '0';" "Front page includes header search"
require_php_false "echo preg_match('/\\[ml_[a-z0-9_\\-]+(?:\\s[^\\]]*)?\\]/', (string) wp_remote_retrieve_body(wp_remote_get(home_url('/')))) ? '1' : '0';" "Front page does not leak raw Market Lense shortcodes"
require_php_false "echo preg_match('/\\[ml_[a-z0-9_\\-]+(?:\\s[^\\]]*)?\\]/', (string) wp_remote_retrieve_body(wp_remote_get(get_post_type_archive_link('ml_report')))) ? '1' : '0';" "Reports archive does not leak raw Market Lense shortcodes"

echo "Smoke test passed."
