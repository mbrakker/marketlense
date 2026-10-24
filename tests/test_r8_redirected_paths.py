from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pymupdf as fitz
import pytest

from src.contracts.candidate_extraction import CandidateExtractOutcome
from src.contracts.drive import DriveFile
from src.contracts.files import (
    PipelineCheckpointWriteRequest,
    PipelineStageCheckpoint,
    ResolvePathWithinRootRequest,
)
from src.contracts.pdf_ocr import PdfOcrSplitRequest
from src.contracts.report_analysis import AnalysisPackPathRequest
from src.contracts.report_assets import (
    CropRefinePageRenderRequest,
    CropRequest,
    PreviewRequest,
)
from src.contracts.report_generation import ReportRuntimeState
from src.contracts.report_models import CropItem
from src.contracts.run_context import RunContext
from src.generators.pdf_text_ocr_generator import _ocr_cache_root
from src.generators.report_generation_shared import (
    cache_path,
    derive_title,
    report_slug,
)
from src.orchestrators import candidate_extraction_orchestrator, ingest_orchestrator
from src.services import file_service
from src.services._pdf.crop import (
    crop_regions,
    render_page_for_crop_refine,
    render_preview,
)
from src.services.pdf_service import split_pdf_for_ocr
from src.services.report_analysis_store_service import pack_path
from src.utils.errors import AppError
from src.utils.path_utils import safe_pdf_name


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _redirect_directory(link: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        link.symlink_to(target, target_is_directory=True)
        return
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"directory junction creation unavailable: {result.stderr}")


def _redirect_file(link: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"target")
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"file symlink creation unavailable: {exc}")


def _build_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=420, height=560)
    page.insert_text((40, 40), "R8 redirected-path test", fontsize=14)
    document.save(path.as_posix())
    document.close()


def _build_multi_page_pdf(path: Path, page_count: int = 3) -> None:
    document = fitz.open()
    for index in range(page_count):
        page = document.new_page(width=420, height=560)
        page.insert_text(
            (40, 40),
            f"R8 redirected-path test page {index + 1}",
            fontsize=14,
        )
    document.save(path.as_posix())
    document.close()


def _candidate_outcome(request) -> CandidateExtractOutcome:
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


def _checkpoint() -> PipelineStageCheckpoint:
    return PipelineStageCheckpoint(
        schema_version="1.0",
        pipeline_name="pipeline",
        file_id="file",
        report_slug="report",
        stage_name="stage",
        stage_status="completed",
        artifact_refs={},
        payload={"schema_version": "1.0"},
        completed_at_utc="2026-10-24T00:00:00+00:00",
        source_run_id="run",
        source_task_id="task",
    )


def test_resolve_path_within_root_rejects_a_file_symlink_alias(tmp_path: Path) -> None:
    root = tmp_path / "root"
    target = root / "target.txt"
    alias = root / "alias.txt"
    root.mkdir()
    target.write_bytes(b"target")
    _redirect_file(alias, target)

    response = file_service.resolve_path_within_root(
        ResolvePathWithinRootRequest(
            schema_version="1.0",
            root_dir=str(root),
            path=str(alias),
            reject_parent_components=False,
        ),
        _ctx(),
    )

    assert response.valid is False
    assert response.reason == "path_redirected"


def test_pipeline_checkpoint_rejects_a_redirected_child_before_write(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    _redirect_directory(root / ".checkpoints", outside)

    with pytest.raises(AppError) as exc_info:
        file_service.write_pipeline_checkpoint(
            PipelineCheckpointWriteRequest(
                schema_version="1.0",
                checkpoint_root=str(root),
                checkpoint=_checkpoint(),
            ),
            _ctx(),
        )

    assert exc_info.value.code == "pipeline_checkpoint_path_invalid"
    assert not list(outside.rglob("*.json"))


def test_cache_path_rejects_a_redirected_cache_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    _redirect_directory(root / "pdf_cache", outside)

    with pytest.raises(AppError) as exc_info:
        cache_path(root / "pdf_cache", "pdf_info", "a" * 64)

    assert exc_info.value.code == "report_cache_path_invalid"


def test_analysis_pack_path_rejects_a_redirected_report_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    _redirect_directory(root / "report", outside)

    with pytest.raises(AppError) as exc_info:
        pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=str(root),
                report_id="file",
                pack_name="doc_map",
                report_slug="report",
            ),
            _ctx(),
        )

    assert exc_info.value.code == "analysis_pack_path_invalid"


def test_crop_refine_rejects_a_redirected_report_directory(tmp_path: Path) -> None:
    pdf_path = tmp_path / "source.pdf"
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    _build_pdf(pdf_path)
    root.mkdir()
    _redirect_directory(root / "report", outside)

    with pytest.raises(AppError) as exc_info:
        render_page_for_crop_refine(
            CropRefinePageRenderRequest(
                schema_version="1.0",
                pdf_path=str(pdf_path),
                out_dir=str(root),
                report_name="report",
                page=0,
                dpi=96,
            ),
            _ctx(),
        )

    assert exc_info.value.code == "crop_refine_page_path_invalid"
    assert not list(outside.rglob("*"))


def test_preview_does_not_write_through_a_redirected_report_directory(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "source.pdf"
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    _build_pdf(pdf_path)
    root.mkdir()
    _redirect_directory(root / "report", outside)

    response = render_preview(
        PreviewRequest(
            schema_version="1.1",
            pdf_path=str(pdf_path),
            out_dir=str(root),
            report_name="report",
            page_number=0,
            dpi=96,
        ),
        _ctx(),
    )

    assert response.image_path is None
    assert not list(outside.rglob("*"))


def test_crop_regions_rejects_a_redirected_report_directory(tmp_path: Path) -> None:
    pdf_path = tmp_path / "source.pdf"
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    _build_pdf(pdf_path)
    root.mkdir()
    _redirect_directory(root / "report", outside)

    with pytest.raises(AppError) as exc_info:
        crop_regions(
            CropRequest(
                schema_version="1.0",
                pdf_path=str(pdf_path),
                out_dir=str(root),
                report_name="report",
                items=[
                    CropItem(
                        id="item-1",
                        type="chart",
                        score=1.0,
                        page=0,
                        bbox=(50.0, 50.0, 200.0, 200.0),
                    )
                ],
                subdir="slices",
                dpi=96,
            ),
            _ctx(),
        )

    assert exc_info.value.code == "crop_region_path_invalid"
    assert not list(outside.rglob("*"))


def test_candidate_cache_rejects_a_redirected_existing_file(
    ingest_settings,
    run_context,
    tmp_path: Path,
) -> None:
    source_pdf = tmp_path / "source.pdf"
    _build_pdf(source_pdf)
    content = source_pdf.read_bytes()
    drive_file = DriveFile(
        schema_version="1.0",
        file_id="redirected-candidate",
        name="source.pdf",
        modified_time=None,
        md5_checksum=hashlib.md5(content).hexdigest(),
    )
    cache_path, _ = candidate_extraction_orchestrator._candidate_cache_paths(
        drive_file,
        ingest_settings,
    )
    outside = tmp_path / "outside"
    target = outside / "candidate.pdf"
    _redirect_file(cache_path, target)
    target.write_bytes(content)

    with pytest.raises(AppError) as exc_info:
        candidate_extraction_orchestrator._download_if_needed(
            drive_file,
            ingest_settings,
            run_context,
            candidate_extraction_orchestrator.CandidateExtractionDependencies.default(),
        )

    assert exc_info.value.code == "candidate_cache_path_invalid"
    assert target.read_bytes() == content


def test_ingest_source_cache_rejects_a_redirected_existing_file(
    ingest_settings,
    tmp_path: Path,
) -> None:
    cache_path = Path(ingest_settings.cache_dir) / safe_pdf_name("redirected-source")
    outside = tmp_path / "outside"
    target = outside / "source.pdf"
    _redirect_file(cache_path, target)

    with pytest.raises(AppError) as exc_info:
        ingest_orchestrator._cache_pdf_path(
            ingest_settings,
            DriveFile(
                schema_version="1.0",
                file_id="redirected-source",
                name="source.pdf",
                modified_time=None,
                md5_checksum=None,
            ),
        )

    assert exc_info.value.code == "ingest_cache_path_invalid"
    assert target.read_bytes() == b"target"


def test_ocr_cache_root_rejects_a_redirected_cache_directory(
    ingest_settings,
    run_context,
    tmp_path: Path,
) -> None:
    cache_root = Path(ingest_settings.cache_dir)
    outside = tmp_path / "outside"
    _redirect_directory(cache_root / "pdf_cache", outside)
    file = DriveFile(
        schema_version="1.0",
        file_id="redirected-ocr",
        name="source.pdf",
        modified_time=None,
        md5_checksum="a" * 32,
    )
    runtime = ReportRuntimeState(
        schema_version="1.0",
        file=file,
        local_pdf_path=str(tmp_path / "source.pdf"),
        settings=ingest_settings,
        md5=file.md5_checksum,
        ctx=run_context,
        file_name=file.name,
        report_name=report_slug(file.name, file.file_id),
        report_title=derive_title(file.name),
        analysis_mode="vector_store",
        analysis_modes=["vector_store"],
        report_worker_limit=1,
        parallel_within_file=False,
    )

    with pytest.raises(AppError) as exc_info:
        _ocr_cache_root(runtime)

    assert exc_info.value.code == "pdf_text_ocr_path_invalid"
    assert not list(outside.rglob("*"))


def test_ocr_split_rejects_a_redirected_output_directory(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    output_dir = tmp_path / "ocr-chunks"
    outside = tmp_path / "outside"
    _build_multi_page_pdf(source_pdf)
    _redirect_directory(output_dir, outside)

    with pytest.raises(AppError) as exc_info:
        split_pdf_for_ocr(
            PdfOcrSplitRequest(
                schema_version="1.0",
                source_pdf_path=str(source_pdf),
                output_dir=str(output_dir),
                chunk_page_count=1,
            ),
            _ctx(),
        )

    assert exc_info.value.code == "pdf_ocr_split_path_invalid"
    assert not list(outside.rglob("*"))


def test_crop_regions_rejects_a_redirected_final_artifact(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "source.pdf"
    root = tmp_path / "root"
    _build_pdf(pdf_path)
    root.mkdir()
    request = CropRequest(
        schema_version="1.0",
        pdf_path=str(pdf_path),
        out_dir=str(root),
        report_name="report",
        items=[
            CropItem(
                id="item-1",
                type="chart",
                score=1.0,
                page=0,
                bbox=(50.0, 50.0, 200.0, 200.0),
            )
        ],
        subdir="slices",
        dpi=96,
    )
    initial = crop_regions(request, _ctx())
    output_path = root / initial.paths[0]
    outside = tmp_path / "outside"
    target = outside / "crop.png"
    output_path.unlink()
    _redirect_file(output_path, target)
    before = target.read_bytes()

    with pytest.raises(AppError) as exc_info:
        crop_regions(request, _ctx())

    assert exc_info.value.code == "crop_region_path_invalid"
    assert target.read_bytes() == before
