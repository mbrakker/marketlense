from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path

import pytest

from src.contracts.files import (
    AppendBytesRequest,
    FileBundleHashRequest,
    FileStatRequest,
    JsonObjectCacheReadRequest,
    JsonObjectCacheWriteRequest,
    ListDirectoryRequest,
    DirectoryPatternCountRequest,
    DirectoryPatternSpec,
    PipelineCheckpointReadRequest,
    PipelineCheckpointWriteRequest,
    PipelineStageCheckpoint,
    PdfCacheTextReadRequest,
    ReadTextRequest,
    WriteBytesRequest,
    ReadJsonRequest,
    StructuredLogLoadRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.report_cards import (
    CardCoverAsset,
    CardCoverAssetSet,
    CoverFingerprint,
    ReportCardManifest,
    ReportCardManifestWriteRequest,
)
from src.services.file_service import (
    append_bytes,
    hash_file_bundle,
    read_json_object_cache,
    write_json_object_cache,
    list_directory,
    count_directory_patterns,
    file_stat,
    load_structured_log_events,
    read_json,
    read_pipeline_checkpoint,
    read_latest_pdf_cache_text,
    read_text,
    write_pipeline_checkpoint,
    write_report_card_manifest,
    write_bytes,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _report_card_manifest() -> ReportCardManifest:
    covers = CardCoverAssetSet(
        schema_version="1.0",
        small=CardCoverAsset("1.0", "small", "assets/report-card-small.png", 1600, 900),
        medium=CardCoverAsset(
            "1.0", "medium", "assets/report-card-medium.png", 1200, 1500
        ),
        large=CardCoverAsset(
            "1.0", "large", "assets/report-card-large.png", 1200, 1600
        ),
    )
    fingerprint = CoverFingerprint(
        schema_version="1.0",
        geometry_family="ascending_trajectory",
        evidence_shape="trend",
        direction="rising",
        geography_scope="global",
        evidence_density="balanced",
        domain_layer="grid",
        seed=184221,
        selection_reason="A sustained upward trend dominates the report evidence.",
    )
    return ReportCardManifest(
        schema_version="1.0",
        title="Global Economic Conditions Quarterly Update",
        title_scale="long",
        publisher="McKinsey & Company",
        published_date="2026-06-09",
        geography_label="Global",
        geography_scope="global",
        covered_period="Q2 2026",
        tldr_compact="Growth remains uneven as rates reshape investment decisions.",
        tldr_standard=(
            "Growth remains uneven across markets as persistent rates reshape "
            "investment decisions through the second quarter of 2026."
        ),
        key_insights=(
            "Investment remains concentrated in resilient service sectors.",
            "Trade pressure is widening the gap between regional outlooks.",
        ),
        fingerprint=fingerprint,
        covers=covers,
    )


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
    external_boundary_mocks_only, tmp_path: Path, assert_app_error
) -> None:
    target = tmp_path / "denied.txt"
    target.write_text("x", encoding="utf-8")

    def _raise_permission(self, *, encoding="utf-8"):
        raise PermissionError("denied")

    external_boundary_mocks_only.setattr(Path, "read_text", _raise_permission)

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


def test_append_bytes_appends_under_the_file_service_lock(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    write_bytes(
        WriteBytesRequest(schema_version="1.0", path=str(path), content=b"first\n"),
        _ctx(),
    )

    response = append_bytes(
        AppendBytesRequest(schema_version="1.0", path=str(path), content=b"second\n"),
        _ctx(),
    )

    assert response.bytes_appended == len(b"second\n")
    assert path.read_bytes() == b"first\nsecond\n"


def test_write_bytes_uses_atomic_replace_and_cleans_stale_temp(tmp_path: Path) -> None:
    target = tmp_path / "atomic.bin"
    stale_temp = tmp_path / "atomic.bin.tmp-write-stale"
    stale_temp.write_bytes(b"stale")
    stale_time = stale_temp.stat().st_mtime - 7200.0
    os.utime(stale_temp, (stale_time, stale_time))

    response = write_bytes(
        WriteBytesRequest(
            schema_version="1.0",
            path=str(target),
            content=b"fresh-bytes",
        ),
        _ctx(),
    )

    assert response.bytes_written == len(b"fresh-bytes")
    assert target.read_bytes() == b"fresh-bytes"
    assert not stale_temp.exists()
    assert list(tmp_path.glob("atomic.bin.tmp-write-*")) == []


def test_write_bytes_uses_short_atomic_temp_for_long_target_name(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{'long-report-artifact-name-' * 5}.json"

    response = write_bytes(
        WriteBytesRequest(
            schema_version="1.0",
            path=str(target),
            content=b'{"status":"ok"}',
        ),
        _ctx(),
    )

    assert response.path == str(target)
    assert target.read_bytes() == b'{"status":"ok"}'
    assert list(tmp_path.glob("*.tmp-write-*")) == []


def test_write_bytes_serializes_same_target_concurrent_writes(tmp_path: Path) -> None:
    target = tmp_path / "shared-cache.json"

    def _write(index: int) -> int:
        response = write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=str(target),
                content=f'{{"index":{index}}}'.encode("utf-8"),
            ),
            _ctx(),
        )
        return response.bytes_written

    with ThreadPoolExecutor(max_workers=4) as executor:
        lengths = list(executor.map(_write, range(12)))

    assert len(lengths) == 12
    assert all(length > 0 for length in lengths)
    assert json.loads(target.read_text(encoding="utf-8"))["index"] in range(12)
    assert list(tmp_path.glob("*.tmp-write-*")) == []


def test_write_bytes_retries_transient_windows_replace_sharing_violation(
    external_boundary_mocks_only,
    tmp_path: Path,
) -> None:
    target = tmp_path / "atomic.bin"
    original_replace = os.replace
    calls = 0

    def _transient_replace(src, dst):
        nonlocal calls
        calls += 1
        if calls == 1:
            error = PermissionError(5, "Access is denied")
            error.winerror = 5
            raise error
        return original_replace(src, dst)

    external_boundary_mocks_only.setattr(os, "replace", _transient_replace)

    response = write_bytes(
        WriteBytesRequest(
            schema_version="1.0",
            path=str(target),
            content=b"updated",
        ),
        _ctx(),
    )

    assert calls == 2
    assert response.bytes_written == len(b"updated")
    assert target.read_bytes() == b"updated"


def test_write_bytes_preserves_existing_file_when_replace_fails(
    external_boundary_mocks_only,
    tmp_path: Path,
    assert_app_error,
) -> None:
    target = tmp_path / "atomic.bin"
    target.write_bytes(b"original")
    created_temp_paths: list[Path] = []
    original_replace = os.replace

    def _failing_replace(src, dst):
        created_temp_paths.append(Path(src))
        raise OSError("replace failed")

    external_boundary_mocks_only.setattr(os, "replace", _failing_replace)

    with pytest.raises(AppError) as exc_info:
        write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=str(target),
                content=b"updated",
            ),
            _ctx(),
        )

    assert_app_error(exc_info.value, code="file_write_failed", retryable=False)
    assert target.read_bytes() == b"original"
    assert created_temp_paths
    assert all(not path.exists() for path in created_temp_paths)
    external_boundary_mocks_only.setattr(os, "replace", original_replace)


def test_write_bytes_cleanup_failure_does_not_mask_replace_error(
    external_boundary_mocks_only,
    tmp_path: Path,
    assert_app_error,
) -> None:
    target = tmp_path / "atomic.bin"
    target.write_bytes(b"original")

    def _failing_replace(src, dst):
        raise OSError("replace failed")

    def _failing_unlink(self, *, missing_ok=False):
        raise OSError("cleanup failed")

    external_boundary_mocks_only.setattr(os, "replace", _failing_replace)
    external_boundary_mocks_only.setattr(Path, "unlink", _failing_unlink)

    with pytest.raises(AppError) as exc_info:
        write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=str(target),
                content=b"updated",
            ),
            _ctx(),
        )

    assert_app_error(exc_info.value, code="file_write_failed", retryable=False)
    assert isinstance(exc_info.value.cause, OSError)
    assert str(exc_info.value.cause) == "replace failed"
    assert target.read_bytes() == b"original"


def test_read_json_returns_typed_payload_and_invalid_json_error(
    tmp_path: Path,
    assert_app_error,
) -> None:
    valid_path = tmp_path / "valid.json"
    invalid_path = tmp_path / "invalid.json"
    valid_path.write_text('{"value": 3}', encoding="utf-8")
    invalid_path.write_text("{invalid", encoding="utf-8")

    response = read_json(
        ReadJsonRequest(schema_version="1.0", path=str(valid_path)),
        _ctx(),
    )
    assert response.payload == {"value": 3}

    with pytest.raises(AppError) as exc_info:
        read_json(
            ReadJsonRequest(schema_version="1.0", path=str(invalid_path)),
            _ctx(),
        )
    assert_app_error(exc_info.value, code="file_json_invalid", retryable=False)


def test_file_stat_reports_path_kind_for_files_dirs_and_missing_paths(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "report.pdf"
    dir_path = tmp_path / "artifacts"
    file_path.write_bytes(b"pdf")
    dir_path.mkdir()

    file_response = file_stat(
        FileStatRequest(schema_version="1.0", path=str(file_path)),
        _ctx(),
    )
    dir_response = file_stat(
        FileStatRequest(schema_version="1.0", path=str(dir_path)),
        _ctx(),
    )
    missing_response = file_stat(
        FileStatRequest(schema_version="1.0", path=str(tmp_path / "missing.pdf")),
        _ctx(),
    )

    assert file_response.exists is True
    assert file_response.is_file is True
    assert file_response.is_dir is False
    assert file_response.size_bytes == 3
    assert dir_response.exists is True
    assert dir_response.is_file is False
    assert dir_response.is_dir is True
    assert missing_response.exists is False
    assert missing_response.is_file is False
    assert missing_response.is_dir is False


def test_load_structured_log_events_applies_byte_and_line_bounds(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "market_lense_2026-06-13.log"
    log_path.write_text(
        "\n".join(
            [
                '10:00:00 | INFO | test | {"event":"old"}',
                "not-json",
                '10:00:02 | INFO | test | {"event":"new"}',
            ]
        ),
        encoding="utf-8",
    )

    response = load_structured_log_events(
        StructuredLogLoadRequest(
            schema_version="1.0",
            path=str(log_path),
            max_lines=2,
            max_bytes=4096,
        ),
        _ctx(),
    )

    assert [event["event"] for event in response.events] == ["new"]
    assert response.events[0]["log_path"] == str(log_path)


def test_count_directory_patterns_groups_overlapping_patterns_by_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "out"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir(parents=True)
    (root / "a" / "validation.json").write_text("{}", encoding="utf-8")
    (root / "b" / "validation_policy.json").write_text("{}", encoding="utf-8")
    (root / "report.html").write_text("<html></html>", encoding="utf-8")

    response = count_directory_patterns(
        DirectoryPatternCountRequest(
            schema_version="1.0",
            patterns=[
                DirectoryPatternSpec(
                    schema_version="1.0",
                    name="validation",
                    root_dir=str(root),
                    glob_pattern="**/validation*.json",
                    recursive=True,
                    include_dirs=False,
                ),
                DirectoryPatternSpec(
                    schema_version="1.0",
                    name="html",
                    root_dir=str(root),
                    glob_pattern="*.html",
                    recursive=False,
                    include_dirs=False,
                ),
            ],
            limit_per_pattern=100,
        ),
        _ctx(),
    )

    assert [(row.name, row.count, row.error) for row in response.rows] == [
        ("validation", 2, ""),
        ("html", 1, ""),
    ]
    assert response.root_walk_count == 1


def test_pipeline_checkpoint_roundtrip_persists_artifact_refs_and_schema(
    tmp_path: Path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level("INFO", logger="market_lense.file_service")
    checkpoint = PipelineStageCheckpoint(
        schema_version="1.0",
        pipeline_name="report_generation",
        file_id="file-1",
        report_slug="market-report",
        stage_name="analysis_complete",
        stage_status="completed",
        artifact_refs={
            "analysis_snapshot": str(tmp_path / "out" / "analysis_vector_store.json"),
            "preview_image": str(tmp_path / "out" / "preview.png"),
        },
        payload={
            "schema_version": "1.0",
            "analysis": {"vector_store_id": "vs_123"},
        },
        completed_at_utc="2026-05-31T00:00:00+00:00",
        source_run_id="run-1",
        source_task_id="task-1",
    )

    write_response = write_pipeline_checkpoint(
        PipelineCheckpointWriteRequest(
            schema_version="1.0",
            checkpoint_root=str(tmp_path),
            checkpoint=checkpoint,
        ),
        _ctx(),
    )
    read_response = read_pipeline_checkpoint(
        PipelineCheckpointReadRequest(
            schema_version="1.0",
            checkpoint_root=str(tmp_path),
            pipeline_name="report_generation",
            file_id="file-1",
            stage_name="analysis_complete",
        ),
        _ctx(),
    )

    assert Path(write_response.checkpoint_path).parts[-3:] == (
        "report_generation",
        "file-1",
        "analysis_complete.json",
    )
    assert read_response.found is True
    assert read_response.checkpoint == checkpoint
    assert read_response.checkpoint_path == write_response.checkpoint_path

    event_payloads = []
    for record in caplog.records:
        try:
            event_payloads.append(json.loads(record.message))
        except json.JSONDecodeError:
            continue
    checkpoint_events = [
        event
        for event in event_payloads
        if event.get("event")
        in {"pipeline_checkpoint_write_complete", "pipeline_checkpoint_read_complete"}
    ]
    assert {event["event"] for event in checkpoint_events} == {
        "pipeline_checkpoint_write_complete",
        "pipeline_checkpoint_read_complete",
    }
    assert_logs_have_required_fields(checkpoint_events)


def test_write_report_card_manifest_persists_validated_payload_and_logs(
    tmp_path: Path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level("INFO", logger="market_lense.file_service")
    output_dir = tmp_path / "out" / "report-slug"

    response = write_report_card_manifest(
        ReportCardManifestWriteRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            manifest=_report_card_manifest(),
        ),
        _ctx(),
    )

    manifest_path = output_dir / "report-card-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert response.manifest_path == str(manifest_path.resolve())
    assert response.bytes_written > 0
    assert payload["tldr_compact"].endswith(".")
    assert len(payload["key_insights"]) == 2
    assert payload["covers"]["small"]["output_path"] == ("assets/report-card-small.png")
    assert payload["covers"]["medium"]["output_path"] == (
        "assets/report-card-medium.png"
    )
    assert payload["covers"]["large"]["output_path"] == ("assets/report-card-large.png")

    events = []
    for record in caplog.records:
        try:
            events.append(json.loads(record.message))
        except json.JSONDecodeError:
            continue
    manifest_events = [
        event
        for event in events
        if event.get("event")
        in {
            "report_card_manifest_write_start",
            "report_card_manifest_write_complete",
        }
    ]
    assert {event["event"] for event in manifest_events} == {
        "report_card_manifest_write_start",
        "report_card_manifest_write_complete",
    }
    assert_logs_have_required_fields(manifest_events)


def test_write_report_card_manifest_wraps_real_output_directory_failure(
    tmp_path: Path,
    assert_app_error,
) -> None:
    output_dir = tmp_path / "blocked"
    output_dir.write_text("not a directory", encoding="utf-8")

    with pytest.raises(AppError) as exc_info:
        write_report_card_manifest(
            ReportCardManifestWriteRequest(
                schema_version="1.0",
                output_dir=str(output_dir),
                manifest=_report_card_manifest(),
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="report_card_manifest_write_failed",
        retryable=False,
    )


def test_json_object_cache_round_trip_and_missing_state(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache" / "payload.json"
    missing = read_json_object_cache(
        JsonObjectCacheReadRequest(schema_version="1.0", path=str(cache_path)),
        _ctx(),
    )
    assert missing.found is False
    assert missing.payload is None
    assert missing.reason == "missing"

    written = write_json_object_cache(
        JsonObjectCacheWriteRequest(
            schema_version="1.0",
            path=str(cache_path),
            payload={"schema_version": "1.0", "value": 7},
        ),
        _ctx(),
    )
    loaded = read_json_object_cache(
        JsonObjectCacheReadRequest(schema_version="1.0", path=str(cache_path)),
        _ctx(),
    )

    assert written.path == str(cache_path)
    assert written.bytes_written == len(cache_path.read_bytes())
    assert loaded.found is True
    assert loaded.reason == "loaded"
    assert loaded.payload == {"schema_version": "1.0", "value": 7}


def test_json_object_cache_returns_invalid_json_state(tmp_path: Path) -> None:
    cache_path = tmp_path / "invalid.json"
    cache_path.write_text("{broken", encoding="utf-8")

    loaded = read_json_object_cache(
        JsonObjectCacheReadRequest(schema_version="1.0", path=str(cache_path)),
        _ctx(),
    )

    assert loaded.found is False
    assert loaded.payload is None
    assert loaded.reason == "invalid_json"


def test_hash_file_bundle_is_deterministic_and_content_sensitive(
    tmp_path: Path,
) -> None:
    first = tmp_path / "report.html.j2"
    second = tmp_path / "report.css.j2"
    first.write_text("template", encoding="utf-8")
    second.write_text("css", encoding="utf-8")
    request = FileBundleHashRequest(
        schema_version="1.0",
        paths=[str(first), str(second)],
    )

    initial = hash_file_bundle(request, _ctx())
    repeated = hash_file_bundle(request, _ctx())
    second.write_text("changed-css", encoding="utf-8")
    changed = hash_file_bundle(request, _ctx())

    expected_entries = {
        str(first): hashlib.sha256(b"template").hexdigest(),
        str(second): hashlib.sha256(b"css").hexdigest(),
    }
    assert initial.sha256 == repeated.sha256
    assert initial.file_sha256 == expected_entries
    assert changed.sha256 != initial.sha256
