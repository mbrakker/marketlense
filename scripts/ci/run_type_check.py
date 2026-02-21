from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MYPY_CONFIG = ROOT / "mypy.ini"


def main() -> int:
    configured_paths = os.getenv("TYPECHECK_PATHS", "").strip().split()
    targets = configured_paths or ["src/contracts", "scripts/ci"]

    print("Type gate files:")
    for path in targets:
        print(f"  - {path}")

    cmd = [sys.executable, "-m", "mypy", "--config-file", str(MYPY_CONFIG), *targets]
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
