# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pymupdf as fitz
import pytest

from src.contracts.files import (
    PipelineCheckpointReadRequest,
    PipelineCheckpointWriteRequest,
    PipelineStageCheckpoint,
)
from src.contracts.report_assets import RenderRequest
from src.services.file_service import (
    read_pipeline_checkpoint,
    write_pipeline_checkpoint,
)
from src.services.pdf_service import crop_regions
from src.services.render_service import render_report

from ._shared import *  # noqa: F401,F403


def test_publication_crop_proof_survives_selection_checkpoint_and_render(tmp_path):
    pdf_path = tmp_path / "selection-proof.pdf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=560)
    page.insert_text((65, 105), "Annual growth by region", fontsize=16)
    page.draw_line((75, 390), (350, 390), color=(0, 0, 0), width=2)
    page.draw_line((75, 150), (75, 390), color=(0, 0, 0), width=2)
    for index, (x, height, label) in enumerate(
        ((110, 120, "North"), (180, 170, "South"), (250, 95, "West"))
    ):
        page.draw_rect(
            fitz.Rect(x, 390 - height, x + 35, 390),
            color=(0.1, 0.35, 0.7),
            fill=(0.2, 0.5, 0.85),
        )
        page.insert_text((x - 3, 410), label, fontsize=9)
        page.insert_text((x, 390 - height - 8), f"{50 + index * 10}%", fontsize=9)
    doc.save(pdf_path.as_posix())
    doc.close()

    settings = _settings(
        tmp_path,
        output_dir=str(tmp_path),
        crop_refine_enabled=False,
        crop_refine_mode="off",
        final_crop_dpi=216,
        rank_selected_max=1,
        rank_max_candidates=4,
    )
    candidate = _candidate(
        cid="chart-1",
        kind="chart",
        page=0,
        bbox=(45.0, 75.0, 385.0, 435.0),
        caption="Annual growth by region",
        meta={"area_frac": 0.2, "text_ratio": 0.2},
    )
    deps = _deps(
        collect_candidates=lambda req, ctx: SimpleNamespace(candidates=[candidate]),
        extract_best_figure=lambda req, ctx: pytest.fail(
            "candidate crop selection must not publish a legacy bitmap"
        ),
        read_json_object_cache=lambda req, ctx: SimpleNamespace(
            found=False, payload={}
        ),
        rank_candidates=lambda req, ctx: SimpleNamespace(
            results=[
                RankedCandidate(
                    id="chart-1",
                    type="chart",
                    score=98,
                    quality_score=98,
                    insight_score=98,
                    data_score=98,
                    keep=True,
                )
            ],
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            request_id="rank",
            raw_content="[]",
        ),
        crop_regions=crop_regions,
    )
    payload = ReportPayload(
        tldr="Grounded summary.",
        title="Report",
        insights=["Supported insight."],
        quote=Quote(text="Source quote", author="Source speaker"),
        figure=Figure(title="Annual growth by region", evidence="chart-1"),
        commentary="Grounded commentary.",
        source="https://example.test/report",
    )
    runtime = SimpleNamespace(
        local_pdf_path=pdf_path.as_posix(),
        settings=settings,
        report_name="report",
        file=SimpleNamespace(file_id="file-proof"),
        md5=None,
        ctx=_ctx(),
        report_worker_limit=1,
        parallel_within_file=False,
    )
    source = SimpleNamespace(
        payload=payload,
        contents_page_number=0,
        pdf_context=None,
        pdf_context_for_tasks=None,
    )

    selection = rsg.select_report_figures(runtime, source, deps)
    assert len(selection.payload._figure_assets) == 1
    selected_asset = selection.payload._figure_assets[0]
    assert selected_asset.crop_qa_accepted is True
    assert selected_asset.crop_dpi == 216
    assert selected_asset.crop_quality_profile == "publication_strict"

    checkpoint_data = selection.payload.to_dict()
    checkpoint_data["artifacts"] = {
        "chart_insight_cards": [
            {
                "candidate_id": "chart-1",
                "status": "generated",
                "crop_qa_accepted": True,
                "evidence_id": "evidence-1",
                "insight_id": "insight-1",
                "caption": "Annual growth by region",
                "public_takeaway": "Growth varies by region.",
                "source_page": 0,
            }
        ]
    }
    checkpoint = PipelineStageCheckpoint(
        schema_version="1.0",
        pipeline_name="report_pipeline",
        file_id="file-proof",
        report_slug="report",
        stage_name="selection_complete",
        stage_status="completed",
        artifact_refs={},
        payload={"data": checkpoint_data},
        completed_at_utc="2026-10-08T00:00:00Z",
        source_run_id="run",
        source_task_id="task",
    )
    write_pipeline_checkpoint(
        PipelineCheckpointWriteRequest(
            schema_version="1.0",
            checkpoint_root=str(tmp_path / "checkpoints"),
            checkpoint=checkpoint,
        ),
        _ctx(),
    )
    restored = read_pipeline_checkpoint(
        PipelineCheckpointReadRequest(
            schema_version="1.0",
            checkpoint_root=str(tmp_path / "checkpoints"),
            pipeline_name="report_pipeline",
            file_id="file-proof",
            stage_name="selection_complete",
        ),
        _ctx(),
    )
    assert restored.found is True
    assert restored.checkpoint is not None
    round_trip_data = restored.checkpoint.payload["data"]
    assert round_trip_data["_figure_assets"][0]["crop_qa_sidecar_path"] == (
        selected_asset.crop_qa_sidecar_path
    )

    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data=round_trip_data,
            doc_name="report.pdf",
            file_id="file-proof",
            out_dir=str(tmp_path),
            preview_png=None,
            final_crop_dpi=216,
        ),
        _ctx(),
    )
    html = Path(response.html_path).read_text(encoding="utf-8")
    assert selected_asset.image_path in html


__all__ = ["test_publication_crop_proof_survives_selection_checkpoint_and_render"]
