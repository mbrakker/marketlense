from pathlib import Path

from src.contracts.report_assets import RenderRequest
from src.contracts.run_context import RunContext
from src.services.render_service import render_report


def test_render_is_deterministic_across_calls(tmp_path):
    data = {
        "title": "Deterministic Report",
        "tldr": "TLDR",
        "insights": ["Insight A", "Insight B", "Insight C", "Insight D", "Insight E"],
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["roi"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 0,
    }
    request = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="deterministic.pdf",
        file_id="file_deterministic",
        out_dir=str(tmp_path),
        preview_png=None,
        tag_acronyms=["ROI"],
    )
    context = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

    first = render_report(request, context)
    second = render_report(request, context)

    first_html = Path(first.html_path).read_text(encoding="utf-8")
    second_html = Path(second.html_path).read_text(encoding="utf-8")
    assert first.html_path == second.html_path
    assert first_html == second_html
