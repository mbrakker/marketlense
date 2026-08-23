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

    if corpus.get("schema_version") != "1.0":
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
        relevant_files = ground_truth.get("relevant_files")
        allowed_files = ground_truth.get("allowed_modified_files")
        if not isinstance(relevant_files, list) or not relevant_files:
            failures.append(f"{case_id}_relevant_files_missing")
            continue
        if not isinstance(allowed_files, list) or not allowed_files:
            failures.append(f"{case_id}_allowed_modified_files_missing")
        for relative_path in (*relevant_files, *(allowed_files or [])):
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

    missing_categories = sorted(REQUIRED_CATEGORIES - set(category_counts))
    if missing_categories:
        failures.append("missing_categories:" + ",".join(missing_categories))
    return {
        "passed": not failures,
        "case_count": len(cases),
        "category_counts": dict(sorted(category_counts.items())),
        "failures": failures,
    }


def _availability(values: list[Any]) -> tuple[Any, str]:
    if not values or any(value == "unavailable" or value is None for value in values):
        return "unavailable", "unavailable"
    return sum(float(value) for value in values), "measured"


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
        relevant_files = set(ground_truth["relevant_files"])
        discovered_files = set(record.get("files_discovered", []))
        modified_files = set(record.get("files_modified", []))
        allowed_files = set(ground_truth["allowed_modified_files"])
        required_checks = set(case["verification"]["required_checks"])
        executed_checks = set(record.get("checks_executed", []))
        discovery_ratio = (
            len(relevant_files & discovered_files) / len(relevant_files)
            if relevant_files
            else 0.0
        )
        checks_ratio = (
            len(required_checks & executed_checks) / len(required_checks)
            if required_checks
            else 0.0
        )
        irrelevant_files = sorted(modified_files - allowed_files)
        score = (
            weights["correct_completion"] * int(bool(record.get("correct_completion")))
            + weights["relevant_files_discovered"] * discovery_ratio
            + max(weights["scope_control"] - len(irrelevant_files), 0)
            + weights["tests_checks_executed"] * checks_ratio
        )
        rows.append(
            {
                "case_id": case_id,
                "score": round(score, 2),
                "correct_completion": bool(record.get("correct_completion")),
                "relevant_files_discovered": discovery_ratio,
                "irrelevant_files_modified": irrelevant_files,
                "required_checks_executed": checks_ratio,
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
        "schema_version": "1.0",
        "evaluated_case_count": len(rows),
        "cases": rows,
        "aggregate": {
            "correct_completion": average("correct_completion"),
            "relevant_files_discovered": average("relevant_files_discovered"),
            "irrelevant_files_modified": sum(
                len(row["irrelevant_files_modified"]) for row in rows
            ),
            "required_checks_executed": average("required_checks_executed"),
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
        "relevant_files_discovered": "unavailable",
        "irrelevant_files_modified": "unavailable",
        "tests_checks_executed": "unavailable",
        "tool_file_read_count": "unavailable",
        "elapsed_seconds": "unavailable",
        "token_usage": "unavailable",
        "estimated_cost_usd": "unavailable",
        "human_intervention_count": "unavailable",
        "rework_count": "unavailable",
    }
    return {
        "schema_version": "1.0",
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
    parser.add_argument("command", choices=("validate", "baseline", "score"))
    parser.add_argument("--corpus", default="benchmarks/agent-engineering/cases.json")
    parser.add_argument("--run-record", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    corpus_path = (ROOT / args.corpus).resolve()

    if args.command == "validate":
        payload = validate_corpus(corpus_path, root=ROOT)
        exit_code = 0 if payload["passed"] else 1
    elif args.command == "baseline":
        payload = build_baseline(corpus_path, root=ROOT)
        exit_code = 0 if payload["validation"]["passed"] else 1
    else:
        if not args.run_record:
            parser.error("score requires --run-record")
        payload = score_run(
            _load_json(corpus_path), _load_json((ROOT / args.run_record).resolve())
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
