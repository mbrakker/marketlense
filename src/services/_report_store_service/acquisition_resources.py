from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from math import ceil

from src.contracts.report_store import (
    AcquisitionAttemptResourceRecordRequest,
    AcquisitionAttemptResourceRecordResponse,
    AcquisitionResourceAggregate,
    AcquisitionResourceAggregateRequest,
    AcquisitionResourceAggregateResponse,
    AcquisitionRouteSuppressionRequest,
    AcquisitionRouteSuppressionResponse,
)
from src.contracts.run_context import RunContext
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import log_event

from .common import logger
from .connection import _metadata_conn

_TERMINAL_OUTCOMES = {"success", "failed", "suppressed"}
_MAX_ROUTE_POLICY_CLASSES = 12


def record_acquisition_attempt_resource(
    request: AcquisitionAttemptResourceRecordRequest,
    ctx: RunContext,
) -> AcquisitionAttemptResourceRecordResponse:
    """Persist one bounded resource envelope without duplicating ledger events."""
    if request.schema_version != "1.0" or request.summary.schema_version != "1.0":
        raise AppError(
            code="acquisition_resource_schema_version_invalid",
            message="Acquisition resource persistence requires supported schema versions",
            retryable=False,
        )
    db_path = str(request.db_path or "").strip()
    summary = request.summary
    _validate_summary(summary=summary, db_path=db_path)
    created = False
    superseded = 0
    try:
        with _metadata_conn(db_path, ctx) as conn:
            existing = conn.execute(
                """
                SELECT normalized_url, route_family, terminal_outcome
                FROM acquisition_attempt_resources WHERE attempt_id = ?
                """,
                (summary.attempt_id,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0] or "") != summary.normalized_url
                    or str(existing[1] or "") != summary.route_family
                    or str(existing[2] or "") != summary.terminal_outcome
                ):
                    raise AppError(
                        code="acquisition_resource_idempotency_conflict",
                        message="Acquisition attempt ID was reused with different content",
                        retryable=False,
                        context={"attempt_id": summary.attempt_id},
                    )
            else:
                conn.execute(
                    """
                    INSERT INTO acquisition_attempt_resources(
                        attempt_id, schema_version, publisher_id, source_identity_id,
                        source_identity_status, normalized_url, route_family,
                        route_policy_version, source_policy_compatibility_hash,
                        started_at_utc, completed_at_utc, elapsed_ms, browser_launches,
                        browser_steps, page_navigations, screenshots, browser_model_calls,
                        input_tokens, cached_input_tokens, output_tokens, drive_reads,
                        drive_writes, mailbox_reads, retry_count, terminal_outcome,
                        terminal_reason, verified_artifact_hash, estimated_cost_usd,
                        avoided_operations_json, incomplete_fields_json,
                        revalidation_override
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        summary.attempt_id,
                        summary.schema_version,
                        summary.publisher_id,
                        summary.source_identity_id,
                        summary.source_identity_status,
                        summary.normalized_url,
                        summary.route_family,
                        summary.route_policy_version,
                        summary.source_policy_compatibility_hash,
                        summary.started_at_utc,
                        summary.completed_at_utc,
                        int(summary.elapsed_ms),
                        int(summary.browser_launches),
                        int(summary.browser_steps),
                        int(summary.page_navigations),
                        int(summary.screenshots),
                        int(summary.browser_model_calls),
                        int(summary.input_tokens),
                        int(summary.cached_input_tokens),
                        int(summary.output_tokens),
                        int(summary.drive_reads),
                        int(summary.drive_writes),
                        int(summary.mailbox_reads),
                        int(summary.retry_count),
                        summary.terminal_outcome,
                        summary.terminal_reason,
                        summary.verified_artifact_hash,
                        round(float(summary.estimated_cost_usd), 6),
                        _bounded_json(summary.avoided_operations),
                        _bounded_json(summary.incomplete_fields),
                        1 if summary.revalidation_override else 0,
                    ),
                )
                created = True
            if summary.terminal_outcome == "success" and summary.revalidation_override:
                cursor = conn.execute(
                    """
                    UPDATE acquisition_route_suppressions
                    SET status = 'superseded', superseded_at_utc = ?,
                        revalidation_attempt_id = ?, updated_at = strftime('%s','now')
                    WHERE normalized_url = ? AND publisher_id = ? AND route_family = ?
                      AND status = 'active'
                    """,
                    (
                        summary.completed_at_utc,
                        summary.attempt_id,
                        summary.normalized_url,
                        summary.publisher_id,
                        summary.route_family,
                    ),
                )
                superseded = max(0, int(cursor.rowcount))
    except sqlite3.Error as exc:
        raise AppError(
            code="acquisition_resource_record_failed",
            message="Acquisition resource summary could not be persisted",
            cause=exc,
            retryable=True,
            context={"attempt_id": summary.attempt_id, "db_path": db_path},
        ) from exc
    response = AcquisitionAttemptResourceRecordResponse(
        schema_version="1.0",
        attempt_id=summary.attempt_id,
        created=created,
        superseded_suppression_count=superseded,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="acquisition_resource_summary_recorded",
            module=logger.name,
            fields={
                "attempt_id": response.attempt_id,
                "created": response.created,
                "publisher_id": summary.publisher_id,
                "route_family": summary.route_family,
                "terminal_outcome": summary.terminal_outcome,
                "terminal_reason": summary.terminal_reason,
                "elapsed_ms": summary.elapsed_ms,
                "browser_launches": summary.browser_launches,
                "browser_steps": summary.browser_steps,
                "browser_model_calls": summary.browser_model_calls,
                "input_tokens": summary.input_tokens,
                "output_tokens": summary.output_tokens,
                "estimated_cost_usd": summary.estimated_cost_usd,
                "incomplete_field_count": len(summary.incomplete_fields),
                "superseded_suppression_count": superseded,
            },
        )
    )
    return response


def evaluate_acquisition_route_suppression(
    request: AcquisitionRouteSuppressionRequest,
    ctx: RunContext,
) -> AcquisitionRouteSuppressionResponse:
    """Return an expiry-bound suppression decision from retained scalar history."""
    _validate_suppression_request(request)
    db_path = str(request.db_path or "").strip()
    now = _parse_now(request.now_utc)
    now_utc = now.isoformat()
    if not request.enabled:
        return _suppression_response(reason="suppression_disabled")
    if request.revalidation_override:
        return _suppression_response(reason="explicit_revalidation_override")
    try:
        with _metadata_conn(db_path, ctx) as conn:
            conn.execute(
                """
                UPDATE acquisition_route_suppressions
                SET status = 'expired', updated_at = strftime('%s','now')
                WHERE normalized_url = ? AND publisher_id = ? AND route_family = ?
                  AND source_policy_compatibility_hash = ? AND status = 'active'
                  AND expires_at_utc <= ?
                """,
                (
                    request.normalized_url,
                    request.publisher_id,
                    request.route_family,
                    request.source_policy_compatibility_hash,
                    now_utc,
                ),
            )
            active = conn.execute(
                """
                SELECT decision_id, reason, sample_size, terminal_failure_count,
                       terminal_failure_rate, expires_at_utc
                FROM acquisition_route_suppressions
                WHERE normalized_url = ? AND publisher_id = ? AND route_family = ?
                  AND source_policy_compatibility_hash = ? AND status = 'active'
                  AND expires_at_utc > ?
                ORDER BY created_at DESC, decision_id DESC LIMIT 1
                """,
                (
                    request.normalized_url,
                    request.publisher_id,
                    request.route_family,
                    request.source_policy_compatibility_hash,
                    now_utc,
                ),
            ).fetchone()
            if active is not None:
                return AcquisitionRouteSuppressionResponse(
                    schema_version="1.0",
                    suppressed=True,
                    decision_id=str(active[0]),
                    reason=str(active[1]),
                    sample_size=int(active[2] or 0),
                    terminal_failure_count=int(active[3] or 0),
                    terminal_failure_rate=float(active[4] or 0.0),
                    expires_at_utc=str(active[5]),
                )
            rows = conn.execute(
                """
                SELECT terminal_outcome, terminal_reason, completed_at_utc
                FROM acquisition_attempt_resources
                WHERE normalized_url = ? AND publisher_id = ? AND route_family = ?
                  AND source_policy_compatibility_hash = ?
                ORDER BY completed_at_utc DESC, attempt_id DESC
                LIMIT 200
                """,
                (
                    request.normalized_url,
                    request.publisher_id,
                    request.route_family,
                    request.source_policy_compatibility_hash,
                ),
            ).fetchall()
            sample_size = len(rows)
            classes = set(request.terminal_failure_classes)
            terminal_failures = sum(
                1
                for row in rows
                if str(row[0] or "") == "failed" and str(row[1] or "") in classes
            )
            failure_rate = terminal_failures / sample_size if sample_size else 0.0
            if (
                sample_size < request.minimum_sample_size
                or failure_rate < request.terminal_failure_threshold
            ):
                return _suppression_response(
                    reason=(
                        "insufficient_terminal_failure_evidence"
                        if sample_size < request.minimum_sample_size
                        else "terminal_failure_threshold_not_met"
                    ),
                    sample_size=sample_size,
                    terminal_failure_count=terminal_failures,
                    terminal_failure_rate=failure_rate,
                )
            expires_at = now + timedelta(seconds=request.ttl_seconds)
            decision_id = sha256_json(
                {
                    "normalized_url": request.normalized_url,
                    "publisher_id": request.publisher_id,
                    "route_family": request.route_family,
                    "policy_hash": request.source_policy_compatibility_hash,
                    "sample_size": sample_size,
                    "terminal_failure_count": terminal_failures,
                    "activated_at_utc": now_utc,
                }
            )
            reason = "eligible_terminal_failure_threshold"
            conn.execute(
                """
                INSERT INTO acquisition_route_suppressions(
                    decision_id, normalized_url, publisher_id, route_family,
                    policy_version, source_policy_compatibility_hash, reason,
                    sample_size, terminal_failure_count, terminal_failure_rate,
                    activated_at_utc, expires_at_utc, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    decision_id,
                    request.normalized_url,
                    request.publisher_id,
                    request.route_family,
                    request.policy_version,
                    request.source_policy_compatibility_hash,
                    reason,
                    sample_size,
                    terminal_failures,
                    round(failure_rate, 6),
                    now_utc,
                    expires_at.isoformat(),
                ),
            )
    except sqlite3.Error as exc:
        raise AppError(
            code="acquisition_route_suppression_evaluation_failed",
            message="Acquisition route suppression could not be evaluated",
            cause=exc,
            retryable=True,
            context={"db_path": db_path, "route_family": request.route_family},
        ) from exc
    response = AcquisitionRouteSuppressionResponse(
        schema_version="1.0",
        suppressed=True,
        decision_id=decision_id,
        reason=reason,
        sample_size=sample_size,
        terminal_failure_count=terminal_failures,
        terminal_failure_rate=round(failure_rate, 6),
        expires_at_utc=expires_at.isoformat(),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="acquisition_route_suppression_activated",
            module=logger.name,
            fields={
                "decision_id": response.decision_id,
                "publisher_id": request.publisher_id,
                "route_family": request.route_family,
                "sample_size": response.sample_size,
                "terminal_failure_count": response.terminal_failure_count,
                "terminal_failure_rate": response.terminal_failure_rate,
                "expires_at_utc": response.expires_at_utc,
            },
        )
    )
    return response


def list_acquisition_resource_aggregates(
    request: AcquisitionResourceAggregateRequest,
    ctx: RunContext,
) -> AcquisitionResourceAggregateResponse:
    """Build bounded publisher/route aggregates with explicit completeness counts."""
    if request.schema_version != "1.0" or not str(request.db_path or "").strip():
        raise AppError(
            code="acquisition_resource_aggregate_request_invalid",
            message="Acquisition aggregate requires a reports database path",
            retryable=False,
        )
    where: list[str] = []
    params: list[object] = []
    if request.publisher_id is not None:
        where.append("publisher_id = ?")
        params.append(str(request.publisher_id))
    if request.route_family is not None:
        where.append("route_family = ?")
        params.append(str(request.route_family))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    try:
        with _metadata_conn(str(request.db_path), ctx) as conn:
            rows = conn.execute(
                f"""
                SELECT publisher_id, route_family, elapsed_ms, browser_steps,
                       terminal_outcome, estimated_cost_usd, avoided_operations_json,
                       incomplete_fields_json, verified_artifact_hash
                FROM acquisition_attempt_resources
                {clause}
                ORDER BY publisher_id, route_family, completed_at_utc, attempt_id
                """,
                tuple(params),
            ).fetchall()
    except sqlite3.Error as exc:
        raise AppError(
            code="acquisition_resource_aggregate_read_failed",
            message="Acquisition resource aggregates could not be read",
            cause=exc,
            retryable=True,
            context={"db_path": str(request.db_path)},
        ) from exc
    groups: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in rows:
        groups.setdefault((str(row[0]), str(row[1])), []).append(row)
    aggregates: list[AcquisitionResourceAggregate] = []
    for (publisher_id, route_family), group in sorted(groups.items()):
        sample_size = len(group)
        successes = sum(
            1
            for row in group
            if str(row[4]) == "success" and str(row[8] or "").strip()
        )
        failures = sum(1 for row in group if str(row[4]) == "failed")
        elapsed = sorted(max(0, int(row[2] or 0)) for row in group)
        steps = sum(max(0, int(row[3] or 0)) for row in group)
        cost = round(sum(max(0.0, float(row[5] or 0.0)) for row in group), 6)
        incomplete = sum(1 for row in group if _json_list(row[7]))
        avoided = [operation for row in group for operation in _json_list(row[6])]
        aggregates.append(
            AcquisitionResourceAggregate(
                schema_version="1.0",
                publisher_id=publisher_id,
                route_family=route_family,
                sample_size=sample_size,
                incomplete_record_count=incomplete,
                verified_acquisition_count=successes,
                success_rate=round(successes / sample_size, 6) if sample_size else 0.0,
                estimated_cost_usd=cost,
                cost_per_verified_acquisition_usd=(
                    round(cost / successes, 6) if successes else None
                ),
                median_elapsed_ms=_nearest_rank(elapsed, 0.5),
                p95_elapsed_ms=_nearest_rank(elapsed, 0.95),
                browser_steps_per_verified_acquisition=(
                    round(steps / successes, 6) if successes else None
                ),
                terminal_failure_count=failures,
                avoided_browser_launches=sum(
                    1 for operation in avoided if operation == "browser_launch"
                ),
                avoided_browser_model_calls=sum(
                    1 for operation in avoided if operation == "browser_model_call"
                ),
            )
        )
    response = AcquisitionResourceAggregateResponse(
        schema_version="1.0", aggregates=aggregates
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="acquisition_resource_aggregates_read",
            module=logger.name,
            fields={
                "aggregate_count": len(response.aggregates),
                "sample_size": sum(item.sample_size for item in response.aggregates),
                "incomplete_record_count": sum(
                    item.incomplete_record_count for item in response.aggregates
                ),
            },
        )
    )
    return response


def _validate_summary(*, summary, db_path: str) -> None:
    required = {
        "db_path": db_path,
        "attempt_id": summary.attempt_id,
        "normalized_url": summary.normalized_url,
        "route_family": summary.route_family,
        "route_policy_version": summary.route_policy_version,
        "source_policy_compatibility_hash": summary.source_policy_compatibility_hash,
        "started_at_utc": summary.started_at_utc,
        "completed_at_utc": summary.completed_at_utc,
        "terminal_outcome": summary.terminal_outcome,
        "source_identity_status": summary.source_identity_status,
    }
    missing = sorted(name for name, value in required.items() if not str(value).strip())
    values = (
        summary.elapsed_ms,
        summary.browser_launches,
        summary.browser_steps,
        summary.page_navigations,
        summary.screenshots,
        summary.browser_model_calls,
        summary.input_tokens,
        summary.cached_input_tokens,
        summary.output_tokens,
        summary.drive_reads,
        summary.drive_writes,
        summary.mailbox_reads,
        summary.retry_count,
        summary.estimated_cost_usd,
    )
    if (
        missing
        or summary.terminal_outcome not in _TERMINAL_OUTCOMES
        or any(float(value) < 0 for value in values)
        or len(summary.avoided_operations) > 8
        or len(summary.incomplete_fields) > 12
    ):
        raise AppError(
            code="acquisition_resource_summary_invalid",
            message="Acquisition resource summary is incomplete or out of bounds",
            retryable=False,
            context={
                "missing_count": len(missing),
                "terminal_outcome": summary.terminal_outcome,
            },
        )


def _validate_suppression_request(request: AcquisitionRouteSuppressionRequest) -> None:
    classes = tuple(
        sorted(
            {
                str(item).strip()
                for item in request.terminal_failure_classes
                if str(item).strip()
            }
        )
    )
    if (
        request.schema_version != "1.0"
        or not str(request.db_path or "").strip()
        or not str(request.normalized_url or "").strip()
        or not str(request.route_family or "").strip()
        or not str(request.policy_version or "").strip()
        or not str(request.source_policy_compatibility_hash or "").strip()
        or int(request.minimum_sample_size) < 3
        or not 0.0 <= float(request.terminal_failure_threshold) <= 1.0
        or int(request.ttl_seconds) <= 0
        or not classes
        or len(classes) > _MAX_ROUTE_POLICY_CLASSES
    ):
        raise AppError(
            code="acquisition_route_suppression_request_invalid",
            message="Route suppression requires bounded typed policy inputs",
            retryable=False,
        )


def _parse_now(value: str) -> datetime:
    if not str(value or "").strip():
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppError(
            code="acquisition_route_suppression_now_invalid",
            message="Route suppression evaluation timestamp is invalid",
            cause=exc,
            retryable=False,
        ) from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _suppression_response(
    *,
    reason: str,
    sample_size: int = 0,
    terminal_failure_count: int = 0,
    terminal_failure_rate: float = 0.0,
) -> AcquisitionRouteSuppressionResponse:
    return AcquisitionRouteSuppressionResponse(
        schema_version="1.0",
        suppressed=False,
        reason=reason,
        sample_size=sample_size,
        terminal_failure_count=terminal_failure_count,
        terminal_failure_rate=round(terminal_failure_rate, 6),
    )


def _bounded_json(values: tuple[str, ...]) -> str:
    return json.dumps(
        sorted({str(value).strip() for value in values if str(value).strip()})[:12],
        separators=(",", ":"),
    )


def _json_list(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed[:12]] if isinstance(parsed, list) else []


def _nearest_rank(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    return values[max(0, ceil(len(values) * percentile) - 1)]
