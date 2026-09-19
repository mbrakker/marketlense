from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from scripts.quality.ias_live_canary_runner import (
    _read_failure_diagnostic,
    run_first_attempt_canary,
    summarize_frozen_cohort_results,
)
from scripts.quality.run_frozen_reliability_cohort import (
    _load_members,
    run_frozen_reliability_cohort,
)
from tests.test_validation_queue_lineage import (
    _full_chain_chat_response_factory,
    _full_chain_response_factory,
)


def test_cohort_member_missing_source_has_typed_terminal_result(tmp_path: Path) -> None:
    result = run_first_attempt_canary(
        runs_root=tmp_path,
        source_path=tmp_path / "missing.pdf",
        max_duration_seconds=1,
    )

    assert result["final_state"] == "failed"
    assert result["workflow_attempt_count"] == 0
    assert result["terminal_failure_code"] == "frozen_cohort_source_missing"
    assert Path(result["run_directory"]).joinpath("result.json").is_file()


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
            [
                (*row[:4], json.dumps(row[4]), "2026-09-19T12:00:00Z")
                for row in rows
            ],
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


def test_first_attempt_canary_uses_production_submission_and_supervisor_path(
    tmp_path: Path,
    external_boundary_mocks_only,
    fake_openai,
) -> None:
    """The canary reaches a terminal result through durable production queues."""

    external_boundary_mocks_only.setenv("OPENAI_API_KEY", "test-openai-key")
    fake_openai.add("vector_stores.create", {"id": "vs_canary_test"})
    fake_openai.add("files.create", {"id": "file_canary_test"})
    fake_openai.add("vector_stores.files.create", {"id": "file_canary_test"})
    fake_openai.add("vector_stores.retrieve", {"status": "completed"})
    fake_openai.add("vector_stores.update", {"id": "vs_canary_test"})
    generated_soft_copy_payloads: list[dict[str, object]] = []
    detected_unsupported_claims: list[str] = []
    fake_openai.add(
        "responses.create",
        _full_chain_response_factory(
            repair_soft_copy=False,
            reproduce_ias_soft_copy=False,
            detected_unsupported_claims=detected_unsupported_claims,
        ),
    )
    fake_openai.add(
        "chat.completions.create",
        _full_chain_chat_response_factory(
            repair_soft_copy=False,
            reproduce_ias_soft_copy=False,
            generated_soft_copy_payloads=generated_soft_copy_payloads,
            detected_unsupported_claims=detected_unsupported_claims,
        ),
    )
    source_path = Path(
        "tests/fixtures/pdf_benchmark/golden/IAS - Industry_Pulse_Report_2026_ACIG.pdf"
    ).resolve()

    result = run_first_attempt_canary(
        runs_root=tmp_path,
        source_path=source_path,
        source_metadata={
            "source_domain": "publisher.example",
            "report_name": "Industry Pulse Report 2026",
            "landing_page_url": "https://publisher.example/reports/industry-pulse-2026",
            "source_page_url": "https://publisher.example/reports",
            "publisher_name": "Industry Analytics Summit",
            "downloaded_at_utc": "2026-08-10T12:00:00Z",
        },
        max_duration_seconds=60,
    )

    assert result["admission_outcome"] == "admitted"
    assert result["workflow_root_id"]
    assert result["final_state"] in {"awaiting_review", "failed"}
    assert Path(result["run_directory"]).joinpath("cohort", "source.json").is_file()
    with sqlite3.connect(
        Path(result["run_directory"]) / "state" / "workflow.sqlite"
    ) as conn:
        jobs = conn.execute(
            """
            SELECT queue_name, status
            FROM workflow_jobs
            WHERE root_workflow_id=?
            ORDER BY created_at_utc, queue_name
            """,
            (result["workflow_root_id"],),
        ).fetchall()
        workers = conn.execute(
            """
            SELECT DISTINCT attempts.worker_id
            FROM workflow_job_attempts AS attempts
            JOIN workflow_jobs AS jobs ON jobs.job_id=attempts.job_id
            WHERE jobs.root_workflow_id=?
            """,
            (result["workflow_root_id"],),
        ).fetchall()

    assert jobs
    assert jobs[0][0] == "source_ingest"
    assert {queue_name for queue_name, _ in jobs} >= {
        "source_ingest",
        "report_selection",
    }
    assert workers
    assert all(
        str(worker_id).startswith(f"ias-live-canary:{result['workflow_root_id']}:")
        for (worker_id,) in workers
    )
    reports_db = Path(result["run_directory"]) / "state" / "reports.sqlite"
    with sqlite3.connect(reports_db) as conn:
        manifest_root = conn.execute(
            "SELECT workflow_run_id FROM validation_runs"
        ).fetchone()
        manifest_stages = {
            stage
            for (stage,) in conn.execute(
                "SELECT DISTINCT stage FROM validation_run_stage_records"
            )
        }

    assert manifest_root == (result["workflow_root_id"],)
    assert manifest_stages >= {
        "admission_preflight",
        "candidate_qualification",
        "source_preparation",
    }


def test_frozen_manifest_requires_pinned_source_provenance(tmp_path: Path) -> None:
    manifest = tmp_path / "cohort.json"
    manifest.write_text(json.dumps({"members": [{"source_path": "missing.pdf"}]}))

    try:
        _load_members(manifest)
    except ValueError as exc:
        assert "exactly 20 members" in str(exc)
    else:
        raise AssertionError("incomplete frozen manifest was accepted")


def test_frozen_manifest_rejects_missing_provenance_before_file_access(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "cohort.json"
    manifest.write_text(json.dumps({"members": [{"source_path": "missing.pdf"}] * 20}))

    try:
        _load_members(manifest)
    except ValueError as exc:
        assert "incomplete source provenance" in str(exc)
    else:
        raise AssertionError("missing provenance was accepted")


def test_frozen_cohort_submits_all_members_through_one_production_run(
    tmp_path: Path,
) -> None:
    members = []
    for index in range(20):
        source_path = tmp_path / f"source-{index}.pdf"
        content = f"frozen-cohort-fixture-{index}".encode("utf-8")
        source_path.write_bytes(content)
        members.append(
            {
                "source_path": str(source_path.resolve()),
                "content_md5": hashlib.md5(content, usedforsecurity=False).hexdigest(),
                "source_domain": "publisher.example",
                "report_name": f"Frozen fixture {index}",
                "landing_page_url": f"https://publisher.example/reports/{index}",
                "source_page_url": "https://publisher.example/reports",
                "publisher_name": "Fixture Publisher",
                "downloaded_at_utc": "2026-09-01T00:00:00Z",
            }
        )
    manifest = tmp_path / "cohort.json"
    manifest.write_text(json.dumps({"members": members}), encoding="utf-8")
    captured: list[dict[str, object]] = []

    def run_once(**kwargs):
        captured.append(kwargs)
        return {
            "git_sha": "a" * 40,
            "run_directory": str(tmp_path / "single-production-run"),
            "reports": [
                {
                    "report_id": f"report-{index}",
                    "admission_outcome": "admitted",
                    "final_state": "failed",
                    "terminal_failure_code": "typed_failure",
                }
                for index in range(20)
            ],
        }

    result = run_frozen_reliability_cohort(
        sources_manifest=manifest,
        runs_root=tmp_path,
        run_cohort_once=run_once,
    )

    assert len(captured) == 1
    assert len(captured[0]["sources"]) == 20
    assert result["cohort_size"] == 20
    assert len(result["reports"]) == 20
    assert result["git_sha"] == "a" * 40
    retained = json.loads(
        Path(result["cohort_directory"])
        .joinpath("cohort_result.json")
        .read_text(encoding="utf-8")
    )
    assert retained["git_sha"] == "a" * 40


def test_cohort_summary_retains_batch_metrics_only_at_cohort_scope() -> None:
    summary = summarize_frozen_cohort_results(
        [
            {
                "report_id": "report-1",
                "admission_outcome": "admitted",
                "final_state": "failed",
                "terminal_failure_code": "typed_failure",
                "cost": None,
                "total_duration_seconds": None,
                "bounded_automatic_repair": None,
            }
        ],
        cohort_metrics={
            "cost_usd": 1.25,
            "duration_seconds": 90.0,
            "bounded_automatic_repair": True,
        },
    )

    assert summary["cohort_cost_usd"] == 1.25
    assert summary["cohort_duration_seconds"] == 90.0
    assert summary["cohort_bounded_automatic_repair"] is True
    assert summary["mean_cost"] == "unavailable"
    assert summary["mean_duration_seconds"] == "unavailable"
    assert summary["bounded_repair_rate"] == "unavailable"


def test_cohort_summary_keeps_failed_admitted_reports_in_its_denominator() -> None:
    summary = summarize_frozen_cohort_results(
        [
            {
                "admission_outcome": "admitted",
                "awaiting_review": True,
                "bounded_automatic_repair": False,
                "publication_readiness": "pass",
                "operator_intervention": False,
                "final_state": "awaiting_review",
                "terminal_failure_code": "",
                "cost": 0.30,
                "total_duration_seconds": 30.0,
            },
            {
                "admission_outcome": "admitted",
                "awaiting_review": False,
                "bounded_automatic_repair": True,
                "publication_readiness": "fail",
                "operator_intervention": False,
                "final_state": "failed",
                "terminal_failure_code": "publish_readiness_failed",
                "cost": 0.10,
                "total_duration_seconds": 10.0,
            },
            {
                "admission_outcome": "insufficient_content",
                "awaiting_review": True,
                "bounded_automatic_repair": False,
                "publication_readiness": "pass",
                "operator_intervention": True,
                "final_state": "awaiting_review",
                "terminal_failure_code": "",
                "cost": 0.20,
                "total_duration_seconds": 20.0,
            },
        ]
    )

    assert summary == {
        "report_count": 3,
        "terminal_outcome_complete": True,
        "missing_terminal_report_count": 0,
        "missing_terminal_report_ids": [],
        "admitted_report_count": 2,
        "cohort_admission_rate": 2 / 3,
        "workflow_denominator": 2,
        "first_attempt_awaiting_review_rate": 1 / 2,
        "publication_readiness_rate": 1 / 2,
        "bounded_repair_rate": 1 / 2,
        "workflow_failure_rate": 1 / 2,
        "typed_terminal_rate": 1.0,
        "operator_intervention_count": 1,
        "failure_code_pareto": {"publish_readiness_failed": 1},
        "mean_cost": 0.2,
        "median_cost": 0.2,
        "mean_duration_seconds": 20.0,
        "median_duration_seconds": 20.0,
    }


def test_cohort_summary_marks_missing_terminal_outcomes_incomplete() -> None:
    summary = summarize_frozen_cohort_results(
        [
            {
                "report_id": "report-1",
                "admission_outcome": "admitted",
                "final_state": "running",
                "terminal_failure_code": "",
            }
        ]
    )

    assert summary["terminal_outcome_complete"] is False
    assert summary["missing_terminal_report_count"] == 1
    assert summary["missing_terminal_report_ids"] == ["report-1"]
