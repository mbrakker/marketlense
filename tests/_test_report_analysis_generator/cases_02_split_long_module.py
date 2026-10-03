# ruff: noqa: F401,F403,F405
from __future__ import annotations
from ._split_support_cases_02_allows_abstained_quote_family import *  # noqa: F401,F403


def test_run_report_analysis_skips_repairs_without_retained_evidence(tmp_path):
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(
            _runtime(tmp_path).settings, validation_regeneration_max_attempts=3
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    attempts = []

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del req, settings, ctx, pack_name, report_name, md5
        return ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[
                ValidationIssue(
                    schema_version="1.0",
                    message="[metrics] Unsupported insight value",
                    severity="error",
                    affected_section="insights:insight-1",
                )
            ],
            severity="error",
            source_path=str(tmp_path / "out" / "validation.json"),
        )

    def _regenerate(request):
        attempts.append(request.attempt_index)
        return ArtifactRegenerationResponse(
            updated_artifacts=request.current_artifacts,
            regenerated_sections=["insights_candidates", "insights_final"],
            prompt_namespaces=[
                "report_vs/artifacts/regenerate/insights_candidates",
                "report_vs/artifacts/regenerate/insights_final",
            ],
            artifacts_path=str(tmp_path / "out" / "artifacts.json"),
            artifacts_snapshot_path=str(
                tmp_path
                / "out"
                / f"artifacts_regen_attempt_{request.attempt_index}.json"
            ),
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {"doc_map": {}},
        generate_artifacts=lambda **kwargs: _artifacts(
            summary={
                "tldr": "x",
                "executive_summary": "x",
                "claim_evidence_map": [],
            },
            insights_candidates=[
                {
                    "id": "insight-1",
                    "text": "x",
                    "evidence_id": "e1",
                    "evidence": "",
                    "metric": {},
                    "pages": [],
                    "score": 0.0,
                }
            ],
            insights_final=[
                {
                    "id": "insight-1",
                    "text": "x",
                    "evidence_id": "e1",
                    "evidence": "",
                    "metric": {},
                    "pages": [],
                },
                {
                    "id": "insight-2",
                    "text": "Insight 2",
                    "evidence_id": "e2",
                    "evidence": "Evidence 2",
                    "metric": {},
                    "pages": [2],
                },
                {
                    "id": "insight-3",
                    "text": "Insight 3",
                    "evidence_id": "e3",
                    "evidence": "Evidence 3",
                    "metric": {},
                    "pages": [3],
                },
                {
                    "id": "insight-4",
                    "text": "Insight 4",
                    "evidence_id": "e4",
                    "evidence": "Evidence 4",
                    "metric": {},
                    "pages": [4],
                },
                {
                    "id": "insight-5",
                    "text": "Insight 5",
                    "evidence_id": "e5",
                    "evidence": "Evidence 5",
                    "metric": {},
                    "pages": [5],
                },
            ],
        ),
        run_validation=_run_validation,
        regenerate_artifacts=_regenerate,
    )

    state = run_report_analysis(
        runtime,
        source,
        selection,
        VectorStoreIndexingState(
            vector_store_id="vs_1",
            openai_file_id="file_1",
            vector_store_status="completed",
            indexed_at_utc="2026-01-01T00:00:00Z",
            last_error=None,
        ),
        deps,
    )

    assert state.validation_report is not None
    assert state.validation_report.status == "fail"
    assert attempts == []
    assert state.regeneration_loop_state is not None
    assert state.regeneration_loop_state.max_reached is False
    assert state.regeneration_loop_state.final_status == "skipped"
    assert state.regeneration_loop_state.attempt_count == 0


def test_run_report_analysis_uses_one_broad_retry_for_unmappable_failures(tmp_path):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    requests = []
    validation_calls = {"count": 0}

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del req, settings, ctx, pack_name, report_name, md5
        validation_calls["count"] += 1
        return ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[
                ValidationIssue(
                    schema_version="1.0",
                    message="[global_consistency] Global consistency mismatch",
                    severity="error",
                    affected_section="global_consistency",
                    rule_id="global_consistency",
                )
            ],
            severity="error",
            source_path=str(tmp_path / "out" / "validation.json"),
        )

    def _regenerate(request):
        requests.append(request)
        return ArtifactRegenerationResponse(
            updated_artifacts=request.current_artifacts,
            regenerated_sections=[
                "summary",
                "insights_candidates",
                "insights_final",
                "quotes",
                "expert_comment",
                "linkedin_post",
            ],
            prompt_namespaces=[],
            artifacts_path=str(tmp_path / "out" / "artifacts.json"),
            artifacts_snapshot_path=str(
                tmp_path / "out" / "artifacts_regen_attempt_1.json"
            ),
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {"doc_map": {}},
        generate_artifacts=lambda **kwargs: _artifacts_without_retained_claims(),
        run_validation=_run_validation,
        regenerate_artifacts=_regenerate,
    )

    state = run_report_analysis(
        runtime,
        source,
        selection,
        VectorStoreIndexingState(
            vector_store_id="vs_1",
            openai_file_id="file_1",
            vector_store_status="completed",
            indexed_at_utc="2026-01-01T00:00:00Z",
            last_error=None,
        ),
        deps,
    )

    assert validation_calls["count"] == 1
    assert requests == []
    assert state.validation_report is not None
    assert state.validation_report.status == "fail"
    assert state.regeneration_loop_state is not None
    assert state.regeneration_loop_state.final_status == "skipped"
