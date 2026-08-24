"""Validate and score the historical Final Engineering Review benchmark.

This corpus-specific development tool evaluates only the evidence-backed
findings returned by the repository-local review Skill. It neither invokes
agents nor modifies a benchmark worktree.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REVIEWERS = frozenset({"correctness", "architecture_simplicity", "regression_testing"})


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def validate_review_corpus(
    corpus_path: Path,
    *,
    task_corpus_path: Path,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Validate review cases against the retained task corpus and current paths."""
    failures: list[str] = []
    try:
        corpus = _load_json(corpus_path)
        task_corpus = _load_json(task_corpus_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "passed": False,
            "case_count": 0,
            "reviewer_counts": {},
            "failures": [str(error)],
        }

    if corpus.get("schema_version") != "1.0":
        failures.append("unsupported_schema_version")
    confidence_threshold = corpus.get("confidence_threshold")
    if not isinstance(confidence_threshold, int) or not (
        1 <= confidence_threshold <= 100
    ):
        failures.append("confidence_threshold_must_be_an_integer_between_1_and_100")
    cases = corpus.get("cases")
    if not isinstance(cases, list):
        return {
            "passed": False,
            "case_count": 0,
            "reviewer_counts": {},
            "failures": [*failures, "cases_must_be_a_list"],
        }
    task_cases = {
        item["id"]: item
        for item in task_corpus.get("cases", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    seen_ids: set[str] = set()
    reviewer_counts: Counter[str] = Counter()
    for number, case in enumerate(cases, start=1):
        label = f"case_{number}"
        if not isinstance(case, dict):
            failures.append(f"{label}_must_be_an_object")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            failures.append(f"{label}_id_missing_or_duplicate")
        seen_ids.add(str(case_id))
        reviewer = case.get("reviewer")
        reviewer_counts[str(reviewer)] += 1
        if reviewer not in REVIEWERS:
            failures.append(f"{case_id}_unknown_reviewer")
        source_case_id = case.get("source_case_id")
        source_case = task_cases.get(source_case_id)
        if source_case is None:
            failures.append(f"{case_id}_source_case_missing")
            continue
        expected_commit = source_case["ground_truth"]["traceability"]["fix_commit"]
        if case.get("fix_commit") != expected_commit:
            failures.append(f"{case_id}_fix_commit_does_not_match_source_case")
        finding = case.get("accepted_finding")
        if not isinstance(finding, dict):
            failures.append(f"{case_id}_accepted_finding_missing")
            continue
        finding_id = finding.get("id")
        evidence_paths = finding.get("evidence_paths")
        if not isinstance(finding_id, str) or not finding_id:
            failures.append(f"{case_id}_accepted_finding_id_missing")
        if not isinstance(evidence_paths, list) or not evidence_paths:
            failures.append(f"{case_id}_accepted_finding_evidence_missing")
            continue
        source_paths = set(source_case["ground_truth"]["historical_reference_files"])
        for path in evidence_paths:
            if not isinstance(path, str) or path not in source_paths:
                failures.append(f"{case_id}_evidence_not_in_source_ground_truth:{path}")
            elif not (root / path).is_file():
                failures.append(f"{case_id}_evidence_path_missing:{path}")
        if (
            not isinstance(case.get("introduced_issue"), str)
            or not case["introduced_issue"]
        ):
            failures.append(f"{case_id}_introduced_issue_missing")

    if len(cases) != 6:
        failures.append("case_count_must_be_six")
    for reviewer in REVIEWERS:
        if reviewer_counts[reviewer] != 2:
            failures.append(f"{reviewer}_must_have_two_cases")
    return {
        "passed": not failures,
        "case_count": len(cases),
        "reviewer_counts": dict(sorted(reviewer_counts.items())),
        "failures": failures,
    }


def score_review_run(
    corpus: dict[str, Any], run_record: dict[str, Any]
) -> dict[str, Any]:
    """Count useful high-confidence findings and high-confidence false positives."""
    threshold = corpus["confidence_threshold"]
    expected = {
        (case["id"], case["accepted_finding"]["id"]): case for case in corpus["cases"]
    }
    useful: list[dict[str, object]] = []
    false_positives: list[dict[str, object]] = []
    suppressed = 0
    seen_expected: set[tuple[str, str]] = set()
    high_confidence_count = 0
    for finding in run_record.get("findings", []):
        if not isinstance(finding, dict):
            continue
        confidence = finding.get("confidence")
        introduced_status = finding.get("introduced_status")
        if not isinstance(confidence, (int, float)) or confidence < threshold:
            suppressed += 1
            continue
        if introduced_status != "introduced":
            suppressed += 1
            continue
        high_confidence_count += 1
        key = (finding.get("case_id"), finding.get("finding_id"))
        expected_case = expected.get(key)
        evidence_paths = finding.get("evidence_paths")
        expected_evidence = (
            set(expected_case["accepted_finding"]["evidence_paths"])
            if expected_case is not None
            else set()
        )
        has_evidence = isinstance(evidence_paths, list) and expected_evidence.issubset(
            set(evidence_paths)
        )
        if expected_case is not None and has_evidence and key not in seen_expected:
            useful.append({"case_id": key[0], "finding_id": key[1]})
            seen_expected.add(key)
        else:
            false_positives.append(
                {
                    "case_id": finding.get("case_id", "unassigned"),
                    "finding_id": finding.get("finding_id", "unidentified"),
                }
            )
    useful_count = len(useful)
    return {
        "schema_version": "1.0",
        "useful_findings": useful,
        "false_positives": false_positives,
        "aggregate": {
            "expected_useful_findings": len(expected),
            "useful_bugs_found": useful_count,
            "useful_bug_find_rate": round(useful_count / len(expected), 4)
            if expected
            else 0.0,
            "high_confidence_findings": high_confidence_count,
            "false_positives": len(false_positives),
            "false_positive_rate": round(
                len(false_positives) / high_confidence_count, 4
            )
            if high_confidence_count
            else 0.0,
            "suppressed_low_confidence_or_pre_existing": suppressed,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "score"))
    parser.add_argument(
        "--corpus",
        default="benchmarks/agent-engineering/final-engineering-review.json",
    )
    parser.add_argument(
        "--task-corpus", default="benchmarks/agent-engineering/cases.json"
    )
    parser.add_argument("--run-record", default="")
    args = parser.parse_args()
    corpus_path = (ROOT / args.corpus).resolve()
    if args.command == "validate":
        report = validate_review_corpus(
            corpus_path,
            task_corpus_path=(ROOT / args.task_corpus).resolve(),
            root=ROOT,
        )
        exit_code = 0 if report["passed"] else 1
    else:
        if not args.run_record:
            parser.error("score requires --run-record")
        report = score_review_run(
            _load_json(corpus_path), _load_json((ROOT / args.run_record).resolve())
        )
        exit_code = 0
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
