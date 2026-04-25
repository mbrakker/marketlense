from __future__ import annotations

import json
import logging
from pathlib import Path

from src.contracts.file_cache import (
    FileCacheMd5SidecarResolveRequest,
    FileCacheMd5SidecarWriteRequest,
)
from src.contracts.run_context import RunContext
from src.services.file_cache_service import resolve_md5_sidecar, write_md5_sidecar


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _decode_service_logs(caplog) -> list[dict]:
    events: list[dict] = []
    for record in caplog.records:
        if record.name != "market_lense.file_cache_service":
            continue
        payload = json.loads(record.getMessage())
        if isinstance(payload, dict):
            events.append(payload)
    return events


def test_write_md5_sidecar_persists_typed_payload(
    tmp_path: Path,
    assert_no_defaulted_required_fields,
) -> None:
    cache_path = tmp_path / "cached.pdf"
    cache_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    stat = cache_path.stat()

    response = write_md5_sidecar(
        FileCacheMd5SidecarWriteRequest(
            schema_version="1.0",
            cache_path=str(cache_path),
            file_id="file-1",
            file_name="cached.pdf",
            md5="0123456789abcdef0123456789abcdef",
            size_bytes=stat.st_size,
            mtime_utc=stat.st_mtime,
        ),
        _ctx(),
    )

    assert response.written is True
    assert response.reason == "written"
    assert response.record is not None
    assert_no_defaulted_required_fields(response)
    assert_no_defaulted_required_fields(response.record)
    payload = json.loads(Path(response.sidecar_path).read_text(encoding="utf-8"))
    assert payload["file_id"] == "file-1"
    assert payload["md5"] == "0123456789abcdef0123456789abcdef"


def test_resolve_md5_sidecar_returns_hit_and_logs_required_fields(
    tmp_path: Path,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    cache_path = tmp_path / "cached.pdf"
    cache_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    stat = cache_path.stat()
    sidecar_path = Path(f"{cache_path}.md5.json")
    sidecar_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "file_id": "file-1",
                "name": "cached.pdf",
                "md5": "abcdefabcdefabcdefabcdefabcdefab",
                "size_bytes": stat.st_size,
                "mtime_utc": int(stat.st_mtime),
            }
        ),
        encoding="utf-8",
    )

    caplog.set_level(logging.INFO, logger="market_lense.file_cache_service")
    response = resolve_md5_sidecar(
        FileCacheMd5SidecarResolveRequest(
            schema_version="1.0",
            cache_path=str(cache_path),
            file_id="file-1",
            size_bytes=stat.st_size,
            mtime_utc=stat.st_mtime,
        ),
        _ctx(),
    )

    assert response.hit is True
    assert response.reason == "matched"
    assert response.resolved_md5 == "abcdefabcdefabcdefabcdefabcdefab"
    assert response.record is not None
    assert_no_defaulted_required_fields(response)
    assert_no_defaulted_required_fields(response.record)
    assert_logs_have_required_fields(_decode_service_logs(caplog))


def test_resolve_md5_sidecar_returns_miss_on_stat_mismatch(tmp_path: Path) -> None:
    cache_path = tmp_path / "cached.pdf"
    cache_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    stat = cache_path.stat()
    Path(f"{cache_path}.md5.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "file_id": "file-1",
                "name": "cached.pdf",
                "md5": "abcdefabcdefabcdefabcdefabcdefab",
                "size_bytes": stat.st_size + 1,
                "mtime_utc": int(stat.st_mtime),
            }
        ),
        encoding="utf-8",
    )

    response = resolve_md5_sidecar(
        FileCacheMd5SidecarResolveRequest(
            schema_version="1.0",
            cache_path=str(cache_path),
            file_id="file-1",
            size_bytes=stat.st_size,
            mtime_utc=stat.st_mtime,
        ),
        _ctx(),
    )

    assert response.hit is False
    assert response.reason == "size_mismatch"
    assert response.resolved_md5 is None
    assert response.record is not None


def test_write_md5_sidecar_returns_incomplete_metadata_without_write(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "cached.pdf"
    cache_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

    response = write_md5_sidecar(
        FileCacheMd5SidecarWriteRequest(
            schema_version="1.0",
            cache_path=str(cache_path),
            file_id="file-1",
            file_name="cached.pdf",
            md5=None,
            size_bytes=None,
            mtime_utc=None,
        ),
        _ctx(),
    )

    assert response.written is False
    assert response.reason == "incomplete_metadata"
    assert Path(response.sidecar_path).exists() is False
