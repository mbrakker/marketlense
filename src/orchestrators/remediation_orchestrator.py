from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from src.contracts.remediation import (
    RemediationActionCode,
    RemediationArtifactReference,
    RemediationBudgetSummary,
    RemediationCheckpointReference,
    RemediationClaimRequest,
    RemediationExpiredLeaseReleaseRequest,
    RemediationIdempotencyKey,
    RemediationOpportunity,
    RemediationOpportunityReport,
    RemediationReaperRequest,
    RemediationReaperResponse,
    RemediationRecord,
    RemediationStatus,
    RemediationTransitionRequest,
    RemediationUpsertRequest,
)
from src.contracts.retry_decision import RetryDecision
from src.contracts.run_context import RunContext
from src.orchestrators.failure_recovery_registry import (
    canonical_failure_code,
    recovery_rule_diagnostics,
    recovery_rule_for,
)
from src.services import state_service
from src.utils.clock import utc_now_seconds_z
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.remediation_orchestrator")

_SIDE_EFFECTING_ACTIONS = {
    "retry_transient_service_call",
    "retry_idempotent_publication",
    "revalidate_replaced_source",
}

# This is intentionally narrow.  Adding an action requires an explicit
# workflow/error pair and still does not enable execution without the reaper
# feature gate, an executor, and idempotency evidence where applicable.
_AUTO_REPAIR_ALLOWLIST: dict[tuple[str, str], set[RemediationActionCode]] = {
    ("report_generation", "provider_timeout"): {
        "resume_valid_checkpoint",
        "retry_transient_service_call",
    },
    ("report_download", "browser_download_timeout"): {
        "retry_transient_service_call",
    },
    ("mail_report_acquisition", "mail_report_not_arrived_yet"): {
        "poll_mailbox_delivery",
    },
    ("claim_embedding", "claim_embedding_provider_count_mismatch"): {
        "retry_transient_service_call",
    },
}


def _parse_utc(value: str, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _opaque_identity(record: RemediationRecord) -> str:
    value = record.source_id or record.publisher_id
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16] if value else ""


def _attempted_cost_usd(record: RemediationRecord) -> float:
    values = record.budget.consumed or {}
    for key in ("cost_usd", "estimated_cost_usd", "actual_cost_usd"):
        try:
            return max(0.0, float(values.get(key) or 0.0))
        except (TypeError, ValueError):
            continue
    return 0.0


def build_remediation_opportunity_report(
    records: list[RemediationRecord],
    *,
    observed_at_utc: str,
    runbook_error_codes: set[str] | None = None,
    max_record_ids_per_opportunity: int = 25,
) -> RemediationOpportunityReport:
    """Aggregate retained remediation rows without returning diagnostics or inputs."""

    runbooks = runbook_error_codes or set()
    now = _parse_utc(observed_at_utc, datetime.now(timezone.utc))
    grouped: dict[tuple[str, str, str, str, str, str], list[RemediationRecord]] = {}
    for record in records:
        retryability = (
            "retryable"
            if record.retry_decision and record.retry_decision.error_retryable
            else "non_retryable"
            if record.retry_decision
            else "unknown"
        )
        runbook_status = "mapped" if record.error_code in runbooks else "missing"
        grouped.setdefault(
            (
                record.workflow,
                record.failed_stage,
                record.error_code,
                record.action_code,
                retryability,
                runbook_status,
            ),
            [],
        ).append(record)

    opportunities: list[RemediationOpportunity] = []
    for key, members in sorted(grouped.items()):
        (
            workflow,
            failed_stage,
            error_code,
            action_code,
            retryability,
            runbook_status,
        ) = key
        ordered = sorted(
            members, key=lambda item: (item.created_at_utc, item.remediation_id)
        )
        oldest = _parse_utc(ordered[0].created_at_utc, now)
        oldest_age = max(0, int((now - oldest).total_seconds()))
        checkpoints = sum(
            bool(
                item.checkpoint
                and item.checkpoint.validation_status == "validated"
                and item.checkpoint.lineage_ref
            )
            for item in ordered
        )
        idempotency = sum(bool(item.idempotency_keys) for item in ordered)
        recurrence = len(ordered)
        reasons = [f"recurrence:{recurrence}", f"oldest_age_seconds:{oldest_age}"]
        score = recurrence * 100 + min(oldest_age // 3600, 72)
        if runbook_status == "mapped":
            score += 10
            reasons.append("runbook_mapped")
        else:
            reasons.append("runbook_missing")
        if checkpoints and idempotency:
            reasons.append("proof_present_but_no_registered_executor")
        else:
            reasons.append("checkpoint_or_idempotency_proof_missing")
        opportunities.append(
            RemediationOpportunity(
                schema_version="1.0",
                workflow=workflow,
                failed_stage=failed_stage,
                error_code=error_code,
                action_code=action_code,
                retryability=retryability,
                runbook_status=runbook_status,
                record_ids=[
                    item.remediation_id
                    for item in ordered[
                        : max(1, min(100, max_record_ids_per_opportunity))
                    ]
                ],
                source_or_publisher_hashes=sorted(
                    {
                        identity
                        for item in ordered
                        if (identity := _opaque_identity(item))
                    }
                )[:25],
                recurrence_count=recurrence,
                oldest_age_seconds=oldest_age,
                attempted_operations=sum(item.attempt_count for item in ordered),
                attempted_cost_usd=round(
                    sum(_attempted_cost_usd(item) for item in ordered), 6
                ),
                checkpoint_available_count=checkpoints,
                idempotency_proven_count=idempotency,
                priority_score=score,
                priority_reasons=reasons,
                executor_eligibility="held_unregistered",
                held_reason="no approved runtime executor registration",
            )
        )
    return RemediationOpportunityReport(
        schema_version="1.0",
        observed_at_utc=observed_at_utc,
        record_count=len(records),
        opportunity_count=len(opportunities),
        opportunities=sorted(
            opportunities,
            key=lambda item: (
                -item.priority_score,
                item.workflow,
                item.failed_stage,
                item.error_code,
            ),
        ),
    )


def _utc_after(now_utc: str, seconds: int) -> str:
    if seconds <= 0:
        return now_utc
    value = now_utc[:-1] + "+00:00" if now_utc.endswith("Z") else now_utc
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (
        (parsed.astimezone(timezone.utc) + timedelta(seconds=seconds))
        .isoformat()
        .replace("+00:00", "Z")
    )


def _failure_code(error: Exception) -> str:
    return error.code if isinstance(error, AppError) else error.__class__.__name__


def remediation_input_checksum(material: dict[str, Any]) -> str:
    """Return a stable checksum without retaining workflow input content."""

    encoded = json.dumps(
        material, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def remediation_budget_summary(budget: Any | None) -> RemediationBudgetSummary:
    """Project configured budget limits without reading or retaining raw inputs."""

    if budget is None:
        return RemediationBudgetSummary(schema_version="1.0")
    remaining: dict[str, float | int] = {}
    for field_name in (
        "max_spend_usd",
        "max_tokens",
        "max_calls",
        "max_steps",
        "max_runtime_seconds",
        "max_retries",
        "max_browser_launches",
        "max_drive_writes",
        "max_drive_reads",
        "max_wordpress_writes",
        "max_pdfs",
        "max_mailbox_reads",
    ):
        value = getattr(budget, field_name, None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            remaining[field_name] = value
    return RemediationBudgetSummary(schema_version="1.0", remaining=remaining)


def _failure_diagnostics(error: Exception) -> dict[str, object]:
    if not isinstance(error, AppError):
        return {"error_type": error.__class__.__name__}
    diagnostics: dict[str, object] = {
        "severity": error.severity,
        "retryable": error.retryable,
        "context_keys": sorted(str(key) for key in error.context),
    }
    if error.cause is not None:
        diagnostics["cause_type"] = error.cause.__class__.__name__
        if isinstance(error.cause, AppError):
            diagnostics["cause_code"] = error.cause.code
            diagnostics["cause_retryable"] = error.cause.retryable
    return diagnostics


def _allowlisted_actions(workflow: str, error_code: str) -> set[RemediationActionCode]:
    rule = recovery_rule_for(workflow, error_code)
    if rule is not None:
        return {rule.next_action}
    return _AUTO_REPAIR_ALLOWLIST.get(
        (workflow.strip().lower(), canonical_failure_code(error_code)), set()
    )


def is_automatically_repairable(record: RemediationRecord) -> bool:
    """Fail closed unless this exact workflow/error/action triple is approved."""

    rule = recovery_rule_for(record.workflow, record.error_code)
    if rule is not None:
        return rule.retryability and record.action_code == rule.next_action
    return record.action_code in _allowlisted_actions(
        record.workflow, record.error_code
    )


def _required_recovery_artifacts_present(
    record: RemediationRecord,
) -> bool:
    rule = recovery_rule_for(record.workflow, record.error_code)
    if rule is None:
        return True
    names = {item.name.strip() for item in record.reusable_artifacts if item.reference}
    return set(rule.reusable_artifacts).issubset(names)


def _recovery_checkpoint_matches_rule(record: RemediationRecord) -> bool:
    rule = recovery_rule_for(record.workflow, record.error_code)
    if rule is None:
        return True
    checkpoint = record.checkpoint
    return bool(
        checkpoint
        and checkpoint.stage_name == rule.required_checkpoint
        and checkpoint.validation_status == "validated"
        and checkpoint.checksum_sha256
        and checkpoint.lineage_ref
        and _required_recovery_artifacts_present(record)
    )


def _recovery_inputs_proven(
    rule,
    checkpoint: RemediationCheckpointReference | None,
    reusable_artifacts: list[RemediationArtifactReference],
) -> bool:
    names = {item.name.strip() for item in reusable_artifacts if item.reference}
    return bool(
        checkpoint
        and checkpoint.stage_name == rule.required_checkpoint
        and checkpoint.validation_status == "validated"
        and checkpoint.checksum_sha256
        and checkpoint.lineage_ref
        and set(rule.reusable_artifacts).issubset(names)
    )


def _terminal_reason(record: RemediationRecord, suffix: str) -> str:
    rule = recovery_rule_for(record.workflow, record.error_code)
    if rule is None:
        return suffix
    return f"terminal_fallback:{rule.terminal_fallback}:{suffix}"


def _action_for_failure(
    *,
    workflow: str,
    error: Exception,
    decision: RetryDecision | None,
    checkpoint: RemediationCheckpointReference | None,
) -> tuple[RemediationActionCode, RemediationStatus, str]:
    code = canonical_failure_code(_failure_code(error))
    if not isinstance(error, AppError):
        return (
            "mark_terminal_blocker",
            "operator_action_required",
            "Inspect the unexpected failure before retrying.",
        )
    if decision is not None and decision.action == "user_action_required":
        return "escalate_credentials", "operator_action_required", decision.next_action
    if any(
        token in code for token in ("credential", "api_key", "oauth", "token_missing")
    ):
        return (
            "escalate_credentials",
            "operator_action_required",
            "Provide or refresh credentials.",
        )
    if decision is not None and decision.action == "defer":
        return "defer_for_budget", "deferred", decision.next_action
    recovery_rule = recovery_rule_for(workflow, code)
    if recovery_rule is not None:
        if not recovery_rule.retryability:
            return (
                "mark_terminal_blocker",
                "terminal",
                f"Recovery policy marks {recovery_rule.retry_scope} non-retryable.",
            )
        return (
            recovery_rule.next_action,
            "pending",
            (
                f"Rerun only {recovery_rule.retry_scope} from "
                f"{recovery_rule.required_checkpoint}."
            ),
        )
    allowed_actions = _allowlisted_actions(workflow, code)
    if (
        code == "mail_report_not_arrived_yet"
        and "poll_mailbox_delivery" in allowed_actions
    ):
        return (
            "poll_mailbox_delivery",
            "pending",
            "Wait for and poll the requested mailbox delivery.",
        )
    if (
        "revalidate_replaced_source" in allowed_actions
        and "source" in code
        and any(token in code for token in ("stale", "replaced", "changed"))
    ):
        return (
            "revalidate_replaced_source",
            "pending",
            "Verify the replacement source before retrying.",
        )
    if (
        "rerun_targeted_artifact_family" in allowed_actions
        and "artifact" in code
        and any(token in code for token in ("invalid", "missing", "validation"))
    ):
        return (
            "rerun_targeted_artifact_family",
            "pending",
            "Rerun only the invalid artifact family.",
        )
    if (
        "retry_idempotent_publication" in allowed_actions
        and decision is not None
        and decision.action == "retry"
    ):
        return (
            "retry_idempotent_publication",
            "pending",
            "Retry publication only after idempotency verification.",
        )
    if (
        "resume_valid_checkpoint" in allowed_actions
        and checkpoint is not None
        and checkpoint.validation_status == "validated"
    ):
        return (
            "resume_valid_checkpoint",
            "pending",
            "Resume from the validated checkpoint.",
        )
    if (
        "retry_transient_service_call" in allowed_actions
        and error.retryable
        and (decision is None or decision.action == "retry")
    ):
        return (
            "retry_transient_service_call",
            "pending",
            decision.next_action
            if decision is not None
            else "retry_after_operator_review",
        )
    return (
        "mark_terminal_blocker",
        "operator_action_required",
        (
            "Operator review is required; the workflow/error combination is "
            "not allowlisted."
        ),
    )


def record_workflow_failure(
    *,
    state_db: str,
    workflow: str,
    stage: str,
    operation: str,
    error: Exception,
    ctx: RunContext,
    retry_decision: RetryDecision | None = None,
    workflow_run_id: str = "",
    input_checksum: str = "",
    report_id: str = "",
    source_id: str = "",
    publisher_id: str = "",
    checkpoint: RemediationCheckpointReference | None = None,
    reusable_artifacts: list[RemediationArtifactReference] | None = None,
    committed_side_effects: list[str] | None = None,
    idempotency_keys: list[RemediationIdempotencyKey] | None = None,
    budget: RemediationBudgetSummary | None = None,
    recovery_identity: dict[str, str] | None = None,
) -> RemediationRecord | None:
    """Persist terminal workflow failure evidence without changing retry policy."""

    if not state_db.strip():
        return None
    now = utc_now_seconds_z()
    action, status, operator_action = _action_for_failure(
        workflow=workflow,
        error=error,
        decision=retry_decision,
        checkpoint=checkpoint,
    )
    code = canonical_failure_code(_failure_code(error))
    recovery_rule = recovery_rule_for(workflow, code)
    fingerprint = {
        "workflow": workflow,
        "run_id": workflow_run_id or str(ctx.run_id),
        "stage": stage,
        "operation": operation,
        "input_checksum": input_checksum,
        "error_code": code,
        "report_id": report_id,
        "source_id": source_id,
        "publisher_id": publisher_id,
    }
    digest = remediation_input_checksum(fingerprint)
    delay = max(0, int(retry_decision.delay_seconds)) if retry_decision else 0
    retained_artifacts = list(reusable_artifacts or [])
    if recovery_rule is not None and not _recovery_inputs_proven(
        recovery_rule, checkpoint, retained_artifacts
    ):
        status = "operator_action_required"
        operator_action = (
            "Recovery proof is incomplete; retain the required checkpoint and "
            "artifacts before retrying the scoped action."
        )
    record = RemediationRecord(
        schema_version="1.0",
        remediation_id=f"rem_{digest[:32]}",
        dedupe_key=f"remediation:{digest}",
        workflow=workflow,
        run_id=workflow_run_id or str(ctx.run_id),
        task_id=str(ctx.task_id),
        span_id=ctx.span_id,
        report_id=report_id,
        source_id=source_id,
        publisher_id=publisher_id,
        input_checksum=input_checksum,
        failed_stage=stage,
        operation=operation,
        error_code=code,
        error_classification=(
            "typed_app_error" if isinstance(error, AppError) else "unknown"
        ),
        retry_decision=retry_decision,
        status=status,
        checkpoint=checkpoint,
        reusable_artifacts=retained_artifacts,
        committed_side_effects=list(committed_side_effects or []),
        idempotency_keys=list(idempotency_keys or []),
        budget=budget or RemediationBudgetSummary(schema_version="1.0"),
        max_attempts=(
            recovery_rule.max_attempts
            if recovery_rule is not None
            else (retry_decision.max_attempts if retry_decision else 1)
        ),
        cooldown_seconds=delay,
        next_eligible_at_utc=_utc_after(now, delay),
        action_code=action,
        operator_next_action=operator_action,
        created_at_utc=now,
        updated_at_utc=now,
        diagnostics={
            **_failure_diagnostics(error),
            **recovery_rule_diagnostics(recovery_rule),
            **{
                str(key): str(value)
                for key, value in (recovery_identity or {}).items()
                if str(value).strip()
            },
        },
    )
    response = state_service.upsert_remediation_record(
        RemediationUpsertRequest(
            schema_version="1.0", state_db=state_db, record=record
        ),
        child_context(ctx, task_id="remediation:record_failure"),
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="remediation_failure_recorded",
            module=logger.name,
            fields={
                "remediation_id": response.record.remediation_id,
                "workflow": response.record.workflow,
                "step": response.record.failed_stage,
                "error_code": response.record.error_code,
                "state_transition": response.record.status,
                "lease_owner": response.record.lease_owner,
                "lease_expires_at_utc": response.record.lease_expires_at_utc,
                "cooldown_seconds": response.record.cooldown_seconds,
                "attempt_count": response.record.attempt_count,
                "max_attempts": response.record.max_attempts,
                "checkpoint_status": (
                    response.record.checkpoint.validation_status
                    if response.record.checkpoint
                    else "absent"
                ),
                "idempotency_status": (
                    "recorded" if response.record.idempotency_keys else "absent"
                ),
                "operator_action": response.record.operator_next_action,
                "avoided_stage_count": len(
                    response.record.diagnostics.get("avoided_stages", [])
                ),
                "avoided_provider_call_count": len(
                    response.record.diagnostics.get("avoided_provider_calls", [])
                ),
                "avoided_token_estimate": response.record.diagnostics.get(
                    "avoided_token_estimate"
                ),
                "avoided_cost_estimate_usd": response.record.diagnostics.get(
                    "avoided_cost_estimate_usd"
                ),
                "created": response.created,
                "deduplicated": response.deduplicated,
            },
        )
    )
    return response.record


RemediationExecutor = Callable[[RemediationRecord, RunContext], str]
RemediationBudgetCheck = Callable[[RemediationRecord, RunContext], str]
RemediationCheckpointValidator = Callable[[RemediationRecord, RunContext], bool]
RemediationIdempotencyCheck = Callable[[RemediationRecord, RunContext], str]


@dataclass(frozen=True)
class RemediationReaperDependencies:
    """Explicit closed-action hooks; absent hooks fail closed to an operator."""

    resume_valid_checkpoint: RemediationExecutor | None = None
    retry_transient_service_call: RemediationExecutor | None = None
    rerun_targeted_artifact_family: RemediationExecutor | None = None
    revalidate_replaced_source: RemediationExecutor | None = None
    poll_mailbox_delivery: RemediationExecutor | None = None
    retry_idempotent_publication: RemediationExecutor | None = None
    budget_check: RemediationBudgetCheck | None = None
    checkpoint_validator: RemediationCheckpointValidator | None = None
    idempotency_check: RemediationIdempotencyCheck | None = None


def _executor_for(
    dependencies: RemediationReaperDependencies,
    action: RemediationActionCode,
) -> RemediationExecutor | None:
    if action == "resume_valid_checkpoint":
        return dependencies.resume_valid_checkpoint
    if action == "retry_transient_service_call":
        return dependencies.retry_transient_service_call
    if action == "rerun_targeted_artifact_family":
        return dependencies.rerun_targeted_artifact_family
    if action == "revalidate_replaced_source":
        return dependencies.revalidate_replaced_source
    if action == "poll_mailbox_delivery":
        return dependencies.poll_mailbox_delivery
    if action == "retry_idempotent_publication":
        return dependencies.retry_idempotent_publication
    return None


def _transition(
    *,
    state_db: str,
    record: RemediationRecord,
    status: RemediationStatus,
    reason: str,
    actor: str,
    ctx: RunContext,
    next_eligible_at_utc: str = "",
    increment_attempt: bool = False,
) -> RemediationRecord:
    return state_service.transition_remediation(
        RemediationTransitionRequest(
            schema_version="1.0",
            state_db=state_db,
            remediation_id=record.remediation_id,
            status=status,
            reason=reason,
            actor=actor,
            next_eligible_at_utc=next_eligible_at_utc,
            increment_attempt=increment_attempt,
        ),
        ctx,
    ).record


def _log_reaper_event(
    ctx: RunContext, event: str, record: RemediationRecord, reason: str
) -> None:
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event=event,
            module=logger.name,
            fields={
                "remediation_id": record.remediation_id,
                "workflow": record.workflow,
                "action_code": record.action_code,
                "status": record.status,
                "step": record.failed_stage,
                "error_code": record.error_code,
                "transition_reason": reason,
                "attempt_count": record.attempt_count,
                "max_attempts": record.max_attempts,
                "lease_owner": record.lease_owner,
                "lease_expires_at_utc": record.lease_expires_at_utc,
                "cooldown_seconds": record.cooldown_seconds,
                "checkpoint_status": (
                    record.checkpoint.validation_status
                    if record.checkpoint
                    else "absent"
                ),
                "idempotency_status": (
                    "recorded" if record.idempotency_keys else "absent"
                ),
                "operator_action": record.operator_next_action,
            },
        )
    )


def run_bounded_remediation_reaper(
    request: RemediationReaperRequest,
    ctx: RunContext,
    *,
    dependencies: RemediationReaperDependencies | None = None,
) -> RemediationReaperResponse:
    """Run at most ``limit`` closed, policy-approved remediation actions once."""

    if not request.execution_enabled:
        return RemediationReaperResponse(schema_version="1.0", inspected_count=0)
    deps = dependencies or RemediationReaperDependencies()
    released = state_service.release_expired_remediation_leases(
        RemediationExpiredLeaseReleaseRequest(
            schema_version="1.0", state_db=request.state_db, now_utc=request.now_utc
        ),
        child_context(ctx, task_id="remediation:release_expired_leases"),
    ).released_ids
    resolved: list[str] = []
    deferred: list[str] = []
    held: list[str] = []
    inspected = 0
    for _ in range(max(1, min(100, request.limit))):
        claim = state_service.claim_next_remediation(
            RemediationClaimRequest(
                schema_version="1.0",
                state_db=request.state_db,
                worker_id=request.worker_id,
                now_utc=request.now_utc,
                lease_seconds=request.lease_seconds,
            ),
            child_context(ctx, task_id="remediation:claim"),
        )
        record = claim.record
        if record is None:
            break
        inspected += 1
        work_ctx = child_context(ctx, task_id=f"remediation:{record.remediation_id}")
        if record.attempt_count >= record.max_attempts:
            record = _transition(
                state_db=request.state_db,
                record=record,
                status="terminal",
                reason="attempt_budget_exhausted",
                actor=request.worker_id,
                ctx=work_ctx,
            )
            _log_reaper_event(
                work_ctx, "remediation_exhausted", record, "attempt_budget_exhausted"
            )
            held.append(record.remediation_id)
            continue
        budget_decision = (
            deps.budget_check(record, work_ctx)
            if deps.budget_check is not None
            else record.budget.decision
        )
        if budget_decision in {"defer", "pause", "stop"}:
            record = _transition(
                state_db=request.state_db,
                record=record,
                status="deferred",
                reason="budget_prevented_retry",
                actor=request.worker_id,
                ctx=work_ctx,
                next_eligible_at_utc=_utc_after(
                    request.now_utc, max(1, record.cooldown_seconds)
                ),
            )
            _log_reaper_event(
                work_ctx,
                "remediation_budget_prevented_retry",
                record,
                "budget_prevented_retry",
            )
            deferred.append(record.remediation_id)
            continue
        if not is_automatically_repairable(record):
            record = _transition(
                state_db=request.state_db,
                record=record,
                status="operator_action_required",
                reason="workflow_error_not_allowlisted",
                actor=request.worker_id,
                ctx=work_ctx,
            )
            _log_reaper_event(
                work_ctx,
                "remediation_operator_action_required",
                record,
                "workflow_error_not_allowlisted",
            )
            held.append(record.remediation_id)
            continue
        recovery_rule = recovery_rule_for(record.workflow, record.error_code)
        if recovery_rule is not None:
            valid = bool(
                _recovery_checkpoint_matches_rule(record)
                and deps.checkpoint_validator
                and deps.checkpoint_validator(record, work_ctx)
            )
            if not valid:
                record = _transition(
                    state_db=request.state_db,
                    record=record,
                    status="terminal",
                    reason=_terminal_reason(record, "checkpoint_or_artifact_rejected"),
                    actor=request.worker_id,
                    ctx=work_ctx,
                )
                _log_reaper_event(
                    work_ctx,
                    "remediation_terminal_blocker",
                    record,
                    "checkpoint_or_artifact_rejected",
                )
                held.append(record.remediation_id)
                continue
        elif record.action_code == "resume_valid_checkpoint":
            valid = bool(
                deps.checkpoint_validator
                and deps.checkpoint_validator(record, work_ctx)
            )
            if not valid:
                record = _transition(
                    state_db=request.state_db,
                    record=record,
                    status="operator_action_required",
                    reason="checkpoint_rejected",
                    actor=request.worker_id,
                    ctx=work_ctx,
                )
                _log_reaper_event(
                    work_ctx,
                    "remediation_checkpoint_rejected",
                    record,
                    "checkpoint_rejected",
                )
                held.append(record.remediation_id)
                continue
        if record.action_code in _SIDE_EFFECTING_ACTIONS:
            proof = (
                deps.idempotency_check(record, work_ctx)
                if deps.idempotency_check
                else "unknown"
            )
            if proof == "already_completed":
                record = _transition(
                    state_db=request.state_db,
                    record=record,
                    status="resolved",
                    reason="idempotency_proved_completed",
                    actor=request.worker_id,
                    ctx=work_ctx,
                )
                _log_reaper_event(
                    work_ctx,
                    "remediation_succeeded",
                    record,
                    "idempotency_proved_completed",
                )
                resolved.append(record.remediation_id)
                continue
            if proof != "safe_to_execute":
                record = _transition(
                    state_db=request.state_db,
                    record=record,
                    status="operator_action_required",
                    reason="idempotency_proof_missing",
                    actor=request.worker_id,
                    ctx=work_ctx,
                )
                _log_reaper_event(
                    work_ctx,
                    "remediation_operator_action_required",
                    record,
                    "idempotency_proof_missing",
                )
                held.append(record.remediation_id)
                continue
        executor = _executor_for(deps, record.action_code)
        if executor is None:
            terminal_status: RemediationStatus = (
                "terminal"
                if record.action_code == "mark_terminal_blocker"
                else "operator_action_required"
            )
            record = _transition(
                state_db=request.state_db,
                record=record,
                status=terminal_status,
                reason="action_not_enabled",
                actor=request.worker_id,
                ctx=work_ctx,
            )
            _log_reaper_event(
                work_ctx,
                "remediation_terminal_blocker"
                if terminal_status == "terminal"
                else "remediation_operator_action_required",
                record,
                "action_not_enabled",
            )
            held.append(record.remediation_id)
            continue
        record = _transition(
            state_db=request.state_db,
            record=record,
            status="retrying",
            reason="remediation_started",
            actor=request.worker_id,
            ctx=work_ctx,
            increment_attempt=True,
        )
        _log_reaper_event(
            work_ctx, "remediation_started", record, "remediation_started"
        )
        try:
            outcome = executor(record, work_ctx)
        except Exception as exc:
            record = _transition(
                state_db=request.state_db,
                record=record,
                status="terminal",
                reason=_terminal_reason(record, "executor_exception"),
                actor=request.worker_id,
                ctx=work_ctx,
            )
            _log_reaper_event(
                work_ctx,
                "remediation_terminal_blocker",
                record,
                f"executor_exception:{exc.__class__.__name__}",
            )
            held.append(record.remediation_id)
            continue
        if outcome == "succeeded":
            record = _transition(
                state_db=request.state_db,
                record=record,
                status="resolved",
                reason="remediation_succeeded",
                actor=request.worker_id,
                ctx=work_ctx,
            )
            _log_reaper_event(
                work_ctx, "remediation_succeeded", record, "remediation_succeeded"
            )
            resolved.append(record.remediation_id)
        elif outcome == "deferred":
            record = _transition(
                state_db=request.state_db,
                record=record,
                status="deferred",
                reason="executor_deferred",
                actor=request.worker_id,
                ctx=work_ctx,
                next_eligible_at_utc=_utc_after(
                    request.now_utc, max(1, record.cooldown_seconds)
                ),
            )
            _log_reaper_event(
                work_ctx, "remediation_deferred", record, "executor_deferred"
            )
            deferred.append(record.remediation_id)
        else:
            status: RemediationStatus = (
                "terminal"
                if recovery_rule is not None or outcome == "terminal"
                else "operator_action_required"
            )
            record = _transition(
                state_db=request.state_db,
                record=record,
                status=status,
                reason=(
                    _terminal_reason(record, f"executor_{outcome or 'held'}")
                    if status == "terminal"
                    else f"executor_{outcome or 'held'}"
                ),
                actor=request.worker_id,
                ctx=work_ctx,
            )
            _log_reaper_event(
                work_ctx,
                "remediation_terminal_blocker"
                if status == "terminal"
                else "remediation_operator_action_required",
                record,
                f"executor_{outcome or 'held'}",
            )
            held.append(record.remediation_id)
    return RemediationReaperResponse(
        schema_version="1.0",
        inspected_count=inspected,
        resolved_ids=resolved,
        deferred_ids=deferred,
        held_ids=held,
        released_lease_ids=released,
    )


__all__ = [
    "RemediationReaperDependencies",
    "is_automatically_repairable",
    "remediation_budget_summary",
    "remediation_input_checksum",
    "record_workflow_failure",
    "build_remediation_opportunity_report",
    "run_bounded_remediation_reaper",
]
