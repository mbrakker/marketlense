from __future__ import annotations

from pathlib import Path

from src.contracts.report_assets import RenderRequest
from src.services.render_service import render_report
from tests.test_render_service_artifacts import _ctx


def test_render_overwrites_existing_html_atomically(tmp_path: Path) -> None:
    first = RenderRequest(
        schema_version="1.0",
        data={
            "title": "First Title",
            "tldr": "TLDR",
            "insights": [
                "Insight A",
                "Insight B",
                "Insight C",
                "Insight D",
                "Insight E",
            ],
            "quote": {"text": "Quote", "author": "Author"},
            "commentary": "Commentary",
            "publisher": "Publisher",
            "taxonomy": ["tag"],
            "region": "US",
            "time_period": "2024",
            "contents_page_number": 0,
        },
        doc_name="overwrite.pdf",
        file_id="file_overwrite",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    second = RenderRequest(
        schema_version="1.0",
        data={**first.data, "title": "Second Title"},
        doc_name=first.doc_name,
        file_id=first.file_id,
        out_dir=first.out_dir,
        preview_png=None,
    )

    first_response = render_report(first, _ctx())
    second_response = render_report(second, _ctx())

    html = Path(second_response.html_path).read_text(encoding="utf-8")
    assert first_response.html_path == second_response.html_path
    assert "Second Title" in html
    assert "First Title" not in html
