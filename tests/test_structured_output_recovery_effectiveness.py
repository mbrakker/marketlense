"""Behavioral coverage for the retained structured-output recovery view."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _event(event: str, fields: dict, *, run_id: str = "run-1") -> str:
    return json.dumps(
        {
            "run_id": run_id,
            "task_id": "task-1",
            "span_id": "span-1",
            "event": event,
            "fields": fields,
        }
    )


def test_effectiveness_report_groups_current_and_legacy_outcomes(
    tmp_path: Path,
) -> None:
    """The view computes output-level outcomes rather than counting attempt events."""

    log_path = tmp_path / "recovery.log"
    output_path = tmp_path / "report.json"
    entries = [
        _event(
            "structured_output_attempt",
            {
                "artifact_family": "doc_map",
                "attempt": 0,
                "final_disposition": "generated",
                "input_tokens": 10,
                "output_tokens": 4,
                "cost_usd": 0.001,
            },
            run_id="legacy-run",
        ),
        _event(
            "structured_output_recovery_outcome",
            {
                "outcome_id": "current-model-repair",
                "workflow": "report_analysis",
                "artifact_family": "taxonomy",
                "schema_name": "taxonomy",
                "provider": "openai",
                "model": "gpt-5-mini",
                "provider_model": "openai:gpt-5-mini",
                "failure_reason": "invalid_json",
                "repair_strategy": "model_repair",
                "provider_attempts": 2,
                "repair_input_tokens": 8,
                "repair_output_tokens": 3,
                "repair_cost_usd": 0.002,
                "elapsed_repair_ms": 12.5,
                "terminal": "success",
            },
        ),
        _event(
            "structured_output_recovery_outcome",
            {
                "outcome_id": "current-first-pass",
                "workflow": "report_analysis",
                "artifact_family": "taxonomy",
                "schema_name": "taxonomy",
                "provider": "openai",
                "model": "gpt-5-mini",
                "provider_model": "openai:gpt-5-mini",
                "failure_reason": "",
                "repair_strategy": "first_pass",
                "provider_attempts": 1,
                "repair_input_tokens": 0,
                "repair_output_tokens": 0,
                "repair_cost_usd": 0,
                "elapsed_repair_ms": 0,
                "terminal": "success",
            },
            run_id="run-2",
        ),
    ]
    log_path.write_text("\n".join(entries), encoding="utf-8")

    command = [
        sys.executable,
        "scripts/quality/structured_output_recovery_effectiveness.py",
        "--log",
        str(log_path),
        "--output",
        str(output_path),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["metrics"] == {
        "output_count": 3,
        "first_pass_valid_rate": 2 / 3,
        "deterministic_repair_success_rate": 0.0,
        "model_repair_success_rate": 1.0,
        "terminal_failure_rate": 0.0,
        "repair_attempts_per_output": 1 / 3,
        "repair_input_tokens": 8,
        "repair_output_tokens": 3,
        "repair_estimated_cost_usd": 0.002,
        "elapsed_repair_ms": 12.5,
    }
    model_group = next(
        group
        for group in report["groups"]
        if group["repair_strategy"] == "model_repair"
    )
    assert model_group["workflow"] == "report_analysis"
    assert model_group["prompt_model_family"] == "taxonomy"
    assert model_group["failure_reason"] == "invalid_json"
    assert report["availability"]["legacy_attribution"] == "partial"
    assert report["availability"]["elapsed_repair_ms"] == "partial"
