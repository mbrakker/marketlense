from __future__ import annotations

import json
from pathlib import Path

from scripts.quality.agent_engineering_benchmark import score_run, validate_corpus

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks" / "agent-engineering" / "cases.json"


def test_agent_engineering_corpus_has_traceable_representative_cases() -> None:
    report = validate_corpus(CORPUS, root=ROOT)

    assert report["passed"] is True
    assert report["case_count"] == 16
    assert report["category_counts"] == {
        "architecture_investigation": 2,
        "browser_acquisition": 3,
        "bug_fix": 2,
        "feature_implementation": 2,
        "llm_prompt_pipeline": 2,
        "pdf_visual_extraction": 2,
        "performance_cost": 1,
        "service_boundary_refactor": 2,
    }
    assert report["failures"] == []


def test_score_run_penalizes_scope_and_preserves_unavailable_measurements() -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    case_id = corpus["cases"][0]["id"]
    run_record = {
        "schema_version": "1.0",
        "agent": {"name": "Codex", "version": "test"},
        "cases": [
            {
                "case_id": case_id,
                "correct_completion": True,
                "files_discovered": corpus["cases"][0]["ground_truth"][
                    "relevant_files"
                ],
                "files_modified": [
                    *corpus["cases"][0]["ground_truth"]["allowed_modified_files"],
                    "README.md",
                ],
                "checks_executed": corpus["cases"][0]["verification"][
                    "required_checks"
                ],
                "tool_file_read_count": 12,
                "elapsed_seconds": 30,
                "token_usage": "unavailable",
                "estimated_cost_usd": "unavailable",
                "human_intervention_count": 0,
                "rework_count": 0,
            }
        ],
    }

    report = score_run(corpus, run_record)

    assert report["aggregate"]["correct_completion"] == 1.0
    assert report["aggregate"]["relevant_files_discovered"] == 1.0
    assert report["aggregate"]["irrelevant_files_modified"] == 1
    assert report["aggregate"]["required_checks_executed"] == 1.0
    assert report["aggregate"]["token_usage_status"] == "unavailable"
    assert report["aggregate"]["estimated_cost_usd_status"] == "unavailable"
    assert report["aggregate"]["human_intervention_count"] == 0
    assert report["aggregate"]["rework_count"] == 0
    assert report["cases"][0]["score"] == 99.0
