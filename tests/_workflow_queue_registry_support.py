from __future__ import annotations

from pathlib import Path

import yaml

from src.contracts.analytics_projection import (
    PROJECTION_SCHEMA_VERSION,
    PROJECTION_VERSION,
    AnalyticsProjectionBatch,
    AnalyticsProjectionUpsertRequest,
    AnalyticsReportRow,
    ProjectionLineage,
    ReportCategoryProjection,
    ReportClaimProjection,
    ReportTagProjection,
)
from src.contracts.semantic_ids import EntityUid, PublisherId, ReportId
from src.contracts.workflow_queue import (
    WorkflowJob,
    WorkflowQueueName,
)
from src.services.analytics_store_service import upsert_projection
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="workflow-queue-registry-test")


def _workflow_job(
    *,
    queue_name: WorkflowQueueName = "vector_retention",
    job_type: str = "vector_retention.v1",
) -> WorkflowJob:
    return WorkflowJob(
        schema_version="1.0",
        job_id="workflow-job-1",
        queue_name=queue_name,
        job_type=job_type,
        job_schema_version="1.0",
        workflow_version="1.0",
        root_workflow_id="",
        parent_job_id="",
        trigger_event_id="",
        correlation_id="",
        entity_type="report",
        entity_id="report-1",
        publisher_id="publisher-1",
        source_identity_id="source-1",
        report_id="report-1",
        input_reference="retained:input",
        input_content_hash="input-hash",
        required_artifact_references=[],
        output_reference="",
        output_content_hash="",
        idempotency_key="workflow-job-1",
        deduplication_scope="test",
        priority=0,
        status="pending",
        available_at_utc="2026-07-18T00:00:00+00:00",
        attempt_count=0,
        max_attempts=3,
        lease_owner="",
        lease_expires_at_utc="",
        heartbeat_at_utc="",
        budget_profile="test",
        execution_plan_hash="plan-1",
        prompt_policy_version="",
        processing_version="queue-test.v1",
        created_at_utc="2026-07-18T00:00:00+00:00",
        updated_at_utc="2026-07-18T00:00:00+00:00",
        started_at_utc="",
        completed_at_utc="",
        error_code="",
        error_message_summary="",
        error_retryable=False,
        terminal_reason="",
        remediation_id="",
    )


def _isolated_app_config(tmp_path: Path) -> Path:
    config_payload = yaml.safe_load(
        Path("src/config/app.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(config_payload, dict)
    paths = config_payload["paths"]
    assert isinstance(paths, dict)
    ingest = config_payload["ingest"]
    assert isinstance(ingest, dict)
    analysis = config_payload["analysis"]
    assert isinstance(analysis, dict)
    ingest["gdrive_folder_id"] = "test-drive-folder"
    evidence_packs = ingest.setdefault("evidence_packs", {})
    assert isinstance(evidence_packs, dict)
    evidence_packs.update(
        {
            "parallel_workers": 1,
            "global_max_in_flight": 1,
            "global_min_interval_ms": 0,
            "doc_map_retry_delay_ms": 0,
        }
    )
    artifacts = ingest.setdefault("artifacts", {})
    assert isinstance(artifacts, dict)
    artifacts.update(
        {
            "parallel_workers": 1,
            "global_max_in_flight": 1,
            "global_min_interval_ms": 0,
        }
    )
    paths.update(
        {
            "output_dir": str(tmp_path / "out"),
            "cache_dir": str(tmp_path / "cache"),
            "state_db": str(tmp_path / "state.sqlite"),
            "reports_db": str(tmp_path / "reports.sqlite"),
            "signal_store_db": str(tmp_path / "signals.sqlite"),
            "ingest_lock": str(tmp_path / "ingest.lock"),
            "publisher_profiles": str(
                Path("Wordpress/config/publisher-profiles.json").resolve()
            ),
            "category_mappings": str(
                Path("src/config/category-mappings.yaml").resolve()
            ),
            "html_tag_acronyms": str(
                Path("src/config/html-tag-acronyms.yaml").resolve()
            ),
            "cover_styles": str(Path("src/config/cover-styles.yaml").resolve()),
        }
    )
    cost = config_payload["cost"]
    assert isinstance(cost, dict)
    cost.update(
        {
            "ledger_path": str(tmp_path / "cost-ledger.jsonl"),
            "daily_path": str(tmp_path / "cost-daily.json"),
            "usage_db_path": str(tmp_path / "llm-usage.sqlite"),
            "pricing_path": str(Path("src/config/llm-costs.yaml").resolve()),
        }
    )
    analysis["cost_ledger_path"] = str(tmp_path / "cost-ledger.jsonl")
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8"
    )
    return config_path


def _seed_projected_signal_source(
    db_path: str,
    *,
    report_id: str,
    publisher: str,
    publisher_id: str,
    claim_text: str = "Checkout trust signals are changing.",
    evidence_text: str = "",
) -> None:
    lineage = ProjectionLineage(
        schema_version=PROJECTION_SCHEMA_VERSION,
        projection_version=PROJECTION_VERSION,
        source_pack="queue-handler-test",
        source_ref=f"{report_id}:fixture",
        generated_at_utc="2026-07-18T00:00:00Z",
        analysis_run_id=f"{report_id}-analysis",
        model="gpt-5-mini",
    )
    report_key = ReportId(report_id)
    batch = AnalyticsProjectionBatch(
        schema_version=PROJECTION_SCHEMA_VERSION,
        projection_version=PROJECTION_VERSION,
        report=AnalyticsReportRow(
            schema_version=PROJECTION_SCHEMA_VERSION,
            projection_version=PROJECTION_VERSION,
            report_id=report_key,
            title=f"{publisher} Checkout Trust Outlook",
            publisher=publisher,
            publisher_id=PublisherId(publisher_id),
            source_md5=f"{report_id}-source-md5",
            ingest_run_id=f"{report_id}-ingest",
            analysis_run_id=f"{report_id}-analysis",
            time_period="2026-07",
            validation_status="pass",
            validation_severity="pass",
            text_density=1200.0,
            projection_generated_at_utc="2026-07-18T00:00:00Z",
        ),
        sections=[],
        findings=[],
        metrics=[],
        quotes=[],
        claims=[
            ReportClaimProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                claim_uid=EntityUid(f"{report_id}:claim:1"),
                report_id=report_key,
                claim=claim_text,
                evidence_id=f"{report_id}:claim:1",
                evidence=evidence_text
                or f"{publisher} observed a grounded checkout trust change.",
                pages=[2],
                lineage=lineage,
            )
        ],
        tags=[
            ReportTagProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                tag_uid=EntityUid(f"{report_id}:tag:checkout"),
                report_id=report_key,
                tag="checkout",
                tag_type="primary",
                lineage=lineage,
            )
        ],
        categories=[
            ReportCategoryProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                category_uid=EntityUid(f"{report_id}:category:commerce"),
                report_id=report_key,
                category_id="commerce",
                label="Commerce",
                fit_score=0.91,
                decision="primary",
                selected=True,
                evidence_sections=["Checkout"],
                lineage=lineage,
            )
        ],
        figures=[],
        vector_queue=[],
    )
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            batch=batch,
        ),
        _ctx(),
    )
