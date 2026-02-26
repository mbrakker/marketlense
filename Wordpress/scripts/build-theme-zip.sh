#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THEME_SLUG="marketlense"
THEME_DIR="$ROOT_DIR/wp-content/themes/$THEME_SLUG"
DIST_DIR="$ROOT_DIR/dist"
ZIP_PATH="$DIST_DIR/$THEME_SLUG.zip"
REPO_ROOT="$(cd "$ROOT_DIR/.." && pwd)"

if [[ ! -d "$THEME_DIR" ]]; then
  echo "Theme directory not found: $THEME_DIR" >&2
  exit 1
fi

mkdir -p "$DIST_DIR"
rm -f "$ZIP_PATH"

PYTHON_BIN=""
PYTHON_ARGS=()

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v py >/dev/null 2>&1; then
  if py -3 -c "import sys" >/dev/null 2>&1; then
    PYTHON_BIN="py"
    PYTHON_ARGS=(-3)
  elif py -c "import sys" >/dev/null 2>&1; then
    PYTHON_BIN="py"
  fi
fi

if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in \
    "$REPO_ROOT/.venv/Scripts/python.exe" \
    "$REPO_ROOT/.venv/bin/python" \
    "$ROOT_DIR/.venv/Scripts/python.exe" \
    "$ROOT_DIR/.venv/bin/python"
  do
    if [[ -x "$candidate" ]]; then
      PYTHON_BIN="$candidate"
      PYTHON_ARGS=()
      break
    fi
  done
fi

if command -v zip >/dev/null 2>&1; then
  (
    cd "$ROOT_DIR/wp-content/themes"
    zip -r "$ZIP_PATH" "$THEME_SLUG" \
      -x "*/.git/*" \
      -x "*/.github/*" \
      -x "*/node_modules/*" \
      -x "*/tests/*" \
      -x "*/test/*" \
      -x "*/.DS_Store" \
      -x "*/Thumbs.db" \
      -x "*/.env" \
      -x "*/.env.*" \
      -x "*/dist/*" \
      -x "*/coverage/*" \
      -x "*/__pycache__/*" \
      -x "*/.pytest_cache/*"
  )
elif [[ -n "$PYTHON_BIN" ]]; then
  "$PYTHON_BIN" "${PYTHON_ARGS[@]}" - "$THEME_DIR" "$ZIP_PATH" "$THEME_SLUG" <<'PY'
import os
import sys
import zipfile

theme_dir = os.path.abspath(sys.argv[1])
zip_path = os.path.abspath(sys.argv[2])
slug = sys.argv[3]
root_parent = os.path.dirname(theme_dir)

exclude_dirs = {
    ".git",
    ".github",
    "node_modules",
    "tests",
    "test",
    "dist",
    "coverage",
    "__pycache__",
    ".pytest_cache",
}
exclude_files = {".DS_Store", "Thumbs.db", ".env"}

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for root, dirs, files in os.walk(theme_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for filename in files:
            if filename in exclude_files or filename.startswith(".env."):
                continue
            abs_path = os.path.join(root, filename)
            rel_path = os.path.relpath(abs_path, root_parent).replace(os.sep, "/")
            if any(part in exclude_dirs for part in rel_path.split("/")):
                continue
            archive.write(abs_path, rel_path)
PY
else
  echo "No packaging tool found." >&2
  echo "Tried: zip, python, python3, py, and local .venv interpreters." >&2
  echo "Install Python or add it to PATH." >&2
  exit 1
fi

echo "Built theme archive: $ZIP_PATH"
