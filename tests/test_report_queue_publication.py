from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.semantic_ids import RunId, ValidationRunId
from src.contracts.validation_run_manifest import ValidationRunManifestCreateRequest
from src.contracts.workflow_queue import (
    PublicationReadinessPayload,
    WordPressPublishPayload,
    WorkflowJobSubmission,
)
from src.orchestrators import workflow_queue_orchestrator as queue_orchestrator
from src.orchestrators._publish_orchestrator.routing import (
    report_publish_package_checksum,
)
from src.orchestrators.admission_preflight_orchestrator import (
    admission_configuration_hash,
    admission_policy_hash,
)
from src.services.report_store_service import create_validation_run_manifest
from src.services.workflow_queue_service import approve_publication_package
from src.utils.errors import AppError
from tests.test_workflow_queue_registry import _ctx, _isolated_app_config, _workflow_job


def test_report_queue_uses_one_exact_approved_package_and_rejects_mutation(
    tmp_path: Path,
) -> None:
    config_path = _isolated_app_config(tmp_path)
    html_path = tmp_path / "out" / "report.html"
    readiness_path = (
        tmp_path / "out" / "report" / "report_analysis" / "publish_readiness.json"
    )
    html_path.parent.mkdir(parents=True)
    readiness_path.parent.mkdir(parents=True)
    html_path.write_text("<html><body>Report</body></html>", encoding="utf-8")
    readiness_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_id": "report-1",
                "status": "pass",
                "artifact_hashes": {},
                "rule_results": [],
                "final_html_hash": "hash",
                "publication_projection_hash": "projection",
                "configuration_hash": "configuration",
                "policy_hash": "policy",
                "producer_revision": "workspace",
                "created_at_utc": "2026-07-18T00:00:00+00:00",
                "expires_at_utc": "2026-07-19T00:00:00+00:00",
                "staleness_conditions": [],
                "provenance": {},
                "artifact_hash": "artifact",
            }
        ),
        encoding="utf-8",
    )
    checksum = report_publish_package_checksum(
        html_path=str(html_path), readiness_reference=str(readiness_path), ctx=_ctx()
    )
    readiness = PublicationReadinessPayload(
        entity_type="report",
        entity_package_reference=str(html_path),
        package_checksum=checksum,
        validation_reference=str(readiness_path),
        lineage_reference="retained:source",
        required_asset_status="ready",
        attributes={"config_path": str(config_path)},
    )
    response = queue_orchestrator._publication_readiness_handler(
        _workflow_job(
            queue_name="publication_readiness", job_type="publication_readiness.v1"
        ),
        readiness,
        _ctx(),
    )
    assert response.result.summary == {"readiness_status": "awaiting_review"}
    publish = WordPressPublishPayload(
        entity_type="report",
        entity_package_reference=str(html_path),
        package_checksum=checksum,
        readiness_reference=str(readiness_path),
        attributes={"config_path": str(config_path)},
        dry_run=True,
    )
    approval = approve_publication_package(
        str(tmp_path / "state.sqlite"),
        package_checksum=checksum,
        actor_id="reviewer",
        note="Report queue test.",
        publish_submission=WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="wordpress_publish",
            job_type="wordpress_publish.v1",
            payload=publish,
            idempotency_key="report-queue-test",
            deduplication_scope="validated-publication-package",
        ),
        ctx=_ctx(),
    )
    completed = queue_orchestrator._wordpress_publish_handler(
        _workflow_job(queue_name="wordpress_publish", job_type="wordpress_publish.v1"),
        replace(publish, approval_id=approval.approval_id),
        _ctx(),
    )
    assert completed.result.summary["publication_status"] == "dry_run"
    assert completed.external_effects == []
    html_path.write_text("<html><body>Changed</body></html>", encoding="utf-8")
    with pytest.raises(AppError, match="no longer matches its immutable references"):
        queue_orchestrator._wordpress_publish_handler(
            _workflow_job(
                queue_name="wordpress_publish", job_type="wordpress_publish.v1"
            ),
            replace(publish, approval_id=approval.approval_id),
            _ctx(),
        )


def test_validation_publication_readiness_records_same_lineage_manifest_stage(
    tmp_path: Path,
) -> None:
    """A durable review-ready package closes A21's manifest readiness boundary."""
    config_path = _isolated_app_config(tmp_path)
    html_path = tmp_path / "out" / "report.html"
    readiness_path = tmp_path / "out" / "report" / "publish_readiness.json"
    html_path.parent.mkdir(parents=True)
    readiness_path.parent.mkdir(parents=True)
    html_path.write_text("<html><body>Report</body></html>", encoding="utf-8")
    readiness_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_id": "report-1",
                "status": "pass",
                "artifact_hashes": {},
                "rule_results": [],
                "final_html_hash": "hash",
                "publication_projection_hash": "projection",
                "configuration_hash": "configuration",
                "policy_hash": "policy",
                "producer_revision": "workspace",
                "created_at_utc": "2026-07-18T00:00:00+00:00",
                "expires_at_utc": "2026-07-19T00:00:00+00:00",
                "staleness_conditions": [],
                "provenance": {},
                "artifact_hash": "artifact",
            }
        ),
        encoding="utf-8",
    )
    from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
    from src.services.config_service import build_ingest_settings, load_settings

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
    root_workflow_id = RunId("queue-root-1")
    validation_run_id = ValidationRunId("validation:queue-readiness")
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            validation_run_id=validation_run_id,
            cohort_id="cohort-1",
            workflow_run_id=root_workflow_id,
            configuration_hash=admission_configuration_hash(settings),
            policy_hash=admission_policy_hash(settings),
            producer_build_identity="workspace",
            created_at_utc="2026-07-18T00:00:00+00:00",
        ),
        _ctx(),
    )
    checksum = report_publish_package_checksum(
        html_path=str(html_path), readiness_reference=str(readiness_path), ctx=_ctx()
    )
    job = replace(
        _workflow_job(
            queue_name="publication_readiness", job_type="publication_readiness.v1"
        ),
        root_workflow_id=str(root_workflow_id),
        report_id="report-1",
        publisher_id="publisher-1",
        source_identity_id="source:report-1",
    )
    payload = PublicationReadinessPayload(
        entity_type="report",
        entity_package_reference=str(html_path),
        package_checksum=checksum,
        validation_reference=str(readiness_path),
        lineage_reference="retained:source",
        required_asset_status="ready",
        validation_run_id=str(validation_run_id),
        cohort_id="cohort-1",
        validation_attempt_number=1,
        validation_parent_attempt_number=0,
        attributes={"config_path": str(config_path)},
    )

    result = queue_orchestrator._publication_readiness_handler(job, payload, _ctx())

    assert result.result.summary == {"readiness_status": "awaiting_review"}
    with sqlite3.connect(settings.reports_db) as conn:
        recorded = conn.execute(
            "SELECT stage.workflow_run_id, stage.stage, stage.terminal_outcome, "
            "attempt.report_id, attempt.source_identity_id "
            "FROM validation_run_stage_records AS stage "
            "JOIN validation_run_entity_attempts AS attempt "
            "ON attempt.attempt_id=stage.attempt_id "
            "WHERE stage.validation_run_id=?",
            (str(validation_run_id),),
        ).fetchall()
    assert recorded == [
        (
            str(root_workflow_id),
            "publication_preflight",
            "succeeded",
            "report-1",
            "source:report-1",
        )
    ]
