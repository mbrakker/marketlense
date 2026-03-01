#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WP_CLI_BIN="${WP_CLI_BIN:-wp}"
WP_CLI_FLAGS="${WP_CLI_FLAGS:-}"
WP_PATH="${WP_PATH:-}"
PUBLISHER_MAP_PATH="${PUBLISHER_MAP_PATH:-$ROOT_DIR/config/publisher-homepages.json}"
META_KEY="ml_publisher_homepage"
TAXONOMY="ml_publisher"
REST_SCRIPT="$ROOT_DIR/scripts/seed-publisher-homepages-rest.py"
read -r -a WP_CLI_FLAGS_ARR <<< "$WP_CLI_FLAGS"

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
  echo "Python is required to parse $PUBLISHER_MAP_PATH." >&2
  exit 1
}

run_python() {
  local python_cmd="$1"
  shift

  if [[ "$python_cmd" == "py -3" ]]; then
    py -3 "$@"
    return
  fi

  "$python_cmd" "$@"
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
  echo "wp-cli unavailable for local WordPress core; switching to REST fallback seeding." >&2
  PUBLISHER_MAP_PATH="$PUBLISHER_MAP_PATH" run_python "$python_cmd" "$REST_SCRIPT"
}

normalize_rows() {
  local python_cmd="$1"
  run_python "$python_cmd" - "$PUBLISHER_MAP_PATH" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
publishers = payload.get("publishers", [])
for item in publishers:
    name = str(item.get("name", "")).strip()
    homepage = str(item.get("homepage", "")).strip()
    if not name:
        continue
    if homepage and "://" not in homepage:
        homepage = f"https://{homepage}"
    print(f"{name}|{homepage}")
PY
}

find_term_id_by_name() {
  local term_name="$1"
  wp_cli term list "$TAXONOMY" --format=csv --fields=term_id,name \
    | awk -F, -v wanted="$term_name" 'NR > 1 && $2 == wanted { print $1; exit }'
}

main() {
  if [[ ! -f "$PUBLISHER_MAP_PATH" ]]; then
    echo "Publisher mapping file does not exist: $PUBLISHER_MAP_PATH" >&2
    exit 1
  fi

  if ! wp_cli_ready; then
    run_rest_fallback
    return
  fi

  local python_cmd
  python_cmd="$(resolve_python_bin)"

  local row
  local name
  local homepage
  local term_id
  while IFS= read -r row; do
    [[ -z "$row" ]] && continue
    IFS='|' read -r name homepage <<< "$row"
    [[ -z "$name" ]] && continue

    term_id="$(find_term_id_by_name "$name")"
    if [[ -z "$term_id" ]]; then
      term_id="$(wp_cli term create "$TAXONOMY" "$name" --porcelain)"
      echo "Created publisher term: $name -> ID $term_id"
    else
      echo "Using publisher term: $name -> ID $term_id"
    fi

    if [[ -n "$homepage" ]]; then
      wp_cli term meta update "$term_id" "$META_KEY" "$homepage" >/dev/null
      echo "Set homepage: $name -> $homepage"
    else
      wp_cli term meta delete "$term_id" "$META_KEY" >/dev/null || true
      echo "Cleared homepage: $name"
    fi
  done < <(normalize_rows "$python_cmd")

  echo "Publisher homepage seeding complete."
}

main "$@"
