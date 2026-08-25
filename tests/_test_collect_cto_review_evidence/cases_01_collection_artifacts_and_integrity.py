# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_collect_cto_review_evidence.py"
)

from ._shared import *  # noqa: F401,F403


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
    _seed_acquisition_resource(
        state,
        publisher="publisher",
        route="direct",
        outcome="success",
    )
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
        assert next(csv.DictReader(handle))["attempts"] == "1"
    with (output / "ocr_vision_metrics.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert next(csv.DictReader(handle))["request_count"] == "1"


def test_collect_uses_task_scoped_acquisition_resources_for_cto_metrics(
    tmp_path: Path,
) -> None:
    state, _ = _seed_state(tmp_path)
    _seed_acquisition_resource(
        state,
        publisher="bcg",
        route="browser_pdf_click",
        outcome="success",
        elapsed_ms=1250,
        browser_launches=1,
        browser_steps=6,
        page_navigations=2,
        screenshots=1,
        browser_model_calls=3,
        input_tokens=110,
        cached_input_tokens=25,
        output_tokens=11,
        drive_writes=1,
        retry_count=2,
        cost=0.031,
    )
    _seed_acquisition_resource(
        state,
        publisher="barclays",
        route="http_direct",
        outcome="failed",
        elapsed_ms=250,
    )

    output = tmp_path / "evidence"
    collect(EvidencePaths(state, tmp_path / "artifacts", output))

    with (output / "acquisition_metrics.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    by_publisher = {row["publisher"]: row for row in rows}

    assert set(by_publisher) == {"barclays", "bcg"}
    assert by_publisher["bcg"] == {
        "publisher": "bcg",
        "route_family": "browser_pdf_click",
        "terminal_outcome": "success",
        "sample_size": "1",
        "attempts": "1",
        "successes": "1",
        "duration_seconds": "1.25",
        "estimated_cost_usd": "0.031",
        "browser_launches": "1",
        "browser_steps": "6",
        "page_navigations": "2",
        "screenshots": "1",
        "browser_model_calls": "3",
        "input_tokens": "110",
        "cached_input_tokens": "25",
        "output_tokens": "11",
        "drive_reads": "0",
        "drive_writes": "1",
        "mailbox_reads": "0",
        "retry_count": "2",
    }


def test_collect_does_not_count_execution_success_without_verified_artifact(
    tmp_path: Path,
) -> None:
    state, _ = _seed_state(tmp_path)
    _seed_acquisition_resource(
        state,
        publisher="publisher",
        route="browser_email_form",
        outcome="success",
        verified_artifact_hash="",
    )
    _seed_acquisition_resource(
        state,
        publisher="publisher",
        route="browser_email_form",
        outcome="success",
        verified_artifact_hash="md5:verified",
    )

    output = tmp_path / "evidence"
    collect(EvidencePaths(state, tmp_path / "artifacts", output))

    with (output / "acquisition_metrics.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        row = next(csv.DictReader(handle))
    assert row["attempts"] == "2"
    assert row["successes"] == "1"
    telemetry = json.loads(
        (output / "runtime_telemetry.json").read_text(encoding="utf-8")
    )
    assert (
        telemetry["browser_per_acquired_report"]["values"]["acquired_report_count"] == 1
    )


def test_collect_writes_named_cto_evidence_artifacts_from_snapshots(
    tmp_path: Path,
) -> None:
    state, _ = _seed_state(tmp_path)
    _seed_acquisition_resource(
        state,
        publisher="publisher",
        route="direct",
        outcome="success",
    )
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
                validation_status='passed', lineage_status='complete'
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
            "active_completeness_percentage": 100.0,
            "all_history_completeness_percentage": 100.0,
            "artifact_count": 1,
            "artifact_family": "source_pdf",
            "complete_active_count": 1,
            "complete_history_count": 1,
            "missing_field_counts": {},
            "processing_version_distribution": {"1.0": 1},
            "schema_version_distribution": {"1.0": 1},
            "superseded_count": 0,
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


def test_manifest_retains_relative_state_namespace(tmp_path: Path) -> None:
    state, _ = _seed_state(tmp_path)
    paths = _paths(tmp_path, state)

    collect(paths)

    manifest = json.loads(
        (paths.output_dir / "evidence_run_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["configuration"]["state_dir"] == "state"


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


__all__ = [
    "test_collect_reads_local_state_and_writes_aggregate_csvs",
    "test_collect_uses_task_scoped_acquisition_resources_for_cto_metrics",
    "test_collect_does_not_count_execution_success_without_verified_artifact",
    "test_collect_writes_named_cto_evidence_artifacts_from_snapshots",
    "test_execution_plan_reconciliation_prefers_production_status_and_falls_back_safely",
    "test_collect_writes_requested_validated_evidence_archive",
    "test_collect_uses_snapshot_when_live_usage_changes_after_snapshot",
    "test_collect_snapshots_wal_backed_database",
    "test_summary_totals_match_finalized_detailed_artifacts",
    "test_summary_mismatch_fails_closed",
    "test_architecture_manifest_commit_mismatch_fails_closed",
    "test_corrupted_snapshot_fails_integrity_validation_and_cleans_workspace",
    "test_optional_databases_are_recorded_without_failure",
    "test_missing_required_database_fails_with_typed_error_and_cleans_workspace",
    "test_temporary_snapshots_are_cleaned_after_success",
    "test_repeated_collection_is_semantically_identical_except_run_identity",
    "test_public_evidence_paths_do_not_expose_absolute_workspace_paths",
    "test_manifest_retains_relative_state_namespace",
    "test_duplicate_explicit_evidence_run_id_fails_closed",
]
