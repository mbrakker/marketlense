from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from src.contracts.report_store import (
    SourceIdentityResolution,
    SourcePublicationMetadata,
)
from src.generators.report_render_generator import (
    _source_derived_publisher,
    render_preview_asset,
    render_report_output,
)
from tests.test_report_render_generator import (
    _analysis,
    _cover_assets,
    _deps,
    _runtime,
    _selection,
    _source,
)


def test_source_derived_publisher_uses_explicit_document_branding() -> None:
    analysis = SimpleNamespace(
        evidence_packs={
            "doc_map": {
                "title": "How GWI's brand tracking transforms metrics.",
                "publisher": "",
                "summary": "A concise guide to GWI's tracker. © GWI 2025.",
            }
        }
    )

    assert _source_derived_publisher(analysis) == "GWI"


def test_render_report_output_fails_closed_for_ungoverned_card_metadata(tmp_path):
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

    deps = _deps(
        render_report=_render_report,
        get_report_metadata=lambda req, ctx: SimpleNamespace(
            title="DB Title",
            publisher="Not extracted",
            time_period="2024",
            region="Global",
            source_url="https://publisher.example/report",
        ),
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
    )

    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    assert outcome.status == "error"
    assert outcome.error.startswith("public_metadata_governance_blocked:")
    assert outcome.report_card_manifest_path is None


def test_render_report_output_omits_an_unverified_source_date(tmp_path):
    runtime = replace(
        _runtime(tmp_path, md5="md5"),
        source_publication_metadata=SourcePublicationMetadata(
            schema_version="1.0",
            source_record_id=7,
            publication_date="2026-06-09",
            publication_date_precision="day",
            evidence_status="unknown",
            contradiction_status="not_applicable",
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    captured = {}
    html_path = tmp_path / "out" / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    def _write_manifest(req, ctx):
        del ctx
        captured["manifest"] = req.manifest
        return SimpleNamespace(
            schema_version="1.0",
            manifest_path=str(Path(req.output_dir) / "report-card-manifest.json"),
            bytes_written=2048,
        )

    deps = _deps(
        render_report=_render_report,
        write_report_card_manifest=_write_manifest,
    )
    render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    assert captured["manifest"].published_date == ""


def test_render_report_output_uses_resolved_identity_for_generated_metadata(
    tmp_path,
):
    base_runtime = _runtime(tmp_path, md5="md5")
    runtime = replace(
        base_runtime,
        report_title=f"{base_runtime.file.file_id}-pdf",
        source_identity=SourceIdentityResolution(
            schema_version="1.0",
            source_identity_id="source:exact-md5",
            canonical_title="Metaverse: Time for Practical Applications",
            publisher_id="activate",
            publisher_name="Activate",
            identity_status="resolved",
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    html_path = tmp_path / "out" / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    captured = {}

    def _render_report(req, ctx):
        del ctx
        captured["render_data"] = dict(req.data)
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    def _generate_cover_images(req, ctx):
        del ctx
        captured["cover"] = req.reports[0]
        return [
            SimpleNamespace(
                schema_version="2.0",
                file_id=runtime.file.file_id,
                title=req.reports[0].title,
                status="generated",
                assets=_cover_assets(runtime),
                error=None,
            )
        ]

    deps = _deps(
        render_report=_render_report,
        generate_cover_images=_generate_cover_images,
        get_report_metadata=lambda req, ctx: SimpleNamespace(
            title="d01c72af1b10260d54ec45e891bfc7af40a041ce-pdf",
            publisher="Not extracted",
            time_period="2023",
            region="Global",
            source_url="",
        ),
    )

    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    assert outcome.status == "error"
    assert outcome.error == "publish_readiness_failed"
    assert (
        captured["render_data"]["title"] == "Metaverse: Time for Practical Applications"
    )
    assert captured["render_data"]["publisher"] == "Activate"
    assert captured["cover"].title == "Metaverse: Time for Practical Applications"
    assert captured["cover"].publisher == "Activate"
