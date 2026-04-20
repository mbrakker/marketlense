from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contracts.files import (
    ListDirectoryRequest,
    PdfCacheTextReadRequest,
    ReadTextRequest,
)
from src.contracts.run_context import RunContext
from src.services.file_service import (
    list_directory,
    read_latest_pdf_cache_text,
    read_text,
)
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


def test_list_directory_rejects_parent_traversal_glob(
    tmp_path: Path,
    assert_app_error,
) -> None:
    root = tmp_path / "root"
    root.mkdir(parents=True, exist_ok=True)
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")

    with pytest.raises(AppError) as exc_info:
        list_directory(
            ListDirectoryRequest(
                schema_version="1.0",
                root_dir=str(root),
                glob_pattern="../*.txt",
                recursive=False,
                include_files=True,
                include_dirs=False,
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="directory_glob_invalid",
        retryable=False,
    )


def test_read_latest_pdf_cache_text_reads_latest_cache_file(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache" / "pdf_cache" / "0123456789abcdef0123456789abcdef"
    cache_root.mkdir(parents=True, exist_ok=True)
    older = cache_root / "text_old.json"
    newer = cache_root / "text_new.json"
    older.write_text(json.dumps({"text": "older"}), encoding="utf-8")
    newer.write_text(json.dumps({"text": "newer"}), encoding="utf-8")

    response = read_latest_pdf_cache_text(
        PdfCacheTextReadRequest(
            schema_version="1.0",
            cache_dir=str(tmp_path / "cache"),
            md5="0123456789abcdef0123456789abcdef",
        ),
        _ctx(),
    )

    assert response.text == "newer"
    assert Path(response.source_path).name == "text_new.json"


def test_read_latest_pdf_cache_text_rejects_invalid_md5_key(
    tmp_path: Path,
    assert_app_error,
) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(AppError) as exc_info:
        read_latest_pdf_cache_text(
            PdfCacheTextReadRequest(
                schema_version="1.0",
                cache_dir=str(cache_dir),
                md5="../outside",
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="pdf_cache_md5_invalid",
        retryable=False,
    )
