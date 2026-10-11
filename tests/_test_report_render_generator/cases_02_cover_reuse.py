# ruff: noqa: F401,F403,F405,I001
from __future__ import annotations

import hashlib

from ._split_support_cases_01_render_output_and_cards import *  # noqa: F401,F403


def test_render_only_reuses_compatible_manifest_and_all_three_cover_assets(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    html_path = Path(runtime.settings.output_dir) / runtime.report_name / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    generated_covers = []

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    def _generate_covers(req, ctx):
        del ctx
        generated_covers.append(req)
        assets = _cover_assets(runtime)
        for asset in (assets.small, assets.medium, assets.large):
            path = Path(asset.output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"cover:{asset.size}".encode())
        return [SimpleNamespace(status="generated", assets=assets, error=None)]

    deps = _deps(
        render_report=_render_report,
        generate_cover_images=_generate_covers,
        write_report_card_manifest=write_report_card_manifest,
    )
    preview = render_preview_asset(runtime, source, deps)
    first = render_report_output(
        runtime, source, selection, analysis, deps, preview_resp=preview
    )
    manifest_path = Path(first.report_card_manifest_path)
    original_manifest = ReportCardManifest.from_dict(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    linked_paths = [
        Path(runtime.settings.output_dir) / runtime.report_name / asset.output_path
        for asset in (
            original_manifest.covers.small,
            original_manifest.covers.medium,
            original_manifest.covers.large,
        )
    ]
    assert all(path.is_file() for path in linked_paths)
    assert [
        asset.content_sha256
        for asset in (
            original_manifest.covers.small,
            original_manifest.covers.medium,
            original_manifest.covers.large,
        )
    ] == [hashlib.sha256(path.read_bytes()).hexdigest() for path in linked_paths]
    assert [
        asset.size
        for asset in (
            original_manifest.covers.small,
            original_manifest.covers.medium,
            original_manifest.covers.large,
        )
    ] == ["small", "medium", "large"]

    replay = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=preview,
        reuse_report_card_assets=True,
    )

    assert len(generated_covers) == 1
    assert replay.report_card_manifest_path == str(manifest_path)
    assert (
        ReportCardManifest.from_dict(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
        == original_manifest
    )


@pytest.mark.parametrize(
    "changed_input",
    [
        "semantics",
        "source",
        "style",
        "region",
        "asset",
        "asset_bytes",
        "legacy_checksum",
    ],
)
def test_render_only_invalidates_cover_reuse_when_approved_inputs_change(
    changed_input, tmp_path
):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    html_path = Path(runtime.settings.output_dir) / runtime.report_name / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    generated_covers = []
    region = {"value": "US"}

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    def _generate_covers(req, ctx):
        del ctx
        generated_covers.append(req)
        assets = _cover_assets(runtime)
        for asset in (assets.small, assets.medium, assets.large):
            path = Path(asset.output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"cover:{asset.size}:{len(generated_covers)}".encode())
        return [SimpleNamespace(status="generated", assets=assets, error=None)]

    def _metadata(req, ctx):
        result = _deps().get_report_metadata(req, ctx)
        return replace(result, region=region["value"])

    deps = _deps(
        render_report=_render_report,
        generate_cover_images=_generate_covers,
        write_report_card_manifest=write_report_card_manifest,
        get_report_metadata=_metadata,
    )
    preview = render_preview_asset(runtime, source, deps)
    render_report_output(
        runtime, source, selection, analysis, deps, preview_resp=preview
    )

    replay_runtime = runtime
    replay_source = source
    replay_selection = selection
    replay_analysis = analysis
    if changed_input == "semantics":
        replay_analysis = replace(
            analysis,
            artifacts_payload={
                **analysis.artifacts_payload,
                "cover_semantics": {
                    **analysis.artifacts_payload["cover_semantics"],
                    "direction": "falling",
                },
            },
        )
    elif changed_input == "source":
        replay_runtime = replace(
            runtime,
            source_identity=SimpleNamespace(
                canonical_title="Updated source title",
                canonical_landing_page_url="https://example.com/updated-source",
                source_metadata_hash="updated-source-hash",
                identity_status="verified",
                publication_date_status="verified",
                publisher_name="Publisher",
            ),
        )
        replay_source = _source(replay_runtime)
        replay_selection = _selection(replay_runtime, replay_source)
        replay_analysis = _analysis(replay_runtime, replay_source, replay_selection)
    elif changed_input == "style":
        Path(runtime.settings.cover_style_path).write_text(
            "style: changed\n", encoding="utf-8"
        )
    elif changed_input == "region":
        region["value"] = "Europe"
    elif changed_input == "asset":
        manifest_path = (
            Path(runtime.settings.output_dir)
            / runtime.report_name
            / "report-card-manifest.json"
        )
        manifest = ReportCardManifest.from_dict(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
        missing_asset = (
            Path(runtime.settings.output_dir)
            / runtime.report_name
            / manifest.covers.medium.output_path
        )
        missing_asset.unlink()
    elif changed_input == "asset_bytes":
        manifest_path = (
            Path(runtime.settings.output_dir)
            / runtime.report_name
            / "report-card-manifest.json"
        )
        manifest = ReportCardManifest.from_dict(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
        modified_asset = (
            Path(runtime.settings.output_dir)
            / runtime.report_name
            / manifest.covers.medium.output_path
        )
        modified_asset.write_bytes(b"tampered cover bytes")
    else:
        manifest_path = (
            Path(runtime.settings.output_dir)
            / runtime.report_name
            / "report-card-manifest.json"
        )
        legacy_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for size in ("small", "medium", "large"):
            legacy_manifest["covers"][size].pop("content_sha256", None)
        manifest_path.write_text(json.dumps(legacy_manifest), encoding="utf-8")

    render_report_output(
        replay_runtime,
        replay_source,
        replay_selection,
        replay_analysis,
        deps,
        preview_resp=preview,
        reuse_report_card_assets=True,
    )

    assert len(generated_covers) == 2
