from __future__ import annotations

import json
from pathlib import Path

from scripts.quality.final_engineering_review_benchmark import (
    score_review_run,
    validate_review_corpus,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks" / "agent-engineering" / "final-engineering-review.json"
TASK_CORPUS = ROOT / "benchmarks" / "agent-engineering" / "cases.json"


def test_review_benchmark_cases_are_traceable_to_historical_tasks() -> None:
    report = validate_review_corpus(CORPUS, task_corpus_path=TASK_CORPUS, root=ROOT)

    assert report["passed"] is True
    assert report["case_count"] == 6
    assert report["reviewer_counts"] == {
        "architecture_simplicity": 2,
        "correctness": 2,
        "regression_testing": 2,
    }
    assert report["failures"] == []


def test_review_score_counts_useful_findings_and_false_positives() -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    expected = corpus["cases"][0]
    source_path = expected["accepted_finding"]["evidence_paths"][0]
    run_record = {
        "schema_version": "1.0",
        "findings": [
            {
                "case_id": expected["id"],
                "finding_id": expected["accepted_finding"]["id"],
                "confidence": 92,
                "introduced_status": "introduced",
                "evidence_paths": [source_path],
            },
            {
                "case_id": expected["id"],
                "finding_id": "unrelated-style-observation",
                "confidence": 91,
                "introduced_status": "introduced",
                "evidence_paths": [source_path],
            },
            {
                "case_id": corpus["cases"][1]["id"],
                "finding_id": corpus["cases"][1]["accepted_finding"]["id"],
                "confidence": 99,
                "introduced_status": "pre_existing",
                "evidence_paths": [
                    corpus["cases"][1]["accepted_finding"]["evidence_paths"][0]
                ],
            },
        ],
    }

    report = score_review_run(corpus, run_record)

    assert report["aggregate"] == {
        "expected_useful_findings": 6,
        "useful_bugs_found": 1,
        "useful_bug_find_rate": 0.1667,
        "high_confidence_findings": 2,
        "false_positives": 1,
        "false_positive_rate": 0.5,
        "suppressed_low_confidence_or_pre_existing": 1,
    }
