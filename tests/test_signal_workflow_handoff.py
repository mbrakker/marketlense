from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.config import ConfigLoadRequest
from src.contracts.files import WriteBytesRequest
from src.contracts.publish import PublishOutcome
from src.contracts.report_cards import CoverFingerprint
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidateReadRequest,
    SignalCandidateStoreRequest,
)
from src.contracts.signal_cards import SignalCardContent
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPublishProjection,
    SignalSourceAttribution,
)
from src.contracts.workflow_queue import (
    BriefingOpportunityPayload,
    ClaimEmbeddingPayload,
    CoverGenerationPayload,
    PublicationReadinessPayload,
    SignalCandidatePayload,
    SignalGenerationPayload,
    WordPressProjectionPayload,
    WordPressPublishPayload,
    WorkflowJobSubmission,
)
from src.contracts.wordpress import (
    WordPressPostLookupResponse,
    WordPressTagEnsureResponse,
    WordPressTaxonomyEnsureResponse,
)
from src.orchestrators import workflow_queue_orchestrator as queue_orchestrator
from src.orchestrators._workflow_queue_handlers.registry import (
    execute_workflow_queue_handler,
)
from src.orchestrators.publish_orchestrator import publish_cross_report_package
from src.services import analytics_store_service
from src.services.config_service import load_settings
from src.services.file_service import write_bytes
from src.services.workflow_queue_service import (
    approve_publication_package,
    claim_next_workflow_job,
    complete_workflow_job,
    enqueue_workflow_job,
    fail_workflow_job,
    load_workflow_job_payload,
    materialize_workflow_outbox,
    start_workflow_job,
)
from src.utils.errors import AppError
from tests._workflow_queue_registry_support import (
    _ctx,
    _isolated_app_config,
    _seed_projected_signal_source,
    _workflow_job,
)


def test_signal_publish_adapter_does_not_borrow_deduplicated_publisher_labels(
    tmp_path,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setenv("OPENAI_API_KEY", "test-openai-key")
    projection = SignalPublishProjection(
        schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
        title="Checkout trust is fragmenting",
        slug="checkout-trust-is-fragmenting",
        summary_html="<p>Trust signals diverged.</p>",
        body_html="<article><p>Evidence-backed body.</p></article>",
        evidence_ids=["evidence-a", "evidence-b", "evidence-c"],
        source_report_ids=["report-a", "report-b", "report-c"],
        topic_ids=["checkout"],
        confidence=0.82,
        uncertainty="Coverage is strongest in retail sources.",
        validation_status="approved",
        card_content=SignalCardContent(
            schema_version="1.0",
            summary="Trust signals diverged.",
            confidence=0.82,
            source_count=3,
            evidence_count=3,
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
        publisher_labels=["Publisher A", "Publisher B"],
        source_attributions=[
            SignalSourceAttribution(report_id="report-a", publisher="Publisher A"),
            SignalSourceAttribution(report_id="report-b", publisher="Publisher B"),
        ],
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
        {"report_id": "report-b", "publisher": "Publisher B"},
        {"report_id": "report-c", "publisher": ""},
    ]
    assert package.signal_card["evidence_count"] == 3
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
    assert readback.source_metadata == package.source_metadata

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
    assert cover_result.downstream[0].payload.attributes["config_path"] == str(
        config_path
    )
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
    assert briefing_cover_result.downstream[0].payload.attributes["config_path"] == str(
        config_path
    )

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
    with sqlite3.connect(tmp_path / "state.sqlite") as connection:
        generation_submission_json = connection.execute(
            "SELECT submission_json FROM workflow_outbox "
            "WHERE queue_name = 'briefing_generation'"
        ).fetchone()
    assert generation_submission_json is not None
    assert json.loads(generation_submission_json[0])["payload"]["attributes"][
        "config_path"
    ] == str(config_path)

    embedding_result = queue_orchestrator._claim_embedding_handler(
        _workflow_job(queue_name="claim_embedding", job_type="claim_embedding.v1"),
        ClaimEmbeddingPayload(
            claim_id="claim-queue-test",
            embedding_row_id="embedding-queue-test",
            model_version="text-embedding-3-large",
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
                "generate_signals": True,
            },
        ),
        _ctx(),
    )
    assert candidate_result.result.output_verified is True
    assert candidate_result.result.summary["candidate_count"] >= 1
    assert candidate_result.result.summary["group_count"] >= 1
    assert candidate_result.downstream
    signal_generation_children = [
        child
        for child in candidate_result.downstream
        if child.queue_name == "signal_generation"
    ]
    assert signal_generation_children
    assert all(
        child.payload.source_report_ids and child.payload.evidence_ids
        for child in signal_generation_children
    )
    generation_submission = signal_generation_children[0]
    generation_payload = generation_submission.payload
    for altered_payload in (
        replace(
            generation_payload,
            frozen_evidence_manifest="signal-candidates:changed-group",
        ),
        replace(generation_payload, input_content_hash="changed-manifest-hash"),
        replace(
            generation_payload,
            attributes={
                **generation_payload.attributes,
                "max_source_reports": 1,
            },
        ),
    ):
        with pytest.raises(AppError) as exc_info:
            queue_orchestrator._signal_generation_handler(
                replace(
                    _workflow_job(
                        queue_name="signal_generation",
                        job_type="signal_generation.v1",
                    ),
                    entity_type="signal",
                    entity_id=altered_payload.candidate_group_id,
                    input_reference=altered_payload.input_reference,
                    input_content_hash=altered_payload.input_content_hash,
                ),
                altered_payload,
                _ctx(),
            )
        assert exc_info.value.code == "signal_frozen_manifest_changed"
        assert exc_info.value.retryable is False
    generation_result = queue_orchestrator._signal_generation_handler(
        replace(
            _workflow_job(
                queue_name="signal_generation", job_type="signal_generation.v1"
            ),
            entity_type="signal",
            entity_id=generation_payload.candidate_group_id,
            input_reference=generation_payload.input_reference,
            input_content_hash=generation_payload.input_content_hash,
        ),
        generation_payload,
        _ctx(),
    )
    assert generation_result.result.output_verified is True
    assert generation_result.downstream[0].queue_name == "cover_generation"
    generated_package = queue_orchestrator._cross_report_package_from_artifact(
        generation_result.result.output_reference, _ctx()
    )
    assert generated_package.selected_report_ids == generation_payload.source_report_ids
    assert generated_package.evidence_reference_ids == generation_payload.evidence_ids
    replayed_candidate_result = queue_orchestrator._signal_candidate_handler(
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
                "generate_signals": True,
            },
        ),
        _ctx(),
    )
    assert [
        child.idempotency_key for child in replayed_candidate_result.downstream
    ] == [child.idempotency_key for child in candidate_result.downstream]
    assert [
        child.payload.input_content_hash
        for child in replayed_candidate_result.downstream
    ] == [child.payload.input_content_hash for child in candidate_result.downstream]
    assert all(
        child.payload.attributes["config_path"] == str(config_path)
        for child in candidate_result.downstream
    )

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


def test_single_source_signal_candidate_is_held_before_generation_queue(
    tmp_path: Path,
) -> None:
    config_path = _isolated_app_config(tmp_path)
    reports_db = str(tmp_path / "reports.sqlite")
    _seed_projected_signal_source(
        reports_db,
        report_id="report-single-source",
        publisher="Publisher A",
        publisher_id="publisher-a",
    )
    result = queue_orchestrator._signal_candidate_handler(
        replace(
            _workflow_job(
                queue_name="signal_candidate", job_type="signal_candidate.v1"
            ),
            publisher_id="publisher-a",
        ),
        SignalCandidatePayload(
            report_id="report-single-source",
            projection_reference="analytics:report:report-single-source",
            signal_selection_policy_version="signal-selection.v1",
            input_reference="analytics:report:report-single-source",
            input_content_hash="single-source-projection-hash",
            processing_version="signal-processing.v1",
            attributes={
                "config_path": str(config_path),
                "topic": "Checkout trust",
                "publisher_filters": ["publisher-a"],
                "generate_signals": True,
                "minimum_source_reports": 2,
                "minimum_evidence_items": 2,
            },
        ),
        _ctx(),
    )

    assert result.result.summary["publication_hold_group_count"] >= 1
    assert json.loads(result.result.summary["publication_hold_reason_counts"]) == {
        "signal_grounding_insufficient": result.result.summary[
            "publication_hold_group_count"
        ]
    }
    assert not [
        child for child in result.downstream if child.queue_name == "signal_generation"
    ]


def test_queued_signal_rejects_changed_projected_evidence_before_publication(
    tmp_path: Path,
) -> None:
    ctx = _ctx()
    config_path = _isolated_app_config(tmp_path)
    app = load_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(config_path)), ctx
    )
    for report_id, publisher, publisher_id in (
        ("report-stale-a", "Publisher A", "publisher-a"),
        ("report-stale-b", "Publisher B", "publisher-b"),
    ):
        _seed_projected_signal_source(
            app.reports_db,
            report_id=report_id,
            publisher=publisher,
            publisher_id=publisher_id,
        )

    candidate_result = queue_orchestrator._signal_candidate_handler(
        _workflow_job(queue_name="signal_candidate", job_type="signal_candidate.v1"),
        SignalCandidatePayload(
            report_id="report-stale-a",
            projection_reference="analytics:report:report-stale-a",
            signal_selection_policy_version="signal-selection.v1",
            input_reference="analytics:report:report-stale-a",
            input_content_hash="projection-content-hash",
            processing_version="signal-processing.v1",
            attributes={
                "config_path": str(config_path),
                "topic": "Checkout trust",
                "publisher_filters": ["publisher-a", "publisher-b"],
                "generate_signals": True,
            },
        ),
        ctx,
    )
    generation_submissions = [
        submission
        for submission in candidate_result.downstream
        if submission.queue_name == "signal_generation"
    ]
    assert generation_submissions
    queued_job, created = enqueue_workflow_job(
        app.state_db, generation_submissions[0], ctx
    )
    assert created is True

    _seed_projected_signal_source(
        app.reports_db,
        report_id="report-stale-a",
        publisher="Publisher A",
        publisher_id="publisher-a",
        claim_text="Checkout trust evidence was replaced after approval.",
        evidence_text="The re-extracted source now supports a different claim.",
    )
    leased = claim_next_workflow_job(
        app.state_db, "signal_generation", "stale-signal-worker", ctx
    )
    assert leased is not None
    running = start_workflow_job(
        app.state_db, leased.job_id, "stale-signal-worker", ctx
    )
    with pytest.raises(AppError) as exc_info:
        execute_workflow_queue_handler(running, load_workflow_job_payload(running), ctx)

    assert exc_info.value.code == "signal_frozen_manifest_evidence_changed"
    assert exc_info.value.retryable is False
    failed = fail_workflow_job(
        app.state_db,
        running.job_id,
        "stale-signal-worker",
        exc_info.value,
        ctx,
    )
    assert failed.status == "dead_letter"
    assert failed.error_code == "signal_frozen_manifest_evidence_changed"
    with sqlite3.connect(app.state_db) as connection:
        downstream_count = connection.execute(
            "SELECT COUNT(*) FROM workflow_outbox WHERE parent_job_id = ?",
            (queued_job.job_id,),
        ).fetchone()[0]
    assert downstream_count == 0


def test_durable_signal_queue_keeps_same_topic_group_snapshots_distinct(
    tmp_path: Path,
    external_boundary_mocks_only,
    publish_settings_factory,
) -> None:
    external_boundary_mocks_only.setenv("OPENAI_API_KEY", "test-openai-key")
    ctx = _ctx()
    config_path = _isolated_app_config(tmp_path)
    app = load_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(config_path)), ctx
    )
    for report_id, publisher, publisher_id in (
        ("report-signal-a", "Publisher A", "publisher-a"),
        ("report-signal-b", "Publisher B", "publisher-b"),
        ("report-signal-c", "Publisher A", "publisher-a"),
    ):
        _seed_projected_signal_source(
            app.reports_db,
            report_id=report_id,
            publisher=publisher,
            publisher_id=publisher_id,
        )

    candidate_result = queue_orchestrator._signal_candidate_handler(
        _workflow_job(queue_name="signal_candidate", job_type="signal_candidate.v1"),
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
                "generate_signals": True,
            },
        ),
        ctx,
    )
    generation_submissions = [
        item
        for item in candidate_result.downstream
        if item.queue_name == "signal_generation"
    ]
    assert len(generation_submissions) >= 2
    queued_submissions = generation_submissions[:2]
    first_submission = queued_submissions[0]
    first_payload = first_submission.payload
    assert isinstance(first_payload, SignalGenerationPayload)
    first_candidates = analytics_store_service.read_signal_candidates(
        SignalCandidateReadRequest(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=first_payload.input_reference,
            manifest_sha256=first_payload.frozen_manifest_sha256,
        ),
        ctx,
    )
    assert len(first_candidates.candidates) == len(first_candidates.groups) == 1
    first_group = first_candidates.groups[0]
    changed_candidates = [
        replace(
            candidate,
            summary="The mutable current view contains newer re-extracted content.",
        )
        for candidate in first_candidates.candidates
    ]
    changed_group = replace(
        first_group,
        summary="The mutable current view contains newer re-extracted content.",
    )
    changed_snapshot = analytics_store_service.upsert_signal_candidates(
        SignalCandidateStoreRequest(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=first_payload.input_reference,
            extraction_request_id=first_group.extraction_request_id,
            candidates=changed_candidates,
            groups=[changed_group],
        ),
        ctx,
    )
    assert (
        changed_snapshot.manifest_hashes[first_group.group_id]
        != first_payload.frozen_manifest_sha256
    )

    first_snapshot = analytics_store_service.read_signal_candidates(
        SignalCandidateReadRequest(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=first_payload.input_reference,
            manifest_sha256=first_payload.frozen_manifest_sha256,
        ),
        ctx,
    )
    assert first_snapshot.candidates == first_candidates.candidates
    assert first_snapshot.groups == [first_group]

    queued_jobs = []
    for submission in queued_submissions:
        queued_job, created = enqueue_workflow_job(app.state_db, submission, ctx)
        assert created is True
        queued_jobs.append(queued_job)
    assert queued_jobs[0].idempotency_key != queued_jobs[1].idempotency_key

    generated_packages = {}
    worker_id = "signal-snapshot-worker"
    for _ in queued_jobs:
        leased = claim_next_workflow_job(
            app.state_db, "signal_generation", worker_id, ctx
        )
        assert leased is not None
        running = start_workflow_job(app.state_db, leased.job_id, worker_id, ctx)
        queued_payload = load_workflow_job_payload(running)
        generation = execute_workflow_queue_handler(running, queued_payload, ctx)
        assert generation.result.output_verified is True
        completed = complete_workflow_job(
            app.state_db,
            running.job_id,
            worker_id,
            generation.result,
            generation.downstream,
            ctx,
            external_effects=generation.external_effects,
        )
        assert completed.status == "succeeded"
        package = queue_orchestrator._cross_report_package_from_artifact(
            generation.result.output_reference, ctx
        )
        generated_packages[package.selected_theme_id] = package

    expected_group_ids = {
        submission.payload.candidate_group_id for submission in queued_submissions
    }
    assert set(generated_packages) == expected_group_ids
    packages = list(generated_packages.values())
    assert len({package.title for package in packages}) == 1
    assert len({package.slug for package in packages}) == 2
    assert len({package.file_id for package in packages}) == 2
    assert len({package.canonical_artifact_path for package in packages}) == 2
    expected_publishers = {
        "report-signal-a": "Publisher A",
        "report-signal-b": "Publisher B",
        "report-signal-c": "Publisher A",
    }
    for package in packages:
        assert {
            item["report_id"]: item["publisher"] for item in package.source_metadata
        } == {
            report_id: expected_publishers[report_id]
            for report_id in package.selected_report_ids
        }

    materialize_workflow_outbox(app.state_db, worker_id, ctx)
    covered_packages = {}
    for _ in queued_submissions:
        leased = claim_next_workflow_job(
            app.state_db, "cover_generation", worker_id, ctx
        )
        assert leased is not None
        running = start_workflow_job(app.state_db, leased.job_id, worker_id, ctx)
        cover = execute_workflow_queue_handler(
            running, load_workflow_job_payload(running), ctx
        )
        assert cover.result.output_verified is True
        complete_workflow_job(
            app.state_db,
            running.job_id,
            worker_id,
            cover.result,
            cover.downstream,
            ctx,
            external_effects=cover.external_effects,
        )
        approved_package = queue_orchestrator._cross_report_package_from_artifact(
            cover.result.output_reference, ctx
        )
        covered_packages[approved_package.selected_theme_id] = approved_package

    assert set(covered_packages) == expected_group_ids
    cover_paths = {
        key: tuple(
            package.signal_card["covers"][size] for size in ("small", "medium", "large")
        )
        for key, package in covered_packages.items()
    }
    assert len(set(cover_paths.values())) == 2
    assert all(Path(path).is_file() for paths in cover_paths.values() for path in paths)

    write_requests = []

    def _mock_lookup(request, ctx):
        del ctx
        return WordPressPostLookupResponse(schema_version="1.0", found=False)

    def _mock_taxonomy_ensure(request, ctx):
        del ctx
        return WordPressTaxonomyEnsureResponse(
            schema_version="1.0",
            slug_to_id={
                term.slug: index for index, term in enumerate(request.terms, 1)
            },
        )

    def _mock_tag_ensure(request, ctx):
        del ctx
        return WordPressTagEnsureResponse(
            schema_version="1.0",
            slug_to_id={slug: index for index, slug in enumerate(request.tags, 1)},
        )

    def _mock_wordpress_write(request, settings, ctx):
        del settings, ctx
        write_requests.append(request)
        write_number = len(write_requests)
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=request.file_id,
            status="published",
            post_id=write_number,
            post_url=f"https://example.test/signals/{request.slug}",
            publication_outcome="published",
            transaction_outcomes=["published"],
            requested_write_count=1,
            actual_write_count=1,
        )

    publish_settings = publish_settings_factory()
    for package in covered_packages.values():
        published = publish_cross_report_package(
            package,
            publish_settings,
            ctx,
            publish_html_fn=_mock_wordpress_write,
            find_post_by_file_id_fn=_mock_lookup,
            ensure_taxonomy_terms_fn=_mock_taxonomy_ensure,
            ensure_tags_fn=_mock_tag_ensure,
        )
        assert published.status == "published"
        replay = publish_cross_report_package(
            package,
            publish_settings,
            ctx,
            publish_html_fn=_mock_wordpress_write,
            find_post_by_file_id_fn=_mock_lookup,
            ensure_taxonomy_terms_fn=_mock_taxonomy_ensure,
            ensure_tags_fn=_mock_tag_ensure,
        )
        assert replay.status == "published"
        assert replay.idempotency_reused is True

    assert len(write_requests) == 2
    assert len({request.file_id for request in write_requests}) == 2
    assert len({request.slug for request in write_requests}) == 2
