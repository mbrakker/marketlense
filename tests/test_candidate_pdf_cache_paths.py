from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from src.contracts.candidate_extraction import CandidateExtractOutcome
from src.contracts.drive import DriveDownloadResponse, DriveFile
from src.orchestrators import candidate_extraction_orchestrator as orchestrator
from src.utils.errors import AppError
from src.utils.path_utils import safe_pdf_name


def _pdf_bytes(label: str) -> bytes:
    payload = BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    page.merge_page(page)
    writer.add_metadata({"/Title": label})
    writer.write(payload)
    return payload.getvalue()


def _drive_file(file_id: str, name: str, content: bytes) -> DriveFile:
    return DriveFile(
        schema_version="1.0",
        file_id=file_id,
        name=name,
        modified_time=None,
        md5_checksum=hashlib.md5(content).hexdigest(),
    )


def _outcome(request) -> CandidateExtractOutcome:
    return CandidateExtractOutcome(
        schema_version="1.0",
        report_id=request.report_id,
        report_name=request.report_name,
        pdf_path=request.pdf_path,
        candidates_path="",
        candidate_count=0,
        chart_count=0,
        table_count=0,
        crop_count=0,
        crop_paths=[],
    )


def _run(
    ingest_settings,
    run_context,
    drive_file: DriveFile,
    content: bytes,
    downloads: list[str],
):
    def _download(request, _ctx):
        downloads.append(request.file.file_id)
        return DriveDownloadResponse(
            schema_version="1.0",
            file=request.file,
            content=content,
            md5=hashlib.md5(content).hexdigest(),
            size=len(content),
        )

    dependencies = replace(
        orchestrator.CandidateExtractionDependencies.default(),
        list_pdfs=lambda _request, _ctx: [drive_file],
        download_pdf=_download,
        generate_candidate_pack=lambda request, _ctx: _outcome(request),
    )
    return orchestrator.run_candidate_extraction(
        ingest_settings,
        limit=1,
        ctx=run_context,
        dependencies=dependencies,
    )[0]


def test_candidate_cache_isolated_by_drive_id_for_same_casefolded_name(
    ingest_settings, run_context
) -> None:
    first_content = _pdf_bytes("first")
    second_content = _pdf_bytes("second")
    first = _drive_file("drive-first", "Report.pdf", first_content)
    second = _drive_file("drive-second", "report.PDF", second_content)
    downloads: list[str] = []

    first_outcome = _run(ingest_settings, run_context, first, first_content, downloads)
    second_outcome = _run(
        ingest_settings, run_context, second, second_content, downloads
    )

    first_path = Path(first_outcome.pdf_path)
    second_path = Path(second_outcome.pdf_path)
    assert first_path != second_path
    assert first_path.name.casefold() != second_path.name.casefold()
    assert first_path.read_bytes() == first_content
    assert second_path.read_bytes() == second_content
    assert downloads == ["drive-first", "drive-second"]


def test_candidate_cache_replay_and_changed_content_use_safe_distinct_artifacts(
    ingest_settings, run_context
) -> None:
    first_content = _pdf_bytes("version-a")
    second_content = _pdf_bytes("version-b")
    first = _drive_file("drive-replayed", "report.pdf", first_content)
    changed = _drive_file("drive-replayed", "REPORT.PDF", second_content)
    downloads: list[str] = []

    first_outcome = _run(ingest_settings, run_context, first, first_content, downloads)
    replay_outcome = _run(ingest_settings, run_context, first, first_content, downloads)
    changed_outcome = _run(
        ingest_settings, run_context, changed, second_content, downloads
    )

    assert replay_outcome.pdf_path == first_outcome.pdf_path
    assert Path(first_outcome.pdf_path).read_bytes() == first_content
    assert changed_outcome.pdf_path != first_outcome.pdf_path
    assert Path(changed_outcome.pdf_path).read_bytes() == second_content
    assert Path(first_outcome.pdf_path).read_bytes() == first_content
    assert downloads == ["drive-replayed", "drive-replayed"]


def test_candidate_cache_without_drive_md5_versions_downloaded_content_safely(
    ingest_settings, run_context
) -> None:
    first_content = _pdf_bytes("missing-md5-a")
    second_content = _pdf_bytes("missing-md5-b")
    first = replace(
        _drive_file("drive-missing-md5", "report.pdf", first_content),
        md5_checksum=None,
    )
    changed = replace(
        _drive_file("drive-missing-md5", "REPORT.PDF", second_content),
        md5_checksum=None,
    )
    downloads: list[str] = []

    first_outcome = _run(ingest_settings, run_context, first, first_content, downloads)
    replay_outcome = _run(ingest_settings, run_context, first, first_content, downloads)
    changed_outcome = _run(
        ingest_settings, run_context, changed, second_content, downloads
    )

    assert first_outcome.error is None
    assert replay_outcome.error is None
    assert changed_outcome.error is None
    assert replay_outcome.pdf_path == first_outcome.pdf_path
    assert changed_outcome.pdf_path != first_outcome.pdf_path
    assert Path(first_outcome.pdf_path).read_bytes() == first_content
    assert Path(changed_outcome.pdf_path).read_bytes() == second_content
    assert downloads == ["drive-missing-md5"] * 3


def test_candidate_download_rejects_source_md5_mismatch_before_publication(
    ingest_settings, run_context
) -> None:
    expected_content = _pdf_bytes("expected")
    downloaded_content = _pdf_bytes("downloaded")
    drive_file = _drive_file("drive-md5-mismatch", "mismatch.pdf", expected_content)
    cache_root = Path(ingest_settings.cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    marker = cache_root / "pre-existing-marker.txt"
    marker.write_bytes(b"keep me")
    downloads: list[str] = []

    def _download(request, _ctx):
        downloads.append(request.file.file_id)
        return DriveDownloadResponse(
            schema_version="1.0",
            file=request.file,
            content=downloaded_content,
            md5=hashlib.md5(downloaded_content).hexdigest(),
            size=len(downloaded_content),
        )

    dependencies = replace(
        orchestrator.CandidateExtractionDependencies.default(),
        download_pdf=_download,
    )
    canonical_path, _ = orchestrator._candidate_cache_paths(drive_file, ingest_settings)

    with pytest.raises(AppError) as exc_info:
        orchestrator._download_if_needed(
            drive_file, ingest_settings, run_context, dependencies
        )

    assert exc_info.value.code == "candidate_source_md5_mismatch"
    assert exc_info.value.retryable is False
    assert downloads == [drive_file.file_id]
    assert not canonical_path.exists()
    assert marker.read_bytes() == b"keep me"


def test_candidate_cache_concurrent_same_source_publishes_complete_artifact(
    ingest_settings, run_context
) -> None:
    content = _pdf_bytes("concurrent")
    drive_file = _drive_file("drive-concurrent", "concurrent.pdf", content)
    downloads: list[str] = []

    def _download(request, _ctx):
        downloads.append(request.file.file_id)
        return DriveDownloadResponse(
            schema_version="1.0",
            file=request.file,
            content=content,
            md5=hashlib.md5(content).hexdigest(),
            size=len(content),
        )

    dependencies = replace(
        orchestrator.CandidateExtractionDependencies.default(),
        download_pdf=_download,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                orchestrator._download_if_needed,
                drive_file,
                ingest_settings,
                run_context,
                dependencies,
            )
            for _ in range(2)
        ]
        results = [future.result() for future in futures]

    paths = {Path(path) for path, _md5 in results}
    assert len(paths) == 1
    path = next(iter(paths))
    assert path.read_bytes() == content
    assert all(md5 == hashlib.md5(content).hexdigest() for _path, md5 in results)
    assert 1 <= len(downloads) <= 2


def test_candidate_cache_promotes_matching_legacy_artifact_without_download(
    ingest_settings, run_context
) -> None:
    content = _pdf_bytes("legacy")
    drive_file = _drive_file("drive-legacy", "legacy report.pdf", content)
    legacy_path = Path(ingest_settings.cache_dir) / safe_pdf_name(drive_file.name)
    legacy_path.write_bytes(content)
    downloads: list[str] = []

    outcome = _run(ingest_settings, run_context, drive_file, content, downloads)

    assert downloads == []
    assert Path(outcome.pdf_path).exists()
    assert Path(outcome.pdf_path) != legacy_path
    assert Path(outcome.pdf_path).read_bytes() == content
    assert legacy_path.read_bytes() == content


def test_candidate_cache_conflict_preserves_existing_artifact(
    ingest_settings, run_context
) -> None:
    content = _pdf_bytes("original")
    drive_file = _drive_file("drive-conflict", "conflict.pdf", content)
    downloads: list[str] = []
    initial = _run(ingest_settings, run_context, drive_file, content, downloads)
    cache_path = Path(initial.pdf_path)
    conflicting_bytes = b"different artifact bytes"
    cache_path.write_bytes(conflicting_bytes)

    outcome = _run(ingest_settings, run_context, drive_file, content, downloads)

    assert outcome.error is not None
    assert "conflicting source-associated" in outcome.error
    assert downloads == ["drive-conflict"]
    assert cache_path.read_bytes() == conflicting_bytes


def test_candidate_cache_rejects_impossible_root_before_download(
    ingest_settings, run_context, tmp_path
) -> None:
    impossible_root = tmp_path / ("deep-cache-root-" * 20)
    settings = replace(ingest_settings, cache_dir=str(impossible_root))
    content = _pdf_bytes("root")
    drive_file = _drive_file("drive-root", "root.pdf", content)
    downloads: list[str] = []
    dependencies = replace(
        orchestrator.CandidateExtractionDependencies.default(),
        download_pdf=lambda *_args: downloads.append("unexpected"),
    )

    with pytest.raises(AppError) as exc_info:
        orchestrator._download_if_needed(
            drive_file, settings, run_context, dependencies
        )

    assert exc_info.value.retryable is False
    assert exc_info.value.code == "candidate_cache_path_invalid"
    assert downloads == []


def test_candidate_cache_compacts_long_unicode_names_within_windows_budgets(
    ingest_settings, run_context
) -> None:
    content = _pdf_bytes("long")
    long_name = ("Очень длинный отчёт " * 18) + ".pdf"
    drive_file = _drive_file("drive-long-name", long_name, content)
    downloads: list[str] = []

    outcome = _run(ingest_settings, run_context, drive_file, content, downloads)

    path = Path(outcome.pdf_path)
    path_units = len(str(path.resolve()).encode("utf-16-le")) // 2
    assert path.exists()
    assert path_units <= 240
    assert len(path.name) <= 255
    assert downloads == ["drive-long-name"]


__all__ = [name for name in globals() if name.startswith("test_candidate_cache_")]
