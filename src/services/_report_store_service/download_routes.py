from __future__ import annotations

import json
import sqlite3
from typing import Optional
from urllib.parse import urlsplit

from src.contracts.report_store import (
    PublisherPrivateApiCandidateObservationRecordRequest,
    PublisherPrivateApiCandidateObservationRecordResponse,
    PublisherPrivateApiCandidatePromotedRequest,
    PublisherDownloadRouteGetRequest,
    PublisherDownloadRouteRecordRequest,
    PublisherDownloadRouteResponse,
)
from src.contracts.run_context import RunContext
from src.utils.coercion import clean_string_list
from src.utils.errors import AppError
from src.utils.logging import log_event

from .common import logger, _normalize_optional_url_key, _optional_int
from .connection import _metadata_conn
from .route_policy import (
    _confidence_score_for_history,
    _default_route_family_for_kind,
    _is_verified_success,
    _publisher_scope_history_rows,
    _route_policy_signals,
    _route_projection_rank,
    _route_reusability_bonus,
)
from .serialization import (
    _bool_from_db,
    _empty_confirmation_evidence,
    _empty_terminal_evidence,
    _parse_confirmation_evidence,
    _parse_json_string_list,
    _parse_route_steps,
    _parse_terminal_evidence,
    _serialize_confirmation_evidence,
    _serialize_route_steps,
    _serialize_terminal_evidence,
)


def record_publisher_private_api_candidate_observation(
    request: PublisherPrivateApiCandidateObservationRecordRequest,
    ctx: RunContext,
) -> PublisherPrivateApiCandidateObservationRecordResponse:
    db_path = request.db_path.strip()
    fingerprint = request.fingerprint.strip()
    if not db_path:
        raise AppError(
            code="private_api_candidate_db_missing",
            message="Report metadata DB path is required for private-API candidate recording",
            retryable=False,
            severity="error",
        )
    if not fingerprint:
        raise AppError(
            code="private_api_candidate_fingerprint_missing",
            message="Private-API candidate fingerprint is required",
            retryable=False,
            severity="error",
        )
    observed_at = str(request.observed_at or "").strip()
    if not observed_at:
        raise AppError(
            code="private_api_candidate_observed_at_missing",
            message="Private-API candidate observed_at timestamp is required",
            retryable=False,
            severity="error",
            context={"fingerprint": fingerprint},
        )
    source_url = request.source_url.strip()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="private_api_candidate_record_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "fingerprint": fingerprint,
                "source_url": source_url,
                "endpoint_pattern": request.endpoint_pattern,
            },
        )
    )
    with _metadata_conn(db_path, ctx) as conn:
        row = conn.execute(
            """
            SELECT
                source_urls_json,
                success_count,
                promoted_playbook_id
            FROM publisher_private_api_candidates
            WHERE fingerprint = ?
            """,
            (fingerprint,),
        ).fetchone()
        source_urls = []
        success_count = 0
        promoted_playbook_id = ""
        if row is not None:
            source_urls = _parse_json_string_list(str(row[0] or "[]"))
            success_count = int(row[1] or 0)
            promoted_playbook_id = str(row[2] or "").strip()
        if source_url and source_url not in source_urls:
            source_urls.append(source_url)
        success_count += 1
        evidence_labels = clean_string_list(request.evidence_labels)
        if row is None:
            conn.execute(
                """
                INSERT INTO publisher_private_api_candidates(
                    fingerprint,
                    publisher_host,
                    endpoint_pattern,
                    method,
                    request_shape_summary,
                    response_pdf_url_json_pointer,
                    expected_status_codes_json,
                    required_response_markers_json,
                    fallback_route_family,
                    route_family,
                    route_kind,
                    evidence_labels_json,
                    source_urls_json,
                    success_count,
                    first_observed_at_utc,
                    last_observed_at_utc
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fingerprint,
                    request.publisher_host.strip(),
                    request.endpoint_pattern.strip(),
                    request.method.strip().upper(),
                    request.request_shape_summary.strip(),
                    request.response_pdf_url_json_pointer.strip(),
                    json.dumps(
                        [int(item) for item in request.expected_status_codes],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        clean_string_list(request.required_response_markers),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    request.fallback_route_family.strip(),
                    request.route_family.strip(),
                    request.route_kind.strip(),
                    json.dumps(
                        evidence_labels,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        source_urls,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    success_count,
                    observed_at,
                    observed_at,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE publisher_private_api_candidates
                SET
                    source_urls_json = ?,
                    success_count = ?,
                    last_observed_at_utc = ?,
                    updated_at = strftime('%s','now')
                WHERE fingerprint = ?
                """,
                (
                    json.dumps(
                        source_urls,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    success_count,
                    observed_at,
                    fingerprint,
                ),
            )
        distinct_source_url_count = len(source_urls)
        already_promoted = bool(promoted_playbook_id)
        eligible = (
            not already_promoted
            and success_count >= max(1, int(request.min_success_count))
            and distinct_source_url_count
            >= max(1, int(request.min_distinct_source_urls))
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="private_api_candidate_record_complete",
            module=logger.name,
            fields={
                "fingerprint": fingerprint,
                "success_count": success_count,
                "distinct_source_url_count": distinct_source_url_count,
                "eligible_for_promotion": eligible,
                "already_promoted": already_promoted,
            },
        )
    )
    return PublisherPrivateApiCandidateObservationRecordResponse(
        schema_version="1.0",
        fingerprint=fingerprint,
        success_count=success_count,
        distinct_source_url_count=distinct_source_url_count,
        eligible_for_promotion=eligible,
        already_promoted=already_promoted,
        promoted_playbook_id=promoted_playbook_id,
    )


def mark_publisher_private_api_candidate_promoted(
    request: PublisherPrivateApiCandidatePromotedRequest,
    ctx: RunContext,
) -> None:
    db_path = request.db_path.strip()
    fingerprint = request.fingerprint.strip()
    playbook_id = request.playbook_id.strip()
    promoted_at = request.promoted_at.strip()
    if not db_path or not fingerprint or not playbook_id or not promoted_at:
        raise AppError(
            code="private_api_candidate_promotion_record_invalid",
            message="Private-API promotion record request is missing required fields",
            retryable=False,
            severity="error",
            context={
                "has_db_path": bool(db_path),
                "has_fingerprint": bool(fingerprint),
                "has_playbook_id": bool(playbook_id),
                "has_promoted_at": bool(promoted_at),
            },
        )
    with _metadata_conn(db_path, ctx) as conn:
        cursor = conn.execute(
            """
            UPDATE publisher_private_api_candidates
            SET
                promoted_playbook_id = ?,
                promoted_at_utc = ?,
                updated_at = strftime('%s','now')
            WHERE fingerprint = ?
            """,
            (playbook_id, promoted_at, fingerprint),
        )
        if cursor.rowcount == 0:
            raise AppError(
                code="private_api_candidate_not_found",
                message="Private-API candidate could not be marked promoted because it was not found",
                retryable=False,
                severity="error",
                context={"fingerprint": fingerprint},
            )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="private_api_candidate_promoted_recorded",
            module=logger.name,
            fields={
                "fingerprint": fingerprint,
                "playbook_id": playbook_id,
                "promoted_at": promoted_at,
            },
        )
    )


def get_publisher_download_route(
    request: PublisherDownloadRouteGetRequest,
    ctx: RunContext,
) -> Optional[PublisherDownloadRouteResponse]:
    db_path = request.db_path.strip()
    normalized_url = request.normalized_url.strip()
    publisher_scope_url = str(request.publisher_scope_url or "").strip() or None
    if not db_path:
        raise AppError(
            code="publisher_route_db_missing",
            message="Report metadata DB path is required for publisher route lookup",
            retryable=False,
            severity="error",
        )
    if not normalized_url:
        raise AppError(
            code="publisher_route_normalized_url_missing",
            message="normalized_url is required for publisher route lookup",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_route_get_start",
            module=logger.name,
            fields={"db_path": db_path, "normalized_url": normalized_url},
        )
    )
    with _metadata_conn(db_path, ctx) as conn:
        history_rows = conn.execute(
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
                confidence_score,
                updated_at
            FROM publisher_download_route_history
            WHERE normalized_url = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (normalized_url,),
        ).fetchall()
        publisher_history_rows = _publisher_scope_history_rows(
            conn=conn,
            normalized_url=normalized_url,
            publisher_scope_url=publisher_scope_url,
        )
        best_history_row = None
        best_history_score = -1
        history_attempts = len(history_rows)
        history_verified_successes = sum(
            1
            for row in history_rows
            if _is_verified_success(str(row[5] or ""), str(row[3] or ""))
        )
        history_last_outcomes = [
            str(row[3] or "").strip()
            for row in history_rows[:5]
            if str(row[3] or "").strip()
        ]
        route_policy = _route_policy_signals(history_rows)
        publisher_route_policy = _route_policy_signals(publisher_history_rows)
        for row in history_rows:
            score = _route_projection_rank(
                str(row[5] or "").strip(),
                str(row[3] or "").strip(),
            ) * 100 + _route_reusability_bonus(
                route_summary=str(row[2] or "").strip(),
                route_steps_json=str(row[7] or "").strip() or None,
                outcome=str(row[3] or "").strip(),
                browser_had_structured_result=_bool_from_db(row[10]),
            )
            if score > best_history_score:
                best_history_row = row
                best_history_score = score
        if best_history_row is not None:
            response = PublisherDownloadRouteResponse(
                schema_version="1.0",
                normalized_url=normalized_url,
                source_url=str(best_history_row[0] or "").strip(),
                route_kind=str(best_history_row[1] or "").strip(),
                route_summary=str(best_history_row[2] or "").strip(),
                outcome=str(best_history_row[3] or "").strip(),
                route_family=str(best_history_row[4] or "").strip(),
                route_status=str(best_history_row[5] or "").strip() or "inferred",
                resolved_target_url=str(best_history_row[6] or "").strip(),
                route_steps=_parse_route_steps(
                    str(best_history_row[7] or "").strip() or None
                ),
                confirmation_evidence=_parse_confirmation_evidence(
                    str(best_history_row[8] or "").strip() or None,
                    final_page_url=str(best_history_row[21] or "").strip(),
                ),
                terminal_evidence=_parse_terminal_evidence(
                    str(best_history_row[9] or "").strip() or None,
                    final_page_url=str(best_history_row[21] or "").strip(),
                ),
                browser_had_structured_result=_bool_from_db(best_history_row[10]),
                used_candidate_pdf_url=_bool_from_db(best_history_row[11]),
                used_candidate_source_page=_bool_from_db(best_history_row[12]),
                updated_at=int(best_history_row[30] or 0),
                candidate_pdf_url=str(best_history_row[13] or "").strip() or None,
                candidate_source_page_urls=_parse_json_string_list(
                    str(best_history_row[14] or "").strip() or None
                ),
                candidate_discovery_provenances=_parse_json_string_list(
                    str(best_history_row[15] or "").strip() or None
                ),
                publisher_discovery_route_kind=str(best_history_row[16] or "").strip()
                or None,
                publisher_recommended_discovery_route_kind=str(
                    best_history_row[17] or ""
                ).strip()
                or None,
                blocked_reason=str(best_history_row[18] or "").strip() or None,
                blocked_reason_detail=str(best_history_row[19] or "").strip() or None,
                last_downloaded_file_path=str(best_history_row[20] or "").strip()
                or None,
                last_final_page_url=str(best_history_row[21] or "").strip() or None,
                onsite_capture_path=str(best_history_row[22] or "").strip() or None,
                onsite_capture_format=str(best_history_row[23] or "").strip() or None,
                onsite_page_count=_optional_int(best_history_row[24]),
                onsite_completeness_status=str(best_history_row[25] or "").strip()
                or None,
                attempts=history_attempts,
                verified_successes=history_verified_successes,
                last_n_outcomes=history_last_outcomes,
                confidence_score=_confidence_score_for_history(
                    attempts=history_attempts,
                    verified_successes=history_verified_successes,
                    route_kind=str(best_history_row[1] or "").strip(),
                    route_family=str(best_history_row[4] or "").strip(),
                    route_status=str(best_history_row[5] or "").strip(),
                    outcome=str(best_history_row[3] or "").strip(),
                    browser_had_structured_result=_bool_from_db(best_history_row[10]),
                    onsite_completeness_status=str(best_history_row[25] or "").strip()
                    or None,
                ),
                exact_route_found=True,
                publisher_scope_url=publisher_scope_url,
                route_policy=route_policy,
                publisher_route_policy=publisher_route_policy,
            )
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_route_get_complete",
                    module=logger.name,
                    fields={
                        "db_path": db_path,
                        "normalized_url": normalized_url,
                        "found": True,
                        "source_url": response.source_url,
                        "route_kind": response.route_kind,
                        "route_family": response.route_family,
                        "route_status": response.route_status,
                        "outcome": response.outcome,
                        "history_backed": True,
                        "route_policy_order": [
                            signal.route_family for signal in route_policy
                        ],
                        "publisher_route_policy_order": [
                            signal.route_family for signal in publisher_route_policy
                        ],
                    },
                )
            )
            return response
        if publisher_route_policy:
            response = PublisherDownloadRouteResponse(
                schema_version="1.0",
                normalized_url=normalized_url,
                source_url=publisher_scope_url or normalized_url,
                route_kind="",
                route_summary="No exact URL route memory is available; publisher-scope route policy is available.",
                outcome="policy_only",
                route_family="",
                route_status="inferred",
                resolved_target_url=normalized_url,
                route_steps=[],
                confirmation_evidence=_empty_confirmation_evidence(
                    final_page_url=normalized_url
                ),
                terminal_evidence=_empty_terminal_evidence(
                    final_page_url=normalized_url
                ),
                browser_had_structured_result=False,
                used_candidate_pdf_url=False,
                used_candidate_source_page=False,
                updated_at=0,
                candidate_pdf_url=None,
                candidate_source_page_urls=[],
                candidate_discovery_provenances=[],
                publisher_discovery_route_kind=None,
                publisher_recommended_discovery_route_kind=None,
                blocked_reason=None,
                blocked_reason_detail=None,
                last_downloaded_file_path=None,
                last_final_page_url=None,
                onsite_capture_path=None,
                onsite_capture_format=None,
                onsite_page_count=None,
                onsite_completeness_status=None,
                attempts=0,
                verified_successes=0,
                last_n_outcomes=[],
                confidence_score=0.0,
                exact_route_found=False,
                publisher_scope_url=publisher_scope_url,
                route_policy=[],
                publisher_route_policy=publisher_route_policy,
            )
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_route_get_complete",
                    module=logger.name,
                    fields={
                        "db_path": db_path,
                        "normalized_url": normalized_url,
                        "found": True,
                        "history_backed": False,
                        "exact_route_found": False,
                        "publisher_scope_url": publisher_scope_url or "",
                        "publisher_route_policy_order": [
                            signal.route_family for signal in publisher_route_policy
                        ],
                    },
                )
            )
            return response
        row = conn.execute(
            """
            SELECT
                insights_url,
                download_route_kind,
                download_route_summary,
                download_route_outcome,
                download_route_last_downloaded_file_path,
                download_route_last_final_page_url,
                download_route_updated_at
            FROM publishers
            WHERE normalized_insights_url=?
              AND download_route_summary IS NOT NULL
            ORDER BY id ASC
            LIMIT 1
            """,
            (normalized_url,),
        ).fetchone()
    if row is not None:
        insights_url = str(row[0] or "").strip()
        legacy_final_page_url = str(row[5] or "").strip()
        legacy_outcome = str(row[3] or "").strip()
        response = PublisherDownloadRouteResponse(
            schema_version="1.0",
            normalized_url=normalized_url,
            source_url=insights_url,
            route_kind=str(row[1] or "").strip(),
            route_summary=str(row[2] or "").strip(),
            outcome=legacy_outcome,
            route_family=(
                "browser_email_form"
                if str(row[1] or "").strip() == "email_delivery"
                else "browser_pdf_click"
            ),
            route_status=(
                "verified"
                if legacy_outcome in {"downloaded", "email_requested"}
                else "inferred"
            ),
            resolved_target_url=legacy_final_page_url or insights_url,
            route_steps=[],
            confirmation_evidence=_empty_confirmation_evidence(
                final_page_url=legacy_final_page_url
            ),
            terminal_evidence=_empty_terminal_evidence(
                final_page_url=legacy_final_page_url
            ),
            browser_had_structured_result=False,
            used_candidate_pdf_url=False,
            used_candidate_source_page=False,
            updated_at=int(row[6] or 0),
            candidate_pdf_url=None,
            candidate_source_page_urls=[],
            candidate_discovery_provenances=[],
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
            blocked_reason=None,
            blocked_reason_detail=None,
            last_downloaded_file_path=str(row[4] or "").strip() or None,
            last_final_page_url=legacy_final_page_url or None,
            onsite_capture_path=None,
            onsite_capture_format=None,
            onsite_page_count=None,
            onsite_completeness_status=None,
            attempts=0,
            verified_successes=0,
            last_n_outcomes=[],
            confidence_score=0.0,
            exact_route_found=True,
            publisher_scope_url=publisher_scope_url,
            route_policy=[],
            publisher_route_policy=publisher_route_policy,
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_route_get_complete",
                module=logger.name,
                fields={
                    "db_path": db_path,
                    "normalized_url": normalized_url,
                    "found": True,
                    "source_url": response.source_url,
                    "route_kind": response.route_kind,
                    "route_family": response.route_family,
                    "route_status": response.route_status,
                    "outcome": response.outcome,
                    "history_backed": False,
                },
            )
        )
        return response
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_route_get_complete",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "found": False,
            },
        )
    )
    return None


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
