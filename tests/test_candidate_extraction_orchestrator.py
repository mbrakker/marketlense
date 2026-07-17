from __future__ import annotations

import json
import logging
from dataclasses import replace
from io import BytesIO
from pathlib import Path

from pypdf import PdfWriter

from src.contracts.drive import DriveDownloadResponse, DriveFile
from src.contracts.remediation import RemediationListRequest
from src.orchestrators import candidate_extraction_orchestrator as orch
from src.services.state_service import list_remediation_records
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


def _deps(**overrides) -> orch.CandidateExtractionDependencies:
    return replace(orch.CandidateExtractionDependencies.default(), **overrides)


def _json_events(caplog, *logger_names: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    allowed = set(logger_names)
    for record in caplog.records:
        if record.name not in allowed:
            continue
        try:
            payload = json.loads(record.getMessage())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def test_candidate_extract_retries_retryable_download_with_real_generator_path(
    caplog,
    ingest_settings,
    run_context,
    assert_logs_have_required_fields,
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

    deps = _deps(
        list_pdfs=lambda req, ctx: [drive_file],
        download_pdf=_download,
        sleep_fn=lambda seconds: sleep_calls.append(int(seconds)),
    )

    caplog.set_level(logging.INFO)
    outcomes = orch.run_candidate_extraction(
        ingest_settings,
        limit=1,
        ctx=run_context,
        dependencies=deps,
    )

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.error is None
    assert outcome.report_id == drive_file.file_id
    assert outcome.report_name == "report-pdf"
    assert Path(outcome.pdf_path).exists()
    assert Path(outcome.candidates_path).exists()
    assert outcome.crop_paths == []
    assert attempts["download"] == 2
    assert sleep_calls == [1]

    saved = json.loads(Path(outcome.candidates_path).read_text(encoding="utf-8"))
    assert saved["report_id"] == drive_file.file_id
    assert saved["pdf_path"] == outcome.pdf_path
    assert saved["candidate_count"] == outcome.candidate_count

    events = _json_events(
        caplog,
        "market_lense.candidate_extraction_orchestrator",
        "market_lense.candidate_extraction_generator",
    )
    assert_logs_have_required_fields(events)
    assert any(event.get("event") == "pdf_cache_miss" for event in events)
    assert any(event.get("event") == "candidate_extract_saved" for event in events)
    assert any(event.get("event") == "candidate_extract_complete" for event in events)


def test_candidate_extract_stops_on_non_retryable_download_error(
    caplog,
    ingest_settings,
    run_context,
    assert_logs_have_required_fields,
) -> None:
    drive_file = _drive_file()
    attempts = {"download": 0}
    sleep_calls: list[int] = []

    def _download(req, ctx):
        attempts["download"] += 1
        raise AppError(code="drive_file_id_missing", message="missing", retryable=False)

    deps = _deps(
        list_pdfs=lambda req, ctx: [drive_file],
        download_pdf=_download,
        sleep_fn=lambda seconds: sleep_calls.append(int(seconds)),
    )

    caplog.set_level(logging.INFO)
    outcomes = orch.run_candidate_extraction(
        ingest_settings,
        limit=1,
        ctx=run_context,
        dependencies=deps,
    )

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.error == "missing"
    assert outcome.candidate_count == 0
    assert outcome.candidates_path == ""
    assert attempts["download"] == 1
    assert sleep_calls == []

    records = list_remediation_records(
        RemediationListRequest(
            schema_version="1.0",
            state_db=ingest_settings.state_db,
            workflow="candidate_extraction",
        ),
        run_context,
    ).records
    assert len(records) == 1
    assert records[0].error_code == "drive_file_id_missing"
    assert records[0].status == "operator_action_required"

    events = _json_events(caplog, "market_lense.candidate_extraction_orchestrator")
    assert_logs_have_required_fields(events)
    assert any(event.get("event") == "candidate_extract_failed" for event in events)
