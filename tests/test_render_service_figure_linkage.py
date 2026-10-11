import json
import logging
from pathlib import Path

import pymupdf as fitz
import pytest

from src.contracts.report_assets import CropRequest, RenderRequest
from src.contracts.report_models import CropItem
from src.contracts.run_context import RunContext
from src.services.pdf_service import crop_regions
from src.services.render_service import render_report


def _ctx():
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _strict_crop(
    tmp_path: Path, candidate_id: str = "approved-chart"
) -> dict[str, object]:
    pdf_path = tmp_path / "source-report.pdf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=560)
    page.insert_text((40, 40), "Market report crop proof", fontsize=14)
    page.draw_rect(
        fitz.Rect(60, 90, 360, 280), color=(0, 0, 0), fill=(0.94, 0.94, 0.94)
    )
    doc.save(pdf_path.as_posix())
    doc.close()

    response = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=tmp_path.as_posix(),
            report_name="report",
            items=[
                CropItem(
                    id=candidate_id,
                    type="figure",
                    score=90.0,
                    page=0,
                    bbox=(45.0, 75.0, 375.0, 305.0),
                )
            ],
            subdir="slices",
            pad=0,
            mode="publication_strict",
            dpi=216,
        ),
        _ctx(),
    )
    outcome = response.outcomes[0]
    assert outcome.accepted is True
    return {
        "image_path": outcome.path,
        "page": 0,
        "candidate_id": candidate_id,
        "kind": "figure",
        "crop_qa_accepted": outcome.accepted,
        "crop_qa_sidecar_path": outcome.qa_sidecar_path,
        "crop_quality_profile": outcome.quality_profile,
        "crop_dpi": outcome.dpi,
        "crop_image_sha256": outcome.image_sha256,
    }


def _render_data(asset: dict[str, object], candidate_id: str) -> dict[str, object]:
    return {
        "title": "Figure Proof Report",
        "tldr": "TLDR",
        "insights": ["Insight A"] * 5,
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "_figure_assets": [asset],
        "artifacts": {
            "chart_insight_cards": [
                {
                    "candidate_id": candidate_id,
                    "status": "generated",
                    "crop_qa_accepted": True,
                    "evidence_id": "evidence-1",
                    "insight_id": "insight-1",
                    "caption": "Approved figure",
                    "public_takeaway": "A supported takeaway.",
                    "source_page": 0,
                }
            ]
        },
    }


def _render(tmp_path: Path, data: dict[str, object], *, final_crop_dpi: int = 216):
    return render_report(
        RenderRequest(
            schema_version="1.0",
            data=data,
            doc_name="figure-proof.pdf",
            file_id="file_figure_proof",
            out_dir=str(tmp_path),
            preview_png=None,
            final_crop_dpi=final_crop_dpi,
        ),
        _ctx(),
    )


def test_render_omits_unaccepted_or_unlinked_figure_assets(tmp_path):
    data = {
        "title": "Figure Safety Report",
        "tldr": "TLDR",
        "insights": ["Insight A"] * 5,
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "_figure_assets": [
            {
                "image_path": "report/slices/rejected.png",
                "page": 2,
                "candidate_id": "rejected-chart",
                "crop_qa_accepted": False,
            },
            {
                "image_path": "report/slices/unlinked.png",
                "page": 3,
                "candidate_id": "unlinked-chart",
                "crop_qa_accepted": True,
            },
        ],
        "artifacts": {"chart_insight_cards": []},
    }

    response = _render(tmp_path, data)
    html = Path(response.html_path).read_text(encoding="utf-8")

    assert 'id="candidates"' not in html
    assert "rejected.png" not in html
    assert "unlinked.png" not in html


def test_render_accepts_a_real_publication_strict_crop(tmp_path):
    asset = _strict_crop(tmp_path)

    response = _render(tmp_path, _render_data(asset, "approved-chart"))

    assert asset["image_path"] in Path(response.html_path).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "mutation,expected_reason",
    [
        ("missing", "qa_sidecar_missing"),
        ("tampered", "fingerprint_content_hash_mismatch"),
        ("rejected_status", "qa_not_accepted"),
        ("wrong_profile", "qa_profile_mismatch"),
        ("wrong_dpi", "qa_dpi_mismatch"),
        ("modified_image", "crop_image_hash_mismatch"),
        ("candidate_mismatch", "qa_candidate_mismatch"),
        ("fractional_dpi", "crop_dpi_invalid"),
        ("fractional_page", "source_page_invalid"),
        ("sidecar_path_mismatch", "qa_sidecar_path_mismatch"),
        ("other_candidate_sidecar", "qa_sidecar_path_mismatch"),
        ("configured_dpi_mismatch", "configured_crop_dpi_mismatch"),
    ],
)
def test_render_rejects_invalid_crop_qa_proof_with_a_reason(
    tmp_path: Path, caplog, mutation: str, expected_reason: str
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.render_service")
    asset = _strict_crop(tmp_path)
    sidecar = tmp_path / str(asset["crop_qa_sidecar_path"])
    if mutation == "missing":
        sidecar.unlink()
    elif mutation == "tampered":
        qa = json.loads(sidecar.read_text(encoding="utf-8"))
        qa["rejection_reason"] = "tampered"
        sidecar.write_text(json.dumps(qa), encoding="utf-8")
    elif mutation == "rejected_status":
        qa = json.loads(sidecar.read_text(encoding="utf-8"))
        qa["accepted"] = False
        qa["qa"]["accepted"] = False
        qa["qa"]["defect_labels"] = ["neighbor_contamination"]
        sidecar.write_text(json.dumps(qa), encoding="utf-8")
    elif mutation == "wrong_profile":
        qa = json.loads(sidecar.read_text(encoding="utf-8"))
        qa["mode"] = "legacy"
        sidecar.write_text(json.dumps(qa), encoding="utf-8")
    elif mutation == "wrong_dpi":
        qa = json.loads(sidecar.read_text(encoding="utf-8"))
        qa["render_dpi"] = 110
        sidecar.write_text(json.dumps(qa), encoding="utf-8")
    elif mutation == "modified_image":
        image_path = tmp_path / str(asset["image_path"])
        image_path.write_bytes(image_path.read_bytes() + b"tampered")
    elif mutation == "candidate_mismatch":
        qa = json.loads(sidecar.read_text(encoding="utf-8"))
        qa["candidate_id"] = "another-candidate"
        sidecar.write_text(json.dumps(qa), encoding="utf-8")
    elif mutation == "fractional_dpi":
        asset["crop_dpi"] = 216.5
    elif mutation == "fractional_page":
        asset["page"] = 0.5
    elif mutation == "other_candidate_sidecar":
        other_asset = _strict_crop(tmp_path, candidate_id="another-candidate")
        asset["crop_qa_sidecar_path"] = other_asset["crop_qa_sidecar_path"]
    else:
        asset["crop_qa_sidecar_path"] = "report/slices/other.png.qa.json"

    response = _render(
        tmp_path,
        _render_data(asset, "approved-chart"),
        final_crop_dpi=288 if mutation == "configured_dpi_mismatch" else 216,
    )
    html = Path(response.html_path).read_text(encoding="utf-8")
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.render_service"
    ]
    filtered = next(
        event
        for event in events
        if event.get("event") == "render_publication_crops_filtered"
    )

    assert str(asset["image_path"]) not in html
    assert filtered["fields"]["accepted_count"] == 0
    assert filtered["fields"]["rejection_reasons"] == {expected_reason: 1}
