# ruff: noqa: F401,F403,F405
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from dataclasses import replace

from pathlib import Path

from threading import Event, Lock

from types import SimpleNamespace

import pytest

from src.contracts.config import ConfigLoadRequest

from src.contracts.run_context import RunContext

from src.contracts.workflow_control import (
    SupervisorRunRequest,
    WorkflowSupervisorSettings,
)

from src.contracts.workflow_queue import (
    WORKFLOW_QUEUE_NAMES,
    MailboxDeliveryPayload,
    MailboxDeliveryResult,
    PublisherDiscoveryPayload,
    PublisherDiscoveryResult,
    ReportAcquisitionPayload,
    ReportAcquisitionResult,
    ReportAnalysisPayload,
    ReportAnalysisResult,
    ReportSelectionPayload,
    ReportSelectionResult,
    SourceIngestPayload,
    SourceIngestResult,
    WorkflowJobSubmission,
    WorkflowQueueControl,
)

from src.orchestrators.workflow_queue_orchestrator import (
    WorkflowQueueHandlerRegistration,
    WorkflowQueueHandlerResult,
)

from src.orchestrators.workflow_supervisor_orchestrator import (
    SupervisorDependencies,
    run_supervisor_once,
)

from src.orchestrators.workflow_worker_orchestrator import run_workflow_worker_once

from src.services import config_service

from src.services.workflow_queue_service import (
    enqueue_workflow_job,
    get_workflow_job,
    list_workflow_job_attempts,
    materialize_workflow_outbox,
    set_workflow_queue_control,
)

from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="parallel", task_id="parallel", span_id="parallel"
    )


def _request(
    *,
    max_parallel_workers: int,
    max_total_jobs: int,
    max_jobs_per_queue: int = 1,
    max_runtime_seconds: int = 120,
    supervisor_lease_seconds: int = 180,
    state_db: str = "state.sqlite",
) -> SupervisorRunRequest:
    return SupervisorRunRequest(
        schema_version="1.0",
        state_db=state_db,
        usage_db_path="usage.sqlite",
        worker_id="supervisor-parallel",
        now_utc="2026-08-11T00:00:00Z",
        settings=WorkflowSupervisorSettings(
            schema_version="1.0",
            enabled=True,
            worker_batches_enabled=True,
            max_parallel_workers=max_parallel_workers,
            max_jobs_per_queue=max_jobs_per_queue,
            max_total_jobs=max_total_jobs,
            max_runtime_seconds=max_runtime_seconds,
            lease_seconds=supervisor_lease_seconds,
        ),
    )


def _set_queue_concurrency(
    state_db: str,
    queue_name: str,
    limit: int,
    *,
    enabled: bool = True,
    mode: str = "active",
    emergency_stop_reason: str = "",
) -> None:
    set_workflow_queue_control(
        state_db,
        WorkflowQueueControl(
            schema_version="1.0",
            queue_name=queue_name,
            mode=mode,
            enabled=enabled,
            worker_concurrency_limit=limit,
            maximum_pending=100,
            maximum_fanout=5,
            max_attempts=3,
            lease_seconds=60,
            budget_profile="default",
            retry_delay_seconds=60,
            emergency_stop_reason=emergency_stop_reason,
            updated_at_utc="",
            updated_by="test",
        ),
        _ctx(),
    )


def _enqueue_report_acquisition_jobs(state_db: str, count: int) -> list[str]:
    _set_queue_concurrency(state_db, "report_acquisition", 5)
    job_ids = []
    for index in range(count):
        job, _ = enqueue_workflow_job(
            state_db,
            WorkflowJobSubmission(
                schema_version="1.0",
                queue_name="report_acquisition",
                job_type="report_acquisition.v1",
                payload=ReportAcquisitionPayload(
                    source_identity_id=f"source-{index}",
                    source_url=f"https://example.test/report-{index}.pdf",
                    publisher_id="publisher-1",
                    input_reference=f"snapshot:report-{index}",
                    input_content_hash=f"source-hash-{index}",
                ),
                idempotency_key=f"parallel:report-acquisition:{index}",
                deduplication_scope="supervisor-parallelism",
            ),
            _ctx(),
            now_utc="2026-08-11T00:00:00+00:00",
        )
        job_ids.append(job.job_id)
    return job_ids


def _queue_handler_registration(
    *,
    queue_name,
    job_type,
    payload_type,
    result_type,
    handler,
    allowed_downstream_job_types=(),
):
    return WorkflowQueueHandlerRegistration(
        queue_name=queue_name,
        job_type=job_type,
        payload_type=payload_type,
        result_type=result_type,
        handler=handler,
        default_retry_policy="bounded",
        default_lease_seconds=60,
        budget_profile="default",
        expected_external_effects=(),
        allowed_downstream_job_types=allowed_downstream_job_types,
    )


def _dependencies(worker) -> SupervisorDependencies:
    return SupervisorDependencies(
        acquire_lease=lambda *args, **kwargs: True,
        release_lease=lambda *args, **kwargs: None,
        materialize_outbox=lambda *args, **kwargs: [],
        recover_leases=lambda *args, **kwargs: [],
        run_worker=worker,
        reconcile=lambda *args, **kwargs: {
            "released_leases": [],
            "repaired_outbox_events": [],
            "anomalies": [],
        },
        queue_health=lambda *args, **kwargs: [],
    )


def _succeeded_worker(*, downstream_queue_names=(), **kwargs):
    del kwargs
    return SimpleNamespace(
        released_lease_job_ids=[],
        terminal_status="succeeded",
        downstream_queue_names=list(downstream_queue_names),
    )


__all__ = [name for name in globals() if not name.startswith("__")]
