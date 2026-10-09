from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.quality.ias_live_canary_runner import (
    _collect_cross_report_handoff_evidence,
    _cross_report_handoffs_terminal,
    _read_report_core_duration,
    _read_report_usage_summary,
    _read_workflow_job_usage,
)
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidate,
    SignalCandidateGroup,
    SignalCandidateSourceRef,
    SignalCandidateStoreRequest,
)
from src.services.analytics_store_service import upsert_signal_candidates
from src.services.config_service import new_runtime_context


def test_cross_report_drain_waits_for_child_jobs_and_outbox_materialization(
    tmp_path: Path,
) -> None:
    state_db = tmp_path / "cross-report-queues.sqlite"
    with sqlite3.connect(state_db) as conn:
        conn.executescript(
            """
            CREATE TABLE workflow_jobs (
              root_workflow_id TEXT, queue_name TEXT, entity_type TEXT, status TEXT
            );
            CREATE TABLE workflow_outbox (
              root_workflow_id TEXT, queue_name TEXT, status TEXT
            );
            INSERT INTO workflow_jobs VALUES
              ('root-1', 'briefing_generation', 'briefing', 'pending'),
              ('root-1', 'wordpress_projection', 'report', 'pending');
            INSERT INTO workflow_outbox VALUES
              ('root-1', 'signal_candidate', 'pending');
            """
        )

    assert (
        _cross_report_handoffs_terminal(
            state_db=str(state_db), root_workflow_id="root-1"
        )
        is False
    )

    with sqlite3.connect(state_db) as conn:
        conn.execute(
            "UPDATE workflow_jobs SET status='succeeded' "
            "WHERE queue_name='briefing_generation'"
        )
        conn.execute("UPDATE workflow_outbox SET status='materialised'")

    assert (
        _cross_report_handoffs_terminal(
            state_db=str(state_db), root_workflow_id="root-1"
        )
        is False
    )

    with sqlite3.connect(state_db) as conn:
        conn.execute(
            "UPDATE workflow_jobs SET status='succeeded' "
            "WHERE queue_name='wordpress_projection'"
        )

    assert (
        _cross_report_handoffs_terminal(
            state_db=str(state_db), root_workflow_id="root-1"
        )
        is True
    )


def test_cross_report_evidence_separates_validated_briefing_usage_and_duration(
    tmp_path: Path,
) -> None:
    state_db = tmp_path / "briefing-evidence.sqlite"
    signal_store_db = tmp_path / "signals.sqlite"
    usage_db = tmp_path / "usage.sqlite"
    with sqlite3.connect(state_db) as conn:
        conn.executescript(
            """
            CREATE TABLE workflow_jobs (
              job_id TEXT, root_workflow_id TEXT, queue_name TEXT, status TEXT,
              entity_type TEXT, attempt_count INTEGER, output_reference TEXT,
              output_content_hash TEXT, started_at_utc TEXT, completed_at_utc TEXT,
              error_code TEXT
            );
            CREATE TABLE workflow_outbox (
              root_workflow_id TEXT, queue_name TEXT, status TEXT
            );
            CREATE TABLE workflow_briefing_opportunities (
              generation_job_id TEXT, source_hashes_json TEXT, publisher_ids_json TEXT
            );
            INSERT INTO workflow_jobs VALUES (
              'brief-job-1', 'root-1', 'briefing_generation', 'succeeded',
              'briefing', 1, 'briefing/artifact.json', 'briefing-hash',
              '2026-10-09T10:00:02+00:00',
              '2026-10-09T10:00:02+00:00', ''
            );
            INSERT INTO workflow_briefing_opportunities VALUES (
              'brief-job-1', '["source-hash-1", "source-hash-2"]',
              '["publisher-1", "publisher-2"]'
            );
            CREATE TABLE performance_telemetry_spans (
              span_id TEXT, stage TEXT, attributes_json TEXT
            );
            CREATE TABLE performance_telemetry_measurements (
              span_id TEXT, metric TEXT, status TEXT, integer_value INTEGER
            );
            INSERT INTO performance_telemetry_spans VALUES (
              'brief-span-1', 'briefing_generation',
              '{"job_id": "brief-job-1"}'
            );
            INSERT INTO performance_telemetry_measurements VALUES (
              'brief-span-1', 'wall_time_ms', 'observed', 28618
            );
            """
        )
    with sqlite3.connect(signal_store_db):
        pass
    ctx = new_runtime_context(task_id="briefing-evidence-test")
    for index in (1, 2):
        group_id = f"signal-group:{index}"
        candidate_id = f"signal-candidate:{index}"
        report_id = f"report-{index}"
        source_ref = SignalCandidateSourceRef(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            report_id=report_id,
            evidence_id=f"{report_id}:claim:1",
            source_table="report_claims",
            entity_uid=f"{report_id}:claim:1",
            content_class="claim",
            page_refs=[1],
            source_metadata={"pages": [1], "evidence": "A retained source claim."},
        )
        candidate = SignalCandidate(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            candidate_id=candidate_id,
            candidate_type="market_signal",
            title=f"Test signal {index}",
            summary="A source-backed signal for the mutation probe.",
            confidence=0.8,
            strength=1.0,
            support_level="single_report",
            caveats=["single_report_coverage"],
            source_report_ids=[report_id],
            evidence_ids=[source_ref.evidence_id],
            source_refs=[source_ref],
            raw_source_context={"fixture": "cross-report-evidence"},
            validation_status="approved",
            validation_notes=["source_backed"],
            group_id=group_id,
            extraction_request_id="extract-1",
            generated_at_utc="2026-10-09T10:00:00Z",
        )
        group = SignalCandidateGroup(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            group_id=group_id,
            stable_key=f"test:signal:{index}",
            title=f"Test signal {index}",
            summary="A source-backed signal for the mutation probe.",
            support_level="single_report",
            candidate_ids=[candidate_id],
            source_report_ids=[report_id],
            evidence_ids=[source_ref.evidence_id],
            caveats=["single_report_coverage"],
            raw_group_context={"agreement_type": "thin_coverage"},
            validation_status="approved",
            extraction_request_id="extract-1",
            generated_at_utc="2026-10-09T10:00:00Z",
            publication_status="held",
            publication_hold_reason="signal_grounding_insufficient",
        )
        upsert_signal_candidates(
            SignalCandidateStoreRequest(
                schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
                db_path=str(signal_store_db),
                extraction_request_id="extract-1",
                candidates=[candidate],
                groups=[group],
            ),
            ctx,
        )
    with sqlite3.connect(usage_db) as conn:
        conn.execute(
            """CREATE TABLE llm_usage_events (
              task_id TEXT, input_tokens INTEGER, cached_input_tokens INTEGER,
              output_tokens INTEGER, tool_calls INTEGER, estimated_cost_usd REAL,
              pricing_status TEXT
            )"""
        )
        conn.execute(
            "INSERT INTO llm_usage_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("workflow_job:brief-job-1", 200, 20, 50, 0, 0.0125, "matched"),
        )

    evidence = _collect_cross_report_handoff_evidence(
        state_db=str(state_db),
        signal_store_db=str(signal_store_db),
        usage_db_path=str(usage_db),
        root_workflow_id="root-1",
        ctx=ctx,
    )

    assert evidence["briefing_validated_multireport_count"] == 1
    assert evidence["briefing_validated_multireport_execution_seconds"] == 28.618
    assert evidence["signal_manifest_count"] == 2
    assert evidence["signal_manifest_readback_verified_count"] == 2
    assert evidence["signal_manifest_replay_verified_count"] == 2
    assert evidence["signal_manifest_mutation_probe_count"] == 2
    assert evidence["signal_manifest_mutation_verified_count"] == 2
    assert evidence["signal_manifest_mutation_preserved"] is True
    assert evidence["signal_manifest_mutation_probe_scope"] == "every_manifest"
    assert evidence["briefing_validated_multireport_provider_usage"] == {
        "provider_calls": 1,
        "input_tokens": 200,
        "cached_input_tokens": 20,
        "output_tokens": 50,
        "tool_calls": 0,
        "estimated_cost_usd": 0.0125,
        "pricing_status_counts": {"matched": 1},
        "unpriced_provider_call_count": 0,
        "cost_available": True,
    }


def test_cross_report_evidence_classifies_blocked_briefing_publish_as_review_hold(
    tmp_path: Path,
) -> None:
    state_db = tmp_path / "cross-report-policy-hold.sqlite"
    usage_db = tmp_path / "usage.sqlite"
    with sqlite3.connect(state_db) as conn:
        conn.executescript(
            """
            CREATE TABLE workflow_jobs (
              job_id TEXT, root_workflow_id TEXT, queue_name TEXT, status TEXT,
              entity_type TEXT, attempt_count INTEGER, output_reference TEXT,
              output_content_hash TEXT, started_at_utc TEXT, completed_at_utc TEXT,
              error_code TEXT
            );
            CREATE TABLE workflow_outbox (
              root_workflow_id TEXT, queue_name TEXT, status TEXT
            );
            CREATE TABLE workflow_briefing_opportunities (
              generation_job_id TEXT, source_hashes_json TEXT, publisher_ids_json TEXT
            );
            INSERT INTO workflow_jobs VALUES (
              'briefing-publish-1', 'root-1', 'wordpress_publish', 'blocked',
              'briefing', 1, '', '', '', '', 'cross_report_publish_live_disabled'
            );
            """
        )
    with sqlite3.connect(usage_db) as conn:
        conn.execute(
            """CREATE TABLE llm_usage_events (
              task_id TEXT, input_tokens INTEGER, cached_input_tokens INTEGER,
              output_tokens INTEGER, tool_calls INTEGER, estimated_cost_usd REAL,
              pricing_status TEXT
            )"""
        )

    evidence = _collect_cross_report_handoff_evidence(
        state_db=str(state_db),
        signal_store_db=str(tmp_path / "missing-signals.sqlite"),
        usage_db_path=str(usage_db),
        root_workflow_id="root-1",
        ctx=new_runtime_context(task_id="briefing-policy-hold-test"),
    )

    assert evidence["queue_terminal"] is True
    assert evidence["queue_terminal_failure_count"] == 1
    assert evidence["queue_expected_policy_hold_count"] == 1
    assert evidence["queue_unclassified_terminal_failure_count"] == 0
    assert evidence["signal_or_briefing_publication_job_count"] == 1
    assert evidence["signal_or_briefing_publication_status_counts"] == {"blocked": 1}
    assert evidence["signal_or_briefing_publication_policy_hold_count"] == 1
    assert evidence["signal_or_briefing_publication_unexpected_job_count"] == 0

    with sqlite3.connect(state_db) as conn:
        conn.execute(
            "UPDATE workflow_jobs SET status='succeeded',error_code='' "
            "WHERE job_id='briefing-publish-1'"
        )
    unsafe_evidence = _collect_cross_report_handoff_evidence(
        state_db=str(state_db),
        signal_store_db=str(tmp_path / "missing-signals.sqlite"),
        usage_db_path=str(usage_db),
        root_workflow_id="root-1",
        ctx=new_runtime_context(task_id="briefing-publication-safety-test"),
    )
    assert unsafe_evidence["signal_or_briefing_publication_status_counts"] == {
        "succeeded": 1
    }
    assert unsafe_evidence["signal_or_briefing_publication_policy_hold_count"] == 0
    assert unsafe_evidence["signal_or_briefing_publication_unexpected_job_count"] == 1


def test_workflow_job_usage_marks_cost_unavailable_for_unresolved_pricing(
    tmp_path: Path,
) -> None:
    usage_db = tmp_path / "usage.sqlite"
    with sqlite3.connect(usage_db) as conn:
        conn.execute(
            """CREATE TABLE llm_usage_events (
              task_id TEXT, input_tokens INTEGER, cached_input_tokens INTEGER,
              output_tokens INTEGER, tool_calls INTEGER, estimated_cost_usd REAL,
              pricing_status TEXT
            )"""
        )
        conn.executemany(
            "INSERT INTO llm_usage_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("workflow_job:brief-job-1", 10, 0, 5, 0, 0.001, "matched"),
                ("workflow_job:brief-job-2", 10, 0, 5, 0, 0.0, "missing"),
            ],
        )

    usage = _read_workflow_job_usage(str(usage_db), ["brief-job-1", "brief-job-2"])

    assert usage["provider_calls"] == 2
    assert usage["pricing_status_counts"] == {"matched": 1, "missing": 1}
    assert usage["unpriced_provider_call_count"] == 1
    assert usage["cost_available"] is False


def test_workflow_job_usage_marks_cost_unavailable_without_pricing_column(
    tmp_path: Path,
) -> None:
    usage_db = tmp_path / "legacy-usage.sqlite"
    with sqlite3.connect(usage_db) as conn:
        conn.execute(
            """CREATE TABLE llm_usage_events (
              task_id TEXT, input_tokens INTEGER, cached_input_tokens INTEGER,
              output_tokens INTEGER, tool_calls INTEGER, estimated_cost_usd REAL
            )"""
        )
        conn.execute(
            "INSERT INTO llm_usage_events VALUES (?, ?, ?, ?, ?, ?)",
            ("workflow_job:brief-job-1", 10, 0, 5, 0, 0.0),
        )

    usage = _read_workflow_job_usage(str(usage_db), ["brief-job-1"])

    assert usage["provider_calls"] == 1
    assert usage["unpriced_provider_call_count"] == 1
    assert usage["cost_available"] is False


def test_report_usage_summary_is_scoped_to_run_and_report(tmp_path: Path) -> None:
    usage_db = tmp_path / "usage.sqlite"
    with sqlite3.connect(usage_db) as conn:
        conn.execute(
            """CREATE TABLE llm_usage_events (
              run_id TEXT, report_id TEXT, input_tokens INTEGER,
              cached_input_tokens INTEGER, output_tokens INTEGER,
              tool_calls INTEGER, estimated_cost_usd REAL, pricing_status TEXT
            )"""
        )
        conn.executemany(
            "INSERT INTO llm_usage_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("run-1", "report-1", 10, 2, 5, 1, 0.01, "matched"),
                ("run-1", "report-2", 100, 20, 50, 3, 0.1, "matched"),
                ("run-2", "report-1", 1000, 200, 500, 9, 1.0, "matched"),
            ],
        )

    usage = _read_report_usage_summary(
        usage_db_path=str(usage_db), run_id="run-1", report_id="report-1"
    )

    assert usage == {
        "provider_calls": 1,
        "input_tokens": 10,
        "cached_input_tokens": 2,
        "output_tokens": 5,
        "tool_calls": 1,
        "estimated_cost_usd": 0.01,
        "pricing_status_counts": {"matched": 1},
        "unpriced_provider_call_count": 0,
        "cost_available": True,
    }


def test_report_usage_summary_marks_unresolved_pricing_unavailable(
    tmp_path: Path,
) -> None:
    usage_db = tmp_path / "usage.sqlite"
    with sqlite3.connect(usage_db) as conn:
        conn.execute(
            """CREATE TABLE llm_usage_events (
              run_id TEXT, report_id TEXT, input_tokens INTEGER,
              cached_input_tokens INTEGER, output_tokens INTEGER,
              tool_calls INTEGER, estimated_cost_usd REAL, pricing_status TEXT
            )"""
        )
        conn.execute(
            "INSERT INTO llm_usage_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("run-1", "report-1", 10, 0, 5, 0, 0.0, "missing"),
        )

    usage = _read_report_usage_summary(
        usage_db_path=str(usage_db), run_id="run-1", report_id="report-1"
    )

    assert usage["provider_calls"] == 1
    assert usage["pricing_status_counts"] == {"missing": 1}
    assert usage["estimated_cost_usd"] is None
    assert usage["cost_available"] is False


def test_report_usage_summary_does_not_invent_zeroes_without_a_ledger(
    tmp_path: Path,
) -> None:
    usage = _read_report_usage_summary(
        usage_db_path=str(tmp_path / "missing.sqlite"),
        run_id="run-1",
        report_id="report-1",
    )

    assert usage is None


def test_report_core_duration_uses_its_first_ingest_and_readiness_completion(
    tmp_path: Path,
) -> None:
    state_db = tmp_path / "workflow.sqlite"
    with sqlite3.connect(state_db) as conn:
        conn.execute(
            """CREATE TABLE workflow_jobs (
              queue_name TEXT, report_id TEXT, root_workflow_id TEXT,
              status TEXT, started_at_utc TEXT, completed_at_utc TEXT
            )"""
        )
        conn.executemany(
            "INSERT INTO workflow_jobs VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    "source_ingest",
                    "report-1",
                    "root-1",
                    "succeeded",
                    "2026-10-09T10:00:00+00:00",
                    "2026-10-09T10:00:10+00:00",
                ),
                (
                    "report_analysis",
                    "report-1",
                    "root-1",
                    "succeeded",
                    "2026-10-09T10:00:20+00:00",
                    "2026-10-09T10:00:50+00:00",
                ),
                (
                    "publication_readiness",
                    "report-1",
                    "root-1",
                    "succeeded",
                    "2026-10-09T10:00:51+00:00",
                    "2026-10-09T10:01:05+00:00",
                ),
                (
                    "publication_readiness",
                    "report-2",
                    "root-1",
                    "succeeded",
                    "2026-10-09T10:01:20+00:00",
                    "2026-10-09T10:02:00+00:00",
                ),
            ],
        )

    evidence = _read_report_core_duration(
        state_db=str(state_db), report_id="report-1", root_workflow_id="root-1"
    )

    assert evidence == {
        "core_processing_duration_seconds": 65.0,
        "core_processing_duration_scope": "complete",
    }
