"""Validate and score the committed MarketLense agent-engineering benchmark.

This is intentionally a corpus-specific quality tool.  It validates the
historical task metadata and normalizes an externally collected agent-run
record; it does not provision worktrees, invoke agents, or run production I/O.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_CATEGORIES = frozenset(
    {
        "architecture_investigation",
        "browser_acquisition",
        "bug_fix",
        "feature_implementation",
        "llm_prompt_pipeline",
        "pdf_visual_extraction",
        "performance_cost",
        "service_boundary_refactor",
    }
)
PROMPT_PATH_MARKERS = ("src/", "tests/", "scripts/", "docs/", ".py", ".json")
PATH_TOKEN = re.compile(r"(?:src|tests|scripts|docs)/[A-Za-z0-9_./-]+")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Benchmark payload must be a JSON object: {path}")
    return payload


def _commit_exists(commit: str, *, root: Path) -> bool:
    if not commit:
        return False
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _path_tokens(command: str) -> tuple[str, ...]:
    return tuple(match.rstrip(".,)") for match in PATH_TOKEN.findall(command))


def validate_corpus(corpus_path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    """Return deterministic structural and provenance checks for this corpus."""
    failures: list[str] = []
    try:
        corpus = _load_json(corpus_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "passed": False,
            "case_count": 0,
            "category_counts": {},
            "failures": [str(error)],
        }

    if corpus.get("schema_version") != "2.0":
        failures.append("unsupported_schema_version")
    cases = corpus.get("cases")
    if not isinstance(cases, list):
        return {
            "passed": False,
            "case_count": 0,
            "category_counts": {},
            "failures": [*failures, "cases_must_be_a_list"],
        }
    if not 15 <= len(cases) <= 20:
        failures.append("case_count_must_be_between_15_and_20")

    category_counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    for position, case in enumerate(cases, start=1):
        label = f"case_{position}"
        if not isinstance(case, dict):
            failures.append(f"{label}_must_be_an_object")
            continue
        case_id = str(case.get("id") or "")
        if not case_id or case_id in seen_ids:
            failures.append(f"{label}_id_missing_or_duplicate")
        seen_ids.add(case_id)
        category = str(case.get("category") or "")
        category_counts[category] += 1
        if category not in REQUIRED_CATEGORIES:
            failures.append(f"{case_id}_unknown_category")

        prompt = str(case.get("task_prompt") or "")
        if not prompt:
            failures.append(f"{case_id}_task_prompt_missing")
        prompt_lower = prompt.lower()
        if any(marker in prompt_lower for marker in PROMPT_PATH_MARKERS):
            failures.append(f"{case_id}_task_prompt_contains_path_marker")

        ground_truth = case.get("ground_truth")
        if not isinstance(ground_truth, dict):
            failures.append(f"{case_id}_ground_truth_missing")
            continue
        reference_files = ground_truth.get("historical_reference_files")
        if not isinstance(reference_files, list) or not reference_files:
            failures.append(f"{case_id}_historical_reference_files_missing")
            continue
        for relative_path in reference_files:
            if (
                not isinstance(relative_path, str)
                or not (root / relative_path).is_file()
            ):
                failures.append(f"{case_id}_missing_ground_truth_path:{relative_path}")
            if (
                isinstance(relative_path, str)
                and Path(relative_path).name.lower() in prompt_lower
            ):
                failures.append(f"{case_id}_task_prompt_leaks_ground_truth_file")

        traceability = ground_truth.get("traceability")
        if not isinstance(traceability, dict) or not _commit_exists(
            str(traceability.get("fix_commit") or ""), root=root
        ):
            failures.append(f"{case_id}_fix_commit_not_resolvable")
        evidence_paths = (
            traceability.get("evidence_paths")
            if isinstance(traceability, dict)
            else None
        )
        if not isinstance(evidence_paths, list) or not evidence_paths:
            failures.append(f"{case_id}_evidence_paths_missing")
        else:
            for relative_path in evidence_paths:
                if (
                    not isinstance(relative_path, str)
                    or not (root / relative_path).is_file()
                ):
                    failures.append(f"{case_id}_missing_evidence_path:{relative_path}")

        verification = case.get("verification")
        checks = (
            verification.get("required_checks")
            if isinstance(verification, dict)
            else None
        )
        if not isinstance(checks, list) or not checks:
            failures.append(f"{case_id}_required_checks_missing")
        else:
            for command in checks:
                if not isinstance(command, str) or not command.strip():
                    failures.append(f"{case_id}_invalid_required_check")
                    continue
                for token in _path_tokens(command):
                    if not (root / token).is_file():
                        failures.append(
                            f"{case_id}_required_check_path_missing:{token}"
                        )

        for required_key in (
            "expected_observable_result",
            "important_failure_conditions",
        ):
            if not case.get(required_key):
                failures.append(f"{case_id}_{required_key}_missing")
        scoring = case.get("scoring")
        if not isinstance(scoring, dict):
            failures.append(f"{case_id}_scoring_missing")
        else:
            weights = scoring.get("weights")
            if not isinstance(weights, dict) or sum(weights.values()) != 100:
                failures.append(f"{case_id}_score_weights_must_sum_to_100")
            elif int(weights.get("correct_completion", 0)) < 60:
                failures.append(f"{case_id}_correctness_weight_must_be_at_least_60")
            elif set(weights) != {
                "correct_completion",
                "architecture_policy_compliance",
                "verified_scope_control",
                "required_verification_success",
            }:
                failures.append(f"{case_id}_invalid_score_weight_keys")

    missing_categories = sorted(REQUIRED_CATEGORIES - set(category_counts))
    if missing_categories:
        failures.append("missing_categories:" + ",".join(missing_categories))
    return {
        "passed": not failures,
        "case_count": len(cases),
        "category_counts": dict(sorted(category_counts.items())),
        "failures": failures,
    }


def validate_evaluator_injections(
    injections_path: Path, *, root: Path = ROOT
) -> dict[str, Any]:
    """Validate pinned, post-worker evaluator payloads without executing them."""
    failures: list[str] = []
    try:
        manifest = _load_json(injections_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {"passed": False, "case_count": 0, "failures": [str(error)]}
    if manifest.get("schema_version") != "1.0":
        failures.append("unsupported_evaluator_injection_schema_version")
    cases = manifest.get("cases")
    if not isinstance(cases, dict) or not cases:
        return {
            "passed": False,
            "case_count": 0,
            "failures": [*failures, "evaluator_injection_cases_missing"],
        }
    for case_id, case in cases.items():
        if not isinstance(case_id, str) or not isinstance(case, dict):
            failures.append("invalid_evaluator_injection_case")
            continue
        starting_revision = str(case.get("starting_revision") or "")
        source_revision = str(case.get("source_revision") or "")
        if not _commit_exists(starting_revision, root=root) or not _commit_exists(
            source_revision, root=root
        ):
            failures.append(f"evaluator_injection_revision_missing:{case_id}")
        elif _git_output(["rev-parse", f"{source_revision}^"], root=root) != starting_revision:
            failures.append(f"evaluator_injection_source_parent_mismatch:{case_id}")
        files = case.get("files")
        if not isinstance(files, list) or not files:
            failures.append(f"evaluator_injection_files_missing:{case_id}")
            continue
        for item in files:
            if not isinstance(item, dict):
                failures.append(f"invalid_evaluator_injection_file:{case_id}")
                continue
            relative_path = item.get("path")
            payload_path = item.get("evaluator_payload_path")
            expected_sha256 = item.get("sha256")
            if not all(isinstance(value, str) and value for value in (relative_path, payload_path, expected_sha256)):
                failures.append(f"invalid_evaluator_payload_metadata:{case_id}")
                continue
            relative = Path(relative_path)
            payload = Path(payload_path)
            if (
                relative.is_absolute()
                or payload.is_absolute()
                or ".." in relative.parts
                or ".." in payload.parts
            ):
                failures.append(f"unsafe_evaluator_payload_path:{case_id}")
                continue
            if item.get("historical_source_path") is not None:
                failures.append(f"ambiguous_evaluator_injection_source:{case_id}")
            if subprocess.run(
                ["git", "cat-file", "-e", f"{starting_revision}:{relative_path}"],
                cwd=root,
                capture_output=True,
                check=False,
            ).returncode == 0:
                failures.append(f"evaluator_injection_parent_already_contains:{relative_path}")
            source_file = root / payload
            if not source_file.is_file():
                failures.append(f"evaluator_injection_payload_missing:{payload_path}")
            elif hashlib.sha256(source_file.read_bytes()).hexdigest() != expected_sha256:
                failures.append(f"evaluator_injection_hash_mismatch:{relative_path}")
    return {"passed": not failures, "case_count": len(cases), "failures": failures}


def validate_protocol(
    *,
    corpus_path: Path,
    protocol_path: Path,
    injections_path: Path,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Validate the immutable pre-Phase-1 comparison contract."""
    failures: list[str] = []
    try:
        corpus = _load_json(corpus_path)
        protocol = _load_json(protocol_path)
        injections = _load_json(injections_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "passed": False,
            "comparison_case_count": 0,
            "holdout_case_count": 0,
            "failures": [str(error)],
        }
    if protocol.get("schema_version") != "1.0":
        failures.append("unsupported_protocol_schema_version")
    corpus_metadata = protocol.get("corpus")
    if not isinstance(corpus_metadata, dict):
        failures.append("protocol_corpus_missing")
    elif corpus_metadata.get("sha256") != hashlib.sha256(corpus_path.read_bytes()).hexdigest():
        failures.append("protocol_corpus_hash_mismatch")
    if protocol.get("evaluator_injection", {}).get("manifest_sha256") != hashlib.sha256(
        injections_path.read_bytes()
    ).hexdigest():
        failures.append("protocol_injection_hash_mismatch")
    if protocol.get("evaluator_injection", {}).get("version") != injections.get(
        "injection_version"
    ):
        failures.append("protocol_injection_version_mismatch")
    injection_validation = validate_evaluator_injections(injections_path, root=root)
    if not injection_validation["passed"]:
        failures.extend(injection_validation["failures"])

    corpus_cases = {case.get("id"): case for case in corpus.get("cases", [])}
    comparison_cases = protocol.get("comparison_cases")
    if not isinstance(comparison_cases, list):
        comparison_cases = []
        failures.append("protocol_comparison_cases_missing")
    comparison_ids = [case.get("id") for case in comparison_cases if isinstance(case, dict)]
    if len(comparison_ids) != 10 or len(set(comparison_ids)) != 10:
        failures.append("protocol_comparison_cases_must_be_exactly_ten_unique")
    for case in comparison_cases:
        if not isinstance(case, dict):
            failures.append("protocol_comparison_case_invalid")
            continue
        case_id = case.get("id")
        corpus_case = corpus_cases.get(case_id)
        if not isinstance(corpus_case, dict):
            failures.append(f"protocol_unknown_comparison_case:{case_id}")
            continue
        traceability = corpus_case.get("ground_truth", {}).get("traceability", {})
        if case.get("fix_commit") != traceability.get("fix_commit"):
            failures.append(f"protocol_fix_commit_mismatch:{case_id}")
        if case.get("task_prompt") != corpus_case.get("task_prompt"):
            failures.append(f"protocol_task_prompt_mismatch:{case_id}")
        starting_revision = case.get("starting_revision")
        if not isinstance(starting_revision, str) or not _commit_exists(
            starting_revision, root=root
        ):
            failures.append(f"protocol_starting_revision_missing:{case_id}")
        elif _git_output(["rev-parse", f"{case.get('fix_commit')}^"], root=root) != starting_revision:
            failures.append(f"protocol_starting_revision_not_fix_parent:{case_id}")

    holdout_ids = protocol.get("holdout_case_ids")
    if not isinstance(holdout_ids, list):
        holdout_ids = []
        failures.append("protocol_holdout_case_ids_missing")
    if len(holdout_ids) != 6 or len(set(holdout_ids)) != 6:
        failures.append("protocol_holdout_cases_must_be_exactly_six_unique")
    if set(comparison_ids) & set(holdout_ids):
        failures.append("protocol_comparison_and_holdout_overlap")
    if set(comparison_ids) | set(holdout_ids) != set(corpus_cases):
        failures.append("protocol_cases_must_partition_corpus")
    elapsed_case_ids = protocol.get("elapsed_comparison_case_ids")
    if not isinstance(elapsed_case_ids, list) or not elapsed_case_ids:
        failures.append("protocol_elapsed_comparison_cases_missing")
    elif len(elapsed_case_ids) != len(set(elapsed_case_ids)):
        failures.append("protocol_elapsed_comparison_cases_not_unique")
    elif not set(elapsed_case_ids) <= set(comparison_ids):
        failures.append("protocol_elapsed_comparison_cases_not_comparison_cases")
    else:
        try:
            run_record = _load_json(
                root
                / "benchmarks/agent-engineering/baselines/codex-pre-phase1-run.json"
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            failures.append(f"protocol_elapsed_baseline_unavailable:{error}")
        else:
            records = {
                record.get("case_id"): record
                for record in run_record.get("cases", [])
                if isinstance(record, dict)
            }
            for case_id in elapsed_case_ids:
                value = records.get(case_id, {}).get("elapsed_seconds")
                independently_measured = records.get(case_id, {}).get(
                    "elapsed_measurement_valid"
                )
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or value < 0
                    or independently_measured is not True
                ):
                    failures.append(f"protocol_elapsed_baseline_invalid:{case_id}")
    return {
        "passed": not failures,
        "comparison_case_count": len(comparison_ids),
        "holdout_case_count": len(holdout_ids),
        "failures": failures,
    }


def _availability(values: list[Any]) -> tuple[Any, str]:
    if not values or any(value == "unavailable" or value is None for value in values):
        return "unavailable", "unavailable"
    return sum(float(value) for value in values), "measured"


def _required_verification_ratio(
    required_checks: set[str], record: dict[str, Any]
) -> float:
    """Return the share of required checks that the evaluator observed passing."""
    if not required_checks:
        return 0.0
    passed_commands = {
        item.get("command")
        for item in record.get("check_results", [])
        if isinstance(item, dict) and item.get("returncode") == 0
    }
    return len(required_checks & passed_commands) / len(required_checks)


def _normalized_scope_violations(record: dict[str, Any]) -> list[dict[str, str]]:
    """Keep only concrete evaluator findings; historical file overlap is not scope."""
    normalized: list[dict[str, str]] = []
    for violation in record.get("verified_scope_violations", []):
        if not isinstance(violation, dict):
            continue
        path = violation.get("path")
        reason = violation.get("reason")
        if isinstance(path, str) and path and isinstance(reason, str) and reason:
            normalized.append({"path": path, "reason": reason})
    return sorted(normalized, key=lambda item: (item["path"], item["reason"]))


def score_run(corpus: dict[str, Any], run_record: dict[str, Any]) -> dict[str, Any]:
    """Score an externally captured run record against committed case truth."""
    cases_by_id = {case["id"]: case for case in corpus.get("cases", [])}
    records_by_id = {
        record.get("case_id"): record
        for record in run_record.get("cases", [])
        if isinstance(record, dict) and record.get("case_id") in cases_by_id
    }
    rows: list[dict[str, Any]] = []
    for case_id, case in cases_by_id.items():
        record = records_by_id.get(case_id)
        if record is None:
            continue
        ground_truth = case["ground_truth"]
        weights = case["scoring"]["weights"]
        historical_reference_files = set(ground_truth["historical_reference_files"])
        discovered_files = set(record.get("files_discovered", []))
        modified_files = set(record.get("files_modified", []))
        required_checks = set(case["verification"]["required_checks"])
        executed_checks = set(record.get("checks_executed", []))
        reference_recall = (
            len(historical_reference_files & discovered_files)
            / len(historical_reference_files)
            if historical_reference_files
            else 0.0
        )
        checks_ratio = (
            len(required_checks & executed_checks) / len(required_checks)
            if required_checks
            else 0.0
        )
        verification_ratio = _required_verification_ratio(required_checks, record)
        scope_violations = _normalized_scope_violations(record)
        score = (
            weights["correct_completion"] * int(bool(record.get("correct_completion")))
            + weights["architecture_policy_compliance"]
            * int(bool(record.get("architecture_policy_compliant")))
            + max(weights["verified_scope_control"] - len(scope_violations), 0)
            + weights["required_verification_success"] * verification_ratio
        )
        rows.append(
            {
                "case_id": case_id,
                "score": round(score, 2),
                "correct_completion": bool(record.get("correct_completion")),
                "architecture_policy_compliant": bool(
                    record.get("architecture_policy_compliant")
                ),
                "historical_reference_file_recall": reference_recall,
                "candidate_files_modified": sorted(modified_files),
                "verified_scope_violations": scope_violations,
                "required_checks_executed": checks_ratio,
                "required_verification_success": verification_ratio,
                "tool_file_read_count": record.get(
                    "tool_file_read_count", "unavailable"
                ),
                "elapsed_seconds": record.get("elapsed_seconds", "unavailable"),
                "token_usage": record.get("token_usage", "unavailable"),
                "estimated_cost_usd": record.get("estimated_cost_usd", "unavailable"),
                "human_intervention_count": record.get(
                    "human_intervention_count", "unavailable"
                ),
                "rework_count": record.get("rework_count", "unavailable"),
            }
        )

    def average(field: str) -> float:
        return (
            round(sum(float(row[field]) for row in rows) / len(rows), 4)
            if rows
            else 0.0
        )

    token_usage, token_status = _availability([row["token_usage"] for row in rows])
    estimated_cost, cost_status = _availability(
        [row["estimated_cost_usd"] for row in rows]
    )
    tool_reads, tool_status = _availability(
        [row["tool_file_read_count"] for row in rows]
    )
    elapsed, elapsed_status = _availability([row["elapsed_seconds"] for row in rows])
    interventions, intervention_status = _availability(
        [row["human_intervention_count"] for row in rows]
    )
    rework, rework_status = _availability([row["rework_count"] for row in rows])
    return {
        "schema_version": "2.0",
        "evaluated_case_count": len(rows),
        "cases": rows,
        "aggregate": {
            "correct_completion": average("correct_completion"),
            "architecture_policy_compliance": average(
                "architecture_policy_compliant"
            ),
            "historical_reference_file_recall": average(
                "historical_reference_file_recall"
            ),
            "candidate_files_modified_count": sum(
                len(row["candidate_files_modified"]) for row in rows
            ),
            "verified_scope_violation_count": sum(
                len(row["verified_scope_violations"]) for row in rows
            ),
            "required_checks_executed": average("required_checks_executed"),
            "required_verification_success": average(
                "required_verification_success"
            ),
            "mean_score": round(sum(row["score"] for row in rows) / len(rows), 2)
            if rows
            else 0.0,
            "tool_file_read_count": tool_reads,
            "tool_file_read_count_status": tool_status,
            "elapsed_seconds": elapsed,
            "elapsed_seconds_status": elapsed_status,
            "token_usage": token_usage,
            "token_usage_status": token_status,
            "estimated_cost_usd": estimated_cost,
            "estimated_cost_usd_status": cost_status,
            "human_intervention_count": interventions,
            "human_intervention_count_status": intervention_status,
            "rework_count": rework,
            "rework_count_status": rework_status,
        },
    }


def _git_output(args: list[str], *, root: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _git_show_bytes(*, revision: str, relative_path: str, root: Path) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(
            f"evaluator injection source is unavailable: {revision}:{relative_path}"
        )
    return result.stdout


def prepare_evaluator_worktree(
    *,
    case_id: str,
    worktree: Path,
    manifest: dict[str, Any],
    root: Path = ROOT,
) -> dict[str, Any]:
    """Inject one evaluator-only test payload after an agent run, deterministically."""
    if manifest.get("schema_version") != "1.0":
        raise ValueError("unsupported_evaluator_injection_schema_version")
    case = manifest.get("cases", {}).get(case_id)
    if not isinstance(case, dict):
        raise ValueError(f"no_evaluator_injection_for_case:{case_id}")
    starting_revision = str(case.get("starting_revision") or "")
    source_revision = str(case.get("source_revision") or "")
    if not starting_revision or not source_revision:
        raise ValueError(f"invalid_evaluator_injection_revisions:{case_id}")
    actual_revision = _git_output(
        ["-C", str(worktree), "rev-parse", "HEAD"], root=root
    )
    if actual_revision != starting_revision:
        raise ValueError(
            f"evaluator_injection_starting_revision_mismatch:{actual_revision}"
        )
    if _git_output(["rev-parse", f"{source_revision}^"], root=root) != starting_revision:
        raise ValueError(f"evaluator_injection_source_parent_mismatch:{case_id}")
    files = case.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError(f"evaluator_injection_files_missing:{case_id}")

    injected: list[dict[str, str]] = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError(f"invalid_evaluator_injection_file:{case_id}")
        relative_path = item.get("path")
        expected_sha256 = item.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected_sha256, str):
            raise ValueError(f"invalid_evaluator_injection_file:{case_id}")
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe_evaluator_injection_path:{relative_path}")
        target = worktree / relative_path
        if target.exists() or target.is_symlink():
            raise ValueError(f"evaluator_injection_destination_exists:{relative_path}")
        parent_contains_file = subprocess.run(
            ["git", "cat-file", "-e", f"{starting_revision}:{relative_path}"],
            cwd=root,
            capture_output=True,
            check=False,
        ).returncode == 0
        if parent_contains_file:
            raise ValueError(f"evaluator_injection_parent_already_contains:{relative_path}")
        evaluator_payload_path = item.get("evaluator_payload_path")
        historical_source_path = item.get("historical_source_path")
        if evaluator_payload_path is not None and historical_source_path is not None:
            raise ValueError(f"ambiguous_evaluator_injection_source:{relative_path}")
        if evaluator_payload_path is None:
            source_path = historical_source_path or relative_path
            if not isinstance(source_path, str):
                raise ValueError(f"invalid_evaluator_injection_source:{relative_path}")
            payload = _git_show_bytes(
                revision=source_revision, relative_path=source_path, root=root
            )
            payload_source = f"{source_revision}:{source_path}"
        else:
            if not isinstance(evaluator_payload_path, str):
                raise ValueError(f"invalid_evaluator_injection_source:{relative_path}")
            evaluator_payload = Path(evaluator_payload_path)
            if evaluator_payload.is_absolute() or ".." in evaluator_payload.parts:
                raise ValueError(f"unsafe_evaluator_payload_path:{evaluator_payload_path}")
            source_file = root / evaluator_payload
            if not source_file.is_file():
                raise ValueError(
                    f"evaluator_injection_payload_missing:{evaluator_payload_path}"
                )
            payload = source_file.read_bytes()
            payload_source = evaluator_payload_path
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if actual_sha256 != expected_sha256:
            raise ValueError(f"evaluator_injection_hash_mismatch:{relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        injected.append(
            {
                "path": relative_path,
                "kind": str(item.get("kind") or "evaluator_payload"),
                "sha256": actual_sha256,
                "payload_source": payload_source,
            }
        )
    return {
        "case_id": case_id,
        "injection_version": manifest.get("injection_version"),
        "starting_revision": starting_revision,
        "source_revision": source_revision,
        "files": injected,
    }


def _head_commit(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def build_baseline(corpus_path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    """Build a revision-bound integrity baseline without simulating agent work."""
    validation = validate_corpus(corpus_path, root=root)
    raw_corpus = corpus_path.read_bytes()
    unavailable_metrics = {
        "correct_completion": "unavailable",
        "historical_reference_file_recall": "unavailable",
        "candidate_files_modified_count": "unavailable",
        "required_verification_success": "unavailable",
        "tool_file_read_count": "unavailable",
        "elapsed_seconds": "unavailable",
        "token_usage": "unavailable",
        "estimated_cost_usd": "unavailable",
        "human_intervention_count": "unavailable",
        "rework_count": "unavailable",
    }
    return {
        "schema_version": "2.0",
        "baseline_kind": "corpus_integrity",
        "agent": {
            "name": "Codex",
            "version": "unavailable",
            "execution": "not_executed",
        },
        "repository_commit": _head_commit(root),
        "corpus_path": corpus_path.relative_to(root).as_posix(),
        "corpus_sha256": hashlib.sha256(raw_corpus).hexdigest(),
        "validation": validation,
        "agent_measurements": unavailable_metrics,
        "interpretation": (
            "This records the current Codex benchmark corpus baseline only. "
            "It does not "
            "claim an agent-performance score because no task-solving run was executed."
        ),
    }


def _write_json(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "validate",
            "validate-injections",
            "validate-protocol",
            "baseline",
            "score",
            "prepare-evaluator-worktree",
        ),
    )
    parser.add_argument("--corpus", default="benchmarks/agent-engineering/cases.json")
    parser.add_argument("--run-record", default="")
    parser.add_argument(
        "--injections", default="benchmarks/agent-engineering/evaluator-injections.json"
    )
    parser.add_argument("--case-id", default="")
    parser.add_argument("--worktree", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    corpus_path = (ROOT / args.corpus).resolve()

    if args.command == "validate":
        payload = validate_corpus(corpus_path, root=ROOT)
        exit_code = 0 if payload["passed"] else 1
    elif args.command == "validate-injections":
        payload = validate_evaluator_injections(
            (ROOT / args.injections).resolve(), root=ROOT
        )
        exit_code = 0 if payload["passed"] else 1
    elif args.command == "validate-protocol":
        payload = validate_protocol(
            corpus_path=corpus_path,
            protocol_path=(
                ROOT / "benchmarks/agent-engineering/pre-phase1-protocol.json"
            ).resolve(),
            injections_path=(ROOT / args.injections).resolve(),
            root=ROOT,
        )
        exit_code = 0 if payload["passed"] else 1
    elif args.command == "baseline":
        payload = build_baseline(corpus_path, root=ROOT)
        exit_code = 0 if payload["validation"]["passed"] else 1
    elif args.command == "score":
        if not args.run_record:
            parser.error("score requires --run-record")
        payload = score_run(
            _load_json(corpus_path), _load_json((ROOT / args.run_record).resolve())
        )
        exit_code = 0
    else:
        if not args.case_id or not args.worktree:
            parser.error("prepare-evaluator-worktree requires --case-id and --worktree")
        payload = prepare_evaluator_worktree(
            case_id=args.case_id,
            worktree=Path(args.worktree).resolve(),
            manifest=_load_json((ROOT / args.injections).resolve()),
            root=ROOT,
        )
        exit_code = 0

    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        _write_json(payload, (ROOT / args.output).resolve())
    else:
        print(rendered, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
