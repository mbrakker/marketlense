from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path

from src.contracts.config import ConfigLoadRequest
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportProjectedDataReadRequest,
    CrossReportPublishPackage,
)
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidate,
    SignalCandidateGroup,
    SignalCandidateSourceRef,
    SignalCandidateStoreRequest,
)
from src.contracts.workflow_queue import PublicationReadinessPayload
from src.services import analytics_store_service
from src.services.config_service import load_settings
from tests._workflow_queue_registry_support import _seed_projected_signal_source
from tests.test_autonomous_publication_approval import (
    _approval_rows,
    _config,
    _ctx,
    _outbox_count,
    _run_readiness,
    _with_package_checksum,
)


def _ready_signal(
    tmp_path: Path,
    config_path: Path,
    *,
    override_publishability: bool = False,
) -> PublicationReadinessPayload:
    original_path = tmp_path / "out" / "signal" / "source_package.json"
    package_path = tmp_path / "out" / "signal" / "approved_package.json"
    original_path.parent.mkdir(parents=True)
    ctx = _ctx()
    app_settings = load_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(config_path)), ctx
    )
    for report_id, publisher, publisher_id in (
        ("report-1", "Publisher A", "publisher-a"),
        ("report-2", "Publisher B", "publisher-b"),
    ):
        _seed_projected_signal_source(
            app_settings.reports_db,
            report_id=report_id,
            publisher=publisher,
            publisher_id=publisher_id,
        )
    projected_data = analytics_store_service.read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=app_settings.reports_db,
            source_report_ids=["report-1", "report-2"],
            evidence_ids=["report-1:claim:1", "report-2:claim:1"],
            content_classes=["claim", "finding", "quote", "metric"],
            minimum_projection_status="projected",
        ),
        ctx,
    )
    source_report_ids = [
        source.report_id for source in projected_data.source_candidates
    ]
    evidence_ids = [item.evidence_id for item in projected_data.evidence]
    candidate_id = "candidate-signal-1"
    group_id = "signal-group-1"
    extraction_request_id = "signal-extraction-1"
    candidate = SignalCandidate(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        candidate_id=candidate_id,
        candidate_type="market_signal",
        title="Checkout trust is changing",
        summary="Checkout trust signals are changing across the two reports.",
        confidence=0.82,
        strength=4.5,
        support_level="multi_report_convergent",
        caveats=["limited_fixture"],
        source_report_ids=source_report_ids,
        evidence_ids=evidence_ids,
        source_refs=[
            SignalCandidateSourceRef(
                schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
                report_id=item.report_id,
                evidence_id=item.evidence_id,
                source_table=item.source_table,
                entity_uid=item.entity_uid,
                content_class=item.content_class,
                page_refs=list(item.source_metadata.get("pages") or []),
                source_metadata=dict(item.source_metadata),
            )
            for item in projected_data.evidence
        ],
        raw_source_context={
            "evidence": [asdict(item) for item in projected_data.evidence]
        },
        validation_status="approved",
        validation_notes=["source_backed"],
        group_id=group_id,
        extraction_request_id=extraction_request_id,
        generated_at_utc="2026-07-18T00:00:00Z",
    )
    group = SignalCandidateGroup(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        group_id=group_id,
        stable_key="checkout-trust:signal",
        title=candidate.title,
        summary=candidate.summary,
        support_level="multi_report_convergent",
        candidate_ids=[candidate_id],
        source_report_ids=source_report_ids,
        evidence_ids=evidence_ids,
        caveats=["limited_fixture"],
        raw_group_context={
            "source_content_hashes": {
                source.report_id: source.content_hash
                for source in projected_data.source_candidates
            }
        },
        validation_status="approved",
        extraction_request_id=extraction_request_id,
        generated_at_utc="2026-07-18T00:00:00Z",
        topic="Checkout trust",
        topic_ids=["commerce"],
        source_category_ids={
            source.report_id: list(source.category_ids)
            for source in projected_data.source_candidates
        },
        publication_status="eligible",
        publication_hold_reason="",
    )
    stored = analytics_store_service.upsert_signal_candidates(
        SignalCandidateStoreRequest(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=app_settings.signal_store_db,
            extraction_request_id=extraction_request_id,
            candidates=[candidate],
            groups=[group],
        ),
        ctx,
    )
    manifest_sha256 = stored.manifest_hashes[group_id]
    validation_hash = hashlib.sha256(b"signal-validation\x1fapproved").hexdigest()
    original = _with_package_checksum(
        CrossReportPublishPackage(
            schema_version="1.0",
            package_id="signal-package-1",
            file_id="signal-file-1",
            target_route="wordpress:ml_signal",
            title="Signal title",
            slug="signal-title",
            excerpt="Evidence-backed signal.",
            body_html="<article>Evidence-backed signal.</article>",
            html_text="<html><body>Evidence-backed signal.</body></html>",
            html_path=str(original_path.with_name("publish.html")),
            canonical_artifact_path=str(original_path),
            artifact_sha256="",
            validation_sha256=validation_hash,
            selected_theme_id="signal-group-1",
            selected_report_ids=["report-1", "report-2"],
            source_metadata=[],
            category_labels=["Markets"],
            tag_labels=["Outlook"],
            evidence_reference_ids=evidence_ids,
            raw_metric_ids=[],
            prompt_hashes={"signal": "prompt-hash"},
            machine_metadata={
                "signal_validation_status": "approved",
                "configuration_hash": "signal-source-config",
                "policy_hash": "signal-source-policy",
                "candidate_group_id": group_id,
                "candidate_manifest_sha256": manifest_sha256,
                "candidate_ids": [candidate_id],
                "selected_report_ids": source_report_ids,
                "evidence_reference_ids": evidence_ids,
                "publishability": {
                    "publishable": True,
                    "diagnostic": False,
                    "override_applied": False,
                    "issues": [],
                    "selected_theme_id": group_id,
                    "selected_report_ids": source_report_ids,
                    "candidate_group_id": group_id,
                    "candidate_manifest_sha256": manifest_sha256,
                },
                "public_entity_metadata": {
                    "schema_version": "1.0",
                    "entity_type": "signal",
                    "source_artifact_id": "signal-file-1",
                    "canonical_route_intent": "wordpress:ml_signal",
                    "publish_eligible": True,
                },
            },
        )
    )
    original_path.write_text(
        json.dumps(asdict(original), sort_keys=True), encoding="utf-8"
    )
    final = _with_package_checksum(
        replace(
            original,
            canonical_artifact_path=str(package_path),
            signal_card={
                "schema_version": "1.0",
                "confidence": 0.82,
                "covers": {
                    "small": "small.webp",
                    "medium": "medium.webp",
                    "large": "large.webp",
                },
            },
        )
    )
    package_path.write_text(json.dumps(asdict(final), sort_keys=True), encoding="utf-8")
    return PublicationReadinessPayload(
        entity_type="signal",
        entity_package_reference=str(package_path),
        package_checksum=final.artifact_sha256,
        validation_reference=str(original_path),
        lineage_reference="retained:signal-source-evidence",
        required_asset_status="ready",
        attributes={
            "config_path": str(config_path),
            "override_publishability": override_publishability,
        },
    )


def test_autonomous_ready_signal_requires_approved_retained_evidence(
    tmp_path: Path,
) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_signal(tmp_path, config_path)

    result = _run_readiness(payload)

    approvals = _approval_rows(tmp_path / "state.sqlite")
    assert result.result.summary["readiness_status"] == "approved"
    assert len(approvals) == 1
    assert approvals[0][1] == payload.package_checksum
    assert _outbox_count(tmp_path / "state.sqlite") == 1


def test_signal_approval_does_not_trust_approved_status_without_manifest_replay(
    tmp_path: Path,
) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_signal(tmp_path, config_path)
    source_path = Path(payload.validation_reference)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["machine_metadata"].pop("candidate_group_id", None)
    source["machine_metadata"].pop("candidate_manifest_sha256", None)
    source["machine_metadata"].pop("candidate_ids", None)
    source["machine_metadata"].pop("publishability", None)
    source_package = _with_package_checksum(CrossReportPublishPackage(**source))
    source_path.write_text(
        json.dumps(asdict(source_package), sort_keys=True), encoding="utf-8"
    )

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_signal_manifest_source_change_stays_manual(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_signal(tmp_path, config_path)
    app_settings = load_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(config_path)), _ctx()
    )
    with sqlite3.connect(app_settings.reports_db) as connection:
        connection.execute(
            "UPDATE report_claims SET claim=? WHERE claim_uid=?",
            ("Changed after Signal approval.", "report-1:claim:1"),
        )
        connection.commit()

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_signal_final_package_manifest_mismatch_stays_manual(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_signal(tmp_path, config_path)
    package_path = Path(payload.entity_package_reference)
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["machine_metadata"]["candidate_manifest_sha256"] = "b" * 64
    package["machine_metadata"]["publishability"]["candidate_manifest_sha256"] = (
        "b" * 64
    )
    checked = _with_package_checksum(CrossReportPublishPackage(**package))
    package_path.write_text(
        json.dumps(asdict(checked), sort_keys=True), encoding="utf-8"
    )
    payload = replace(payload, package_checksum=checked.artifact_sha256)

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_signal_missing_override_provenance_remains_manual(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = replace(
        _ready_signal(tmp_path, config_path),
        attributes={"config_path": str(config_path)},
    )

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_signal_override_path_remains_manual(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_signal(tmp_path, config_path, override_publishability=True)

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


__all__ = [
    "test_autonomous_ready_signal_requires_approved_retained_evidence",
    "test_signal_approval_does_not_trust_approved_status_without_manifest_replay",
    "test_signal_manifest_source_change_stays_manual",
    "test_signal_final_package_manifest_mismatch_stays_manual",
    "test_signal_missing_override_provenance_remains_manual",
    "test_signal_override_path_remains_manual",
]
