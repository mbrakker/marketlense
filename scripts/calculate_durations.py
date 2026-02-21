from __future__ import annotations

import runpy
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    runpy.run_path(str(project_root / "calculate_durations.py"), run_name="__main__")


if __name__ == "__main__":
    main()
