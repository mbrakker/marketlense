# ruff: noqa: E501

import csv
import json
import os
import sqlite3
import subprocess
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.quality._cto_review_evidence.log_content_leakage import (
    Canary,
    _build_matcher,
)
from scripts.quality._cto_review_evidence.cto_evidence import (
    _execution_plan_reconciliation_status,
)
from scripts.quality.collect_cto_review_evidence import (
    ROOT,
    ArtifactIntegrityError,
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


def test_collect_reads_local_state_and_writes_aggregate_csvs(tmp_path: Path) -> None:
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
    with sqlite3.connect(state / "llm_usage.sqlite") as db:
        db.execute(
            "CREATE TABLE llm_usage_events (timestamp_utc,provider,model,action,semantic_task,prompt_namespace,provider_call_status,input_tokens,cached_input_tokens,output_tokens,total_tokens,estimated_cost_usd)"
        )
        db.execute(
            "INSERT INTO llm_usage_events VALUES ('2026-01-01T00:00:00Z','openai','m','openai_ocr_pdf','ocr','','completed',1,0,2,3,0.1)"
        )
    output = tmp_path / "evidence"
    collect(EvidencePaths(state, tmp_path / "artifacts", output))
    with (output / "acquisition_metrics.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert next(csv.DictReader(handle))["attempts"] == "2"
    with (output / "ocr_vision_metrics.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert next(csv.DictReader(handle))["request_count"] == "1"


def test_collect_writes_named_cto_evidence_artifacts_from_snapshots(
    tmp_path: Path,
) -> None:
    state, _ = _seed_state(tmp_path)
    with sqlite3.connect(state / "reports.sqlite") as db:
        for column in (
            "source_id",
            "content_hash",
            "storage_ref",
            "schema_version_used",
            "processing_version",
            "validation_status",
            "lineage_status",
        ):
            db.execute(f"ALTER TABLE artifact_lineage_records ADD COLUMN {column}")
        db.execute(
            """
            UPDATE artifact_lineage_records
            SET source_id='source-1', content_hash='hash-1', storage_ref='safe-ref',
                schema_version_used='1.0', processing_version='1.0',
                validation_status='passed', lineage_status='verified'
            """
        )
        db.execute(
            """
            CREATE TABLE artifact_execution_plan_runs (
              plan_hash, report_id, execution_intent, execution_mode,
              planned_stages_json, actual_stages_json,
              planned_external_calls_json, actual_external_calls_json,
              planned_side_effects_json, actual_side_effects_json,
              reusable_artifact_ids_json, divergence_json, actual_cost_usd,
              execution_status
            )
            """
        )
        db.execute(
            """
            INSERT INTO artifact_execution_plan_runs VALUES
            ('plan-1','report-1','render','enforce','["render"]','["render"]',
             '["html_render"]','["html_render"]','["filesystem"]',
             '["filesystem"]','["a"]',
             '{"reconciliation_status":"matched","avoided_planned_external_calls":[]}',
             0.2,'completed')
            """
        )
    paths = _paths(tmp_path, state, output_name="CTO_evidence")

    collect(paths)

    expected = {
        "README.md",
        "workflow_to_remediation_coverage.json",
        "artifact_lineage_completeness.json",
        "architecture_manifest.json",
        "source_identity_schema.json",
        "editorial_rule_catalog.json",
        "effective_run_profile_matrix.json",
        "github_main_status.json",
        "runtime_telemetry.json",
    }
    assert expected <= {path.name for path in paths.output_dir.iterdir()}
    assert (paths.output_dir / "README.md").read_text(encoding="utf-8") == (
        ROOT / "docs/CTO_evidence/README.md"
    ).read_text(encoding="utf-8")

    lineage = json.loads(
        (paths.output_dir / "artifact_lineage_completeness.json").read_text(
            encoding="utf-8"
        )
    )
    assert lineage["status"] == "available"
    assert lineage["families"] == [
        {
            "active_count": 1,
            "artifact_count": 1,
            "artifact_family": "source_pdf",
            "complete_count": 1,
            "completeness_percentage": 100.0,
        }
    ]
    telemetry = json.loads(
        (paths.output_dir / "runtime_telemetry.json").read_text(encoding="utf-8")
    )
    assert (
        telemetry["acquisition_by_publisher_and_route"]["values"]["rows"][0][
            "successful_acquisition_rate"
        ]
        == 1.0
    )
    assert telemetry["minimal_plan_actual_call_divergence"]["values"]["rows"] == [
        {
            "actual_call_count": 1,
            "divergent_plan_count": 0,
            "enforcement_deferred_or_blocked_count": 0,
            "execution_intent": "render",
            "execution_mode": "enforce",
            "matching_plan_count": 1,
            "plan_count": 1,
            "planned_call_count": 1,
            "unreconciled_plan_count": 0,
        }
    ]
    assert (
        json.loads(
            (paths.output_dir / "github_main_status.json").read_text(encoding="utf-8")
        )["reason"]
        == "github_status_not_requested"
    )


def test_execution_plan_reconciliation_prefers_production_status_and_falls_back_safely() -> (
    None
):
    matched = {
        "planned_stages_json": '["render"]',
        "actual_stages_json": '["render"]',
        "planned_external_calls_json": '["html_render", "model"]',
        "actual_external_calls_json": '["html_render"]',
        "planned_side_effects_json": '["filesystem"]',
        "actual_side_effects_json": '["filesystem"]',
        "divergence_json": json.dumps(
            {
                "reconciliation_status": "matched",
                "avoided_planned_external_calls": ["model"],
            }
        ),
    }
    reordered_historical = {
        "planned_stages_json": '["analysis", "render"]',
        "actual_stages_json": '["render", "analysis"]',
        "planned_external_calls_json": '["model", "filesystem"]',
        "actual_external_calls_json": '["filesystem", "model"]',
        "planned_side_effects_json": '["filesystem"]',
        "actual_side_effects_json": '["filesystem"]',
        "divergence_json": "{}",
    }
    unplanned = {
        **reordered_historical,
        "actual_external_calls_json": '["filesystem", "model", "network"]',
    }

    assert _execution_plan_reconciliation_status(matched) == "matched"
    assert _execution_plan_reconciliation_status(reordered_historical) == "matched"
    assert _execution_plan_reconciliation_status(unplanned) == "diverged"
    assert (
        _execution_plan_reconciliation_status(
            {**reordered_historical, "actual_external_calls_json": "not-json"}
        )
        == "unreconciled"
    )


def test_collect_writes_requested_validated_evidence_archive(tmp_path: Path) -> None:
    state, _ = _seed_state(tmp_path)
    archive_path = tmp_path / "docs" / "cto-review-evidence.zip"
    paths = EvidencePaths(
        state,
        tmp_path / "artifacts",
        tmp_path / "evidence",
        workspace_parent=tmp_path,
        archive_path=archive_path,
    )

    generated = collect(paths)

    assert archive_path in generated
    with zipfile.ZipFile(archive_path) as archive:
        assert "consistency_validation.json" in archive.namelist()
        assert "executive_summary.json" in archive.namelist()


def test_collect_uses_snapshot_when_live_usage_changes_after_snapshot(
    tmp_path: Path,
) -> None:
    state, usage_path = _seed_state(tmp_path)

    def add_live_event(_: dict[str, Path]) -> None:
        with sqlite3.connect(usage_path) as db:
            db.execute(
                "INSERT INTO llm_usage_events VALUES ('2026-02-01T00:00:00Z','openai','m','openai_ocr_pdf','ocr','','completed',1,0,2,3,0.1)"
            )

    paths = _paths(tmp_path, state)
    collect(paths, _after_snapshot=add_live_event)

    assert _summary(paths.output_dir)["totals"]["llm"]["call_count"] == 1


def test_collect_snapshots_wal_backed_database(tmp_path: Path) -> None:
    state, _ = _seed_state(tmp_path, wal=True)
    paths = _paths(tmp_path, state)

    collect(paths)

    manifest = json.loads(
        (paths.output_dir / "snapshot_manifest.json").read_text(encoding="utf-8")
    )
    usage = next(
        entry
        for entry in manifest["snapshots"]
        if entry["logical_database_name"] == "llm_usage"
    )
    assert usage["journal_mode"] == "wal"
    assert _summary(paths.output_dir)["totals"]["llm"]["call_count"] == 1


def test_summary_totals_match_finalized_detailed_artifacts(tmp_path: Path) -> None:
    state, _ = _seed_state(tmp_path, costs=(0.1, 0.2))
    paths = _paths(tmp_path, state)

    collect(paths)
    validate_consistency(
        paths.output_dir,
        expected_run_id=json.loads(
            (paths.output_dir / "detailed_metrics.json").read_text(encoding="utf-8")
        )["evidence_run_id"],
    )

    llm = _summary(paths.output_dir)["totals"]["llm"]
    assert llm == {
        "call_count": 2,
        "input_tokens": 2,
        "output_tokens": 4,
        "total_tokens": 6,
        "estimated_cost_usd": "0.3",
    }


def test_summary_mismatch_fails_closed(tmp_path: Path) -> None:
    state, _ = _seed_state(tmp_path)
    paths = _paths(tmp_path, state)
    collect(paths)
    summary_path = paths.output_dir / "executive_summary.json"
    summary = _summary(paths.output_dir)
    summary["totals"]["llm"]["call_count"] = 99
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(RowCountMismatchError):
        validate_consistency(
            paths.output_dir,
            expected_run_id=json.loads(
                (paths.output_dir / "detailed_metrics.json").read_text(encoding="utf-8")
            )["evidence_run_id"],
        )


def test_architecture_manifest_commit_mismatch_fails_closed(tmp_path: Path) -> None:
    state, _ = _seed_state(tmp_path)
    paths = _paths(tmp_path, state)
    collect(paths)
    architecture_path = paths.output_dir / "architecture_manifest.json"
    architecture = json.loads(architecture_path.read_text(encoding="utf-8"))
    architecture["repository_commit_sha"] = "0" * 40
    architecture_path.write_text(json.dumps(architecture), encoding="utf-8")

    with pytest.raises(RepositoryShaMismatchError):
        validate_consistency(
            paths.output_dir,
            expected_run_id=json.loads(
                (paths.output_dir / "detailed_metrics.json").read_text(encoding="utf-8")
            )["evidence_run_id"],
        )


def test_corrupted_snapshot_fails_integrity_validation_and_cleans_workspace(
    tmp_path: Path,
) -> None:
    state, _ = _seed_state(tmp_path)
    paths = _paths(tmp_path, state)

    def corrupt(snapshots: dict[str, Path]) -> None:
        snapshots["llm_usage"].write_bytes(b"not a sqlite database")

    with pytest.raises(SnapshotIntegrityError):
        collect(paths, _after_snapshot=corrupt)

    assert not list(tmp_path.glob("cto_evidence_*"))


def test_optional_databases_are_recorded_without_failure(tmp_path: Path) -> None:
    state, _ = _seed_state(tmp_path)
    paths = _paths(tmp_path, state)

    collect(paths)

    manifest = json.loads(
        (paths.output_dir / "snapshot_manifest.json").read_text(encoding="utf-8")
    )
    optional = {
        entry["logical_database_name"]: entry["source_accessibility"]
        for entry in manifest["snapshots"]
    }
    assert optional["index"] == "missing_optional"
    assert optional["ui_runs"] == "missing_optional"


def test_missing_required_database_fails_with_typed_error_and_cleans_workspace(
    tmp_path: Path,
) -> None:
    state, usage_path = _seed_state(tmp_path)
    usage_path.unlink()
    paths = _paths(tmp_path, state)

    with pytest.raises(RequiredEvidenceDatabaseError):
        collect(paths)

    assert not list(tmp_path.glob("cto_evidence_*"))


def test_temporary_snapshots_are_cleaned_after_success(tmp_path: Path) -> None:
    state, _ = _seed_state(tmp_path)

    collect(_paths(tmp_path, state))

    assert not list(tmp_path.glob("cto_evidence_*"))


def test_repeated_collection_is_semantically_identical_except_run_identity(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first_state, _ = _seed_state(first_root, costs=(0.1, 0.2))
    second_state, _ = _seed_state(second_root, costs=(0.1, 0.2))
    first = _paths(
        first_root,
        first_state,
        output_name="evidence",
    )
    second = _paths(
        second_root,
        second_state,
        output_name="evidence",
    )

    collect(first)
    collect(second)

    first_detail = json.loads(
        (first.output_dir / "detailed_metrics.json").read_text(encoding="utf-8")
    )
    second_detail = json.loads(
        (second.output_dir / "detailed_metrics.json").read_text(encoding="utf-8")
    )
    assert first_detail["metrics"] == second_detail["metrics"]


def test_public_evidence_paths_do_not_expose_absolute_workspace_paths(
    tmp_path: Path,
) -> None:
    state, _ = _seed_state(tmp_path)
    paths = _paths(tmp_path, state)

    collect(paths)

    rendered = "\n".join(
        (paths.output_dir / name).read_text(encoding="utf-8")
        for name in (
            "snapshot_manifest.json",
            "evidence_run_manifest.json",
            "executive_summary.json",
        )
    )
    assert str(tmp_path) not in rendered
    assert "C:\\" not in rendered


def test_duplicate_explicit_evidence_run_id_fails_closed(tmp_path: Path) -> None:
    state, _ = _seed_state(tmp_path)
    paths = EvidencePaths(
        state,
        tmp_path / "artifacts",
        tmp_path / "evidence",
        evidence_run_id="stable-run",
        workspace_parent=tmp_path,
    )
    collect(paths)

    with pytest.raises(DuplicateEvidenceRunIdError):
        collect(paths)


def test_strict_clean_exact_head_snapshots_logs_and_publishes_redacted_bundle(
    tmp_path: Path,
) -> None:
    paths, sha, source, editorial = _strict_paths(tmp_path)
    (paths.log_dir / "ignored.log").write_text(source, encoding="utf-8")

    collect(paths)

    manifest = json.loads((paths.output_dir / "evidence_run_manifest.json").read_text())
    snapshots = json.loads((paths.output_dir / "snapshot_manifest.json").read_text())
    leakage = json.loads((paths.output_dir / "log_content_leakage.json").read_text())
    validation = json.loads(
        (paths.output_dir / "consistency_validation.json").read_text()
    )
    assert manifest["repository"] == {
        "expected_commit_sha": sha,
        "start_commit_sha": sha,
        "end_commit_sha": sha,
        "head_stable": True,
        "dirty_worktree_start": False,
        "dirty_worktree_end": False,
        "exact_head_verified": True,
    }
    assert snapshots["log_snapshots"][0]["source_path"] == "market_lense_2026-07-16.log"
    assert len(snapshots["log_snapshots"]) == 1
    assert snapshots["log_snapshots"][0]["snapshot_path"].startswith("standard_logs/")
    assert (
        snapshots["log_snapshots"][0]["structured_event_metadata_mode"]
        == "matches_only"
    )
    assert leakage["status"] == "passed"
    assert leakage["coverage"]["source_canary_count"] == 5
    assert leakage["coverage"]["editorial_canary_count"] == 5
    assert validation["passed"] is True
    assert validation["repository_commit_sha"] == sha
    rendered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in paths.output_dir.iterdir()
        if path.suffix in {".json", ".csv"}
    )
    assert source not in rendered
    assert editorial not in rendered
    assert all(
        "sha256" in item and "byte_count" in item
        for item in manifest["artifact_inventory"]
    )


def test_declared_smoke_log_scope_is_explicit_in_public_evidence(
    tmp_path: Path,
) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    paths = EvidencePaths(
        **{
            **paths.__dict__,
            "log_corpus_scope": "post_remediation_smoke_only",
        }
    )

    collect(paths)

    manifest = json.loads((paths.output_dir / "evidence_run_manifest.json").read_text())
    leakage = json.loads((paths.output_dir / "log_content_leakage.json").read_text())
    expected_scope = "post_remediation_smoke_only"
    assert manifest["log_corpus"]["operator_declared_scope"] == expected_scope
    assert leakage["log_corpus"]["operator_declared_scope"] == expected_scope
    assert (
        "post_remediation_smoke_only_no_representative_report_processing"
        in leakage["limitations"]
    )
    assert "does not attest" in manifest["log_corpus"]["repository_provenance"]


def test_unknown_log_corpus_scope_fails_before_snapshot_work(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    paths = EvidencePaths(**{**paths.__dict__, "log_corpus_scope": "unknown"})

    with pytest.raises(LogCorpusScopeError):
        collect(paths)

    assert not paths.output_dir.exists()


def test_strict_expected_commit_mismatch_fails_before_snapshot_work(
    tmp_path: Path,
) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    paths = EvidencePaths(**{**paths.__dict__, "expected_commit_sha": "0" * 40})

    with pytest.raises(RepositoryHeadMismatchError):
        collect(paths)

    assert not paths.output_dir.exists()
    assert not list(tmp_path.glob("cto_evidence_*"))


def test_strict_dirty_worktree_fails(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    (paths.repository_root / "tracked.txt").write_text("changed\n", encoding="utf-8")

    with pytest.raises(RepositoryWorktreeDirtyError):
        collect(paths)


def test_strict_collection_ignores_only_its_staging_directory(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    documentation_dir = paths.repository_root / "docs"
    documentation_dir.mkdir()
    (documentation_dir / ".keep").write_text("\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "docs/.keep"],
        cwd=paths.repository_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "add docs directory"],
        cwd=paths.repository_root,
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=paths.repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    paths = EvidencePaths(
        **{
            **paths.__dict__,
            "output_dir": documentation_dir / "CTO_evidence",
            "expected_commit_sha": sha,
        }
    )

    collect(paths)

    validate_consistency(
        paths.output_dir,
        expected_run_id=json.loads(
            (paths.output_dir / "detailed_metrics.json").read_text(encoding="utf-8")
        )["evidence_run_id"],
        strict=True,
    )


def test_strict_collection_rejects_other_untracked_changes_at_finalization(
    tmp_path: Path,
) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)

    def create_untracked(_: dict[str, Path]) -> None:
        (paths.repository_root / "untracked.txt").write_text(
            "unexpected\n", encoding="utf-8"
        )

    with pytest.raises(RepositoryWorktreeDirtyError):
        collect(paths, _after_snapshot=create_untracked)

    assert not paths.output_dir.exists()


def test_strict_head_change_during_collection_fails_and_does_not_publish(
    tmp_path: Path,
) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)

    def advance_head(_: dict[str, Path]) -> None:
        repository = paths.repository_root
        (repository / "tracked.txt").write_text("next\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
        subprocess.run(["git", "commit", "-m", "next"], cwd=repository, check=True)

    with pytest.raises(RepositoryHeadChangedError):
        collect(paths, _after_snapshot=advance_head)

    assert not paths.output_dir.exists()


def test_strict_unavailable_git_metadata_fails(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    non_repository = tmp_path / "not-a-repository"
    non_repository.mkdir()
    paths = EvidencePaths(**{**paths.__dict__, "repository_root": non_repository})

    with pytest.raises(RepositoryStateUnavailableError):
        collect(paths)


def test_live_log_changes_after_snapshot_do_not_affect_leakage_scan(
    tmp_path: Path,
) -> None:
    paths, _, source, _ = _strict_paths(tmp_path)
    live_log = paths.log_dir / "market_lense_2026-07-16.log"

    def add_leak(_: dict[str, Path]) -> None:
        live_log.write_text(source, encoding="utf-8")

    collect(paths, _after_snapshot=add_leak)

    leakage = json.loads((paths.output_dir / "log_content_leakage.json").read_text())
    assert leakage["passed"] is True


@pytest.mark.parametrize("kind", ["source", "editorial"])
def test_strict_retained_content_in_standard_log_fails_closed(
    tmp_path: Path, kind: str
) -> None:
    paths, _, source, editorial = _strict_paths(tmp_path)
    leaked = source if kind == "source" else editorial
    _seed_standard_log(tmp_path, leaked)

    with pytest.raises(LogContentLeakageError):
        collect(paths)

    assert not paths.output_dir.exists()


def test_json_escaped_and_windowed_retained_content_fail_leakage_assessment(
    tmp_path: Path,
) -> None:
    paths, _, source, _ = _strict_paths(tmp_path)
    normalized = " ".join(source.casefold().split())
    middle = (len(normalized) - 80) // 2
    partial = f"{normalized[:80]} unrelated operational marker {normalized[middle : middle + 80]}"
    _seed_standard_log(tmp_path, json.dumps({"nested": partial}, ensure_ascii=True))

    with pytest.raises(LogContentLeakageError):
        collect(paths)


def test_log_matcher_detects_full_and_windowed_canary_content() -> None:
    content = _retained_paragraph("source", 1)
    canary = Canary(
        canary_class="source",
        report_identity="report-1",
        relative_artifact_path="report-1/report_analysis/doc_map.json",
        field_family="summary",
        normalized_text=" ".join(content.casefold().split()),
    )
    matcher = _build_matcher([canary])

    assert matcher(f"operational record {canary.normalized_text}") == [
        (canary, "full", 0)
    ]

    normalized = canary.normalized_text
    middle = (len(normalized) - 80) // 2
    windowed = f"{normalized[:80]} unrelated marker {normalized[middle : middle + 80]}"
    assert matcher(windowed) == [(canary, "windowed", 2)]


def test_missing_canary_coverage_is_incomplete_and_fails_strict_collection(
    tmp_path: Path,
) -> None:
    state, _ = _seed_state(tmp_path)
    repository, sha = _init_git_repository(tmp_path)
    paths = EvidencePaths(
        state,
        tmp_path / "empty-artifacts",
        tmp_path / "evidence",
        log_dir=_seed_standard_log(tmp_path),
        require_exact_head=True,
        expected_commit_sha=sha,
        repository_root=repository,
        workspace_parent=tmp_path,
    )

    with pytest.raises(EvidenceCoverageError):
        collect(paths)

    assert not paths.output_dir.exists()


def test_corrupt_retained_canary_artifact_fails_closed_in_strict_mode(
    tmp_path: Path,
) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    (paths.artifact_dir / "report-00" / "report_analysis" / "doc_map.json").write_text(
        "{not-json", encoding="utf-8"
    )

    with pytest.raises(RetainedArtifactEvidenceError):
        collect(paths)

    assert not paths.output_dir.exists()


def test_freshness_requires_a_fresh_standard_log(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    old = datetime.now(UTC) - timedelta(days=2)
    log_path = paths.log_dir / "market_lense_2026-07-16.log"
    timestamp = old.timestamp()
    os.utime(log_path, (timestamp, timestamp))
    paths = EvidencePaths(
        **{
            **paths.__dict__,
            "fresh_after": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        }
    )

    with pytest.raises(EvidenceCoverageError):
        collect(paths)


def test_tampered_leakage_artifact_fails_inventory_validation(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    collect(paths)
    leakage_path = paths.output_dir / "log_content_leakage.json"
    leakage = json.loads(leakage_path.read_text())
    leakage["status"] = "failed"
    leakage_path.write_text(json.dumps(leakage), encoding="utf-8")

    with pytest.raises(ArtifactIntegrityError):
        validate_consistency(
            paths.output_dir,
            expected_run_id=json.loads(
                (paths.output_dir / "detailed_metrics.json").read_text()
            )["evidence_run_id"],
            strict=True,
        )


def test_atomic_replace_never_merges_prior_bundle_files(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    collect(paths)
    (paths.output_dir / "old-only.txt").write_text("obsolete", encoding="utf-8")
    replacement = EvidencePaths(
        **{
            **paths.__dict__,
            "replace_output": True,
            "evidence_run_id": "replacement-run",
        }
    )

    collect(replacement)

    assert not (replacement.output_dir / "old-only.txt").exists()
    assert (
        json.loads((replacement.output_dir / "evidence_run_manifest.json").read_text())[
            "evidence_run_id"
        ]
        == "replacement-run"
    )
