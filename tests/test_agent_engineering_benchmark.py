from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest
from scripts.quality.agent_engineering_benchmark import (
    prepare_evaluator_worktree,
    score_run,
    validate_corpus,
    validate_protocol,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks" / "agent-engineering" / "cases.json"
PROTOCOL = ROOT / "benchmarks" / "agent-engineering" / "pre-phase1-protocol.json"
INJECTIONS = ROOT / "benchmarks" / "agent-engineering" / "evaluator-injections.json"


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


def test_score_run_preserves_unavailable_measurements_without_historical_scope_penalty() -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    case_id = corpus["cases"][0]["id"]
    run_record = {
        "schema_version": "1.0",
        "agent": {"name": "Codex", "version": "test"},
        "cases": [
            {
                "case_id": case_id,
                "correct_completion": True,
                "architecture_policy_compliant": True,
                "files_discovered": corpus["cases"][0]["ground_truth"][
                    "historical_reference_files"
                ],
                "files_modified": [
                    *corpus["cases"][0]["ground_truth"][
                        "historical_reference_files"
                    ],
                    "README.md",
                ],
                "verified_scope_violations": [],
                "checks_executed": corpus["cases"][0]["verification"][
                    "required_checks"
                ],
                "check_results": [
                    {"command": command, "returncode": 0}
                    for command in corpus["cases"][0]["verification"][
                        "required_checks"
                    ]
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
    assert report["aggregate"]["historical_reference_file_recall"] == 1.0
    assert report["aggregate"]["verified_scope_violation_count"] == 0
    assert report["aggregate"]["required_checks_executed"] == 1.0
    assert report["aggregate"]["token_usage_status"] == "unavailable"
    assert report["aggregate"]["estimated_cost_usd_status"] == "unavailable"
    assert report["aggregate"]["human_intervention_count"] == 0
    assert report["aggregate"]["rework_count"] == 0
    assert report["cases"][0]["score"] == 100.0


def test_score_run_keeps_historical_reference_recall_diagnostic_only() -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    case = corpus["cases"][0]
    run_record = {
        "schema_version": "2.0",
        "cases": [
            {
                "case_id": case["id"],
                "correct_completion": True,
                "architecture_policy_compliant": True,
                "files_discovered": [],
                "files_modified": ["README.md"],
                "verified_scope_violations": [],
                "checks_executed": case["verification"]["required_checks"],
                "check_results": [
                    {"command": command, "returncode": 0}
                    for command in case["verification"]["required_checks"]
                ],
            }
        ],
    }

    report = score_run(corpus, run_record)

    assert report["cases"][0]["historical_reference_file_recall"] == 0.0
    assert report["cases"][0]["candidate_files_modified"] == ["README.md"]
    assert report["cases"][0]["verified_scope_violations"] == []
    assert report["cases"][0]["score"] == 100.0


def test_score_run_penalizes_only_evaluator_verified_scope_violations() -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    case = corpus["cases"][0]
    run_record = {
        "schema_version": "2.0",
        "cases": [
            {
                "case_id": case["id"],
                "correct_completion": True,
                "architecture_policy_compliant": True,
                "files_discovered": case["ground_truth"]["historical_reference_files"],
                "files_modified": ["README.md"],
                "verified_scope_violations": [
                    {"path": "README.md", "reason": "unrelated to case outcome"}
                ],
                    "checks_executed": case["verification"]["required_checks"],
                    "check_results": [
                        {"command": item, "returncode": 0}
                        for item in case["verification"]["required_checks"]
                    ],
            }
        ],
    }

    report = score_run(corpus, run_record)

    assert report["aggregate"]["verified_scope_violation_count"] == 1
    assert report["cases"][0]["score"] == 99.0


def test_prepare_evaluator_worktree_injects_only_manifest_declared_files(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "benchmark@example.test")
    _git(repository, "config", "user.name", "Benchmark")
    (repository / "tracked.txt").write_text("parent\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-m", "parent")
    parent = _git(repository, "rev-parse", "HEAD").strip()
    (repository / "tests").mkdir()
    (repository / "tests" / "evaluator.py").write_text("assert True\n", encoding="utf-8")
    (repository / "unrelated.txt").write_text("do not inject\n", encoding="utf-8")
    _git(repository, "add", "tests/evaluator.py", "unrelated.txt")
    _git(repository, "commit", "-m", "fix")
    fix_commit = _git(repository, "rev-parse", "HEAD").strip()
    worktree = tmp_path / "candidate"
    _git(repository, "worktree", "add", "--detach", str(worktree), parent)
    manifest = {
        "schema_version": "1.0",
        "injection_version": "test-v1",
        "cases": {
            "ML-TEST-001": {
                "starting_revision": parent,
                "source_revision": fix_commit,
                "files": [
                    {
                        "path": "tests/evaluator.py",
                        "sha256": hashlib.sha256(b"assert True\n").hexdigest(),
                        "kind": "regression_test",
                    }
                ],
            }
        },
    }

    result = prepare_evaluator_worktree(
        case_id="ML-TEST-001",
        worktree=worktree,
        manifest=manifest,
        root=repository,
    )

    assert result["injection_version"] == "test-v1"
    assert result["starting_revision"] == parent
    assert result["source_revision"] == fix_commit
    assert result["files"] == [
        {
            "path": "tests/evaluator.py",
            "kind": "regression_test",
            "sha256": hashlib.sha256(b"assert True\n").hexdigest(),
        }
    ]
    assert (worktree / "tests" / "evaluator.py").read_text(encoding="utf-8") == "assert True\n"
    assert not (worktree / "unrelated.txt").exists()
    _git(repository, "worktree", "remove", "--force", str(worktree))


def test_prepare_evaluator_worktree_refuses_a_non_parent_revision(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "benchmark@example.test")
    _git(repository, "config", "user.name", "Benchmark")
    (repository / "tracked.txt").write_text("parent\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-m", "parent")
    parent = _git(repository, "rev-parse", "HEAD").strip()
    (repository / "tests").mkdir()
    (repository / "tests" / "evaluator.py").write_text("assert True\n", encoding="utf-8")
    _git(repository, "add", "tests/evaluator.py")
    _git(repository, "commit", "-m", "fix")
    fix_commit = _git(repository, "rev-parse", "HEAD").strip()
    worktree = tmp_path / "candidate"
    _git(repository, "worktree", "add", "--detach", str(worktree), parent)
    manifest = {
        "schema_version": "1.0",
        "injection_version": "test-v1",
        "cases": {
            "ML-TEST-001": {
                "starting_revision": fix_commit,
                "source_revision": fix_commit,
                "files": [
                    {
                        "path": "tests/evaluator.py",
                        "sha256": hashlib.sha256(b"assert True\n").hexdigest(),
                    }
                ],
            }
        },
    }

    with pytest.raises(ValueError, match="starting_revision_mismatch"):
        prepare_evaluator_worktree(
            case_id="ML-TEST-001",
            worktree=worktree,
            manifest=manifest,
            root=repository,
        )

    assert not (worktree / "tests" / "evaluator.py").exists()
    _git(repository, "worktree", "remove", "--force", str(worktree))


def test_pre_phase1_protocol_freezes_ten_comparison_cases_and_six_holdouts() -> None:
    report = validate_protocol(
        corpus_path=CORPUS,
        protocol_path=PROTOCOL,
        injections_path=INJECTIONS,
        root=ROOT,
    )

    assert report["passed"] is True
    assert report["comparison_case_count"] == 10
    assert report["holdout_case_count"] == 6
    assert report["failures"] == []


def _git(repository: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repository, text=True, stderr=subprocess.STDOUT
    )
