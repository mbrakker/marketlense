# ruff: noqa: E501,F401,F403,F405

import csv
import json
import os
import sqlite3
import subprocess
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.quality._cto_review_evidence.cto_evidence import (
    _execution_plan_reconciliation_status,
)
from scripts.quality._cto_review_evidence.log_content_leakage import (
    Canary,
    _build_matcher,
)
from scripts.quality.collect_cto_review_evidence import (
    ROOT,
    DuplicateEvidenceRunIdError,
    EvidenceCoverageError,
    EvidencePaths,
    LogContentLeakageError,
    LogCorpusScopeError,
    RepositoryHeadChangedError,
    RepositoryHeadMismatchError,
    RepositoryShaMismatchError,
    RepositoryStateUnavailableError,
    RepositoryWorktreeDirtyError,
    RequiredEvidenceDatabaseError,
    RetainedArtifactEvidenceError,
    RowCountMismatchError,
    SnapshotIntegrityError,
    collect,
    validate_consistency,
)


def _seed_state(
    tmp_path: Path,
    *,
    costs: tuple[float, ...] = (0.1,),
    wal: bool = False,
) -> tuple[Path, Path]:
    state = tmp_path / "state"
    state.mkdir()
    with sqlite3.connect(state / "reports.sqlite") as db:
        db.execute(
            "CREATE TABLE publisher_download_route_history (route_family,route_kind,outcome,route_status,attempts,verified_successes,route_steps_json,browser_had_structured_result,onsite_capture_path)"
        )
        db.execute(
            "INSERT INTO publisher_download_route_history VALUES ('direct','pdf','downloaded','verified',2,2,'[]',0,'')"
        )
        db.execute(
            "CREATE TABLE artifact_lineage_records (artifact_id,artifact_kind,report_id,producer)"
        )
        db.execute("CREATE TABLE artifact_lineage_states (artifact_id,state)")
        db.execute(
            "INSERT INTO artifact_lineage_records VALUES ('a','source_pdf','r','selection')"
        )
        db.execute("INSERT INTO artifact_lineage_states VALUES ('a','active')")
    db.close()
    usage_path = state / "llm_usage.sqlite"
    with sqlite3.connect(usage_path) as db:
        if wal:
            assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        db.execute(
            "CREATE TABLE llm_usage_events (timestamp_utc,provider,model,action,semantic_task,prompt_namespace,provider_call_status,input_tokens,cached_input_tokens,output_tokens,total_tokens,estimated_cost_usd)"
        )
        for index, cost in enumerate(costs, start=1):
            db.execute(
                "INSERT INTO llm_usage_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"2026-01-{index:02d}T00:00:00Z",
                    "openai",
                    "m",
                    "openai_ocr_pdf",
                    "ocr",
                    "",
                    "completed",
                    1,
                    0,
                    2,
                    3,
                    cost,
                ),
            )
    db.close()
    return state, usage_path


def _seed_acquisition_resource(
    state: Path,
    *,
    publisher: str,
    route: str,
    outcome: str,
    elapsed_ms: int = 0,
    browser_launches: int = 0,
    browser_steps: int = 0,
    page_navigations: int = 0,
    screenshots: int = 0,
    browser_model_calls: int = 0,
    input_tokens: int = 0,
    cached_input_tokens: int = 0,
    output_tokens: int = 0,
    drive_reads: int = 0,
    drive_writes: int = 0,
    mailbox_reads: int = 0,
    retry_count: int = 0,
    cost: float = 0.0,
    verified_artifact_hash: str | None = None,
) -> None:
    with sqlite3.connect(state / "reports.sqlite") as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS acquisition_attempt_resources (
              publisher_id, route_family, terminal_outcome, elapsed_ms,
              browser_launches, browser_steps, page_navigations, screenshots,
              browser_model_calls, input_tokens, cached_input_tokens,
              output_tokens, drive_reads, drive_writes, mailbox_reads,
              retry_count, estimated_cost_usd, verified_artifact_hash
            )
            """
        )
        db.execute(
            """
            INSERT INTO acquisition_attempt_resources VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                publisher,
                route,
                outcome,
                elapsed_ms,
                browser_launches,
                browser_steps,
                page_navigations,
                screenshots,
                browser_model_calls,
                input_tokens,
                cached_input_tokens,
                output_tokens,
                drive_reads,
                drive_writes,
                mailbox_reads,
                retry_count,
                cost,
                (
                    "md5:verified"
                    if verified_artifact_hash is None and outcome == "success"
                    else str(verified_artifact_hash or "")
                ),
            ),
        )


def _paths(
    tmp_path: Path, state: Path, *, output_name: str = "evidence"
) -> EvidencePaths:
    return EvidencePaths(
        state,
        tmp_path / "artifacts",
        tmp_path / output_name,
        workspace_parent=tmp_path,
    )


def _summary(output: Path) -> dict[str, object]:
    return json.loads((output / "executive_summary.json").read_text(encoding="utf-8"))


def _retained_paragraph(kind: str, index: int) -> str:
    return (
        f"Synthetic {kind} paragraph {index} describes a specific retained market "
        "finding with enough independently meaningful detail to distinguish it from "
        "ordinary operational messages. It records a concrete trend, supporting "
        "context, decision implications, and a bounded interpretation for the review "
        "sample without using any production report content."
    )


def _seed_retained_report_artifacts(tmp_path: Path) -> tuple[Path, str, str]:
    artifact_root = tmp_path / "retained"
    source_first = ""
    editorial_first = ""
    for index in range(5):
        report = artifact_root / f"report-{index:02d}" / "report_analysis"
        report.mkdir(parents=True)
        source = _retained_paragraph("source", index)
        editorial = _retained_paragraph("editorial", index)
        (report / "doc_map.json").write_text(
            json.dumps(
                {"sections": [{"title": f"Section {index}", "summary": source}]}
            ),
            encoding="utf-8",
        )
        (report / "artifacts.json").write_text(
            json.dumps(
                {
                    "schema_version": "3.0",
                    "linkedin_post": editorial,
                    "expert_comment": editorial,
                }
            ),
            encoding="utf-8",
        )
        if index == 0:
            source_first = source
            editorial_first = editorial
    return artifact_root, source_first, editorial_first


def _seed_standard_log(tmp_path: Path, payload: str = "safe operational event") -> Path:
    log_dir = tmp_path / "logs"
    log_dir.mkdir(exist_ok=True)
    path = log_dir / "market_lense_2026-07-16.log"
    path.write_text(
        f'12:00:00 | INFO | market_lense.test | {{"event":"test_event","message":{json.dumps(payload)}}}\n',
        encoding="utf-8",
    )
    return log_dir


def _init_git_repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init"], cwd=repository, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.invalid"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Evidence Tests"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    (repository / "tracked.txt").write_text("initial\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "tracked.txt"], cwd=repository, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repository, sha


def _strict_paths(tmp_path: Path) -> tuple[EvidencePaths, str, str, str]:
    state, _ = _seed_state(tmp_path)
    artifacts, source, editorial = _seed_retained_report_artifacts(tmp_path)
    log_dir = _seed_standard_log(tmp_path)
    repository, sha = _init_git_repository(tmp_path)
    return (
        EvidencePaths(
            state,
            artifacts,
            tmp_path / "evidence",
            log_dir=log_dir,
            require_exact_head=True,
            expected_commit_sha=sha,
            repository_root=repository,
            workspace_parent=tmp_path,
        ),
        sha,
        source,
        editorial,
    )


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
