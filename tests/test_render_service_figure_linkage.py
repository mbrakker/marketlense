from pathlib import Path
import hashlib

from PIL import Image

from src.contracts.report_assets import RenderRequest
from src.contracts.run_context import RunContext
from src.services.render_service import render_report


def _ctx():
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


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

    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data=data,
            doc_name="figure-safety.pdf",
            file_id="file_figure_safety",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )
    html = Path(response.html_path).read_text(encoding="utf-8")

    assert 'id="candidates"' not in html
    assert "rejected.png" not in html
    assert "unlinked.png" not in html


def test_render_requires_matching_final_crop_image_hash(tmp_path):
    image_path = tmp_path / "report" / "slices" / "approved.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (16, 12), color="white").save(image_path)
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    sidecar_path = "report/slices/approved.png.qa.json"
    (tmp_path / sidecar_path).write_text('{"accepted":true}', encoding="utf-8")
    data = {
        "title": "Figure Proof Report",
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
                "image_path": "report/slices/approved.png",
                "page": 2,
                "candidate_id": "approved-chart",
                "crop_qa_accepted": True,
                "crop_qa_sidecar_path": sidecar_path,
                "crop_quality_profile": "publication_strict",
                "crop_dpi": 216,
                "crop_image_sha256": image_sha256,
            }
        ],
        "artifacts": {
            "chart_insight_cards": [
                {
                    "candidate_id": "approved-chart",
                    "status": "generated",
                    "crop_qa_accepted": True,
                    "evidence_id": "evidence-1",
                    "insight_id": "insight-1",
                    "caption": "Approved chart",
                    "public_takeaway": "A supported takeaway.",
                    "source_page": 2,
                }
            ]
        },
    }

    first = render_report(
        RenderRequest(
            schema_version="1.0",
            data=data,
            doc_name="figure-proof.pdf",
            file_id="file_figure_proof",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )
    assert "approved.png" in Path(first.html_path).read_text(encoding="utf-8")

    image_path.write_bytes(image_path.read_bytes() + b"tampered")
    second = render_report(
        RenderRequest(
            schema_version="1.0",
            data=data,
            doc_name="figure-proof.pdf",
            file_id="file_figure_proof",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )
    assert "approved.png" not in Path(second.html_path).read_text(encoding="utf-8")
