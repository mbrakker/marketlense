"""Collect internally consistent CTO evidence from immutable SQLite snapshots."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.quality._cto_review_evidence.log_content_leakage import (
        extract_canaries,
        normalize_text,
        scan_logs,
    )
except ModuleNotFoundError:  # Direct `python scripts/quality/...` execution.
    from _cto_review_evidence.log_content_leakage import (
        extract_canaries,
        normalize_text,
        scan_logs,
    )

COLLECTOR_VERSION = "3.0"
COST_TOLERANCE = Decimal("0.000001")
COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
CANONICAL_LOG_RE = re.compile(r"^market_lense_\d{4}-\d{2}-\d{2}\.log$")
LOG_CORPUS_SCOPES = frozenset(
    {
        "not_declared",
        "post_remediation_smoke_only",
        "representative_report_processing",
    }
)
LOG_CORPUS_LIMITATIONS = {
    "not_declared": "log_corpus_scope_not_declared",
    "post_remediation_smoke_only": (
        "post_remediation_smoke_only_no_representative_report_processing"
    ),
}
RETAINED_ARTIFACT_FILENAMES = frozenset(
    {
        "artifacts.json",
        "crop_refine.json",
        "doc_map.json",
        "document_map.json",
        "extracted_text.json",
        "findings.json",
        "limitations.json",
        "methods.json",
        "page_text.json",
        "quote_candidates.json",
        "scope.json",
        "source_text.json",
    }
)


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


class RepositoryStateUnavailableError(EvidenceConsistencyError):
    """Raised when strict evidence cannot inspect Git repository state."""


class RepositoryHeadMismatchError(EvidenceConsistencyError):
    """Raised when the requested commit is not the initial repository HEAD."""


class RepositoryHeadChangedError(EvidenceConsistencyError):
    """Raised when repository HEAD changes during strict collection."""


class RepositoryWorktreeDirtyError(EvidenceConsistencyError):
    """Raised when strict collection observes a dirty worktree."""


class EvidenceFreshnessError(EvidenceConsistencyError):
    """Raised when a strict evidence run lacks fresh required evidence."""


class LogSnapshotError(EvidenceConsistencyError):
    """Raised when a discovered standard application log cannot be frozen."""


class EvidenceCoverageError(EvidenceConsistencyError):
    """Raised when strict content-leakage coverage is incomplete."""


class LogCorpusScopeError(EvidenceConsistencyError):
    """Raised when an operator-declared log corpus scope is not recognized."""


class RetainedArtifactEvidenceError(EvidenceConsistencyError):
    """Raised when a retained artifact needed for evidence cannot be assessed."""


class LogContentLeakageError(EvidenceConsistencyError):
    """Raised when report or editorial retained content appears in standard logs."""


class ArtifactIntegrityError(EvidenceConsistencyError):
    """Raised when a finalized artifact inventory cannot be verified."""


class RawCanaryDisclosureError(EvidenceConsistencyError):
    """Raised when a private retained paragraph appears in public evidence."""


class OutputDirectoryNotEmptyError(EvidenceConsistencyError):
    """Raised when publication would merge an evidence run into an old bundle."""


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
    # CLI supplies the operational default (logs); direct legacy callers opt in.
    log_dir: Path = Path()
    required_databases: tuple[str, ...] = ("reports", "llm_usage")
    debug_retain_snapshots: bool = False
    evidence_run_id: str | None = None
    workspace_parent: Path | None = None
    archive_path: Path | None = None
    require_exact_head: bool = False
    expected_commit_sha: str | None = None
    fresh_after: str | None = None
    log_corpus_scope: str = "not_declared"
    minimum_source_canaries: int = 5
    minimum_editorial_canaries: int = 5
    maximum_canaries_per_class: int = 25
    replace_output: bool = False
    repository_root: Path = ROOT


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


def _archive_evidence_bundle(output_dir: Path, archive_path: Path) -> Path:
    """Atomically replace the distributable ZIP after evidence is validated."""
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="cto_evidence_archive_", dir=archive_path.parent
    ) as temp_dir:
        temporary_base = Path(temp_dir) / archive_path.stem
        created = Path(
            shutil.make_archive(str(temporary_base), "zip", root_dir=output_dir)
        )
        created.replace(archive_path)
    return archive_path


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
    artifact_dir: Path, workspace: Path, *, strict: bool
) -> tuple[Path, list[dict[str, object]]]:
    """Freeze retained JSON inputs before metrics or canary extraction reads them."""
    destination_root = workspace / "retained_artifacts"
    entries: list[dict[str, object]] = []
    if not artifact_dir.exists():
        return destination_root, entries
    for source in sorted(artifact_dir.rglob("*.json")):
        if source.name not in RETAINED_ARTIFACT_FILENAMES:
            continue
        try:
            relative = source.relative_to(artifact_dir)
            destination = destination_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            entries.append(
                {
                    "source_path": relative.as_posix(),
                    "snapshot_path": f"retained_artifacts/{relative.as_posix()}",
                    "source_file_size": source.stat().st_size,
                    "snapshot_file_size": destination.stat().st_size,
                    "snapshot_sha256": _sha256(destination),
                    "accessibility": "readable",
                }
            )
        except OSError as exc:
            if strict:
                raise RetainedArtifactEvidenceError(
                    f"Retained artifact cannot be snapshotted: {source.name}"
                ) from exc
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


def _snapshot_standard_logs(
    log_dir: Path, workspace: Path, *, strict: bool
) -> tuple[Path, list[dict[str, object]]]:
    """Copy only canonical application logs and defer every read to their snapshots."""
    destination_root = workspace / "standard_logs"
    entries: list[dict[str, object]] = []
    if not log_dir.exists():
        return destination_root, entries
    for source in sorted(log_dir.iterdir()):
        if not source.is_file() or not CANONICAL_LOG_RE.fullmatch(source.name):
            continue
        relative = source.relative_to(log_dir)
        destination = destination_root / relative
        entry: dict[str, object] = {
            "source_path": relative.as_posix(),
            "snapshot_path": f"standard_logs/{relative.as_posix()}",
            "source_file_size": None,
            "snapshot_file_size": None,
            "snapshot_sha256": None,
            "source_modified_at": None,
            "first_parsed_event_timestamp": None,
            "last_parsed_event_timestamp": None,
            "total_line_count": 0,
            "parsed_structured_event_count": 0,
            "unparsed_line_count": 0,
            "accessibility": "unreadable",
        }
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            source_stat = source.stat()
            shutil.copyfile(source, destination)
            entry.update(
                {
                    "source_file_size": source_stat.st_size,
                    "snapshot_file_size": destination.stat().st_size,
                    "snapshot_sha256": _sha256(destination),
                    "source_modified_at": datetime.fromtimestamp(
                        source_stat.st_mtime, UTC
                    ).isoformat(),
                    "accessibility": "readable",
                }
            )
        except OSError as exc:
            if strict:
                raise LogSnapshotError(
                    f"Standard log cannot be snapshotted: {relative.as_posix()}"
                ) from exc
        entries.append(entry)
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


def _git_state(repository_root: Path, *, strict: bool) -> tuple[str, bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repository_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        if not COMMIT_SHA_RE.fullmatch(commit):
            raise RepositoryStateUnavailableError(
                "Git did not return a full 40-character repository commit SHA"
            )
        return commit, dirty
    except (OSError, subprocess.CalledProcessError) as exc:
        if strict:
            raise RepositoryStateUnavailableError(
                "Strict CTO evidence requires available Git metadata"
            ) from exc
        return "unavailable", True


def _parse_aware_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceFreshnessError(
            "fresh_after must be a timezone-aware ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise EvidenceFreshnessError("fresh_after must include a timezone offset or Z")
    return parsed.astimezone(UTC)


def _repository_provenance(
    paths: EvidencePaths,
) -> tuple[dict[str, object], datetime | None]:
    """Validate strict start state before any expensive source snapshot work."""
    fresh_after = (
        _parse_aware_timestamp(paths.fresh_after) if paths.fresh_after else None
    )
    if paths.expected_commit_sha and not COMMIT_SHA_RE.fullmatch(
        paths.expected_commit_sha
    ):
        raise RepositoryHeadMismatchError(
            "expected_commit_sha must be a full 40-character commit SHA"
        )
    start_sha, dirty = _git_state(
        paths.repository_root, strict=paths.require_exact_head
    )
    expected_sha = (paths.expected_commit_sha or start_sha).lower()
    if paths.require_exact_head:
        if dirty:
            raise RepositoryWorktreeDirtyError(
                "Strict CTO evidence requires a clean worktree at collection start"
            )
        if start_sha != expected_sha:
            raise RepositoryHeadMismatchError(
                f"Repository HEAD {start_sha} does not match expected {expected_sha}"
            )
    return (
        {
            "expected_commit_sha": expected_sha,
            "start_commit_sha": start_sha,
            "end_commit_sha": None,
            "head_stable": False,
            "dirty_worktree_start": dirty,
            "dirty_worktree_end": None,
            "exact_head_verified": False,
        },
        fresh_after,
    )


def _finalize_repository_provenance(
    paths: EvidencePaths, repository: dict[str, object]
) -> None:
    end_sha, end_dirty = _git_state(
        paths.repository_root, strict=paths.require_exact_head
    )
    repository["end_commit_sha"] = end_sha
    repository["dirty_worktree_end"] = end_dirty
    expected = str(repository["expected_commit_sha"])
    start = str(repository["start_commit_sha"])
    stable = start == expected == end_sha
    repository["head_stable"] = stable
    if paths.require_exact_head:
        if end_dirty:
            raise RepositoryWorktreeDirtyError(
                "Strict CTO evidence requires a clean worktree at finalization"
            )
        if end_sha != start:
            raise RepositoryHeadChangedError(
                f"Repository HEAD changed during collection: {start} to {end_sha}"
            )
        if end_sha != expected:
            raise RepositoryHeadMismatchError(
                f"Final repository HEAD {end_sha} does not match expected {expected}"
            )
        repository["exact_head_verified"] = True


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
        "generated_at": _utc_now(),
        "evidence_run_id": run_id,
        "repository_commit_sha": commit_sha,
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


def validate_consistency(
    output_dir: Path,
    *,
    expected_run_id: str,
    strict: bool = False,
    forbidden_canaries: tuple[str, ...] = (),
    require_validation: bool = True,
) -> None:
    """Verify one finalized bundle without trusting its own inventory."""
    required_names = (
        "evidence_run_manifest.json",
        "snapshot_manifest.json",
        "detailed_metrics.json",
        "executive_summary.json",
        "log_content_leakage.json",
    )
    files = {name: output_dir / name for name in required_names}
    for name, path in files.items():
        if not path.is_file():
            raise MissingArtifactError(f"Required evidence artifact is missing: {name}")
    manifest = json.loads(
        files["evidence_run_manifest.json"].read_text(encoding="utf-8")
    )
    snapshot = json.loads(files["snapshot_manifest.json"].read_text(encoding="utf-8"))
    detailed = json.loads(files["detailed_metrics.json"].read_text(encoding="utf-8"))
    summary = json.loads(files["executive_summary.json"].read_text(encoding="utf-8"))
    leakage = json.loads(files["log_content_leakage.json"].read_text(encoding="utf-8"))
    validation_path = output_dir / "consistency_validation.json"
    if require_validation and not validation_path.is_file():
        raise MissingArtifactError(
            "Required evidence artifact is missing: consistency_validation.json"
        )
    validation = (
        json.loads(validation_path.read_text(encoding="utf-8"))
        if require_validation
        else None
    )
    commit_sha = str(manifest.get("repository", {}).get("expected_commit_sha") or "")
    artifacts = (manifest, snapshot, detailed, summary, leakage)
    if any(
        str(item.get("evidence_run_id") or "") != expected_run_id for item in artifacts
    ):
        raise DuplicateEvidenceRunIdError(
            "Evidence artifacts do not share one evidence run ID"
        )
    if any(
        str(item.get("repository_commit_sha") or "") != commit_sha
        for item in (snapshot, detailed, summary, leakage)
    ):
        raise RepositoryShaMismatchError(
            "Evidence artifacts do not share one repository SHA"
        )
    if manifest.get("snapshot_manifest_sha256") != _sha256(
        files["snapshot_manifest.json"]
    ):
        raise ManifestHashMismatchError(
            "Snapshot manifest hash does not match the finalized file"
        )
    if validation is not None:
        if (
            validation.get("evidence_run_id") != expected_run_id
            or validation.get("repository_commit_sha") != commit_sha
        ):
            raise ArtifactIntegrityError(
                "Consistency validation provenance does not match the evidence bundle"
            )
        if validation.get("run_manifest_sha256") != _sha256(
            files["evidence_run_manifest.json"]
        ):
            raise ArtifactIntegrityError(
                "Consistency validation does not hash the finalized run manifest"
            )
    repository = manifest.get("repository", {})
    if strict:
        if not repository.get("exact_head_verified"):
            raise RepositoryHeadMismatchError(
                "Strict bundle does not verify exact HEAD"
            )
        if repository.get("start_commit_sha") != repository.get("end_commit_sha"):
            raise RepositoryHeadChangedError(
                "Repository HEAD differs between start and end"
            )
        if repository.get("dirty_worktree_start") or repository.get(
            "dirty_worktree_end"
        ):
            raise RepositoryWorktreeDirtyError("Strict bundle records a dirty worktree")
    inventory = manifest.get("artifact_inventory", [])
    if not isinstance(inventory, list):
        raise ArtifactIntegrityError("Artifact inventory is missing or invalid")
    if any(
        item.get("relative_path") == "evidence_run_manifest.json"
        for item in inventory
        if isinstance(item, dict)
    ):
        raise ArtifactIntegrityError(
            "Run manifest must not hash itself in its inventory"
        )
    metrics = detailed.get("metrics", {})
    if not isinstance(metrics, dict):
        raise SummaryBeforeDetailedArtifactsError("Detailed metrics payload is invalid")
    llm = [
        row for row in metrics.get("llm_usage_metrics.csv", []) if isinstance(row, dict)
    ]
    acquisition = [
        row
        for row in metrics.get("acquisition_metrics.csv", [])
        if isinstance(row, dict)
    ]
    failures = [
        row for row in metrics.get("failure_metrics.csv", []) if isinstance(row, dict)
    ]
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
    for item in inventory:
        if not isinstance(item, dict):
            raise ArtifactIntegrityError("Artifact inventory entry is invalid")
        relative = str(item.get("relative_path") or "")
        path = output_dir / relative
        if not path.is_file():
            raise MissingArtifactError(f"Inventoried artifact is missing: {relative}")
        if int(item.get("byte_count") or -1) != path.stat().st_size or item.get(
            "sha256"
        ) != _sha256(path):
            raise ArtifactIntegrityError(f"Artifact inventory mismatch: {relative}")
        if (
            item.get("evidence_run_id") != expected_run_id
            or item.get("repository_commit_sha") != commit_sha
        ):
            raise ArtifactIntegrityError(
                f"Artifact inventory provenance mismatch: {relative}"
            )
    if strict:
        if leakage.get("status") == "incomplete":
            raise EvidenceCoverageError("Strict bundle has incomplete leakage evidence")
        if leakage.get("status") == "failed" or leakage.get("matches"):
            raise LogContentLeakageError("Strict bundle detects report content in logs")
        if leakage.get("status") != "passed" or leakage.get("passed") is not True:
            raise EvidenceCoverageError(
                "Strict bundle lacks a passed leakage assessment"
            )
        coverage = leakage.get("coverage", {})
        if int(coverage.get("source_canary_count") or 0) < int(
            manifest.get("configuration", {}).get("minimum_source_canaries") or 0
        ) or int(coverage.get("editorial_canary_count") or 0) < int(
            manifest.get("configuration", {}).get("minimum_editorial_canaries") or 0
        ):
            raise EvidenceCoverageError(
                "Strict bundle has insufficient canary coverage"
            )
        if int(coverage.get("log_files_scanned") or 0) < 1:
            raise EvidenceCoverageError("Strict bundle has no standard logs")
        if manifest.get("fresh_after") and not leakage.get("fresh_log_seen"):
            raise EvidenceFreshnessError("Strict bundle has no fresh standard log")
    rendered = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in output_dir.rglob("*.*")
        if path.is_file()
    )
    normalized_rendered = normalize_text(rendered)
    if any(value and value in normalized_rendered for value in forbidden_canaries):
        raise RawCanaryDisclosureError(
            "A raw retained canary appears in public evidence"
        )


def _artifact_inventory(
    output_dir: Path, *, run_id: str, commit_sha: str
) -> list[dict[str, object]]:
    """Inventory final content except self-referential manifest/validation anchors."""
    inventory: list[dict[str, object]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name in {
            "evidence_run_manifest.json",
            "consistency_validation.json",
        }:
            continue
        schema_version: str | None = None
        if path.suffix == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and isinstance(
                    payload.get("schema_version"), str
                ):
                    schema_version = payload["schema_version"]
            except (OSError, json.JSONDecodeError):
                schema_version = None
        inventory.append(
            {
                "artifact_name": path.name,
                "relative_path": path.relative_to(output_dir).as_posix(),
                "schema_version": schema_version,
                "byte_count": path.stat().st_size,
                "sha256": _sha256(path),
                "evidence_run_id": run_id,
                "repository_commit_sha": commit_sha,
                "required": True,
            }
        )
    return inventory


def _prepare_destination(paths: EvidencePaths, run_id: str) -> None:
    if not paths.output_dir.exists():
        return
    if not paths.output_dir.is_dir():
        raise OutputDirectoryNotEmptyError("Evidence output path is not a directory")
    manifest_path = paths.output_dir / "evidence_run_manifest.json"
    if manifest_path.is_file():
        try:
            if (
                json.loads(manifest_path.read_text(encoding="utf-8")).get(
                    "evidence_run_id"
                )
                == run_id
            ):
                raise DuplicateEvidenceRunIdError(
                    f"Evidence run ID already exists: {run_id}"
                )
        except json.JSONDecodeError:
            pass
    if any(paths.output_dir.iterdir()) and not paths.replace_output:
        raise OutputDirectoryNotEmptyError(
            "Evidence output directory is not empty; use --replace-output to replace it"
        )


def _publish_bundle(
    staging_dir: Path, destination: Path, *, replace_output: bool
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if destination.exists():
        if not replace_output:
            raise OutputDirectoryNotEmptyError("Evidence output directory is not empty")
        backup = destination.with_name(
            f".{destination.name}.previous-{uuid.uuid4().hex}"
        )
        destination.replace(backup)
    try:
        staging_dir.replace(destination)
    except OSError:
        if backup is not None and not destination.exists():
            backup.replace(destination)
        raise
    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)


def _leakage_payload(
    *,
    run_id: str,
    commit_sha: str,
    artifact_snapshot_root: Path,
    log_snapshot_root: Path,
    log_entries: list[dict[str, object]],
    fresh_after: datetime | None,
    log_corpus_scope: str,
    minimum_source: int,
    minimum_editorial: int,
    maximum_per_class: int,
) -> tuple[dict[str, object], tuple[str, ...]]:
    source_canaries, editorial_canaries, examined = extract_canaries(
        artifact_snapshot_root, maximum_per_class=maximum_per_class
    )
    canaries = [*source_canaries, *editorial_canaries]
    matches, log_coverage, fresh_log_seen = scan_logs(
        log_snapshot_root,
        log_entries,
        canaries,
        fresh_after=fresh_after,
        parse_timestamp=lambda value: _parse_log_timestamp(value),
    )
    coverage: dict[str, object] = {
        "artifact_files_examined": examined,
        "reports_sampled": len({item.report_identity for item in canaries}),
        "source_canary_count": len(source_canaries),
        "editorial_canary_count": len(editorial_canaries),
        **log_coverage,
    }
    limitations = (
        [LOG_CORPUS_LIMITATIONS[log_corpus_scope]]
        if log_corpus_scope in LOG_CORPUS_LIMITATIONS
        else []
    )
    incomplete = False
    if len(source_canaries) < minimum_source:
        incomplete = True
        limitations.append("insufficient_source_canaries")
    if len(editorial_canaries) < minimum_editorial:
        incomplete = True
        limitations.append("insufficient_editorial_canaries")
    if int(log_coverage["log_files_scanned"]) == 0:
        incomplete = True
        limitations.append("no_standard_logs")
    if fresh_after is not None and not fresh_log_seen:
        incomplete = True
        limitations.append("no_fresh_standard_log")
    status = "failed" if matches else "incomplete" if incomplete else "passed"
    return (
        {
            "schema_version": "1.0",
            "generated_at": _utc_now(),
            "evidence_run_id": run_id,
            "repository_commit_sha": commit_sha,
            "status": status,
            "passed": status == "passed",
            "fresh_after": fresh_after.isoformat() if fresh_after else None,
            "fresh_log_seen": fresh_log_seen,
            "log_corpus": _log_corpus_provenance(log_corpus_scope),
            "coverage": coverage,
            "canaries": [item.public_metadata() for item in canaries],
            "matches": matches,
            "limitations": limitations,
        },
        tuple(item.normalized_text for item in canaries),
    )


def _parse_log_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (
        parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    )


def _log_corpus_provenance(scope: str) -> dict[str, str]:
    return {
        "operator_declared_scope": scope,
        "scope_attestation": (
            "The collector verifies the snapshotted corpus and content coverage, "
            "not whether the declared workflow scope was actually executed."
        ),
        "repository_provenance": (
            "The repository commit identifies the evidence collector revision; it "
            "does not attest to the producer revision of historical log records."
        ),
    }


def collect(
    paths: EvidencePaths,
    *,
    command_args: tuple[str, ...] = (),
    _after_snapshot: Callable[[dict[str, Path]], None] | None = None,
) -> list[Path]:
    """Create one staged, immutable, internally consistent CTO evidence bundle."""
    if paths.minimum_source_canaries < 1 or paths.minimum_editorial_canaries < 1:
        raise EvidenceCoverageError("Minimum canary controls must be positive")
    if paths.maximum_canaries_per_class < max(
        paths.minimum_source_canaries, paths.minimum_editorial_canaries
    ):
        raise EvidenceCoverageError(
            "Maximum canaries cannot be below a required minimum"
        )
    if paths.log_corpus_scope not in LOG_CORPUS_SCOPES:
        raise LogCorpusScopeError(
            "log_corpus_scope must be one of: " + ", ".join(sorted(LOG_CORPUS_SCOPES))
        )
    run_id = paths.evidence_run_id or uuid.uuid4().hex
    _prepare_destination(paths, run_id)
    repository, fresh_after = _repository_provenance(paths)
    started_at_dt = datetime.now(UTC)
    if fresh_after is not None and started_at_dt < fresh_after:
        raise EvidenceFreshnessError(
            "Evidence run start is before the requested freshness threshold"
        )
    started_at = started_at_dt.isoformat()
    workspace = Path(
        tempfile.mkdtemp(prefix="cto_evidence_", dir=paths.workspace_parent)
    )
    staging_parent = Path(
        tempfile.mkdtemp(prefix="cto_evidence_stage_", dir=paths.output_dir.parent)
    )
    staging_dir = staging_parent / "bundle"
    staging_dir.mkdir()
    snapshots: dict[str, Path] = {}
    entries: list[dict[str, object]] = []
    archive_path: Path | None = None
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
            paths.artifact_dir, workspace, strict=paths.require_exact_head
        )
        log_snapshot_root, log_entries = _snapshot_standard_logs(
            paths.log_dir, workspace, strict=paths.require_exact_head
        )
        if _after_snapshot is not None:
            _after_snapshot(dict(snapshots))
        _validate_snapshot_integrity(entries, snapshots)
        commit_sha = str(repository["expected_commit_sha"])
        try:
            leakage, forbidden_canaries = _leakage_payload(
                run_id=run_id,
                commit_sha=commit_sha,
                artifact_snapshot_root=artifact_snapshot_root,
                log_snapshot_root=log_snapshot_root,
                log_entries=log_entries,
                fresh_after=fresh_after,
                log_corpus_scope=paths.log_corpus_scope,
                minimum_source=paths.minimum_source_canaries,
                minimum_editorial=paths.minimum_editorial_canaries,
                maximum_per_class=paths.maximum_canaries_per_class,
            )
        except ValueError as exc:
            raise RetainedArtifactEvidenceError(
                "A retained report artifact required for canary assessment is unreadable"
            ) from exc
        snapshot_manifest_path = _write_json(
            staging_dir / "snapshot_manifest.json",
            {
                "schema_version": "1.0",
                "generated_at": _utc_now(),
                "evidence_run_id": run_id,
                "repository_commit_sha": commit_sha,
                "snapshots": entries,
                "artifact_snapshots": artifact_entries,
                "log_snapshots": log_entries,
            },
        )
        metrics = _metric_rows(snapshots, artifact_snapshot_root)
        csv_paths = [
            _write_csv(staging_dir / name, rows) for name, rows in metrics.items()
        ]
        detailed_path = _write_json(
            staging_dir / "detailed_metrics.json",
            {
                "schema_version": "1.0",
                "generated_at": _utc_now(),
                "evidence_run_id": run_id,
                "repository_commit_sha": commit_sha,
                "metrics": metrics,
            },
        )
        leakage_path = _write_json(staging_dir / "log_content_leakage.json", leakage)
        summary_artifacts = [
            path.name
            for path in [
                *csv_paths,
                detailed_path,
                snapshot_manifest_path,
                leakage_path,
            ]
        ]
        _write_json(
            staging_dir / "executive_summary.json",
            _executive_summary(
                detailed_path,
                run_id=run_id,
                commit_sha=commit_sha,
                artifact_names=summary_artifacts,
            ),
        )
        _finalize_repository_provenance(paths, repository)
        configuration = {
            "state_dir": _public_path(paths.state_dir, paths.state_dir),
            "artifact_dir": _public_path(paths.artifact_dir, ROOT),
            "log_dir": _public_path(paths.log_dir, ROOT),
            "required_databases": sorted(paths.required_databases),
            "minimum_source_canaries": paths.minimum_source_canaries,
            "minimum_editorial_canaries": paths.minimum_editorial_canaries,
            "maximum_canaries_per_class": paths.maximum_canaries_per_class,
        }
        manifest_path = _write_json(
            staging_dir / "evidence_run_manifest.json",
            {
                "schema_version": "1.0",
                "generated_at": _utc_now(),
                "evidence_run_id": run_id,
                "repository_commit_sha": commit_sha,
                "collector_version": COLLECTOR_VERSION,
                "repository": repository,
                "started_at": started_at,
                "ended_at": _utc_now(),
                "fresh_after": fresh_after.isoformat() if fresh_after else None,
                "log_corpus": _log_corpus_provenance(paths.log_corpus_scope),
                "configuration": configuration,
                "configuration_hash": hashlib.sha256(
                    json.dumps(configuration, sort_keys=True).encode("utf-8")
                ).hexdigest(),
                "snapshot_manifest_sha256": _sha256(snapshot_manifest_path),
                "command_args": list(command_args),
                "python_version": sys.version,
                "operating_system": platform.platform(),
                "artifact_inventory": _artifact_inventory(
                    staging_dir, run_id=run_id, commit_sha=commit_sha
                ),
            },
        )
        validate_consistency(
            staging_dir,
            expected_run_id=run_id,
            strict=paths.require_exact_head,
            forbidden_canaries=forbidden_canaries,
            require_validation=False,
        )
        validation_status = str(leakage["status"])
        _write_json(
            staging_dir / "consistency_validation.json",
            {
                "schema_version": "1.0",
                "generated_at": _utc_now(),
                "evidence_run_id": run_id,
                "repository_commit_sha": commit_sha,
                "passed": validation_status == "passed"
                and bool(repository["exact_head_verified"]),
                "status": "passed"
                if validation_status == "passed"
                and bool(repository["exact_head_verified"])
                else validation_status,
                "exact_head_verified": bool(repository["exact_head_verified"]),
                "run_manifest_sha256": _sha256(manifest_path),
                "cost_tolerance_usd": _render_decimal(COST_TOLERANCE),
                "checks": {
                    "exact_head": "passed"
                    if repository["exact_head_verified"]
                    else "not_required",
                    "snapshot_integrity": "passed",
                    "artifact_hashes": "passed",
                    "log_freshness": "passed"
                    if not fresh_after or leakage["fresh_log_seen"]
                    else "failed",
                    "source_canary_coverage": "passed"
                    if leakage["coverage"]["source_canary_count"]
                    >= paths.minimum_source_canaries
                    else "failed",
                    "editorial_canary_coverage": "passed"
                    if leakage["coverage"]["editorial_canary_count"]
                    >= paths.minimum_editorial_canaries
                    else "failed",
                    "log_content_leakage": validation_status,
                    "summary_consistency": "passed",
                },
            },
        )
        if paths.require_exact_head and validation_status != "passed":
            if validation_status == "failed":
                raise LogContentLeakageError(
                    "CTO evidence found retained content in standard logs"
                )
            raise EvidenceCoverageError("CTO evidence lacks required leakage coverage")
        if paths.archive_path is not None:
            archive_path = _archive_evidence_bundle(staging_dir, paths.archive_path)
        _publish_bundle(
            staging_dir, paths.output_dir, replace_output=paths.replace_output
        )
        published = sorted(paths.output_dir.iterdir())
        return [*published, *([archive_path] if archive_path is not None else [])]
    finally:
        shutil.rmtree(staging_parent, ignore_errors=True)
        if not paths.debug_retain_snapshots:
            shutil.rmtree(workspace, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", default="state")
    parser.add_argument("--artifact-dir", default="out")
    parser.add_argument("--log-dir", default="logs")
    parser.add_argument("--output-dir", default="out/cto-review-evidence")
    parser.add_argument("--archive-path", default="docs/cto-review-evidence.zip")
    parser.add_argument("--debug-retain-snapshots", action="store_true")
    parser.add_argument("--require-exact-head", action="store_true")
    parser.add_argument("--expected-commit-sha", default="")
    parser.add_argument("--fresh-after", default="")
    parser.add_argument(
        "--log-corpus-scope",
        choices=sorted(LOG_CORPUS_SCOPES),
        default="not_declared",
        help="Operator-declared scope of the snapshotted standard log corpus.",
    )
    parser.add_argument("--minimum-source-canaries", type=int, default=5)
    parser.add_argument("--minimum-editorial-canaries", type=int, default=5)
    parser.add_argument("--maximum-canaries-per-class", type=int, default=25)
    parser.add_argument("--replace-output", action="store_true")
    args = parser.parse_args()
    for path in collect(
        EvidencePaths(
            Path(args.state_dir),
            Path(args.artifact_dir),
            Path(args.output_dir),
            log_dir=Path(args.log_dir),
            debug_retain_snapshots=args.debug_retain_snapshots,
            archive_path=Path(args.archive_path),
            require_exact_head=args.require_exact_head,
            expected_commit_sha=args.expected_commit_sha or None,
            fresh_after=args.fresh_after or None,
            log_corpus_scope=args.log_corpus_scope,
            minimum_source_canaries=args.minimum_source_canaries,
            minimum_editorial_canaries=args.minimum_editorial_canaries,
            maximum_canaries_per_class=args.maximum_canaries_per_class,
            replace_output=args.replace_output,
        ),
        command_args=tuple(sys.argv[1:]),
    ):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
