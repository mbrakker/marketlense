from __future__ import annotations

from pathlib import Path

from src.contracts.files import ListDirectoryRequest
from src.contracts.run_context import RunContext
from src.services.file_service import list_directory


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_list_directory_supports_recursive_and_filters(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.log").write_text("b", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "c.txt").write_text("c", encoding="utf-8")

    non_recursive = list_directory(
        ListDirectoryRequest(
            schema_version="1.0",
            root_dir=str(tmp_path),
            glob_pattern="*.txt",
            recursive=False,
            include_files=True,
            include_dirs=False,
        ),
        _ctx(),
    )
    assert len(non_recursive.entries) == 1
    assert non_recursive.entries[0].name == "a.txt"

    recursive = list_directory(
        ListDirectoryRequest(
            schema_version="1.0",
            root_dir=str(tmp_path),
            glob_pattern="*.txt",
            recursive=True,
            include_files=True,
            include_dirs=False,
        ),
        _ctx(),
    )
    names = [entry.name for entry in recursive.entries]
    assert "a.txt" in names
    assert "c.txt" in names
