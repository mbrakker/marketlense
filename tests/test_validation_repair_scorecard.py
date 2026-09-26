from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from src.contracts.llm_usage import LLMUsageLedgerAppendRequest, LLMUsageLedgerEntry
from src.contracts.regeneration import FailureFingerprint
from src.contracts.run_context import RunContext
from src.contracts.validation_reliability import ValidationReliabilityBuildRequest
from src.contracts.validation_run_manifest import (
    ValidationRunManifestCreateRequest,
    ValidationRunManifestRecordRequest,
    ValidationRunManifestStageRecord,
)
from src.services.llm_usage_ledger_service import append_usage
from src.services.report_store_service import (
    create_validation_run_manifest,
    record_validation_run_manifest_stage,
)
from src.services.validation_reliability_service import (
    build_validation_reliability_artifact,
)


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="workflow-1",
        task_id="repair-scorecard",
        span_id="span-1",
        trace_id="trace-1",
    )


def _create_manifest(reports_db: str, report_id: str) -> None:
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=reports_db,
            validation_run_id="validation-1",
            cohort_id="cohort-1",
            workflow_run_id="workflow-1",
            configuration_hash="configuration-hash",
            policy_hash="policy-hash",
            producer_build_identity="build-sha",
            created_at_utc="2026-09-20T10:00:00+00:00",
        ),
        _ctx(),
    )
    record_validation_run_manifest_stage(
        ValidationRunManifestRecordRequest(
            schema_version="1.0",
            db_path=reports_db,
            record=ValidationRunManifestStageRecord(
                schema_version="1.0",
                validation_run_id="validation-1",
                cohort_id="cohort-1",
                workflow_run_id="workflow-1",
                entity_type="report",
                publisher_id="publisher-1",
                report_id=report_id,
                source_identity_id=f"source-{report_id}",
                stage="regeneration",
                attempt_number=1,
                parent_attempt_number=0,
                input_artifact_ids=("input-1",),
                output_artifact_ids=("output-1",),
                started_at_utc="2026-09-20T10:00:00+00:00",
                completed_at_utc="2026-09-20T10:01:00+00:00",
                terminal_outcome="succeeded",
                failure_code="",
                retryable=False,
                repair_disposition="targeted_repair",
                duplicate_disposition="none",
                supersession_state="current",
                idempotency_state="new",
                configuration_hash="configuration-hash",
                policy_hash="policy-hash",
                producer_build_identity="build-sha",
            ),
        ),
        _ctx(),
    )


def _usage(report_id: str, repair_attempt: int) -> LLMUsageLedgerEntry:
    return LLMUsageLedgerEntry(
        schema_version="1.0",
        timestamp_utc="2026-09-20T10:00:30+00:00",
        provider="openai",
        action="artifact_regeneration",
        run_id="workflow-1",
        task_id="repair-scorecard",
        span_id="span-1",
        trace_id="trace-1",
        model="gpt-5-mini",
        request_id=f"request-{report_id}",
        publisher_name="Publisher",
        report_name="Report",
        source_url="https://example.test/report",
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        cached_input_tokens=0,
        tool_calls=0,
        estimated_cost_usd=0.012,
        prompt_namespace="report_vs/artifact_repair",
        prompt_hash="prompt-hash",
        provider_decision="openai_primary",
        cache_decision="disabled",
        temperature=0.0,
        seed=7,
        timeout_seconds=30.0,
        semantic_task="artifact_regeneration",
        report_id=report_id,
        workflow="report_analysis",
        stage="regeneration",
        artifact_family="summary",
        validation_run_id="validation-1",
        cohort_id="cohort-1",
        workflow_run_id="workflow-1",
        publisher_id="publisher-1",
        model_policy_namespace="report_vs/artifact_repair",
        policy_namespace="report_vs/artifact_repair",
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_build_identity="build-sha",
        repair_attempt=repair_attempt,
    )


def _audit(
    *,
    report_id: str,
    promotion_outcome: str,
    repair_action: str = "REGENERATE_ITEM",
    strategy_fingerprint: str = "strategy-a",
    candidate_fingerprint: str = "a" * 64,
    resolved: tuple[str, ...] = (),
    persisting: tuple[str, ...] = ("failure-a",),
    attempt_index: int = 1,
    evidence_ids: tuple[str, ...] = ("finding-1",),
) -> dict:
    return {
        "schema_version": "1.0",
        "report_id": report_id,
        "validation_run_id": "validation-1",
        "cohort_id": "cohort-1",
        "workflow_run_id": "workflow-1",
        "configuration_hash": "configuration-hash",
        "policy_hash": "policy-hash",
        "producer_build_identity": "build-sha",
        "attempt_index": attempt_index,
        "before_sha256": "b" * 64,
        "after_sha256": candidate_fingerprint,
        "transformation_scope": ["summary"],
        "allowed_paths": ["summary.tldr"],
        "validation_status": "pass" if promotion_outcome == "promoted" else "fail",
        "promotion_outcome": promotion_outcome,
        "validation_issues": [],
        "failure_fingerprints": list(persisting or resolved),
        "repair_action": repair_action,
        "repair_strategy": "current_evidence",
        "selected_evidence_ids": list(evidence_ids),
        "strategy_fingerprint": strategy_fingerprint,
        "repair_delta": {
            "validator_identity": "validator-v1",
            "introduced_hard_failure_count": 0,
            "mutation_scope_result": "pass",
            "resolved": [
                {
                    "rule_id": "grounding",
                    "affected_section": "summary",
                    "entity_id": value,
                    "evidence_ids": ["finding-1"],
                }
                for value in resolved
            ],
            "persisting": [
                {
                    "rule_id": "grounding",
                    "affected_section": "summary",
                    "entity_id": value,
                    "evidence_ids": ["finding-1"],
                }
                for value in persisting
            ],
            "introduced": [],
        },
        "latency_ms": 250,
    }


def test_repair_scorecard_excludes_rolled_back_and_removed_candidates(
    tmp_path: Path,
) -> None:
    """Changing success to include rollback/removal must fail this scorecard."""

    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    audit_root = tmp_path / "audits"
    for report_id in ("report-1", "report-2", "report-3", "report-4"):
        _create_manifest(reports_db, report_id)
    append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0", db_path=usage_db, entry=_usage("report-3", 1)
        ),
        _ctx(),
    )
    append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=usage_db,
            entry=replace(
                _usage("report-3", 1),
                action="structured_output:repair",
                semantic_task="validation_grounding_model_repair",
                stage="validation_grounding_model_repair",
                artifact_family="validation_grounding",
                input_tokens=900,
                output_tokens=200,
                total_tokens=1100,
                estimated_cost_usd=0.25,
            ),
        ),
        _ctx(),
    )
    audit_payloads = (
        _audit(report_id="report-1", promotion_outcome="rolled_back"),
        _audit(report_id="report-2", promotion_outcome="rolled_back"),
        _audit(
            report_id="report-3",
            promotion_outcome="promoted",
            strategy_fingerprint="strategy-b",
            candidate_fingerprint="c" * 64,
            resolved=("failure-a",),
            persisting=(),
        ),
        _audit(
            report_id="report-4",
            promotion_outcome="promoted",
            repair_action="REMOVE_CLAIM",
            strategy_fingerprint="strategy-c",
            candidate_fingerprint="d" * 64,
            resolved=("failure-a",),
            persisting=(),
        ),
    )
    for index, payload in enumerate(audit_payloads, start=1):
        path = audit_root / f"report-{index}" / "report_analysis"
        path.mkdir(parents=True)
        (path / "regeneration_candidate_audit_1.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
            repair_evidence_root=str(audit_root),
        ),
        _ctx(),
    )

    scorecard = artifact.repair_scorecard
    assert scorecard.measurement_status == "available"
    assert scorecard.repair_chain_count == 4
    assert scorecard.success_at_1_count == 1
    assert scorecard.success_at_1_rate == 0.25
    assert scorecard.success_at_3_count == 1
    assert scorecard.rolled_back_attempt_count == 2
    assert scorecard.abstention_or_removal_attempt_count == 1
    assert scorecard.repeated_failed_strategy_evidence_attempt_count == 2
    assert scorecard.repeated_failed_candidate_attempt_count == 2
    assert scorecard.benchmark_denominator_complete is False
    assert scorecard.hard_failure_introduction_attempt_count == 0
    assert scorecard.hard_failure_introduction_count == 0
    assert scorecard.hard_failure_introduction_rate == 0.0
    assert scorecard.current_residual_failure_odds == 3.0
    assert scorecard.current_residual_failure_odds_state == "available"
    assert scorecard.deterministic_repair_share == 0.75
    assert scorecard.model_repair_share == 0.25
    assert scorecard.model_call_count == 1
    assert scorecard.input_tokens == 100
    assert scorecard.output_tokens == 20
    assert scorecard.estimated_cost_usd == 0.012
    assert scorecard.failure_class_distribution[0].failure_class == "grounding"
    assert scorecard.failure_class_distribution[0].attempt_count == 4
    assert {attempt.failure_rule_ids for attempt in scorecard.attempts} == {
        ("grounding",)
    }
    by_mode = {metric.repair_mode: metric for metric in scorecard.mode_metrics}
    assert by_mode["model"].attempt_count == 1
    assert by_mode["model"].successful_attempt_count == 1
    assert by_mode["model"].model_call_count == 1
    assert by_mode["deterministic"].attempt_count == 3
    assert by_mode["deterministic"].model_call_count == 0


def test_repair_scorecard_marks_missing_retained_audits_unavailable(
    tmp_path: Path,
) -> None:
    """Returning zero success for absent repair evidence must fail this scorecard."""

    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    _create_manifest(reports_db, "report-1")

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    scorecard = artifact.repair_scorecard
    assert scorecard.measurement_status == "unavailable"
    assert scorecard.repair_chain_count is None
    assert scorecard.success_at_1_rate is None
    assert scorecard.usage_attribution == "unavailable"
    assert scorecard.model_call_count is None
    assert scorecard.current_residual_failure_odds_state == "unavailable"
    assert scorecard.mode_metrics == ()


def test_repair_scorecard_does_not_treat_missing_hard_failure_attribution_as_zero(
    tmp_path: Path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    audit_root = tmp_path / "audits"
    _create_manifest(reports_db, "report-1")
    payload = _audit(report_id="report-1", promotion_outcome="rolled_back")
    del payload["repair_delta"]["introduced_hard_failure_count"]
    path = audit_root / "report-1" / "report_analysis"
    path.mkdir(parents=True)
    (path / "regeneration_candidate_audit_1.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
            repair_evidence_root=str(audit_root),
        ),
        _ctx(),
    )

    scorecard = artifact.repair_scorecard
    assert scorecard.repair_attempt_count == 1
    assert scorecard.hard_failure_introduction_count is None
    assert scorecard.hard_failure_introduction_attempt_count is None
    assert scorecard.hard_failure_introduction_rate is None


def test_repair_scorecard_counts_scope_rule_delta_without_diagnostic_text(
    tmp_path: Path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    audit_root = tmp_path / "audits"
    _create_manifest(reports_db, "report-1")
    payload = _audit(report_id="report-1", promotion_outcome="rolled_back")
    payload["repair_delta"]["introduced"] = [
        {
            "rule_id": "regeneration_scope_violation",
            "affected_section": "summary",
            "entity_id": "summary.tldr",
            "evidence_ids": [],
        }
    ]
    payload["repair_delta"]["mutation_scope_result"] = "fail"
    path = audit_root / "report-1" / "report_analysis"
    path.mkdir(parents=True)
    (path / "regeneration_candidate_audit_1.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
            repair_evidence_root=str(audit_root),
        ),
        _ctx(),
    )

    assert artifact.repair_scorecard.out_of_scope_mutation_attempt_count == 1


def test_repair_scorecard_keys_repeated_strategy_by_failure_and_evidence(
    tmp_path: Path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    audit_root = tmp_path / "audits"
    for report_id in ("report-1", "report-2"):
        _create_manifest(reports_db, report_id)
    payloads = (
        _audit(report_id="report-1", promotion_outcome="rolled_back"),
        _audit(
            report_id="report-2",
            promotion_outcome="rolled_back",
            evidence_ids=("finding-2",),
        ),
    )
    for payload in payloads:
        path = audit_root / payload["report_id"] / "report_analysis"
        path.mkdir(parents=True)
        (path / "regeneration_candidate_audit_1.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
            repair_evidence_root=str(audit_root),
        ),
        _ctx(),
    )

    scorecard = artifact.repair_scorecard
    assert scorecard.repeated_failed_strategy_evidence_attempt_count == 0
    assert scorecard.repeated_failed_candidate_attempt_count == 2


def test_repair_scorecard_pairs_a_frozen_baseline_denominator(
    tmp_path: Path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    audit_root = tmp_path / "audits"
    _create_manifest(reports_db, "report-1")
    initial_fingerprint = FailureFingerprint(
        rule_id="grounding",
        affected_section="summary",
        entity_id="failure-a",
        evidence_ids=["finding-1"],
    ).key
    baseline_audit = _audit(
        report_id="report-1",
        promotion_outcome="rolled_back",
        persisting=("failure-a",),
    )
    baseline_manifest = {
        "schema_version": "1.0",
        "frozen": True,
        "baseline_identity": {
            "configuration_hash": "configuration-hash",
            "policy_hash": "policy-hash",
            "producer_build_identity": "build-sha",
            "validator_identity": "validator-v1",
            "schema_identity_sha256": "2" * 64,
        },
        "cases": [
            {
                "report_id": "report-1",
                "original_artifact_canonical_sha256": "b" * 64,
                "initial_validation_sha256": "e" * 64,
                "initial_failure_fingerprints": [initial_fingerprint],
                "evidence_pack_sha256": {"findings": "f" * 64},
                "expected_legal_mutation_scope": ["summary.tldr"],
                "identities": {
                    "prompt_identity_sha256": "1" * 64,
                    "artifact_schema_identity": "schema-" + "2" * 64,
                    "validator_identity": "validator-v1",
                    "configuration_hash": "configuration-hash",
                    "policy_hash": "policy-hash",
                    "producer_build_identity": "build-sha",
                },
                "historical_outcome": "rolled_back_validation_fail",
                "baseline_attempts": [baseline_audit],
            }
        ],
    }
    canonical = (
        json.dumps(
            baseline_manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    )
    baseline_manifest["manifest_sha256"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    manifest_path = tmp_path / "frozen-benchmark.json"
    manifest_path.write_text(json.dumps(baseline_manifest), encoding="utf-8")

    first = _audit(
        report_id="report-1",
        promotion_outcome="rolled_back",
        persisting=("failure-a",),
        attempt_index=1,
    )
    second = _audit(
        report_id="report-1",
        promotion_outcome="promoted",
        strategy_fingerprint="strategy-b",
        candidate_fingerprint="c" * 64,
        resolved=("failure-a",),
        persisting=(),
        attempt_index=2,
    )
    for payload in (first, second):
        path = audit_root / "report-1" / "report_analysis"
        path.mkdir(parents=True, exist_ok=True)
        (
            path / f"regeneration_candidate_audit_{payload['attempt_index']}.json"
        ).write_text(json.dumps(payload), encoding="utf-8")

    request = ValidationReliabilityBuildRequest(
        schema_version="1.0",
        reports_db_path=reports_db,
        usage_db_path=usage_db,
        validation_run_id="validation-1",
        repair_evidence_root=str(audit_root),
        repair_benchmark_manifest_path=str(manifest_path),
        current_schema_identity_sha256="2" * 64,
    )
    artifact = build_validation_reliability_artifact(request, _ctx())

    scorecard = artifact.repair_scorecard
    assert scorecard.benchmark_case_count == 1
    assert scorecard.benchmark_denominator_complete is True
    assert scorecard.benchmark_comparison_status == "paired"
    assert scorecard.success_at_1_count == 0
    assert scorecard.success_at_3_count == 1
    assert scorecard.baseline_success_at_3_count == 0
    assert scorecard.baseline_residual_failure_odds_state == "unbounded"
    assert scorecard.current_residual_failure_odds == 0
    assert scorecard.residual_odds_reduction_state == "unbounded"
    assert scorecard.baseline_usage_attribution == "unavailable"

    second["allowed_paths"] = ["summary.tldr", "expert_comment"]
    second_path = (
        audit_root
        / "report-1"
        / "report_analysis"
        / "regeneration_candidate_audit_2.json"
    )
    second_path.write_text(json.dumps(second), encoding="utf-8")
    broadened = build_validation_reliability_artifact(request, _ctx())
    assert broadened.repair_scorecard.benchmark_denominator_complete is True
    assert broadened.repair_scorecard.out_of_scope_mutation_attempt_count == 1
    assert broadened.repair_scorecard.success_at_3_count == 0

    incompatible = build_validation_reliability_artifact(
        replace(request, current_schema_identity_sha256="3" * 64), _ctx()
    )
    assert incompatible.repair_scorecard.benchmark_denominator_complete is False
    assert incompatible.repair_scorecard.benchmark_comparison_status == "incompatible"
