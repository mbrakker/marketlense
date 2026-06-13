from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path

import pytest

from src.contracts.files import (
    ListDirectoryRequest,
    PipelineCheckpointReadRequest,
    PipelineCheckpointWriteRequest,
    PipelineStageCheckpoint,
    PdfCacheTextReadRequest,
    ReadTextRequest,
    WriteBytesRequest,
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
    list_directory,
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


def test_write_bytes_preserves_existing_file_when_replace_fails(
    monkeypatch,
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

    monkeypatch.setattr(os, "replace", _failing_replace)

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
    monkeypatch.setattr(os, "replace", original_replace)


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
