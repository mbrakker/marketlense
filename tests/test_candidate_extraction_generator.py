from __future__ import annotations

import json
from types import SimpleNamespace

from src.contracts.candidate_extraction import CandidateExtractRequest
from src.contracts.candidates import Candidate
from src.contracts.report_assets import CropResponse, ExtractCandidatesResponse
from src.contracts.run_context import RunContext
from src.generators import candidate_extraction_generator as gen


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


def test_generate_candidate_pack_success_with_crops(tmp_path, monkeypatch):
    pdf_ctx = _FakePdfContext()
    written: dict[str, object] = {}

    monkeypatch.setattr(
        gen,
        "build_pdf_context",
        lambda req, ctx: SimpleNamespace(context=pdf_ctx),
    )
    monkeypatch.setattr(
        gen,
        "collect_candidates_service",
        lambda req, ctx: ExtractCandidatesResponse(
            schema_version="1.0",
            candidates=_candidates(),
        ),
    )
    monkeypatch.setattr(
        gen,
        "crop_regions_service",
        lambda req, ctx: CropResponse(
            schema_version="1.0",
            paths=["candidates/c1.png", "candidates/c2.png"],
        ),
    )

    def _write_bytes(req, ctx):
        written["path"] = req.path
        written["content"] = req.content
        return SimpleNamespace(path=req.path)

    monkeypatch.setattr(gen, "write_bytes", _write_bytes)

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


def test_generate_candidate_pack_continues_when_pdf_context_build_fails(
    tmp_path, monkeypatch
):
    written: dict[str, object] = {}
    monkeypatch.setattr(
        gen,
        "build_pdf_context",
        lambda req, ctx: (_ for _ in ()).throw(RuntimeError("context failed")),
    )
    monkeypatch.setattr(
        gen,
        "collect_candidates_service",
        lambda req, ctx: ExtractCandidatesResponse(
            schema_version="1.0",
            candidates=[_candidates()[0]],
        ),
    )
    monkeypatch.setattr(
        gen,
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
