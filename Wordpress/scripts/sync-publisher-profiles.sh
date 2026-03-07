#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REST_SCRIPT="$ROOT_DIR/scripts/sync-publisher-profiles-rest.py"

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
  echo "Python is required to run publisher profile sync." >&2
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

main() {
  if [[ ! -f "$REST_SCRIPT" ]]; then
    echo "Publisher profile sync script missing: $REST_SCRIPT" >&2
    exit 1
  fi

  local python_cmd
  python_cmd="$(resolve_python_bin)"
  run_python "$python_cmd" "$REST_SCRIPT"
}

main "$@"
