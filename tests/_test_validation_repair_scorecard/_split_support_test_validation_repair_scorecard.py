# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_validation_repair_scorecard.py"
)

import hashlib
import json
from dataclasses import replace
from pathlib import Path
import pytest
from src.contracts.llm_usage import LLMUsageLedgerAppendRequest, LLMUsageLedgerEntry
from src.contracts.regeneration import FailureFingerprint
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationIssue
from src.contracts.validation_reliability import (
    ValidationReliabilityBenchmarkCaseAttribution,
    ValidationReliabilityBuildRequest,
    ValidationReliabilityValidationIdentity,
)
from src.contracts.validation_run_manifest import (
    ValidationRunManifestCreateRequest,
    ValidationRunManifestRecordRequest,
    ValidationRunManifestStageRecord,
)
from src.orchestrators._report_analysis_orchestrator import (
    validation as analysis_validation,
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


def _validation_usage(report_id: str, family: str) -> LLMUsageLedgerEntry:
    action = (
        "validate:grounding"
        if family == "validation_grounding"
        else "validate:semantic"
    )
    return replace(
        _usage(report_id, 0),
        request_id=f"validation-{report_id}-{family}",
        task_id=(f"report:{report_id}:regen:1:validation_regen_candidate_1:{family}"),
        action=action,
        semantic_task=action,
        stage=f"{family.removeprefix('validation_')}_primary",
        artifact_family=family,
        model_policy_namespace="report_vs/validate",
        policy_namespace="report_vs/validate",
        repair_attempt=0,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
