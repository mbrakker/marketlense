from __future__ import annotations

from pathlib import Path


MAX_TEST_FILE_LINES = 1000


def test_first_party_test_modules_stay_below_long_file_threshold() -> None:
    long_files: list[str] = []

    for path in sorted(Path("tests").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        line_count = sum(1 for _ in path.open(encoding="utf-8"))
        if line_count > MAX_TEST_FILE_LINES:
            long_files.append(f"{path.as_posix()}:{line_count}")

    assert long_files == []
