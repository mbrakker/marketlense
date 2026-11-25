from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from pypdf import PdfWriter

from src.contracts.candidate_extraction import CandidateExtractRequest
from src.contracts.candidates import Candidate
from src.contracts.report_assets import (
    CropResponse,
    ExtractCandidatesResponse,
    PdfCandidateExtractionStats,
    PdfDegradedPage,
)
from src.contracts.run_context import RunContext
from src.generators import candidate_extraction_generator as gen
from src.generators import report_selection_generator as selection
from src.generators.report_generation_dependencies import ReportSelectionDependencies


class _FakePdfContext:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _request(tmp_path, *, save_crops: bool = True) -> CandidateExtractRequest:
    return CandidateExtractRequest(
        schema_version="1.0",
        report_id="report_1",
        report_name="report-name",
        pdf_path=str(tmp_path / "report.pdf"),
        output_dir=str(tmp_path),
        subdir="candidates",
        save_crops=save_crops,
    )


def _candidates() -> list[Candidate]:
    return [
        Candidate(
            schema_version="1.0",
            id="c1",
            kind="chart",
            page=0,
            bbox=(1.0, 2.0, 10.0, 20.0),
            preview_text="candidate one",
        ),
        Candidate(
            schema_version="1.0",
            id="c2",
            kind="table",
            page=1,
            bbox=(2.0, 3.0, 11.0, 21.0),
            preview_text="candidate two",
        ),
    ]


def test_same_name_reports_write_distinct_candidate_artifacts(tmp_path):
    pdf_path = tmp_path / "report.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    with pdf_path.open("wb") as stream:
        writer.write(stream)
    request = _request(tmp_path, save_crops=False)
    first = gen.generate_candidate_pack(request, _ctx())
    second = gen.generate_candidate_pack(replace(request, report_id="report_2"), _ctx())

    assert first.candidates_path != second.candidates_path
    assert (
        json.loads(Path(first.candidates_path).read_text())["report_id"] == "report_1"
    )
    assert (
        json.loads(Path(second.candidates_path).read_text())["report_id"] == "report_2"
    )


def test_same_name_reports_use_distinct_thumbnail_and_crop_namespaces(
    tmp_path, external_boundary_mocks_only
):
    collected = []
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "build_pdf_context",
        lambda req, ctx: SimpleNamespace(context=None),
    )

    def collect(req, ctx):
        collected.append(req.report_name)
        return ExtractCandidatesResponse(
            schema_version="1.0", candidates=[_candidates()[0]]
        )

    def crop(req, ctx):
        return CropResponse(
            schema_version="1.0", paths=[f"{req.report_name}/candidates/c1.png"]
        )

    external_boundary_mocks_only.setattr(gen.pdf_service, "collect_candidates", collect)
    external_boundary_mocks_only.setattr(gen.pdf_service, "crop_regions", crop)
    request = _request(tmp_path)
    first = gen.generate_candidate_pack(request, _ctx())
    second = gen.generate_candidate_pack(replace(request, report_id="report_2"), _ctx())

    assert collected[0] != collected[1]
    assert first.crop_paths == [f"{collected[0]}/candidates/c1.png"]
    assert second.crop_paths == [f"{collected[1]}/candidates/c1.png"]
    assert Path(first.candidates_path).parent.parent.name == collected[0]
    assert Path(second.candidates_path).parent.parent.name == collected[1]


def test_selection_reads_candidate_pack_by_report_identity(
    tmp_path, ingest_settings, external_boundary_mocks_only
):
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "build_pdf_context",
        lambda req, ctx: SimpleNamespace(context=None),
    )
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "collect_candidates",
        lambda req, ctx: ExtractCandidatesResponse(
            schema_version="1.0", candidates=[_candidates()[0]]
        ),
    )
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "crop_regions",
        lambda req, ctx: CropResponse(
            schema_version="1.0", paths=[f"{req.report_name}/candidates/c1.png"]
        ),
    )
    request = replace(_request(tmp_path), output_dir=ingest_settings.output_dir)
    first = gen.generate_candidate_pack(request, _ctx())
    second = gen.generate_candidate_pack(replace(request, report_id="report_2"), _ctx())
    dependencies = ReportSelectionDependencies.default()

    for outcome in (first, second):
        result = selection._load_candidate_crop_path_map(
            settings=ingest_settings,
            report_name=outcome.report_name,
            report_id=outcome.report_id,
            ctx=_ctx(),
            dependencies=dependencies,
        )
        assert result == {"c1": outcome.crop_paths[0]}


def test_selection_rejects_legacy_and_mismatched_candidate_packs(ingest_settings):
    legacy = (
        Path(ingest_settings.output_dir)
        / "report-name"
        / "candidates"
        / "candidates.json"
    )
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps(
            {
                "report_id": "report_1",
                "candidates": [
                    {"id": "c1", "crop_path": "report-name/candidates/c1.png"}
                ],
            }
        ),
        encoding="utf-8",
    )
    dependencies = ReportSelectionDependencies.default()
    kwargs = {
        "settings": ingest_settings,
        "report_name": "report-name",
        "report_id": "report_1",
        "ctx": _ctx(),
        "dependencies": dependencies,
    }
    assert selection._load_candidate_crop_path_map(**kwargs) == {}

    assert (
        selection._candidate_extraction_output_path(ingest_settings, "report-name")
        == legacy
    )
    assert (
        selection._load_candidate_crop_path_map(
            settings=ingest_settings,
            report_name="report-name",
            ctx=_ctx(),
            dependencies=dependencies,
        )
        == {}
    )
    canonical = selection._candidate_extraction_output_path(
        ingest_settings, "report-name", report_id="report_1"
    )
    canonical.parent.mkdir(parents=True)
    canonical.write_text(
        json.dumps(
            {
                "report_id": "report_2",
                "candidates": [{"id": "c1", "crop_path": "wrong-source.png"}],
            }
        ),
        encoding="utf-8",
    )
    assert selection._load_candidate_crop_path_map(**kwargs) == {}
    assert legacy.exists()


def test_generate_candidate_pack_success_with_crops(
    tmp_path,
    external_boundary_mocks_only,
):
    pdf_ctx = _FakePdfContext()
    written: dict[str, object] = {}

    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "build_pdf_context",
        lambda req, ctx: SimpleNamespace(context=pdf_ctx),
    )
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "collect_candidates",
        lambda req, ctx: ExtractCandidatesResponse(
            schema_version="1.0",
            candidates=_candidates(),
        ),
    )
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "crop_regions",
        lambda req, ctx: CropResponse(
            schema_version="1.0",
            paths=["candidates/c1.png", "candidates/c2.png"],
        ),
    )

    def _write_bytes(req, ctx):
        written["path"] = req.path
        written["content"] = req.content
        return SimpleNamespace(path=req.path)

    external_boundary_mocks_only.setattr(
        gen.file_service,
        "write_bytes",
        _write_bytes,
    )

    outcome = gen.generate_candidate_pack(_request(tmp_path, save_crops=True), _ctx())

    assert outcome.error is None
    assert outcome.candidate_count == 2
    assert outcome.chart_count == 1
    assert outcome.table_count == 1
    assert outcome.crop_count == 2
    assert outcome.crop_paths == ["candidates/c1.png", "candidates/c2.png"]
    assert isinstance(written.get("path"), str)
    payload = json.loads((written.get("content") or b"{}").decode("utf-8"))
    assert payload["candidate_count"] == 2
    assert payload["candidates"][0]["crop_path"] == "candidates/c1.png"
    assert pdf_ctx.closed is True


def test_generate_candidate_pack_maps_crop_outcomes_by_candidate_id(
    tmp_path,
    external_boundary_mocks_only,
):
    written: dict[str, object] = {}

    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "build_pdf_context",
        lambda req, ctx: SimpleNamespace(context=None),
    )
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "collect_candidates",
        lambda req, ctx: ExtractCandidatesResponse(
            schema_version="1.0",
            candidates=_candidates(),
        ),
    )
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "crop_regions",
        lambda req, ctx: CropResponse(
            schema_version="1.0",
            paths=["candidates/c2.png"],
            outcomes=[
                SimpleNamespace(
                    candidate_id="c1",
                    path="",
                    accepted=False,
                    qa_sidecar_path="candidates/c1.png.qa.json",
                    score=41.0,
                    defects=["low_information"],
                    rejection_reason="low_information",
                    quality_profile="publication_strict",
                ),
                SimpleNamespace(
                    candidate_id="c2",
                    path="candidates/c2.png",
                    accepted=True,
                    qa_sidecar_path="candidates/c2.png.qa.json",
                    score=94.0,
                    defects=[],
                    rejection_reason="",
                    quality_profile="publication_strict",
                ),
            ],
        ),
    )
    external_boundary_mocks_only.setattr(
        gen.file_service,
        "write_bytes",
        lambda req, ctx: (
            written.update({"path": req.path, "content": req.content})
            or SimpleNamespace(path=req.path)
        ),
    )

    outcome = gen.generate_candidate_pack(_request(tmp_path, save_crops=True), _ctx())

    assert outcome.crop_paths == ["candidates/c2.png"]
    payload = json.loads((written.get("content") or b"{}").decode("utf-8"))
    assert payload["candidates"][0]["crop_path"] == ""
    assert payload["candidates"][0]["crop_qa_accepted"] is False
    assert payload["candidates"][0]["crop_qa_score"] == 41.0
    assert payload["candidates"][0]["crop_qa_defects"] == ["low_information"]
    assert payload["candidates"][1]["crop_path"] == "candidates/c2.png"
    assert payload["candidates"][1]["crop_qa_accepted"] is True
    assert (
        payload["candidates"][1]["crop_qa_sidecar_path"] == "candidates/c2.png.qa.json"
    )


def test_generate_candidate_pack_persists_degraded_page_reasons(
    tmp_path,
    external_boundary_mocks_only,
):
    written: dict[str, object] = {}
    degraded_page = PdfDegradedPage(
        schema_version="1.0",
        page=0,
        stage="triage",
        reason_code="pdf_candidate_page_triage_failed",
        policy="include_with_warning",
        message="triage failed",
    )
    candidate = Candidate(
        schema_version="1.0",
        id="c1",
        kind="chart",
        page=0,
        bbox=(1.0, 2.0, 10.0, 20.0),
        preview_text="candidate one",
        meta={
            "degraded_page_reasons": [
                {
                    "stage": degraded_page.stage,
                    "reason_code": degraded_page.reason_code,
                    "policy": degraded_page.policy,
                    "message": degraded_page.message,
                }
            ]
        },
    )
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "build_pdf_context",
        lambda req, ctx: (_ for _ in ()).throw(RuntimeError("context failed")),
    )
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "collect_candidates",
        lambda req, ctx: ExtractCandidatesResponse(
            schema_version="1.0",
            candidates=[candidate],
            stats=PdfCandidateExtractionStats(
                schema_version="1.0",
                degraded_pages=[degraded_page],
                triage_failure_count=1,
                extraction_failure_count=0,
            ),
        ),
    )
    external_boundary_mocks_only.setattr(
        gen.file_service,
        "write_bytes",
        lambda req, ctx: (
            written.update({"path": req.path, "content": req.content})
            or SimpleNamespace(path=req.path)
        ),
    )

    outcome = gen.generate_candidate_pack(_request(tmp_path, save_crops=False), _ctx())

    assert outcome.candidate_count == 1
    payload = json.loads((written.get("content") or b"{}").decode("utf-8"))
    assert payload["degraded_pages"][0]["reason_code"] == degraded_page.reason_code
    assert (
        payload["candidates"][0]["meta"]["degraded_page_reasons"][0]["reason_code"]
        == degraded_page.reason_code
    )


def test_generate_candidate_pack_continues_when_pdf_context_build_fails(
    tmp_path,
    external_boundary_mocks_only,
):
    written: dict[str, object] = {}
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "build_pdf_context",
        lambda req, ctx: (_ for _ in ()).throw(RuntimeError("context failed")),
    )
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "collect_candidates",
        lambda req, ctx: ExtractCandidatesResponse(
            schema_version="1.0",
            candidates=[_candidates()[0]],
        ),
    )
    external_boundary_mocks_only.setattr(
        gen.file_service,
        "write_bytes",
        lambda req, ctx: (
            written.update({"path": req.path, "content": req.content})
            or SimpleNamespace(path=req.path)
        ),
    )

    outcome = gen.generate_candidate_pack(_request(tmp_path, save_crops=False), _ctx())

    assert outcome.error is None
    assert outcome.candidate_count == 1
    assert outcome.crop_count == 0
    payload = json.loads((written.get("content") or b"{}").decode("utf-8"))
    assert payload["chart_count"] == 1
    assert payload["table_count"] == 0


def test_generate_candidate_pack_sanitizes_output_path_segments(
    tmp_path,
    external_boundary_mocks_only,
):
    written: dict[str, object] = {}
    request = CandidateExtractRequest(
        schema_version="1.0",
        report_id="report_1",
        report_name="../escape",
        pdf_path=str(tmp_path / "report.pdf"),
        output_dir=str(tmp_path / "out"),
        subdir="../candidates",
        save_crops=False,
    )
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "build_pdf_context",
        lambda req, ctx: (_ for _ in ()).throw(RuntimeError("context failed")),
    )
    external_boundary_mocks_only.setattr(
        gen.pdf_service,
        "collect_candidates",
        lambda req, ctx: ExtractCandidatesResponse(
            schema_version="1.0",
            candidates=[_candidates()[0]],
        ),
    )
    external_boundary_mocks_only.setattr(
        gen.file_service,
        "write_bytes",
        lambda req, ctx: (
            written.update({"path": req.path, "content": req.content})
            or SimpleNamespace(path=req.path)
        ),
    )

    outcome = gen.generate_candidate_pack(request, _ctx())
    expected_path = (
        tmp_path
        / "out"
        / "candidate-eb8584b81bf45732f5a230fbf89114e06c92c6ac1ba488c879ca117519dca64b"
        / "candidates"
        / "candidates.json"
    )

    assert outcome.candidates_path == str(expected_path)
    assert written["path"] == str(expected_path)
