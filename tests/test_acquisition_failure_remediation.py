from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path


def _load_module():
    path = Path("scripts/quality/acquisition_failure_remediation.py")
    spec = importlib.util.spec_from_file_location(
        "acquisition_failure_remediation", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freeze_excludes_later_verified_candidate_and_retains_failed_candidate(
    tmp_path,
):
    module = _load_module()
    db_path = tmp_path / "reports.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE publisher_download_route_history (
                id INTEGER, normalized_url TEXT, route_family TEXT, route_kind TEXT,
                route_status TEXT, outcome TEXT, attempts INTEGER, blocked_reason TEXT,
                blocked_reason_detail TEXT, last_final_page_url TEXT,
                resolved_target_url TEXT, last_downloaded_file_path TEXT,
                onsite_capture_format TEXT, onsite_completeness_status TEXT,
                candidate_pdf_url TEXT, candidate_source_page_urls_json TEXT,
                candidate_discovery_provenances_json TEXT, updated_at TEXT
            );
            CREATE TABLE acquisition_attempt_resources (
                attempt_id TEXT, normalized_url TEXT, publisher_id TEXT,
                route_family TEXT, terminal_outcome TEXT, terminal_reason TEXT,
                started_at_utc TEXT, completed_at_utc TEXT, elapsed_ms INTEGER,
                browser_launches INTEGER, page_navigations INTEGER, browser_steps INTEGER,
                screenshots INTEGER, browser_model_calls INTEGER, input_tokens INTEGER,
                output_tokens INTEGER, estimated_cost_usd REAL, mailbox_reads INTEGER,
                drive_reads INTEGER, drive_writes INTEGER,
                source_policy_compatibility_hash TEXT, route_policy_version TEXT
            );
            CREATE TABLE publishers (id INTEGER, name TEXT);
            CREATE TABLE report_sources (
                id INTEGER, normalized_landing_page_url TEXT, report_name TEXT,
                source_page_url TEXT, publisher_name TEXT, discovered_at_utc TEXT
            );
            CREATE TABLE source_identity_resolutions (
                source_record_id INTEGER, source_identity_id TEXT, resolved_at_utc TEXT
            );
            """
        )
        connection.execute("INSERT INTO publishers VALUES (1, 'Example Publisher')")
        connection.execute(
            "INSERT INTO acquisition_attempt_resources VALUES "
            "('failed', 'https://example.test/failed', 'publisher:example-publisher', "
            "'browser_email_form', 'failed', 'blocked_missing_identity_field', "
            "'2026-08-14T00:00:00Z', '2026-08-14T00:00:01Z', 1000, 1, 1, 2, 0, 1, "
            "10, 2, 0.01, 0, 0, 0, 'policy-hash', 'policy-v1')"
        )
        connection.execute(
            "INSERT INTO publisher_download_route_history VALUES "
            "(1, 'https://example.test/verified', 'direct_pdf_probe', 'pdf_download', "
            "'verified', 'downloaded', 1, '', '', '', '', '', '', '', '', '[]', '[]', "
            "'2026-08-14T00:00:02Z')"
        )
        connection.execute(
            "INSERT INTO acquisition_attempt_resources VALUES "
            "('earlier-failure', 'https://example.test/verified', 'publisher:example-publisher', "
            "'browser_pdf_click', 'failed', 'browser_download_agent_timeout', "
            "'2026-08-14T00:00:00Z', '2026-08-14T00:00:01Z', 1000, 1, 1, 2, 0, 1, "
            "10, 2, 0.01, 0, 0, 0, 'policy-hash', 'policy-v1')"
        )
    result = module.freeze_failed_acquisition_manifest(
        reports_db=db_path,
        output_path=tmp_path / "manifest.json",
        producer_sha="abc123",
    )
    assert result["candidate_count"] == 1
    candidate = result["candidates"][0]
    assert candidate["canonical_candidate_url"] == "https://example.test/failed"
    assert candidate["original_typed_error_code"] == "blocked_missing_identity_field"
    assert candidate["original_resource_attempts"][0]["duration_seconds"] == 1.0
    assert result["manifest_sha256"]


def test_relative_credential_path_is_owned_by_supplied_dotenv_directory(tmp_path):
    module = _load_module()
    dotenv_path = tmp_path / ".env"
    credential_path = tmp_path / "credentials" / "token.json"
    credential_path.parent.mkdir()
    credential_path.write_text("{}", encoding="utf-8")
    resolved = module._owned_dotenv_credential_paths(
        dotenv_path,
        {"GOOGLE_OAUTH_TOKEN_JSON": "credentials/token.json"},
    )
    assert resolved == {"GOOGLE_OAUTH_TOKEN_JSON": str(credential_path)}


def test_artifact_verification_accepts_verified_browser_rendered_pdf(tmp_path):
    module = _load_module()
    rendered_pdf = tmp_path / "report-browser-rendered.pdf"
    rendered_pdf.write_bytes(b"%PDF-1.7 browser-rendered report")

    verification = module._artifact_verification(
        {
            "acquisition_result": {
                "outcome": "captured",
                "route_status": "verified",
                "route_family": "browser_onsite_report",
                "onsite_capture_path": str(rendered_pdf),
                "onsite_capture_format": "rendered_onsite_pdf",
                "drive_uploads": [{"status": "uploaded"}],
            }
        }
    )

    assert verification["source_kind"] == "rendered_onsite_pdf"
    assert verification["verified_usable_artifact"] is True
    assert verification["publisher_supplied"] is False


def test_artifact_verification_preserves_verified_browser_printed_pdf(tmp_path):
    module = _load_module()
    rendered_pdf = tmp_path / "report-browser-printed.pdf"
    rendered_pdf.write_bytes(b"%PDF-1.7 browser printed report")

    verification = module._artifact_verification(
        {
            "acquisition_result": {
                "outcome": "captured",
                "route_status": "verified",
                "route_family": "browser_onsite_report",
                "onsite_capture_path": str(rendered_pdf),
                "onsite_capture_format": "browser_rendered_pdf",
                "drive_uploads": [{"status": "uploaded"}],
            }
        }
    )

    assert verification["source_kind"] == "browser_rendered_pdf"
    assert verification["verified_usable_artifact"] is True
    assert verification["publisher_supplied"] is False


def test_isolated_attempt_supervisor_returns_typed_timeout(tmp_path):
    module = _load_module()

    result = module._run_isolated_attempt_process(
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        response_path=tmp_path / "response.json",
        timeout_seconds=0.1,
    )

    assert result["status"] == "timeout"
    assert result["error_code"] == "acquisition_attempt_supervisor_timeout"
    assert result["response"] is None


def test_supervisor_timeout_record_is_terminal_with_incomplete_telemetry():
    module = _load_module()

    record = module._supervisor_terminal_record(
        candidate={
            "failure_candidate_id": "fac_timeout",
            "canonical_candidate_url": "https://example.test/report",
            "publisher_id": "publisher:example",
            "publisher_name": "Example",
        },
        producer_sha="abc123",
        configuration_hash="config-hash",
        run_id="run-1",
        started_at="2026-08-22T00:00:00Z",
        supervisor_result={
            "status": "timeout",
            "error_code": "acquisition_attempt_supervisor_timeout",
            "duration_seconds": 360.0,
        },
    )

    assert record["acquisition_error"]["error_code"] == (
        "acquisition_attempt_supervisor_timeout"
    )
    assert record["artifact_verification"]["verified_usable_artifact"] is False
    assert record["resource_attempts"][0]["telemetry_status"] == "incomplete"
    assert record["resource_attempts"][0]["browser_launches"] is None


def test_isolated_replay_uses_only_matching_child_terminal_record():
    module = _load_module()
    candidate = {
        "failure_candidate_id": "fac_child",
        "canonical_candidate_url": "https://example.test/report",
    }
    child_record = {
        "failure_candidate_id": "fac_child",
        "artifact_verification": {"verified_usable_artifact": True},
    }

    record = module._record_from_isolated_attempt(
        candidate=candidate,
        producer_sha="abc123",
        configuration_hash="config-hash",
        run_id="run-1",
        started_at="2026-08-22T00:00:00Z",
        supervisor_result={
            "status": "completed",
            "error_code": "",
            "duration_seconds": 1.0,
            "response": {"records": [child_record]},
        },
    )

    assert record is child_record
