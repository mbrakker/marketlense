from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.quality._cto_review_evidence.run_projection import (
    FORMAT_GENERIC,
    FORMAT_PROVIDER_PROFILE,
    FORMAT_REUSE,
    FORMAT_WORDPRESS,
    project_cto_evidence,
)
from src.contracts.cto_evidence import (
    CTOEvidenceOutcomeCount,
    cto_evidence_bundle_payload,
    parse_cto_evidence_bundle,
    validate_cto_evidence_bundle,
)

COLLECTOR_SHA = "a" * 40
RUN_SHA = "b" * 40
BASELINE_SHA = "c" * 40
SUBJECT_IDENTITY = hashlib.sha256(b"opaque-subject").hexdigest()


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, sort_keys=True).encode("utf-8")
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _source(
    path: Path,
    *,
    source_id: str = "run_metrics",
    tested_sha: str | None = RUN_SHA,
    role: str = "run",
    format_id: str = FORMAT_GENERIC,
    payload: object | None = None,
) -> dict[str, object]:
    digest = _write_json(path, payload if payload is not None else {})
    return {
        "schema_version": "1.0",
        "source_id": source_id,
        "producer": "fixture_producer",
        "format_id": format_id,
        "path": path.relative_to(path.parents[1]).as_posix(),
        "sha256": digest,
        "tested_repository_sha": tested_sha,
        "role": role,
    }


def _run_manifest(
    *,
    sources: list[dict[str, object]],
    required: list[str] | None = None,
    criteria: list[dict[str, object]] | None = None,
    comparison: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "run_id": "fixture-run",
        "run_type": "unlisted-run-kind",
        "objective": "Check run-scoped evidence projection.",
        "tested_repository_sha": RUN_SHA,
        "producer_repository_sha": COLLECTOR_SHA,
        "started_at_utc": "2026-10-06T10:00:00Z",
        "ended_at_utc": "2026-10-06T10:01:00Z",
        "subjects": [
            {
                "schema_version": "1.0",
                "subject_id": "subject-1",
                "identity_sha256": SUBJECT_IDENTITY,
                "immutable": True,
            }
        ],
        "configuration_identities": [],
        "stages_in_scope": ["generation"],
        "stages_out_of_scope": ["publication"],
        "external_side_effects_enabled": False,
        "operator_intervention_policy": "No operator intervention.",
        "sources": sources,
        "required_evidence_classes": required or [],
        "criteria": criteria or [],
        "comparison": comparison,
    }


def _project(tmp_path: Path, manifest: dict[str, object]):
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "run.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    historical_path = root / "runtime_telemetry.json"
    historical_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "legacy_usage": {
                    "status": "available",
                    "values": {"cost_usd": 900.0, "request_count": 1200},
                },
            }
        ),
        encoding="utf-8",
    )
    bundle = project_cto_evidence(
        run_manifest_path=manifest_path,
        repository_root=root,
        collector_repository_sha=COLLECTOR_SHA,
        historical_telemetry_path=historical_path,
    )
    return root, bundle


def _generic_payload(**overrides: object) -> dict[str, object]:
    return {
        "tested_repository_sha": RUN_SHA,
        "measurements": {"resource.cost_usd": 1.25, "resource.provider_calls": 3},
        "subjects": [
            {
                "identity_sha256": SUBJECT_IDENTITY,
                "outcome": "success",
                "metrics": {"resource.cost_usd": 1.25, "resource.provider_calls": 3},
            }
        ],
        "outcomes": {"success": 1},
        "attempts": [
            {
                "subject_identity_sha256": SUBJECT_IDENTITY,
                "attempt_number": 1,
                "kind": "initial_execution",
                "outcome": "failed",
                "failure_code": "validation_failed",
            },
            {
                "subject_identity_sha256": SUBJECT_IDENTITY,
                "attempt_number": 2,
                "parent_attempt_number": 1,
                "kind": "deterministic_recovery",
                "outcome": "success",
            },
        ],
        "reuse_decisions": [
            {
                "subject_identity_sha256": SUBJECT_IDENTITY,
                "eligible_candidates": 2,
                "reused_validations": 1,
                "newly_executed_validations": 1,
                "avoided_grounding_calls": 4,
                "avoided_provider_calls": 2,
                "fallback_reason_code": None,
            }
        ],
        **overrides,
    }


def test_run_metrics_are_separate_from_historical_context_and_keep_attempts(
    tmp_path: Path,
) -> None:
    source_payload = _generic_payload()
    source = _source(
        tmp_path / "repo" / "evidence" / "metrics.json", payload=source_payload
    )
    _, bundle = _project(
        tmp_path,
        _run_manifest(
            sources=[source],
            required=["measurements", "outcomes", "attempt_history", "reuse"],
        ),
    )

    assert bundle.completeness == "complete", (
        bundle.limitations,
        bundle.run_evidence.limitations if bundle.run_evidence else None,
    )
    assert bundle.run_evidence is not None
    run_metrics = {item.metric_id: item for item in bundle.run_evidence.metrics}
    historical_metrics = {
        item.metric_id: item for item in bundle.historical_state.metrics
    }
    assert run_metrics["run_metrics.resource.cost_usd"].value == 1.25
    aggregate_costs = [
        item
        for item in bundle.run_evidence.metrics
        if item.metric_id == "run_metrics.resource.cost_usd" and item.subject_id is None
    ]
    assert aggregate_costs, [
        (item.metric_id, item.subject_id, item.value)
        for item in bundle.run_evidence.metrics
    ]
    aggregate_cost = aggregate_costs[0]
    subject_cost = next(
        item
        for item in bundle.run_evidence.metrics
        if item.metric_id == "run_metrics.resource.cost_usd"
        and item.subject_id == "subject-1"
    )
    assert aggregate_cost.value == subject_cost.value == 1.25
    assert historical_metrics["historical.legacy_usage.cost_usd"].value == 900.0
    assert all(
        not item.metric_id.startswith("historical.")
        for item in bundle.run_evidence.metrics
    )
    assert [(item.outcome, item.count) for item in bundle.run_evidence.outcomes] == [
        ("success", 1)
    ]
    assert [item.kind for item in bundle.run_evidence.attempts] == [
        "initial_execution",
        "deterministic_recovery",
    ]
    assert bundle.executive_summary.recovery_attempt_count == 1
    assert bundle.executive_summary.reused_validation_count == 1
    assert bundle.executive_summary.avoided_provider_call_count == 2
    decision = bundle.run_evidence.reuse_decisions[0]
    assert decision.avoided_provider_calls == 2
    assert "actual" not in decision.__dataclass_fields__
    payload = cto_evidence_bundle_payload(bundle)
    assert parse_cto_evidence_bundle(payload) == bundle


def test_unavailable_run_measurements_stay_unavailable_and_required_class_is_incomplete(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "repo" / "evidence" / "metrics.json",
        payload={
            "tested_repository_sha": RUN_SHA,
            "subjects": [{"identity_sha256": SUBJECT_IDENTITY, "outcome": "success"}],
        },
    )
    manifest = _run_manifest(
        sources=[source],
        required=["measurements", "provider_timing", "outcomes"],
        criteria=[
            {
                "schema_version": "1.0",
                "criterion_id": "publication-is-out-of-scope",
                "description": "Publication is explicitly excluded.",
                "metric_id": "publication.writes",
                "operator": "eq",
                "expected_value": 0,
                "required": True,
                "stage": "publication",
            },
            {
                "schema_version": "1.0",
                "criterion_id": "run-cost-retained",
                "description": "The run must retain a measured cost value.",
                "metric_id": "run_metrics.resource.cost_usd",
                "operator": "gte",
                "expected_value": 0,
                "required": True,
                "stage": "generation",
            },
        ],
    )
    _, bundle = _project(tmp_path, manifest)

    assert bundle.completeness == "incomplete"
    assert bundle.disposition == "insufficient_evidence"
    assert bundle.run_evidence is not None
    cost = next(
        item
        for item in bundle.run_evidence.metrics
        if item.metric_id == "resource.cost_usd"
    )
    assert cost.status == "unavailable"
    assert cost.value is None
    assert bundle.run_evidence.criteria[0].disposition == "not_evaluated"
    assert bundle.run_evidence.criteria[0].actual_value is None
    assert bundle.run_evidence.criteria[1].disposition == "insufficient_evidence"


def test_exact_tested_sha_mismatch_marks_bundle_invalid(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "repo" / "evidence" / "metrics.json",
        payload={"tested_repository_sha": BASELINE_SHA, "measurements": {"calls": 1}},
    )
    _, bundle = _project(tmp_path, _run_manifest(sources=[source]))

    assert bundle.completeness == "invalid"
    assert bundle.disposition == "fail"
    assert any("tested SHA contradicts" in item for item in bundle.limitations)


def test_required_exact_sha_is_incomplete_without_source_binding(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "repo" / "evidence" / "unbound.json",
        tested_sha=None,
        payload={"measurements": {"provider_calls": 1}},
    )
    _, bundle = _project(
        tmp_path,
        _run_manifest(sources=[source], required=["exact_repository_sha"]),
    )

    assert bundle.completeness == "incomplete"
    assert any("exact_repository_sha" in item for item in bundle.limitations)


def test_exact_sha_requires_every_run_source_to_be_bound(tmp_path: Path) -> None:
    sources = [
        _source(
            tmp_path / "repo" / "evidence" / "metrics-1.json",
            source_id="run_metrics_1",
            payload={"measurements": {"calls": 1}},
        ),
        _source(
            tmp_path / "repo" / "evidence" / "metrics-2.json",
            source_id="run_metrics_2",
            tested_sha=None,
            payload={
                "tested_repository_sha": RUN_SHA,
                "measurements": {"calls": 2},
            },
        ),
    ]

    _, bundle = _project(tmp_path, _run_manifest(sources=sources))

    assert bundle.completeness == "complete"


def test_exact_sha_is_incomplete_when_one_candidate_source_is_unbound(
    tmp_path: Path,
) -> None:
    bound = _source(
        tmp_path / "repo" / "evidence" / "bound.json",
        source_id="bound_metrics",
        payload={"measurements": {"calls": 1}},
    )
    unbound = _source(
        tmp_path / "repo" / "evidence" / "unbound.json",
        source_id="unbound_metrics",
        tested_sha=None,
        role="candidate",
        payload={"measurements": {"retries": 2}},
    )

    _, bundle = _project(
        tmp_path,
        _run_manifest(sources=[bound, unbound], required=["exact_repository_sha"]),
    )

    assert bundle.completeness == "incomplete"
    assert bundle.disposition != "pass"
    assert any("exact_repository_sha" in item for item in bundle.limitations)


def test_exact_sha_contradiction_in_one_run_source_is_invalid(tmp_path: Path) -> None:
    bound = _source(
        tmp_path / "repo" / "evidence" / "bound.json",
        source_id="bound_metrics",
        payload={"measurements": {"calls": 1}},
    )
    contradictory = _source(
        tmp_path / "repo" / "evidence" / "contradictory.json",
        source_id="contradictory_metrics",
        payload={
            "tested_repository_sha": BASELINE_SHA,
            "measurements": {"retries": 2},
        },
    )

    _, bundle = _project(tmp_path, _run_manifest(sources=[bound, contradictory]))

    assert bundle.completeness == "invalid"
    assert bundle.disposition == "fail"


def test_unbound_supporting_source_does_not_block_exact_run_sha(
    tmp_path: Path,
) -> None:
    run_source = _source(
        tmp_path / "repo" / "evidence" / "run.json",
        source_id="run_metrics",
        payload={"measurements": {"calls": 1}},
    )
    supporting_source = _source(
        tmp_path / "repo" / "evidence" / "context.json",
        source_id="context",
        tested_sha=None,
        role="supporting",
        payload={"measurements": {"context_count": 1}},
    )

    _, bundle = _project(
        tmp_path, _run_manifest(sources=[run_source, supporting_source])
    )

    assert bundle.completeness == "complete"


def test_per_subject_totals_that_disagree_with_run_totals_are_invalid(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "repo" / "evidence" / "metrics.json",
        payload={
            "tested_repository_sha": RUN_SHA,
            "measurements": {"resource.cost_usd": 2.0},
            "subjects": [
                {
                    "identity_sha256": SUBJECT_IDENTITY,
                    "outcome": "success",
                    "metrics": {"resource.cost_usd": 1.0},
                }
            ],
        },
    )
    _, bundle = _project(tmp_path, _run_manifest(sources=[source]))

    assert bundle.completeness == "invalid"
    assert bundle.disposition == "fail"
    assert any("do not reconcile" in item for item in bundle.limitations)


def test_comparison_records_delta_without_causal_claim(tmp_path: Path) -> None:
    baseline_payload = {
        "tested_repository_sha": BASELINE_SHA,
        "measurements": {"wall_seconds": 10},
    }
    candidate_payload = {
        "tested_repository_sha": RUN_SHA,
        "measurements": {"wall_seconds": 7},
    }
    baseline = _source(
        tmp_path / "repo" / "evidence" / "baseline.json",
        source_id="baseline",
        tested_sha=BASELINE_SHA,
        role="baseline",
        payload=baseline_payload,
    )
    candidate = _source(
        tmp_path / "repo" / "evidence" / "candidate.json",
        source_id="candidate",
        tested_sha=RUN_SHA,
        role="candidate",
        payload=candidate_payload,
    )
    identity = [{"schema_version": "1.0", "key": "dataset", "value": "cohort-v1"}]
    comparison = {
        "schema_version": "1.0",
        "comparison_id": "optimization-check",
        "baseline_source_id": "baseline",
        "candidate_source_id": "candidate",
        "baseline_selector": "measurements",
        "candidate_selector": "measurements",
        "baseline_repository_sha": BASELINE_SHA,
        "candidate_repository_sha": RUN_SHA,
        "baseline_identity": identity,
        "candidate_identity": identity,
        "invariants": [],
        "changed_variables": ["provider_concurrency"],
        "limitations": ["Workload variance remains possible."],
    }
    _, bundle = _project(
        tmp_path,
        _run_manifest(
            sources=[baseline, candidate],
            required=["comparison"],
            comparison=comparison,
        ),
    )

    assert bundle.run_evidence is not None
    projected = bundle.run_evidence.comparison
    assert projected is not None
    assert projected.status == "compatible"
    assert projected.causal_attribution == "not_established"
    assert projected.metric_deltas[0].value == -3.0
    assert projected.limitations == ("Workload variance remains possible.",)
    assert parse_cto_evidence_bundle(cto_evidence_bundle_payload(bundle)) == bundle


def test_missing_source_is_incomplete_and_hash_mismatch_is_invalid(
    tmp_path: Path,
) -> None:
    source = {
        "schema_version": "1.0",
        "source_id": "missing_source",
        "producer": "fixture_producer",
        "format_id": FORMAT_GENERIC,
        "path": "evidence/missing.json",
        "sha256": "d" * 64,
        "tested_repository_sha": RUN_SHA,
        "role": "run",
    }
    _, missing_bundle = _project(
        tmp_path / "missing", _run_manifest(sources=[source], required=["measurements"])
    )
    assert missing_bundle.completeness == "incomplete"
    assert missing_bundle.disposition != "pass"

    mismatch_source = _source(
        tmp_path / "mismatch" / "repo" / "evidence" / "actual.json",
        payload={"tested_repository_sha": RUN_SHA, "measurements": {"calls": 1}},
    )
    mismatch_source["sha256"] = "e" * 64
    _, mismatch_bundle = _project(
        tmp_path / "mismatch", _run_manifest(sources=[mismatch_source])
    )
    assert mismatch_bundle.completeness == "invalid"
    assert mismatch_bundle.disposition == "fail"


def test_wordpress_attempt_readback_and_repeat_are_independent(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "repo" / "evidence" / "wordpress.json",
        format_id=FORMAT_WORDPRESS,
        payload={
            "producer_commit": RUN_SHA,
            "scope": {"authorized_publication_subset_size": 11},
            "publication_attempt": {
                "created_count": 6,
                "blocked_count": 5,
                "outcome_counts": {"error": 0},
            },
            "readback": {
                "status": "not_completed",
                "authenticated_full_readback_verified_count": None,
            },
            "repeat_publication": {"status": "not_run", "actual_writes": None},
        },
    )
    _, bundle = _project(
        tmp_path,
        _run_manifest(sources=[source], required=["external_actions", "side_effects"]),
    )

    assert bundle.completeness == "complete"
    assert bundle.run_evidence is not None
    action = bundle.run_evidence.external_actions[0]
    assert action.attempted_actions == 11
    assert action.actual_writes is None
    assert action.skipped_actions is None
    assert action.blocked_actions == 5
    assert action.authenticated_readback == "not_run"
    assert action.repeat_result == "not_run"
    assert action.idempotency_result == "not_evaluated"


def test_wordpress_zero_write_replay_does_not_claim_readback(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "repo" / "evidence" / "wordpress.json",
        format_id=FORMAT_WORDPRESS,
        payload={
            "producer_commit": RUN_SHA,
            "scope": {"authorized_publication_subset_size": 0},
            "publication_attempt": {
                "created_count": 0,
                "blocked_count": 0,
                "outcome_counts": {"error": 0},
            },
            "readback": {"status": "not_completed"},
            "repeat_publication": {"status": "verified", "actual_writes": 0},
        },
    )
    _, bundle = _project(tmp_path, _run_manifest(sources=[source]))

    assert bundle.run_evidence is not None
    action = bundle.run_evidence.external_actions[0]
    assert action.actual_writes is None
    assert action.authenticated_readback == "not_run"
    assert action.repeat_result == "zero_write"
    assert action.idempotency_result == "passed"


def test_provider_elapsed_and_active_wall_are_distinct_measurements(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "repo" / "evidence" / "provider.json",
        payload={
            "tested_repository_sha": RUN_SHA,
            "measurements": {
                "provider_elapsed_ms_total": 700,
                "provider_active_wall_ms": 420,
                "queue_wait_ms_total": 80,
            },
        },
    )
    _, bundle = _project(
        tmp_path,
        _run_manifest(sources=[source], required=["provider_timing"]),
    )

    assert bundle.completeness == "incomplete"
    assert bundle.disposition != "pass"
    assert bundle.run_evidence is not None
    metrics = {item.metric_id: item for item in bundle.run_evidence.metrics}
    total = metrics["run_metrics.provider_elapsed_ms_total"]
    active = metrics["run_metrics.provider_active_wall_ms"]
    assert total.value == 700 and active.value == 420
    assert "not critical path" in total.measurement_semantics
    assert "union of active provider intervals" in active.measurement_semantics
    executive_metrics = bundle.executive_summary.key_metrics
    assert len(executive_metrics) <= 20
    assert {item.metric_id for item in executive_metrics} >= {
        "run_metrics.provider_elapsed_ms_total",
        "run_metrics.provider_active_wall_ms",
    }
    assert any("provider_timing" in item for item in bundle.limitations)


def test_provider_profile_binds_only_the_declared_hashed_report_subject(
    tmp_path: Path,
) -> None:
    report_id = "fixture-provider-report"
    source = _source(
        tmp_path / "repo" / "evidence" / "provider.json",
        format_id=FORMAT_PROVIDER_PROFILE,
        payload={
            "report_id": report_id,
            "provider_elapsed_ms_total": 700,
            "provider_active_wall_ms": 420,
            "report_wall_clock_seconds": 8.0,
            "estimated_cost_usd": 1.25,
        },
    )
    manifest = _run_manifest(
        sources=[source],
        required=["immutable_subjects", "provider_timing", "resource_usage"],
    )
    subjects = manifest["subjects"]
    assert isinstance(subjects, list) and isinstance(subjects[0], dict)
    subjects[0]["identity_sha256"] = hashlib.sha256(
        report_id.encode("utf-8")
    ).hexdigest()
    _, bundle = _project(tmp_path, manifest)

    assert bundle.completeness == "complete"
    assert bundle.run_evidence is not None
    profile_metrics = [
        item
        for item in bundle.run_evidence.metrics
        if item.metric_id.startswith("run_metrics.")
    ]
    assert profile_metrics
    assert any(item.subject_id == "subject-1" for item in profile_metrics)
    assert any(item.subject_id is None for item in profile_metrics)
    assert report_id not in json.dumps(cto_evidence_bundle_payload(bundle))


def test_aggregate_reuse_counters_are_summarized_without_fake_subject_rows(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "repo" / "evidence" / "reuse.json",
        format_id=FORMAT_REUSE,
        payload={
            "implementation_commit": RUN_SHA,
            "repair_bearing_follow_up": {
                "summed_reuse_counters": {
                    "reused_validation_results": 7,
                    "newly_validated_claims": 5,
                    "grounding_calls_avoided": 3,
                    "semantic_validation_calls_avoided": 2,
                },
                "reuse_decisions": [{"outcome": "pass"}],
            },
        },
    )
    _, bundle = _project(
        tmp_path,
        _run_manifest(sources=[source], required=["reuse"]),
    )

    assert bundle.completeness == "complete"
    assert bundle.run_evidence is not None
    assert bundle.run_evidence.reuse_evidence_status == "partial"
    assert bundle.run_evidence.reuse_decisions == ()
    assert bundle.executive_summary.reused_validation_count == 7
    assert bundle.executive_summary.avoided_provider_call_count == 5


def test_acquisition_retry_preserves_attempts_and_per_subject_cost(
    tmp_path: Path,
) -> None:
    candidate_id = "acquisition-candidate"
    source = _source(
        tmp_path / "repo" / "evidence" / "acquisition.json",
        format_id="marketlense/acquisition-projection/1.0",
        payload={
            "before_after": {},
            "attempts": [
                {
                    "candidate_id": candidate_id,
                    "tested_commit": RUN_SHA,
                    "verified_artifact": False,
                    "failure_class": "transient_fetch",
                    "agent_calls": 2,
                    "browser_launches": 1,
                    "cost_usd": 0.5,
                    "duration_seconds": 3.0,
                    "mailbox_reads": 1,
                    "tokens": 100,
                },
                {
                    "candidate_id": candidate_id,
                    "tested_commit": RUN_SHA,
                    "verified_artifact": True,
                    "agent_calls": 1,
                    "browser_launches": 0,
                    "cost_usd": 1.0,
                    "duration_seconds": 4.0,
                    "mailbox_reads": 0,
                    "tokens": 150,
                },
            ],
        },
    )
    manifest = _run_manifest(
        sources=[source],
        required=["outcomes", "attempt_history", "resource_usage"],
    )
    subjects = manifest["subjects"]
    assert isinstance(subjects, list) and isinstance(subjects[0], dict)
    subjects[0]["identity_sha256"] = hashlib.sha256(
        candidate_id.encode("utf-8")
    ).hexdigest()
    _, bundle = _project(tmp_path, manifest)

    assert bundle.completeness == "complete"
    assert bundle.run_evidence is not None
    assert [(item.kind, item.outcome) for item in bundle.run_evidence.attempts] == [
        ("initial_execution", "failed"),
        ("workflow_retry", "success"),
    ]
    assert [(item.outcome, item.count) for item in bundle.run_evidence.outcomes] == [
        ("acquired", 1)
    ]
    costs = [
        item
        for item in bundle.run_evidence.metrics
        if item.metric_id == "resource.acquisition.cost_usd"
    ]
    assert sorted(item.value for item in costs if item.value is not None) == [1.5, 1.5]


def test_generic_cost_metric_name_does_not_prove_resource_usage(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "repo" / "evidence" / "generic-cost.json",
        payload={"measurements": {"estimated_cost_usd": 1.25}},
    )

    _, bundle = _project(
        tmp_path,
        _run_manifest(sources=[source], required=["resource_usage"]),
    )

    assert bundle.completeness == "incomplete"
    assert bundle.disposition != "pass"
    assert bundle.run_evidence is not None
    cost = next(
        item
        for item in bundle.run_evidence.metrics
        if item.metric_id == "run_metrics.estimated_cost_usd"
    )
    assert cost.value == 1.25
    assert any("resource_usage" in item for item in bundle.limitations)


def test_unregistered_source_format_is_incomplete_not_silently_complete(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "repo" / "evidence" / "unknown.json",
        format_id="marketlense/unregistered-format/1.0",
        payload={"measurements": {"wall_seconds": 2}},
    )
    _, bundle = _project(
        tmp_path,
        _run_manifest(sources=[source], required=["measurements"]),
    )

    assert bundle.completeness == "incomplete"
    assert bundle.disposition == "not_evaluated"
    assert any("No projection adapter" in item for item in bundle.limitations)


def test_complete_outcome_totals_must_match_subject_terminal_outcomes(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "repo" / "evidence" / "metrics.json",
        payload=_generic_payload(),
    )
    _, bundle = _project(
        tmp_path,
        _run_manifest(sources=[source], required=["outcomes"]),
    )

    assert bundle.completeness == "complete"
    assert bundle.run_evidence is not None
    contradictory_outcomes = (
        CTOEvidenceOutcomeCount(schema_version="1.0", outcome="success", count=2),
    )
    contradictory_evidence = replace(
        bundle.run_evidence, outcomes=contradictory_outcomes
    )
    contradictory_summary = replace(
        bundle.executive_summary, outcomes=contradictory_outcomes
    )
    contradictory_bundle = replace(
        bundle,
        run_evidence=contradictory_evidence,
        executive_summary=contradictory_summary,
    )

    with pytest.raises(ValueError, match="outcome totals do not reconcile"):
        validate_cto_evidence_bundle(contradictory_bundle)


def test_artifact_dag_comparison_verifies_each_endpoint_sha(tmp_path: Path) -> None:
    dag_path = tmp_path / "repo" / "evidence" / "dag.json"
    dag_payload = {
        "implementation": {"base_commit": BASELINE_SHA, "dag_commit": RUN_SHA},
        "before": {"duration_seconds": 12.0},
        "after": {"duration_seconds": 8.0},
        "comparison": {"measurement_limit": "Matched local benchmark runs."},
    }
    baseline = _source(
        dag_path,
        source_id="baseline",
        tested_sha=BASELINE_SHA,
        role="baseline",
        format_id="marketlense/artifact-dag-benchmark/1.0",
        payload=dag_payload,
    )
    candidate = _source(
        dag_path,
        source_id="candidate",
        tested_sha=RUN_SHA,
        role="candidate",
        format_id="marketlense/artifact-dag-benchmark/1.0",
        payload=dag_payload,
    )
    identity = [{"schema_version": "1.0", "key": "cohort", "value": "same-cohort"}]
    comparison = {
        "schema_version": "1.0",
        "comparison_id": "dag-before-after",
        "baseline_source_id": "baseline",
        "candidate_source_id": "candidate",
        "baseline_selector": "before",
        "candidate_selector": "after",
        "baseline_repository_sha": BASELINE_SHA,
        "candidate_repository_sha": RUN_SHA,
        "baseline_identity": identity,
        "candidate_identity": identity,
        "invariants": [],
        "changed_variables": ["artifact_scheduling"],
        "limitations": ["Local timings may vary."],
    }
    _, bundle = _project(
        tmp_path,
        _run_manifest(
            sources=[baseline, candidate],
            required=["comparison"],
            comparison=comparison,
        ),
    )

    assert bundle.completeness == "complete"
    assert bundle.run_evidence is not None
    assert bundle.run_evidence.comparison is not None
    assert bundle.run_evidence.comparison.status == "compatible"
    assert bundle.run_evidence.comparison.metric_deltas[0].value == -4.0


def test_crop_qa_uses_existing_sidecar_and_hashes_candidate_identity(
    tmp_path: Path,
) -> None:
    candidate_id = "fixture-crop-candidate"
    sidecar = _source(
        tmp_path / "repo" / candidate_id / "crop.qa.json",
        source_id="crop_qa",
        format_id="marketlense/crop-qa-sidecar/1.0",
        payload={
            "candidate_id": candidate_id,
            "candidate_type": "figure",
            "mode": "publication_strict",
            "accepted": True,
            "render_dpi": 300,
            "qa": {
                "accepted": True,
                "total_score": 0.9,
                "defect_labels": [],
                "detectors": {},
            },
        },
    )
    manifest = _run_manifest(
        sources=[sidecar],
        required=["immutable_subjects", "visual_quality"],
    )
    subjects = manifest["subjects"]
    assert isinstance(subjects, list) and isinstance(subjects[0], dict)
    subjects[0]["identity_sha256"] = hashlib.sha256(
        candidate_id.encode("utf-8")
    ).hexdigest()
    _, bundle = _project(tmp_path, manifest)

    assert bundle.completeness == "complete"
    assert bundle.run_evidence is not None
    assert bundle.run_evidence.quality_dimensions[0].reviewed_subject_count == 1
    assert candidate_id not in json.dumps(cto_evidence_bundle_payload(bundle))
