from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.files import WriteBytesRequest
from src.contracts.report_cards import CoverFingerprint
from src.contracts.signal_cards import SignalCardContent
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPublishProjection,
)
from src.contracts.workflow_queue import (
    BriefingOpportunityPayload,
    ClaimEmbeddingPayload,
    CoverGenerationPayload,
    PublicationReadinessPayload,
    SignalCandidatePayload,
    WordPressProjectionPayload,
    WordPressPublishPayload,
    WorkflowJobSubmission,
)
from src.orchestrators import workflow_queue_orchestrator as queue_orchestrator
from src.services.file_service import write_bytes
from src.services.workflow_queue_service import (
    approve_publication_package,
)
from src.utils.errors import AppError
from tests._workflow_queue_registry_support import (
    _ctx,
    _isolated_app_config,
    _seed_projected_signal_source,
    _workflow_job,
)


def test_signal_publish_adapter_retains_card_evidence_and_fallback_publishers(
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
    generation_payload = replace(
        generation_submission.payload,
        attributes={
            **generation_submission.payload.attributes,
            "max_source_reports": 1,
            "max_evidence_items": 1,
        },
    )
    for altered_payload in (
        replace(
            generation_payload,
            frozen_evidence_manifest="signal-candidates:changed-group",
        ),
        replace(generation_payload, input_content_hash="changed-manifest-hash"),
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
