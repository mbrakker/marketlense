#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WP_CLI_BIN="${WP_CLI_BIN:-wp}"
WP_CLI_FLAGS="${WP_CLI_FLAGS:-}"
WP_PATH="${WP_PATH:-}"
read -r -a WP_CLI_FLAGS_ARR <<< "$WP_CLI_FLAGS"
REST_SCRIPT="$ROOT_DIR/scripts/provision-site-structure-rest.py"

is_windows_bridge_available() {
  command -v cmd.exe >/dev/null 2>&1
}

_cmd_quote() {
  local value="$1"
  value="${value//^/^^}"
  value="${value//&/^&}"
  value="${value//|/^|}"
  value="${value//</^<}"
  value="${value//>/^>}"
  printf '"%s"' "$value"
}

wp_cli_windows() {
  local args=("$WP_CLI_BIN")
  if [[ -n "$WP_PATH" ]]; then
    args+=("--path=$WP_PATH")
  fi
  args+=("${WP_CLI_FLAGS_ARR[@]}" "$@")
  local command_str=""
  local item
  for item in "${args[@]}"; do
    if [[ -n "$command_str" ]]; then
      command_str+=" "
    fi
    command_str+="$(_cmd_quote "$item")"
  done
  cmd.exe /d /s /c "$command_str"
}

wp_cli() {
  if command -v "$WP_CLI_BIN" >/dev/null 2>&1; then
    if [[ -n "$WP_PATH" ]]; then
      "$WP_CLI_BIN" "--path=$WP_PATH" "${WP_CLI_FLAGS_ARR[@]}" "$@"
    else
      "$WP_CLI_BIN" "${WP_CLI_FLAGS_ARR[@]}" "$@"
    fi
    return
  fi
  if is_windows_bridge_available; then
    wp_cli_windows "$@"
    return
  fi
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
    [[ -x "$WP_CLI_BIN" || -f "$WP_CLI_BIN" ]]
    return
  fi
  if command -v "$WP_CLI_BIN" >/dev/null 2>&1; then
    return 0
  fi
  if is_windows_bridge_available; then
    cmd.exe /d /s /c "where $WP_CLI_BIN" >/dev/null 2>&1
    return $?
  fi
  return 1
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
  echo "wp-cli unavailable for direct WordPress access; switching to REST fallback provisioning." >&2
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

  local title
  local slug
  local page_id
  for page_spec in "${pages[@]}"; do
    IFS='|' read -r title slug <<< "$page_spec"
    page_id="$(ensure_page "$title" "$slug")"
  done

  echo "Provisioning complete."
}

main "$@"
