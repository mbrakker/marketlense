from __future__ import annotations

import json
from pathlib import Path

from src.contracts.llm_usage import LLMUsageLedgerAppendRequest, LLMUsageLedgerEntry
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
        "attempt_index": 1,
        "before_sha256": "b" * 64,
        "after_sha256": candidate_fingerprint,
        "transformation_scope": ["summary"],
        "validation_status": "pass" if promotion_outcome == "promoted" else "fail",
        "promotion_outcome": promotion_outcome,
        "validation_issues": [],
        "failure_fingerprints": list(persisting or resolved),
        "repair_action": repair_action,
        "repair_strategy": "current_evidence",
        "selected_evidence_ids": ["finding-1"],
        "strategy_fingerprint": strategy_fingerprint,
        "repair_delta": {
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
    assert scorecard.mode_metrics == ()
