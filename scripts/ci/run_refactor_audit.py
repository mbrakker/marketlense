from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def refactor_audit_commands() -> tuple[tuple[str, ...], ...]:
    return (
        ("python", "scripts/ci/check_split_symbol_links.py"),
        ("python", "scripts/ci/check_architecture_imports.py"),
        ("python", "scripts/ci/check_role_io_boundaries.py"),
        ("python", "scripts/ci/check_service_boundary_map.py"),
        ("python", "scripts/ci/check_refactor_movement_evidence.py"),
        ("python", "scripts/count_long_files.py", "--root", "."),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the canonical behavior-preserving refactor audit."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print commands without executing them.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    commands = refactor_audit_commands()
    for index, command in enumerate(commands, start=1):
        print(f"[{index}/{len(commands)}] {' '.join(command)}", flush=True)
        if args.list:
            continue
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
