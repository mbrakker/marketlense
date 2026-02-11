from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.contracts.drive import DriveDownloadToPathResponse, DriveFile
from src.orchestrators import ingest_orchestrator as orch
from src.utils.errors import AppError


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj <</Type/Catalog>> endobj\n%%EOF\n"


def test_retry_on_retryable_app_error(ingest_settings, monkeypatch) -> None:
    settings = replace(ingest_settings, batch_limit=1, ingest_worker_limit=1)
    drive_file = DriveFile(
        schema_version="1.0",
        file_id="file-1",
        name="retry.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    retry_error = AppError(
        code="openai_request_failed",
        message="retry",
        retryable=True,
    )
    attempt_count = {"value": 0}
    sleep_calls: list[int] = []

    def _download(req, ctx):
        payload = _pdf_bytes()
        out_path = Path(req.output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)
        return DriveDownloadToPathResponse(
            schema_version="1.0",
            file=req.file,
            output_path=req.output_path,
            md5="md5",
            size=len(payload),
        )

    def _generate_report(file, cache_path, settings, md5, ctx):
        attempt_count["value"] += 1
        raise retry_error

    monkeypatch.setattr(orch, "list_pdfs", lambda req, ctx: [drive_file])
    monkeypatch.setattr(orch, "download_pdf_to_path", _download)
    monkeypatch.setattr(orch, "generate_report", _generate_report)
    monkeypatch.setattr(orch.time, "sleep", lambda seconds: sleep_calls.append(int(seconds)))

    outcomes = orch.run_ingest(settings, limit=1)

    assert len(outcomes) == 1
    assert outcomes[0].status == "error"
    assert outcomes[0].file_id == "file-1"
    assert attempt_count["value"] == 3
    assert sleep_calls == [1, 2]
