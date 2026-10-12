from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from scripts.quality.ias_live_canary_runner import (
    _ValidationReuseEventCapture,
    _read_failure_diagnostic,
    _validation_reuse_telemetry_summary,
)
from src.utils.logging import log_event, new_run_context


def test_validation_reuse_capture_retains_only_bounded_decision_counters(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "validation_claim_reuse_decisions.jsonl"
    logger = logging.getLogger("market_lense.validation_generator")
    prior_level = logger.level
    context = new_run_context(task_id="reuse-capture-test")

    with _ValidationReuseEventCapture(event_path) as handler:
        logger.info(
            log_event(
                context,
                role="generator",
                event="prompt_rendered_identity",
                module="market_lense.validation_generator",
                fields={"prompt_content_hash": "not-the-target-event"},
            )
        )
        logger.info(
            log_event(
                context,
                role="generator",
                event="validation_claim_reuse_decided",
                module="market_lense.validation_generator",
                fields={
                    "total_candidate_claims": 2,
                    "reused_validation_results": 1,
                    "newly_validated_claims": 1,
                    "grounding_calls_avoided": 1,
                    "semantic_validation_calls_avoided": 1,
                    "reuse_fallback_reason_counts": {"new_claim": 1},
                    "claim_text": "private claim content must not be retained",
                },
            )
        )

    lines = event_path.read_text(encoding="utf-8").splitlines()
    assert logger.level == prior_level
    assert handler.event_count == 1
    assert len(lines) == 1
    assert "private claim content" not in lines[0]
    event = json.loads(lines[0])
    assert event["event"] == "validation_claim_reuse_decided"
    assert event["fields"] == {
        "total_candidate_claims": 2,
        "reused_validation_results": 1,
        "newly_validated_claims": 1,
        "grounding_calls_avoided": 1,
        "semantic_validation_calls_avoided": 1,
        "reuse_fallback_reason_counts": {"new_claim": 1},
    }
    summary = _validation_reuse_telemetry_summary(event_path, handler)
    assert summary["event_count"] == 1
    assert summary["totals_across_validation_passes"] == {
        "total_candidate_claims": 2,
        "reused_validation_results": 1,
        "newly_validated_claims": 1,
        "grounding_calls_avoided": 1,
        "semantic_validation_calls_avoided": 1,
    }
    assert summary["reuse_fallback_reason_counts"] == {"new_claim": 1}


def test_failure_diagnostic_uses_retained_validation_finding_without_source_text(
    tmp_path: Path,
) -> None:
    """A terminal validation export identifies a retained rule and entity."""

    validation_path = tmp_path / "validation.json"
    validation_path.write_text(
        json.dumps(
            {
                "status": "fail",
                "issues": [
                    {
                        "severity": "error",
                        "rule_id": "schema_reference_missing",
                        "affected_section": "editorial_plan",
                        "entity_id": "finding:42",
                        "evidence_ids": ["finding:42"],
                        "message": "private source text must not be exported",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    reports_db = tmp_path / "reports.sqlite"
    with sqlite3.connect(reports_db) as conn:
        conn.executescript(
            """
            CREATE TABLE validation_run_entity_attempts (
              attempt_id TEXT, validation_run_id TEXT, report_id TEXT,
              attempt_number INTEGER
            );
            CREATE TABLE validation_run_stage_records (
              attempt_id TEXT, stage TEXT, failure_code TEXT,
              repair_disposition TEXT, output_artifact_ids_json TEXT,
              completed_at_utc TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO validation_run_entity_attempts VALUES (?, ?, ?, ?)",
            ("attempt-1", "validation-1", "report-1", 1),
        )
        conn.execute(
            "INSERT INTO validation_run_stage_records VALUES (?, ?, ?, ?, ?, ?)",
            (
                "attempt-1",
                "semantic_validation",
                "validation_failed",
                "targeted_repair",
                json.dumps([str(validation_path)]),
                "2026-09-19T12:00:00Z",
            ),
        )

    diagnostic = _read_failure_diagnostic(
        state_db=tmp_path / "workflow.sqlite",
        reports_db=reports_db,
        report_id="report-1",
        validation_run_id="validation-1",
        root_workflow_id="workflow-1",
        outer_code="validation_failed",
    )

    assert diagnostic == {
        "stage": "semantic_validation",
        "outer_code": "validation_failed",
        "inner_error_class": "",
        "validator_rule": "schema_reference_missing",
        "artifact_family": "editorial_plan",
        "claim_or_entity_id": "finding:42",
        "repair_attempt": 1,
        "error_context": {
            "affected_section": "editorial_plan",
            "evidence_id": "finding:42",
        },
    }


def test_failure_diagnostic_projects_structured_reference_and_cover_terminal_causes(
    tmp_path: Path,
) -> None:
    """Each non-validation terminal family keeps its actionable retained identifier."""

    state_db = tmp_path / "workflow.sqlite"
    with sqlite3.connect(state_db) as conn:
        conn.executescript(
            """
            CREATE TABLE remediation_records (
              report_id TEXT, run_id TEXT, error_code TEXT, failed_stage TEXT,
              diagnostics_json TEXT, updated_at_utc TEXT
            );
            """
        )
        rows = [
            (
                "contentstack",
                "workflow-1",
                "artifact_structured_output_invalid",
                "report_pipeline",
                {
                    "error_context": {
                        "artifact_family": "summary",
                        "error_class": "schema_missing_required",
                        "repair_attempt": 2,
                    }
                },
            ),
            (
                "reference",
                "workflow-1",
                "schema_reference_missing",
                "report_pipeline",
                {"error_context": {"missing_references": ["finding:42"]}},
            ),
            (
                "cover",
                "workflow-1",
                "cover_fingerprint_invalid",
                "report_pipeline",
                {"error_context": {"field": "selection_reason"}},
            ),
        ]
        conn.executemany(
            "INSERT INTO remediation_records VALUES (?, ?, ?, ?, ?, ?)",
            [(*row[:4], json.dumps(row[4]), "2026-09-19T12:00:00Z") for row in rows],
        )

    diagnostics = {
        report_id: _read_failure_diagnostic(
            state_db=state_db,
            reports_db=tmp_path / "reports.sqlite",
            report_id=report_id,
            validation_run_id="validation-1",
            root_workflow_id="workflow-1",
            outer_code=code,
        )
        for report_id, code in (
            ("contentstack", "artifact_structured_output_invalid"),
            ("reference", "schema_reference_missing"),
            ("cover", "cover_fingerprint_invalid"),
        )
    }

    assert diagnostics["contentstack"]["stage"] == "artifact_generation"
    assert diagnostics["contentstack"]["inner_error_class"] == "schema_missing_required"
    assert diagnostics["contentstack"]["artifact_family"] == "summary"
    assert diagnostics["contentstack"]["repair_attempt"] == 2
    assert diagnostics["reference"]["stage"] == "artifact_generation"
    assert diagnostics["reference"]["claim_or_entity_id"] == "finding:42"
    assert diagnostics["cover"]["stage"] == "rendering"
    assert diagnostics["cover"]["error_context"] == {"field": "selection_reason"}


def test_failure_diagnostic_scans_past_issue_free_stage_records(
    tmp_path: Path,
) -> None:
    """A generic validation_failed surfaces the retained inner validator finding.

    Regression: the terminal `analysis_complete` stage record is the newest
    failing record but points at the analysis vector store, which carries no
    validation-issues document. The reader must keep scanning the older
    failing validation stages instead of returning no diagnostic at all.
    """

    validation_path = tmp_path / "validation.json"
    validation_path.write_text(
        json.dumps(
            {
                "status": "fail",
                "issues": [
                    {
                        "severity": "info",
                        "rule_id": "family_confidence",
                        "affected_section": "evidence_pack:limitations",
                        "entity_id": "",
                        "evidence_ids": [],
                        "message": "informational abstention",
                    },
                    {
                        "severity": "error",
                        "rule_id": "claim_support",
                        "affected_section": "summary.claim_evidence_map[0]",
                        "entity_id": "strategy",
                        "evidence_ids": [],
                        "message": "source prose that must never be exported",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    checkpoint_path = tmp_path / "analysis_vector_store.json"
    checkpoint_path.write_text(json.dumps({"vectors": []}), encoding="utf-8")
    reports_db = tmp_path / "reports.sqlite"
    with sqlite3.connect(reports_db) as conn:
        conn.executescript(
            """
            CREATE TABLE validation_run_entity_attempts (
              attempt_id TEXT, validation_run_id TEXT, report_id TEXT,
              attempt_number INTEGER
            );
            CREATE TABLE validation_run_stage_records (
              attempt_id TEXT, stage TEXT, failure_code TEXT,
              repair_disposition TEXT, output_artifact_ids_json TEXT,
              completed_at_utc TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO validation_run_entity_attempts VALUES (?, ?, ?, ?)",
            ("attempt-1", "validation-1", "report-1", 1),
        )
        rows = [
            (
                "attempt-1",
                "analysis_complete",
                "validation_failed",
                "not_required",
                json.dumps([str(checkpoint_path)]),
                "2026-09-20T00:16:11.959102+00:00",
            ),
            (
                "attempt-1",
                "regeneration",
                "validation_failed",
                "targeted_repair",
                json.dumps([str(tmp_path / "artifacts.json")]),
                "2026-09-20T00:16:11.901010+00:00",
            ),
            (
                "attempt-1",
                "semantic_validation",
                "validation_failed",
                "targeted_repair",
                json.dumps([str(validation_path)]),
                "2026-09-20T00:16:11.889746+00:00",
            ),
        ]
        conn.executemany(
            "INSERT INTO validation_run_stage_records VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )

    diagnostic = _read_failure_diagnostic(
        state_db=tmp_path / "workflow.sqlite",
        reports_db=reports_db,
        report_id="report-1",
        validation_run_id="validation-1",
        root_workflow_id="workflow-1",
        outer_code="validation_failed",
    )

    assert diagnostic == {
        "stage": "semantic_validation",
        "outer_code": "validation_failed",
        "inner_error_class": "",
        "validator_rule": "claim_support",
        "artifact_family": "summary.claim_evidence_map[0]",
        "claim_or_entity_id": "strategy",
        "repair_attempt": 1,
        "error_context": {
            "affected_section": "summary.claim_evidence_map[0]",
        },
    }
    assert "prose" not in json.dumps(diagnostic)
