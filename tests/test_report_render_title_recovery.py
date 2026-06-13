from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from src.generators.report_render_generator import render_report_output
from tests.test_report_render_generator import (
    _analysis,
    _deps,
    _runtime,
    _selection,
    _source,
)


def test_render_report_output_recovers_opaque_title_from_pdf_metadata(tmp_path):
    expected_title = "Activate Technology & Media Outlook 2018"
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    source = replace(
        source,
        info_response=replace(source.info_response, metadata={"Title": expected_title}),
    )
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    opaque_title = "d8ca0bf6efb9c703343867f6df0f26a2553aa78f"
    analysis = replace(
        analysis,
        payload=replace(analysis.payload, title=opaque_title),
        data_dict={**analysis.data_dict, "title": opaque_title},
    )
    stored = {}
    html_path = tmp_path / "out" / "report.html"
    html_path.parent.mkdir(parents=True)

    def _upsert(req, ctx):
        del ctx
        stored["request"] = req

    def _get_metadata(req, ctx):
        del req, ctx
        return replace(
            _deps().get_report_metadata(None, None),
            title=stored["request"].title,
        )

    def _render(req, ctx):
        del ctx
        assert req.data["title"] == expected_title
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        _deps(
            upsert_report_metadata=_upsert,
            get_report_metadata=_get_metadata,
            render_report=_render,
        ),
        preview_resp=SimpleNamespace(image_path="preview.png"),
    )

    assert stored["request"].title == expected_title
    assert outcome.html_path == str(html_path)
    assert Path(outcome.html_path).exists()
