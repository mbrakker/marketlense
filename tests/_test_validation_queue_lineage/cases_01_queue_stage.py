# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403
from ._shared import _workflow_job


def test_queue_stage_builder_preserves_workflow_lineage() -> None:
    job = _workflow_job(
        queue_name="report_acquisition", job_type="report_acquisition.v1"
    )
    stage = queue_orchestrator._stage_child_submission(
        job=job,
        payload=SourceIngestPayload(
            source_artifact_reference="retained:source.pdf",
            source_content_hash="source-md5",
            report_id="report-1",
            processing_version="parser.v2",
            validation_run_id="validation-1",
            cohort_id="cohort-1",
            validation_attempt_number=2,
            validation_parent_attempt_number=1,
        ),
        next_queue="report_selection",
        next_payload=SourceIngestPayload(
            source_artifact_reference="retained:source.pdf",
            source_content_hash="source-md5",
            report_id="report-1",
            processing_version="parser.v2",
        ),
    )
    assert stage.idempotency_key == "report-1:report_selection:source-md5:parser.v2"
    assert stage.root_workflow_id == job.job_id
    assert stage.correlation_id == job.job_id
    assert stage.source_identity_id == "source-1"
    assert stage.payload.validation_run_id == "validation-1"
    assert stage.payload.cohort_id == "cohort-1"
    assert stage.payload.validation_attempt_number == 2
    assert stage.payload.validation_parent_attempt_number == 1
