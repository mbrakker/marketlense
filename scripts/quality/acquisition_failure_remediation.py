"""Freeze and replay the failed-acquisition cohort from a retained run.

This tool intentionally does not discover candidates.  It derives a stable
candidate set from the retained acquisition ledgers, excluding only candidates
with a later verified route outcome.  The resulting manifest is the sole input
to any replay stage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

SCHEMA_VERSION = "1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _rows(
    connection: sqlite3.Connection, query: str, args: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    try:
        cursor = connection.execute(query, args)
    except sqlite3.OperationalError:
        return []
    columns = [item[0] for item in cursor.description or ()]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _decode_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return (
        [str(item) for item in decoded if str(item).strip()]
        if isinstance(decoded, list)
        else []
    )


def _publisher_name(connection: sqlite3.Connection, publisher_id: str, url: str) -> str:
    if publisher_id:
        suffix = publisher_id.removeprefix("publisher:")
        row = connection.execute(
            "SELECT name FROM publishers WHERE lower(replace(replace(name, ' & ', '-'), ' ', '-'))=? "
            "ORDER BY id LIMIT 1",
            (suffix,),
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    row = connection.execute(
        "SELECT publisher_name FROM report_sources "
        "WHERE normalized_landing_page_url=? AND publisher_name<>'' ORDER BY id DESC LIMIT 1",
        (url,),
    ).fetchone()
    return str(row[0]) if row and row[0] else publisher_id.removeprefix("publisher:")


def _source_metadata(connection: sqlite3.Connection, url: str) -> dict[str, Any]:
    source = connection.execute(
        "SELECT id, report_name, source_page_url, publisher_name, discovered_at_utc "
        "FROM report_sources WHERE normalized_landing_page_url=? ORDER BY id DESC LIMIT 1",
        (url,),
    ).fetchone()
    if source is None:
        return {
            "source_record_id": "",
            "candidate_title": "",
            "source_page_urls": [],
            "discovery_provenance": [],
            "discovered_at_utc": "",
        }
    source_id, title, source_page_url, _, discovered_at = source
    resolution = connection.execute(
        "SELECT source_identity_id FROM source_identity_resolutions "
        "WHERE source_record_id=? ORDER BY resolved_at_utc DESC LIMIT 1",
        (source_id,),
    ).fetchone()
    return {
        "source_record_id": str(source_id),
        "source_identity_id": str(resolution[0])
        if resolution and resolution[0]
        else "",
        "candidate_title": str(title or ""),
        "source_page_urls": [str(source_page_url)] if source_page_url else [],
        "discovery_provenance": ["retained_source_record"],
        "discovered_at_utc": str(discovered_at or ""),
    }


def freeze_failed_acquisition_manifest(
    *, reports_db: Path, output_path: Path, producer_sha: str
) -> dict[str, Any]:
    """Create a deterministic immutable manifest for all unverified candidates."""
    with sqlite3.connect(reports_db) as connection:
        connection.row_factory = sqlite3.Row
        history = _rows(
            connection,
            "SELECT * FROM publisher_download_route_history ORDER BY normalized_url, id",
        )
        resources = _rows(
            connection,
            "SELECT * FROM acquisition_attempt_resources ORDER BY normalized_url, started_at_utc, attempt_id",
        )
        history_by_url: dict[str, list[dict[str, Any]]] = defaultdict(list)
        resource_by_url: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in history:
            history_by_url[str(row.get("normalized_url") or "")].append(row)
        for row in resources:
            resource_by_url[str(row.get("normalized_url") or "")].append(row)

        candidate_urls = set(history_by_url) | set(resource_by_url)
        candidates: list[dict[str, Any]] = []
        for url in sorted(item for item in candidate_urls if item):
            route_rows = history_by_url[url]
            resource_rows = resource_by_url[url]
            has_verified_route = any(
                str(row.get("route_status") or "") == "verified"
                and str(row.get("outcome") or "") in {"downloaded", "captured"}
                for row in route_rows
            )
            if has_verified_route:
                continue
            failed_resources = [
                row
                for row in resource_rows
                if str(row.get("terminal_outcome") or "") != "success"
            ]
            failed_routes = [
                row
                for row in route_rows
                if str(row.get("route_status") or "") != "verified"
                or str(row.get("outcome") or "")
                in {"email_required", "failed", "failed_retryable", "failed_terminal"}
            ]
            if not failed_resources and not failed_routes:
                continue
            publisher_id = next(
                (
                    str(row.get("publisher_id") or "")
                    for row in resource_rows
                    if row.get("publisher_id")
                ),
                "",
            )
            metadata = _source_metadata(connection, url)
            publisher_name = metadata.get("publisher_name") or _publisher_name(
                connection, publisher_id, url
            )
            original_route_attempts = [
                {
                    "route_history_id": str(row.get("id") or ""),
                    "route_family": str(row.get("route_family") or ""),
                    "route_kind": str(row.get("route_kind") or ""),
                    "route_status": str(row.get("route_status") or ""),
                    "outcome": str(row.get("outcome") or ""),
                    "attempts": int(row.get("attempts") or 0),
                    "blocked_reason": str(row.get("blocked_reason") or ""),
                    "blocked_reason_detail": str(
                        row.get("blocked_reason_detail") or ""
                    ),
                    "terminal_url": str(
                        row.get("last_final_page_url")
                        or row.get("resolved_target_url")
                        or ""
                    ),
                    "artifact_status": {
                        "last_downloaded_file_path": str(
                            row.get("last_downloaded_file_path") or ""
                        ),
                        "onsite_capture_format": str(
                            row.get("onsite_capture_format") or ""
                        ),
                        "onsite_completeness_status": str(
                            row.get("onsite_completeness_status") or ""
                        ),
                    },
                    "candidate_pdf_url": str(row.get("candidate_pdf_url") or ""),
                    "source_page_urls": _decode_list(
                        row.get("candidate_source_page_urls_json")
                    ),
                    "discovery_provenances": _decode_list(
                        row.get("candidate_discovery_provenances_json")
                    ),
                    "updated_at": str(row.get("updated_at") or ""),
                }
                for row in route_rows
            ]
            original_resources = [
                {
                    "attempt_id": str(row.get("attempt_id") or ""),
                    "route_family": str(row.get("route_family") or ""),
                    "terminal_outcome": str(row.get("terminal_outcome") or ""),
                    "terminal_reason": str(row.get("terminal_reason") or ""),
                    "started_at": str(row.get("started_at_utc") or ""),
                    "completed_at": str(row.get("completed_at_utc") or ""),
                    "duration_seconds": round(
                        int(row.get("elapsed_ms") or 0) / 1000, 3
                    ),
                    "browser_launches": int(row.get("browser_launches") or 0),
                    "page_navigations": int(row.get("page_navigations") or 0),
                    "browser_steps": int(row.get("browser_steps") or 0),
                    "screenshots": int(row.get("screenshots") or 0),
                    "llm_calls": int(row.get("browser_model_calls") or 0),
                    "input_tokens": int(row.get("input_tokens") or 0),
                    "output_tokens": int(row.get("output_tokens") or 0),
                    "estimated_cost_usd": float(row.get("estimated_cost_usd") or 0),
                    "mailbox_reads": int(row.get("mailbox_reads") or 0),
                    "drive_reads": int(row.get("drive_reads") or 0),
                    "drive_writes": int(row.get("drive_writes") or 0),
                    "configuration_hash": str(
                        row.get("source_policy_compatibility_hash") or ""
                    ),
                    "policy_hash": str(row.get("route_policy_version") or ""),
                }
                for row in resource_rows
            ]
            terminal_resource = failed_resources[-1] if failed_resources else {}
            terminal_route = failed_routes[-1] if failed_routes else {}
            source_pages = list(metadata.get("source_page_urls") or [])
            provenance = list(metadata.get("discovery_provenance") or [])
            for row in original_route_attempts:
                source_pages.extend(row["source_page_urls"])
                provenance.extend(row["discovery_provenances"])
            candidate = {
                "failure_candidate_id": "fac_" + _sha256({"url": url})[:24],
                "source_record_id": metadata.get("source_record_id", ""),
                "source_identity_id": metadata.get("source_identity_id", ""),
                "publisher_id": publisher_id,
                "publisher_name": publisher_name,
                "canonical_candidate_url": url,
                "source_page_urls": sorted(set(item for item in source_pages if item)),
                "candidate_title": metadata.get("candidate_title", ""),
                "discovery_provenance": sorted(
                    set(item for item in provenance if item)
                ),
                "original_route_attempts": original_route_attempts,
                "original_attempt_count": sum(
                    int(row["attempts"] or 0) for row in original_route_attempts
                )
                + len(failed_resources),
                "original_terminal_outcome": str(
                    terminal_route.get("outcome")
                    or terminal_resource.get("terminal_outcome")
                    or ""
                ),
                "original_typed_error_code": str(
                    terminal_route.get("blocked_reason")
                    or terminal_resource.get("terminal_reason")
                    or ""
                ),
                "original_terminal_url": str(
                    terminal_route.get("last_final_page_url")
                    or terminal_route.get("resolved_target_url")
                    or ""
                ),
                "original_artifact_status": "unverified",
                "original_acquisition_timestamp": str(
                    terminal_resource.get("completed_at_utc")
                    or terminal_route.get("updated_at")
                    or ""
                ),
                "original_configuration_hash": str(
                    terminal_resource.get("source_policy_compatibility_hash") or ""
                ),
                "original_policy_hash": str(
                    terminal_resource.get("route_policy_version") or ""
                ),
                "original_resource_attempts": original_resources,
            }
            candidates.append(candidate)
    frozen = {
        "schema_version": SCHEMA_VERSION,
        "manifest_kind": "immutable_failed_acquisition_cohort",
        "source_reports_db": str(reports_db.resolve()),
        "source_reports_db_sha256": _file_sha256(reports_db),
        "producer_git_sha": producer_sha,
        "frozen_at_utc": _now(),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    frozen["manifest_sha256"] = _sha256(
        {key: value for key, value in frozen.items() if key != "manifest_sha256"}
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(frozen, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return frozen


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _owned_dotenv_credential_paths(
    dotenv_path: Path, values: dict[str, str | None]
) -> dict[str, str]:
    """Resolve existing relative credential paths against their dotenv owner."""
    resolved: dict[str, str] = {}
    for key in (
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "GOOGLE_OAUTH_CLIENT_JSON",
        "GOOGLE_OAUTH_TOKEN_JSON",
        "GMAIL_OAUTH_CLIENT_PATH",
        "GMAIL_OAUTH_TOKEN_PATH",
    ):
        raw_value = str(values.get(key) or "").strip()
        if not raw_value:
            continue
        candidate = Path(raw_value).expanduser()
        if candidate.is_absolute():
            continue
        owned_path = (dotenv_path.parent / candidate).resolve()
        if owned_path.exists():
            resolved[key] = str(owned_path)
    return resolved


def _load_external_dotenv_with_owned_paths(dotenv_path: Path) -> None:
    """Load a supplied dotenv file and keep relative credential paths portable.

    A run harness may intentionally live in a dedicated worktree while its
    sandbox credentials remain in the operator's primary workspace. Relative
    path values therefore belong to the dotenv file, not to the worktree.
    """
    from dotenv import dotenv_values, load_dotenv

    load_dotenv(dotenv_path)
    for key, value in _owned_dotenv_credential_paths(
        dotenv_path, dotenv_values(dotenv_path)
    ).items():
        os.environ[key] = value


def _safe_path_reference(value: str | None) -> str:
    """Keep an artifact reference without retaining user-controlled page text."""
    return str(value or "").replace("\\", "/")


def _safe_result(result: Any) -> dict[str, Any]:
    terminal = result.terminal_evidence
    confirmation = result.confirmation_evidence
    return {
        "route_family": result.route_family,
        "route_kind": result.route_kind,
        "route_status": result.route_status,
        "outcome": result.outcome,
        "blocked_reason": result.blocked_reason or "",
        "blocked_reason_detail": result.blocked_reason_detail or "",
        "final_url": result.final_page_url,
        "resolved_target_url": result.resolved_target_url,
        "used_memory_route": result.used_memory_route,
        "encountered_form_fields": list(result.encountered_form_fields),
        "route_steps": [
            {
                "index": step.index,
                "action": step.action,
                "target_role": step.target_role,
                "target_url": step.target_url,
                "result": step.result,
                "expected_evidence": list(step.expected_evidence),
                "observed_evidence": list(step.observed_evidence),
                "verification_status": step.verification_status,
            }
            for step in result.route_steps
        ],
        "confirmation": {
            "url_changed": confirmation.url_changed,
            "submit_button_state": confirmation.submit_button_state,
            "form_disappeared": confirmation.form_disappeared,
            "final_page_url": confirmation.final_page_url,
            "confirmation_score": confirmation.confirmation_score,
            "signal_labels": list(confirmation.signal_labels),
        },
        "terminal_evidence": {
            "final_page_url": terminal.final_page_url,
            "final_page_title": terminal.final_page_title,
            "artifact_url": terminal.artifact_url,
            "artifact_kind": terminal.artifact_kind,
            "artifact_validation_status": terminal.artifact_validation_status,
            "artifact_validation_detail": terminal.artifact_validation_detail,
            "confirmation_signal_count": terminal.confirmation_signal_count,
            "traversed_page_urls": list(terminal.traversed_page_urls),
            "visited_url_timeline": list(terminal.visited_url_timeline),
            "observed_document_urls": list(terminal.observed_document_urls),
            "network_events": [
                {
                    "url": event.url,
                    "initiator_type": event.initiator_type,
                    "signal_kind": event.signal_kind,
                }
                for event in terminal.network_events
            ],
            "html_snapshot_path": _safe_path_reference(terminal.html_snapshot_path),
            "screenshot_path": _safe_path_reference(terminal.screenshot_path),
            "dom_snapshot_sha256": terminal.dom_snapshot_sha256,
            "evidence_labels": list(terminal.evidence_labels),
        },
        "downloaded_file_path": _safe_path_reference(result.downloaded_file_path),
        "downloaded_mime_type": result.downloaded_mime_type or "",
        "downloaded_size_bytes": result.downloaded_size_bytes or 0,
        "onsite_capture_path": _safe_path_reference(result.onsite_capture_path),
        "onsite_capture_format": result.onsite_capture_format or "",
        "onsite_page_count": result.onsite_page_count or 0,
        "onsite_completeness_status": result.onsite_completeness_status or "",
        "drive_uploads": [
            {
                "status": upload.status,
                "file_id": upload.drive_file.file_id if upload.drive_file else "",
                "folder_id": upload.folder_id,
                "mime_type": upload.mime_type,
                "size": upload.size,
                "md5": upload.md5 or "",
            }
            for upload in result.drive_uploads
        ],
    }


def _artifact_verification(record: dict[str, Any]) -> dict[str, Any]:
    result = record.get("acquisition_result") or {}
    outcome = str(result.get("outcome") or "")
    route_status = str(result.get("route_status") or "")
    downloaded = Path(str(result.get("downloaded_file_path") or ""))
    captured = Path(str(result.get("onsite_capture_path") or ""))
    if outcome == "downloaded":
        exists = downloaded.is_file()
        prefix = downloaded.read_bytes()[:5] if exists else b""
        return {
            "source_kind": "native_pdf_report",
            "acquisition_method": str(result.get("route_family") or ""),
            "retained_artifact_format": "pdf",
            "artifact_exists": exists,
            "size_bytes": downloaded.stat().st_size if exists else 0,
            "signature_valid": prefix == b"%PDF-",
            "route_verified": route_status == "verified",
            "drive_persisted": bool(result.get("drive_uploads")),
            "verified_usable_artifact": bool(
                exists
                and prefix == b"%PDF-"
                and route_status == "verified"
                and result.get("drive_uploads")
            ),
        }
    if outcome == "captured":
        exists = captured.is_file()
        capture_format = str(result.get("onsite_capture_format") or "html")
        if capture_format in {"browser_rendered_pdf", "rendered_onsite_pdf"}:
            prefix = captured.read_bytes()[:5] if exists else b""
            return {
                "source_kind": capture_format,
                "acquisition_method": "browser_capture",
                "retained_artifact_format": "pdf",
                "artifact_exists": exists,
                "size_bytes": captured.stat().st_size if exists else 0,
                "signature_valid": prefix == b"%PDF-",
                "route_verified": route_status == "verified",
                "drive_persisted": bool(result.get("drive_uploads")),
                "publisher_supplied": False,
                "verified_usable_artifact": bool(
                    exists
                    and prefix == b"%PDF-"
                    and route_status == "verified"
                    and result.get("drive_uploads")
                ),
                "reason": (
                    "Verified complete on-site report rendered to PDF; "
                    "not a publisher-supplied PDF."
                ),
            }
        return {
            "source_kind": "onsite_report",
            "acquisition_method": "browser_capture",
            "retained_artifact_format": capture_format,
            "artifact_exists": exists,
            "size_bytes": captured.stat().st_size if exists else 0,
            "signature_valid": None,
            "route_verified": route_status == "verified",
            "drive_persisted": bool(result.get("drive_uploads")),
            "verified_usable_artifact": False,
            "reason": "onsite capture is retained separately and is never classified as a native PDF download",
        }
    return {
        "source_kind": "unknown",
        "acquisition_method": str(result.get("route_family") or ""),
        "retained_artifact_format": "none",
        "artifact_exists": False,
        "size_bytes": 0,
        "signature_valid": None,
        "route_verified": False,
        "drive_persisted": False,
        "verified_usable_artifact": False,
    }


def _resource_rows(reports_db: str | Path, url: str) -> list[dict[str, Any]]:
    reports_db = Path(reports_db)
    if not reports_db.exists():
        return []
    with sqlite3.connect(reports_db) as connection:
        rows = _rows(
            connection,
            "SELECT * FROM acquisition_attempt_resources WHERE normalized_url=? ORDER BY started_at_utc, attempt_id",
            (url,),
        )
    for row in rows:
        row["duration_seconds"] = round(int(row.get("elapsed_ms") or 0) / 1000, 3)
    return rows


def _terminate_attempt_process_tree(process_id: int) -> None:
    """Terminate only the isolated candidate worker and its descendants."""
    try:
        parent = psutil.Process(process_id)
    except psutil.Error:
        return
    processes = [*parent.children(recursive=True), parent]
    for process in processes:
        try:
            process.terminate()
        except psutil.Error:
            continue
    _, alive = psutil.wait_procs(processes, timeout=3)
    for process in alive:
        try:
            process.kill()
        except psutil.Error:
            continue
    psutil.wait_procs(alive, timeout=3)


def _run_isolated_attempt_process(
    *, command: list[str], response_path: Path, timeout_seconds: float
) -> dict[str, Any]:
    """Run one replay candidate in a disposable process with a hard deadline."""
    started_monotonic = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError as exc:
        return {
            "status": "spawn_failed",
            "error_code": "acquisition_attempt_supervisor_spawn_failed",
            "response": None,
            "return_code": None,
            "duration_seconds": round(time.monotonic() - started_monotonic, 3),
            "error_type": type(exc).__name__,
        }
    try:
        return_code = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_attempt_process_tree(process.pid)
        return {
            "status": "timeout",
            "error_code": "acquisition_attempt_supervisor_timeout",
            "response": None,
            "return_code": None,
            "duration_seconds": round(time.monotonic() - started_monotonic, 3),
        }
    if not response_path.exists():
        return {
            "status": "missing_response",
            "error_code": "acquisition_attempt_child_missing_result",
            "response": None,
            "return_code": return_code,
            "duration_seconds": round(time.monotonic() - started_monotonic, 3),
        }
    try:
        response = json.loads(response_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid_response",
            "error_code": "acquisition_attempt_child_invalid_result",
            "response": None,
            "return_code": return_code,
            "duration_seconds": round(time.monotonic() - started_monotonic, 3),
        }
    return {
        "status": "completed",
        "error_code": "",
        "response": response,
        "return_code": return_code,
        "duration_seconds": round(time.monotonic() - started_monotonic, 3),
    }


def _supervisor_terminal_record(
    *,
    candidate: dict[str, Any],
    producer_sha: str,
    configuration_hash: str,
    run_id: str,
    started_at: str,
    supervisor_result: dict[str, Any],
) -> dict[str, Any]:
    """Represent a killed or malformed child without inventing browser usage."""
    duration_seconds = float(supervisor_result.get("duration_seconds") or 0.0)
    error_code = str(
        supervisor_result.get("error_code")
        or "acquisition_attempt_supervisor_failed"
    )
    resource_attempt = {
        "attempt_id": "supervisor:" + str(candidate.get("failure_candidate_id") or ""),
        "normalized_url": str(candidate.get("canonical_candidate_url") or ""),
        "route_family": "supervisor_isolation",
        "terminal_outcome": "failed",
        "terminal_reason": error_code,
        "duration_seconds": round(duration_seconds, 3),
        "retry_count": 0,
        "telemetry_status": "incomplete",
        "browser_launches": None,
        "browser_model_calls": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "estimated_cost_usd": None,
    }
    record = {
        "failure_candidate_id": candidate.get("failure_candidate_id") or "",
        "source_record_id": candidate.get("source_record_id") or "",
        "source_identity_id": candidate.get("source_identity_id") or "",
        "publisher_id": candidate.get("publisher_id") or "",
        "publisher_name": candidate.get("publisher_name") or "",
        "canonical_candidate_url": candidate.get("canonical_candidate_url") or "",
        "run_id": run_id,
        "attempt_id": "diagnostic:" + str(candidate.get("failure_candidate_id") or ""),
        "parent_attempt": "",
        "producer_git_sha": producer_sha,
        "configuration_hash": configuration_hash,
        "policy_hash": "current_head_default_policy",
        "phase": "diagnostic_before_fixes",
        "started_at": started_at,
        "completed_at": _now(),
        "duration_seconds": round(duration_seconds, 3),
        "acquisition_error": {
            "error_code": error_code,
            "retryable": True,
            "severity": "error",
        },
        "resource_attempts": [resource_attempt],
    }
    record["artifact_verification"] = _artifact_verification(record)
    return record


def _record_from_isolated_attempt(
    *,
    candidate: dict[str, Any],
    producer_sha: str,
    configuration_hash: str,
    run_id: str,
    started_at: str,
    supervisor_result: dict[str, Any],
) -> dict[str, Any]:
    """Accept exactly one matching child record or synthesize a terminal failure."""
    response = supervisor_result.get("response")
    records = response.get("records") if isinstance(response, dict) else None
    if (
        supervisor_result.get("status") == "completed"
        and isinstance(records, list)
        and len(records) == 1
        and isinstance(records[0], dict)
        and records[0].get("failure_candidate_id")
        == candidate.get("failure_candidate_id")
    ):
        return records[0]
    result = dict(supervisor_result)
    if not str(result.get("error_code") or "").strip():
        result["error_code"] = "acquisition_attempt_child_invalid_result"
    return _supervisor_terminal_record(
        candidate=candidate,
        producer_sha=producer_sha,
        configuration_hash=configuration_hash,
        run_id=run_id,
        started_at=started_at,
        supervisor_result=result,
    )


def _replay_failed_acquisition_manifest_direct(
    *,
    manifest_path: Path,
    config_path: Path,
    dotenv_path: Path,
    output_dir: Path,
    producer_sha: str,
    candidate_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Replay exactly the frozen candidates through the existing acquisition boundaries."""
    workspace_root = str(Path(__file__).resolve().parents[2])
    if workspace_root not in sys.path:
        sys.path.insert(0, workspace_root)
    _load_external_dotenv_with_owned_paths(dotenv_path)
    os.environ["MARKET_LENSE_CONFIG_PATH"] = str(config_path.resolve())
    os.environ["MARKET_LENSE_PRODUCER_COMMIT"] = producer_sha
    from src.contracts.browser_download import ReportDownloadOrchestratorRequest
    from src.contracts.config import ConfigLoadRequest
    from src.contracts.mailbox_acquisition import MailReportAcquisitionRequest
    from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
    from src.orchestrators.mail_report_acquisition_orchestrator import (
        run_mail_report_acquisition,
    )
    from src.orchestrators.report_download_orchestrator import run_report_download
    from src.services.config_service import (
        load_browser_download_settings,
        load_mailbox_acquisition_settings,
    )
    from src.utils.errors import AppError
    from src.utils.logging import child_context, new_run_context

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    supplied_hash = str(manifest.get("manifest_sha256") or "")
    calculated_hash = _sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    if not supplied_hash or supplied_hash != calculated_hash:
        raise RuntimeError(
            "Failed acquisition manifest hash does not match its frozen contents"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    settings_request = ConfigLoadRequest(
        schema_version="1.0", path=str(config_path.resolve())
    )
    root_context = new_run_context(
        task_id="acquisition_failure_remediation_diagnostic",
        producer_commit_sha=producer_sha,
    )
    browser_settings = load_browser_download_settings(settings_request, root_context)
    mailbox_settings = load_mailbox_acquisition_settings(settings_request, root_context)
    config_hash = _sha256(
        {
            "config_sha256": _file_sha256(config_path),
            "identity_config_sha256": _file_sha256(
                Path(browser_settings.identity_config_path)
            ),
            "mailbox_provider": mailbox_settings.provider,
            "mailbox_poll_timeout_seconds": mailbox_settings.poll_timeout_seconds,
            "mailbox_poll_interval_seconds": mailbox_settings.poll_interval_seconds,
        }
    )
    records: list[dict[str, Any]] = []
    jsonl_path = output_dir / "acquisition_attempts.jsonl"
    selected_candidates = [
        candidate
        for candidate in manifest["candidates"]
        if candidate_ids is None or candidate["failure_candidate_id"] in candidate_ids
    ]
    for ordinal, candidate in enumerate(selected_candidates, start=1):
        started_at = _now()
        started_monotonic = time.monotonic()
        context = child_context(
            root_context,
            task_id=f"remediation_{ordinal}_{candidate['failure_candidate_id']}",
        )
        trace = PublisherInventoryCandidateTrace(
            schema_version="1.0",
            canonical_url=candidate["canonical_candidate_url"],
            title=candidate.get("candidate_title")
            or candidate["canonical_candidate_url"],
            discovered_on_page_number=1,
            source_page_urls=list(candidate.get("source_page_urls") or []),
            discovery_provenances=list(candidate.get("discovery_provenance") or []),
        )
        record: dict[str, Any] = {
            "failure_candidate_id": candidate["failure_candidate_id"],
            "source_record_id": candidate.get("source_record_id") or "",
            "source_identity_id": candidate.get("source_identity_id") or "",
            "publisher_id": candidate.get("publisher_id") or "",
            "publisher_name": candidate.get("publisher_name") or "",
            "canonical_candidate_url": candidate["canonical_candidate_url"],
            "run_id": context.run_id,
            "attempt_id": "diagnostic:" + candidate["failure_candidate_id"],
            "parent_attempt": "",
            "producer_git_sha": producer_sha,
            "configuration_hash": config_hash,
            "policy_hash": "current_head_default_policy",
            "phase": "diagnostic_before_fixes",
            "started_at": started_at,
        }
        try:
            result = run_report_download(
                ReportDownloadOrchestratorRequest(
                    schema_version="1.0",
                    url=candidate["canonical_candidate_url"],
                    settings=browser_settings,
                    state_db=browser_settings.state_db,
                    reports_db=browser_settings.reports_db,
                    candidate_trace=trace,
                    publisher_insights_url=(
                        trace.source_page_urls[0] if trace.source_page_urls else None
                    ),
                    report_title=trace.title,
                    publisher_id=candidate.get("publisher_id") or "",
                    publisher_name=candidate.get("publisher_name") or "",
                    mailbox_settings=mailbox_settings,
                ),
                ctx=context,
            )
            record["acquisition_result"] = _safe_result(result)
            if result.outcome == "email_requested":
                mail_context = child_context(
                    context,
                    task_id=f"mail_{ordinal}_{candidate['failure_candidate_id']}",
                )
                try:
                    mail_result = run_mail_report_acquisition(
                        MailReportAcquisitionRequest(
                            schema_version="1.0",
                            source_url=candidate["canonical_candidate_url"],
                            report_title=trace.title,
                            publisher_name=candidate.get("publisher_name") or "",
                            delivery_email=None,
                            reports_db=browser_settings.reports_db,
                            mailbox_settings=mailbox_settings,
                            browser_download_settings=browser_settings,
                            requested_after_utc=started_at,
                        ),
                        ctx=mail_context,
                    )
                    record["mailbox_result"] = {
                        "outcome": mail_result.outcome,
                        "mailbox_poll_count": mail_result.mailbox_poll_count,
                        "selected_report_url": mail_result.selected_report_url or "",
                        "selected_message_id_sha256": _sha256(
                            mail_result.selected_message_id or ""
                        )
                        if mail_result.selected_message_id
                        else "",
                        "acquisition_result_taxonomy": mail_result.acquisition_result_taxonomy,
                        "downloaded_file_path": _safe_path_reference(
                            mail_result.downloaded_file_path
                        ),
                    }
                except AppError as exc:
                    record["mailbox_result"] = {
                        "outcome": "failed",
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                    }
        except AppError as exc:
            record["acquisition_error"] = {
                "error_code": exc.code,
                "retryable": exc.retryable,
                "severity": exc.severity,
            }
        record["completed_at"] = _now()
        record["duration_seconds"] = round(time.monotonic() - started_monotonic, 3)
        record["resource_attempts"] = _resource_rows(
            browser_settings.reports_db, candidate["canonical_candidate_url"]
        )
        record["artifact_verification"] = _artifact_verification(record)
        records.append(record)
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")
    output = {
        "schema_version": SCHEMA_VERSION,
        "phase": "diagnostic_before_fixes",
        "run_id": root_context.run_id,
        "producer_git_sha": producer_sha,
        "manifest_sha256": supplied_hash,
        "configuration_hash": config_hash,
        "candidate_count": len(records),
        "records": records,
    }
    (output_dir / "diagnostic_replay.json").write_text(
        json.dumps(output, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def _isolated_attempt_timeout_seconds(
    *, config_path: Path, producer_sha: str
) -> tuple[float, str]:
    """Use the existing route envelope plus bounded supervisor cleanup grace."""
    workspace_root = str(Path(__file__).resolve().parents[2])
    if workspace_root not in sys.path:
        sys.path.insert(0, workspace_root)
    from src.contracts.config import ConfigLoadRequest
    from src.services.config_service import load_browser_download_settings
    from src.utils.logging import new_run_context

    context = new_run_context(
        task_id="acquisition_failure_remediation_supervisor",
        producer_commit_sha=producer_sha,
    )
    settings = load_browser_download_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(config_path.resolve())),
        context,
    )
    route_timeout = max(
        (float(budget.timeout_seconds) for budget in settings.route_budgets),
        default=float(settings.timeout_seconds),
    )
    configuration_hash = _sha256(
        {
            "config_sha256": _file_sha256(config_path),
            "identity_config_sha256": _file_sha256(
                Path(settings.identity_config_path)
            ),
            "isolation": "per_candidate_process",
        }
    )
    return route_timeout + 120.0, configuration_hash


def replay_failed_acquisition_manifest(
    *,
    manifest_path: Path,
    config_path: Path,
    dotenv_path: Path,
    output_dir: Path,
    producer_sha: str,
    candidate_ids: set[str] | None = None,
    process_isolated: bool = True,
) -> dict[str, Any]:
    """Replay a frozen cohort with one disposable process per candidate."""
    if not process_isolated:
        return _replay_failed_acquisition_manifest_direct(
            manifest_path=manifest_path,
            config_path=config_path,
            dotenv_path=dotenv_path,
            output_dir=output_dir,
            producer_sha=producer_sha,
            candidate_ids=candidate_ids,
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    supplied_hash = str(manifest.get("manifest_sha256") or "")
    calculated_hash = _sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    if not supplied_hash or supplied_hash != calculated_hash:
        raise RuntimeError(
            "Failed acquisition manifest hash does not match its frozen contents"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    _load_external_dotenv_with_owned_paths(dotenv_path)
    attempt_timeout_seconds, configuration_hash = _isolated_attempt_timeout_seconds(
        config_path=config_path, producer_sha=producer_sha
    )
    selected_candidates = [
        candidate
        for candidate in manifest["candidates"]
        if candidate_ids is None or candidate["failure_candidate_id"] in candidate_ids
    ]
    run_id = "supervisor-" + str(uuid.uuid4())
    records: list[dict[str, Any]] = []
    jsonl_path = output_dir / "acquisition_attempts.jsonl"
    worker_root = output_dir / "isolated_attempt_workers"
    worker_root.mkdir(parents=True, exist_ok=True)
    for ordinal, candidate in enumerate(selected_candidates, start=1):
        started_at = _now()
        worker_output_dir = (
            worker_root / f"{ordinal:03d}-{candidate['failure_candidate_id']}"
        )
        response_path = worker_output_dir / "diagnostic_replay.json"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "replay",
            "--manifest",
            str(manifest_path.resolve()),
            "--config",
            str(config_path.resolve()),
            "--dotenv",
            str(dotenv_path.resolve()),
            "--output-dir",
            str(worker_output_dir.resolve()),
            "--producer-sha",
            producer_sha,
            "--candidate-id",
            str(candidate["failure_candidate_id"]),
            "--worker",
        ]
        supervisor_result = _run_isolated_attempt_process(
            command=command,
            response_path=response_path,
            timeout_seconds=attempt_timeout_seconds,
        )
        record = _record_from_isolated_attempt(
            candidate=candidate,
            producer_sha=producer_sha,
            configuration_hash=configuration_hash,
            run_id=run_id,
            started_at=started_at,
            supervisor_result=supervisor_result,
        )
        records.append(record)
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")
    output = {
        "schema_version": SCHEMA_VERSION,
        "phase": "diagnostic_before_fixes",
        "run_id": run_id,
        "producer_git_sha": producer_sha,
        "manifest_sha256": supplied_hash,
        "configuration_hash": configuration_hash,
        "candidate_count": len(records),
        "records": records,
        "process_isolated": True,
        "attempt_timeout_seconds": attempt_timeout_seconds,
    }
    (output_dir / "diagnostic_replay.json").write_text(
        json.dumps(output, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze", help="freeze the exact failed cohort")
    freeze.add_argument("--reports-db", required=True)
    freeze.add_argument("--output", required=True)
    freeze.add_argument("--producer-sha", required=True)
    replay = subparsers.add_parser("replay", help="replay only a frozen failed cohort")
    replay.add_argument("--manifest", required=True)
    replay.add_argument("--config", required=True)
    replay.add_argument("--dotenv", required=True)
    replay.add_argument("--output-dir", required=True)
    replay.add_argument("--producer-sha", required=True)
    replay.add_argument("--candidate-id", action="append", default=[])
    replay.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.command == "freeze":
        result = freeze_failed_acquisition_manifest(
            reports_db=Path(args.reports_db),
            output_path=Path(args.output),
            producer_sha=args.producer_sha,
        )
        print(
            json.dumps(
                {
                    "candidate_count": result["candidate_count"],
                    "manifest_sha256": result["manifest_sha256"],
                }
            )
        )
    if args.command == "replay":
        result = replay_failed_acquisition_manifest(
            manifest_path=Path(args.manifest),
            config_path=Path(args.config),
            dotenv_path=Path(args.dotenv),
            output_dir=Path(args.output_dir),
            producer_sha=args.producer_sha,
            candidate_ids=set(args.candidate_id) or None,
            process_isolated=not args.worker,
        )
        print(
            json.dumps(
                {
                    "candidate_count": result["candidate_count"],
                    "run_id": result["run_id"],
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
