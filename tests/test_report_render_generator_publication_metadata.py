from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.report_cards import ReportCardManifestWriteResponse
from src.contracts.report_store import (
    SourceIdentityResolution,
    SourcePublicationMetadata,
)
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


def test_render_report_output_writes_verified_source_date_to_complete_manifest(
    tmp_path,
):
    runtime = replace(
        _runtime(tmp_path, md5="md5"),
        source_publication_metadata=SourcePublicationMetadata(
            schema_version="1.0",
            source_record_id=7,
            publication_date="2026-06-09",
            publication_date_precision="day",
            source_url="https://publisher.example/report",
            retrieved_at_utc="2026-06-10T08:30:00Z",
            evidence_kind="json_ld_date_published",
            evidence_locator="json_ld[0].datePublished",
            evidence_value_hash="source-date-sha",
            evidence_status="verified",
            contradiction_status="none",
        ),
        source_identity=SourceIdentityResolution(
            schema_version="1.0",
            source_record_id=7,
            source_identity_id="source:verified",
            canonical_title="Publisher Evidence Report",
            publisher_name="Publisher Example",
            canonical_landing_page_url="https://publisher.example/report",
            publication_date="2026-06-09",
            publication_date_status="verified",
            retrieved_at_utc="2026-06-10T08:30:00Z",
            content_hash="md5:md5",
            resolution_method="publisher_evidence_preferred",
            identity_confidence="high",
            identity_status="resolved",
            source_metadata_hash="source-metadata-hash",
            observation_count=1,
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    captured = {}
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del ctx
        captured["render_data"] = dict(req.data)
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    def _generate_covers(req, ctx):
        del ctx
        captured["cover_request"] = req
        return [
            SimpleNamespace(
                schema_version="2.0",
                file_id=runtime.file.file_id,
                title="DB Title",
                status="generated",
                assets=_cover_assets(runtime),
                error=None,
            )
        ]

    def _write_manifest(req, ctx):
        del ctx
        captured["manifest_request"] = req
        return ReportCardManifestWriteResponse(
            schema_version="1.0",
            manifest_path=str(Path(req.output_dir) / "report-card-manifest.json"),
            bytes_written=2048,
        )

    deps = _deps(
        render_report=_render_report,
        generate_cover_images=_generate_covers,
        write_report_card_manifest=_write_manifest,
    )
    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    manifest_request = captured["manifest_request"]
    manifest = manifest_request.manifest
    assert captured["cover_request"].reports[0].fingerprint == manifest.fingerprint
    assert manifest_request.output_dir == str(
        Path(runtime.settings.output_dir) / runtime.report_name
    )
    assert manifest.published_date == "2026-06-09"
    assert manifest.tldr_compact.endswith(".")
    assert manifest.tldr_standard.endswith(".")
    assert manifest.key_insights == (
        "Channel efficiency improved across the measured period.",
        "Investment shifted toward higher-return customer segments.",
    )
    assert manifest.covers.small.output_path == "assets/report-card-small.png"
    assert manifest.covers.medium.output_path == "assets/report-card-medium.png"
    assert manifest.covers.large.output_path == "assets/report-card-large.png"
    assert manifest.source_title == "Publisher Evidence Report"
    assert manifest.source_url == "https://publisher.example/report"
    assert (
        manifest.source_note == "Source: Publisher Example — Publisher Evidence Report"
    )
    assert manifest.source_metadata_hash == "source-metadata-hash"
    assert manifest.source_identity_status == "resolved"
    assert manifest.source_publication_date_status == "verified"
    assert captured["render_data"]["source_publication_date"] == "2026-06-09"
    assert outcome.schema_version == "1.1"
    assert outcome.report_card_manifest_path == str(
        Path(runtime.settings.output_dir)
        / runtime.report_name
        / "report-card-manifest.json"
    )


def test_render_report_output_rejects_conflicting_source_publication_metadata(tmp_path):
    runtime = replace(
        _runtime(tmp_path, md5="md5"),
        source_publication_metadata=SourcePublicationMetadata(
            schema_version="1.0",
            source_record_id=7,
            evidence_status="conflicting",
            contradiction_status="conflicting",
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    html_path = tmp_path / "out" / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    with pytest.raises(AppError) as exc_info:
        render_report_output(
            runtime,
            source,
            selection,
            analysis,
            _deps(render_report=_render_report),
            preview_resp=render_preview_asset(runtime, source, _deps()),
        )

    assert exc_info.value.code == "source_publication_metadata_not_renderable"
