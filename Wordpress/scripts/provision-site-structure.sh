#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WP_CLI_BIN="${WP_CLI_BIN:-wp}"
WP_CLI_FLAGS="${WP_CLI_FLAGS:-}"
read -r -a WP_CLI_FLAGS_ARR <<< "$WP_CLI_FLAGS"
REST_SCRIPT="$ROOT_DIR/scripts/provision-site-structure-rest.py"

wp_cli() {
  "$WP_CLI_BIN" "${WP_CLI_FLAGS_ARR[@]}" "$@"
}

resolve_python_bin() {
  if command -v python >/dev/null 2>&1; then
    printf "%s" "python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf "%s" "python3"
    return
  fi
  if command -v py >/dev/null 2>&1; then
    printf "%s" "py -3"
    return
  fi
  echo "Python is required for REST fallback provisioning." >&2
  exit 1
}

wp_cli_available() {
  if [[ "$WP_CLI_BIN" == */* ]]; then
    [[ -x "$WP_CLI_BIN" ]]
    return
  fi
  command -v "$WP_CLI_BIN" >/dev/null 2>&1
}

wp_cli_ready() {
  if ! wp_cli_available; then
    return 1
  fi
  wp_cli core is-installed >/dev/null 2>&1
}

run_rest_fallback() {
  if [[ ! -f "$REST_SCRIPT" ]]; then
    echo "REST fallback script missing: $REST_SCRIPT" >&2
    exit 1
  fi

  local python_cmd
  python_cmd="$(resolve_python_bin)"
  echo "wp-cli unavailable for local WordPress core; switching to REST fallback provisioning." >&2
  eval "$python_cmd" "\"$REST_SCRIPT\""
}

ensure_page() {
  local title="$1"
  local slug="$2"
  local page_id

  page_id="$(wp_cli post list \
    --post_type=page \
    --name="$slug" \
    --posts_per_page=1 \
    --post_status=publish,draft,pending,private \
    --field=ID | head -n 1 || true)"

  if [[ -z "$page_id" ]]; then
    page_id="$(wp_cli post create \
      --post_type=page \
      --post_status=publish \
      --post_title="$title" \
      --post_name="$slug" \
      --post_content="" \
      --porcelain)"
    echo "Created page: $title ($slug) -> ID $page_id" >&2
  else
    wp_cli post update "$page_id" \
      --post_status=publish \
      --post_title="$title" \
      --post_name="$slug" >/dev/null
    echo "Updated page: $title ($slug) -> ID $page_id" >&2
  fi

  printf "%s" "$page_id"
}

ensure_menu() {
  local menu_name="$1"
  local menu_slug="$2"
  local menu_id

  menu_id="$(
    wp_cli menu list --format=csv --fields=term_id,slug \
      | awk -F, -v slug="$menu_slug" 'NR > 1 && $2 == slug { print $1; exit }'
  )"

  if [[ -z "$menu_id" ]]; then
    menu_id="$(wp_cli menu create "$menu_name" --porcelain)"
    echo "Created menu: $menu_name -> ID $menu_id" >&2
  else
    echo "Using menu: $menu_name -> ID $menu_id" >&2
  fi

  printf "%s" "$menu_id"
}

clear_menu_items() {
  local menu_id="$1"
  local existing_ids

  existing_ids="$(wp_cli menu item list "$menu_id" --format=ids || true)"
  if [[ -z "$existing_ids" ]]; then
    return
  fi

  for item_id in $existing_ids; do
    wp_cli menu item delete "$item_id" --force >/dev/null
  done
}

menu_location_exists() {
  local location="$1"
  wp_cli menu location list --format=csv --fields=location \
    | awk -F, -v wanted="$location" 'NR > 1 && $1 == wanted { found = 1 } END { exit(found ? 0 : 1) }'
}

assign_menu_location_if_available() {
  local menu_id="$1"
  local location="$2"

  if menu_location_exists "$location"; then
    wp_cli menu location assign "$menu_id" "$location" >/dev/null
    echo "Assigned menu $menu_id to location '$location'."
    return
  fi

  echo "Menu location '$location' is not registered; skipped assignment."
}

add_menu_pages_in_order() {
  local menu_id="$1"
  shift
  local page_id

  for page_id in "$@"; do
    wp_cli menu item add-post "$menu_id" "$page_id" >/dev/null
  done
}

main() {
  if ! wp_cli_ready; then
    run_rest_fallback
    return
  fi

  declare -a pages=(
    "About|about"
    "Methodology|methodology"
    "Topics directory|topics-directory"
    "Publishers directory|publishers-directory"
    "Submit a Report|submit-a-report"
    "Contact|contact"
    "Privacy|privacy"
    "Terms|terms"
  )

  declare -A page_ids=()

  local title
  local slug
  local page_id
  for page_spec in "${pages[@]}"; do
    IFS='|' read -r title slug <<< "$page_spec"
    page_id="$(ensure_page "$title" "$slug")"
    page_ids["$slug"]="$page_id"
  done

  local primary_menu_id
  primary_menu_id="$(ensure_menu "Market Lense Primary" "market-lense-primary")"
  clear_menu_items "$primary_menu_id"
  wp_cli menu item add-custom "$primary_menu_id" "Reports" "/reports/" >/dev/null
  add_menu_pages_in_order "$primary_menu_id" \
    "${page_ids[topics-directory]}" \
    "${page_ids[publishers-directory]}" \
    "${page_ids[methodology]}" \
    "${page_ids[about]}" \
    "${page_ids[submit-a-report]}" \
    "${page_ids[contact]}"
  assign_menu_location_if_available "$primary_menu_id" "primary"

  local footer_menu_id
  footer_menu_id="$(ensure_menu "Market Lense Footer" "market-lense-footer")"
  clear_menu_items "$footer_menu_id"
  add_menu_pages_in_order "$footer_menu_id" \
    "${page_ids[privacy]}" \
    "${page_ids[terms]}" \
    "${page_ids[contact]}"
  assign_menu_location_if_available "$footer_menu_id" "footer"

  echo "Provisioning complete."
}

main "$@"
