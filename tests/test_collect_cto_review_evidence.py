# ruff: noqa: E501

import csv
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from scripts.quality.collect_cto_review_evidence import (
    DuplicateEvidenceRunIdError,
    EvidencePaths,
    RequiredEvidenceDatabaseError,
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
