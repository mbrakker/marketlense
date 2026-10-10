# ruff: noqa: F401,F403,F405
from __future__ import annotations
from ._split_support_cases_01_render_output_and_cards import *  # noqa: F401,F403


def test_public_source_note_keeps_title_when_publisher_is_absent(tmp_path) -> None:
    runtime = replace(
        _runtime(tmp_path, md5="md5"),
        source_identity=SimpleNamespace(
            canonical_title="Publisher Evidence Report",
            publisher_name="",
        ),
    )

    assert _public_source_note(runtime) == "Source: Publisher Evidence Report"


def test_public_source_note_decodes_a_url_encoded_canonical_title(tmp_path) -> None:
    runtime = replace(
        _runtime(tmp_path, md5="md5"),
        source_identity=SimpleNamespace(
            canonical_title="GWI%20Brand%20tracking%20guide",
            publisher_name="GWI",
        ),
    )

    assert _public_source_note(runtime) == "Source: GWI — GWI Brand tracking guide"


def test_resolved_public_publisher_prefers_matching_document_casing(tmp_path) -> None:
    runtime = replace(
        _runtime(tmp_path, md5="md5"),
        source_identity=SimpleNamespace(
            identity_status="resolved", publisher_name="iAB Europe"
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = replace(
        _analysis(runtime, source, selection),
        evidence_packs={"doc_map": {"publisher": "IAB Europe"}},
    )

    assert _resolved_public_publisher(runtime, analysis) == "IAB Europe"


def test_resolved_report_title_replaces_a_runtime_slug_with_document_map_title(
    tmp_path,
) -> None:
    runtime = replace(
        _runtime(tmp_path, md5="md5"),
        file=DriveFile(
            schema_version="1.0",
            file_id="file-1",
            name="gwi-20brand-20tracking-20guide-pdf",
            modified_time="2026-06-10T08:30:00Z",
            md5_checksum="md5",
        ),
        file_name="gwi-20brand-20tracking-20guide-pdf",
        report_name="gwi-20brand-20tracking-20guide-pdf",
        report_title="gwi-20brand-20tracking-20guide-pdf",
        source_identity=SimpleNamespace(
            identity_status="resolved",
            canonical_title="GWI%20Brand%20tracking%20guide",
            publisher_name="GWI",
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = replace(
        _analysis(runtime, source, selection),
        payload=replace(source.payload, title=runtime.report_title),
        evidence_packs={"doc_map": {"title": "GWI%20Brand%20tracking%20guide"}},
    )

    assert _resolved_report_title(runtime, source, analysis) == (
        "GWI Brand tracking guide"
    )


def test_resolved_report_title_replaces_source_identifier_with_document_map_title(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = replace(
        _analysis(runtime, source, selection),
        evidence_packs={"doc_map": {"title": "Document Map Report Title"}},
    )

    assert (
        _resolved_report_title(
            runtime,
            source,
            analysis,
            "source-12345678901234567890",
        )
        == "Document Map Report Title"
    )


def test_resolved_report_title_rejects_generic_pdf_metadata_and_humanizes_source_name(
    tmp_path,
) -> None:
    raw_file_name = "IAB_Europe_AdEx_Benchmark_2025_updated.pdf"
    runtime = replace(
        _runtime(tmp_path, md5="md5"),
        file=DriveFile(
            schema_version="1.0",
            file_id="file-1",
            name=raw_file_name,
            modified_time="2026-06-10T08:30:00Z",
            md5_checksum="md5",
        ),
        file_name=raw_file_name,
        report_name=raw_file_name.removesuffix(".pdf"),
        report_title=raw_file_name.removesuffix(".pdf"),
        source_identity=SimpleNamespace(
            identity_status="resolved",
            canonical_title=raw_file_name,
            publisher_name="IAB Europe",
        ),
    )
    source = replace(
        _source(runtime),
        info_response=replace(
            _source(runtime).info_response,
            metadata={"Title": "PowerPoint Presentation"},
        ),
    )
    selection = _selection(runtime, source)
    analysis = replace(
        _analysis(runtime, source, selection),
        payload=replace(source.payload, title=runtime.report_title),
        evidence_packs={"doc_map": {}},
    )

    assert _resolved_report_title(runtime, source, analysis) == (
        "IAB Europe AdEx Benchmark 2025 updated"
    )


def test_resolved_report_title_prefers_source_grounded_citation_over_filename_identity(
    tmp_path,
) -> None:
    runtime = replace(
        _runtime(tmp_path, md5="md5"),
        source_identity=SimpleNamespace(
            identity_status="resolved",
            canonical_title="IAB-Europes-Guide-to-AI-in-Retail-Commerce-Media-June-26.pdf",
            publisher_name="iAB Europe",
        ),
    )
    source = replace(
        _source(runtime),
        title_resolution=ReportTitleResolution(
            title="IAB-Europes-Guide-to-AI-in-Retail-Commerce-Media-June-26.pdf",
            candidate_source="filename",
        ),
    )
    selection = _selection(runtime, source)
    analysis = replace(
        _analysis(runtime, source, selection),
        payload=replace(
            source.payload,
            title="IAB-Europes-Guide-to-AI-in-Retail-Commerce-Media-June-26.pdf",
        ),
        artifacts_payload={
            "claim_ledger": [
                {
                    "citation": (
                        "IAB Europe's Guide to AI in Retail & Commerce Media, "
                        "Introduction"
                    )
                }
            ]
        },
    )

    assert _resolved_report_title(runtime, source, analysis) == (
        "IAB Europe's Guide to AI in Retail & Commerce Media"
    )


def test_render_report_output_sources_metadata_from_db_and_returns_complete_outcome(
    tmp_path, assert_no_defaulted_required_fields
):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    render_calls: list[str] = []
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        render_calls.append(req.data["title"])
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(render_report=_render_report)

    preview_resp = render_preview_asset(runtime, source, deps)
    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=preview_resp,
    )

    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "error"
    assert outcome.error == "retained_claim_materialization_identity_missing"
    assert render_calls == ["DB Title"]


def test_render_materializes_final_retained_claim_package_with_current_lineage(
    tmp_path,
):
    runtime = _runtime(tmp_path, md5="source-md5")
    runtime = replace(
        runtime,
        ctx=replace(
            runtime.ctx,
            source_identity_id="source:report-1",
            configuration_hash="a" * 64,
            policy_hash="b" * 64,
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    candidate = attach_claim_validation_execution_identity(
        validate_retained_claims(
            analysis.artifacts_payload or {},
            analysis.evidence_packs,
            source_identity=runtime.ctx.source_identity_id,
        ),
        report_id=runtime.file.file_id,
        source_id=runtime.ctx.source_identity_id,
        source_md5=runtime.md5 or "",
        configuration_hash=runtime.ctx.configuration_hash,
        policy_hash=runtime.ctx.policy_hash,
    )
    store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name="validation_retained_claim_validation_candidate",
            payload=candidate,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    html_path = Path(runtime.settings.output_dir) / "final-report.html"
    rendered_html = "<html><body><h1>Rendered report</h1></body></html>"

    def render_report(_request, _ctx):
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(rendered_html, encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    dependencies = _deps(render_report=render_report)
    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        dependencies,
        preview_resp=render_preview_asset(runtime, source, dependencies),
    )

    retained_path = outcome.evidence_packs["retained_claim_validation"]
    retained = json.loads(Path(retained_path).read_text(encoding="utf-8"))
    readiness = json.loads(
        Path(outcome.evidence_packs["publish_readiness"]).read_text(encoding="utf-8")
    )

    assert retained["lineage"]["final_artifact_hash"] == sha256_json(
        analysis.artifacts_payload or {}
    )
    assert retained["lineage"]["publication_projection_hash"] == (
        publication_projection_hash(rendered_html)
    )
    assert retained["lineage"]["evidence_pack_hash"] == sha256_json(
        analysis.evidence_packs
    )
    assert retained["lineage"]["source_md5"] == "source-md5"
    assert retained["lineage"]["source_id"] == "source:report-1"
    assert retained["lineage"]["claim_validation_validator_version"] == (
        "retained_claim_validation:v4"
    )
    assert retained["lineage"]["grounding_validator_version"] == (
        CLAIM_GROUNDING_VALIDATOR_VERSION
    )
    assert retained["validation_identity"]["source_md5"] == "source-md5"
    assert claim_validation_package_hash_valid(retained)
    assert (
        readiness["artifact_hashes"]["retained_claim_validation"]
        == retained["package_hash"]
    )
    assert any(
        item["rule_id"] == "publish_readiness.retained_claim_grounding"
        for item in readiness["rule_results"]
    )
    grounding_rule = next(
        item
        for item in readiness["rule_results"]
        if item["rule_id"] == "publish_readiness.retained_claim_grounding"
    )
    actual_unsupported_count = sum(
        result["candidate"]["factual"] and result["status"] == "unsupported"
        for result in retained["results"]
    )
    actual_unresolved_count = sum(
        result["candidate"]["factual"] and result["status"] == "unresolved"
        for result in retained["results"]
    )
    assert retained["unsupported_factual_count"] == actual_unsupported_count
    assert retained["unresolved_factual_count"] == actual_unresolved_count
    assert (
        f"unsupported_factual_count={actual_unsupported_count}"
        in grounding_rule["detail"]
    )
    assert (
        f"unresolved_factual_count={actual_unresolved_count}"
        in grounding_rule["detail"]
    )


def test_render_projects_card_tldr_from_final_insight_when_summary_abstains(
    tmp_path,
):
    runtime = _runtime(tmp_path, md5="source-md5")
    runtime = replace(
        runtime,
        ctx=replace(
            runtime.ctx,
            source_identity_id="source:report-1",
            configuration_hash="a" * 64,
            policy_hash="b" * 64,
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    baseline = _analysis(runtime, source, selection)
    artifacts = {
        **(baseline.artifacts_payload or {}),
        "summary": {
            "tldr": "",
            "card_tldr_compact": "",
            "executive_summary": "",
            "claim_evidence_map": [],
        },
        "family_status": {
            "summary": {
                "schema_version": "1.0",
                "family": "summary",
                "status": "abstained",
                "policy_action": "abstain",
                "reason": "summary_no_short_direct_claim",
            }
        },
    }
    analysis = replace(baseline, artifacts_payload=artifacts)
    candidate = attach_claim_validation_execution_identity(
        validate_retained_claims(
            artifacts,
            analysis.evidence_packs,
            source_identity=runtime.ctx.source_identity_id,
        ),
        report_id=runtime.file.file_id,
        source_id=runtime.ctx.source_identity_id,
        source_md5=runtime.md5 or "",
        configuration_hash=runtime.ctx.configuration_hash,
        policy_hash=runtime.ctx.policy_hash,
    )
    store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name="validation_retained_claim_validation_candidate",
            payload=candidate,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    html_path = Path(runtime.settings.output_dir) / "final-report.html"
    manifest_writes = []

    def render_report(_request, _ctx):
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(
            "<html><body>Rendered report</body></html>", encoding="utf-8"
        )
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    def write_manifest(request, _ctx):
        manifest_writes.append(request)
        return ReportCardManifestWriteResponse(
            schema_version="1.0",
            manifest_path=str(Path(request.output_dir) / "report-card-manifest.json"),
            bytes_written=1,
        )

    dependencies = _deps(
        render_report=render_report,
        write_report_card_manifest=write_manifest,
    )
    render_report_output(
        runtime,
        source,
        selection,
        analysis,
        dependencies,
        preview_resp=render_preview_asset(runtime, source, dependencies),
    )

    assert len(manifest_writes) == 1
    expected = analysis.artifacts_payload["insights_final"][0]["text"]
    assert manifest_writes[0].manifest.tldr_compact == expected
    assert manifest_writes[0].manifest.tldr_standard == expected


def test_render_materializes_final_package_when_validation_candidate_is_missing(
    tmp_path,
):
    runtime = _runtime(tmp_path, md5="source-md5")
    runtime = replace(
        runtime,
        ctx=replace(
            runtime.ctx,
            source_identity_id="source:report-1",
            configuration_hash="a" * 64,
            policy_hash="b" * 64,
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    html_path = Path(runtime.settings.output_dir) / "final-report.html"
    rendered_html = "<html><body><h1>Rendered report</h1></body></html>"

    def render_report(_request, _ctx):
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(rendered_html, encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    dependencies = _deps(render_report=render_report)
    preview_resp = render_preview_asset(runtime, source, dependencies)
    first = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        dependencies,
        preview_resp=preview_resp,
    )
    first_package = json.loads(
        Path(first.evidence_packs["retained_claim_validation"]).read_text(
            encoding="utf-8"
        )
    )
    second = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        dependencies,
        preview_resp=preview_resp,
    )
    second_package = json.loads(
        Path(second.evidence_packs["retained_claim_validation"]).read_text(
            encoding="utf-8"
        )
    )

    assert first.evidence_packs["retained_claim_validation"]
    assert first_package["lineage"]["report_id"] == runtime.file.file_id
    assert first_package["lineage"]["final_artifact_hash"] == sha256_json(
        analysis.artifacts_payload or {}
    )
    assert second_package["package_hash"] == first_package["package_hash"]
    assert "package_missing" not in Path(
        first.evidence_packs["publish_readiness"]
    ).read_text(encoding="utf-8")


def test_failed_final_package_materialization_has_a_typed_terminal_reason(tmp_path):
    runtime = _runtime(tmp_path, md5="source-md5")
    runtime = replace(
        runtime,
        ctx=replace(
            runtime.ctx,
            source_identity_id="source:report-1",
            configuration_hash="",
            policy_hash="b" * 64,
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    html_path = Path(runtime.settings.output_dir) / "final-report.html"

    def render_report(_request, _ctx):
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text("<html><body>Report</body></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    dependencies = _deps(render_report=render_report)
    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        dependencies,
        preview_resp=render_preview_asset(runtime, source, dependencies),
    )

    assert outcome.status == "error"
    assert outcome.error == "retained_claim_materialization_identity_missing"


def test_render_report_output_does_not_emit_html_for_failed_canonical_validation(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = replace(
        _analysis(runtime, source, selection),
        validation_report=ValidationReport(
            schema_version="1.1",
            status="fail",
            severity="error",
            issues=[],
            source_path="validation.json",
        ),
    )
    render_calls: list[object] = []
    metadata_calls: list[object] = []
    deps = _deps(
        render_report=lambda req, ctx: render_calls.append((req, ctx)),
        upsert_report_metadata=lambda req, ctx: metadata_calls.append((req, ctx)),
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
    assert outcome.error == "validation_failed"
    assert outcome.html_path == ""
    assert outcome.publish_readiness_status is None
    assert render_calls == []
    assert metadata_calls == []


@pytest.mark.parametrize(
    ("resolution", "expected_error"),
    [
        (
            ReportTitleResolution(
                issues=("generic_title_missing",),
            ),
            "report_title_generic_or_missing",
        ),
        (
            ReportTitleResolution(
                title="Different Market Outlook 2026",
                explicit_source_title="Market Outlook 2026",
            ),
            "report_title_conflicts_explicit_source",
        ),
    ],
)
def test_render_report_output_blocks_invalid_source_title_identity(
    tmp_path, resolution, expected_error
) -> None:
    runtime = _runtime(tmp_path, md5="md5")
    source = replace(_source(runtime), title_resolution=resolution)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    render_calls: list[object] = []
    metadata_calls: list[object] = []
    deps = _deps(
        render_report=lambda req, ctx: render_calls.append((req, ctx)),
        upsert_report_metadata=lambda req, ctx: metadata_calls.append((req, ctx)),
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
    assert outcome.error == expected_error
    assert outcome.html_path == ""
    assert render_calls == []
    assert metadata_calls == []


def test_render_report_output_passes_db_source_url_to_public_renderer(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    captured = {}
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del ctx
        captured["source"] = req.data["source"]
        captured["canonical_url"] = req.data["canonical_url"]
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(
        render_report=_render_report,
        get_report_metadata=lambda req, ctx: replace(
            _deps().get_report_metadata(req, ctx),
            source_url="https://publisher.example/reports/original-study",
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

    assert captured == {"source": "", "canonical_url": ""}


def test_render_report_output_preserves_analysis_metadata_when_db_metadata_missing(
    tmp_path,
):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    captured = {}
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del ctx
        captured["title"] = req.data["title"]
        captured["publisher"] = req.data["publisher"]
        captured["time_period"] = req.data["time_period"]
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(
        render_report=_render_report, get_report_metadata=lambda req, ctx: None
    )

    preview_resp = render_preview_asset(runtime, source, deps)
    render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=preview_resp,
    )

    assert captured == {
        "title": "Doc Title",
        "publisher": "Doc Publisher",
        "time_period": "2026",
    }


from .cases_01_split_long_module import *  # noqa: F401,F403
