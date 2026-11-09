from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path

from scripts.quality.export_reliability_run_evidence import export_run_evidence


def _create_export_state(state_dir: Path, run_id: str, report_ids: list[str]) -> None:
    with sqlite3.connect(state_dir / "reports.sqlite") as conn:
        conn.executescript(
            """
            CREATE TABLE validation_run_cohort_members (
              validation_run_id TEXT, report_id TEXT, publisher_id TEXT,
              source_identity_id TEXT
            );
            CREATE TABLE validation_run_entity_attempts (
              validation_run_id TEXT, report_id TEXT, terminal_outcome TEXT,
              terminal_stage TEXT, failure_code TEXT, is_current INTEGER
            );
            CREATE TABLE validation_run_stage_records (
              validation_run_id TEXT, stage TEXT, terminal_outcome TEXT,
              failure_code TEXT, retryable INTEGER, repair_disposition TEXT,
              idempotency_state TEXT, started_at_utc TEXT, completed_at_utc TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO validation_run_cohort_members VALUES (?, ?, ?, ?)",
            [
                (run_id, report_id, f"publisher-{index}", f"source-{index}")
                for index, report_id in enumerate(report_ids, start=1)
            ],
        )


def test_export_run_evidence_uses_authoritative_frozen_member_outcomes(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "state"
    artifact_dir = tmp_path / "out"
    output_dir = tmp_path / "evidence"
    state_dir.mkdir()
    artifact_dir.mkdir()
    run_id = "validation:frozen-member"
    cohort_result = tmp_path / "cohort_result.json"
    cohort_result.write_text(
        json.dumps(
            {
                "cohort_size": 2,
                "reports": [
                    {
                        "report_id": "activate",
                        "final_state": "failed",
                        "terminal_failure_code": (
                            "artifact_final_insight_coverage_invalid"
                        ),
                        "publication_readiness": "fail",
                        "failure_diagnostic": {
                            "stage": "initial_selection",
                            "outer_code": "artifact_final_insight_coverage_invalid",
                        },
                    },
                    {
                        "report_id": "adjust",
                        "final_state": "awaiting_review",
                        "terminal_failure_code": "",
                        "publication_readiness": "pass",
                    },
                ],
                "summary": {
                    "failure_code_pareto": {
                        "artifact_final_insight_coverage_invalid": 1
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    _create_export_state(state_dir, run_id, ["activate", "adjust"])
    with sqlite3.connect(state_dir / "reports.sqlite") as conn:
        conn.executemany(
            "INSERT INTO validation_run_entity_attempts VALUES (?, ?, ?, ?, ?, ?)",
            [
                (run_id, "activate", "missing", "", "", 1),
                (run_id, "adjust", "failed", "validation", "validation_failed", 1),
            ],
        )

    export_run_evidence(
        state_dir=state_dir,
        artifact_dir=artifact_dir,
        output_dir=output_dir,
        validation_run_id=run_id,
        authoritative_cohort_result_path=cohort_result,
    )

    with output_dir.joinpath("terminal_outcomes.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert list(csv.DictReader(handle)) == [
            {
                "report_id": "activate",
                "terminal_outcome": "failed",
                "terminal_stage": "initial_selection",
                "failure_code": "artifact_final_insight_coverage_invalid",
            },
            {
                "report_id": "adjust",
                "terminal_outcome": "awaiting_review",
                "terminal_stage": "",
                "failure_code": "",
            },
        ]
    details = json.loads(output_dir.joinpath("failure_details.json").read_text())
    assert details["terminal_failures"] == [
        {
            "report_id": "activate",
            "terminal_outcome": "failed",
            "terminal_stage": "initial_selection",
            "failure_code": "artifact_final_insight_coverage_invalid",
            "stage": "initial_selection",
            "outer_code": "artifact_final_insight_coverage_invalid",
            "inner_error_class": "",
            "validator_rule": "",
            "artifact_family": "",
            "claim_or_entity_id": "",
            "repair_attempt": 0,
            "error_context": {},
        }
    ]
    manifest = json.loads(output_dir.joinpath("artifact_manifest.json").read_text())
    entries = {entry["relative_path"]: entry for entry in manifest["entries"]}
    terminal_path = output_dir / "terminal_outcomes.csv"
    assert (
        entries["terminal_outcomes.csv"]["sha256"]
        == hashlib.sha256(terminal_path.read_bytes()).hexdigest()
    )
    assert "artifact_manifest.json" not in entries


def test_export_run_evidence_retains_bounded_candidate_audit_lineage(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "state"
    artifact_dir = tmp_path / "out"
    output_dir = tmp_path / "evidence"
    state_dir.mkdir()
    artifact_dir.mkdir()
    run_id = "validation:candidate-audit"
    audit = {
        "attempt_index": 1,
        "before_sha256": "a" * 64,
        "after_sha256": "b" * 64,
        "validation_status": "pass",
        "promotion_outcome": "promoted",
        "repair_action": "REGENERATE_ITEM",
        "repair_strategy": "current_evidence",
        "allowed_paths": ["insights_final[item=claim-1].so_what"],
        "selected_evidence_ids": ["verified-fact:claim-1"],
        "validation_issues": ["family_confidence:quotes"],
        "evidence_lineage": [
            {
                "entity_kind": "insights_final",
                "entity_id": "claim-1",
                "original_evidence_ids": ["verified-fact:claim-1"],
                "candidate_evidence_ids": ["verified-fact:claim-1"],
                "original_source_pages": [4],
                "candidate_source_pages": [4],
                "text": "PRIVATE_SOURCE_PROSE",
            }
        ],
        "repair_delta": {
            "candidate_sha256": "c" * 64,
            "input_sha256": "a" * 64,
            "mutation_scope_result": "pass",
            "evidence_lineage_result": "pass",
            "semantic_grounding_validation_status": "evaluated",
            "evidence_ids_used": ["verified-fact:claim-1"],
            "resolved": ["PRIVATE_REPAIR_PROSE"],
        },
        "current_artifacts_path": "PRIVATE_CURRENT_PATH",
        "candidate_artifacts_path": "PRIVATE_CANDIDATE_PATH",
    }
    (artifact_dir / "regeneration_candidate_audit_1.json").write_text(
        json.dumps(audit), encoding="utf-8"
    )
    _create_export_state(state_dir, run_id, ["r1"])

    export_run_evidence(
        state_dir=state_dir,
        artifact_dir=artifact_dir,
        output_dir=output_dir,
        validation_run_id=run_id,
    )

    projection = json.loads(
        output_dir.joinpath("repair_effectiveness.json").read_text()
    )
    retained = projection["candidate_audit_attempts"][0]
    assert retained["before_sha256"] == "a" * 64
    assert retained["after_sha256"] == "b" * 64
    assert retained["repair_delta"]["candidate_sha256"] == "c" * 64
    assert retained["evidence_lineage"][0]["candidate_source_pages"] == [4]
    assert "PRIVATE_SOURCE_PROSE" not in json.dumps(projection)
    assert "PRIVATE_REPAIR_PROSE" not in json.dumps(projection)
    assert "PRIVATE_CURRENT_PATH" not in json.dumps(projection)
