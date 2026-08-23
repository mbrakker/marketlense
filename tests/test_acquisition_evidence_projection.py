from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _record(
    *,
    candidate_id: str,
    verified: bool,
    route: str,
    terminal_reason: str,
    agent_calls: int,
    blocked_reason: str = "",
) -> dict[str, object]:
    return {
        "failure_candidate_id": candidate_id,
        "publisher_id": "publisher:example",
        "canonical_candidate_url": "https://private.example/report",
        "producer_git_sha": "commit-example",
        "configuration_hash": "configuration-example",
        "duration_seconds": 12.5,
        "acquisition_result": {
            "route_family": route,
            "route_kind": "pdf_download",
            "outcome": "downloaded" if verified else "email_required",
            "blocked_reason": blocked_reason,
        },
        "artifact_verification": {
            "verified_usable_artifact": verified,
            "source_kind": "publisher_pdf" if verified else "unknown",
            "retained_artifact_format": "pdf" if verified else "none",
            "drive_persisted": verified,
        },
        "resource_attempts": [
            {
                "route_family": route,
                "terminal_reason": terminal_reason,
                "browser_launches": 1,
                "browser_model_calls": agent_calls,
                "input_tokens": 100,
                "cached_input_tokens": 20,
                "output_tokens": 10,
                "estimated_cost_usd": 0.0125,
                "mailbox_reads": 0,
            }
        ],
    }


def test_projection_builder_writes_sanitized_consistent_evidence_views(
    tmp_path: Path,
) -> None:
    current_path = tmp_path / "current.jsonl"
    baseline_path = tmp_path / "baseline.json"
    output_dir = tmp_path / "projection"
    current_records = [
        _record(
            candidate_id="fac_success",
            verified=True,
            route="direct_pdf_probe",
            terminal_reason="verified",
            agent_calls=0,
        ),
        _record(
            candidate_id="fac_failure",
            verified=False,
            route="browser_listing_hub",
            terminal_reason="blocked_no_progress",
            agent_calls=2,
        ),
        _record(
            candidate_id="fac_static_archive",
            verified=False,
            route="browser_preflight_terminal_static_archive",
            terminal_reason="observed",
            agent_calls=0,
            blocked_reason="blocked_static_archive",
        ),
    ]
    baseline_records = [
        _record(
            candidate_id="fac_success",
            verified=False,
            route="browser_pdf_click",
            terminal_reason="browser_download_agent_timeout",
            agent_calls=3,
        ),
        _record(
            candidate_id="fac_failure",
            verified=False,
            route="browser_listing_hub",
            terminal_reason="blocked_no_progress",
            agent_calls=4,
        ),
        _record(
            candidate_id="fac_static_archive",
            verified=False,
            route="browser_preflight_terminal_static_archive",
            terminal_reason="observed",
            agent_calls=0,
            blocked_reason="blocked_static_archive",
        ),
    ]
    current_path.write_text(
        "".join(json.dumps(record) + "\n" for record in current_records),
        encoding="utf-8",
    )
    baseline_path.write_text(
        json.dumps({"records": baseline_records}), encoding="utf-8"
    )
    current_sha256 = hashlib.sha256(current_path.read_bytes()).hexdigest()

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/quality/acquisition_evidence_projection.py",
            "--current-jsonl",
            str(current_path),
            "--baseline-json",
            str(baseline_path),
            "--output-dir",
            str(output_dir),
            "--expected-current-sha256",
            current_sha256,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    projection = json.loads(
        (output_dir / "acquisition_evidence_projection.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["candidate_id"] for item in projection["attempts"]] == [
        "fac_failure",
        "fac_static_archive",
        "fac_success",
    ]
    assert projection["attempts"][0]["tokens"] == {
        "input": 100,
        "cached_input": 20,
        "output": 10,
    }
    assert projection["failure_pareto"] == [
        {
            "agent_calls": 2,
            "browser_launches": 1,
            "candidate_count": 1,
            "cost_usd": 0.0125,
            "duration_seconds": 12.5,
            "terminal_reason": "blocked_no_progress",
        },
        {
            "agent_calls": 0,
            "browser_launches": 1,
            "candidate_count": 1,
            "cost_usd": 0.0125,
            "duration_seconds": 12.5,
            "terminal_reason": "blocked_static_archive",
        }
    ]
    assert projection["before_after"]["current"]["verified_acquisitions"] == 1
    assert projection["before_after"]["baseline"]["agent_calls"] == 7
    assert projection["remaining_failures"][0]["candidate_id"] == "fac_failure"
    static_archive = next(
        item
        for item in projection["attempts"]
        if item["candidate_id"] == "fac_static_archive"
    )
    assert static_archive["failure_class"] == "external_source_unavailable"
    assert static_archive["terminal_reason"] == "blocked_static_archive"
    assert projection["consistency"]["candidate_sets_match"] is True
    assert projection["consistency"]["expected_current_hash_matches"] is True
    assert "private.example" not in json.dumps(projection)

    hash_mismatch = subprocess.run(
        [
            sys.executable,
            "scripts/quality/acquisition_evidence_projection.py",
            "--current-jsonl",
            str(current_path),
            "--baseline-json",
            str(baseline_path),
            "--output-dir",
            str(tmp_path / "hash-mismatch"),
            "--expected-current-sha256",
            "not-the-current-hash",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert hash_mismatch.returncode != 0
    assert "does not match the expected hash" in hash_mismatch.stderr
