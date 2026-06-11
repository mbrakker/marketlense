from __future__ import annotations

import json

from src.contracts.report_store import (
    PublisherPrivateApiCandidateObservationRecordRequest,
    PublisherPrivateApiCandidateObservationRecordResponse,
    PublisherPrivateApiCandidatePromotedRequest,
)
from src.contracts.run_context import RunContext
from src.utils.coercion import clean_string_list
from src.utils.errors import AppError
from src.utils.logging import log_event

from ..common import logger
from ..connection import _metadata_conn
from ..serialization import _parse_json_string_list

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
