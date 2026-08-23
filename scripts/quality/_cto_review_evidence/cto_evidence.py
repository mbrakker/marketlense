"""Generate bounded CTO evidence artifacts from repository and snapshot inputs."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from collections import Counter, defaultdict
from dataclasses import MISSING, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from src.contracts._report_store.metadata import (
    SourceIdentityObservation,
    SourceIdentityResolution,
)
from src.contracts.public_editorial_quality import (
    PUBLIC_EDITORIAL_QUALITY_SCHEMA_VERSION,
    PUBLIC_EDITORIAL_VALIDATOR_VERSION,
)
from src.generators.public_editorial_quality_generator import (
    ADVISORY_RULE_IDS,
    BLOCKING_RULE_IDS,
)

SCHEMA_VERSION = "1.0"
_LINEAGE_REQUIRED_COLUMNS = (
    "artifact_id",
    "artifact_kind",
    "report_id",
    "source_id",
    "content_hash",
    "storage_ref",
    "producer",
    "schema_version_used",
    "processing_version",
    "validation_status",
    "lineage_status",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return payload


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
    )


def _table_columns(path: Path | None, table: str) -> set[str]:
    if path is None or not path.exists():
        return set()
    db = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        if not _table_exists(db, table):
            return set()
        return {str(row[1]) for row in db.execute(f"PRAGMA table_info({table})")}
    finally:
        db.close()


def _rows(path: Path | None, table: str) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    db = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        db.row_factory = sqlite3.Row
        if not _table_exists(db, table):
            return []
        return [dict(row) for row in db.execute(f"SELECT * FROM {table}")]
    finally:
        db.close()


def _json_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _json_mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list_with_validity(value: object) -> tuple[list[str], bool]:
    """Read a persisted call-category array without treating corruption as empty.

    The production execution-plan writer persists canonical JSON arrays.  Older
    rows are read defensively here because evidence must distinguish a valid
    historical "no calls" record from unavailable reconciliation evidence.
    """
    if isinstance(value, list):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [], False
    else:
        return [], False
    if not isinstance(parsed, list):
        return [], False
    normalized: list[str] = []
    for item in parsed:
        if not isinstance(item, str) or not item.strip():
            return [], False
        token = item.strip()
        if token not in normalized:
            normalized.append(token)
    return sorted(normalized), True


def _execution_plan_reconciliation_status(plan: dict[str, Any]) -> str:
    """Return the canonical result, or fail closed for incomplete old rows.

    ``record_minimal_execution_plan_result`` intentionally writes a populated
    reconciliation object for *both* matched and divergent executions.  Its
    ``reconciliation_status`` is therefore authoritative whenever present.
    Rows predating that field use the same set-based unplanned-work rule as the
    writer: avoided planned work remains a match; only unplanned stages, calls,
    or side effects diverge.
    """
    raw_divergence = plan.get("divergence_json")
    declared = _json_mapping(raw_divergence)
    raw_status = str(declared.get("reconciliation_status") or "").strip().lower()
    if raw_status in {"matched", "diverged"}:
        return raw_status
    if raw_status:
        return "unreconciled"

    comparisons = (
        ("planned_stages_json", "actual_stages_json"),
        ("planned_external_calls_json", "actual_external_calls_json"),
        ("planned_side_effects_json", "actual_side_effects_json"),
    )
    for planned_key, actual_key in comparisons:
        planned, planned_valid = _json_list_with_validity(plan.get(planned_key))
        actual, actual_valid = _json_list_with_validity(plan.get(actual_key))
        if not planned_valid or not actual_valid:
            return "unreconciled"
        if set(actual) - set(planned):
            return "diverged"
    return "matched"


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 6)


def _status_counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "unknown") for row in rows).items()))


def _report_host(row: dict[str, Any]) -> str:
    for key in ("source_url", "normalized_url", "resolved_target_url"):
        value = str(row.get(key) or "").strip()
        if value:
            host = urlsplit(value).netloc.casefold()
            if host:
                return host
    return "unattributed"


def _parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def _ages_seconds(rows: list[dict[str, Any]], key: str) -> list[float]:
    now = datetime.now(UTC)
    return [
        round((now - timestamp).total_seconds(), 3)
        for row in rows
        if (timestamp := _parse_timestamp(row.get(key))) is not None
    ]


def _nested_evidence_counts(value: object) -> Counter[str]:
    counts: Counter[str] = Counter()
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold()
            if "screenshot" in normalized:
                counts["screenshots"] += 1
            if "page_load" in normalized or "page_info" in normalized:
                counts["page_loads"] += 1
            counts.update(_nested_evidence_counts(child))
    elif isinstance(value, list):
        for child in value:
            counts.update(_nested_evidence_counts(child))
    return counts


def _metric(
    status: str,
    source: str,
    values: dict[str, object],
    *limitations: str,
) -> dict[str, object]:
    return {
        "status": status,
        "source": source,
        "values": values,
        "limitations": list(limitations),
    }


def artifact_lineage_completeness(snapshot: Path | None) -> dict[str, object]:
    columns = _table_columns(snapshot, "artifact_lineage_records")
    missing_columns = sorted(set(_LINEAGE_REQUIRED_COLUMNS) - columns)
    if missing_columns:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "unavailable",
            "definition": "A complete lineage record has all required canonical fields and verified lineage status.",
            "missing_columns": missing_columns,
            "families": [],
        }
    states = {
        str(row.get("artifact_id") or ""): str(row.get("state") or "")
        for row in _rows(snapshot, "artifact_lineage_states")
    }
    families: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "artifact_count": 0,
            "active_count": 0,
            "superseded_count": 0,
            "complete_active_count": 0,
            "complete_history_count": 0,
            "missing_field_counts": Counter(),
            "processing_version_distribution": Counter(),
            "schema_version_distribution": Counter(),
        }
    )
    for row in _rows(snapshot, "artifact_lineage_records"):
        family = str(row.get("artifact_kind") or "unknown")
        entry = families[family]
        entry["artifact_count"] += 1
        state = states.get(str(row.get("artifact_id") or ""), "")
        if state == "active":
            entry["active_count"] += 1
        if state == "superseded":
            entry["superseded_count"] += 1
        entry["processing_version_distribution"][
            str(row.get("processing_version") or "missing")
        ] += 1
        entry["schema_version_distribution"][
            str(row.get("schema_version_used") or "missing")
        ] += 1
        missing = [
            key
            for key in _LINEAGE_REQUIRED_COLUMNS
            if not str(row.get(key) or "").strip()
        ]
        if str(row.get("lineage_status") or "") != "complete":
            missing.append("lineage_status_not_complete")
        for field_name in missing:
            entry["missing_field_counts"][field_name] += 1
        complete = not missing
        if complete:
            entry["complete_history_count"] += 1
            if state == "active":
                entry["complete_active_count"] += 1
    rows = [
        {
            "artifact_family": name,
            "artifact_count": counts["artifact_count"],
            "active_count": counts["active_count"],
            "superseded_count": counts["superseded_count"],
            "complete_active_count": counts["complete_active_count"],
            "complete_history_count": counts["complete_history_count"],
            "active_completeness_percentage": round(
                100 * _ratio(counts["complete_active_count"], counts["active_count"]),
                4,
            )
            if counts["active_count"]
            else 0.0,
            "all_history_completeness_percentage": round(
                100
                * _ratio(counts["complete_history_count"], counts["artifact_count"]),
                4,
            )
            if counts["artifact_count"]
            else 0.0,
            "missing_field_counts": dict(
                sorted(counts["missing_field_counts"].items())
            ),
            "processing_version_distribution": dict(
                sorted(counts["processing_version_distribution"].items())
            ),
            "schema_version_distribution": dict(
                sorted(counts["schema_version_distribution"].items())
            ),
        }
        for name, counts in sorted(families.items())
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "available" if rows else "empty",
        "definition": "Completeness is reported separately for active and all-history records; planner-safe rows require all canonical fields and lineage_status=complete.",
        "families": rows,
    }


def _workflow_remediation_coverage(root: Path) -> dict[str, object]:
    source = root / "docs/ops/remediation_workflow_coverage.yaml"
    payload = _read_yaml(source)
    workflows = payload.get("workflows")
    if not isinstance(workflows, list):
        raise ValueError("Remediation coverage inventory has no workflows")
    rows: list[dict[str, object]] = []
    for raw in workflows:
        if not isinstance(raw, dict):
            continue
        workflow = str(raw.get("workflow") or "").strip()
        module = str(raw.get("module") or "").strip()
        coverage = str(raw.get("coverage") or "").strip()
        module_path = root / module
        has_hook = (
            module_path.is_file()
            and "record_workflow_failure" in module_path.read_text(encoding="utf-8")
        )
        rows.append(
            {
                "workflow": workflow,
                "entrypoint": module,
                "coverage": coverage,
                "reason": str(raw.get("reason") or "").strip(),
                "ledger_hook_verified": has_hook if coverage == "covered" else None,
                "verification_status": (
                    "passed" if coverage != "covered" or has_hook else "failed"
                ),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "docs/ops/remediation_workflow_coverage.yaml",
        "workflow_count": len(rows),
        "covered_count": sum(row["coverage"] == "covered" for row in rows),
        "exempt_count": sum(row["coverage"] == "exempt" for row in rows),
        "workflows": sorted(rows, key=lambda row: str(row["workflow"])),
    }


def _architecture_manifest(root: Path, commit_sha: str) -> dict[str, object]:
    policy_path = root / "docs/quality/architecture_policy.yaml"
    policy = _read_yaml(policy_path)
    roles = policy.get("roles") if isinstance(policy.get("roles"), dict) else {}
    external = (
        policy.get("external_system_ownership")
        if isinstance(policy.get("external_system_ownership"), dict)
        else {}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "repository_commit_sha": commit_sha,
        "architecture_policy_schema_version": str(policy.get("schema_version") or ""),
        "source_inputs": [
            {
                "path": "docs/quality/architecture_policy.yaml",
                "sha256": _sha256(policy_path),
            }
        ],
        "roles": dict(sorted((str(key), str(value)) for key, value in roles.items())),
        "external_system_ownership": {
            str(name): {
                "canonical_entrypoint": str(details.get("canonical_entrypoint") or ""),
                "private_roots": list(details.get("private_roots") or []),
            }
            for name, details in sorted(external.items())
            if isinstance(details, dict)
        },
    }


def _contract_fields(contract: type[object]) -> list[dict[str, object]]:
    return [
        {
            "name": item.name,
            "type": str(item.type),
            "required": item.default is MISSING and item.default_factory is MISSING,
            "description": str(item.metadata.get("doc") or ""),
        }
        for item in fields(contract)
    ]


def _source_identity_schema() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_schema_version": "1.0",
        "observation_contract": {
            "name": "SourceIdentityObservation",
            "fields": _contract_fields(SourceIdentityObservation),
        },
        "resolution_contract": {
            "name": "SourceIdentityResolution",
            "fields": _contract_fields(SourceIdentityResolution),
        },
        "resolution_policy": {
            "implementation": "src/services/_report_store_service/metadata.py",
            "selection_order": [
                "publication_date_status",
                "identity_confidence",
                "title_evidence_locator_present",
                "canonical_landing_page_url_present",
                "resolution_method",
                "canonical_title",
                "publisher_name",
                "content_hash",
            ],
            "conflict_behavior": "Conflicting publication dates clear the resolved date and set identity_status to conflicting.",
            "legacy_behavior": "A legacy report-source record is retained as legacy_unverified rather than promoted to resolved identity.",
        },
    }


def _editorial_rule_catalog() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "validator_version": PUBLIC_EDITORIAL_VALIDATOR_VERSION,
        "contract_schema_version": PUBLIC_EDITORIAL_QUALITY_SCHEMA_VERSION,
        "implementation": "src/generators/public_editorial_quality_generator.py",
        "rules": [
            {
                "rule_id": rule_id,
                "severity": "error",
                "kind": "blocking",
                "waivable_via": "ingest.validation.public_editorial_quality.disabled_rule_waivers",
            }
            for rule_id in sorted(BLOCKING_RULE_IDS)
        ]
        + [
            {
                "rule_id": rule_id,
                "severity": "warning",
                "kind": "advisory_measurement",
                "waivable_via": None,
            }
            for rule_id in sorted(ADVISORY_RULE_IDS)
        ],
    }


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        prior = merged.get(key)
        merged[key] = (
            _deep_merge(prior, value)
            if isinstance(prior, dict) and isinstance(value, dict)
            else value
        )
    return merged


def _effective_run_profiles(root: Path) -> dict[str, object]:
    config_path = root / "src/config/app.yaml"
    data = _read_yaml(config_path)
    profile = os.environ.get("MARKET_LENSE_CONFIG_PROFILE", "").strip()
    overlays: list[str] = []
    for candidate in (
        config_path.with_name(f"app.{profile}.yaml") if profile else None,
        config_path.with_name("app.local.yaml"),
    ):
        if candidate is not None and candidate.is_file():
            data = _deep_merge(data, _read_yaml(candidate))
            overlays.append(candidate.relative_to(root).as_posix())
    control = data.get("workflow_control")
    control = control if isinstance(control, dict) else {}
    profiles = control.get("preflight_profiles")
    profiles = profiles if isinstance(profiles, dict) else {}
    rows = []
    for name, raw in sorted(profiles.items()):
        item = raw if isinstance(raw, dict) else {}
        rows.append(
            {
                "profile": str(name),
                "workflow": str(item.get("workflow") or name),
                "planned_side_effects": list(item.get("planned_side_effects") or []),
                "requires": {
                    "llm": bool(item.get("require_llm", False)),
                    "drive": bool(item.get("require_drive", False)),
                    "publish": bool(item.get("require_publish", False)),
                    "browser": bool(item.get("require_browser", False)),
                },
                "prompt_namespaces": list(item.get("prompt_namespaces") or []),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "configuration_path": "src/config/app.yaml",
        "requested_profile": profile or None,
        "applied_overlays": overlays,
        "profiles": rows,
    }


def _github_repository_slug(root: Path) -> str | None:
    try:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    for marker in ("github.com/", "github.com:"):
        if marker in remote:
            slug = remote.split(marker, maxsplit=1)[1].removesuffix(".git")
            return slug if "/" in slug else None
    return None


def github_main_status(
    root: Path, *, include: bool, tested_commit_sha: str = ""
) -> dict[str, object]:
    if not include:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "unavailable",
            "reason": "github_status_not_requested",
        }
    slug = _github_repository_slug(root)
    if not slug:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "unavailable",
            "reason": "github_origin_not_configured",
        }
    try:
        main_commit = json.loads(
            subprocess.run(
                ["gh", "api", "--method", "GET", f"repos/{slug}/commits/main"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
        main_sha = str(main_commit.get("sha") or "")
        sha = tested_commit_sha or main_sha
        if not sha:
            raise ValueError("GitHub returned no commit SHA")
        checks = json.loads(
            subprocess.run(
                [
                    "gh",
                    "api",
                    "--method",
                    "GET",
                    f"repos/{slug}/commits/{sha}/check-runs?per_page=100",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
        pull_requests = json.loads(
            subprocess.run(
                [
                    "gh",
                    "api",
                    "--method",
                    "GET",
                    f"repos/{slug}/commits/{sha}/pulls",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return {
            "schema_version": SCHEMA_VERSION,
            "repository": slug,
            "status": "unavailable",
            "reason": "github_api_unavailable",
        }
    runs = checks.get("check_runs") if isinstance(checks, dict) else []
    runs = runs if isinstance(runs, list) else []
    states = Counter(
        str(row.get("status") or "unknown") for row in runs if isinstance(row, dict)
    )
    conclusions = Counter(
        str(row.get("conclusion") or "pending") for row in runs if isinstance(row, dict)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "available",
        "repository": slug,
        "tested_commit_sha": sha,
        "main_commit_sha": main_sha,
        "revision_match": bool(not tested_commit_sha or main_sha == tested_commit_sha),
        "check_runs": {
            "total": len(runs),
            "status_counts": dict(sorted(states.items())),
            "conclusion_counts": dict(sorted(conclusions.items())),
            "failed_count": sum(
                conclusions.get(value, 0)
                for value in ("failure", "cancelled", "timed_out", "action_required")
            ),
            "pending_count": sum(
                states.get(value, 0) for value in ("queued", "in_progress")
            ),
        },
        "associated_pull_requests": [
            {
                "number": int(row.get("number") or 0),
                "state": str(row.get("state") or ""),
                "merged_at": row.get("merged_at"),
                "url": str(row.get("html_url") or ""),
            }
            for row in pull_requests
            if isinstance(row, dict)
        ],
    }


def _runtime_telemetry(
    snapshots: dict[str, Path], artifact_dir: Path
) -> dict[str, object]:
    reports = snapshots.get("reports")
    usage = snapshots.get("llm_usage")
    state = snapshots.get("index")
    acquisition_resources = _rows(reports, "acquisition_attempt_resources")
    llm_events = _rows(usage, "llm_usage_events")
    plans = _rows(reports, "artifact_execution_plan_runs")
    remediation = _rows(state, "remediation_records")
    transitions = _rows(state, "remediation_transitions")
    deferred = _rows(usage, "budget_authority_deferred_work")
    queue = _rows(reports, "vector_projection_queue")
    queue_transitions = _rows(reports, "claim_embedding_queue_transitions")
    observations = _rows(state, "workflow_control_observations")

    acquisition: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"route_records": 0, "attempt_count": 0, "success_count": 0}
    )
    for resource in acquisition_resources:
        key = (
            str(resource.get("publisher_id") or "unattributed"),
            str(resource.get("route_family") or "unknown"),
        )
        entry = acquisition[key]
        entry["route_records"] += 1
        entry["attempt_count"] += 1
        entry["success_count"] += int(
            str(resource.get("terminal_outcome") or "").casefold() == "success"
        )
    acquisition_rows = [
        {
            "publisher": publisher,
            "route_family": family,
            **values,
            "successful_acquisition_rate": _ratio(
                values["success_count"], values["attempt_count"]
            ),
        }
        for (publisher, family), values in sorted(acquisition.items())
    ]

    browser_values = {
        "acquired_report_count": sum(
            values["success_count"] for values in acquisition.values()
        ),
        "browser_sessions": sum(
            int(row.get("browser_launches") or 0)
            for row in acquisition_resources
        ),
        "browser_steps": sum(
            int(row.get("browser_steps") or 0) for row in acquisition_resources
        ),
        "page_loads": sum(
            int(row.get("page_navigations") or 0) for row in acquisition_resources
        ),
        "screenshots": sum(
            int(row.get("screenshots") or 0) for row in acquisition_resources
        ),
        "duration_seconds": sum(
            int(row.get("elapsed_ms") or 0) / 1000
            for row in acquisition_resources
        ),
    }

    llm_scopes: dict[tuple[str, str, str], dict[str, object]] = defaultdict(
        lambda: {"call_count": 0, "estimated_cost_usd": 0.0}
    )
    ocr_events: list[dict[str, Any]] = []
    crop_qa_calls = 0
    for event in llm_events:
        scope = (
            str(event.get("action") or ""),
            str(event.get("semantic_task") or ""),
            str(event.get("prompt_namespace") or ""),
        )
        entry = llm_scopes[scope]
        entry["call_count"] = int(entry["call_count"]) + 1
        entry["estimated_cost_usd"] = round(
            float(entry["estimated_cost_usd"])
            + float(event.get("estimated_cost_usd") or 0),
            6,
        )
        search = " ".join(scope).casefold()
        if "ocr" in search:
            ocr_events.append(event)
        if "crop" in search and ("qa" in search or "vision" in search):
            crop_qa_calls += 1
    scope_rows = [
        {
            "action": key[0],
            "semantic_task": key[1],
            "prompt_namespace": key[2],
            **values,
        }
        for key, values in sorted(llm_scopes.items())
    ]

    crop_candidates = 0
    crop_accepted = 0
    crop_files = 0
    for path in sorted(artifact_dir.rglob("crop_refine.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        results = payload.get("results") if isinstance(payload, dict) else []
        if not isinstance(results, list):
            continue
        crop_files += 1
        crop_candidates += len(results)
        crop_accepted += sum(
            bool(item.get("is_valid_candidate"))
            for item in results
            if isinstance(item, dict)
        )

    divergence: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {
            "plan_count": 0,
            "matching_plan_count": 0,
            "divergent_plan_count": 0,
            "unreconciled_plan_count": 0,
            "enforcement_deferred_or_blocked_count": 0,
            "planned_call_count": 0,
            "actual_call_count": 0,
        }
    )
    for plan in plans:
        key = (
            str(plan.get("execution_intent") or "unknown"),
            str(plan.get("execution_mode") or "unknown"),
        )
        entry = divergence[key]
        planned, planned_valid = _json_list_with_validity(
            plan.get("planned_external_calls_json")
        )
        actual, actual_valid = _json_list_with_validity(
            plan.get("actual_external_calls_json")
        )
        status = _execution_plan_reconciliation_status(plan)
        entry["plan_count"] += 1
        entry[
            {
                "matched": "matching_plan_count",
                "diverged": "divergent_plan_count",
                "unreconciled": "unreconciled_plan_count",
            }[status]
        ] += 1
        if str(plan.get("execution_status") or "").strip().lower() in {
            "blocked",
            "deferred",
        }:
            entry["enforcement_deferred_or_blocked_count"] += 1
        if planned_valid:
            entry["planned_call_count"] += len(planned)
        if actual_valid:
            entry["actual_call_count"] += len(actual)

    deferred_ages = _ages_seconds(deferred, "deferred_at_utc")
    remediation_transition_counts = Counter(
        str(row.get("remediation_id") or "") for row in transitions
    )
    queued_ages = _ages_seconds(
        [row for row in queue if str(row.get("embedding_status") or "") != "embedded"],
        "created_at_utc",
    )
    publication_rows = [
        row
        for row in observations
        if "publish" in str(row.get("workflow") or "").casefold()
        or "wordpress" in str(row.get("step_name") or "").casefold()
    ]
    successful_publications = sum(
        str(row.get("outcome") or "").casefold()
        in {"success", "completed", "published"}
        for row in publication_rows
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "acquisition_by_publisher_and_route": _metric(
            "available" if acquisition_rows else "empty",
            "reports.acquisition_attempt_resources",
            {"rows": acquisition_rows},
        ),
        "browser_per_acquired_report": _metric(
            "available" if acquisition_resources else "empty",
            "reports.acquisition_attempt_resources",
            browser_values,
        ),
        "cost_per_acquired_and_published_report": _metric(
            "partial" if plans or publication_rows else "unavailable",
            "reports.artifact_execution_plan_runs; index.workflow_control_observations",
            {
                "execution_plan_cost_usd": round(
                    sum(float(row.get("actual_cost_usd") or 0) for row in plans), 6
                ),
                "published_workflow_observation_count": len(publication_rows),
                "successful_publication_observation_count": successful_publications,
            },
            "The retained ledger does not associate a complete cost total with one acquired or published report across all providers and side effects.",
        ),
        "cost_by_llm_scope_and_artifact_family": _metric(
            "partial" if scope_rows else "empty",
            "llm_usage.llm_usage_events; reports.artifact_execution_plan_runs",
            {
                "llm_scopes": scope_rows,
                "execution_plan_cost_usd": round(
                    sum(float(row.get("actual_cost_usd") or 0) for row in plans), 6
                ),
            },
            "LLM events do not retain an artifact-family identifier, so a cost allocation by family is not asserted.",
        ),
        "cache_and_reuse_by_artifact_family": _metric(
            "partial" if plans else "unavailable",
            "reports.artifact_execution_plan_runs; reports.artifact_lineage_records",
            {
                "plan_count": len(plans),
                "planned_reusable_artifact_count": sum(
                    len(_json_list(row.get("reusable_artifact_ids_json")))
                    for row in plans
                ),
            },
            "The retained plan audit records reusable artifacts but not cache lookup hit/miss decisions by family.",
        ),
        "ocr_incidence_and_success": _metric(
            "available" if llm_events else "empty",
            "llm_usage.llm_usage_events",
            {
                "ocr_call_count": len(ocr_events),
                "ocr_incidence_among_llm_calls": _ratio(
                    len(ocr_events), len(llm_events)
                ),
                "ocr_success_rate": _ratio(
                    sum(
                        str(row.get("provider_call_status") or "").casefold()
                        == "completed"
                        for row in ocr_events
                    ),
                    len(ocr_events),
                ),
            },
        ),
        "crop_qa": _metric(
            "partial" if crop_files or crop_qa_calls else "empty",
            "retained crop_refine.json; llm_usage.llm_usage_events",
            {
                "crop_refinement_file_count": crop_files,
                "crop_candidate_count": crop_candidates,
                "crop_qa_call_count": crop_qa_calls,
                "accepted_candidate_count": crop_accepted,
                "acceptance_rate": _ratio(crop_accepted, crop_candidates),
            },
            "Crop cache sidecars identify retained results but do not record whether a request was a cache hit, so reuse rate is unavailable.",
        ),
        "minimal_plan_actual_call_divergence": _metric(
            "available" if divergence else "empty",
            "reports.artifact_execution_plan_runs",
            {
                "rows": [
                    {"execution_intent": key[0], "execution_mode": key[1], **values}
                    for key, values in sorted(divergence.items())
                ]
            },
        ),
        "deferred_work_age_and_completion": _metric(
            "available" if deferred else "empty",
            "llm_usage.budget_authority_deferred_work",
            {
                "status_counts": _status_counts(deferred, "status"),
                "mean_age_seconds": round(sum(deferred_ages) / len(deferred_ages), 3)
                if deferred_ages
                else None,
                "completion_rate": _ratio(
                    sum(
                        bool(str(row.get("completed_at_utc") or "").strip())
                        for row in deferred
                    ),
                    len(deferred),
                ),
            },
        ),
        "remediation_outcomes": _metric(
            "available" if remediation else "empty",
            "index.remediation_records; index.remediation_transitions",
            {
                "status_counts": _status_counts(remediation, "status"),
                "success_rate": _ratio(
                    sum(
                        str(row.get("status") or "") == "resolved"
                        for row in remediation
                    ),
                    len(remediation),
                ),
                "human_intervention_rate": _ratio(
                    sum(
                        str(row.get("status") or "") == "operator_action_required"
                        for row in remediation
                    ),
                    len(remediation),
                ),
                "recurrence_rate": _ratio(
                    sum(
                        remediation_transition_counts.get(
                            str(row.get("remediation_id") or ""), 0
                        )
                        > 1
                        for row in remediation
                    ),
                    len(remediation),
                ),
            },
        ),
        "embedding_queue_and_avoided_reembedding": _metric(
            "partial" if queue or queue_transitions else "empty",
            "reports.vector_projection_queue; reports.claim_embedding_queue_transitions",
            {
                "queue_status_counts": _status_counts(queue, "embedding_status"),
                "mean_open_queue_age_seconds": round(
                    sum(queued_ages) / len(queued_ages), 3
                )
                if queued_ages
                else None,
                "transition_reason_counts": _status_counts(
                    queue_transitions, "reason_code"
                ),
            },
            "The queue proves content-hash-aware admission but does not retain a dedicated avoided-re-embedding counter.",
        ),
        "wordpress_publication": _metric(
            "partial" if publication_rows else "empty",
            "index.workflow_control_observations",
            {
                "observation_count": len(publication_rows),
                "outcome_counts": _status_counts(publication_rows, "outcome"),
                "mean_latency_ms": round(
                    sum(int(row.get("latency_ms") or 0) for row in publication_rows)
                    / len(publication_rows),
                    3,
                )
                if publication_rows
                else None,
                "failure_rate": _ratio(
                    len(publication_rows) - successful_publications,
                    len(publication_rows),
                ),
            },
            "Duplicate and rollback outcomes are not distinguished in the retained workflow observation schema.",
        ),
        "human_editorial_quality_ratings": _metric(
            "unavailable",
            "operator-maintained blinded review corpus",
            {},
            "No completed, retained human-rating corpus is present in the canonical runtime stores.",
        ),
        "public_page_performance_and_errors": _metric(
            "unavailable",
            "hosted public-page observability",
            {},
            "Hosted public-page performance and visitor-facing error telemetry are not retained in the local evidence stores.",
        ),
    }


def _readme() -> str:
    return """# CTO Evidence\n\nThis directory is generated by `scripts/quality/collect_cto_review_evidence.py`. It is a point-in-time, machine-readable evidence surface; do not edit the files by hand.\n\nRepository artifacts describe the revision that produced the bundle. Runtime telemetry is derived only from immutable SQLite and retained-artifact snapshots. Each metric declares `available`, `partial`, `empty`, or `unavailable`; an unavailable metric is a retention gap, not a zero value.\n\nGenerate a strict review bundle with:\n\n```powershell\n$evidenceHeadSha = git rev-parse HEAD\n$freshAfter = \"<current-run-start-ISO-8601>\"\npython scripts/quality/collect_cto_review_evidence.py --state-dir state --artifact-dir out --log-dir logs --output-dir docs/CTO_evidence --expected-commit-sha $evidenceHeadSha --require-exact-head --fresh-after $freshAfter --log-corpus-scope representative_report_processing --include-github-status --replace-output\n```\n\nThe GitHub status snapshot is intentionally opt-in because it is an external read. It records the tested revision separately from latest `main`, and returns an explicit unavailable status when it cannot be collected.\n"""


def write_cto_evidence(
    *,
    output_dir: Path,
    repository_root: Path,
    snapshots: dict[str, Path],
    artifact_dir: Path,
    repository_commit_sha: str,
    include_github_status: bool,
    tested_commit_sha: str = "",
) -> list[Path]:
    """Write the public CTO artifacts from already-frozen collector inputs."""
    artifacts: dict[str, object] = {
        "workflow_to_remediation_coverage.json": _workflow_remediation_coverage(
            repository_root
        ),
        "artifact_lineage_completeness.json": artifact_lineage_completeness(
            snapshots.get("reports")
        ),
        "architecture_manifest.json": _architecture_manifest(
            repository_root, repository_commit_sha
        ),
        "source_identity_schema.json": _source_identity_schema(),
        "editorial_rule_catalog.json": _editorial_rule_catalog(),
        "effective_run_profile_matrix.json": _effective_run_profiles(repository_root),
        "github_main_status.json": github_main_status(
            repository_root,
            include=include_github_status,
            tested_commit_sha=tested_commit_sha or repository_commit_sha,
        ),
        "runtime_telemetry.json": _runtime_telemetry(snapshots, artifact_dir),
    }
    paths = [
        (output_dir / "README.md"),
        *[output_dir / name for name in artifacts],
    ]
    paths[0].parent.mkdir(parents=True, exist_ok=True)
    paths[0].write_text(_readme(), encoding="utf-8")
    for name, payload in artifacts.items():
        _write_json(output_dir / name, payload)
    return paths
