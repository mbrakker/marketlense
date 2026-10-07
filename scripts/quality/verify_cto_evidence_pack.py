"""Verify committed CTO evidence manifests, bundles, source hashes, and index."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.cto_evidence import (  # noqa: E402
    cto_evidence_bundle_payload,
    parse_cto_evidence_bundle,
    parse_cto_evidence_run,
    validate_cto_evidence_run,
)

RUNS_DIR = Path("docs/CTO_evidence/runs")
INDEX_PATH = Path("docs/CTO_evidence/evidence_index.json")
INVENTORY_PATH = Path("docs/CTO_evidence/evidence_inventory.json")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ABSOLUTE_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\|/(?:home|Users?|tmp|var|srv)/)"
)
_EMAIL_RE = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_URL_RE = re.compile(r"\bhttps?://", re.IGNORECASE)
_SECRET_RE = re.compile(
    r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|Bearer\s+\S+)",
    re.IGNORECASE,
)
_DATABASE_URL_RE = re.compile(r"\b(?:postgres(?:ql)?|mysql|sqlite)://", re.IGNORECASE)
_IDENTITY_KEYS = frozenset(
    {
        "candidate_id",
        "publisher_id",
        "report_id",
        "report_name",
        "report_number",
        "report_title",
        "source_identity_id",
        "url",
    }
)
_CONTENT_KEYS = frozenset(
    {
        "email_body",
        "raw_model_response",
        "raw_report_text",
        "rendered_prompt",
        "source_document_excerpt",
        "source_extract",
    }
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside_root(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve(strict=True)
    if path != ROOT and ROOT not in path.parents:
        raise ValueError("path_resolves_outside_repository")
    return path


def _walk(value: object, path: str = "$") -> Iterator[tuple[str, object]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")
    else:
        yield path, value


def _source_identity_values(source_paths: list[Path]) -> set[str]:
    identities: set[str] = set()
    for path in source_paths:
        try:
            payload = _read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        for field_path, value in _walk(payload):
            key = field_path.rsplit(".", 1)[-1].split("[", 1)[0].casefold()
            if key in _IDENTITY_KEYS and isinstance(value, str) and value:
                identities.add(value)
    return identities


def _privacy_scan(bundle: dict[str, Any], source_paths: list[Path]) -> dict[str, Any]:
    serialized = json.dumps(bundle, ensure_ascii=True, sort_keys=True)
    identity_values = _source_identity_values(source_paths)
    identity_matches = sum(value in serialized for value in identity_values)
    content_fields = [
        field_path
        for field_path, _ in _walk(bundle)
        if field_path.rsplit(".", 1)[-1].split("[", 1)[0].casefold() in _CONTENT_KEYS
    ]
    checks = {
        "absolute_paths": not bool(_ABSOLUTE_PATH_RE.search(serialized)),
        "emails": not bool(_EMAIL_RE.search(serialized)),
        "urls": not bool(_URL_RE.search(serialized)),
        "credentials": not bool(_SECRET_RE.search(serialized)),
        "database_connection_strings": not bool(_DATABASE_URL_RE.search(serialized)),
        "source_identity_values": identity_matches == 0,
        "raw_content_fields": not content_fields,
        "bundle_byte_bound": len(serialized.encode("utf-8")) <= 1_000_000,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "identity_match_count": identity_matches,
        "raw_content_field_count": len(content_fields),
        "bundle_bytes": len(serialized.encode("utf-8")),
    }


def _missing_classes(bundle: dict[str, Any]) -> list[str]:
    missing: set[str] = set()
    limitations = list(bundle.get("limitations") or [])
    run_evidence = bundle.get("run_evidence")
    if isinstance(run_evidence, dict):
        limitations.extend(run_evidence.get("limitations") or [])
    prefix = "Required evidence class "
    suffix = " is unavailable from retained authoritative sources."
    for limitation in limitations:
        if isinstance(limitation, str) and limitation.startswith(prefix):
            value = limitation[len(prefix) :]
            if value.endswith(suffix):
                missing.add(value[: -len(suffix)])
    return sorted(missing)


def _criteria(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    run_evidence = bundle.get("run_evidence")
    if not isinstance(run_evidence, dict):
        return []
    criteria = run_evidence.get("criteria")
    if not isinstance(criteria, list):
        return []
    return [
        {
            "criterion_id": item.get("criterion_id"),
            "disposition": item.get("disposition"),
            "required": item.get("required"),
            "operator": item.get("operator"),
            "expected_value": item.get("expected_value"),
            "actual_value": item.get("actual_value"),
        }
        for item in criteria
        if isinstance(item, dict)
    ]


def _verify_run(manifest_path: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    relative_manifest_path = manifest_path.relative_to(ROOT).as_posix()
    run_id = manifest_path.parent.name
    try:
        manifest = _read_json(manifest_path)
        run = parse_cto_evidence_run(manifest)
        validate_cto_evidence_run(run)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"run_id": run_id, "status": "failed"}, [
            f"{run_id}:manifest_invalid:{type(exc).__name__}"
        ]

    if run.run_id != run_id:
        errors.append(f"{run_id}:manifest_directory_run_id_mismatch")
    if "exact_repository_sha" not in run.required_evidence_classes:
        errors.append(f"{run_id}:exact_repository_sha_not_required")

    source_paths: list[Path] = []
    source_results: list[dict[str, Any]] = []
    for source in run.sources:
        role = source.role
        if role in {"run", "candidate"}:
            expected_sha = (
                run.comparison.candidate_repository_sha
                if role == "candidate" and run.comparison is not None
                else run.tested_repository_sha
            )
        elif role == "baseline" and run.comparison is not None:
            expected_sha = run.comparison.baseline_repository_sha
        else:
            expected_sha = source.tested_repository_sha
        if expected_sha is not None and source.tested_repository_sha != expected_sha:
            errors.append(f"{run_id}:source_tested_sha_mismatch:{source.source_id}")
        if role == "baseline" and run.comparison is None:
            errors.append(
                f"{run_id}:baseline_source_without_comparison:{source.source_id}"
            )
        try:
            source_path = _inside_root(source.path)
            actual_sha = _sha256(source_path)
        except (OSError, ValueError):
            errors.append(f"{run_id}:source_unavailable:{source.source_id}")
            source_results.append(
                {"source_id": source.source_id, "status": "unavailable"}
            )
            continue
        source_paths.append(source_path)
        source_match = actual_sha == source.sha256 and bool(
            _SHA256_RE.fullmatch(actual_sha)
        )
        if not source_match:
            errors.append(f"{run_id}:source_sha_mismatch:{source.source_id}")
        source_results.append(
            {
                "source_id": source.source_id,
                "role": role,
                "path": source.path,
                "sha256": source.sha256,
                "tested_repository_sha": source.tested_repository_sha,
                "verified": source_match,
            }
        )

    bundle_path = manifest_path.parent / "cto_evidence_bundle.json"
    verification_path = manifest_path.parent / "verification.json"
    try:
        bundle_payload = _read_json(bundle_path)
        parsed_bundle = parse_cto_evidence_bundle(bundle_payload)
        roundtrip_ok = cto_evidence_bundle_payload(parsed_bundle) == bundle_payload
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"run_id": run_id, "status": "failed"}, [
            *errors,
            f"{run_id}:bundle_invalid:{type(exc).__name__}",
        ]
    if not roundtrip_ok:
        errors.append(f"{run_id}:bundle_roundtrip_mismatch")
    if parsed_bundle.run is None or parsed_bundle.run.run_id != run.run_id:
        errors.append(f"{run_id}:bundle_manifest_identity_mismatch")
    missing_classes = _missing_classes(bundle_payload)
    if "exact_repository_sha" in missing_classes:
        errors.append(f"{run_id}:exact_repository_sha_unproven")
    if parsed_bundle.completeness == "invalid":
        errors.append(f"{run_id}:bundle_fail_closed_invalid")
    if parsed_bundle.completeness == "complete" and _missing_classes(bundle_payload):
        errors.append(f"{run_id}:complete_with_missing_required_classes")

    bundle_sources = {item.source_id: item for item in parsed_bundle.source_references}
    for source in run.sources:
        projected_source = bundle_sources.get(source.source_id)
        if projected_source is None or projected_source.status != "verified":
            errors.append(f"{run_id}:bundle_source_not_verified:{source.source_id}")
            continue
        if (
            projected_source.sha256 != source.sha256
            or projected_source.tested_repository_sha != source.tested_repository_sha
            or projected_source.role != source.role
        ):
            errors.append(
                f"{run_id}:bundle_source_reference_mismatch:{source.source_id}"
            )

    expected_manifest_sha = _sha256(manifest_path)
    manifest_reference = next(
        (
            item
            for item in bundle_payload.get("source_references", [])
            if isinstance(item, dict) and item.get("source_id") == "run_manifest"
        ),
        None,
    )
    if (
        not isinstance(manifest_reference, dict)
        or manifest_reference.get("sha256") != expected_manifest_sha
        or manifest_reference.get("status") != "verified"
    ):
        errors.append(f"{run_id}:bundle_manifest_source_mismatch")

    privacy = _privacy_scan(bundle_payload, source_paths)
    if privacy["status"] != "passed":
        errors.append(f"{run_id}:privacy_or_bounded_output_failed")

    verification = {
        "schema_version": "1.0",
        "run_id": run_id,
        "run_type": run.run_type,
        "tested_repository_sha": run.tested_repository_sha,
        "collector_repository_sha": parsed_bundle.collector_repository_sha,
        "manifest_path": relative_manifest_path,
        "manifest_sha256": expected_manifest_sha,
        "bundle_path": bundle_path.relative_to(ROOT).as_posix(),
        "bundle_sha256": _sha256(bundle_path),
        "source_sha_verification": "passed"
        if all(item.get("verified") for item in source_results)
        else "failed",
        "sources": source_results,
        "contract_parse_roundtrip": "passed" if roundtrip_ok else "failed",
        "completeness": parsed_bundle.completeness,
        "disposition": parsed_bundle.disposition,
        "required_evidence_classes": sorted(run.required_evidence_classes),
        "available_evidence_classes": sorted(
            set(run.required_evidence_classes) - set(_missing_classes(bundle_payload))
        ),
        "missing_evidence_classes": _missing_classes(bundle_payload),
        "criteria_results": _criteria(bundle_payload),
        "subject_count": len(parsed_bundle.run_evidence.subjects)
        if parsed_bundle.run_evidence
        else 0,
        "metric_count": len(parsed_bundle.run_evidence.metrics)
        if parsed_bundle.run_evidence
        else 0,
        "source_count": len(run.sources),
        "comparison_status": (
            parsed_bundle.run_evidence.comparison.status
            if parsed_bundle.run_evidence and parsed_bundle.run_evidence.comparison
            else "not_applicable"
        ),
        "unavailable_metric_count": sum(
            metric.status == "unavailable"
            for metric in parsed_bundle.run_evidence.metrics
        )
        if parsed_bundle.run_evidence
        else 0,
        "privacy_bounded_content_scan": privacy,
        "status": "passed" if not errors else "failed",
    }
    try:
        recorded = _read_json(verification_path)
    except (OSError, ValueError, json.JSONDecodeError):
        errors.append(f"{run_id}:verification_metadata_missing_or_invalid")
    else:
        for key, value in verification.items():
            if recorded.get(key) != value:
                errors.append(f"{run_id}:verification_metadata_mismatch:{key}")
    verification["errors"] = sorted(set(errors))
    return verification, errors


def _verify_inventory() -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    try:
        inventory = _read_json(ROOT / INVENTORY_PATH)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}, ["evidence_inventory_missing_or_invalid"]
    records = inventory.get("sources") if isinstance(inventory, dict) else None
    if not isinstance(records, list) or not records:
        return inventory, ["evidence_inventory_sources_missing"]

    manifest_sources: dict[str, set[str]] = {}
    for manifest_path in sorted((ROOT / RUNS_DIR).glob("*/run_manifest.json")):
        try:
            manifest = _read_json(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        for source in manifest.get("sources", []):
            if isinstance(source, dict) and isinstance(source.get("path"), str):
                tested_sha = source.get("tested_repository_sha")
                if isinstance(tested_sha, str):
                    manifest_sources.setdefault(source["path"], set()).add(tested_sha)

    for number, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"evidence_inventory_record_invalid:{number}")
            continue
        source_path = record.get("source_path")
        source_digest = record.get("source_sha256")
        if not isinstance(source_path, str):
            errors.append(f"evidence_inventory_source_path_missing:{number}")
        elif record.get("source_retained_in_repository") is True:
            try:
                retained_path = _inside_root(source_path)
                if _sha256(retained_path) != source_digest:
                    errors.append(f"evidence_inventory_source_hash_mismatch:{number}")
            except (OSError, ValueError):
                errors.append(f"evidence_inventory_source_unavailable:{number}")

        included_path = record.get("included_source_path")
        included_digest = record.get("included_source_sha256")
        if included_path is not None:
            if not isinstance(included_path, str) or not isinstance(
                included_digest, str
            ):
                errors.append(f"evidence_inventory_included_source_malformed:{number}")
                continue
            try:
                public_path = _inside_root(included_path)
                if _sha256(public_path) != included_digest:
                    errors.append(f"evidence_inventory_included_hash_mismatch:{number}")
            except (OSError, ValueError):
                errors.append(
                    f"evidence_inventory_included_source_unavailable:{number}"
                )

            expected_shas = sorted(manifest_sources.get(included_path, set()))
            declared_shas = record.get("included_source_tested_repository_shas", [])
            if declared_shas != expected_shas:
                errors.append(f"evidence_inventory_tested_sha_mismatch:{number}")

    serialized = json.dumps(inventory, ensure_ascii=True, sort_keys=True)
    if (
        _ABSOLUTE_PATH_RE.search(serialized)
        or _EMAIL_RE.search(serialized)
        or _URL_RE.search(serialized)
        or _SECRET_RE.search(serialized)
        or _DATABASE_URL_RE.search(serialized)
    ):
        errors.append("evidence_inventory_privacy_scan_failed")

    for source_path in sorted(
        (ROOT / "docs/CTO_evidence/source_artifacts").rglob("*.json")
    ):
        source_text = source_path.read_text(encoding="utf-8")
        source_payload = json.loads(source_text)
        if (
            _ABSOLUTE_PATH_RE.search(source_text)
            or _EMAIL_RE.search(source_text)
            or _URL_RE.search(source_text)
            or _SECRET_RE.search(source_text)
            or _DATABASE_URL_RE.search(source_text)
        ):
            errors.append(
                f"public_source_privacy_scan_failed:{source_path.relative_to(ROOT).as_posix()}"
            )
        for field_path, value in _walk(source_payload):
            key = field_path.rsplit(".", 1)[-1].split("[", 1)[0].casefold()
            if key not in _IDENTITY_KEYS or not isinstance(value, str):
                continue
            if not re.fullmatch(
                r"(?:candidate|subject)-[0-9a-f]{64}|[0-9a-f]{64}", value
            ):
                errors.append(
                    f"public_source_identity_not_hashed:{source_path.relative_to(ROOT).as_posix()}"
                )
                break
    return inventory, errors


def verify_pack() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    manifest_paths = sorted((ROOT / RUNS_DIR).glob("*/run_manifest.json"))
    if not manifest_paths:
        errors.append("no_run_manifests_found")
    for manifest_path in manifest_paths:
        result, run_errors = _verify_run(manifest_path)
        results.append(result)
        errors.extend(run_errors)

    inventory, inventory_errors = _verify_inventory()
    errors.extend(inventory_errors)
    try:
        index = _read_json(ROOT / INDEX_PATH)
    except (OSError, ValueError, json.JSONDecodeError):
        index = {}
        errors.append("evidence_index_missing_or_invalid")
    if index.get("evidence_inventory_sha256") != _sha256(ROOT / INVENTORY_PATH):
        errors.append("evidence_index_inventory_hash_mismatch")
    matrix = index.get("coverage_matrix") if isinstance(index, dict) else None
    allowed_matrix_statuses = {
        "proven",
        "partial",
        "unavailable",
        "not_applicable",
        "not_evaluated",
    }
    required_matrix_areas = {
        "correctness_validation",
        "publication_readiness",
        "factual_quality_controls",
        "performance",
        "provider_timing",
        "resource_usage_cost",
        "concurrency",
        "critical_path",
        "retry_attempt_history",
        "reuse",
        "acquisition",
        "visual_qa",
        "editorial_review",
        "publication_side_effects",
        "idempotency_readback",
        "immutable_subject_coverage",
        "exact_repository_sha",
    }
    if not isinstance(matrix, dict) or not required_matrix_areas <= set(matrix):
        errors.append("evidence_coverage_matrix_incomplete")
    elif any(
        not isinstance(item, dict) or item.get("status") not in allowed_matrix_statuses
        for item in matrix.values()
    ):
        errors.append("evidence_coverage_matrix_status_invalid")
    exact_sha_row = (
        matrix.get("exact_repository_sha") if isinstance(matrix, dict) else None
    )
    if not isinstance(exact_sha_row, dict) or exact_sha_row.get("status") != "proven":
        errors.append("evidence_coverage_exact_sha_not_proven")
    if index.get("historical_telemetry_count") != sum(
        item.get("producer_format") == "marketlense/runtime-telemetry/1.0"
        for item in inventory.get("sources", [])
        if isinstance(item, dict)
    ):
        errors.append("evidence_index_historical_telemetry_count_mismatch")
    indexed_runs = index.get("runs") if isinstance(index, dict) else None
    declared_collector_sha = (
        index.get("collector_repository_sha") if isinstance(index, dict) else None
    )
    for result in results:
        if result.get("collector_repository_sha") != declared_collector_sha:
            errors.append(f"collector_repository_sha_mismatch:{result['run_id']}")
    if not isinstance(indexed_runs, list) or len(indexed_runs) != len(results):
        errors.append("evidence_index_run_count_mismatch")
    else:
        indexed = {
            item.get("run_id"): item for item in indexed_runs if isinstance(item, dict)
        }
        for result in results:
            entry = indexed.get(result["run_id"])
            if not isinstance(entry, dict):
                errors.append(f"evidence_index_missing_run:{result['run_id']}")
                continue
            if (
                entry.get("bundle_sha256") != result.get("bundle_sha256")
                or entry.get("manifest_sha256") != result.get("manifest_sha256")
                or entry.get("tested_repository_sha")
                != result.get("tested_repository_sha")
                or entry.get("completeness") != result.get("completeness")
                or entry.get("disposition") != result.get("disposition")
                or entry.get("bundle_path") != result.get("bundle_path")
                or entry.get("run_type") != result.get("run_type")
                or entry.get("subject_count") != result.get("subject_count")
                or entry.get("source_count") != result.get("source_count")
                or entry.get("comparison_status") != result.get("comparison_status")
                or entry.get("evidence_classes_proven")
                != result.get("available_evidence_classes")
                or entry.get("evidence_classes_missing")
                != result.get("missing_evidence_classes")
            ):
                errors.append(f"evidence_index_entry_mismatch:{result['run_id']}")

    current_head = index.get("current_head") if isinstance(index, dict) else None
    current_run = next(
        (
            item
            for item in results
            if item.get("run_id") == "current-head-integrity-20261007"
        ),
        None,
    )
    if (
        not isinstance(current_head, dict)
        or current_run is None
        or current_head.get("run_id") != current_run.get("run_id")
        or current_head.get("tested_repository_sha")
        != current_run.get("tested_repository_sha")
        or any(
            item.get("disposition") != "pass"
            for item in current_run.get("criteria_results", [])
            if item.get("required")
        )
    ):
        errors.append("current_head_integrity_summary_mismatch")

    return {
        "schema_version": "1.0",
        "status": "passed" if not errors else "failed",
        "run_count": len(results),
        "passed_run_count": sum(item["status"] == "passed" for item in results),
        "runs": results,
        "errors": sorted(set(errors)),
    }


def main() -> int:
    result = verify_pack()
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
