# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_run_report_analysis_allows_abstained_quote_family(tmp_path):
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(_runtime(tmp_path).settings, figure_caption_enabled=False),
    )
    source = _source(runtime)
    source.payload.quote.text = ""
    selection = _selection(runtime, source)
    validation_calls = []
    artifacts = _artifacts(
        quotes_final=[],
        family_status={
            "quotes": {
                "schema_version": "1.0",
                "family": "quotes",
                "source": "artifact",
                "status": "abstained",
                "confidence_score": 0.65,
                "policy_action": "regenerate",
                "reason": "quotes_missing_verbatim_source",
            }
        },
    )
    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=lambda **kwargs: artifacts,
        run_validation=lambda *args, **kwargs: (
            validation_calls.append(args[0])
            or ValidationReport(
                schema_version="1.1",
                status="pass",
                issues=[],
                severity="pass",
                source_path=str(tmp_path / "out" / "validation.json"),
            )
        ),
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

    assert validation_calls
    assert state.payload.quote.text == ""
    assert state.artifacts_payload["family_status"]["quotes"]["status"] == "abstained"

def test_run_report_analysis_regenerates_failed_section_until_pass(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
):
    caplog.set_level(logging.INFO, logger="market_lense.report_analysis_orchestrator")
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    validation_calls: list[str] = []
    regeneration_requests = []

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del settings, ctx, report_name, md5
        validation_calls.append(
            f"{pack_name}:{req.artifacts.get('summary', {}).get('tldr', '')}"
        )
        if len(validation_calls) == 1:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[grounding] Unsupported summary claim",
                        severity="error",
                        affected_section="executive_summary",
                    )
                ],
                severity="error",
                source_path=str(tmp_path / "out" / "validation.json"),
            )
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        )

    def _regenerate(request):
        regeneration_requests.append(request)
        return ArtifactRegenerationResponse(
            updated_artifacts=_artifacts(
                summary={
                    "tldr": "repaired",
                    "executive_summary": "Grounded summary",
                    "claim_evidence_map": [],
                }
            ),
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            artifacts_path=str(tmp_path / "out" / "artifacts.json"),
            artifacts_snapshot_path=str(
                tmp_path / "out" / "artifacts_regen_attempt_1.json"
            ),
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=lambda **kwargs: _artifacts(
            summary={
                "tldr": "broken",
                "executive_summary": "Broken summary",
                "claim_evidence_map": [],
            }
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
            vector_store_status="indexing",
            indexed_at_utc=None,
            last_error=None,
        ),
        deps,
    )

    assert state.validation_report is not None
    assert state.validation_report.status == "pass"
    assert state.regeneration_loop_state is not None
    assert state.regeneration_loop_state.attempt_count == 1
    assert state.regeneration_loop_state.final_status == "pass"
    assert state.regeneration_attempts[0].regenerated_sections == ["summary"]
    assert regeneration_requests[0].plan.mode == "targeted"
    assert regeneration_requests[0].plan.targets[0].target_section == "summary"
    assert "artifacts_regen_attempt_1" in state.evidence_paths
    assert "validation_regen_attempt_1" in state.evidence_paths

    events = _orchestrator_events(caplog)
    regen_events = [
        event
        for event in events
        if str(event.get("event", "")).startswith("validation_regen_")
    ]
    assert_logs_have_required_fields(regen_events)
    assert {event["event"] for event in regen_events} >= {
        "validation_regen_loop_start",
        "validation_regen_plan_built",
        "validation_regen_attempt_start",
        "validation_regen_attempt_complete",
        "validation_regen_pass",
    }

def test_run_report_analysis_maps_topic_section_failures_to_topics_regeneration(
    tmp_path,
):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    validation_calls: list[str] = []
    regeneration_requests = []

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del settings, ctx, report_name, md5
        validation_calls.append(pack_name)
        if len(validation_calls) == 1:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[toc_integrity] TOC coverage is missing section 'Media brands'.",
                        severity="error",
                        affected_section="toc_entries:section-1",
                        rule_id="toc_integrity",
                        repair_target="topics",
                        entity_id="section-1",
                    )
                ],
                severity="error",
                source_path=str(tmp_path / "out" / "validation.json"),
            )
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        )

    def _regenerate(request):
        regeneration_requests.append(request)
        return ArtifactRegenerationResponse(
            updated_artifacts=request.current_artifacts,
            regenerated_sections=[
                "toc_entries",
                "toc_topics",
                "toc_topics_expanded",
            ],
            prompt_namespaces=[],
            artifacts_path=str(tmp_path / "out" / "artifacts.json"),
            artifacts_snapshot_path=str(
                tmp_path / "out" / "artifacts_regen_attempt_1.json"
            ),
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {
                "title": "Doc Title",
                "publisher": "Doc Publisher",
                "sections": [
                    {
                        "id": "section-1",
                        "title": "Media brands",
                        "summary": "Media brand ad equity section.",
                        "key_points": [],
                        "pages": [17],
                    }
                ],
            }
        },
        generate_artifacts=lambda **kwargs: _artifacts(
            toc_entries=[
                {
                    "section_id": "section-2",
                    "section_title": "Sentiments on GenAI",
                    "display_title": "Media brand ad equity",
                    "summary": "Wrong section summary",
                    "key_points": [],
                    "pages": [25],
                    "order": 1,
                }
            ],
            toc_topics=["Media brand ad equity"],
            toc_topics_expanded=[
                {
                    "topic": "Media brand ad equity",
                    "summary": "Wrong section summary",
                    "key_points": [],
                    "section_id": "section-2",
                    "section_title": "Sentiments on GenAI",
                    "pages": [25],
                }
            ],
            summary={
                "tldr": "broken",
                "executive_summary": "Broken summary",
                "claim_evidence_map": [],
            },
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
            vector_store_status="indexing",
            indexed_at_utc=None,
            last_error=None,
        ),
        deps,
    )

    assert state.validation_report is not None
    assert state.validation_report.status == "pass"
    assert len(regeneration_requests) == 1
    assert regeneration_requests[0].plan.mode == "targeted"
    assert regeneration_requests[0].plan.targets[0].target_section == "topics"
    assert regeneration_requests[0].plan.targets[0].regenerate_steps == [
        "toc_entries",
        "toc_topics",
        "toc_topics_expanded",
    ]
    assert state.regeneration_attempts[0].regenerated_sections == [
        "toc_entries",
        "toc_topics",
        "toc_topics_expanded",
    ]

def test_run_report_analysis_stops_after_regeneration_max_attempts(tmp_path):
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
    assert attempts == [1, 2, 3]
    assert state.regeneration_loop_state is not None
    assert state.regeneration_loop_state.max_reached is True
    assert state.regeneration_loop_state.attempt_count == 3

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
        generate_artifacts=lambda **kwargs: _artifacts(
            summary={
                "tldr": "x",
                "executive_summary": "x",
                "claim_evidence_map": [],
            }
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

    assert validation_calls["count"] == 2
    assert len(requests) == 1
    assert requests[0].plan.mode == "broad"
    assert [target.target_section for target in requests[0].plan.targets] == [
        "summary",
        "insights_bundle",
        "quotes",
        "expert_comment",
        "linkedin_post",
    ]
    assert state.validation_report is not None
    assert state.validation_report.status == "fail"
    assert state.regeneration_loop_state is not None
    assert state.regeneration_loop_state.final_status == "skipped"

def test_run_report_analysis_maps_semantic_pack_failure_to_rule_specific_targets(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
):
    caplog.set_level(logging.INFO, logger="market_lense.report_analysis_orchestrator")
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    requests = []
    validation_calls = {"count": 0}

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del req, settings, ctx, pack_name, report_name, md5
        validation_calls["count"] += 1
        if validation_calls["count"] == 1:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[semantic] Semantic validation failed: model payload incomplete",
                        severity="error",
                        affected_section="semantic",
                        rule_id="semantic",
                    )
                ],
                severity="error",
                source_path=str(tmp_path / "out" / "validation.json"),
            )
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        )

    def _regenerate(request):
        requests.append(request)
        return ArtifactRegenerationResponse(
            updated_artifacts={
                **request.current_artifacts,
                "insights_final": [
                    {
                        "id": f"insight-{index}",
                        "text": f"Repaired insight {index}",
                        "evidence_id": f"e{index}",
                        "evidence": f"Evidence {index}",
                        "metric": {},
                        "pages": [index],
                    }
                    for index in range(1, 6)
                ],
                "quotes_final": [
                    {
                        "id": "quote-1",
                        "text": "Repaired quote",
                        "evidence_id": "q1",
                        "page": 2,
                    }
                ],
            },
            regenerated_sections=[
                "insights_candidates",
                "insights_final",
                "quotes",
            ],
            prompt_namespaces=[
                "report_vs/artifacts/regenerate/insights_candidates",
                "report_vs/artifacts/regenerate/insights_final",
                "report_vs/artifacts/regenerate/quotes",
            ],
            artifacts_path=str(tmp_path / "out" / "artifacts.json"),
            artifacts_snapshot_path=str(
                tmp_path / "out" / "artifacts_regen_attempt_1.json"
            ),
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {"doc_map": {}},
        generate_artifacts=lambda **kwargs: _artifacts(
            summary={
                "tldr": "x",
                "executive_summary": "x",
                "claim_evidence_map": [],
            }
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

    assert len(requests) == 1
    assert requests[0].plan.mode == "targeted"
    assert [target.target_section for target in requests[0].plan.targets] == [
        "insights_bundle",
        "quotes",
    ]
    assert len(requests[0].plan.targets) < 5
    assert state.validation_report is not None
    assert state.validation_report.status == "pass"

    events = _orchestrator_events(caplog)
    plan_events = [
        event for event in events if event["event"] == "validation_regen_plan_built"
    ]
    complete_events = [
        event
        for event in events
        if event["event"] == "validation_regen_attempt_complete"
    ]
    assert plan_events[-1]["fields"]["target_details"] == [
        {
            "target_section": "insights_bundle",
            "regenerate_steps": ["insights_candidates", "insights_final"],
            "prompt_namespaces": [
                "report_vs/artifacts/regenerate/insights_candidates",
                "report_vs/artifacts/regenerate/insights_final",
            ],
            "rule_ids": ["semantic"],
        },
        {
            "target_section": "quotes",
            "regenerate_steps": ["quotes"],
            "prompt_namespaces": ["report_vs/artifacts/regenerate/quotes"],
            "rule_ids": ["semantic"],
        },
    ]
    assert set(complete_events[-1]["fields"]["artifact_diff"]["changed_keys"]) >= {
        "insights_final",
        "quotes_final",
    }
    assert complete_events[-1]["fields"]["artifacts_snapshot_path"].endswith(
        "artifacts_regen_attempt_1.json"
    )
    assert_logs_have_required_fields(plan_events + complete_events)

__all__ = [
    "test_run_report_analysis_allows_abstained_quote_family",
    "test_run_report_analysis_regenerates_failed_section_until_pass",
    "test_run_report_analysis_maps_topic_section_failures_to_topics_regeneration",
    "test_run_report_analysis_stops_after_regeneration_max_attempts",
    "test_run_report_analysis_uses_one_broad_retry_for_unmappable_failures",
    "test_run_report_analysis_maps_semantic_pack_failure_to_rule_specific_targets",
]
