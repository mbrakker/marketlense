# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_generate_report_resumes_from_all_semantic_checkpoints_with_validated_artifacts(
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
        file_id="file_all_restart",
        name="restart.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-restart",
        task_id="task-restart",
        span_id="span-restart",
    )
    stage_calls = {
        "source": 0,
        "selection": 0,
        "vector_create": 0,
        "evidence": 0,
        "artifacts": 0,
        "validation": 0,
        "render": 0,
        "projection": 0,
    }
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

    def _extract_pdf_info(req, ctx):
        stage_calls["source"] += 1
        return SimpleNamespace(
            schema_version="1.0",
            path=req.path,
            page_count=1,
            metadata={"k": "v"},
        )

    def _collect_candidates(req, ctx):
        stage_calls["selection"] += 1
        return SimpleNamespace(candidates=[])

    def _vector_store_create(req, ctx):
        stage_calls["vector_create"] += 1
        return SimpleNamespace(vector_store_id=f"vs_{stage_calls['vector_create']}")

    def _fake_evidence(*args, **kwargs):
        stage_calls["evidence"] += 1
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
        stage_calls["artifacts"] += 1
        return _analysis_artifacts()

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        stage_calls["validation"] += 1
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
        stage_calls["render"] += 1
        rendered_payloads.append(dict(req.data))
        html_path = Path(req.out_dir) / f"{req.file_id}-{stage_calls['render']}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(
            json.dumps(req.data, ensure_ascii=True, sort_keys=True),
            encoding="utf-8",
        )
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    def _project(req):
        stage_calls["projection"] += 1
        return None

    full_deps = _base_vector_report_dependencies(
        tmp_path,
        extract_pdf_info=_extract_pdf_info,
        collect_candidates=_collect_candidates,
        vector_store_create=_vector_store_create,
        generate_evidence_packs=_fake_evidence,
        generate_artifacts=_fake_artifacts,
        run_validation=_fake_validation,
        analysis_store_pack=_store_pack,
        render_report=_render_report,
        upsert_report_metadata=lambda req, ctx: None,
        get_report_metadata=lambda req, ctx: None,
    )
    full_outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=full_deps,
        analytics_projection_fn=_project,
    )
    full_render_payload = rendered_payloads[-1]
    assert full_outcome.status == "processed"

    def _stable_render_payload(payload: dict) -> dict:
        stable = json.loads(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        stable.pop("_vector_store_id", None)
        return stable

    def _unexpected_source(*args, **kwargs):
        pytest.fail("semantic restart reran source preparation")

    def _unexpected_selection(*args, **kwargs):
        pytest.fail("semantic restart reran figure selection")

    def _unexpected_vector_create(*args, **kwargs):
        pytest.fail("semantic restart recreated vector store")

    def _unexpected_analysis(*args, **kwargs):
        pytest.fail("semantic restart reran analysis model work")

    def _unexpected_render(*args, **kwargs):
        pytest.fail("render checkpoint restart reran rendering")

    source_resume = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=_base_vector_report_dependencies(
            tmp_path,
            build_pdf_context=_unexpected_source,
            extract_pdf_info=_unexpected_source,
            extract_pdf_text=_unexpected_source,
            collect_candidates=_collect_candidates,
            vector_store_create=_vector_store_create,
            generate_evidence_packs=_fake_evidence,
            generate_artifacts=_fake_artifacts,
            run_validation=_fake_validation,
            analysis_store_pack=_store_pack,
            render_report=_render_report,
            upsert_report_metadata=lambda req, ctx: None,
            get_report_metadata=lambda req, ctx: None,
        ),
        analytics_projection_fn=_project,
        resume_from_stage="source_prepared",
    )
    assert source_resume.status == "processed"
    assert _stable_render_payload(rendered_payloads[-1]) == _stable_render_payload(
        full_render_payload
    )

    selection_resume = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=_base_vector_report_dependencies(
            tmp_path,
            build_pdf_context=_unexpected_source,
            extract_pdf_info=_unexpected_source,
            extract_pdf_text=_unexpected_source,
            collect_candidates=_unexpected_selection,
            vector_store_create=_unexpected_vector_create,
            generate_evidence_packs=_fake_evidence,
            generate_artifacts=_fake_artifacts,
            run_validation=_fake_validation,
            analysis_store_pack=_store_pack,
            render_report=_render_report,
            upsert_report_metadata=lambda req, ctx: None,
            get_report_metadata=lambda req, ctx: None,
        ),
        analytics_projection_fn=_project,
        resume_from_stage="selection_complete",
    )
    assert selection_resume.status == "processed"
    assert _stable_render_payload(rendered_payloads[-1]) == _stable_render_payload(
        full_render_payload
    )

    analysis_resume = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=_base_vector_report_dependencies(
            tmp_path,
            build_pdf_context=_unexpected_source,
            extract_pdf_info=_unexpected_source,
            collect_candidates=_unexpected_selection,
            vector_store_create=_unexpected_vector_create,
            generate_evidence_packs=_unexpected_analysis,
            generate_artifacts=_unexpected_analysis,
            run_validation=_unexpected_analysis,
            render_report=_render_report,
            upsert_report_metadata=lambda req, ctx: None,
            get_report_metadata=lambda req, ctx: None,
        ),
        analytics_projection_fn=_project,
        resume_from_stage="analysis_complete",
    )
    assert analysis_resume.status == "processed"
    assert _stable_render_payload(rendered_payloads[-1]) == _stable_render_payload(
        full_render_payload
    )

    render_resume = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=_base_vector_report_dependencies(
            tmp_path,
            build_pdf_context=_unexpected_source,
            extract_pdf_info=_unexpected_source,
            collect_candidates=_unexpected_selection,
            vector_store_create=_unexpected_vector_create,
            generate_evidence_packs=_unexpected_analysis,
            generate_artifacts=_unexpected_analysis,
            run_validation=_unexpected_analysis,
            render_report=_unexpected_render,
            upsert_report_metadata=lambda req, ctx: None,
            get_report_metadata=lambda req, ctx: None,
        ),
        analytics_projection_fn=_project,
        resume_from_stage="render_complete",
    )
    assert render_resume == analysis_resume

    assert stage_calls == {
        "source": 1,
        "selection": 2,
        "vector_create": 2,
        "evidence": 3,
        "artifacts": 3,
        "validation": 3,
        "render": 4,
        "projection": 4,
    }


def test_generate_report_latest_safe_restart_skips_corrupt_newer_checkpoint(
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
        file_id="file_latest_restart",
        name="latest.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-latest",
        task_id="task-latest",
        span_id="span-latest",
    )
    render_calls = {"count": 0}

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

    def _render_report(req, ctx):
        render_calls["count"] += 1
        html_path = Path(req.out_dir) / f"{req.file_id}-{render_calls['count']}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(
            json.dumps(req.data, ensure_ascii=True, sort_keys=True),
            encoding="utf-8",
        )
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    deps = _base_vector_report_dependencies(
        tmp_path,
        generate_evidence_packs=lambda *args, **kwargs: {
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
        },
        generate_artifacts=lambda *args, **kwargs: _analysis_artifacts(),
        run_validation=lambda req, settings, ctx, pack_name="validation", **kwargs: (
            ValidationReport(
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
        ),
        analysis_store_pack=_store_pack,
        render_report=_render_report,
        upsert_report_metadata=lambda req, ctx: None,
        get_report_metadata=lambda req, ctx: None,
    )
    full_outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=deps,
        analytics_projection_fn=lambda req: None,
    )
    assert full_outcome.html_path
    Path(full_outcome.html_path).write_text("corrupted render", encoding="utf-8")

    latest_outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=deps,
        analytics_projection_fn=lambda req: None,
        resume_from_stage="latest_safe",
    )

    assert latest_outcome.status == "processed"
    assert latest_outcome.html_path != full_outcome.html_path
    assert render_calls["count"] == 2


def test_generate_report_restart_rejects_checkpoint_artifact_hash_mismatch(
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
        file_id="file_hash_restart",
        name="hash.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-hash",
        task_id="task-hash",
        span_id="span-hash",
    )

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

    def _render_report(req, ctx):
        html_path = Path(req.out_dir) / f"{req.file_id}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(
            json.dumps(req.data, ensure_ascii=True, sort_keys=True),
            encoding="utf-8",
        )
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    deps = _base_vector_report_dependencies(
        tmp_path,
        generate_evidence_packs=lambda *args, **kwargs: {
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
        },
        generate_artifacts=lambda *args, **kwargs: _analysis_artifacts(),
        run_validation=lambda req, settings, ctx, pack_name="validation", **kwargs: (
            ValidationReport(
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
        ),
        analysis_store_pack=_store_pack,
        render_report=_render_report,
        upsert_report_metadata=lambda req, ctx: None,
        get_report_metadata=lambda req, ctx: None,
    )
    outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=deps,
        analytics_projection_fn=lambda req: None,
    )
    assert outcome.html_path
    Path(outcome.html_path).write_text("tampered", encoding="utf-8")

    with pytest.raises(AppError) as exc_info:
        rgo.run_report_generation(
            file,
            str(pdf_path),
            settings,
            md5="md5",
            ctx=ctx,
            dependencies=deps,
            analytics_projection_fn=lambda req: None,
            resume_from_stage="render_complete",
        )

    assert exc_info.value.code == "report_pipeline_checkpoint_artifact_hash_mismatch"
    assert exc_info.value.retryable is False


__all__ = [
    "test_generate_report_resumes_from_all_semantic_checkpoints_with_validated_artifacts",
    "test_generate_report_latest_safe_restart_skips_corrupt_newer_checkpoint",
    "test_generate_report_restart_rejects_checkpoint_artifact_hash_mismatch",
]
