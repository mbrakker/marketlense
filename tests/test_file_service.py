from __future__ import annotations

from pathlib import Path

import pytest

from src.contracts.files import ListDirectoryRequest, ReadTextRequest
from src.contracts.run_context import RunContext
from src.services.file_service import list_directory, read_text
from src.utils.errors import AppError


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


def test_read_text_wraps_os_error_as_typed_app_error(
    monkeypatch, tmp_path: Path, assert_app_error
) -> None:
    target = tmp_path / "denied.txt"
    target.write_text("x", encoding="utf-8")

    def _raise_permission(self, *, encoding="utf-8"):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", _raise_permission)

    with pytest.raises(AppError) as exc_info:
        read_text(
            ReadTextRequest(schema_version="1.0", path=str(target)),
            _ctx(),
        )

    assert_app_error(exc_info.value, code="file_read_failed", retryable=False)
