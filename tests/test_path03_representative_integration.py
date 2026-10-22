from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from pypdf import PdfReader

from src.contracts.drive import DriveDownloadResponse, DriveFile
from src.contracts.pdf_ocr import PdfOcrSplitRequest
from src.orchestrators import (
    candidate_extraction_orchestrator as candidate_orchestrator,
)
from src.services.pdf_service import split_pdf_for_ocr
from src.utils.path_utils import WINDOWS_COMPONENT_BUDGET, windows_path_units


@pytest.mark.integration
def test_path03_representative_candidate_and_ocr_artifacts(
    ingest_settings, run_context, tmp_path: Path
) -> None:
    source_path = (
        Path(__file__).parent
        / "fixtures"
        / "pdf_benchmark"
        / "golden"
        / "CAPGEMINI - 2026-Retail-Trends_ACIG.pdf"
    )
    source_content = source_path.read_bytes()
    source_md5 = hashlib.md5(source_content).hexdigest()
    drive_file = DriveFile(
        schema_version="1.0",
        file_id="path03-representative-source",
        name=source_path.name,
        modified_time=None,
        md5_checksum=source_md5,
    )
    settings = replace(
        ingest_settings,
        output_dir=str(tmp_path / "output"),
        cache_dir=str(tmp_path / "cache"),
    )
    downloads: list[str] = []

    def _list_pdfs(request, _ctx):
        return [drive_file]

    def _download_pdf(request, _ctx):
        downloads.append(request.file.file_id)
        return DriveDownloadResponse(
            schema_version="1.0",
            file=request.file,
            content=source_content,
            md5=source_md5,
            size=len(source_content),
        )

    dependencies = replace(
        candidate_orchestrator.CandidateExtractionDependencies.default(),
        list_pdfs=_list_pdfs,
        download_pdf=_download_pdf,
    )

    outcomes = candidate_orchestrator.run_candidate_extraction(
        settings,
        limit=1,
        ctx=run_context,
        dependencies=dependencies,
    )
    outcome = outcomes[0]
    assert outcome.error is None
    assert Path(outcome.pdf_path).read_bytes() == source_content
    assert windows_path_units(outcome.pdf_path) <= 240
    assert windows_path_units(Path(outcome.pdf_path).name) <= WINDOWS_COMPONENT_BUDGET
    persisted = json.loads(Path(outcome.candidates_path).read_text(encoding="utf-8"))
    assert persisted["pdf_path"] == outcome.pdf_path

    replay = candidate_orchestrator.run_candidate_extraction(
        settings,
        limit=1,
        ctx=run_context,
        dependencies=dependencies,
    )[0]
    assert replay.error is None
    assert replay.pdf_path == outcome.pdf_path
    assert downloads == [drive_file.file_id]

    source_reader = PdfReader(outcome.pdf_path, strict=False)
    output_dir = tmp_path / "ocr-readback"
    split_response = split_pdf_for_ocr(
        PdfOcrSplitRequest(
            schema_version="1.0",
            source_pdf_path=outcome.pdf_path,
            output_dir=str(output_dir),
            chunk_page_count=7,
        ),
        run_context,
    )
    expected_start = 1
    for chunk in split_response.chunks:
        assert chunk.source_pdf_path == outcome.pdf_path
        assert Path(chunk.chunk_pdf_path).is_file()
        assert windows_path_units(chunk.chunk_pdf_path) <= 240
        chunk_reader = PdfReader(chunk.chunk_pdf_path, strict=False)
        assert len(chunk_reader.pages) == chunk.page_count
        assert chunk.start_page_number == expected_start
        assert chunk.end_page_number == expected_start + chunk.page_count - 1
        for offset, chunk_page in enumerate(chunk_reader.pages):
            source_page = source_reader.pages[chunk.start_page_number - 1 + offset]
            assert chunk_page.mediabox == source_page.mediabox
            assert chunk_page.extract_text() == source_page.extract_text()
        expected_start = chunk.end_page_number + 1
    assert expected_start == len(source_reader.pages) + 1
