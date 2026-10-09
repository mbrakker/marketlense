import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

import scripts.quality.ias_live_canary_runner as canary_runner
from scripts.quality.ias_live_canary_runner import (
    _collect_frozen_cohort_queue_timing_evidence,
    _queue_terminal_state,
    _read_retained_claim_counts,
    _replay_completed_wordpress_jobs,
    _seed_isolated_workflow_queue_controls,
    _sum_member_metric,
    _validate_wordpress_staging_origin,
    _wordpress_publication_evidence,
    ensure_isolated_publication_queue_disabled,
    prepare_isolated_canary_run,
    run_ias_first_attempt_canary,
)
from src.contracts.config import ConfigLoadRequest
from src.contracts.report_analysis import AnalysisPackPathRequest
from src.contracts.semantic_ids import ReportId
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidate,
    SignalCandidateGroup,
    SignalCandidateSourceRef,
    SignalCandidateStoreRequest,
)
from src.contracts.workflow_queue import (
    WordPressPublishPayload,
    WorkflowJobSubmission,
    WorkflowStageResult,
)
from src.services.analytics_store_service import upsert_signal_candidates
from src.services.config_service import (
    load_settings,
    load_workflow_control_settings,
    load_workflow_queue_policies,
    new_runtime_context,
)
from src.services.report_analysis_store_service import pack_path
from src.services.workflow_queue_service import (
    claim_next_workflow_job,
    complete_workflow_job,
    enqueue_workflow_job,
    get_workflow_queue_control,
    start_workflow_job,
)


def _long_test_output_root(tmp_path: Path) -> Path:
    """Keep path-compaction coverage deterministic on short Linux temp roots."""
    return tmp_path / ("isolated-run-" + "r" * 20) / "output"


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
    assert control.autonomous_publication_policy.enabled is False
    queues = load_workflow_queue_policies(
        ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)),
        new_runtime_context(task_id="isolated-canary-queue-test"),
    )
    assert queues["wordpress_publish"].enabled is False


def test_isolated_canary_staging_mode_is_explicit_draft_only_and_host_pinned(
    tmp_path: Path,
) -> None:
    run = prepare_isolated_canary_run(
        runs_root=tmp_path,
        publish_to_wordpress_staging=True,
        staging_hostname="marketlense.medianewsonline.com",
        allow_insecure_staging_http=True,
        enable_cross_report_analysis=True,
    )

    config = yaml.safe_load(run.config_path.read_text(encoding="utf-8"))
    control = load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)),
        new_runtime_context(task_id="isolated-staging-policy-test"),
    )
    queues = load_workflow_queue_policies(
        ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)),
        new_runtime_context(task_id="isolated-staging-queue-test"),
    )

    assert control.autonomous_publication_policy.enabled is True
    assert control.supervisor.deferred_work_enabled is True
    assert control.supervisor.remediation_enabled is True
    assert queues["wordpress_publish"].enabled is True
    assert queues["publisher_discovery"].enabled is False
    assert queues["report_acquisition"].enabled is False
    assert queues["mailbox_delivery"].enabled is False
    assert config["publish"]["wp"]["post_status"] == "draft"
    assert config["cross_report_analysis"]["enabled"] is True
    assert config["cross_report_analysis"]["publish_enabled"] is False


def test_isolated_canary_refuses_an_unconfirmed_publication_host(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="confirmed WordPress staging host"):
        prepare_isolated_canary_run(
            runs_root=tmp_path,
            publish_to_wordpress_staging=True,
            staging_hostname="production.example",
        )


def test_isolated_canary_refuses_http_opt_in_without_staging_publication(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="requires WordPress staging publication"):
        prepare_isolated_canary_run(
            runs_root=tmp_path,
            allow_insecure_staging_http=True,
        )


def test_wordpress_staging_origin_allows_pinned_http_opt_in() -> None:
    origin = _validate_wordpress_staging_origin(
        "http://marketlense.medianewsonline.com",
        staging_hostname="marketlense.medianewsonline.com",
        allow_insecure_http=True,
    )

    assert origin.scheme == "http"
    assert origin.hostname == "marketlense.medianewsonline.com"


@pytest.mark.parametrize(
    ("site_url", "hostname", "allow_insecure_http"),
    [
        (
            "http://marketlense.medianewsonline.com",
            "marketlense.medianewsonline.com",
            False,
        ),
        (
            "https://marketlense.medianewsonline.com:8443",
            "marketlense.medianewsonline.com",
            False,
        ),
        (
            "https://user@marketlense.medianewsonline.com",
            "marketlense.medianewsonline.com",
            False,
        ),
        (
            "https://marketlense.medianewsonline.com?next=evil",
            "marketlense.medianewsonline.com",
            False,
        ),
        (
            "https://marketlense.medianewsonline.com?",
            "marketlense.medianewsonline.com",
            False,
        ),
        (
            "https://marketlense.medianewsonline.com/#fragment",
            "marketlense.medianewsonline.com",
            False,
        ),
        (
            "https://marketlense.medianewsonline.com/#",
            "marketlense.medianewsonline.com",
            False,
        ),
        ("https://other.example", "marketlense.medianewsonline.com", False),
    ],
)
def test_wordpress_staging_origin_rejects_unapproved_or_ambiguous_targets(
    site_url: str, hostname: str, allow_insecure_http: bool
) -> None:
    with pytest.raises(ValueError):
        _validate_wordpress_staging_origin(
            site_url,
            staging_hostname=hostname,
            allow_insecure_http=allow_insecure_http,
        )


@pytest.mark.parametrize(
    (
        "write_count",
        "readback_verified",
        "workflow_attempt_count",
        "wordpress_post_id",
        "expected",
    ),
    [
        (1, True, 1, 42, (True, True)),
        (0, True, 1, 42, (False, False)),
        (1, True, 2, 42, (False, False)),
        (1, False, 1, 42, (True, False)),
        (1, True, 1, 99, (False, False)),
    ],
)
def test_wordpress_publication_evidence_requires_first_attempt_create_and_readback(
    write_count: int,
    readback_verified: bool,
    workflow_attempt_count: int,
    wordpress_post_id: int,
    expected: tuple[bool, bool],
) -> None:
    evidence = _wordpress_publication_evidence(
        publication_outcome={
            "status": "published",
            "publication_outcome": "post_created",
            "file_id": "report-1",
            "post_id": 42,
            "actual_write_count": write_count,
            "authenticated_readback_verified": readback_verified,
            "readback_expectation": {
                "file_id": "report-1",
                "post_type": "ml_report",
            },
            "readback_checks": [
                {"name": name, "status": "verified"}
                for name in (
                    "post_id",
                    "report_file_identity",
                    "canonical_url",
                    "post_type",
                    "status",
                    "content_checksum",
                    "source_attribution",
                    "metadata",
                    "taxonomy_assignments",
                    "media_associations",
                )
            ],
        },
        workflow_status="succeeded",
        workflow_attempt_count=workflow_attempt_count,
        wordpress_post_id=wordpress_post_id,
        expected_file_id="report-1",
        expected_post_type="ml_report",
    )

    assert (
        evidence["wordpress_created_this_run"],
        evidence["wordpress_authenticated_readback"],
    ) == expected


def test_wordpress_publication_evidence_requires_verified_metadata_readback() -> None:
    outcome = {
        "status": "published",
        "publication_outcome": "post_created",
        "file_id": "report-1",
        "post_id": 42,
        "actual_write_count": 1,
        "authenticated_readback_verified": True,
        "readback_expectation": {"file_id": "report-1", "post_type": "ml_report"},
        "readback_checks": [
            {"name": "post_id", "status": "verified"},
            {"name": "metadata", "status": "not_verified"},
        ],
    }

    evidence = _wordpress_publication_evidence(
        publication_outcome=outcome,
        workflow_status="succeeded",
        workflow_attempt_count=1,
        wordpress_post_id=42,
        expected_file_id="report-1",
        expected_post_type="ml_report",
    )

    assert evidence == {
        "wordpress_created_this_run": True,
        "wordpress_authenticated_readback": False,
    }


def test_wordpress_publication_evidence_rejects_conflicting_duplicate_checks() -> None:
    outcome = {
        "status": "published",
        "publication_outcome": "post_created",
        "file_id": "report-1",
        "post_id": 42,
        "actual_write_count": 1,
        "authenticated_readback_verified": True,
        "readback_expectation": {"file_id": "report-1", "post_type": "ml_report"},
        "readback_checks": [
            {"name": name, "status": "verified"}
            for name in (
                "post_id",
                "report_file_identity",
                "canonical_url",
                "post_type",
                "status",
                "content_checksum",
                "source_attribution",
                "metadata",
                "taxonomy_assignments",
                "media_associations",
            )
        ]
        + [{"name": "metadata", "status": "mismatch"}],
    }

    evidence = _wordpress_publication_evidence(
        publication_outcome=outcome,
        workflow_status="succeeded",
        workflow_attempt_count=1,
        wordpress_post_id=42,
        expected_file_id="report-1",
        expected_post_type="ml_report",
    )

    assert evidence["wordpress_created_this_run"] is True
    assert evidence["wordpress_authenticated_readback"] is False


def test_signal_manifest_mutation_probe_closes_temporary_sqlite_handles(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "signals.sqlite"
    ctx = new_runtime_context(task_id="signal-manifest-close-test")
    group_id = "signal-group:test"
    candidate_id = "signal-candidate:test"
    source_ref = SignalCandidateSourceRef(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        report_id="report-1",
        evidence_id="report-1:claim:1",
        source_table="report_claims",
        entity_uid="report-1:claim:1",
        content_class="claim",
        page_refs=[1],
        source_metadata={"pages": [1], "evidence": "A retained source claim."},
    )
    candidate = SignalCandidate(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        candidate_id=candidate_id,
        candidate_type="market_signal",
        title="Test signal",
        summary="A source-backed signal for the mutation probe.",
        confidence=0.8,
        strength=1.0,
        support_level="single_report",
        caveats=["single_report_coverage"],
        source_report_ids=["report-1"],
        evidence_ids=["report-1:claim:1"],
        source_refs=[source_ref],
        raw_source_context={"fixture": "focused-test"},
        validation_status="approved",
        validation_notes=["source_backed"],
        group_id=group_id,
        extraction_request_id="extract-1",
        generated_at_utc="2026-10-09T10:00:00Z",
    )
    group = SignalCandidateGroup(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        group_id=group_id,
        stable_key="test:signal",
        title="Test signal",
        summary="A source-backed signal for the mutation probe.",
        support_level="single_report",
        candidate_ids=[candidate_id],
        source_report_ids=["report-1"],
        evidence_ids=["report-1:claim:1"],
        caveats=["single_report_coverage"],
        raw_group_context={"agreement_type": "thin_coverage"},
        validation_status="approved",
        extraction_request_id="extract-1",
        generated_at_utc="2026-10-09T10:00:00Z",
        publication_status="held",
        publication_hold_reason="signal_grounding_insufficient",
    )
    stored = upsert_signal_candidates(
        SignalCandidateStoreRequest(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=str(db_path),
            extraction_request_id="extract-1",
            candidates=[candidate],
            groups=[group],
        ),
        ctx,
    )

    verified = canary_runner._verify_signal_manifest_immutable(
        signal_store_db=str(db_path),
        manifest_hash=stored.manifest_hashes[group_id],
        extraction_request_id="extract-1",
        group_id=group_id,
        ctx=ctx,
    )

    assert verified is True
    assert list(tmp_path.glob("signal-manifest-mutation-*")) == []


def test_queue_terminal_state_accepts_a_published_autonomous_report(
    tmp_path: Path,
) -> None:
    state_db = tmp_path / "workflow.sqlite"
    with sqlite3.connect(state_db) as conn:
        conn.executescript(
            """
            CREATE TABLE workflow_publication_readiness (
              package_checksum TEXT, readiness_status TEXT
            );
            CREATE TABLE workflow_jobs (
              queue_name TEXT, output_content_hash TEXT, report_id TEXT,
              root_workflow_id TEXT, status TEXT, error_code TEXT,
              completed_at_utc TEXT
            );
            CREATE TABLE published (
              file_id TEXT PRIMARY KEY, md5 TEXT NOT NULL,
              published_at INTEGER NOT NULL, wp_post_id INTEGER NOT NULL,
              wp_post_url TEXT NOT NULL, post_type TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO workflow_publication_readiness VALUES ('pkg', 'approved');
            INSERT INTO workflow_jobs VALUES
              ('publication_readiness', 'pkg', 'report-1', 'root-1',
               'succeeded', '', '');
            INSERT INTO published VALUES
              ('report-1', 'source-hash', 1, 42,
               'https://staging.example/posts/42', 'ml_report');
            """
        )

    state = _queue_terminal_state(
        state_db=str(state_db), report_id="report-1", root_workflow_id="root-1"
    )

    assert state == "published"


def test_completed_wordpress_job_duplicate_submission_reuses_record_without_writes(
    tmp_path: Path,
) -> None:
    state_db = tmp_path / "workflow.sqlite"
    ctx = new_runtime_context(task_id="wordpress-job-replay-test")
    get_workflow_queue_control(state_db, "wordpress_publish", ctx)
    available = datetime.now(timezone.utc) + timedelta(seconds=1)
    claim_time = available + timedelta(seconds=1)
    start_time = claim_time + timedelta(seconds=1)
    complete_time = start_time + timedelta(seconds=1)

    def as_iso(value: datetime) -> str:
        return value.isoformat(timespec="seconds")

    submission = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="wordpress_publish",
        job_type="wordpress_publish.v1",
        payload=WordPressPublishPayload(
            schema_version="1.0",
            entity_type="report",
            entity_package_reference="report.html",
            package_checksum="package-hash",
            approval_id="approval-id",
            target_site="https://marketlense.medianewsonline.com",
        ),
        idempotency_key="publish:report-1:package-hash",
        deduplication_scope="wordpress_publish",
        root_workflow_id="root-1",
        report_id="report-1",
        available_at_utc=as_iso(available),
    )
    job, created = enqueue_workflow_job(state_db, submission, ctx)
    assert created is True
    claimed = claim_next_workflow_job(
        state_db,
        "wordpress_publish",
        "replay-test-worker",
        ctx,
        now_utc=as_iso(claim_time),
    )
    assert claimed is not None
    start_workflow_job(
        state_db,
        claimed.job_id,
        "replay-test-worker",
        ctx,
        now_utc=as_iso(start_time),
    )
    complete_workflow_job(
        state_db,
        claimed.job_id,
        "replay-test-worker",
        WorkflowStageResult(
            output_reference="https://marketlense.medianewsonline.com/report/42",
            output_content_hash="package-hash",
            output_verified=True,
        ),
        [],
        ctx,
        now_utc=as_iso(complete_time),
        external_effects=["wordpress"],
    )
    with sqlite3.connect(state_db) as conn:
        conn.execute(
            "INSERT INTO published VALUES (?, ?, ?, ?, ?, ?)",
            (
                "report-1",
                "source-hash",
                1,
                42,
                "https://marketlense.medianewsonline.com/report/42",
                "ml_report",
            ),
        )

    replay = _replay_completed_wordpress_jobs(
        state_db=str(state_db),
        root_workflow_id="root-1",
        report_ids=("report-1",),
        ctx=ctx,
    )

    assert replay["status"] == "verified"
    assert replay["duplicate_submissions"] == 1
    assert replay["first_attempt_publication_jobs"] == 1
    assert replay["created_duplicate_jobs"] == 0
    assert replay["attempt_counts_unchanged"] is True
    assert replay["published_rows_unchanged"] is True
    assert replay["additional_wordpress_writes"] == 0
    with sqlite3.connect(state_db) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM workflow_jobs "
                "WHERE queue_name='wordpress_publish'"
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM workflow_job_attempts").fetchone()[0]
            == 1
        )


def test_member_metric_sum_requires_every_report_value() -> None:
    reports = [
        {"cost": 0.01, "model_provider_calls": 1},
        {"cost": 0.02, "model_provider_calls": 2},
    ]

    assert _sum_member_metric(reports, "cost") == 0.03
    assert _sum_member_metric(reports, "model_provider_calls") == 3
    assert _sum_member_metric([*reports, {"cost": None}], "cost") is None


def test_staging_batch_requires_cross_report_handoff_verification(
    tmp_path: Path,
) -> None:
    from scripts.quality.run_frozen_reliability_cohort import (
        run_frozen_reliability_cohort,
    )

    with pytest.raises(ValueError, match="cross-report handoff"):
        run_frozen_reliability_cohort(
            sources_manifest=tmp_path / "not-loaded.json",
            runs_root=tmp_path / "runs",
            shared_batch=True,
            publish_to_wordpress_staging=True,
            staging_hostname="marketlense.medianewsonline.com",
        )


def test_isolated_canary_persists_publication_queue_disabled_without_changing_limits(
    tmp_path: Path,
) -> None:
    run = prepare_isolated_canary_run(runs_root=tmp_path)
    ctx = new_runtime_context(task_id="isolated-canary-publication-queue-test")
    settings = load_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)), ctx
    )
    initial = get_workflow_queue_control(settings.state_db, "wordpress_publish", ctx)

    disabled = ensure_isolated_publication_queue_disabled(
        state_db=settings.state_db, ctx=ctx
    )
    persisted = get_workflow_queue_control(settings.state_db, "wordpress_publish", ctx)

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

    assert evidence["terminal_dependency_chain"]["terminal_report_id"] == "report-b"
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
    assert (
        next(
            item
            for item in evidence["stage_attempts"]
            if item["job_id"] == job_ids[("report-a", "source_ingest")]
        )["on_terminal_dependency_chain"]
        is False
    )


def test_retained_claim_counts_require_the_exact_report_and_source_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sources" / f"source-{'x' * 80}.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"frozen source")
    source_hash = hashlib.md5(source.read_bytes(), usedforsecurity=False).hexdigest()
    report_id = f"cohort-{source_hash[:20]}"
    ctx = new_runtime_context(task_id="canary-retained-claim-path")
    output_dir = _long_test_output_root(tmp_path)
    validation = Path(
        pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=str(output_dir),
                report_id=ReportId(report_id),
                pack_name="validation_retained_claim_validation_candidate",
                report_slug=canary_runner.slugify(source.name),
            ),
            ctx,
        ).output_path
    )
    assert validation.parent.parent.name != canary_runner.slugify(source.name)
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
        output_dir=output_dir,
        source_path=source,
        report_id=report_id,
        ctx=ctx,
    ) == (0, 0)
    assert (
        _read_retained_claim_counts(
            output_dir=output_dir,
            source_path=source,
            report_id="other",
            ctx=ctx,
        )
        is None
    )


def test_frozen_member_validation_uses_its_own_artifact_not_a_sibling_report(
    tmp_path: Path,
) -> None:
    output_dir = _long_test_output_root(tmp_path)
    source_path = tmp_path / "sources" / f"adjust-{'x' * 80}.pdf"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"frozen Adjust source")
    source_hash = hashlib.md5(
        source_path.read_bytes(), usedforsecurity=False
    ).hexdigest()
    report_id = f"cohort-{source_hash[:20]}"
    ctx = new_runtime_context(task_id="canary-member-validation-path")
    target = Path(
        pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=str(output_dir),
                report_id=ReportId(report_id),
                pack_name="validation",
                report_slug=canary_runner.slugify(source_path.name),
            ),
            ctx,
        ).output_path
    )
    sibling = Path(
        pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=str(output_dir),
                report_id=ReportId("cohort-sibling"),
                pack_name="validation",
                report_slug="z-sibling",
            ),
            ctx,
        ).output_path
    )
    assert target.parent.parent.name != canary_runner.slugify(source_path.name)
    target.parent.mkdir(parents=True)
    sibling.parent.mkdir(parents=True)
    target.write_text('{"status":"pass"}', encoding="utf-8")
    sibling.write_text('{"status":"fail"}', encoding="utf-8")

    read_member_validation = getattr(canary_runner, "report_validation_passed", None)
    assert read_member_validation is not None
    assert (
        read_member_validation(output_dir, source_path, report_id=report_id, ctx=ctx)
        is True
    )


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
