from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pypdf import PdfWriter

from src.contracts.drive import DriveDownloadResponse, DriveFile
from src.orchestrators import candidate_extraction_orchestrator as orch
from src.utils.errors import AppError


def _drive_file() -> DriveFile:
    return DriveFile(
        schema_version="1.0",
        file_id="file-1",
        name="report.pdf",
        modified_time=None,
        md5_checksum="md5",
    )


def _pdf_bytes() -> bytes:
    payload = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    writer.write(payload)
    return payload.getvalue()


def test_candidate_extract_retries_retryable_download(
    ingest_settings, monkeypatch
) -> None:
    drive_file = _drive_file()
    attempts = {"download": 0}
    sleep_calls: list[int] = []

    def _download(req, ctx):
        attempts["download"] += 1
        if attempts["download"] < 2:
            raise AppError(
                code="drive_download_failed", message="retry", retryable=True
            )
        payload = _pdf_bytes()
        return DriveDownloadResponse(
            schema_version="1.0",
            file=req.file,
            content=payload,
            md5="md5",
            size=len(payload),
        )

    monkeypatch.setattr(orch, "list_pdfs", lambda req, ctx: [drive_file])
    monkeypatch.setattr(orch, "download_pdf", _download)
    monkeypatch.setattr(
        orch.time, "sleep", lambda seconds: sleep_calls.append(int(seconds))
    )

    outcomes = orch.run_candidate_extraction(ingest_settings, limit=1)

    assert len(outcomes) == 1
    assert outcomes[0].error is None
    assert Path(outcomes[0].candidates_path).exists()
    assert attempts["download"] == 2
    assert sleep_calls == [1]


def test_candidate_extract_stops_on_non_retryable_download_error(
    ingest_settings, monkeypatch
) -> None:
    drive_file = _drive_file()
    attempts = {"download": 0}
    sleep_calls: list[int] = []

    def _download(req, ctx):
        attempts["download"] += 1
        raise AppError(code="drive_file_id_missing", message="missing", retryable=False)

    monkeypatch.setattr(orch, "list_pdfs", lambda req, ctx: [drive_file])
    monkeypatch.setattr(orch, "download_pdf", _download)
    monkeypatch.setattr(
        orch.time, "sleep", lambda seconds: sleep_calls.append(int(seconds))
    )

    outcomes = orch.run_candidate_extraction(ingest_settings, limit=1)

    assert len(outcomes) == 1
    assert outcomes[0].error == "missing"
    assert outcomes[0].candidate_count == 0
    assert attempts["download"] == 1
    assert sleep_calls == []
