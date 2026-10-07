# ruff: noqa: F401,F403,F405
from __future__ import annotations
from ._split_support_cases_01_render_output_and_cards import *  # noqa: F401,F403


def test_render_report_output_omits_private_pdf_download_href(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    Path(runtime.local_pdf_path).write_bytes(b"%PDF-1.4\n")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    captured = {}
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del ctx
        captured["has_download_href"] = "_source_download_href" in req.data
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(render_report=_render_report)

    render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    assert captured["has_download_href"] is False


def test_render_report_citations_use_report_page_labels_without_internal_targets(
    tmp_path, run_context
):
    from src.contracts.report_assets import RenderRequest
    from src.services.render_service import render_report

    out_dir = tmp_path / "out"
    data = {
        "title": "Retail Forecast 2026",
        "publisher": "Forecast Co",
        "source": "https://forecast.example/report",
        "_figure_section_enabled": False,
        "artifacts": {
            "summary": {
                "tldr": "Retail demand is changing.",
                "executive_summary": "Retail demand is changing across channels.",
                "claim_evidence_map": [
                    {
                        "claim": "Retail demand is changing.",
                        "evidence_id": "local-evidence-123",
                        "evidence": "Demand moved across channels.",
                        "pages": [7],
                        "evidence_spans": [
                            {
                                "evidence_id": "local-evidence-123",
                                "source_pack": "cache/evidence-window.json",
                                "page": 7,
                            }
                        ],
                    }
                ],
            },
            "insights_final": [
                {
                    "text": "Demand moved across channels.",
                    "evidence_id": "local-insight-456",
                    "pages": [8],
                }
            ],
            "quotes_final": [
                {
                    "text": "Consumers are shifting channels.",
                    "speaker": "Analyst",
                    "citation": "C:/tmp/evidence-window.json",
                    "page": 9,
                    "evidence_id": "local-quote-789",
                }
            ],
        },
        "evidence_packs": {"doc_map": {"title": "Retail Forecast 2026"}},
    }

    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data=data,
            doc_name="retail-forecast.pdf",
            file_id="file-1",
            out_dir=str(out_dir),
            preview_png="",
            tag_acronyms=[],
        ),
        run_context,
    )

    html = Path(response.html_path).read_text(encoding="utf-8")
    assert "Retail Forecast 2026, page 7" in html
    assert "Retail Forecast 2026, page 8" in html
    assert "Retail Forecast 2026, page 9" in html
    assert "local-evidence-123" not in html
    assert "local-insight-456" not in html
    assert "local-quote-789" not in html
    assert "cache/evidence-window.json" not in html
    assert "C:/tmp/evidence-window.json" not in html


def test_render_report_output_uses_html_cache_hit_and_skips_render(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    expected_html = Path(runtime.settings.output_dir) / f"{runtime.report_name}.html"
    expected_html.parent.mkdir(parents=True, exist_ok=True)
    expected_html.write_text("<html>cached</html>", encoding="utf-8")

    preview_resp = SimpleNamespace(
        schema_version="1.1", image_path="preview.png", page_number=0
    )
    cached_data = {
        **analysis.data_dict,
        "title": "DB Title",
        "publisher": "DB Publisher",
        "time_period": "Q1 2026",
        "canonical_url": "",
        "source": "",
        "source_publication_date": "",
    }
    template_contents = {
        "report.html.j2": "template",
        "report.css.j2": "css",
        "_report_macros.j2": "macros",
    }
    cache_key = html_cache_key(
        "md5",
        _template_bundle_sha(template_contents),
        sha256_json(cached_data),
        "preview.png",
        runtime.file_name,
        render_contract_version="2.2",
    )

    def _read_text(req, ctx):
        if req.path == str(expected_html):
            return SimpleNamespace(content=expected_html.read_text(encoding="utf-8"))
        if req.path.endswith(f"{runtime.report_name}.html.cache.json"):
            return SimpleNamespace(content=json.dumps({"key": cache_key}))
        for name, content in template_contents.items():
            if req.path.endswith(name):
                return SimpleNamespace(content=content)
        raise AssertionError(f"Unexpected read: {req.path}")

    def _read_cache(req, ctx):
        del ctx
        assert req.path.endswith(f"{runtime.report_name}.html.cache.json")
        return SimpleNamespace(found=True, payload={"key": cache_key})

    def _hash_bundle(req, ctx):
        del ctx
        assert {Path(path).name for path in req.paths} == set(template_contents)
        return SimpleNamespace(sha256=_template_bundle_sha(template_contents))

    def _file_stat(req, ctx):
        del ctx
        return SimpleNamespace(exists=Path(req.path) == expected_html)

    deps = _deps(
        read_text=_read_text,
        read_json_object_cache=_read_cache,
        hash_file_bundle=_hash_bundle,
        file_stat=_file_stat,
        render_report=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("render_report should be skipped on cache hit")
        ),
    )

    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=preview_resp,
    )

    assert outcome.html_path == str(expected_html)


def test_render_report_output_invalidates_cache_when_css_template_changes(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    expected_html = Path(runtime.settings.output_dir) / f"{runtime.report_name}.html"
    expected_html.parent.mkdir(parents=True, exist_ok=True)
    expected_html.write_text("<html>stale</html>", encoding="utf-8")

    preview_resp = SimpleNamespace(
        schema_version="1.1", image_path="preview.png", page_number=0
    )
    cached_data = {
        **analysis.data_dict,
        "title": "DB Title",
        "publisher": "DB Publisher",
        "time_period": "Q1 2026",
        "source": "",
    }
    stale_template_contents = {
        "report.html.j2": "template",
        "report.css.j2": "old-css",
        "_report_macros.j2": "macros",
    }
    current_template_contents = {
        "report.html.j2": "template",
        "report.css.j2": "new-css",
        "_report_macros.j2": "macros",
    }
    stale_cache_key = html_cache_key(
        "md5",
        _template_bundle_sha(stale_template_contents),
        sha256_json(cached_data),
        "preview.png",
        runtime.file_name,
        render_contract_version="2.0",
    )
    render_calls: list[str] = []

    def _read_text(req, ctx):
        if req.path == str(expected_html):
            return SimpleNamespace(content=expected_html.read_text(encoding="utf-8"))
        if req.path.endswith(f"{runtime.report_name}.html.cache.json"):
            return SimpleNamespace(content=json.dumps({"key": stale_cache_key}))
        for name, content in current_template_contents.items():
            if req.path.endswith(name):
                return SimpleNamespace(content=content)
        raise AssertionError(f"Unexpected read: {req.path}")

    def _read_cache(req, ctx):
        del ctx
        assert req.path.endswith(f"{runtime.report_name}.html.cache.json")
        return SimpleNamespace(found=True, payload={"key": stale_cache_key})

    def _hash_bundle(req, ctx):
        del ctx
        assert {Path(path).name for path in req.paths} == set(current_template_contents)
        return SimpleNamespace(sha256=_template_bundle_sha(current_template_contents))

    def _render_report(req, ctx):
        del ctx
        render_calls.append(req.data["title"])
        expected_html.write_text("<html>fresh</html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(expected_html))

    def _file_stat(req, ctx):
        del ctx
        return SimpleNamespace(exists=Path(req.path) == expected_html)

    deps = _deps(
        read_text=_read_text,
        read_json_object_cache=_read_cache,
        hash_file_bundle=_hash_bundle,
        file_stat=_file_stat,
        render_report=_render_report,
    )

    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=preview_resp,
    )

    assert outcome.html_path == str(expected_html)
    assert render_calls == ["DB Title"]
    assert expected_html.read_text(encoding="utf-8") == "<html>fresh</html>"


def test_html_cache_key_changes_when_render_contract_changes() -> None:
    shared = (
        "md5",
        "template-sha",
        "data-sha",
        "preview.png",
        "report.pdf",
    )

    assert html_cache_key(*shared, render_contract_version="1.0") != html_cache_key(
        *shared,
        render_contract_version="2.0",
    )


def test_render_preview_asset_reuses_contents_preview_when_contents_is_first_page(
    tmp_path,
):
    runtime = _runtime(tmp_path, md5="md5")
    source = replace(
        _source(runtime),
        contents_page_number=1,
        contents_image="report/assets/report-contents.png",
    )
    render_calls: list[tuple[str, int, str]] = []
    deps = _deps(
        render_preview=lambda req, ctx: (
            render_calls.append((req.pdf_path, req.page_number, req.variant))
            or SimpleNamespace(
                schema_version="1.1",
                image_path="preview.png",
                page_number=req.page_number,
            )
        )
    )

    preview_resp = render_preview_asset(runtime, source, deps)

    assert preview_resp.image_path == "report/assets/report-contents.png"
    assert preview_resp.page_number == 0
    assert render_calls == []


def test_render_preview_asset_renders_when_contents_page_does_not_overlap(
    tmp_path,
):
    runtime = _runtime(tmp_path, md5="md5")
    source = replace(
        _source(runtime),
        contents_page_number=2,
        contents_image="report/assets/report-contents.png",
    )
    render_calls: list[tuple[str, int, str]] = []
    deps = _deps(
        render_preview=lambda req, ctx: (
            render_calls.append((req.pdf_path, req.page_number, req.variant))
            or SimpleNamespace(
                schema_version="1.1",
                image_path="preview.png",
                page_number=req.page_number,
            )
        )
    )

    preview_resp = render_preview_asset(runtime, source, deps)

    assert preview_resp.image_path == "preview.png"
    assert render_calls == [(runtime.local_pdf_path, 0, "")]


def test_render_report_output_propagates_retryable_cover_error(
    tmp_path, assert_app_error
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

    deps = _deps(
        render_report=_render_report,
        generate_cover_images=lambda req, ctx: (_ for _ in ()).throw(
            AppError(
                code="cover_render_failed",
                message="temporary cover render failure",
                retryable=True,
            )
        ),
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
        code="cover_render_failed",
        retryable=True,
        severity="error",
    )


def test_render_report_output_does_not_use_file_modified_time_for_card_date(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = replace(
        _analysis(runtime, source, selection),
        artifacts_payload={
            "summary": {
                "tldr": "A complete standard summary explains the report.",
                "card_tldr_compact": "A compact report-card summary.",
            },
            "cover_semantics": {
                "evidence_shape": "trend",
                "direction": "rising",
                "evidence_density": "balanced",
                "domain_layer": "grid",
                "selection_reason": "The report presents a sustained trend.",
            },
            "insights_final": [
                {"text": "Channel efficiency improved."},
                {"text": "Investment shifted."},
            ],
        },
        evidence_packs={"doc_map": {"title": source.payload.title}},
    )
    writes = []
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(
        render_report=_render_report,
        write_report_card_manifest=lambda req, ctx: (
            writes.append(req)
            or SimpleNamespace(manifest_path="report-card-manifest.json")
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

    assert len(writes) == 1
    assert writes[0].manifest.published_date == ""
    assert outcome.status == "error"
    assert outcome.error == "retained_claim_materialization_identity_missing"


def test_render_only_regenerates_card_manifest_when_it_is_missing(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    generated_covers = []
    written_manifests = []

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(
        render_report=_render_report,
        generate_cover_images=lambda req, ctx: (
            generated_covers.append(req)
            or [
                SimpleNamespace(
                    status="generated",
                    assets=_cover_assets(runtime),
                    error=None,
                )
            ]
        ),
        write_report_card_manifest=lambda req, ctx: (
            written_manifests.append(req)
            or SimpleNamespace(
                manifest_path=str(Path(req.output_dir) / "report-card-manifest.json")
            )
        ),
    )

    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
        reuse_report_card_assets=True,
    )

    assert len(generated_covers) == 1
    assert len(written_manifests) == 1
    assert outcome.report_card_manifest_path.endswith("report-card-manifest.json")


def test_report_card_seed_ignores_runtime_cache_metadata_but_tracks_artifact_changes(
    tmp_path,
):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    baseline = _analysis(runtime, source, selection)
    generated_covers = []
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(
        render_report=_render_report,
        generate_cover_images=lambda req, ctx: (
            generated_covers.append(req)
            or [
                SimpleNamespace(
                    status="generated", assets=_cover_assets(runtime), error=None
                )
            ]
        ),
        write_report_card_manifest=lambda req, ctx: SimpleNamespace(
            manifest_path=str(Path(req.output_dir) / "report-card-manifest.json")
        ),
    )
    preview = render_preview_asset(runtime, source, deps)
    payloads = [
        {**baseline.artifacts_payload, "_cache": {"hit": False}},
        {**baseline.artifacts_payload, "_cache": {"hit": True, "elapsed_ms": 17}},
        {
            **baseline.artifacts_payload,
            "insights_final": [
                {"text": "A changed first finding."},
                baseline.artifacts_payload["insights_final"][1],
            ],
            "_cache": {"hit": True, "elapsed_ms": 17},
        },
    ]

    for artifacts_payload in payloads:
        render_report_output(
            runtime,
            source,
            selection,
            replace(baseline, artifacts_payload=artifacts_payload),
            deps,
            preview_resp=preview,
        )

    seeds = [request.reports[0].fingerprint.seed for request in generated_covers]
    assert len(seeds) == 3
    assert seeds[0] == seeds[1]
    assert seeds[2] != seeds[1]


def test_render_omits_ambiguous_retained_cover_period_before_card_generation(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    generated_covers = []

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    def _metadata(req, ctx):
        metadata = _deps().get_report_metadata(req, ctx)
        return replace(
            metadata,
            time_period=(
                "2025 (primary coverage) with outlook into 2026 and beyond; "
                "return a valid JSON object with no text after it. "
                "The period field must contain only a compact normalized label."
            ),
        )

    deps = _deps(
        render_report=_render_report,
        get_report_metadata=_metadata,
        generate_cover_images=lambda req, ctx: (
            generated_covers.append(req)
            or [
                SimpleNamespace(
                    status="generated",
                    assets=_cover_assets(runtime),
                    error=None,
                )
            ]
        ),
    )

    render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    assert generated_covers[0].reports[0].time_period is None


def test_render_report_output_does_not_write_manifest_after_cover_error(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    writes = []
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(
        render_report=_render_report,
        generate_cover_images=lambda req, ctx: [
            SimpleNamespace(
                schema_version="2.0",
                file_id=runtime.file.file_id,
                title="DB Title",
                status="error",
                assets=None,
                error="cover failed",
            )
        ],
        write_report_card_manifest=lambda req, ctx: writes.append(req),
    )

    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    assert writes == []
    assert outcome.status == "error"
    assert outcome.error == "cover_asset_set_incomplete: cover failed"
    assert outcome.report_card_manifest_path is None


def test_render_report_output_fails_closed_for_invalid_card_content(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = replace(
        _analysis(runtime, source, selection),
        artifacts_payload={
            **_analysis(runtime, source, selection).artifacts_payload,
            "summary": {
                "tldr": "A complete standard summary explains the report finding.",
                "card_tldr_compact": "This summary is incomplete",
            },
        },
    )
    writes = []
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

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
        write_report_card_manifest=lambda req, ctx: writes.append(req),
    )

    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    assert writes == []
    assert outcome.status == "error"
    assert outcome.error.startswith("card_tldr_compact_invalid:")
    assert outcome.report_card_manifest_path is None
    assert outcome.publish_readiness_status == "fail"
    readiness = json.loads(
        Path(outcome.evidence_packs["publish_readiness"]).read_text(encoding="utf-8")
    )
    card_rule = next(
        item
        for item in readiness["rule_results"]
        if item["rule_id"] == "publish_readiness.report_card_manifest"
    )
    assert card_rule["status"] == "fail"
