# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from src.contracts.regeneration import RepairDecision, RepairPatchOperation
from src.generators.validation.regeneration_candidate import (
    retained_claim_repair_issues,
)

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


def test_run_report_analysis_rolls_back_failed_candidate_regeneration(tmp_path):
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(
            _runtime(tmp_path).settings, validation_regeneration_max_attempts=1
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    original = _artifacts_without_retained_claims(
        summary={
            "tldr": "current artifact",
            "executive_summary": "Current summary",
            "claim_evidence_map": [],
        }
    )
    candidate = _artifacts_without_retained_claims(
        summary={
            "tldr": "candidate artifact",
            "card_tldr_compact": "Candidate summary",
            "executive_summary": "Candidate summary",
            "claim_evidence_map": [],
        },
    )
    _set_interpretive_summary_provenance(original)
    _set_interpretive_summary_provenance(candidate)
    validation_calls = 0

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        nonlocal validation_calls
        del req, settings, ctx, pack_name, report_name, md5
        validation_calls += 1
        if validation_calls == 1:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[grounding] Unsupported summary claim",
                        severity="error",
                        affected_section="summary",
                        rule_id="grounding",
                        repair_target="summary",
                    )
                ],
                severity="error",
            )
        return ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[
                ValidationIssue(
                    schema_version="1.0",
                    message="[grounding] Candidate introduced issue Y",
                    severity="error",
                    affected_section="linkedin_post",
                    rule_id="candidate_y",
                    repair_target="linkedin_post",
                )
            ],
            severity="error",
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title"}},
            "findings": {
                "findings": [
                    {"id": f"f{index}", "pages": [index]} for index in range(1, 6)
                ]
            },
            "quote_candidates": {"quote_candidates": [{"id": "q1", "page": 1}]},
        },
        generate_artifacts=lambda **kwargs: original,
        run_validation=_run_validation,
        regenerate_artifacts=lambda request: ArtifactRegenerationResponse(
            updated_artifacts=candidate,
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            candidate_artifacts_path=str(
                tmp_path / "out" / "artifacts_regen_candidate_1.json"
            ),
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

    assert state.artifacts_payload["summary"]["tldr"] == "current artifact"
    assert state.regeneration_attempts[0].promotion_outcome == "rolled_back"
    assert state.regeneration_attempts[0].candidate_audit_path
    assert state.validation_report.status == "fail"
    assert [issue.rule_id for issue in state.validation_report.issues] == ["grounding"]
    candidate_audit = json.loads(
        Path(state.regeneration_attempts[0].candidate_audit_path).read_text(
            encoding="utf-8"
        )
    )
    assert candidate_audit["validation_issues"] == ["candidate_y:linkedin_post"]


@pytest.mark.parametrize(
    ("baseline_retained_severity", "expected_outcome"),
    [("error", "rolled_back"), ("warning", "promoted")],
)
def test_candidate_promotion_preserves_promoted_retained_claim_severity(
    tmp_path, baseline_retained_severity: str, expected_outcome: str
) -> None:
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(
            _runtime(tmp_path).settings, validation_regeneration_max_attempts=1
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    evidence_packs = {
        "doc_map": {"docMap": {"title": "Doc Title"}},
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": "European loyalty reached 49% in 2024.",
                    "pages": [1],
                },
                *[{"id": f"f{index}", "pages": [index]} for index in range(2, 6)],
            ]
        },
        "quote_candidates": {"quote_candidates": [{"id": "q1", "page": 1}]},
    }
    original = _artifacts_without_retained_claims(
        summary={
            "tldr": "Broken summary",
            "card_tldr_compact": "Stable summary card text",
            "executive_summary": "Current summary",
            "claim_evidence_map": [
                {
                    "id": "summary-claim-1",
                    "claim": "European loyalty reached 99% in 2023.",
                    "evidence_id": "f1",
                    "evidence": "European loyalty reached 49% in 2024.",
                    "pages": [1],
                }
            ],
        }
    )
    _set_interpretive_summary_provenance(original)
    candidate = deepcopy(original)
    candidate["summary"]["tldr"] = "Repaired summary"
    _set_interpretive_summary_provenance(candidate)
    retained_issues = [
        replace(issue, severity=baseline_retained_severity)
        for issue in retained_claim_repair_issues(original, evidence_packs)
    ]
    validation_calls = 0

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        nonlocal validation_calls
        del req, settings, ctx, pack_name, report_name, md5
        validation_calls += 1
        if validation_calls == 1:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[grounding] Broken summary text",
                        severity="error",
                        affected_section="summary.tldr",
                        rule_id="grounding",
                        repair_target="summary",
                    ),
                    *retained_issues,
                ],
                severity="error",
            )
        return ValidationReport(
            schema_version="1.1", status="pass", issues=[], severity="pass"
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: evidence_packs,
        generate_artifacts=lambda **kwargs: original,
        run_validation=_run_validation,
        regenerate_artifacts=lambda request: ArtifactRegenerationResponse(
            updated_artifacts=candidate,
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            candidate_artifacts_path=str(
                tmp_path / "out" / "artifacts_regen_candidate_1.json"
            ),
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

    assert len(state.regeneration_attempts) == 1
    assert state.regeneration_attempts[0].promotion_outcome == expected_outcome
    assert state.artifacts_payload["summary"]["tldr"] == (
        "Repaired summary" if expected_outcome == "promoted" else "Broken summary"
    )
    if expected_outcome == "rolled_back":
        assert any(
            item.rule_id == "retained_claim.number_value_unit_match"
            for item in state.regeneration_attempts[0].repair_delta.persisting
        )
    else:
        assert any(
            issue.rule_id == "retained_claim.number_value_unit_match"
            and issue.severity == "warning"
            for issue in state.validation_report.issues
        )


def test_run_report_analysis_retries_from_last_promoted_artifacts_after_rollback(
    tmp_path,
):
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(
            _runtime(tmp_path).settings, validation_regeneration_max_attempts=2
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    original = _artifacts_without_retained_claims(
        summary={
            "tldr": "original artifact",
            "executive_summary": "Original summary",
            "claim_evidence_map": [],
        }
    )
    candidates = [
        _artifacts_without_retained_claims(
            summary={
                "tldr": "failed candidate",
                "card_tldr_compact": "Failed candidate summary",
                "executive_summary": "Failed candidate summary",
                "claim_evidence_map": [],
            },
        ),
        _artifacts_without_retained_claims(
            summary={
                "tldr": "repaired artifact",
                "card_tldr_compact": "Repaired summary",
                "executive_summary": "Repaired summary",
                "claim_evidence_map": [],
            },
        ),
    ]
    for artifact in [original, *candidates]:
        _set_interpretive_summary_provenance(artifact)
    regeneration_inputs = []
    repair_usage_attempts = []
    regeneration_targets = []
    regeneration_strategies = []
    retry_memories = []
    validation_calls = 0

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        nonlocal validation_calls
        del req, settings, ctx, pack_name, report_name, md5
        validation_calls += 1
        if validation_calls == 1:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[grounding] Unsupported summary claim",
                        severity="error",
                        affected_section="summary",
                        rule_id="grounding",
                        repair_target="summary",
                    )
                ],
                severity="error",
            )
        if validation_calls == 2:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[grounding] Candidate introduced issue Y",
                        severity="error",
                        affected_section="linkedin_post",
                        rule_id="candidate_y",
                        repair_target="linkedin_post",
                    )
                ],
                severity="error",
            )
        return ValidationReport(
            schema_version="1.1", status="pass", issues=[], severity="pass"
        )

    def _regenerate(request):
        repair_usage_attempts.append(request.ctx.repair_attempt)
        regeneration_inputs.append(request.current_artifacts["summary"]["tldr"])
        regeneration_targets.append(
            [target.target_section for target in request.plan.targets]
        )
        retry_memories.append(list(request.repair_memory))
        attempt = request.attempt_index
        strategy = "current_evidence" if attempt == 1 else "alternative_evidence"
        evidence_id = "f1" if attempt == 1 else "f2"
        regeneration_strategies.append(request.plan.targets[0].repair_strategy)
        decision = RepairDecision(
            diagnosed_failure_class="grounding",
            repair_action="REGENERATE_ITEM",
            repair_strategy=strategy,
            evidence_ids_used=[evidence_id],
            protected_fields=["summary.card_tldr_compact"],
            changed_paths=["summary.tldr"],
            minimal_patch=[
                RepairPatchOperation(
                    op="replace",
                    path="summary.tldr",
                    value=candidates[attempt - 1]["summary"]["tldr"],
                )
            ],
        )
        return ArtifactRegenerationResponse(
            updated_artifacts=candidates[attempt - 1],
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            candidate_artifacts_path=str(
                tmp_path / "out" / f"artifacts_regen_candidate_{attempt}.json"
            ),
            repair_action="REGENERATE_ITEM",
            repair_strategy=strategy,
            selected_evidence_ids=[evidence_id],
            repair_decisions=[decision],
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title"}},
            "findings": {
                "findings": [
                    {"id": f"f{index}", "pages": [index]} for index in range(1, 6)
                ]
            },
            "quote_candidates": {"quote_candidates": [{"id": "q1", "page": 1}]},
        },
        generate_artifacts=lambda **kwargs: original,
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

    assert regeneration_inputs == ["original artifact", "original artifact"]
    assert repair_usage_attempts == [1, 2]
    assert regeneration_targets == [["summary"], ["summary"]]
    assert regeneration_strategies == ["current_evidence", "alternative_evidence"]
    assert retry_memories[0] == []
    assert retry_memories[1][0].introduced[0].rule_id == "candidate_y"
    assert retry_memories[1][0].repair_strategy == "current_evidence"
    assert retry_memories[1][0].strategy_fingerprint == (
        state.regeneration_attempts[0].strategy_fingerprint
    )
    assert retry_memories[1][0].evidence_ids_used == ["f1"]
    assert (
        retry_memories[1][0].candidate_sha256
        == json.loads(
            Path(state.regeneration_attempts[0].candidate_audit_path).read_text(
                encoding="utf-8"
            )
        )["after_sha256"]
    )
    assert len(state.regeneration_attempts) == 2
    assert state.regeneration_attempts[0].promotion_outcome == "rolled_back"
    assert state.regeneration_attempts[1].promotion_outcome == "promoted"
    assert state.artifacts_payload["summary"]["tldr"] == "repaired artifact"
    first_audit = json.loads(
        Path(state.regeneration_attempts[0].candidate_audit_path).read_text(
            encoding="utf-8"
        )
    )
    assert first_audit["repair_delta"]["introduced_hard_failure_count"] == 1
    assert first_audit["repair_decisions"][0]["minimal_patch"][0]["value"] == (
        "failed candidate"
    )
    assert (
        state.artifacts_payload["summary"]["tldr"]
        != first_audit["repair_decisions"][0]["minimal_patch"][0]["value"]
    )
    assert state.validation_report is not None
    assert state.validation_report.status == "pass"
    assert (
        state.regeneration_attempts[1].artifacts_path
        == state.evidence_paths["artifacts"]
    )
    assert (
        state.regeneration_attempts[1].validation_path
        == state.evidence_paths["validation"]
    )


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


__all__ = [
    "test_run_report_analysis_allows_abstained_quote_family",
    "test_run_report_analysis_regenerates_failed_section_until_pass",
    "test_run_report_analysis_rolls_back_failed_candidate_regeneration",
    "test_candidate_promotion_preserves_promoted_retained_claim_severity",
    "test_run_report_analysis_retries_from_last_promoted_artifacts_after_rollback",
    "test_run_report_analysis_maps_topic_section_failures_to_topics_regeneration",
    "test_run_report_analysis_stops_after_regeneration_max_attempts",
    "test_run_report_analysis_uses_one_broad_retry_for_unmappable_failures",
]
