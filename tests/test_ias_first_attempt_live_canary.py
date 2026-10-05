import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import scripts.quality.ias_live_canary_runner as canary_runner
from scripts.quality.ias_live_canary_runner import (
    _collect_frozen_cohort_queue_timing_evidence,
    _read_retained_claim_counts,
    _seed_isolated_workflow_queue_controls,
    ensure_isolated_publication_queue_disabled,
    prepare_isolated_canary_run,
    run_ias_first_attempt_canary,
)
from src.contracts.config import ConfigLoadRequest
from src.services.config_service import (
    load_settings,
    load_workflow_control_settings,
    load_workflow_queue_policies,
    new_runtime_context,
)
from src.services.workflow_queue_service import get_workflow_queue_control


def test_prepare_isolated_canary_run_creates_fresh_root_with_only_rooted_mutable_paths(
    tmp_path: Path,
) -> None:
    run = prepare_isolated_canary_run(runs_root=tmp_path)

    assert run.root.is_dir()
    assert run.root.parent == tmp_path
    assert run.config_path.is_file()
    assert run.mutable_paths
    assert all(path.is_relative_to(run.root) for path in run.mutable_paths)
    assert not any(path.exists() for path in run.mutable_paths)


def test_isolated_canary_config_keeps_repository_owned_cost_pricing_available(
    tmp_path: Path,
) -> None:
    run = prepare_isolated_canary_run(runs_root=tmp_path)

    settings = load_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)),
        new_runtime_context(task_id="isolated-canary-config-test"),
    )

    assert settings.model_pricing
    assert Path(settings.category_mapping_path).is_file()
    assert Path(settings.publisher_profiles_path).is_file()
    assert Path(settings.cover_style_path).is_file()
    control = load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)),
        new_runtime_context(task_id="isolated-canary-supervisor-test"),
    )
    assert control.supervisor.enabled is True
    assert control.supervisor.worker_batches_enabled is True
    assert control.supervisor.max_parallel_workers == 3
    assert control.supervisor.max_jobs_per_queue == 3
    assert control.supervisor.max_total_jobs == 60
    queues = load_workflow_queue_policies(
        ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)),
        new_runtime_context(task_id="isolated-canary-queue-test"),
    )
    assert queues["wordpress_publish"].enabled is False


def test_isolated_canary_persists_publication_queue_disabled_without_changing_limits(
    tmp_path: Path,
) -> None:
    run = prepare_isolated_canary_run(runs_root=tmp_path)
    ctx = new_runtime_context(task_id="isolated-canary-publication-queue-test")
    settings = load_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)), ctx
    )
    initial = get_workflow_queue_control(
        settings.state_db, "wordpress_publish", ctx
    )

    disabled = ensure_isolated_publication_queue_disabled(
        state_db=settings.state_db, ctx=ctx
    )
    persisted = get_workflow_queue_control(
        settings.state_db, "wordpress_publish", ctx
    )

    assert initial.enabled is True
    assert disabled.enabled is False
    assert persisted.enabled is False
    assert persisted.worker_concurrency_limit == initial.worker_concurrency_limit
    assert persisted.max_attempts == initial.max_attempts


def test_frozen_cohort_seeds_isolated_queue_controls_from_config_before_submission(
    tmp_path: Path,
) -> None:
    run = prepare_isolated_canary_run(runs_root=tmp_path)
    source_config = Path("src/config/app.yaml")
    source_config_before = source_config.read_bytes()
    ctx = new_runtime_context(task_id="isolated-canary-queue-seed-test")
    settings = load_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)), ctx
    )

    controls = _seed_isolated_workflow_queue_controls(
        state_db=settings.state_db,
        config_path=run.config_path,
        ctx=ctx,
    )
    publication = ensure_isolated_publication_queue_disabled(
        state_db=settings.state_db, ctx=ctx
    )

    assert controls["source_ingest"].worker_concurrency_limit == 5
    assert controls["report_analysis"].worker_concurrency_limit == 5
    assert controls["report_selection"].worker_concurrency_limit == 5
    assert controls["report_render"].worker_concurrency_limit == 5
    assert controls["publication_readiness"].worker_concurrency_limit == 5
    assert controls["wordpress_publish"].enabled is False
    assert publication.enabled is False
    for field in (
        "schema_version",
        "queue_name",
        "mode",
        "worker_concurrency_limit",
        "maximum_pending",
        "maximum_fanout",
        "max_attempts",
        "lease_seconds",
        "budget_profile",
        "retry_delay_seconds",
        "emergency_stop_reason",
    ):
        assert getattr(publication, field) == getattr(
            controls["wordpress_publish"], field
        )
    assert (
        get_workflow_queue_control(
            settings.state_db, "source_ingest", ctx
        ).worker_concurrency_limit
        == 5
    )
    with sqlite3.connect(settings.state_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM workflow_jobs").fetchone()[0] == 0
    assert source_config.read_bytes() == source_config_before


def test_cohort_queue_timing_uses_persisted_attempts_and_existing_elapsed_metrics(
    tmp_path: Path,
) -> None:
    state_db = tmp_path / "workflow.sqlite"
    with sqlite3.connect(state_db) as conn:
        conn.executescript(
            """
            CREATE TABLE workflow_queue_controls (
              queue_name TEXT, enabled INTEGER, worker_concurrency_limit INTEGER,
              max_attempts INTEGER
            );
            CREATE TABLE workflow_jobs (
              job_id TEXT, report_id TEXT, queue_name TEXT, parent_job_id TEXT,
              job_type TEXT, status TEXT, created_at_utc TEXT, available_at_utc TEXT,
              started_at_utc TEXT, completed_at_utc TEXT, attempt_count INTEGER,
              root_workflow_id TEXT
            );
            CREATE TABLE workflow_job_attempts (
              job_id TEXT, attempt_number INTEGER, started_at_utc TEXT,
              completed_at_utc TEXT, outcome TEXT, error_code TEXT
            );
            CREATE TABLE workflow_job_transitions (
              job_id TEXT, reason TEXT
            );
            CREATE TABLE published (file_id TEXT);
            CREATE TABLE performance_telemetry_spans (
              span_id TEXT, run_id TEXT, stage TEXT, queue_name TEXT,
              worker_id TEXT, attributes_json TEXT
            );
            CREATE TABLE performance_telemetry_measurements (
              span_id TEXT, metric TEXT, status TEXT, integer_value INTEGER
            );
            """
        )
        stages = (
            "source_ingest",
            "report_selection",
            "report_analysis",
            "report_render",
            "publication_readiness",
        )
        conn.executemany(
            "INSERT INTO workflow_queue_controls VALUES (?, 1, 1, 3)",
            [(stage,) for stage in stages],
        )
        jobs = []
        attempts = []
        parent_by_report = {"report-a": "", "report-b": ""}
        timing = {
            ("report-a", "source_ingest"): ("00", "04"),
            ("report-b", "source_ingest"): ("04", "05"),
            ("report-a", "report_selection"): ("05", "06"),
            ("report-b", "report_selection"): ("06", "07"),
            ("report-a", "report_analysis"): ("07", "09"),
            ("report-b", "report_analysis"): ("09", "12"),
            ("report-a", "report_render"): ("12", "13"),
            ("report-b", "report_render"): ("13", "14"),
            ("report-a", "publication_readiness"): ("14", "15"),
            ("report-b", "publication_readiness"): ("15", "16"),
        }
        job_ids = {}
        for report_id in ("report-a", "report-b"):
            for stage in stages:
                start_second, end_second = timing[(report_id, stage)]
                job_id = f"{report_id}:{stage}"
                job_ids[(report_id, stage)] = job_id
                created_second = (
                    "01"
                    if report_id == "report-b" and stage == "source_ingest"
                    else start_second
                )
                created = f"2026-10-04T10:00:{created_second}+00:00"
                started = f"2026-10-04T10:00:{start_second}+00:00"
                completed = f"2026-10-04T10:00:{end_second}+00:00"
                jobs.append(
                    (
                        job_id,
                        report_id,
                        stage,
                        parent_by_report[report_id],
                        f"{stage}.v1",
                        "succeeded",
                        created,
                        created,
                        started,
                        started,
                        1,
                        "workflow-1",
                    )
                )
                attempts.append((job_id, 1, started, completed, "succeeded", ""))
                parent_by_report[report_id] = job_id
        conn.executemany(
            "INSERT INTO workflow_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", jobs
        )
        conn.executemany(
            "INSERT INTO workflow_job_attempts VALUES (?,?,?,?,?,?)", attempts
        )
        telemetry_job = job_ids[("report-b", "report_analysis")]
        span_id = "span-report-b-analysis"
        conn.execute(
            "INSERT INTO performance_telemetry_spans VALUES (?,?,?,?,?,?)",
            (
                span_id,
                "run-1",
                "report_analysis",
                "report_analysis",
                "worker-1",
                json.dumps({"job_id": telemetry_job}),
            ),
        )
        conn.executemany(
            "INSERT INTO performance_telemetry_measurements VALUES (?,?,?,?)",
            [
                (span_id, "queue_wait_ms", "observed", 1200),
                (span_id, "wall_time_ms", "observed", 3000),
            ],
        )

    evidence = _collect_frozen_cohort_queue_timing_evidence(
        state_db=str(state_db),
        root_workflow_id="workflow-1",
        report_ids=("report-a", "report-b"),
    )

    assert (
        evidence["terminal_dependency_chain"]["terminal_report_id"] == "report-b"
    )
    assert (
        evidence["terminal_dependency_chain"]["path_source"]
        == "workflow_job_parent_chain"
    )
    path_jobs = evidence["terminal_dependency_chain"]["jobs"]
    assert [item["stage"] for item in path_jobs] == [
        "source_ingest",
        "report_selection",
        "report_analysis",
        "report_render",
        "publication_readiness",
    ]
    assert all(item["on_terminal_dependency_chain"] for item in path_jobs)
    assert evidence["resource_constrained_critical_path"]["derived"] is False
    assert all(
        "materially_contributes_to_critical_path" not in item
        for item in evidence["stage_attempts"]
    )
    analysis = next(
        item for item in evidence["stage_attempts"] if item["job_id"] == telemetry_job
    )
    assert analysis["execution_seconds"] == 3.0
    assert analysis["queue_wait_seconds"] == 1.2
    assert analysis["execution_source"] == "performance_telemetry.wall_time_ms"
    assert analysis["queue_wait_source"] == "performance_telemetry.queue_wait_ms"
    assert evidence["queue_concurrency"]["source_ingest"]["configured_workers"] == 1
    assert (
        evidence["queue_concurrency"]["source_ingest"]["max_observed_running_jobs"] == 1
    )
    assert evidence["publication_write_count"] == 0
    assert next(
        item
        for item in evidence["stage_attempts"]
        if item["job_id"] == job_ids[("report-a", "source_ingest")]
    )["on_terminal_dependency_chain"] is False


def test_retained_claim_counts_require_the_exact_report_and_source_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"frozen source")
    source_hash = hashlib.md5(source.read_bytes(), usedforsecurity=False).hexdigest()
    report_id = f"cohort-{source_hash[:20]}"
    validation = (
        tmp_path
        / "output"
        / canary_runner.slugify(source.name)
        / "report_analysis"
        / "validation_retained_claim_validation_candidate.json"
    )
    validation.parent.mkdir(parents=True)
    validation.write_text(
        json.dumps(
            {
                "validation_identity": {
                    "report_id": report_id,
                    "source_md5": source_hash,
                },
                "unsupported_factual_count": 0,
                "unresolved_factual_count": 0,
            }
        ),
        encoding="utf-8",
    )

    assert _read_retained_claim_counts(
        output_dir=tmp_path / "output", source_path=source, report_id=report_id
    ) == (0, 0)
    assert (
        _read_retained_claim_counts(
            output_dir=tmp_path / "output", source_path=source, report_id="other"
        )
        is None
    )


def test_frozen_member_validation_uses_its_own_artifact_not_a_sibling_report(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    source_path = tmp_path / "sources" / "adjust.pdf"
    target = output_dir / "adjust-pdf" / "report_analysis" / "validation.json"
    sibling = output_dir / "z-sibling" / "report_analysis" / "validation.json"
    target.parent.mkdir(parents=True)
    sibling.parent.mkdir(parents=True)
    target.write_text('{"status":"fail"}', encoding="utf-8")
    sibling.write_text('{"status":"pass"}', encoding="utf-8")

    read_member_validation = getattr(canary_runner, "report_validation_passed", None)
    assert read_member_validation is not None
    assert read_member_validation(output_dir, source_path) is False


def test_live_canary_records_a_typed_terminal_input_failure(tmp_path: Path) -> None:
    result = run_ias_first_attempt_canary(
        runs_root=tmp_path,
        source_path=tmp_path / "missing-ias.pdf",
    )

    assert result["final_state"] == "failed"
    assert result["awaiting_review"] is False
    assert result["workflow_attempt_count"] == 0
    assert result["terminal_failure_code"] == "ias_canary_source_missing"
    assert (Path(result["run_directory"]) / "result.json").is_file()


def test_live_canary_script_prints_one_json_result_for_a_typed_failure(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/quality/run_ias_first_attempt_canary.py",
            "--runs-root",
            str(tmp_path),
            "--source",
            str(tmp_path / "missing-ias.pdf"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert (
        json.loads(completed.stdout)["terminal_failure_code"]
        == "ias_canary_source_missing"
    )
