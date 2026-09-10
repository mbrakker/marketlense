from __future__ import annotations

import json
import sqlite3
from hashlib import md5, sha256
from pathlib import Path

from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.report_store import ReportSourceRecordRequest
from src.contracts.run_context import RunContext
from src.contracts.validation_run_manifest import (
    FrozenValidationCohortQueueSubmissionRequest,
)
from src.contracts.workflow_queue import SourceIngestPayload
from src.orchestrators.admission_preflight_orchestrator import (
    admission_configuration_hash,
    admission_policy_hash,
)
from src.orchestrators.ingest_orchestrator import (
    submit_frozen_validation_cohort_to_queue,
)
from src.orchestrators.workflow_worker_orchestrator import run_workflow_worker_once
from src.services.config_service import build_ingest_settings, load_settings
from src.services.report_store_service import record_report_source
from src.services.workflow_queue_service import (
    load_workflow_job_payload,
    materialize_workflow_outbox,
)
from tests.test_workflow_queue_registry import _isolated_app_config


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="submission-request-run",
        task_id="task-1",
        span_id="span-1",
        producer_commit_sha="build-sha",
    )


def test_frozen_validation_queue_submission_binds_manifest_to_generated_queue_root(
    tmp_path,
    external_boundary_mocks_only,
    fake_openai,
) -> None:
    """The production bridge, rather than a caller, supplies matching lineage."""
    external_boundary_mocks_only.setenv("OPENAI_API_KEY", "test-openai-key")
    fake_openai.add("vector_stores.create", {"id": "vs_queue_test"})
    fake_openai.add("files.create", {"id": "file_queue_test"})
    fake_openai.add("vector_stores.files.create", {"id": "file_queue_test"})
    config_path = _isolated_app_config(tmp_path)
    settings = build_ingest_settings(
        IngestSettingsBuildRequest(
            schema_version="1.0",
            app_settings=load_settings(
                ConfigLoadRequest(schema_version="1.0", path=str(config_path)),
                _ctx(),
            ),
        ),
        _ctx(),
    )
    source_path = Path(
        "tests/fixtures/pdf_benchmark/golden/IAS - Industry_Pulse_Report_2026_ACIG.pdf"
    ).resolve()
    source_hash = md5(source_path.read_bytes(), usedforsecurity=False).hexdigest()
    record_report_source(
        ReportSourceRecordRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            source_domain="publisher.example",
            report_name="Industry Pulse Report 2026",
            landing_page_url="https://publisher.example/reports/industry-pulse-2026",
            downloaded_at_utc="2026-08-10T12:00:00Z",
            md5=source_hash,
            publisher_name="Industry Analytics Summit",
        ),
        _ctx(),
    )
    cohort_manifest = tmp_path / "frozen-cohort.json"
    member = {
        "schema_version": "1.0",
        "file_id": "report-1",
        "name": source_path.name,
        "modified_time": None,
        "md5_checksum": source_hash,
        "mime_type": "application/pdf",
        "report_id": "report-1",
        "source_identity_id": source_hash,
        "publisher_id": "publisher-1",
        "selection_reason": "deterministic_admission_preflight",
    }
    cohort_id = sha256(
        json.dumps(
            [
                {
                    key: member[key]
                    for key in (
                        "schema_version",
                        "file_id",
                        "name",
                        "modified_time",
                        "md5_checksum",
                        "mime_type",
                    )
                }
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    validation_run_id = (
        "validation:"
        + sha256(
            json.dumps(
                {
                    "cohort_id": cohort_id,
                    "configuration_hash": admission_configuration_hash(settings),
                    "policy_hash": admission_policy_hash(settings),
                    "producer_build_identity": "build-sha",
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    )
    cohort_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.2",
                "cohort_id": cohort_id,
                "cohort_size": 1,
                "validation_run_id": validation_run_id,
                "configuration_hash": admission_configuration_hash(settings),
                "policy_hash": admission_policy_hash(settings),
                "producer_build_identity": "build-sha",
                "members": [member],
                "admission_decisions": [
                    {
                        "file_id": "report-1",
                        "source_identity_id": source_hash,
                        "publisher_id": "publisher-1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    reports_db = settings.reports_db
    state_db = settings.state_db

    response = submit_frozen_validation_cohort_to_queue(
        FrozenValidationCohortQueueSubmissionRequest(
            schema_version="1.0",
            state_db=state_db,
            reports_db=reports_db,
            cohort_manifest=str(cohort_manifest),
            source_ingest_payloads=(
                SourceIngestPayload(
                    source_identity_id=source_hash,
                    source_artifact_reference=str(source_path),
                    source_content_hash=source_hash,
                    report_id="report-1",
                    parser_ocr_compatibility_version="parser.v1",
                    input_reference=str(source_path),
                    input_content_hash=source_hash,
                    processing_version="parser.v1",
                    attributes={"config_path": str(config_path)},
                ),
            ),
        ),
        _ctx(),
    )

    assert response.root_workflow_id
    assert response.validation_run_id == validation_run_id
    assert response.cohort_id == cohort_id
    assert len(response.jobs) == 1
    source_job = response.jobs[0]
    assert source_job.root_workflow_id == response.root_workflow_id
    payload = load_workflow_job_payload(source_job)
    assert payload.validation_run_id == response.validation_run_id
    assert payload.cohort_id == response.cohort_id
    worker_result = run_workflow_worker_once(
        state_db=state_db,
        queue_name="source_ingest",
        worker_id="validation-lineage-test-worker",
        ctx=_ctx(),
    )
    assert worker_result.terminal_status == "succeeded"
    materialize_workflow_outbox(state_db, "validation-lineage-test-worker", _ctx())
    selection_result = run_workflow_worker_once(
        state_db=state_db,
        queue_name="report_selection",
        worker_id="validation-lineage-test-worker",
        ctx=_ctx(),
    )
    assert selection_result.terminal_status == "succeeded"
    materialize_workflow_outbox(state_db, "validation-lineage-test-worker", _ctx())
    with sqlite3.connect(reports_db) as conn:
        run = conn.execute(
            "SELECT workflow_run_id FROM validation_runs WHERE validation_run_id=?",
            (response.validation_run_id,),
        ).fetchone()
        stage_roots = conn.execute(
            "SELECT DISTINCT workflow_run_id FROM validation_run_stage_records "
            "WHERE validation_run_id=?",
            (response.validation_run_id,),
        ).fetchall()
    with sqlite3.connect(state_db) as conn:
        queue_rows = conn.execute(
            "SELECT queue_name, root_workflow_id, payload_json FROM workflow_jobs "
            "WHERE report_id=? ORDER BY created_at_utc, job_id",
            ("report-1",),
        ).fetchall()
    assert run == (response.root_workflow_id,)
    assert stage_roots == [(response.root_workflow_id,)]
    assert [row[0] for row in queue_rows] == [
        "source_ingest",
        "report_selection",
        "report_analysis",
    ]
    for _queue_name, root_workflow_id, raw_payload in queue_rows:
        payload = json.loads(raw_payload)
        assert root_workflow_id == response.root_workflow_id
        assert payload["validation_run_id"] == response.validation_run_id
        assert payload["cohort_id"] == response.cohort_id
