# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_report_generation_scores_two_ingested_reports_for_same_publisher(
    tmp_path,
) -> None:
    settings = replace(
        _ingest_settings(tmp_path),
        ingest_worker_limit=1,
        report_worker_limit=1,
    )
    publisher_name = "Example Research"
    source_rows = [
        (
            "file_score_1",
            "2026 Global Retail Market Outlook Benchmark Survey",
            "https://research.example.com/reports/2026-retail-market-outlook",
        ),
        (
            "file_score_2",
            "2026 Consumer Commerce Trends Benchmark Survey",
            "https://research.example.com/reports/2026-commerce-trends-benchmark",
        ),
    ]
    seed_ctx = RunContext(
        schema_version="1.0",
        run_id="run-seed",
        task_id="seed-report-sources",
        span_id="span-seed",
    )
    for _file_id, title, url in source_rows:
        record_discovered_report_source(
            ReportSourceDiscoveryRecordRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                publisher_name=publisher_name,
                source_domain="research.example.com",
                report_name=title,
                landing_page_url=url,
                source_page_url="https://research.example.com/research/reports",
                discovered_at_utc="2026-06-05T00:00:00Z",
                discovered_on_page_number=1,
            ),
            seed_ctx,
        )

    def _store_pack(request, ctx):
        path = (
            Path(request.output_dir)
            / slugify(request.report_slug or request.report_id)
            / "report_analysis"
            / f"{request.pack_name}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(request.payload), encoding="utf-8")
        return SimpleNamespace(output_path=str(path))

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(
                Path(settings.output_dir)
                / slugify(kwargs.get("report_name") or req.report_id)
                / "report_analysis"
                / f"{pack_name}.json"
            ),
        )

    def _render_report(req, ctx):
        html_path = Path(settings.output_dir) / f"{req.file_id}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text("<html></html>", encoding="utf-8")
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    files = [
        DriveFile(
            schema_version="1.0",
            file_id=file_id,
            name=f"{title}.pdf",
            modified_time=None,
            md5_checksum=f"md5-{file_id}",
        )
        for file_id, title, _url in source_rows
    ]
    titles_by_file_id = {file_id: title for file_id, title, _url in source_rows}

    def _generate_report(current_file, cache_path, current_settings, md5, ctx):
        title = titles_by_file_id[current_file.file_id]

        def _evidence(report_id, vector_store_id, settings, ctx, **kwargs):
            return {
                "doc_map": {
                    "docMap": {
                        "title": title,
                        "publisher": publisher_name,
                        "sections": [{"title": "Overview"}],
                    },
                    "doc_id": "d",
                },
                "scope": {},
                "methods": {},
                "findings": {},
                "limitations": {},
                "quote_candidates": {},
            }

        def _artifacts(
            report_id,
            doc_map,
            evidence_packs,
            settings,
            vector_store_id=None,
            source_status=None,
            ctx=None,
            report_name=None,
            **kwargs,
        ):
            payload = _analysis_artifacts()
            _store_pack(
                AnalysisStorePackRequest(
                    schema_version="1.0",
                    output_dir=settings.output_dir,
                    report_id=report_id,
                    pack_name="artifacts",
                    payload=payload,
                    report_slug=report_name,
                ),
                ctx,
            )
            return payload

        deps = _base_vector_report_dependencies(
            tmp_path,
            generate_evidence_packs=_evidence,
            generate_artifacts=_artifacts,
            run_validation=_fake_validation,
            analysis_store_pack=_store_pack,
            render_report=_render_report,
        )
        return rgo.run_report_generation(
            current_file,
            cache_path,
            current_settings,
            md5=md5,
            ctx=ctx,
            dependencies=deps,
            analytics_projection_fn=lambda req: None,
        )

    outcomes = orch.run_ingest(
        settings,
        limit=2,
        dependencies=_batch_dependencies(
            list_pdfs=lambda req, ctx: files,
            process_file=_make_ingest_process(generate_report=_generate_report),
        ),
    )

    assert [outcome.status for outcome in outcomes] == ["processed", "processed"]

    history = list_report_source_quality_history(
        ReportSourceQualityHistoryRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            publisher_name=publisher_name,
            limit=10,
        ),
        seed_ctx,
    )

    assert len(history.items) == 2
    assert {item.report_name for item in history.items} == {
        title for _file_id, title, _url in source_rows
    }
    assert {item.source_page_url for item in history.items} == {
        "https://research.example.com/research/reports"
    }
    assert all(item.source_status == "downloaded" for item in history.items)
    assert all(item.overall_score >= 78.0 for item in history.items)

    with sqlite3.connect(settings.reports_db) as conn:
        scored_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM report_sources
            WHERE publisher_name=?
              AND report_value_score IS NOT NULL
              AND report_value_score_json IS NOT NULL
            """,
            (publisher_name,),
        ).fetchone()[0]
    assert scored_rows == 2

def test_report_generation_scores_drive_only_ingest_without_source_url(
    tmp_path,
) -> None:
    settings = replace(
        _ingest_settings(tmp_path),
        ingest_worker_limit=1,
        report_worker_limit=1,
    )
    title = "2026 Customer Market Outlook Benchmark Survey"
    publisher_name = "Drive Only Research"
    file = DriveFile(
        schema_version="1.0",
        file_id="drive_only_score_file",
        name=f"{title}.pdf",
        modified_time=None,
        md5_checksum="md5-drive-only",
    )
    rendered_scores: list[dict] = []

    def _store_pack(request, ctx):
        path = (
            Path(request.output_dir)
            / slugify(request.report_slug or request.report_id)
            / "report_analysis"
            / f"{request.pack_name}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(request.payload), encoding="utf-8")
        return SimpleNamespace(output_path=str(path))

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(
                Path(settings.output_dir)
                / slugify(kwargs.get("report_name") or req.report_id)
                / "report_analysis"
                / f"{pack_name}.json"
            ),
        )

    def _evidence(report_id, vector_store_id, settings, ctx, **kwargs):
        return {
            "doc_map": {
                "docMap": {
                    "title": title,
                    "publisher": publisher_name,
                    "sections": [{"title": "Overview"}],
                },
                "doc_id": "d",
            },
            "scope": {},
            "methods": {},
            "findings": {},
            "limitations": {},
            "quote_candidates": {},
        }

    def _artifacts(
        report_id,
        doc_map,
        evidence_packs,
        settings,
        vector_store_id=None,
        source_status=None,
        ctx=None,
        report_name=None,
        **kwargs,
    ):
        payload = _analysis_artifacts(source="")
        _store_pack(
            AnalysisStorePackRequest(
                schema_version="1.0",
                output_dir=settings.output_dir,
                report_id=report_id,
                pack_name="artifacts",
                payload=payload,
                report_slug=report_name,
            ),
            ctx,
        )
        return payload

    def _render_report(req, ctx):
        rendered_scores.append(req.data.get("_report_value_score", {}))
        html_path = Path(settings.output_dir) / f"{req.file_id}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text("<html></html>", encoding="utf-8")
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    def _generate_report(current_file, cache_path, current_settings, md5, ctx):
        deps = _base_vector_report_dependencies(
            tmp_path,
            generate_evidence_packs=_evidence,
            generate_artifacts=_artifacts,
            run_validation=_fake_validation,
            analysis_store_pack=_store_pack,
            render_report=_render_report,
        )
        return rgo.run_report_generation(
            current_file,
            cache_path,
            current_settings,
            md5=md5,
            ctx=ctx,
            dependencies=deps,
            analytics_projection_fn=lambda req: None,
        )

    outcomes = orch.run_ingest(
        settings,
        limit=1,
        dependencies=_batch_dependencies(
            list_pdfs=lambda req, ctx: [file],
            process_file=_make_ingest_process(generate_report=_generate_report),
        ),
    )

    assert [outcome.status for outcome in outcomes] == ["processed"]
    assert rendered_scores
    assert {
        component["dimension"] for component in rendered_scores[0]["components"]
    } == {
        "market_insight_depth",
        "evidence_specificity",
        "decision_relevance",
        "recency_timeliness",
        "source_authority_originality",
    }

    with sqlite3.connect(settings.reports_db) as conn:
        row = conn.execute(
            """
            SELECT landing_page_url, source_domain, report_value_score_json
            FROM report_sources
            WHERE md5=?
            """,
            ("md5",),
        ).fetchone()

    assert row is not None
    assert row[0] == "https://drive.google.com/file/d/drive_only_score_file/view"
    assert row[1] == "drive.google.com"
    score_payload = json.loads(row[2])
    assert {
        component["dimension"] for component in score_payload["components"]
    } == {
        "market_insight_depth",
        "evidence_specificity",
        "decision_relevance",
        "recency_timeliness",
        "source_authority_originality",
    }

def test_generate_report_doc_map_empty_halts(
    tmp_path,
) -> None:
    settings = _ingest_settings(tmp_path)
    settings = settings.__class__(
        **{**settings.__dict__, "openai_timeout_seconds": 3600.0}
    )
    pdf_path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    file = DriveFile(
        schema_version="1.0",
        file_id="file_vs",
        name="vector.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-vs",
        task_id="task-vs",
        span_id="span-vs",
    )

    def _fake_evidence(*args, **kwargs):
        raise AppError(
            code="doc_map_empty",
            message="doc_map_empty:no_content",
            retryable=False,
            context={
                "sections_count": 0,
                "not_found_reason": "model_returned_no_json",
            },
        )

    def _unexpected(*args, **kwargs):
        pytest.fail("Unexpected downstream call after doc_map_empty")

    deps = _base_vector_report_dependencies(
        tmp_path,
        generate_evidence_packs=_fake_evidence,
        generate_artifacts=_unexpected,
        run_validation=_unexpected,
        render_report=_unexpected,
        upsert_report_metadata=_unexpected,
    )

    outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=deps,
    )

    assert outcome.status == "error"
    assert "doc_map_empty" in (outcome.error or "")
    assert outcome.vector_store_id == "vs_new"
    assert outcome.doc_map_summary is not None
    assert outcome.doc_map_summary.get("sections_count") == 0
    assert outcome.doc_map_summary.get("not_found_reason") == "model_returned_no_json"

def test_generate_report_resumes_from_analysis_checkpoint_without_upstream_rerun(
    tmp_path,
) -> None:
    settings = replace(_ingest_settings(tmp_path), report_worker_limit=1)
    pdf_path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    file = DriveFile(
        schema_version="1.0",
        file_id="file_vs",
        name="vector.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-vs",
        task_id="task-vs",
        span_id="span-vs",
    )
    upstream_calls = {"evidence": 0, "artifacts": 0, "validation": 0}
    rendered_payloads: list[dict] = []

    def _store_pack(request: AnalysisStorePackRequest, ctx):
        path = (
            Path(request.output_dir)
            / slugify(request.report_slug or str(request.report_id))
            / "report_analysis"
            / f"{request.pack_name}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(request.payload, ensure_ascii=True), encoding="utf-8"
        )
        return SimpleNamespace(output_path=str(path))

    def _fake_evidence(*args, **kwargs):
        upstream_calls["evidence"] += 1
        return {
            "doc_map": {
                "docMap": {
                    "title": "Checkpoint Title",
                    "publisher": "Checkpoint Publisher",
                    "sections": [{"title": "Overview"}],
                },
                "doc_id": "d",
            },
            "scope": {},
            "methods": {},
            "findings": {},
            "limitations": {},
            "quote_candidates": {},
        }

    def _fake_artifacts(*args, **kwargs):
        upstream_calls["artifacts"] += 1
        return _analysis_artifacts()

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        upstream_calls["validation"] += 1
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(
                Path(settings.output_dir)
                / slugify(kwargs.get("report_name") or str(req.report_id))
                / "report_analysis"
                / f"{pack_name}.json"
            ),
        )

    def _render_report(req, ctx):
        rendered_payloads.append(dict(req.data))
        html_path = Path(req.out_dir) / f"{req.file_id}-{len(rendered_payloads)}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(
            json.dumps(req.data, ensure_ascii=True, sort_keys=True),
            encoding="utf-8",
        )
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    full_deps = _base_vector_report_dependencies(
        tmp_path,
        generate_evidence_packs=_fake_evidence,
        generate_artifacts=_fake_artifacts,
        run_validation=_fake_validation,
        analysis_store_pack=_store_pack,
        render_report=_render_report,
        upsert_report_metadata=lambda req, ctx: None,
        get_report_metadata=lambda req, ctx: None,
        generate_cover_images=lambda req, ctx: [],
    )

    full_outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=full_deps,
    )
    full_render_payload = rendered_payloads[-1]

    def _unexpected_upstream(*args, **kwargs):
        pytest.fail("resume from analysis checkpoint reran an upstream stage")

    resume_deps = _base_vector_report_dependencies(
        tmp_path,
        build_pdf_context=_unexpected_upstream,
        extract_pdf_info=_unexpected_upstream,
        extract_best_figure=_unexpected_upstream,
        collect_candidates=_unexpected_upstream,
        vector_store_create=_unexpected_upstream,
        generate_evidence_packs=_unexpected_upstream,
        generate_artifacts=_unexpected_upstream,
        run_validation=_unexpected_upstream,
        render_report=_render_report,
        upsert_report_metadata=lambda req, ctx: None,
        get_report_metadata=lambda req, ctx: None,
        generate_cover_images=lambda req, ctx: [],
    )

    resumed_outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=resume_deps,
        resume_from_stage="analysis_complete",
    )
    resumed_render_payload = rendered_payloads[-1]

    assert full_outcome.status == "processed"
    assert resumed_outcome.status == "processed"
    assert full_render_payload == resumed_render_payload
    assert resumed_outcome.evidence_packs == full_outcome.evidence_packs
    assert upstream_calls == {"evidence": 1, "artifacts": 1, "validation": 1}

def test_generate_report_deletes_vector_store_when_retention_disabled(
    tmp_path,
) -> None:
    settings = replace(_ingest_settings(tmp_path), vector_store_keep=False)
    pdf_path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as handle:
        writer.write(handle)
    file = DriveFile(
        schema_version="1.0",
        file_id="file_vs",
        name="vector.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-vs",
        task_id="task-vs",
        span_id="span-vs",
    )
    delete_calls = []

    def _store_pack(request, ctx):
        return SimpleNamespace(
            output_path=str(
                Path(request.output_dir)
                / slugify(request.report_slug or request.report_id)
                / "report_analysis"
                / f"{request.pack_name}.json"
            )
        )

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(
                Path(settings.output_dir)
                / slugify(kwargs.get("report_name") or req.report_id)
                / "report_analysis"
                / f"{pack_name}.json"
            ),
        )

    def _fake_render_report(req, ctx):
        html_path = tmp_path / "out.html"
        html_path.write_text("<html></html>", encoding="utf-8")
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    deps = _base_vector_report_dependencies(
        tmp_path,
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {
                "docMap": {
                    "title": "DocMap Title",
                    "publisher": "DocMap Publisher",
                    "sections": [{"title": "Overview"}],
                },
                "doc_id": "d",
            },
            "scope": {},
            "methods": {},
            "findings": {},
            "limitations": {},
            "quote_candidates": {},
        },
        generate_artifacts=lambda **kwargs: _analysis_artifacts(),
        run_validation=_fake_validation,
        analysis_store_pack=_store_pack,
        render_report=_fake_render_report,
        upsert_report_metadata=lambda req, ctx: None,
        vector_store_delete=lambda req, ctx: (
            delete_calls.append(req.vector_store_id)
            or SimpleNamespace(
                vector_store_id=req.vector_store_id,
                deleted=True,
                missing_remote=False,
            )
        ),
    )

    outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=deps,
    )

    assert delete_calls == ["vs_new"]
    assert outcome.status == "processed"
    assert outcome.vector_store_id is None
    assert outcome.vector_store_status == "deleted"

__all__ = [
    "test_report_generation_scores_two_ingested_reports_for_same_publisher",
    "test_report_generation_scores_drive_only_ingest_without_source_url",
    "test_generate_report_doc_map_empty_halts",
    "test_generate_report_resumes_from_analysis_checkpoint_without_upstream_rerun",
    "test_generate_report_deletes_vector_store_when_retention_disabled",
]
