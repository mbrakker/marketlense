from __future__ import annotations

import json
from dataclasses import asdict, replace

import pytest

from src.contracts.remediation import (
    RemediationArtifactReference,
    RemediationCheckpointReference,
    RemediationClaimRequest,
    RemediationExpiredLeaseReleaseRequest,
    RemediationIdempotencyKey,
    RemediationListRequest,
    RemediationReaperRequest,
    RemediationRecord,
    RemediationSoakReportRequest,
    RemediationTransitionRequest,
    RemediationUpsertRequest,
)
from src.orchestrators.failure_recovery_registry import (
    canonical_failure_code,
    recovery_rule_for,
)
from src.orchestrators.remediation_orchestrator import (
    RemediationReaperDependencies,
    build_remediation_opportunity_report,
    record_workflow_failure,
    run_bounded_remediation_reaper,
)
from src.services.state_service import (
    claim_next_remediation,
    list_remediation_records,
    read_remediation_soak_report,
    release_expired_remediation_leases,
    transition_remediation,
    upsert_remediation_record,
)
from src.utils.errors import AppError
from src.utils.logging import new_run_context

NOW = "2026-07-15T12:00:00Z"


def _ctx():
    return new_run_context(task_id="test_remediation_ledger")


def _record(record_id: str, **changes: object) -> RemediationRecord:
    base = RemediationRecord(
        schema_version="1.0",
        remediation_id=record_id,
        dedupe_key=f"dedupe:{record_id}",
        workflow="report_generation",
        run_id="run-1",
        task_id="task-1",
        span_id="span-1",
        error_code="provider_timeout",
        error_classification="typed_app_error",
        action_code="retry_transient_service_call",
        created_at_utc=NOW,
        updated_at_utc=NOW,
        max_attempts=2,
    )
    return replace(base, **changes)


def _records(state_db: str) -> list[RemediationRecord]:
    return list_remediation_records(
        RemediationListRequest(schema_version="1.0", state_db=state_db), _ctx()
    ).records


def test_opportunity_report_is_deterministic_and_does_not_leak_source_ids() -> None:
    records = [
        _record(
            "older",
            source_id="private-source-id",
            created_at_utc="2026-07-14T12:00:00Z",
            attempt_count=2,
        ),
        _record(
            "newer",
            dedupe_key="dedupe:newer",
            source_id="private-source-id",
            created_at_utc=NOW,
            attempt_count=1,
        ),
        _record(
            "held",
            dedupe_key="dedupe:held",
            error_code="missing_runbook",
            action_code="mark_terminal_blocker",
        ),
    ]

    report = build_remediation_opportunity_report(
        records,
        observed_at_utc=NOW,
        runbook_error_codes={"provider_timeout"},
    )

    assert report.opportunity_count == 2
    assert report.opportunities[0].record_ids == ["older", "newer"]
    assert report.opportunities[0].priority_reasons[-1] == (
        "checkpoint_or_idempotency_proof_missing"
    )
    assert report.opportunities[0].executor_eligibility == "held_unregistered"
    payload = json.dumps(asdict(report), sort_keys=True)
    assert "private-source-id" not in payload
    assert report.opportunities[0].source_or_publisher_hashes


def test_duplicate_failure_upsert_reuses_current_record(tmp_path) -> None:
    state_db = str(tmp_path / "state.sqlite")
    first = upsert_remediation_record(
        RemediationUpsertRequest(
            schema_version="1.0", state_db=state_db, record=_record("rem-1")
        ),
        _ctx(),
    )
    duplicate = upsert_remediation_record(
        RemediationUpsertRequest(
            schema_version="1.0",
            state_db=state_db,
            record=replace(
                _record("different-id"),
                dedupe_key="dedupe:rem-1",
                error_code="provider_timeout",
            ),
        ),
        _ctx(),
    )

    assert first.created is True
    assert duplicate.created is False
    assert duplicate.deduplicated is True
    assert duplicate.record.remediation_id == "rem-1"
    assert len(_records(state_db)) == 1
    soak = read_remediation_soak_report(
        RemediationSoakReportRequest(
            schema_version="1.0",
            state_db=state_db,
            now_utc=NOW,
            runbook_error_codes=["provider_timeout"],
        ),
        _ctx(),
    )
    assert soak.created_record_ids == ["rem-1"]
    assert soak.deduplicated_record_ids == ["rem-1"]
    assert soak.missing_runbook_error_codes == []


def test_lease_contention_cooldown_and_expiry_recovery(tmp_path) -> None:
    state_db = str(tmp_path / "state.sqlite")
    upsert_remediation_record(
        RemediationUpsertRequest(
            schema_version="1.0",
            state_db=state_db,
            record=_record("cooldown", next_eligible_at_utc="2026-07-15T12:01:00Z"),
        ),
        _ctx(),
    )
    assert (
        claim_next_remediation(
            RemediationClaimRequest(
                schema_version="1.0", state_db=state_db, worker_id="one", now_utc=NOW
            ),
            _ctx(),
        ).record
        is None
    )

    upsert_remediation_record(
        RemediationUpsertRequest(
            schema_version="1.0",
            state_db=state_db,
            record=_record("cooldown", next_eligible_at_utc=NOW),
        ),
        _ctx(),
    )
    first = claim_next_remediation(
        RemediationClaimRequest(
            schema_version="1.0",
            state_db=state_db,
            worker_id="one",
            now_utc=NOW,
            lease_seconds=1,
        ),
        _ctx(),
    ).record
    second = claim_next_remediation(
        RemediationClaimRequest(
            schema_version="1.0", state_db=state_db, worker_id="two", now_utc=NOW
        ),
        _ctx(),
    ).record
    assert first is not None and first.lease_owner == "one"
    assert second is None

    released = release_expired_remediation_leases(
        RemediationExpiredLeaseReleaseRequest(
            schema_version="1.0", state_db=state_db, now_utc="2026-07-15T12:00:02Z"
        ),
        _ctx(),
    )
    assert released.released_ids == ["cooldown"]
    recovered = claim_next_remediation(
        RemediationClaimRequest(
            schema_version="1.0",
            state_db=state_db,
            worker_id="two",
            now_utc="2026-07-15T12:00:02Z",
        ),
        _ctx(),
    ).record
    assert recovered is not None and recovered.lease_owner == "two"


def test_read_only_soak_reports_stale_eligible_held_and_missing_runbooks(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "state.sqlite")
    for record in (
        _record("a-stale", error_code="browser_download_timeout"),
        _record("b-eligible", dedupe_key="dedupe:b-eligible", error_code="unmapped"),
        _record(
            "c-held",
            dedupe_key="dedupe:c-held",
            status="operator_action_required",
            action_code="mark_terminal_blocker",
        ),
        _record(
            "d-legacy-blocker",
            dedupe_key="dedupe:d-legacy-blocker",
            action_code="mark_terminal_blocker",
        ),
    ):
        upsert_remediation_record(
            RemediationUpsertRequest(
                schema_version="1.0", state_db=state_db, record=record
            ),
            _ctx(),
        )
    claimed = claim_next_remediation(
        RemediationClaimRequest(
            schema_version="1.0",
            state_db=state_db,
            worker_id="worker",
            now_utc=NOW,
            lease_seconds=1,
        ),
        _ctx(),
    ).record
    assert claimed is not None and claimed.remediation_id == "a-stale"

    soak = read_remediation_soak_report(
        RemediationSoakReportRequest(
            schema_version="1.0",
            state_db=state_db,
            now_utc="2026-07-15T12:00:02Z",
            runbook_error_codes=["browser_download_timeout"],
        ),
        _ctx(),
    )

    assert soak.stale_lease_ids == ["a-stale"]
    assert soak.eligible_record_ids == ["b-eligible"]
    assert soak.held_record_ids == ["c-held", "d-legacy-blocker"]
    assert soak.missing_runbook_error_codes == ["provider_timeout", "unmapped"]


def test_state_transitions_are_durable_and_invalid_transition_fails_closed(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "state.sqlite")
    upsert_remediation_record(
        RemediationUpsertRequest(
            schema_version="1.0", state_db=state_db, record=_record("states")
        ),
        _ctx(),
    )
    claimed = claim_next_remediation(
        RemediationClaimRequest(
            schema_version="1.0",
            state_db=state_db,
            worker_id="worker",
            now_utc=NOW,
        ),
        _ctx(),
    ).record
    assert claimed is not None
    retrying = transition_remediation(
        RemediationTransitionRequest(
            schema_version="1.0",
            state_db=state_db,
            remediation_id="states",
            status="retrying",
            reason="remediation_started",
            actor="worker",
            increment_attempt=True,
        ),
        _ctx(),
    ).record
    deferred = transition_remediation(
        RemediationTransitionRequest(
            schema_version="1.0",
            state_db=state_db,
            remediation_id="states",
            status="deferred",
            reason="service_cooldown",
            actor="worker",
            next_eligible_at_utc="2026-07-15T12:02:00Z",
        ),
        _ctx(),
    ).record
    assert retrying.status == "retrying"
    assert retrying.attempt_count == 1
    assert deferred.status == "deferred"

    with pytest.raises(AppError) as error:
        transition_remediation(
            RemediationTransitionRequest(
                schema_version="1.0",
                state_db=state_db,
                remediation_id="states",
                status="retrying",
                reason="invalid_restart",
                actor="worker",
            ),
            _ctx(),
        )
    assert error.value.code == "remediation_transition_invalid"


def test_reaper_enforces_attempt_budget_and_current_budget_gate(tmp_path) -> None:
    state_db = str(tmp_path / "state.sqlite")
    for record in (
        _record("exhausted", attempt_count=2),
        _record("budget", dedupe_key="dedupe:budget"),
    ):
        upsert_remediation_record(
            RemediationUpsertRequest(
                schema_version="1.0", state_db=state_db, record=record
            ),
            _ctx(),
        )
    response = run_bounded_remediation_reaper(
        RemediationReaperRequest(
            schema_version="1.0",
            state_db=state_db,
            worker_id="reaper",
            now_utc=NOW,
            limit=2,
            execution_enabled=True,
        ),
        _ctx(),
        dependencies=RemediationReaperDependencies(
            budget_check=lambda record, ctx: (
                "defer" if record.remediation_id == "budget" else "allow"
            )
        ),
    )
    states = {record.remediation_id: record.status for record in _records(state_db)}
    assert response.inspected_count == 2
    assert states == {"exhausted": "terminal", "budget": "deferred"}


def test_reaper_accepts_valid_checkpoint_and_rejects_missing_lineage(tmp_path) -> None:
    state_db = str(tmp_path / "state.sqlite")
    valid = _record(
        "valid",
        action_code="resume_valid_checkpoint",
        checkpoint=RemediationCheckpointReference(
            schema_version="1.0",
            path="checkpoint.json",
            stage_name="analysis_complete",
            checksum_sha256="abc",
            lineage_ref="lineage-1",
        ),
    )
    invalid = _record(
        "invalid",
        dedupe_key="dedupe:invalid",
        action_code="resume_valid_checkpoint",
        checkpoint=RemediationCheckpointReference(
            schema_version="1.0",
            path="checkpoint.json",
            stage_name="analysis_complete",
            checksum_sha256="abc",
            lineage_ref="",
        ),
    )
    for record in (valid, invalid):
        upsert_remediation_record(
            RemediationUpsertRequest(
                schema_version="1.0", state_db=state_db, record=record
            ),
            _ctx(),
        )
    response = run_bounded_remediation_reaper(
        RemediationReaperRequest(
            schema_version="1.0",
            state_db=state_db,
            worker_id="reaper",
            now_utc=NOW,
            limit=2,
            execution_enabled=True,
        ),
        _ctx(),
        dependencies=RemediationReaperDependencies(
            checkpoint_validator=lambda record, ctx: bool(
                record.checkpoint and record.checkpoint.lineage_ref
            ),
            resume_valid_checkpoint=lambda record, ctx: "succeeded",
        ),
    )
    states = {record.remediation_id: record.status for record in _records(state_db)}
    assert response.resolved_ids == ["valid"]
    assert states["valid"] == "resolved"
    assert states["invalid"] == "operator_action_required"


@pytest.mark.parametrize(
    ("record_id", "action"),
    [
        ("wordpress", "retry_idempotent_publication"),
        ("drive", "rerun_targeted_artifact_family"),
        ("email", "retry_transient_service_call"),
    ],
)
def test_reaper_does_not_repeat_side_effect_without_idempotency_proof(
    tmp_path, record_id: str, action: str
) -> None:
    state_db = str(tmp_path / f"{record_id}.sqlite")
    upsert_remediation_record(
        RemediationUpsertRequest(
            schema_version="1.0",
            state_db=state_db,
            record=_record(
                record_id, action_code=action, dedupe_key=f"dedupe:{record_id}"
            ),
        ),
        _ctx(),
    )
    calls: list[str] = []
    run_bounded_remediation_reaper(
        RemediationReaperRequest(
            schema_version="1.0",
            state_db=state_db,
            worker_id="reaper",
            now_utc=NOW,
            execution_enabled=True,
        ),
        _ctx(),
        dependencies=RemediationReaperDependencies(
            retry_idempotent_publication=lambda record, ctx: (
                calls.append("wordpress") or "succeeded"
            ),
            rerun_targeted_artifact_family=lambda record, ctx: (
                calls.append("drive") or "succeeded"
            ),
            retry_transient_service_call=lambda record, ctx: (
                calls.append("email") or "succeeded"
            ),
        ),
    )
    assert calls == []
    assert _records(state_db)[0].status == "operator_action_required"


def test_credential_error_escalates_without_automatic_retry(tmp_path) -> None:
    record = record_workflow_failure(
        state_db=str(tmp_path / "state.sqlite"),
        workflow="publishing",
        stage="publish_html",
        operation="publish_html",
        error=AppError(
            code="wordpress_credentials_missing", message="missing", retryable=False
        ),
        ctx=_ctx(),
    )
    assert record is not None
    assert record.action_code == "escalate_credentials"
    assert record.status == "operator_action_required"


def test_known_allowlisted_failure_is_pending_and_unknown_is_operator_held(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "state.sqlite")
    known = record_workflow_failure(
        state_db=state_db,
        workflow="report_download",
        stage="browser_download",
        operation="download_report",
        error=AppError(
            code="browser_download_timeout", message="timed out", retryable=True
        ),
        ctx=_ctx(),
    )
    unknown = record_workflow_failure(
        state_db=state_db,
        workflow="report_download",
        stage="browser_download",
        operation="download_report",
        error=RuntimeError("unexpected"),
        ctx=_ctx(),
        input_checksum="different-input",
    )

    assert known is not None
    assert known.status == "pending"
    assert known.action_code == "retry_transient_service_call"
    assert unknown is not None
    assert unknown.status == "operator_action_required"
    assert unknown.action_code == "mark_terminal_blocker"


def test_failure_specific_recovery_rule_persists_narrow_scope(tmp_path) -> None:
    record = record_workflow_failure(
        state_db=str(tmp_path / "state.sqlite"),
        workflow="report_generation",
        stage="taxonomy",
        operation="resolve_taxonomy",
        error=AppError(
            code="taxonomy_invalid_json", message="invalid", retryable=False
        ),
        ctx=_ctx(),
        checkpoint=RemediationCheckpointReference(
            schema_version="1.0",
            path="selection.checkpoint.json",
            stage_name="selection_complete",
            checksum_sha256="checkpoint-sha",
            lineage_ref="lineage-selection",
        ),
        reusable_artifacts=[
            RemediationArtifactReference(
                schema_version="1.0", name=name, reference=f"retained/{name}"
            )
            for name in ("source_pdf", "analysis_pdf", "vector_store")
        ],
    )

    assert record is not None
    assert record.status == "pending"
    assert record.action_code == "rerun_targeted_artifact_family"
    assert record.max_attempts == 1
    assert record.diagnostics["recovery_scope"] == "taxonomy"
    assert record.diagnostics["required_checkpoint"] == "selection_complete"
    assert record.diagnostics["avoided_provider_calls"] == [
        "pdf_parse",
        "ocr",
        "crop_render",
        "crop_qa",
    ]


def test_wordpress_readback_alias_is_auto_enqueued_only_with_preflight_proof(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "state.sqlite")
    record = record_workflow_failure(
        state_db=state_db,
        workflow="publishing",
        stage="authenticated_readback",
        operation="publish_html",
        error=AppError(
            code="wordpress_post_create_readback_missing",
            message="readback missing",
            retryable=False,
        ),
        ctx=_ctx(),
        workflow_run_id="publish-run",
        input_checksum="publish-checksum",
        report_id="report-1",
        checkpoint=RemediationCheckpointReference(
            schema_version="1.0",
            path="publication-preflight.json",
            stage_name="publication_preflight",
            checksum_sha256="checkpoint-sha",
            lineage_ref="rendered-lineage",
        ),
        reusable_artifacts=[
            RemediationArtifactReference(
                schema_version="1.0",
                name="rendered_html",
                reference="retained/report.html",
            ),
            RemediationArtifactReference(
                schema_version="1.0",
                name="publish_readiness",
                reference="publish-idempotency-key",
            ),
        ],
        idempotency_keys=[
            RemediationIdempotencyKey(
                schema_version="1.0",
                scope="wordpress_publish",
                key="publish-idempotency-key",
                input_checksum="publish-checksum",
            )
        ],
    )

    assert record is not None
    assert record.error_code == "wordpress_readback_failed"
    assert record.status == "pending"
    calls: list[str] = []
    response = run_bounded_remediation_reaper(
        RemediationReaperRequest(
            schema_version="1.0",
            state_db=state_db,
            worker_id="reaper",
            now_utc=record.next_eligible_at_utc,
            execution_enabled=True,
        ),
        _ctx(),
        dependencies=RemediationReaperDependencies(
            checkpoint_validator=lambda _record, _ctx: True,
            idempotency_check=lambda _record, _ctx: "safe_to_execute",
            retry_idempotent_publication=lambda _record, _ctx: (
                calls.append("readback") or "succeeded"
            ),
        ),
    )

    assert response.resolved_ids == [record.remediation_id]
    assert calls == ["readback"]
    persisted = _records(state_db)[0]
    assert persisted.status == "resolved"
    assert persisted.run_id == "publish-run"
    assert persisted.report_id == "report-1"


@pytest.mark.parametrize(
    ("workflow", "error_code", "scope", "checkpoint", "artifacts"),
    [
        (
            "report_generation",
            "taxonomy_invalid_json",
            "taxonomy",
            "selection_complete",
            ("source_pdf", "analysis_pdf", "vector_store"),
        ),
        (
            "report_generation",
            "category_fit_contradiction",
            "category_fit",
            "selection_complete",
            ("source_pdf", "analysis_pdf", "vector_store"),
        ),
        (
            "report_generation",
            "unsupported_material_claim",
            "affected_claim_or_insight",
            "analysis_complete",
            ("analysis_pdf", "artifacts", "validation"),
        ),
        (
            "report_generation",
            "final_html_internal_identifier",
            "rendering",
            "analysis_complete",
            ("analysis_pdf", "artifacts", "validation"),
        ),
        (
            "report_generation",
            "missing_report_card_manifest",
            "report_cards",
            "analysis_complete",
            ("analysis_pdf", "artifacts", "validation"),
        ),
        (
            "publishing",
            "wordpress_readback_failed",
            "wordpress_readback",
            "publication_preflight",
            ("rendered_html", "publish_readiness"),
        ),
    ],
)
def test_failure_registry_has_finite_safe_recovery_contract(
    workflow: str,
    error_code: str,
    scope: str,
    checkpoint: str,
    artifacts: tuple[str, ...],
) -> None:
    rule = recovery_rule_for(workflow, error_code)

    assert rule is not None
    assert rule.retryability is True
    assert rule.retry_scope == scope
    assert rule.max_attempts == 1
    assert rule.required_checkpoint == checkpoint
    assert rule.reusable_artifacts == artifacts
    assert rule.required_invalidations
    assert rule.terminal_fallback
    assert rule.avoided_stages
    assert rule.avoided_provider_calls


def test_failure_registry_normalizes_only_its_typed_codes() -> None:
    assert canonical_failure_code("TAXONOMY_INVALID_JSON") == "taxonomy_invalid_json"
    assert canonical_failure_code("ValueError") == "ValueError"


def test_typed_recovery_runs_once_with_verified_artifacts_and_finishes_terminally(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "state.sqlite")
    checkpoint = RemediationCheckpointReference(
        schema_version="1.0",
        path="selection.checkpoint.json",
        stage_name="selection_complete",
        checksum_sha256="checkpoint-sha",
        lineage_ref="lineage-selection",
    )
    record = record_workflow_failure(
        state_db=state_db,
        workflow="report_generation",
        stage="taxonomy",
        operation="resolve_taxonomy",
        error=AppError(
            code="taxonomy_invalid_json", message="invalid", retryable=False
        ),
        ctx=_ctx(),
        workflow_run_id="retained-run",
        report_id="report-1",
        checkpoint=checkpoint,
        reusable_artifacts=[
            RemediationArtifactReference(
                schema_version="1.0", name=name, reference=f"retained/{name}"
            )
            for name in ("source_pdf", "analysis_pdf", "vector_store")
        ],
    )
    calls: list[tuple[str, str, str]] = []

    response = run_bounded_remediation_reaper(
        RemediationReaperRequest(
            schema_version="1.0",
            state_db=state_db,
            worker_id="reaper",
            now_utc=record.next_eligible_at_utc if record is not None else NOW,
            execution_enabled=True,
        ),
        _ctx(),
        dependencies=RemediationReaperDependencies(
            checkpoint_validator=lambda candidate, _ctx: (
                candidate.checkpoint == checkpoint
            ),
            rerun_targeted_artifact_family=lambda candidate, _ctx: (
                calls.append(
                    (candidate.run_id, candidate.report_id, candidate.error_code)
                )
                or "succeeded"
            ),
        ),
    )

    assert record is not None
    assert response.resolved_ids == [record.remediation_id]
    assert calls == [("retained-run", "report-1", "taxonomy_invalid_json")]
    finished = _records(state_db)[0]
    assert finished.status == "resolved"
    assert finished.attempt_count == 1


def test_reaper_holds_unknown_workflow_error_even_when_an_executor_exists(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "state.sqlite")
    upsert_remediation_record(
        RemediationUpsertRequest(
            schema_version="1.0",
            state_db=state_db,
            record=_record(
                "unknown",
                workflow="candidate_extraction",
                error_code="drive_file_id_missing",
                action_code="retry_transient_service_call",
            ),
        ),
        _ctx(),
    )
    calls: list[str] = []
    response = run_bounded_remediation_reaper(
        RemediationReaperRequest(
            schema_version="1.0",
            state_db=state_db,
            worker_id="reaper",
            now_utc=NOW,
            execution_enabled=True,
        ),
        _ctx(),
        dependencies=RemediationReaperDependencies(
            retry_transient_service_call=lambda record, ctx: (
                calls.append(record.remediation_id) or "succeeded"
            ),
            idempotency_check=lambda record, ctx: "safe_to_execute",
        ),
    )

    assert calls == []
    assert response.held_ids == ["unknown"]
    assert _records(state_db)[0].status == "operator_action_required"


def test_reaper_converts_executor_exception_to_typed_terminal_fallback(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "state.sqlite")
    upsert_remediation_record(
        RemediationUpsertRequest(
            schema_version="1.0", state_db=state_db, record=_record("crashed")
        ),
        _ctx(),
    )

    def _crash(record: RemediationRecord, ctx) -> str:
        raise RuntimeError("worker terminated")

    response = run_bounded_remediation_reaper(
        RemediationReaperRequest(
            schema_version="1.0",
            state_db=state_db,
            worker_id="worker",
            now_utc=NOW,
            lease_seconds=1,
            execution_enabled=True,
        ),
        _ctx(),
        dependencies=RemediationReaperDependencies(
            retry_transient_service_call=_crash,
            idempotency_check=lambda record, ctx: "safe_to_execute",
        ),
    )
    assert response.held_ids == ["crashed"]
    assert _records(state_db)[0].status == "terminal"
