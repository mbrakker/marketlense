# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_ingest_file_orchestrator.py"
)

from ._split_support_test_ingest_file_orchestrator import *  # noqa: F401,F403


def test_existing_html_cache_requires_passing_readiness(
    ingest_settings, run_context
) -> None:
    file = _drive_file(md5_checksum="drive-md5")
    cache_path = f"{ingest_settings.cache_dir}/{file.file_id}.pdf"

    def _file_stat(request, _ctx):
        return FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=request.path == cache_path,
            size_bytes=10 if request.path == cache_path else None,
            mtime_utc=1.0 if request.path == cache_path else None,
            md5="drive-md5" if request.compute_md5 else None,
        )

    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=lambda current, _path, _settings, md5, _ctx: _outcome(
            current, md5
        ),
        write_md5_sidecar_fn=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            written=True,
            reason="written",
        ),
        read_text_fn=lambda _request, _ctx: SimpleNamespace(
            content='{"status":"fail"}'
        ),
    )
    dependencies = replace(
        dependencies,
        existing_report_html=lambda *_args, **_kwargs: "out/file-1.html",
    )

    result = run_ingest_file(
        file=file,
        index=0,
        settings=ingest_settings,
        root_ctx=run_context,
        dependencies=dependencies,
    )

    assert (result.outcome.status, result.outcome.error) == ("processed", None)


def test_stale_canonical_package_resumes_owner_without_duplicate_acquisition(
    ingest_settings, run_context
) -> None:
    """Removing the canonical owner route would download and create another package."""
    file = _drive_file(md5_checksum="drive-md5")
    calls = {
        "downloads": 0,
        "report_id": "",
        "resume_stage": "",
        "auto_resume": False,
    }

    def _download(*_args, **_kwargs):
        calls["downloads"] += 1
        raise AssertionError("canonical stale reuse must not acquire the duplicate")

    def _run_report_pipeline(
        current_file,
        _path,
        _settings,
        md5,
        _ctx,
        *,
        resume_from_stage=None,
        auto_resume_from_latest_safe=False,
        readiness_refresh_plan=None,
        refresh_telemetry_path=None,
        **_kwargs,
    ):
        calls["report_id"] = current_file.file_id
        calls["resume_stage"] = resume_from_stage or ""
        calls["auto_resume"] = auto_resume_from_latest_safe
        assert readiness_refresh_plan is not None
        assert refresh_telemetry_path.endswith("publish_readiness_refresh_plan.json")
        return _outcome(current_file, md5)

    dependencies = _base_dependencies(
        file_stat_fn=lambda request, _ctx: FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=False,
            size_bytes=None,
            mtime_utc=None,
            md5=None,
        ),
        run_report_pipeline_fn=_run_report_pipeline,
        write_md5_sidecar_fn=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            written=True,
            reason="written",
        ),
        download_pdf_to_path_fn=_download,
        read_text_fn=lambda _request, _ctx: SimpleNamespace(
            content='{"status":"fail"}'
        ),
    )
    dependencies = replace(
        dependencies,
        existing_report_html=lambda *_args, **_kwargs: RetainedReportPackage(
            schema_version="1.0",
            report_id="drive-original",
            html_path="out/original.html",
            canonical_source_identity="source:exact",
            source_content_hash="md5:drive-md5",
            reason="canonical_identity_and_content_hash_match",
        ),
    )

    result = run_ingest_file(
        file=file,
        index=0,
        settings=ingest_settings,
        root_ctx=run_context,
        dependencies=dependencies,
    )

    assert result.outcome.status == "processed", result.outcome.error
    assert calls == {
        "downloads": 0,
        "report_id": "drive-original",
        "resume_stage": "",
        "auto_resume": True,
    }
    with sqlite3.connect(ingest_settings.reports_db) as conn:
        telemetry = conn.execute(
            """
            SELECT highest_reused_checkpoint, reused_stages_json,
                   regenerated_stages_json, acquisition_actions_avoided,
                   browser_launches_avoided, pdf_parse_avoided, ocr_avoided,
                   extraction_avoided, vector_work_avoided,
                   model_calls_avoided_status, model_calls_avoided,
                   tokens_avoided_status, input_tokens_avoided,
                   output_tokens_avoided, estimated_cost_avoided_status,
                   estimated_cost_avoided_usd
            FROM report_source_reuse_telemetry
            """
        ).fetchone()
    assert telemetry == (
        "analysis_complete",
        '["acquisition","source_prepared","selection_complete","analysis_complete"]',
        '["render_complete"]',
        1,
        0,
        0,
        0,
        0,
        0,
        "unavailable",
        0,
        "unavailable",
        0,
        0,
        "unavailable",
        0.0,
    )


def test_existing_html_cache_rejects_readiness_from_another_producer_revision(
    ingest_settings, run_context
) -> None:
    """A ready cached HTML package cannot cross a producer-revision boundary."""
    file = _drive_file(md5_checksum="drive-md5")
    cache_path = f"{ingest_settings.cache_dir}/{file.file_id}.pdf"
    html = (
        "<!doctype html><!--\n"
        "marketbearing-build:\n"
        "  git_sha: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "  generation_run_id: generation-run-1\n"
        "  validation_run_id: validation-run-1\n"
        "  source_id: source:file-1\n"
        "  source_md5: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
        "  artifact_hash: cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\n"
        "  generation_profile: safe_default\n"
        "  generated_at_utc: 2026-08-26T12:00:00+00:00\n"
        "--><html><head><title>Report 2026 | MarketLense</title>"
        '<link rel="canonical" href="https://marketlense.example/reports/report">'
        "</head><body><h1>Report 2026</h1>"
        "<p>Revenue grew in the measured market.</p>"
        '<section id="source"><a href="https://publisher.example/report">'
        "Open original source</a></section></body></html>"
    )
    readiness = evaluate_publish_readiness(
        report_id=file.file_id,
        artifacts={
            "categories": ["markets"],
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": "Revenue grew in the measured market.",
                        "evidence_id": "F1",
                        "evidence": "Revenue grew in the measured market.",
                    }
                ]
            },
            "insights_final": [],
            "quotes_final": [],
            "chart_insight_cards": [],
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "F1",
                        "snippet": "Revenue grew in the measured market.",
                        "page": 1,
                    }
                ]
            }
        },
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="out/file-1.html",
        report_card_manifest_path="report-card-manifest.json",
        category_ids=["markets"],
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="previous-producer",
        provenance={
            "publisher_landing_page_url": "https://publisher.example/report",
            "original_report_url": "",
            "marketlense_article_url": "https://marketlense.example/reports/report",
        },
        created_at=datetime.now(UTC),
    )
    assert readiness.status == "pass"

    def _file_stat(request, _ctx):
        return FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=request.path == cache_path,
            size_bytes=10 if request.path == cache_path else None,
            mtime_utc=1.0 if request.path == cache_path else None,
            md5="drive-md5" if request.compute_md5 else None,
        )

    resumed_from = {"stage": None, "auto": None}

    def _run_report_pipeline(
        current,
        _path,
        _settings,
        md5,
        _ctx,
        *,
        auto_resume_from_latest_safe=False,
        resume_from_stage=None,
    ):
        resumed_from["stage"] = resume_from_stage
        resumed_from["auto"] = auto_resume_from_latest_safe
        return _outcome(current, md5)

    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=_run_report_pipeline,
        write_md5_sidecar_fn=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            written=True,
            reason="written",
        ),
        read_text_fn=lambda request, _ctx: SimpleNamespace(
            content=(
                html
                if str(request.path).endswith(".html")
                else json.dumps(publish_readiness_payload(readiness))
            )
        ),
    )
    dependencies = replace(
        dependencies,
        existing_report_html=lambda *_args, **_kwargs: "out/file-1.html",
    )

    result = run_ingest_file(
        file=file,
        index=0,
        settings=ingest_settings,
        root_ctx=replace(
            run_context,
            configuration_hash="configuration-hash",
            policy_hash="policy-hash",
            producer_commit_sha="current-producer",
        ),
        dependencies=dependencies,
    )

    assert (result.outcome.status, result.outcome.error) == ("processed", None)
    assert resumed_from == {"stage": None, "auto": True}


def test_expired_readiness_uses_the_existing_enforced_render_recovery_path(
    ingest_settings, run_context
) -> None:
    file = _drive_file(md5_checksum="drive-md5")
    cache_path = f"{ingest_settings.cache_dir}/{file.file_id}.pdf"
    html = (
        "<!doctype html><!--\n"
        "marketbearing-build:\n"
        "  git_sha: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "  generation_run_id: generation-run-1\n"
        "  validation_run_id: validation-run-1\n"
        "  source_id: source:file-1\n"
        "  source_md5: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
        "  artifact_hash: cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\n"
        "  generation_profile: safe_default\n"
        "  generated_at_utc: 2026-08-26T12:00:00+00:00\n"
        "--><html><head><title>Report 2026 | MarketLense</title>"
        '<link rel="canonical" href="https://marketlense.example/reports/report">'
        "</head><body><h1>Report 2026</h1>"
        "<p>Revenue grew in the measured market.</p>"
        '<section id="source"><a href="https://publisher.example/report">'
        "Open original source</a></section></body></html>"
    )
    readiness = evaluate_publish_readiness(
        report_id=file.file_id,
        artifacts={
            "categories": ["markets"],
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": "Revenue grew in the measured market.",
                        "evidence_id": "F1",
                        "evidence": "Revenue grew in the measured market.",
                    }
                ]
            },
            "insights_final": [],
            "quotes_final": [],
            "chart_insight_cards": [],
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "F1",
                        "snippet": "Revenue grew in the measured market.",
                        "page": 1,
                    }
                ]
            }
        },
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="out/file-1.html",
        report_card_manifest_path="report-card-manifest.json",
        category_ids=["markets"],
        configuration_hash=run_context.configuration_hash,
        policy_hash=run_context.policy_hash,
        producer_revision=run_context.producer_commit_sha,
        provenance={
            "publisher_landing_page_url": "https://publisher.example/report",
            "original_report_url": "",
            "marketlense_article_url": "https://marketlense.example/reports/report",
        },
        created_at=datetime.now(UTC) - timedelta(days=2),
    )
    captured: dict[str, object] = {}

    def _file_stat(request, _ctx):
        return FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=request.path == cache_path,
            size_bytes=10 if request.path == cache_path else None,
            mtime_utc=1.0 if request.path == cache_path else None,
            md5="drive-md5" if request.compute_md5 else None,
        )

    def _run_report_pipeline(
        current,
        _path,
        _settings,
        md5,
        _ctx,
        *,
        auto_resume_from_latest_safe=False,
        resume_from_stage=None,
        execution_plan_mode=None,
        recovery_execution_intent=None,
        recovery_invalidations=None,
        readiness_refresh_plan=None,
        refresh_telemetry_path=None,
    ):
        captured.update(
            {
                "auto": auto_resume_from_latest_safe,
                "stage": resume_from_stage,
                "mode": execution_plan_mode,
                "intent": recovery_execution_intent,
                "invalidations": recovery_invalidations,
                "state": readiness_refresh_plan.previous_readiness_state,
                "telemetry_path": refresh_telemetry_path,
            }
        )
        return _outcome(current, md5)

    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=_run_report_pipeline,
        write_md5_sidecar_fn=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            written=True,
            reason="written",
        ),
        read_text_fn=lambda request, _ctx: SimpleNamespace(
            content=(
                html
                if str(request.path).endswith(".html")
                else json.dumps(publish_readiness_payload(readiness))
            )
        ),
    )
    dependencies = replace(
        dependencies,
        existing_report_html=lambda *_args, **_kwargs: "out/file-1.html",
    )

    result = run_ingest_file(
        file=file,
        index=0,
        settings=ingest_settings,
        root_ctx=run_context,
        dependencies=dependencies,
    )

    assert result.outcome.status == "processed"
    assert captured == {
        "auto": True,
        "stage": None,
        "mode": "enforce",
        "intent": "render_repair",
        "invalidations": {"rendered_html": "publish_readiness.expired"},
        "state": "stale",
        "telemetry_path": str(
            Path("out/file-1")
            / "report_analysis"
            / "publish_readiness_refresh_plan.json"
        ),
    }


def test_missing_md5_is_computed_before_pipeline(ingest_settings, run_context):
    settings = replace(ingest_settings, vector_store_keep=True)
    file = _drive_file(md5_checksum=None)
    non_md5_calls = {"count": 0}
    compute_md5_calls = {"count": 0}
    pipeline_md5 = {"value": None}

    def _file_stat(request, _ctx):
        if request.compute_md5:
            compute_md5_calls["count"] += 1
            return FileStatResponse(
                schema_version="1.0",
                path=request.path,
                exists=True,
                size_bytes=10,
                mtime_utc=123.0,
                md5="computed-md5",
            )
        non_md5_calls["count"] += 1
        if non_md5_calls["count"] == 1:
            return FileStatResponse(
                schema_version="1.0",
                path=request.path,
                exists=False,
                size_bytes=None,
                mtime_utc=None,
                md5=None,
            )
        return FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=True,
            size_bytes=10,
            mtime_utc=123.0,
            md5=None,
        )

    def _run_report_pipeline(current_file, _cache_path, _settings, md5, _ctx):
        pipeline_md5["value"] = md5
        return _outcome(current_file, md5)

    sidecar_writes = []
    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=_run_report_pipeline,
        write_md5_sidecar_fn=lambda request, _ctx: (
            sidecar_writes.append(
                (
                    f"{request.cache_path}.md5.json",
                    request.file_id,
                    request.md5,
                    request.size_bytes,
                    request.mtime_utc,
                )
            )
            or FileCacheMd5SidecarWriteResponse(
                schema_version="1.0",
                cache_path=request.cache_path,
                sidecar_path=f"{request.cache_path}.md5.json",
                record=None,
                written=True,
                reason="written",
            )
        ),
    )

    result = run_ingest_file(file, 0, settings, run_context, dependencies)

    assert result.outcome.status == "processed"
    assert pipeline_md5["value"] == "computed-md5"
    assert compute_md5_calls["count"] == 1


def test_missing_eof_after_bounded_download_retries_stops_before_pipeline(
    ingest_settings,
    run_context,
):
    file = _drive_file(md5_checksum=None)
    download_calls = {"count": 0}
    download_budgets = []
    pipeline_calls = {"count": 0}
    state_records = []

    def _file_stat(request, _ctx):
        return FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=False,
            size_bytes=None,
            mtime_utc=None,
            md5=None,
        )

    def _download(req, _ctx):
        download_calls["count"] += 1
        download_budgets.append(req.run_budget)
        return DriveDownloadToPathResponse(
            schema_version="1.0",
            file=req.file,
            output_path=req.output_path,
            md5="source-md5",
            size=10,
        )

    def _run_report_pipeline(current_file, _cache_path, _settings, md5, _ctx):
        del current_file, md5
        pipeline_calls["count"] += 1
        raise AssertionError("report pipeline should not run for malformed PDF")

    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=_run_report_pipeline,
        write_md5_sidecar_fn=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            record=None,
            written=False,
            reason="not_called",
        ),
        check_pdf_eof_fn=lambda req, _ctx: PdfEofCheckResponse(
            schema_version="1.0", path=req.path, has_eof=False
        ),
        download_pdf_to_path_fn=_download,
        state_record_fn=lambda request, _ctx: (
            state_records.append(request) or SimpleNamespace()
        ),
    )
    run_budget = RunBudget(
        schema_version="1.0",
        run_id=run_context.run_id,
        publisher_name="",
        usage_db_path=ingest_settings.usage_db_path,
    )
    dependencies = replace(dependencies, run_budget=run_budget)

    result = run_ingest_file(file, 0, ingest_settings, run_context, dependencies)

    assert result.outcome.status == "error"
    assert result.outcome.error == (
        f"Downloaded PDF is missing EOF marker: {ingest_settings.cache_dir}/file-1.pdf"
    )
    assert download_calls["count"] == 2
    assert download_budgets == [run_budget, run_budget]
    assert pipeline_calls["count"] == 0
    assert len(state_records) == 1
    assert state_records[0].state_db == ingest_settings.state_db
    assert state_records[0].file_id == "file-1"
    assert state_records[0].md5 == "source-md5"
    assert state_records[0].last_error == (
        "pdf_download_missing_eof: "
        f"Downloaded PDF is missing EOF marker: {ingest_settings.cache_dir}/file-1.pdf"
    )
    assert state_records[0].text_validation_status == "fail"
    assert state_records[0].text_validation_reason == "pdf_download_missing_eof"


def test_structural_integrity_failure_is_quarantined_before_report_pipeline(
    ingest_settings,
    run_context,
):
    file = _drive_file(md5_checksum="source-md5")
    pipeline_calls = {"count": 0}
    quarantines = []

    def _file_stat(request, _ctx):
        return FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=True,
            size_bytes=100,
            mtime_utc=123.0,
            md5="source-md5" if request.compute_md5 else None,
        )

    def _integrity(request, _ctx):
        return PdfIntegrityCheckResponse(
            schema_version="1.0",
            path=request.path,
            size_bytes=100,
            sha256="a" * 64,
            md5="source-md5",
            validator_version="pdf-integrity-v1",
            has_pdf_header=True,
            has_eof=True,
            parser_opened=False,
            page_count=0,
            failure_code="pdf_parser_open_failed",
            retryable=False,
            validated_at_utc="2026-07-19T10:00:00+00:00",
        )

    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=lambda *_args: (
            pipeline_calls.__setitem__("count", pipeline_calls["count"] + 1)
            or _outcome(file, "source-md5")
        ),
        write_md5_sidecar_fn=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            record=None,
            written=False,
            reason="not_called",
        ),
        check_pdf_integrity_fn=_integrity,
        upsert_source_quarantine_fn=lambda request, _ctx: (
            quarantines.append(request.record) or SimpleNamespace(record=request.record)
        ),
    )

    result = run_ingest_file(file, 0, ingest_settings, run_context, dependencies)

    assert result.outcome.status == "error"
    assert pipeline_calls["count"] == 0
    assert len(quarantines) == 1
    assert quarantines[0].status == "active"
    assert quarantines[0].failure_code == "pdf_parser_open_failed"
