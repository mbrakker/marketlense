from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
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
from src.contracts.files import WriteBytesRequest
from src.contracts.report_cards import CoverFingerprint
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import EntityUid, PublisherId, ReportId
from src.contracts.signal_cards import SignalCardContent
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPublishProjection,
)
from src.contracts.workflow_queue import (
    BriefingOpportunityPayload,
    ClaimEmbeddingPayload,
    CoverGenerationPayload,
    MailboxDeliveryPayload,
    MaintenancePayload,
    PublicationReadinessPayload,
    PublisherDiscoveryPayload,
    PublisherDiscoveryResult,
    QueuePayload,
    ReportAcquisitionPayload,
    ReportSelectionPayload,
    SignalCandidatePayload,
    SignalGenerationPayload,
    SourceIngestPayload,
    WordPressProjectionPayload,
    WordPressPublishPayload,
    WorkflowJob,
    WorkflowJobSubmission,
    WorkflowQueueName,
)
from src.orchestrators import workflow_queue_orchestrator as queue_orchestrator
from src.orchestrators.workflow_queue_orchestrator import (
    WorkflowQueueHandlerRegistration,
    WorkflowQueueHandlerResult,
)
from src.services.analytics_store_service import upsert_projection
from src.services.file_service import write_bytes
from src.services.workflow_queue_service import (
    approve_publication_package,
)
from src.utils.errors import AppError
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
            "pricing_path": str(Path("src/config/llm-costs.yaml").resolve()),
        }
    )
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
                claim="Checkout trust signals are changing.",
                evidence_id=f"{report_id}:claim:1",
                evidence=f"{publisher} observed a grounded checkout trust change.",
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


def test_verified_reference_and_execution_boundary_are_typed_and_fail_closed() -> None:
    job = _workflow_job()
    payload = MaintenancePayload(
        subject_id="retained-artifact",
        input_reference="retained:artifact",
        input_content_hash="artifact-hash",
    )

    completed = queue_orchestrator.execute_workflow_queue_handler(job, payload, _ctx())

    assert completed.result.output_reference == "retained:artifact"
    assert completed.result.output_content_hash == "artifact-hash"
    assert completed.result.output_verified is True
    with pytest.raises(AppError, match="requires a retained reference"):
        queue_orchestrator._verified_reference_handler(
            job, MaintenancePayload(subject_id="missing-reference"), _ctx()
        )
    with pytest.raises(AppError, match="not registered"):
        queue_orchestrator.resolve_workflow_queue_handler("unknown", "unknown.v1")
    with pytest.raises(AppError, match="does not match"):
        queue_orchestrator.execute_workflow_queue_handler(
            job,
            PublisherDiscoveryPayload(
                publisher_id="publisher-1",
                insights_url="https://example.test/insights",
                discovery_policy_version="v1",
            ),
            _ctx(),
        )


def test_execution_boundary_rejects_a_registered_handler_with_disallowed_fanout() -> (
    None
):
    job = _workflow_job()
    parent_payload = MaintenancePayload(
        subject_id="retained-artifact",
        input_reference="retained:artifact",
        input_content_hash="artifact-hash",
    )

    def disallowed_handler(
        _job: WorkflowJob,
        _payload: QueuePayload,
        _ctx_value: RunContext,
    ) -> WorkflowQueueHandlerResult:
        return WorkflowQueueHandlerResult(
            result=queue_orchestrator.WorkflowStageResult(
                output_reference="retained:artifact",
                output_content_hash="artifact-hash",
                output_verified=True,
            ),
            downstream=[
                WorkflowJobSubmission(
                    schema_version="1.0",
                    queue_name="publisher_discovery",
                    job_type="publisher_discovery.v1",
                    payload=PublisherDiscoveryPayload(
                        publisher_id="publisher-1",
                        insights_url="https://example.test/insights",
                        discovery_policy_version="v1",
                    ),
                    idempotency_key="forbidden-child",
                    deduplication_scope="test",
                )
            ],
        )

    registry = {
        ("vector_retention", "vector_retention.v1"): WorkflowQueueHandlerRegistration(
            queue_name="vector_retention",
            job_type="vector_retention.v1",
            payload_type=MaintenancePayload,
            result_type=queue_orchestrator.WorkflowStageResult,
            handler=disallowed_handler,
            default_retry_policy="test",
            default_lease_seconds=60,
            budget_profile="test",
            expected_external_effects=(),
            allowed_downstream_job_types=(),
        )
    }

    with pytest.raises(AppError, match="unapproved downstream"):
        queue_orchestrator.execute_workflow_queue_handler(
            job, parent_payload, _ctx(), registry=registry
        )


def test_execution_boundary_normalizes_a_registered_result_contract() -> None:
    job = _workflow_job()
    payload = MaintenancePayload(
        subject_id="retained-artifact",
        input_reference="retained:artifact",
        input_content_hash="artifact-hash",
    )

    def generic_result_handler(
        _job: WorkflowJob,
        _payload: QueuePayload,
        _ctx_value: RunContext,
    ) -> WorkflowQueueHandlerResult:
        return WorkflowQueueHandlerResult(
            result=queue_orchestrator.WorkflowStageResult(
                output_reference="retained:artifact",
                output_content_hash="artifact-hash",
                output_verified=True,
            )
        )

    registry = {
        ("vector_retention", "vector_retention.v1"): WorkflowQueueHandlerRegistration(
            queue_name="vector_retention",
            job_type="vector_retention.v1",
            payload_type=MaintenancePayload,
            result_type=PublisherDiscoveryResult,
            handler=generic_result_handler,
            default_retry_policy="test",
            default_lease_seconds=60,
            budget_profile="test",
            expected_external_effects=(),
            allowed_downstream_job_types=(),
        )
    }

    completed = queue_orchestrator.execute_workflow_queue_handler(
        job, payload, _ctx(), registry=registry
    )

    assert isinstance(completed.result, PublisherDiscoveryResult)
    assert completed.result.output_verified is True


def test_queue_attribute_and_budget_override_parsers_preserve_operator_intent() -> None:
    base = MaintenancePayload(attributes={})
    assert queue_orchestrator._requested_budget_override(base) is None
    assert queue_orchestrator._string_list_attribute(
        MaintenancePayload(attributes={"publishers": [" publisher-1 ", ""]}),
        "publishers",
    ) == ["publisher-1"]
    assert queue_orchestrator._positive_int_attribute(base, "limit", 3) == 3
    assert queue_orchestrator._positive_float_attribute(base, "cost", 1.25) == 1.25
    assert queue_orchestrator._boolean_attribute(base, "dry_run", True) is True

    override = queue_orchestrator._requested_budget_override(
        MaintenancePayload(
            attributes={
                "budget_override_actor": "operator-1",
                "budget_override_reason": "bounded live validation",
                "budget_override_expires_at_utc": "2026-07-18T01:00:00+00:00",
                "budget_override_scope": "briefing_generation",
            }
        )
    )
    assert override is not None
    assert override.actor == "operator-1"
    assert override.scope == "briefing_generation"

    with pytest.raises(AppError, match="requires actor"):
        queue_orchestrator._requested_budget_override(
            MaintenancePayload(attributes={"budget_override_actor": "operator-1"})
        )
    with pytest.raises(AppError, match="lists of strings"):
        queue_orchestrator._string_list_attribute(
            MaintenancePayload(attributes={"publishers": "publisher-1"}),
            "publishers",
        )
    for invalid in (True, "not-an-int", 0, ["not-an-int"]):
        with pytest.raises(AppError, match="positive integers"):
            queue_orchestrator._positive_int_attribute(
                MaintenancePayload(attributes={"limit": invalid}), "limit", 1
            )
    for invalid in (True, "not-a-float", 0, ["not-a-float"]):
        with pytest.raises(AppError, match="positive numbers"):
            queue_orchestrator._positive_float_attribute(
                MaintenancePayload(attributes={"cost": invalid}), "cost", 1.0
            )
    with pytest.raises(AppError, match="must be booleans"):
        queue_orchestrator._boolean_attribute(
            MaintenancePayload(attributes={"dry_run": "yes"}), "dry_run", False
        )


def test_queue_handoff_builders_preserve_hashes_and_workflow_lineage() -> None:
    job = _workflow_job(
        queue_name="report_acquisition", job_type="report_acquisition.v1"
    )
    ingest = queue_orchestrator._source_ingest_submission(
        job=job,
        artifact_reference="retained:source.pdf",
        source_hash="source-md5",
        source_identity_id="source-1",
        report_id="report-1",
        processing_version="parser.v2",
    )
    assert ingest.queue_name == "source_ingest"
    assert ingest.idempotency_key == "source-md5:source_ingest:parser.v2"
    assert ingest.parent_job_id == job.job_id
    assert isinstance(ingest.payload, SourceIngestPayload)
    assert ingest.payload.source_content_hash == "source-md5"

    stage = queue_orchestrator._stage_child_submission(
        job=job,
        payload=SourceIngestPayload(
            source_artifact_reference="retained:source.pdf",
            source_content_hash="source-md5",
            report_id="report-1",
            processing_version="parser.v2",
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


def test_operational_handlers_reject_incomplete_inputs_before_external_work() -> None:
    job = _workflow_job(
        queue_name="report_acquisition", job_type="report_acquisition.v1"
    )
    with pytest.raises(AppError, match="requires a source URL"):
        queue_orchestrator._report_acquisition_handler(
            job, ReportAcquisitionPayload(), _ctx()
        )
    with pytest.raises(AppError, match="requires source, title, and publisher"):
        queue_orchestrator._mailbox_delivery_handler(
            job, MailboxDeliveryPayload(), _ctx()
        )
    with pytest.raises(AppError, match="supports retained Briefing and Signal"):
        queue_orchestrator._wordpress_publish_handler(
            job, WordPressPublishPayload(entity_type="report"), _ctx()
        )
    with pytest.raises(AppError, match="selected topic"):
        queue_orchestrator._signal_generation_handler(
            job,
            SignalGenerationPayload(
                candidate_group_id="signal-group-1",
                frozen_evidence_manifest="signal-candidates:group-1",
            ),
            _ctx(),
        )
    with pytest.raises(AppError, match="immutable source artifact hash"):
        queue_orchestrator._report_stage_handler(
            resume_from_stage="source_prepared", next_queue="report_selection"
        )(job, SourceIngestPayload(), _ctx())


def test_signal_publish_adapter_retains_card_evidence_and_fallback_publishers(
    tmp_path,
) -> None:
    projection = SignalPublishProjection(
        schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
        title="Checkout trust is fragmenting",
        slug="checkout-trust-is-fragmenting",
        summary_html="<p>Trust signals diverged.</p>",
        body_html="<article><p>Evidence-backed body.</p></article>",
        evidence_ids=["evidence-a", "evidence-b"],
        source_report_ids=["report-a", "report-b"],
        topic_ids=["checkout"],
        confidence=0.82,
        uncertainty="Coverage is strongest in retail sources.",
        validation_status="approved",
        card_content=SignalCardContent(
            schema_version="1.0",
            summary="Trust signals diverged.",
            confidence=0.82,
            source_count=2,
            evidence_count=2,
            uncertainty="Coverage is strongest in retail sources.",
            fingerprint=CoverFingerprint(
                schema_version="1.0",
                geometry_family="signal_lattice",
                evidence_shape="system",
                direction="neutral",
                geography_scope="unknown",
                evidence_density="balanced",
                domain_layer="grid",
                seed=41,
                selection_reason="Queue adapter coverage test.",
            ),
        ),
        file_id="signal-file-1",
        html_text="<html><body>Signal</body></html>",
        topic_labels=["Checkout"],
        tag_labels=["Trust"],
        publisher_labels=["Publisher A"],
    )

    package = queue_orchestrator._signal_publish_package(
        group_id="signal-group-1",
        package_path="out/workflow_queue/signals/publish_package.json",
        projection=projection,
    )

    assert package.target_route == "wordpress:ml_signal"
    assert package.selected_theme_id == "signal-group-1"
    assert package.source_metadata == [
        {"report_id": "report-a", "publisher": "Publisher A"},
        {"report_id": "report-b", "publisher": ""},
    ]
    assert package.signal_card["evidence_count"] == 2
    assert package.machine_metadata["signal_validation_status"] == "approved"

    retained_path = str(tmp_path / "publish_package.json")
    persisted = queue_orchestrator._persist_queue_publish_package(
        package, retained_path, _ctx()
    )
    readback = queue_orchestrator._cross_report_package_from_artifact(
        retained_path, _ctx()
    )

    assert persisted.artifact_sha256
    assert queue_orchestrator._package_checksum(persisted) == persisted.artifact_sha256
    assert readback.artifact_sha256 == persisted.artifact_sha256
    assert readback.canonical_artifact_path == retained_path
    assert queue_orchestrator._verified_file_hash(retained_path, _ctx())

    config_path = _isolated_app_config(tmp_path)
    cover_result = queue_orchestrator._cover_generation_handler(
        _workflow_job(queue_name="cover_generation", job_type="cover_generation.v1"),
        CoverGenerationPayload(
            entity_type="signal",
            entity_package_reference=retained_path,
            input_content_hash=persisted.artifact_sha256,
            attributes={"config_path": str(config_path)},
        ),
        _ctx(),
    )
    assert cover_result.result.output_verified is True
    assert cover_result.downstream[0].queue_name == "publication_readiness"
    assert Path(cover_result.result.output_reference).is_file()

    briefing_path = str(tmp_path / "briefing_publish_package.json")
    briefing_package = queue_orchestrator._persist_queue_publish_package(
        replace(
            persisted,
            package_id="briefing-package-1",
            file_id="briefing-file-1",
            target_route="wordpress:ml_briefing",
            signal_card={},
            briefing_card={},
        ),
        briefing_path,
        _ctx(),
    )
    briefing_cover_result = queue_orchestrator._cover_generation_handler(
        _workflow_job(queue_name="cover_generation", job_type="cover_generation.v1"),
        CoverGenerationPayload(
            entity_type="briefing",
            entity_package_reference=briefing_path,
            input_content_hash=briefing_package.artifact_sha256,
            attributes={"config_path": str(config_path)},
        ),
        _ctx(),
    )
    assert briefing_cover_result.result.output_verified is True
    assert briefing_cover_result.downstream[0].queue_name == "publication_readiness"

    ready_result = queue_orchestrator._publication_readiness_handler(
        _workflow_job(
            queue_name="publication_readiness", job_type="publication_readiness.v1"
        ),
        PublicationReadinessPayload(
            entity_type="briefing",
            entity_package_reference=briefing_cover_result.result.output_reference,
            package_checksum=briefing_cover_result.result.output_content_hash,
            validation_reference=briefing_path,
            lineage_reference=briefing_path,
            required_asset_status="ready",
            attributes={"config_path": str(config_path)},
        ),
        _ctx(),
    )
    assert ready_result.result.output_verified is True
    assert ready_result.result.summary == {"readiness_status": "awaiting_review"}
    assert ready_result.downstream == []
    unready_result = queue_orchestrator._publication_readiness_handler(
        _workflow_job(
            queue_name="publication_readiness", job_type="publication_readiness.v1"
        ),
        PublicationReadinessPayload(
            entity_type="briefing",
            entity_package_reference=briefing_cover_result.result.output_reference,
            package_checksum="unready-checksum",
            validation_reference=briefing_path,
            lineage_reference=briefing_path,
            required_asset_status="missing",
            attributes={"config_path": str(config_path)},
        ),
        _ctx(),
    )
    assert unready_result.result.output_verified is False
    assert unready_result.result.summary == {"readiness_status": "not_publishable"}

    opportunity_result = queue_orchestrator._briefing_opportunity_handler(
        _workflow_job(
            queue_name="briefing_opportunity", job_type="briefing_opportunity.v1"
        ),
        BriefingOpportunityPayload(
            topic="Checkout trust",
            geography="global",
            rolling_window="2026-W29",
            source_hashes=["source-hash-a", "source-hash-b"],
            briefing_policy_version="briefing-policy.v1",
            processing_version="briefing-processing.v1",
            prompt_policy_version="briefing-prompt.v1",
            attributes={
                "config_path": str(config_path),
                "publisher_ids": ["publisher-a", "publisher-b"],
            },
        ),
        _ctx(),
    )
    assert opportunity_result.result.output_verified is True
    assert opportunity_result.result.summary == {
        "opportunity_status": "frozen",
        "source_count": 2,
    }
    assert opportunity_result.result.output_reference.startswith(
        "workflow-opportunity:"
    )

    embedding_result = queue_orchestrator._claim_embedding_handler(
        _workflow_job(queue_name="claim_embedding", job_type="claim_embedding.v1"),
        ClaimEmbeddingPayload(
            claim_id="claim-queue-test",
            embedding_row_id="embedding-queue-test",
            model_version="text-embedding-3-small",
            input_reference="analytics:claim:claim-queue-test",
            input_content_hash="claim-content-hash",
            attributes={"config_path": str(config_path), "dry_run": True},
        ),
        _ctx(),
    )
    assert embedding_result.result.output_verified is True
    assert embedding_result.result.summary == {
        "embedded_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
    }
    assert embedding_result.external_effects == []

    reports_db = str(tmp_path / "reports.sqlite")
    _seed_projected_signal_source(
        reports_db,
        report_id="report-signal-a",
        publisher="Publisher A",
        publisher_id="publisher-a",
    )
    _seed_projected_signal_source(
        reports_db,
        report_id="report-signal-b",
        publisher="Publisher B",
        publisher_id="publisher-b",
    )
    candidate_result = queue_orchestrator._signal_candidate_handler(
        replace(
            _workflow_job(
                queue_name="signal_candidate", job_type="signal_candidate.v1"
            ),
            publisher_id="publisher-a",
        ),
        SignalCandidatePayload(
            report_id="report-signal-a",
            projection_reference="analytics:report:report-signal-a",
            signal_selection_policy_version="signal-selection.v1",
            input_reference="analytics:report:report-signal-a",
            input_content_hash="projection-content-hash",
            processing_version="signal-processing.v1",
            attributes={
                "config_path": str(config_path),
                "topic": "Checkout trust",
                "publisher_filters": ["publisher-a", "publisher-b"],
                "generate_signals": False,
            },
        ),
        _ctx(),
    )
    assert candidate_result.result.output_verified is True
    assert candidate_result.result.summary["candidate_count"] >= 1
    assert candidate_result.result.summary["group_count"] >= 1
    assert candidate_result.downstream == []

    publish_submission = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="wordpress_publish",
        job_type="wordpress_publish.v1",
        payload=WordPressPublishPayload(
            entity_type="briefing",
            entity_package_reference=briefing_cover_result.result.output_reference,
            package_checksum=briefing_cover_result.result.output_content_hash,
            attributes={"config_path": str(config_path)},
        ),
        idempotency_key="briefing-wordpress-publish",
        deduplication_scope="validated-publication-package",
    )
    approval = approve_publication_package(
        str(tmp_path / "state.sqlite"),
        package_checksum=briefing_cover_result.result.output_content_hash,
        actor_id="queue-test-reviewer",
        note="Local publication guard coverage.",
        publish_submission=publish_submission,
        ctx=_ctx(),
    )
    with pytest.raises(AppError, match="does not match its retained package route"):
        queue_orchestrator._wordpress_publish_handler(
            _workflow_job(
                queue_name="wordpress_publish", job_type="wordpress_publish.v1"
            ),
            WordPressPublishPayload(
                entity_type="signal",
                entity_package_reference=briefing_cover_result.result.output_reference,
                package_checksum=briefing_cover_result.result.output_content_hash,
                approval_id=approval.approval_id,
                attributes={"config_path": str(config_path)},
            ),
            _ctx(),
        )
    with pytest.raises(AppError, match="remains disabled by configuration"):
        queue_orchestrator._wordpress_publish_handler(
            _workflow_job(
                queue_name="wordpress_publish", job_type="wordpress_publish.v1"
            ),
            replace(publish_submission.payload, approval_id=approval.approval_id),
            _ctx(),
        )

    checksum_mismatch_readiness = queue_orchestrator._publication_readiness_handler(
        _workflow_job(
            queue_name="publication_readiness", job_type="publication_readiness.v1"
        ),
        PublicationReadinessPayload(
            entity_type="briefing",
            entity_package_reference=briefing_cover_result.result.output_reference,
            package_checksum="approved-different-checksum",
            validation_reference=briefing_path,
            lineage_reference=briefing_path,
            required_asset_status="ready",
            attributes={"config_path": str(config_path)},
        ),
        _ctx(),
    )
    checksum_mismatch_submission = replace(
        publish_submission,
        idempotency_key="briefing-wordpress-publish-mismatch",
        payload=replace(
            publish_submission.payload,
            package_checksum=checksum_mismatch_readiness.result.output_content_hash,
        ),
    )
    mismatch_approval = approve_publication_package(
        str(tmp_path / "state.sqlite"),
        package_checksum=checksum_mismatch_readiness.result.output_content_hash,
        actor_id="queue-test-reviewer",
        note="Local checksum guard coverage.",
        publish_submission=checksum_mismatch_submission,
        ctx=_ctx(),
    )
    with pytest.raises(AppError, match="does not match the retained entity package"):
        queue_orchestrator._wordpress_publish_handler(
            _workflow_job(
                queue_name="wordpress_publish", job_type="wordpress_publish.v1"
            ),
            replace(
                checksum_mismatch_submission.payload,
                approval_id=mismatch_approval.approval_id,
            ),
            _ctx(),
        )
    with pytest.raises(AppError, match="projection remains disabled"):
        queue_orchestrator._wordpress_projection_handler(
            _workflow_job(
                queue_name="wordpress_projection", job_type="wordpress_projection.v1"
            ),
            WordPressProjectionPayload(
                published_entity_reference=briefing_cover_result.result.output_reference,
                wordpress_id="123",
                entity_type="briefing",
                input_content_hash=briefing_cover_result.result.output_content_hash,
                attributes={"config_path": str(config_path)},
            ),
            _ctx(),
        )
    with pytest.raises(AppError, match="requires a retained verified file"):
        queue_orchestrator._verified_file_hash(str(tmp_path / "missing.pdf"), _ctx())

    invalid_artifacts = (
        ("not-json.json", b"not-json", "not valid JSON"),
        ("not-object.json", b"[]", "not a valid retained entity artifact"),
        ("wrong-contract.json", b"{}", "incompatible with the current contract"),
    )
    for filename, content, expected_message in invalid_artifacts:
        invalid_path = str(tmp_path / filename)
        write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=invalid_path,
                content=content,
                make_parents=True,
            ),
            _ctx(),
        )
        with pytest.raises(AppError, match=expected_message):
            queue_orchestrator._cross_report_package_from_artifact(invalid_path, _ctx())

    with pytest.raises(AppError, match="does not match the retained package route"):
        queue_orchestrator._cover_generation_handler(
            _workflow_job(
                queue_name="cover_generation", job_type="cover_generation.v1"
            ),
            CoverGenerationPayload(
                entity_type="briefing",
                entity_package_reference=retained_path,
            ),
            _ctx(),
        )
    with pytest.raises(AppError, match="no longer matches its queued checksum"):
        queue_orchestrator._cover_generation_handler(
            _workflow_job(
                queue_name="cover_generation", job_type="cover_generation.v1"
            ),
            CoverGenerationPayload(
                entity_type="signal",
                entity_package_reference=retained_path,
                input_content_hash="different-checksum",
            ),
            _ctx(),
        )


def test_source_ingest_checkpoint_hands_off_to_report_selection(
    tmp_path: Path,
) -> None:
    config_path = _isolated_app_config(tmp_path)
    source_path = Path(
        "tests/fixtures/pdf_benchmark/golden/IAS - Industry_Pulse_Report_2026_ACIG.pdf"
    ).resolve()
    source_hash = queue_orchestrator._verified_file_hash(str(source_path), _ctx())
    job = _workflow_job(queue_name="source_ingest", job_type="source_ingest.v1")

    result = queue_orchestrator._report_stage_handler(
        resume_from_stage="",
        stop_after_stage="source_prepared",
        next_queue="report_selection",
    )(
        job,
        SourceIngestPayload(
            source_identity_id="ias-industry-pulse",
            source_artifact_reference=str(source_path),
            source_content_hash=source_hash,
            report_id="ias-industry-pulse-2026",
            parser_ocr_compatibility_version="parser.v1",
            input_reference=str(source_path),
            input_content_hash=source_hash,
            processing_version="parser.v1",
            attributes={"config_path": str(config_path)},
        ),
        _ctx(),
    )

    assert result.result.output_verified is True
    assert result.result.summary["checkpoint"] == "source_prepared"
    assert len(result.downstream) == 1
    child = result.downstream[0]
    assert child.queue_name == "report_selection"
    assert child.parent_job_id == job.job_id
    assert child.idempotency_key == (
        f"ias-industry-pulse-2026:report_selection:{source_hash}:parser.v1"
    )

    selection_result = queue_orchestrator._report_stage_handler(
        resume_from_stage="source_prepared",
        stop_after_stage="selection_complete",
        next_queue="report_analysis",
    )(
        replace(
            job,
            queue_name="report_selection",
            job_type="report_selection.v1",
        ),
        ReportSelectionPayload(
            report_id="ias-industry-pulse-2026",
            source_prepared_checkpoint="source_prepared",
            input_reference=str(source_path),
            input_content_hash=source_hash,
            processing_version="parser.v1",
            attributes={"config_path": str(config_path)},
        ),
        _ctx(),
    )
    assert selection_result.result.output_verified is True
    assert selection_result.result.summary["checkpoint"] == "selection_complete"
    assert selection_result.downstream[0].queue_name == "report_analysis"


# Worker lifecycle failure cases live in test_workflow_queue_worker_failures.py.
