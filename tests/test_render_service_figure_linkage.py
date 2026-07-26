from pathlib import Path

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
