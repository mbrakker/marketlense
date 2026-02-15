from __future__ import annotations

from types import SimpleNamespace

from src.contracts.candidate_extraction import CandidateExtractOutcome
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


def _candidate_outcome(report_id: str, report_name: str, pdf_path: str) -> CandidateExtractOutcome:
    return CandidateExtractOutcome(
        schema_version="1.0",
        report_id=report_id,
        report_name=report_name,
        pdf_path=pdf_path,
        candidates_path="out/candidates.json",
        candidate_count=1,
        chart_count=1,
        table_count=0,
        crop_count=1,
        crop_paths=["out/crop.png"],
        error=None,
    )


def test_candidate_extract_retries_retryable_download(ingest_settings, monkeypatch) -> None:
    drive_file = _drive_file()
    attempts = {"download": 0}
    sleep_calls: list[int] = []

    monkeypatch.setattr(orch, "list_pdfs", lambda req, ctx: [drive_file])
    monkeypatch.setattr(orch, "file_exists", lambda req, ctx: SimpleNamespace(exists=False))

    def _download(req, ctx):
        attempts["download"] += 1
        if attempts["download"] < 2:
            raise AppError(code="drive_download_failed", message="retry", retryable=True)
        return DriveDownloadResponse(
            schema_version="1.0",
            file=req.file,
            content=b"%PDF-1.4\n%%EOF\n",
            md5="md5",
            size=14,
        )

    monkeypatch.setattr(orch, "download_pdf", _download)
    monkeypatch.setattr(orch, "write_bytes", lambda req, ctx: SimpleNamespace(md5="md5"))
    monkeypatch.setattr(orch, "check_pdf_eof", lambda req, ctx: SimpleNamespace(has_eof=True))
    monkeypatch.setattr(
        orch,
        "generate_candidate_pack",
        lambda req, ctx: _candidate_outcome(req.report_id, req.report_name, req.pdf_path),
    )
    monkeypatch.setattr(orch.time, "sleep", lambda seconds: sleep_calls.append(int(seconds)))

    outcomes = orch.run_candidate_extraction(ingest_settings, limit=1)

    assert len(outcomes) == 1
    assert outcomes[0].error is None
    assert attempts["download"] == 2
    assert sleep_calls == [1]


def test_candidate_extract_stops_on_non_retryable_download_error(ingest_settings, monkeypatch) -> None:
    drive_file = _drive_file()
    attempts = {"download": 0}
    sleep_calls: list[int] = []

    monkeypatch.setattr(orch, "list_pdfs", lambda req, ctx: [drive_file])
    monkeypatch.setattr(orch, "file_exists", lambda req, ctx: SimpleNamespace(exists=False))

    def _download(req, ctx):
        attempts["download"] += 1
        raise AppError(code="drive_file_id_missing", message="missing", retryable=False)

    monkeypatch.setattr(orch, "download_pdf", _download)
    monkeypatch.setattr(orch, "write_bytes", lambda req, ctx: SimpleNamespace(md5="md5"))
    monkeypatch.setattr(orch, "check_pdf_eof", lambda req, ctx: SimpleNamespace(has_eof=True))
    monkeypatch.setattr(
        orch,
        "generate_candidate_pack",
        lambda req, ctx: (_ for _ in ()).throw(AssertionError("should not generate when download fails")),
    )
    monkeypatch.setattr(orch.time, "sleep", lambda seconds: sleep_calls.append(int(seconds)))

    outcomes = orch.run_candidate_extraction(ingest_settings, limit=1)

    assert len(outcomes) == 1
    assert outcomes[0].error == "missing"
    assert outcomes[0].candidate_count == 0
    assert attempts["download"] == 1
    assert sleep_calls == []
