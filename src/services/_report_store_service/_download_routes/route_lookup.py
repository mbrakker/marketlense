from __future__ import annotations

from typing import Optional

from src.contracts.report_store import (
    PublisherDownloadRouteGetRequest,
    PublisherDownloadRouteResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

from ..common import logger, _optional_int
from ..connection import _metadata_conn
from ..route_policy import (
    _confidence_score_for_history,
    _is_verified_success,
    _publisher_scope_history_rows,
    _route_policy_signals,
    _route_projection_rank,
    _route_reusability_bonus,
)
from ..serialization import (
    _bool_from_db,
    _empty_confirmation_evidence,
    _empty_terminal_evidence,
    _parse_confirmation_evidence,
    _parse_json_string_list,
    _parse_route_steps,
    _parse_terminal_evidence,
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
