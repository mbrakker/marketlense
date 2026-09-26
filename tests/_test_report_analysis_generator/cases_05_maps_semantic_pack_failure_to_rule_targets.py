# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


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
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {},
            "findings": {
                "findings": [
                    {
                        "id": f"e{index}",
                        "text": f"Repaired insight {index}. Evidence {index}.",
                        "page": index,
                    }
                    for index in range(1, 6)
                ]
            },
            "quote_candidates": {
                "quote_candidates": [{"id": "q1", "text": "Repaired quote", "page": 2}]
            },
        },
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
    "test_run_report_analysis_maps_semantic_pack_failure_to_rule_specific_targets"
]
