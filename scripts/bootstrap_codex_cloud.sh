#!/usr/bin/env bash
set -euo pipefail

readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PYTHON_BIN="${PYTHON_BIN:-python3.12}"
readonly VENV_DIR="${CODEX_CLOUD_VENV_DIR:-${REPOSITORY_ROOT}/.venv}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  printf 'Python 3.12 is required; %s was not found.\n' "${PYTHON_BIN}" >&2
  exit 1
fi

if [[ "$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != "3.12" ]]; then
  printf 'Python 3.12 is required; %s reports a different version.\n' "${PYTHON_BIN}" >&2
  exit 1
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --require-hashes \
  -r "${REPOSITORY_ROOT}/requirements.lock"
"${VENV_DIR}/bin/python" -m pip check

printf 'Codex Cloud environment ready: %s\n' "${VENV_DIR}/bin/python"
