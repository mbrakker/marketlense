"""Collect internally consistent CTO evidence from immutable SQLite snapshots."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterator


ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_VERSION = "2.0"
COST_TOLERANCE = Decimal("0.000001")


class EvidenceConsistencyError(RuntimeError):
    """Base error for an evidence bundle that cannot be trusted."""


class RequiredEvidenceDatabaseError(EvidenceConsistencyError):
    """Raised when a required retained database is missing or inaccessible."""


class SnapshotIntegrityError(EvidenceConsistencyError):
    """Raised when a finalized SQLite snapshot is not internally consistent."""


class MissingArtifactError(EvidenceConsistencyError):
    """Raised when a required evidence artifact was not finalized."""


class ManifestHashMismatchError(EvidenceConsistencyError):
    """Raised when the retained snapshot manifest no longer has its recorded hash."""


class RepositoryShaMismatchError(EvidenceConsistencyError):
    """Raised when artifacts disagree about the repository commit they describe."""


class DuplicateEvidenceRunIdError(EvidenceConsistencyError):
    """Raised when an output directory already contains the requested run ID."""


class SummaryBeforeDetailedArtifactsError(EvidenceConsistencyError):
    """Raised when an executive summary has no finalized detailed source artifact."""


class RowCountMismatchError(EvidenceConsistencyError):
    """Raised when an executive count differs from its detailed rows."""


class TokenMismatchError(EvidenceConsistencyError):
    """Raised when executive token totals differ from detailed rows."""


class CostMismatchError(EvidenceConsistencyError):
    """Raised when executive cost totals differ from detailed rows."""


@dataclass(frozen=True)
class EvidencePaths:
    """Read-only inputs and generated evidence output configuration."""

    state_dir: Path
    artifact_dir: Path
    output_dir: Path
    required_databases: tuple[str, ...] = ("reports", "llm_usage")
    debug_retain_snapshots: bool = False
    evidence_run_id: str | None = None
    workspace_parent: Path | None = None


@dataclass(frozen=True)
class DatabaseSpec:
    """A mutable SQLite source that must be copied before evidence queries begin."""

    name: str
    filename: str
    tables: tuple[str, ...]
    timestamp_columns: tuple[str, ...] = ()


DATABASES = (
    DatabaseSpec(
        "reports",
        "reports.sqlite",
        (
            "publisher_download_route_history",
            "artifact_lineage_records",
            "artifact_lineage_states",
        ),
        ("created_at_utc", "updated_at_utc", "timestamp_utc"),
    ),
    DatabaseSpec(
        "llm_usage",
        "llm_usage.sqlite",
        ("llm_usage_events",),
        ("timestamp_utc",),
    ),
    DatabaseSpec(
        "index",
        "index.sqlite",
        ("workflow_control_observations",),
        ("observed_at_utc",),
    ),
    DatabaseSpec(
        "ui_runs",
        "ui_runs.sqlite",
        ("ui_runs",),
        ("finished_at_utc", "started_at_utc"),
    ),
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _connection(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    try:
        yield connection
    finally:
        connection.close()


def _exists(connection: sqlite3.Connection, table: str) -> bool:
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
    )


def _query(path: Path | None, table: str, sql: str) -> list[dict[str, object]]:
    if path is None or not path.exists():
        return []
    with _connection(path) as connection:
        return (
            [dict(row) for row in connection.execute(sql)]
            if _exists(connection, table)
            else []
        )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    stable_rows = rows or [
        {"status": "unavailable", "detail": "No retained records found."}
    ]
    fieldnames = list(dict.fromkeys(key for row in stable_rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stable_rows)
    return path


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def _public_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _decimal(value: object) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def _render_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def _sqlite_metadata(
    connection: sqlite3.Connection, spec: DatabaseSpec
) -> tuple[dict[str, int], str | None]:
    counts: dict[str, int] = {}
    maximum: str | None = None
    for table in spec.tables:
        if not _exists(connection, table):
            continue
        counts[table] = int(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        )
        columns = {
            str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
        }
        for column in spec.timestamp_columns:
            if column not in columns:
                continue
            candidate = connection.execute(
                f"SELECT MAX({column}) FROM {table}"
            ).fetchone()[0]
            if candidate is not None:
                maximum = max(maximum or "", str(candidate))
    return counts, maximum


def _snapshot_database(
    *,
    spec: DatabaseSpec,
    paths: EvidencePaths,
    workspace: Path,
) -> tuple[Path | None, dict[str, object]]:
    source = paths.state_dir / spec.filename
    entry: dict[str, object] = {
        "logical_database_name": spec.name,
        "source_path": _public_path(source, paths.state_dir),
        "snapshot_path": f"snapshots/{spec.name}.sqlite",
        "source_exists": source.exists(),
        "source_accessibility": "missing",
        "source_file_size": source.stat().st_size if source.exists() else None,
        "snapshot_file_size": None,
        "snapshot_sha256": None,
        "schema_version": None,
        "table_row_counts": {},
        "maximum_relevant_timestamp": None,
        "snapshot_created_at": _utc_now(),
        "integrity_check": "not_run",
        "foreign_key_check": "not_run",
        "journal_mode": None,
    }
    required = spec.name in paths.required_databases
    if not source.exists():
        if required:
            raise RequiredEvidenceDatabaseError(
                f"Required evidence database is missing: {spec.name}"
            )
        entry["source_accessibility"] = "missing_optional"
        return None, entry

    snapshot = workspace / "snapshots" / f"{spec.name}.sqlite"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _connection(source) as source_connection:
            entry["source_accessibility"] = "readable"
            entry["journal_mode"] = str(
                source_connection.execute("PRAGMA journal_mode").fetchone()[0]
            )
            destination = sqlite3.connect(snapshot)
            try:
                source_connection.backup(destination)
            finally:
                destination.close()
        with _connection(snapshot) as snapshot_connection:
            integrity_rows = [
                str(row[0])
                for row in snapshot_connection.execute("PRAGMA integrity_check")
            ]
            foreign_rows = [
                tuple(row)
                for row in snapshot_connection.execute("PRAGMA foreign_key_check")
            ]
            entry["integrity_check"] = integrity_rows
            entry["foreign_key_check"] = foreign_rows
            if integrity_rows != ["ok"] or foreign_rows:
                raise SnapshotIntegrityError(
                    f"SQLite snapshot integrity failed for {spec.name}"
                )
            entry["schema_version"] = int(
                snapshot_connection.execute("PRAGMA schema_version").fetchone()[0]
            )
            counts, maximum = _sqlite_metadata(snapshot_connection, spec)
            entry["table_row_counts"] = counts
            entry["maximum_relevant_timestamp"] = maximum
        entry["snapshot_file_size"] = snapshot.stat().st_size
        entry["snapshot_sha256"] = _sha256(snapshot)
        return snapshot, entry
    except (OSError, sqlite3.Error) as exc:
        entry["source_accessibility"] = "unreadable"
        entry["integrity_check"] = "error"
        if required:
            raise RequiredEvidenceDatabaseError(
                f"Required evidence database is inaccessible: {spec.name}"
            ) from exc
        return None, entry


def _validate_snapshot_integrity(
    entries: list[dict[str, object]], snapshots: dict[str, Path]
) -> None:
    for entry in entries:
        name = str(entry["logical_database_name"])
        snapshot = snapshots.get(name)
        if snapshot is None:
            continue
        if (
            entry.get("integrity_check") != ["ok"]
            or entry.get("foreign_key_check") != []
        ):
            raise SnapshotIntegrityError(
                f"Snapshot integrity metadata failed for {name}"
            )
        try:
            with _connection(snapshot) as connection:
                integrity_rows = [
                    str(row[0]) for row in connection.execute("PRAGMA integrity_check")
                ]
                foreign_rows = [
                    tuple(row) for row in connection.execute("PRAGMA foreign_key_check")
                ]
        except sqlite3.Error as exc:
            raise SnapshotIntegrityError(
                f"Snapshot integrity failed for {name}"
            ) from exc
        if integrity_rows != ["ok"] or foreign_rows:
            raise SnapshotIntegrityError(f"Snapshot integrity failed for {name}")


def _snapshot_artifact_inputs(
    artifact_dir: Path, workspace: Path
) -> tuple[Path, list[dict[str, object]]]:
    """Freeze the retained crop inputs so no metric reads a mutable live artifact."""
    destination_root = workspace / "crop_artifacts"
    entries: list[dict[str, object]] = []
    for source in sorted(artifact_dir.rglob("crop_refine.json")):
        try:
            relative = source.relative_to(artifact_dir)
            destination = destination_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            entries.append(
                {
                    "source_path": relative.as_posix(),
                    "snapshot_path": f"crop_artifacts/{relative.as_posix()}",
                    "source_file_size": source.stat().st_size,
                    "snapshot_file_size": destination.stat().st_size,
                    "snapshot_sha256": _sha256(destination),
                    "accessibility": "readable",
                }
            )
        except OSError:
            entries.append(
                {
                    "source_path": _public_path(source, artifact_dir),
                    "snapshot_path": "",
                    "source_file_size": None,
                    "snapshot_file_size": None,
                    "snapshot_sha256": None,
                    "accessibility": "unreadable",
                }
            )
    return destination_root, entries


def _aggregate_llm_rows(raw_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, ...], dict[str, object]] = {}
    for row in raw_rows:
        key = tuple(
            str(row.get(name) or "")
            for name in (
                "date",
                "provider",
                "model",
                "action",
                "semantic_task",
                "prompt_namespace",
                "provider_call_status",
            )
        )
        group = grouped.setdefault(
            key,
            {
                "date": key[0],
                "provider": key[1],
                "model": key[2],
                "action": key[3],
                "semantic_task": key[4],
                "prompt_namespace": key[5],
                "provider_call_status": key[6],
                "request_count": 0,
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": Decimal("0"),
                "unknown_pricing_count": 0,
            },
        )
        for name in (
            "request_count",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "total_tokens",
        ):
            group[name] = int(group[name]) + int(row.get(name) or 0)
        group["estimated_cost_usd"] = _decimal(group["estimated_cost_usd"]) + _decimal(
            row.get("estimated_cost_usd")
        )
        group["unknown_pricing_count"] = int(group["unknown_pricing_count"]) + int(
            row.get("estimated_cost_usd") is None
        )
    result: list[dict[str, object]] = []
    for key in sorted(grouped):
        row = dict(grouped[key])
        row["estimated_cost_usd"] = _render_decimal(_decimal(row["estimated_cost_usd"]))
        result.append(row)
    return result


def _aggregate_ocr_rows(raw_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    selected = [
        row
        for row in raw_rows
        if any(
            token
            in " ".join(
                str(row.get(field) or "").lower()
                for field in ("action", "semantic_task", "prompt_namespace")
            )
            for token in ("ocr", "vision", "crop")
        )
    ]
    grouped: dict[tuple[str, ...], dict[str, object]] = {}
    for row in selected:
        key = tuple(
            str(row.get(name) or "")
            for name in (
                "action",
                "semantic_task",
                "provider",
                "model",
                "provider_call_status",
            )
        )
        group = grouped.setdefault(
            key,
            {
                "action": key[0],
                "semantic_task": key[1],
                "provider": key[2],
                "model": key[3],
                "provider_call_status": key[4],
                "request_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_usd": Decimal("0"),
            },
        )
        for name in ("request_count", "input_tokens", "output_tokens"):
            group[name] = int(group[name]) + int(row.get(name) or 0)
        group["estimated_cost_usd"] = _decimal(group["estimated_cost_usd"]) + _decimal(
            row.get("estimated_cost_usd")
        )
    result: list[dict[str, object]] = []
    for key in sorted(grouped):
        row = dict(grouped[key])
        row["estimated_cost_usd"] = _render_decimal(_decimal(row["estimated_cost_usd"]))
        result.append(row)
    return result


def _metric_rows(
    snapshots: dict[str, Path], artifact_dir: Path
) -> dict[str, list[dict[str, object]]]:
    reports = snapshots.get("reports")
    usage = snapshots.get("llm_usage")
    index = snapshots.get("index")
    ui = snapshots.get("ui_runs")
    acquisition = _query(
        reports,
        "publisher_download_route_history",
        """
        SELECT 'unattributed' publisher,route_family,route_kind,outcome,route_status,
        COUNT(*) sample_size,SUM(attempts) attempts,SUM(verified_successes) successes,
        'route history has no publisher, duration or cost fields' limitation
        FROM publisher_download_route_history GROUP BY route_family,route_kind,outcome,route_status
        ORDER BY route_family,route_kind,outcome""",
    )
    browser = _query(
        reports,
        "publisher_download_route_history",
        """
        SELECT route_family,COUNT(*) acquisition_records,SUM(attempts) attempts,
        SUM(json_array_length(route_steps_json)) browser_steps,
        SUM(CASE WHEN browser_had_structured_result THEN 1 ELSE 0 END) structured_browser_records,
        SUM(CASE WHEN onsite_capture_path<>'' AND onsite_capture_path IS NOT NULL THEN 1 ELSE 0 END) onsite_capture_records,
        'launch/navigation/screenshot/network/duration fields not retained' limitation
        FROM publisher_download_route_history GROUP BY route_family ORDER BY route_family""",
    )
    llm_events = _query(
        usage,
        "llm_usage_events",
        """
        SELECT substr(timestamp_utc,1,10) date,provider,model,action,semantic_task,prompt_namespace,
        provider_call_status,input_tokens,cached_input_tokens,output_tokens,total_tokens,estimated_cost_usd,
        1 request_count
        FROM llm_usage_events ORDER BY timestamp_utc,provider,model,action,semantic_task""",
    )
    lineage = _query(
        reports,
        "artifact_lineage_records",
        """
        SELECT r.artifact_kind,s.state,r.producer,COUNT(*) artifact_count,COUNT(DISTINCT r.report_id) report_count,
        'persisted lineage; reuse-decision event count is not retained' limitation
        FROM artifact_lineage_records r JOIN artifact_lineage_states s USING(artifact_id)
        GROUP BY r.artifact_kind,s.state,r.producer ORDER BY r.artifact_kind,s.state,r.producer""",
    )
    failures = _query(
        index,
        "workflow_control_observations",
        """
        SELECT workflow,step_name stage,error_code,error_retryable,error_severity,outcome,COUNT(*) record_count,
        SUM(retry_count) retry_count,MIN(observed_at_utc) first_seen,MAX(observed_at_utc) last_seen
        FROM workflow_control_observations WHERE error_code<>''
        GROUP BY workflow,stage,error_code,error_retryable,error_severity,outcome ORDER BY record_count DESC""",
    )
    failures += _query(
        ui,
        "ui_runs",
        """
        SELECT run_type workflow,'ui_run' stage,error_code,error_retryable,error_severity,status outcome,COUNT(*) record_count,
        0 retry_count,MIN(finished_at_utc) first_seen,MAX(finished_at_utc) last_seen
        FROM ui_runs WHERE error_code<>'' GROUP BY run_type,error_code,error_retryable,error_severity,status""",
    )
    wordpress = _query(
        index,
        "workflow_control_observations",
        """
        SELECT workflow,step_name,outcome,error_code,COUNT(*) record_count,SUM(retry_count) retry_count,
        MIN(latency_ms) min_latency_ms,MAX(latency_ms) max_latency_ms
        FROM workflow_control_observations WHERE workflow LIKE '%publish%' OR step_name LIKE '%wordpress%'
        GROUP BY workflow,step_name,outcome,error_code ORDER BY workflow,step_name,outcome""",
    )
    crop: list[dict[str, object]] = []
    for path in sorted(artifact_dir.rglob("crop_refine.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        results = data.get("results", [])
        crop.append(
            {
                "report": path.parent.parent.name,
                "refinement_records": len(results),
                "valid_candidates": sum(
                    bool(item.get("is_valid_candidate"))
                    for item in results
                    if isinstance(item, dict)
                ),
                "model": data.get("_cache", {}).get("model", ""),
                "limitation": "No .qa.json visual-defect sidecars retained.",
            }
        )
    return {
        "acquisition_metrics.csv": acquisition,
        "browser_metrics.csv": browser,
        "llm_usage_metrics.csv": _aggregate_llm_rows(llm_events),
        "ocr_vision_metrics.csv": _aggregate_ocr_rows(llm_events),
        "lineage_reuse_metrics.csv": lineage,
        "failure_metrics.csv": failures,
        "wordpress_metrics.csv": wordpress,
        "crop_quality_metrics.csv": crop,
    }


def _git_state() -> tuple[str, bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return "unavailable", True


def _executive_summary(
    detailed_path: Path, *, run_id: str, commit_sha: str, artifact_names: list[str]
) -> dict[str, object]:
    if not detailed_path.is_file():
        raise SummaryBeforeDetailedArtifactsError(
            "Detailed artifacts were not finalized"
        )
    detailed = json.loads(detailed_path.read_text(encoding="utf-8"))
    if detailed.get("evidence_run_id") != run_id:
        raise DuplicateEvidenceRunIdError(
            "Detailed artifacts carry a different evidence run ID"
        )
    metrics = detailed.get("metrics")
    if not isinstance(metrics, dict):
        raise SummaryBeforeDetailedArtifactsError("Detailed metrics payload is invalid")
    llm_rows = metrics.get("llm_usage_metrics.csv", [])
    acquisition_rows = metrics.get("acquisition_metrics.csv", [])
    failure_rows = metrics.get("failure_metrics.csv", [])
    if not all(
        isinstance(rows, list) for rows in (llm_rows, acquisition_rows, failure_rows)
    ):
        raise SummaryBeforeDetailedArtifactsError("Detailed metric rows are invalid")
    llm = [row for row in llm_rows if isinstance(row, dict)]
    acquisition = [row for row in acquisition_rows if isinstance(row, dict)]
    failures = [row for row in failure_rows if isinstance(row, dict)]
    return {
        "schema_version": "1.0",
        "evidence_run_id": run_id,
        "repository": {"commit_sha": commit_sha},
        "artifacts": artifact_names,
        "totals": {
            "llm": {
                "call_count": sum(int(row.get("request_count") or 0) for row in llm),
                "input_tokens": sum(int(row.get("input_tokens") or 0) for row in llm),
                "output_tokens": sum(int(row.get("output_tokens") or 0) for row in llm),
                "total_tokens": sum(int(row.get("total_tokens") or 0) for row in llm),
                "estimated_cost_usd": _render_decimal(
                    sum(
                        (_decimal(row.get("estimated_cost_usd")) for row in llm),
                        Decimal("0"),
                    )
                ),
            },
            "acquisition": {
                "record_count": sum(
                    int(row.get("sample_size") or 0) for row in acquisition
                ),
                "attempt_count": sum(
                    int(row.get("attempts") or 0) for row in acquisition
                ),
                "success_count": sum(
                    int(row.get("successes") or 0) for row in acquisition
                ),
            },
            "failures": {
                "record_count": sum(
                    int(row.get("record_count") or 0) for row in failures
                )
            },
        },
    }


def validate_consistency(output_dir: Path, *, expected_run_id: str) -> None:
    """Fail closed when finalized evidence artifacts disagree with one another."""
    manifest_path = output_dir / "evidence_run_manifest.json"
    snapshot_manifest_path = output_dir / "snapshot_manifest.json"
    detailed_path = output_dir / "detailed_metrics.json"
    summary_path = output_dir / "executive_summary.json"
    for path in (manifest_path, snapshot_manifest_path, detailed_path, summary_path):
        if not path.is_file():
            raise MissingArtifactError(
                f"Required evidence artifact is missing: {path.name}"
            )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    detailed = json.loads(detailed_path.read_text(encoding="utf-8"))
    if (
        len(
            {
                str(manifest.get("evidence_run_id")),
                str(summary.get("evidence_run_id")),
                str(detailed.get("evidence_run_id")),
                expected_run_id,
            }
        )
        != 1
    ):
        raise DuplicateEvidenceRunIdError(
            "Evidence artifacts do not share one evidence run ID"
        )
    snapshot_hash = _sha256(snapshot_manifest_path)
    if manifest.get("snapshot_manifest_sha256") != snapshot_hash:
        raise ManifestHashMismatchError(
            "Snapshot manifest hash does not match the finalized file"
        )
    if summary.get("repository", {}).get("commit_sha") != manifest.get(
        "repository", {}
    ).get("commit_sha"):
        raise RepositoryShaMismatchError(
            "Executive summary and run manifest disagree on commit SHA"
        )
    manifest_names = set(manifest.get("generated_artifacts", []))
    if any(name not in manifest_names for name in summary.get("artifacts", [])):
        raise MissingArtifactError(
            "Executive summary names an artifact absent from the run manifest"
        )
    metrics = detailed.get("metrics", {})
    if not isinstance(metrics, dict):
        raise SummaryBeforeDetailedArtifactsError("Detailed metrics payload is invalid")
    llm_rows = metrics.get("llm_usage_metrics.csv", [])
    acquisition_rows = metrics.get("acquisition_metrics.csv", [])
    failure_rows = metrics.get("failure_metrics.csv", [])
    if not all(
        isinstance(rows, list) for rows in (llm_rows, acquisition_rows, failure_rows)
    ):
        raise SummaryBeforeDetailedArtifactsError(
            "Detailed metric row sets are invalid"
        )
    llm = [row for row in llm_rows if isinstance(row, dict)]
    acquisition = [row for row in acquisition_rows if isinstance(row, dict)]
    failures = [row for row in failure_rows if isinstance(row, dict)]
    totals = summary.get("totals", {})
    llm_totals = totals.get("llm", {}) if isinstance(totals, dict) else {}
    acquisition_totals = (
        totals.get("acquisition", {}) if isinstance(totals, dict) else {}
    )
    failure_totals = totals.get("failures", {}) if isinstance(totals, dict) else {}
    expected_calls = sum(int(row.get("request_count") or 0) for row in llm)
    expected_input = sum(int(row.get("input_tokens") or 0) for row in llm)
    expected_output = sum(int(row.get("output_tokens") or 0) for row in llm)
    expected_tokens = sum(int(row.get("total_tokens") or 0) for row in llm)
    if int(llm_totals.get("call_count") or 0) != expected_calls:
        raise RowCountMismatchError("LLM call total differs from detailed LLM rows")
    if (
        int(llm_totals.get("input_tokens") or 0) != expected_input
        or int(llm_totals.get("output_tokens") or 0) != expected_output
        or int(llm_totals.get("total_tokens") or 0) != expected_tokens
        or expected_tokens != expected_input + expected_output
    ):
        raise TokenMismatchError("LLM token totals differ from detailed LLM rows")
    expected_cost = sum(
        (_decimal(row.get("estimated_cost_usd")) for row in llm), Decimal("0")
    )
    if (
        abs(_decimal(llm_totals.get("estimated_cost_usd")) - expected_cost)
        > COST_TOLERANCE
    ):
        raise CostMismatchError("LLM cost total differs from detailed LLM rows")
    if int(acquisition_totals.get("record_count") or 0) != sum(
        int(row.get("sample_size") or 0) for row in acquisition
    ):
        raise RowCountMismatchError(
            "Acquisition total differs from detailed route metrics"
        )
    if int(failure_totals.get("record_count") or 0) != sum(
        int(row.get("record_count") or 0) for row in failures
    ):
        raise RowCountMismatchError(
            "Failure total differs from detailed failure records"
        )


def collect(
    paths: EvidencePaths,
    *,
    command_args: tuple[str, ...] = (),
    _after_snapshot: Callable[[dict[str, Path]], None] | None = None,
) -> list[Path]:
    """Write a validated evidence bundle from one read-consistent snapshot set."""
    run_id = paths.evidence_run_id or uuid.uuid4().hex
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    existing_manifest = paths.output_dir / "evidence_run_manifest.json"
    if existing_manifest.is_file():
        try:
            existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        if existing.get("evidence_run_id") == run_id:
            raise DuplicateEvidenceRunIdError(
                f"Evidence run ID already exists: {run_id}"
            )
    workspace = Path(
        tempfile.mkdtemp(prefix="cto_evidence_", dir=paths.workspace_parent)
    )
    started_at = _utc_now()
    commit_sha, dirty = _git_state()
    snapshots: dict[str, Path] = {}
    entries: list[dict[str, object]] = []
    try:
        for spec in DATABASES:
            snapshot, entry = _snapshot_database(
                spec=spec, paths=paths, workspace=workspace
            )
            entries.append(entry)
            if snapshot is not None:
                snapshots[spec.name] = snapshot
        _validate_snapshot_integrity(entries, snapshots)
        artifact_snapshot_root, artifact_entries = _snapshot_artifact_inputs(
            paths.artifact_dir, workspace
        )
        if _after_snapshot is not None:
            _after_snapshot(dict(snapshots))
        _validate_snapshot_integrity(entries, snapshots)
        snapshot_manifest_path = _write_json(
            paths.output_dir / "snapshot_manifest.json",
            {
                "schema_version": "1.0",
                "evidence_run_id": run_id,
                "snapshots": entries,
                "artifact_snapshots": artifact_entries,
            },
        )
        metrics = _metric_rows(snapshots, artifact_snapshot_root)
        csv_paths = [
            _write_csv(paths.output_dir / name, rows) for name, rows in metrics.items()
        ]
        detailed_path = _write_json(
            paths.output_dir / "detailed_metrics.json",
            {"schema_version": "1.0", "evidence_run_id": run_id, "metrics": metrics},
        )
        summary_artifacts = [
            path.name for path in [*csv_paths, detailed_path, snapshot_manifest_path]
        ]
        summary_path = _write_json(
            paths.output_dir / "executive_summary.json",
            _executive_summary(
                detailed_path,
                run_id=run_id,
                commit_sha=commit_sha,
                artifact_names=summary_artifacts,
            ),
        )
        generated_artifacts = [
            *summary_artifacts,
            summary_path.name,
            "evidence_run_manifest.json",
            "consistency_validation.json",
        ]
        configuration = {
            "state_dir": _public_path(paths.state_dir, paths.state_dir),
            "artifact_dir": _public_path(paths.artifact_dir, ROOT),
            "required_databases": sorted(paths.required_databases),
        }
        manifest_path = _write_json(
            paths.output_dir / "evidence_run_manifest.json",
            {
                "schema_version": "1.0",
                "evidence_run_id": run_id,
                "collector_version": COLLECTOR_VERSION,
                "repository": {"commit_sha": commit_sha, "dirty_worktree": dirty},
                "started_at": started_at,
                "ended_at": _utc_now(),
                "configuration_hash": hashlib.sha256(
                    json.dumps(configuration, sort_keys=True).encode("utf-8")
                ).hexdigest(),
                "snapshot_manifest_sha256": _sha256(snapshot_manifest_path),
                "command_args": list(command_args),
                "python_version": sys.version,
                "operating_system": platform.platform(),
                "generated_artifacts": generated_artifacts,
            },
        )
        validate_consistency(paths.output_dir, expected_run_id=run_id)
        validation_path = _write_json(
            paths.output_dir / "consistency_validation.json",
            {
                "schema_version": "1.0",
                "evidence_run_id": run_id,
                "status": "passed",
                "cost_tolerance_usd": _render_decimal(COST_TOLERANCE),
            },
        )
        return [
            *csv_paths,
            detailed_path,
            snapshot_manifest_path,
            summary_path,
            manifest_path,
            validation_path,
        ]
    finally:
        if not paths.debug_retain_snapshots:
            shutil.rmtree(workspace, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", default="state")
    parser.add_argument("--artifact-dir", default="out")
    parser.add_argument("--output-dir", default="out/cto-review-evidence")
    parser.add_argument("--debug-retain-snapshots", action="store_true")
    args = parser.parse_args()
    for path in collect(
        EvidencePaths(
            Path(args.state_dir),
            Path(args.artifact_dir),
            Path(args.output_dir),
            debug_retain_snapshots=args.debug_retain_snapshots,
        ),
        command_args=tuple(sys.argv[1:]),
    ):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
