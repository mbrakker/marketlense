from __future__ import annotations

import json
import sqlite3
from typing import Optional
from urllib.parse import urlsplit

from src.contracts.report_store import PublisherDownloadRouteRecordRequest
from src.contracts.run_context import RunContext
from src.utils.coercion import clean_string_list
from src.utils.errors import AppError
from src.utils.logging import log_event

from ..common import logger, _normalize_optional_url_key
from ..connection import _metadata_conn
from ..route_policy import (
    _confidence_score_for_history,
    _is_verified_success,
    _route_projection_rank,
    _route_reusability_bonus,
)
from ..serialization import (
    _bool_from_db,
    _serialize_confirmation_evidence,
    _serialize_route_steps,
    _serialize_terminal_evidence,
)

def record_publisher_download_route(
    request: PublisherDownloadRouteRecordRequest,
    ctx: RunContext,
) -> None:
    db_path = request.db_path.strip()
    normalized_url = request.normalized_url.strip()
    source_url = request.source_url.strip()
    route_kind = request.route_kind.strip()
    route_summary = request.route_summary.strip()
    outcome = request.outcome.strip()
    route_family = request.route_family.strip()
    route_status = request.route_status.strip()
    resolved_target_url = request.resolved_target_url.strip()
    browser_had_structured_result = bool(request.browser_had_structured_result)
    last_downloaded_file_path = (
        request.last_downloaded_file_path.strip()
        if request.last_downloaded_file_path
        and request.last_downloaded_file_path.strip()
        else None
    )
    last_final_page_url = (
        request.last_final_page_url.strip()
        if request.last_final_page_url and request.last_final_page_url.strip()
        else None
    )
    blocked_reason = (
        request.blocked_reason.strip()
        if request.blocked_reason and request.blocked_reason.strip()
        else None
    )
    blocked_reason_detail = (
        request.blocked_reason_detail.strip()
        if request.blocked_reason_detail and request.blocked_reason_detail.strip()
        else None
    )
    onsite_capture_path = (
        request.onsite_capture_path.strip()
        if request.onsite_capture_path and request.onsite_capture_path.strip()
        else None
    )
    onsite_capture_format = (
        request.onsite_capture_format.strip()
        if request.onsite_capture_format and request.onsite_capture_format.strip()
        else None
    )
    onsite_page_count = request.onsite_page_count
    onsite_completeness_status = (
        request.onsite_completeness_status.strip()
        if request.onsite_completeness_status
        and request.onsite_completeness_status.strip()
        else None
    )
    if not db_path:
        raise AppError(
            code="publisher_route_db_missing",
            message="Report metadata DB path is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    if not normalized_url:
        raise AppError(
            code="publisher_route_normalized_url_missing",
            message="normalized_url is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    if not source_url:
        raise AppError(
            code="publisher_route_source_url_missing",
            message="source_url is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    if not route_kind:
        raise AppError(
            code="publisher_route_kind_missing",
            message="route_kind is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    if not route_summary:
        raise AppError(
            code="publisher_route_summary_missing",
            message="route_summary is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    if not outcome:
        raise AppError(
            code="publisher_route_outcome_missing",
            message="outcome is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    if not route_family:
        raise AppError(
            code="publisher_route_family_missing",
            message="route_family is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    if not route_status:
        raise AppError(
            code="publisher_route_status_missing",
            message="route_status is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    if not resolved_target_url:
        raise AppError(
            code="publisher_route_resolved_target_url_missing",
            message="resolved_target_url is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_route_record_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "source_url": source_url,
                "route_kind": route_kind,
                "route_family": route_family,
                "route_status": route_status,
                "outcome": outcome,
            },
        )
    )
    try:
        with _metadata_conn(db_path, ctx) as conn:
            existing_history_rows = conn.execute(
                """
                SELECT outcome, route_status
                FROM publisher_download_route_history
                WHERE normalized_url = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (normalized_url,),
            ).fetchall()
            attempts = len(existing_history_rows) + 1
            verified_successes = sum(
                1
                for row in existing_history_rows
                if _is_verified_success(str(row[1] or ""), str(row[0] or ""))
            )
            if _is_verified_success(route_status, outcome):
                verified_successes += 1
            last_n_outcomes = [outcome] + [
                str(row[0] or "").strip()
                for row in existing_history_rows[:4]
                if str(row[0] or "").strip()
            ]
            confidence_score = _confidence_score_for_history(
                attempts=attempts,
                verified_successes=verified_successes,
                route_kind=route_kind,
                route_family=route_family,
                route_status=route_status,
                outcome=outcome,
                browser_had_structured_result=browser_had_structured_result,
                onsite_completeness_status=onsite_completeness_status,
            )
            conn.execute(
                """
                INSERT INTO publisher_download_route_history(
                    normalized_url,
                    source_url,
                    route_kind,
                    route_summary,
                    outcome,
                    route_family,
                    route_status,
                    resolved_target_url,
                    route_steps_json,
                    confirmation_evidence_json,
                    terminal_evidence_json,
                    browser_had_structured_result,
                    used_candidate_pdf_url,
                    used_candidate_source_page,
                    candidate_pdf_url,
                    candidate_source_page_urls_json,
                    candidate_discovery_provenances_json,
                    publisher_discovery_route_kind,
                    publisher_recommended_discovery_route_kind,
                    blocked_reason,
                    blocked_reason_detail,
                    last_downloaded_file_path,
                    last_final_page_url,
                    onsite_capture_path,
                    onsite_capture_format,
                    onsite_page_count,
                    onsite_completeness_status,
                    attempts,
                    verified_successes,
                    last_n_outcomes_json,
                    confidence_score
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_url,
                    source_url,
                    route_kind,
                    route_summary,
                    outcome,
                    route_family,
                    route_status,
                    resolved_target_url,
                    _serialize_route_steps(request.route_steps),
                    _serialize_confirmation_evidence(request.confirmation_evidence),
                    _serialize_terminal_evidence(request.terminal_evidence),
                    1 if request.browser_had_structured_result else 0,
                    1 if request.used_candidate_pdf_url else 0,
                    1 if request.used_candidate_source_page else 0,
                    str(request.candidate_pdf_url or "").strip() or None,
                    json.dumps(
                        clean_string_list(request.candidate_source_page_urls),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        clean_string_list(request.candidate_discovery_provenances),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    str(request.publisher_discovery_route_kind or "").strip() or None,
                    str(
                        request.publisher_recommended_discovery_route_kind or ""
                    ).strip()
                    or None,
                    blocked_reason,
                    blocked_reason_detail,
                    last_downloaded_file_path,
                    last_final_page_url,
                    onsite_capture_path,
                    onsite_capture_format,
                    onsite_page_count,
                    onsite_completeness_status,
                    attempts,
                    verified_successes,
                    json.dumps(
                        clean_string_list(last_n_outcomes),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    confidence_score,
                ),
            )
            recorded_source_url = source_url
            recorded_route_kind = route_kind
            recorded_outcome = outcome
            best_history_row = conn.execute(
                """
                SELECT
                    source_url,
                    route_kind,
                    route_summary,
                    outcome,
                    route_family,
                    route_status,
                    resolved_target_url,
                    route_steps_json,
                    browser_had_structured_result,
                    last_downloaded_file_path,
                    last_final_page_url
                FROM publisher_download_route_history
                WHERE normalized_url = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (normalized_url,),
            ).fetchall()
            best_projection = None
            best_score = -1
            for row in best_history_row:
                score = _route_projection_rank(
                    str(row[5] or "").strip(),
                    str(row[3] or "").strip(),
                ) * 100 + _route_reusability_bonus(
                    route_summary=str(row[2] or "").strip(),
                    route_steps_json=str(row[7] or "").strip() or None,
                    outcome=str(row[3] or "").strip(),
                    browser_had_structured_result=_bool_from_db(row[8]),
                )
                if score > best_score:
                    best_projection = row
                    best_score = score
            projected_source_url = source_url
            projected_route_kind = route_kind
            projected_route_summary = route_summary
            projected_outcome = outcome
            projected_last_downloaded_file_path = last_downloaded_file_path
            projected_last_final_page_url = last_final_page_url
            if best_projection is not None:
                projected_source_url = (
                    str(best_projection[0] or "").strip() or projected_source_url
                )
                projected_route_kind = (
                    str(best_projection[1] or "").strip() or projected_route_kind
                )
                projected_route_summary = (
                    str(best_projection[2] or "").strip() or projected_route_summary
                )
                projected_outcome = (
                    str(best_projection[3] or "").strip() or projected_outcome
                )
                projected_last_downloaded_file_path = (
                    str(best_projection[9] or "").strip()
                    or projected_last_downloaded_file_path
                )
                projected_last_final_page_url = (
                    str(best_projection[10] or "").strip()
                    or projected_last_final_page_url
                )
            publisher_row = conn.execute(
                """
                SELECT id, insights_url
                FROM publishers
                WHERE normalized_insights_url=?
                ORDER BY id ASC
                LIMIT 1
                """,
                (normalized_url,),
            ).fetchone()
            matched_id: Optional[int] = None
            if publisher_row is not None:
                matched_id = int(publisher_row[0])
                projected_source_url = (
                    str(publisher_row[1] or "").strip() or projected_source_url
                )
            if matched_id is None:
                parsed = urlsplit(projected_source_url)
                normalized_projected_source_url = _normalize_optional_url_key(
                    projected_source_url
                )
                placeholder_name = parsed.netloc or projected_source_url
                homepage = (
                    f"{parsed.scheme}://{parsed.netloc}/"
                    if parsed.scheme and parsed.netloc
                    else ""
                )
                cur = conn.execute(
                    """
                    INSERT INTO publishers(
                        name,
                        homepage,
                        self_presentation,
                        insights_url,
                        normalized_insights_url,
                        download_route_kind,
                        download_route_summary,
                        download_route_outcome,
                        download_route_last_downloaded_file_path,
                        download_route_last_final_page_url,
                        download_route_updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
                    """,
                    (
                        placeholder_name,
                        homepage,
                        "",
                        projected_source_url,
                        normalized_projected_source_url,
                        projected_route_kind,
                        projected_route_summary,
                        projected_outcome,
                        projected_last_downloaded_file_path,
                        projected_last_final_page_url,
                    ),
                )
                matched_id = int(cur.lastrowid or 0)
            else:
                conn.execute(
                    """
                    UPDATE publishers
                    SET
                        download_route_kind=?,
                        download_route_summary=?,
                        download_route_outcome=?,
                        download_route_last_downloaded_file_path=?,
                        download_route_last_final_page_url=?,
                        download_route_updated_at=strftime('%s','now')
                    WHERE id=?
                    """,
                    (
                        projected_route_kind,
                        projected_route_summary,
                        projected_outcome,
                        projected_last_downloaded_file_path,
                        projected_last_final_page_url,
                        matched_id,
                    ),
                )
    except sqlite3.Error as exc:
        raise AppError(
            code="publisher_route_record_failed",
            message="Failed to record publisher route memory",
            cause=exc,
            retryable=True,
            context={"db_path": db_path, "source_url": source_url},
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_route_record_complete",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "source_url": recorded_source_url,
                "route_kind": recorded_route_kind,
                "route_family": route_family,
                "route_status": route_status,
                "outcome": recorded_outcome,
                "projected_route_kind": projected_route_kind,
                "projected_outcome": projected_outcome,
                "blocked_reason": blocked_reason or "",
                "onsite_capture_path": onsite_capture_path or "",
                "attempts": attempts,
                "verified_successes": verified_successes,
                "confidence_score": confidence_score,
            },
        )
    )
