from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.generators.report_render_generator import (
    render_preview_asset,
    render_report_output,
)
from src.utils.errors import AppError
from tests.test_report_render_generator import (
    _analysis,
    _cover_assets,
    _deps,
    _runtime,
    _selection,
    _source,
)


def test_render_report_output_propagates_retryable_manifest_write_error(
    tmp_path,
    assert_app_error,
):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    def _write_manifest(req, ctx):
        del req, ctx
        raise AppError(
            code="report_card_manifest_write_failed",
            message="temporary storage outage",
            retryable=True,
        )

    deps = _deps(
        render_report=_render_report,
        generate_cover_images=lambda req, ctx: [
            SimpleNamespace(
                schema_version="2.0",
                file_id=runtime.file.file_id,
                title="DB Title",
                status="generated",
                assets=_cover_assets(runtime),
                error=None,
            )
        ],
        write_report_card_manifest=_write_manifest,
    )

    with pytest.raises(AppError) as err:
        render_report_output(
            runtime,
            source,
            selection,
            analysis,
            deps,
            preview_resp=render_preview_asset(runtime, source, deps),
        )

    assert_app_error(
        err.value,
        code="report_card_manifest_write_failed",
        retryable=True,
        severity="error",
    )
