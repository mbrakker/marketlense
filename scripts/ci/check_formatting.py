from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    configured_paths = os.getenv("FORMAT_PATHS", "").strip().split()
    targets = configured_paths or ["scripts/ci", "tests/contracts"]

    print("Format gate files:")
    for path in targets:
        print(f"  - {path}")

    cmd = [sys.executable, "-m", "ruff", "format", "--check", *targets]
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
