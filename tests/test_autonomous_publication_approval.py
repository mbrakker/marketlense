from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.cross_report_analysis import (
    CrossReportPublishPackage,
    CrossReportValidationResult,
)
from src.contracts.publish_readiness import (
    PublishReadinessArtifact,
    PublishReadinessRuleResult,
)
from src.contracts.workflow_queue import (
    PublicationReadinessPayload,
    WordPressPublishPayload,
    WorkflowJobSubmission,
)
from src.generators.publish_readiness_generator import (
    _artifact_signature,
    publication_projection_hash,
    publish_readiness_payload,
)
from src.orchestrators import workflow_queue_orchestrator as queue_orchestrator
from src.orchestrators._publish_orchestrator.routing import (
    report_publish_package_checksum,
)
from src.orchestrators._workflow_queue_handlers.publishing import (
    _with_package_checksum,
)
from src.orchestrators.admission_preflight_orchestrator import (
    admission_configuration_hash,
    admission_policy_hash,
)
from src.services.config_service import (
    build_ingest_settings,
    load_settings,
    load_workflow_control_settings,
)
from src.services.workflow_queue_service import (
    approve_publication_package,
    record_publication_readiness,
)
from src.utils.errors import AppError
from tests.test_workflow_queue_registry import _ctx, _isolated_app_config, _workflow_job


def _config(
    tmp_path: Path, *, autonomous: bool, validation_policy: str = "block"
) -> Path:
    path = _isolated_app_config(tmp_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    publish = payload.get("publish")
    assert isinstance(publish, dict)
    validation = publish.setdefault("validation", {})
    assert isinstance(validation, dict)
    validation["policy"] = validation_policy
    control = payload.setdefault("workflow_control", {})
    assert isinstance(control, dict)
    if autonomous:
        control["autonomous_publication_policy"] = {
            "enabled": True,
            "policy_id": "autonomous_mvp_publication_v1",
        }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _ready_report(tmp_path: Path, config_path: Path) -> PublicationReadinessPayload:
    html_path = tmp_path / "out" / "report.html"
    readiness_path = tmp_path / "out" / "report" / "publish_readiness.json"
    html_path.parent.mkdir(parents=True)
    readiness_path.parent.mkdir(parents=True)
    html = "<html><body>Verified report</body></html>"
    html_path.write_text(html, encoding="utf-8")
    ctx = _ctx()
    app_settings = load_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(config_path)), ctx
    )
    ingest_settings = build_ingest_settings(
        IngestSettingsBuildRequest(schema_version="1.0", app_settings=app_settings),
        ctx,
    )
    now = datetime.now(UTC)
    artifact = PublishReadinessArtifact(
        report_id="report-1",
        status="pass",
        rule_results=[
            PublishReadinessRuleResult(
                rule_id="publish_readiness.semantic_grounding",
                status="pass",
                surfaces=["validation"],
            ),
            PublishReadinessRuleResult(
                rule_id="publish_readiness.retained_claim_grounding",
                status="pass",
                surfaces=["retained_claim_validation"],
                detail="unsupported_factual_count=0; unresolved_factual_count=0",
            ),
        ],
        final_html_hash=hashlib.sha256(html.encode("utf-8")).hexdigest(),
        publication_projection_hash=publication_projection_hash(html),
        configuration_hash=admission_configuration_hash(ingest_settings),
        policy_hash=admission_policy_hash(ingest_settings),
        producer_revision="workspace",
        created_at_utc=now.isoformat(),
        expires_at_utc=(now + timedelta(days=2)).isoformat(),
        staleness_conditions=["final_html_hash_changed", "expired"],
    )
    artifact = replace(artifact, artifact_hash=_artifact_signature(artifact))
    readiness_path.write_text(
        json.dumps(publish_readiness_payload(artifact), sort_keys=True),
        encoding="utf-8",
    )
    checksum = report_publish_package_checksum(
        html_path=str(html_path), readiness_reference=str(readiness_path), ctx=_ctx()
    )
    return PublicationReadinessPayload(
        entity_type="report",
        entity_package_reference=str(html_path),
        package_checksum=checksum,
        validation_reference=str(readiness_path),
        lineage_reference="retained:source-report-1",
        required_asset_status="ready",
        attributes={"config_path": str(config_path)},
    )


def _run_readiness(payload: PublicationReadinessPayload):
    job = replace(
        _workflow_job(
            queue_name="publication_readiness", job_type="publication_readiness.v1"
        ),
        entity_type=payload.entity_type,
        entity_id=payload.entity_package_reference,
    )
    return queue_orchestrator._publication_readiness_handler(
        job,
        payload,
        _ctx(),
    )


def _ready_briefing(
    tmp_path: Path,
    config_path: Path,
    *,
    validation_status: str = "pass",
    issues: list[str] | None = None,
    override_publishability: bool = False,
) -> PublicationReadinessPayload:
    package_path = tmp_path / "out" / "briefing" / "publish_package.json"
    package_path.parent.mkdir(parents=True)
    validation = CrossReportValidationResult(
        schema_version="1.0",
        status=validation_status,  # type: ignore[arg-type]
        checked_evidence_ids=["evidence-1"],
        issues=list(issues or []),
        passed=validation_status == "pass" and not issues,
    )
    validation_hash = hashlib.sha256(
        json.dumps(
            asdict(validation), ensure_ascii=True, sort_keys=True, default=str
        ).encode("utf-8")
    ).hexdigest()
    package = _with_package_checksum(
        CrossReportPublishPackage(
            schema_version="1.0",
            package_id="briefing-package-1",
            file_id="briefing-file-1",
            target_route="wordpress:ml_briefing",
            title="Briefing title",
            slug="briefing-title",
            excerpt="Verified synthesis.",
            body_html="<article>Verified synthesis.</article>",
            html_text="<html><body>Verified synthesis.</body></html>",
            html_path=str(package_path.with_name("publish.html")),
            canonical_artifact_path=str(package_path),
            artifact_sha256="",
            validation_sha256=validation_hash,
            selected_theme_id="theme-1",
            selected_report_ids=["report-1", "report-2"],
            source_metadata=[
                {"report_id": "report-1", "publisher": "Publisher A"},
                {"report_id": "report-2", "publisher": "Publisher B"},
            ],
            category_labels=["Markets"],
            tag_labels=["Outlook"],
            evidence_reference_ids=["evidence-1"],
            raw_metric_ids=[],
            prompt_hashes={"briefing": "prompt-hash"},
            machine_metadata={"validation_status": validation_status},
        )
    )
    artifact = {
        "config_fingerprint": "briefing-source-config",
        "policy_hash": "briefing-source-policy",
        "validation_result": asdict(validation),
        "publish_package": asdict(package),
    }
    package_path.write_text(json.dumps(artifact, sort_keys=True), encoding="utf-8")
    return PublicationReadinessPayload(
        entity_type="briefing",
        entity_package_reference=str(package_path),
        package_checksum=package.artifact_sha256,
        validation_reference=str(package_path),
        lineage_reference="retained:briefing-sources",
        required_asset_status="ready",
        attributes={
            "config_path": str(config_path),
            "override_publishability": override_publishability,
        },
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
            evidence_reference_ids=["evidence-1", "evidence-2"],
            raw_metric_ids=[],
            prompt_hashes={"signal": "prompt-hash"},
            machine_metadata={
                "signal_validation_status": "approved",
                "configuration_hash": "signal-source-config",
                "policy_hash": "signal-source-policy",
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


def _approval_rows(state_db: Path) -> list[tuple[str, str, str, str]]:
    with sqlite3.connect(state_db) as conn:
        return conn.execute(
            "SELECT approval_id,package_checksum,actor_id,note "
            "FROM workflow_publication_approvals WHERE action='approved'"
        ).fetchall()


def _resign_readiness(payload: PublicationReadinessPayload, **changes: object) -> None:
    path = Path(payload.validation_reference)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.update(changes)
    raw["artifact_hash"] = ""
    artifact = PublishReadinessArtifact(**raw)
    path.write_text(
        json.dumps(
            publish_readiness_payload(
                replace(artifact, artifact_hash=_artifact_signature(artifact))
            ),
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _outbox_count(state_db: Path) -> int:
    with sqlite3.connect(state_db) as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM workflow_outbox "
                "WHERE queue_name='wordpress_publish'"
            ).fetchone()[0]
        )


def test_autonomous_ready_report_records_one_checksum_bound_approval_and_outbox(
    tmp_path: Path,
) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_report(tmp_path, config_path)
    state_db = tmp_path / "state.sqlite"

    result = _run_readiness(payload)

    approvals = _approval_rows(state_db)
    assert result.result.summary["readiness_status"] == "approved"
    assert len(approvals) == 1
    approval_id, checksum, actor_id, note = approvals[0]
    assert checksum == payload.package_checksum
    assert actor_id.startswith("autonomous_mvp_publication_v1:")
    assert payload.package_checksum in note
    assert "policy_sha256=" in note
    assert "config_sha256=" in note
    assert len(approval_id) == 36
    assert _outbox_count(state_db) == 1
    with sqlite3.connect(state_db) as conn:
        submission_json = conn.execute(
            "SELECT submission_json FROM workflow_outbox "
            "WHERE queue_name='wordpress_publish'"
        ).fetchone()[0]
    submission = json.loads(submission_json)
    assert submission["payload"]["approval_id"] == approval_id
    assert submission["payload"]["package_checksum"] == payload.package_checksum


def test_manual_default_leaves_ready_report_awaiting_review(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=False)
    payload = _ready_report(tmp_path, config_path)

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_only_explicit_autonomous_overlay_enables_publication_auto_approval() -> None:
    control = load_workflow_control_settings(
        ConfigLoadRequest(
            schema_version="1.0", path="src/config/app.autonomous_mvp.yaml"
        ),
        _ctx(),
    )

    assert control.autonomous_publication_policy.enabled is True
    assert (
        control.autonomous_publication_policy.policy_id
        == "autonomous_mvp_publication_v1"
    )


def test_invalid_report_readiness_creates_no_automatic_approval(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_report(tmp_path, config_path)
    _resign_readiness(payload, status="fail")
    payload = replace(
        payload,
        package_checksum=report_publish_package_checksum(
            html_path=payload.entity_package_reference,
            readiness_reference=payload.validation_reference,
            ctx=_ctx(),
        ),
    )

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "not_publishable"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_warning_review_readiness_result_does_not_auto_approve(
    tmp_path: Path,
) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_report(tmp_path, config_path)
    rules = json.loads(Path(payload.validation_reference).read_text(encoding="utf-8"))[
        "rule_results"
    ]
    rules[0]["status"] = "warn"
    _resign_readiness(payload, rule_results=rules)
    payload = replace(
        payload,
        package_checksum=report_publish_package_checksum(
            html_path=payload.entity_package_reference,
            readiness_reference=payload.validation_reference,
            ctx=_ctx(),
        ),
    )

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_warn_publish_policy_remains_manual(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True, validation_policy="warn")
    payload = _ready_report(tmp_path, config_path)

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_expired_report_readiness_remains_manual(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_report(tmp_path, config_path)
    expired = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    _resign_readiness(payload, expires_at_utc=expired)
    payload = replace(
        payload,
        package_checksum=report_publish_package_checksum(
            html_path=payload.entity_package_reference,
            readiness_reference=payload.validation_reference,
            ctx=_ctx(),
        ),
    )

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_changed_source_configuration_identity_remains_manual(
    tmp_path: Path,
) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_report(tmp_path, config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["ingest"]["batch_limit"] = int(config["ingest"]["batch_limit"]) + 1
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_unresolved_claim_grounding_remains_manual(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_report(tmp_path, config_path)
    rules = json.loads(Path(payload.validation_reference).read_text(encoding="utf-8"))[
        "rule_results"
    ]
    rules[1]["detail"] = "unsupported_factual_count=0; unresolved_factual_count=1"
    _resign_readiness(payload, rule_results=rules)
    payload = replace(
        payload,
        package_checksum=report_publish_package_checksum(
            html_path=payload.entity_package_reference,
            readiness_reference=payload.validation_reference,
            ctx=_ctx(),
        ),
    )

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_publication_override_path_remains_manual(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = replace(
        _ready_report(tmp_path, config_path),
        attributes={"config_path": str(config_path), "publish_override": True},
    )

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_stale_package_checksum_creates_no_automatic_approval(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = replace(
        _ready_report(tmp_path, config_path), package_checksum="stale-package-checksum"
    )

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "not_publishable"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_changed_readiness_reference_remains_manual(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_report(tmp_path, config_path)
    alternate_validation_path = Path(payload.validation_reference).with_name(
        "alternate_readiness.json"
    )
    alternate_validation_path.write_bytes(
        Path(payload.validation_reference).read_bytes()
    )
    record_publication_readiness(
        str(tmp_path / "state.sqlite"),
        package_checksum=payload.package_checksum,
        entity_type=payload.entity_type,
        package_reference=payload.entity_package_reference,
        validation_reference=payload.validation_reference,
        lineage_reference=payload.lineage_reference,
        required_asset_status="ready",
        readiness_status="awaiting_review",
        reason="initial ready package",
        ctx=_ctx(),
    )
    payload = replace(payload, validation_reference=str(alternate_validation_path))

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_changed_report_package_is_not_automatically_approved(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_report(tmp_path, config_path)
    record_publication_readiness(
        str(tmp_path / "state.sqlite"),
        package_checksum=payload.package_checksum,
        entity_type=payload.entity_type,
        package_reference=payload.entity_package_reference,
        validation_reference=payload.validation_reference,
        lineage_reference=payload.lineage_reference,
        required_asset_status="ready",
        readiness_status="awaiting_review",
        reason="initial ready package",
        ctx=_ctx(),
    )
    Path(payload.entity_package_reference).write_text(
        "<html><body>Changed after readiness</body></html>", encoding="utf-8"
    )

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_duplicate_ready_report_replay_keeps_one_approval_and_outbox(
    tmp_path: Path,
) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_report(tmp_path, config_path)

    _run_readiness(payload)
    _run_readiness(payload)

    assert len(_approval_rows(tmp_path / "state.sqlite")) == 1
    assert _outbox_count(tmp_path / "state.sqlite") == 1


def test_autonomous_ready_briefing_uses_retained_validation_and_package_checksums(
    tmp_path: Path,
) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_briefing(tmp_path, config_path)

    result = _run_readiness(payload)

    approvals = _approval_rows(tmp_path / "state.sqlite")
    assert result.result.summary["readiness_status"] == "approved"
    assert len(approvals) == 1
    assert approvals[0][1] == payload.package_checksum
    assert _outbox_count(tmp_path / "state.sqlite") == 1


def test_briefing_missing_override_provenance_remains_manual(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = replace(
        _ready_briefing(tmp_path, config_path),
        attributes={"config_path": str(config_path)},
    )

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_briefing_override_path_remains_manual(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_briefing(tmp_path, config_path, override_publishability=True)

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


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


def test_briefing_warning_validation_remains_manual(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_briefing(
        tmp_path,
        config_path,
        validation_status="fail",
        issues=["warning: evidence review required"],
    )

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_changed_briefing_package_is_not_automatically_approved(tmp_path: Path) -> None:
    config_path = _config(tmp_path, autonomous=True)
    payload = _ready_briefing(tmp_path, config_path)
    artifact_path = Path(payload.entity_package_reference)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["publish_package"]["body_html"] = "<article>Changed</article>"
    artifact_path.write_text(json.dumps(artifact, sort_keys=True), encoding="utf-8")

    result = _run_readiness(payload)

    assert result.result.summary["readiness_status"] == "awaiting_review"
    assert _approval_rows(tmp_path / "state.sqlite") == []
    assert _outbox_count(tmp_path / "state.sqlite") == 0


def test_worker_rejects_briefing_mutation_after_checksum_bound_approval(
    tmp_path: Path,
) -> None:
    config_path = _config(tmp_path, autonomous=False)
    payload = _ready_briefing(tmp_path, config_path)
    _run_readiness(payload)
    publish_payload = WordPressPublishPayload(
        entity_type="briefing",
        entity_package_reference=payload.entity_package_reference,
        package_checksum=payload.package_checksum,
        attributes={"config_path": str(config_path)},
    )
    approval = approve_publication_package(
        str(tmp_path / "state.sqlite"),
        package_checksum=payload.package_checksum,
        actor_id="test-reviewer",
        note="Checksum guard test.",
        publish_submission=WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="wordpress_publish",
            job_type="wordpress_publish.v1",
            payload=publish_payload,
            idempotency_key=f"default:briefing:{payload.package_checksum}",
            deduplication_scope="wordpress-publish-package",
        ),
        ctx=_ctx(),
    )
    artifact_path = Path(payload.entity_package_reference)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["publish_package"]["body_html"] = (
        "<article>Changed after approval</article>"
    )
    artifact_path.write_text(json.dumps(artifact, sort_keys=True), encoding="utf-8")

    try:
        queue_orchestrator._wordpress_publish_handler(
            replace(
                _workflow_job(
                    queue_name="wordpress_publish", job_type="wordpress_publish.v1"
                ),
                entity_type="briefing",
            ),
            replace(publish_payload, approval_id=approval.approval_id),
            _ctx(),
        )
    except AppError as exc:
        assert "checksum does not match" in exc.message
    else:
        raise AssertionError("changed retained package passed its approval checksum")
