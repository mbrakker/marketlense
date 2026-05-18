from __future__ import annotations

import json
import sqlite3
from typing import List, Optional, cast
from urllib.parse import urlsplit

from src.contracts.publisher_inventory import PublisherInventoryRoutePolicySignal
from src.contracts.report_store import PublisherDownloadRoutePolicySignal
from src.utils.coercion import clean_string_list

from .serialization import _parse_route_steps


def _route_projection_rank(route_status: str, outcome: str) -> int:
    normalized_status = str(route_status or "").strip().lower()
    normalized_outcome = str(outcome or "").strip().lower()
    if normalized_status == "verified" and normalized_outcome == "downloaded":
        return 5
    if normalized_status == "verified" and normalized_outcome == "captured":
        return 4
    if normalized_status == "verified" and normalized_outcome == "email_requested":
        return 3
    if normalized_status == "inferred" and normalized_outcome == "downloaded":
        return 2
    if normalized_status == "inferred" and normalized_outcome == "captured":
        return 2
    if normalized_status == "inferred" and normalized_outcome == "email_requested":
        return 1
    if normalized_outcome == "email_required":
        return 1
    return 0


def _route_reusability_bonus(
    *,
    route_summary: str,
    route_steps_json: str | None,
    outcome: str,
    browser_had_structured_result: bool,
) -> int:
    bonus = 0
    if browser_had_structured_result:
        bonus += 3
    route_steps = _parse_route_steps(route_steps_json)
    if route_steps:
        bonus += 2
    actions = [str(step.action or "").strip().lower() for step in route_steps]
    scroll_count = sum(1 for action in actions if action == "scroll")
    non_scroll_count = sum(1 for action in actions if action and action != "scroll")
    bonus += min(non_scroll_count, 3)
    bonus -= min(scroll_count, 4)
    normalized_outcome = str(outcome or "").strip().lower()
    if normalized_outcome == "captured" and "extract" in actions:
        bonus += 8
    elif normalized_outcome == "email_requested" and "submit" in actions:
        bonus += 8
    elif normalized_outcome == "downloaded" and any(
        action in {"download", "save_as_pdf"} for action in actions
    ):
        bonus += 8
    normalized_summary = str(route_summary or "").strip().lower()
    if "extract" in normalized_summary:
        bonus += 3
    if "scroll" in normalized_summary and "extract" not in normalized_summary:
        bonus -= 1
    return bonus


def _is_verified_success(route_status: str, outcome: str) -> bool:
    normalized_status = str(route_status or "").strip().lower()
    normalized_outcome = str(outcome or "").strip().lower()
    return normalized_status == "verified" and normalized_outcome in {
        "downloaded",
        "email_requested",
        "captured",
    }


def _confidence_score_for_history(
    *,
    attempts: int,
    verified_successes: int,
    route_kind: str,
    route_family: str,
    route_status: str,
    outcome: str,
    browser_had_structured_result: bool,
    onsite_completeness_status: str | None,
) -> float:
    if attempts <= 0:
        return 0.0
    base = verified_successes / attempts
    normalized_route_kind = str(route_kind or "").strip().lower()
    normalized_route_family = str(route_family or "").strip().lower()
    completeness = str(onsite_completeness_status or "").strip().lower()
    if _is_verified_success(route_status, outcome):
        if normalized_route_family in {"direct_pdf_probe", "http_pdf_probe"}:
            base += 0.3
        elif normalized_route_kind == "email_delivery":
            base += 0.15
        elif normalized_route_kind == "onsite_report":
            base += 0.2 if completeness == "complete" else -0.15
        elif browser_had_structured_result:
            base += 0.2
        else:
            base += 0.05
    elif str(outcome or "").strip().lower() == "email_required":
        base += 0.05
    if not browser_had_structured_result and normalized_route_family not in {
        "direct_pdf_probe",
        "http_pdf_probe",
    }:
        base -= 0.15
    if normalized_route_kind == "onsite_report" and completeness != "complete":
        base -= 0.2
    return min(1.0, round(base, 3))


def _route_policy_signals(
    history_rows: list[tuple],
) -> List[PublisherDownloadRoutePolicySignal]:
    grouped: dict[str, dict[str, object]] = {}
    for row in history_rows:
        route_kind = str(row[1] or "").strip()
        route_family = str(row[4] or "").strip() or _default_route_family_for_kind(
            route_kind
        )
        route_status = str(row[5] or "").strip()
        outcome = str(row[3] or "").strip()
        blocked_reason = str(row[18] or "").strip()
        browser_had_structured_result = _bool_from_db(row[10])
        onsite_completeness_status = str(row[25] or "").strip() or None
        bucket = grouped.setdefault(
            route_family,
            {
                "route_family": route_family,
                "route_kind": route_kind,
                "attempts": 0,
                "verified_successes": 0,
                "blocked_attempts": 0,
                "recent_outcomes": [],
                "last_outcome": outcome,
                "last_route_status": route_status,
                "last_blocked_reason": blocked_reason,
                "last_browser_had_structured_result": browser_had_structured_result,
                "last_onsite_completeness_status": onsite_completeness_status,
            },
        )
        bucket["attempts"] = _bucket_int(bucket, "attempts") + 1
        if route_kind:
            bucket["route_kind"] = route_kind
        if _is_verified_success(route_status, outcome):
            bucket["verified_successes"] = _bucket_int(bucket, "verified_successes") + 1
        if blocked_reason:
            bucket["blocked_attempts"] = _bucket_int(bucket, "blocked_attempts") + 1
            if not bucket.get("last_blocked_reason"):
                bucket["last_blocked_reason"] = blocked_reason
        recent_outcomes = bucket["recent_outcomes"]
        if isinstance(recent_outcomes, list) and outcome and len(recent_outcomes) < 5:
            recent_outcomes.append(outcome)

    signals: List[PublisherDownloadRoutePolicySignal] = []
    for bucket in grouped.values():
        attempts = _bucket_int(bucket, "attempts")
        verified_successes = _bucket_int(bucket, "verified_successes")
        blocked_attempts = _bucket_int(bucket, "blocked_attempts")
        route_kind = str(bucket["route_kind"] or "").strip()
        route_family = str(bucket["route_family"] or "").strip()
        last_route_status = str(bucket["last_route_status"] or "").strip()
        last_outcome = str(bucket["last_outcome"] or "").strip()
        success_rate = round(verified_successes / attempts, 3) if attempts else 0.0
        confidence_score = _confidence_score_for_history(
            attempts=attempts,
            verified_successes=verified_successes,
            route_kind=route_kind,
            route_family=route_family,
            route_status=last_route_status,
            outcome=last_outcome,
            browser_had_structured_result=bool(
                bucket["last_browser_had_structured_result"]
            ),
            onsite_completeness_status=str(
                bucket["last_onsite_completeness_status"] or ""
            ).strip()
            or None,
        )
        blocked_rate = blocked_attempts / attempts if attempts else 0.0
        latest_verified_bonus = (
            0.08 if _is_verified_success(last_route_status, last_outcome) else 0.0
        )
        rank_score = min(
            1.0,
            max(
                0.0,
                (confidence_score * 0.6)
                + (success_rate * 0.35)
                + latest_verified_bonus
                - min(0.25, blocked_rate * 0.25),
            ),
        )
        recent_outcomes_value = bucket["recent_outcomes"]
        signals.append(
            PublisherDownloadRoutePolicySignal(
                schema_version="1.0",
                route_family=route_family,
                route_kind=route_kind,
                attempts=attempts,
                verified_successes=verified_successes,
                blocked_attempts=blocked_attempts,
                success_rate=success_rate,
                confidence_score=confidence_score,
                rank_score=round(rank_score, 3),
                last_outcome=last_outcome,
                last_route_status=last_route_status,
                last_blocked_reason=str(bucket["last_blocked_reason"] or "").strip()
                or None,
                recent_outcomes=(
                    list(recent_outcomes_value)
                    if isinstance(recent_outcomes_value, list)
                    else []
                ),
            )
        )
    return sorted(
        signals,
        key=lambda signal: (
            signal.rank_score,
            signal.confidence_score,
            signal.success_rate,
            signal.verified_successes,
            -signal.blocked_attempts,
        ),
        reverse=True,
    )


def _publisher_scope_history_rows(
    *,
    conn: sqlite3.Connection,
    normalized_url: str,
    publisher_scope_url: str | None,
) -> list[tuple[object, ...]]:
    scope_hosts = {
        _url_host(value)
        for value in [publisher_scope_url, normalized_url]
        if str(value or "").strip()
    }
    scope_hosts.discard("")
    if not scope_hosts:
        return []
    rows = conn.execute(
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
            updated_at,
            normalized_url
        FROM publisher_download_route_history
        WHERE normalized_url <> ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 500
        """,
        (normalized_url,),
    ).fetchall()
    scoped_rows: list[tuple] = []
    for row in rows:
        row_scope_values = [
            str(row[0] or "").strip(),
            str(row[31] or "").strip(),
            *_parse_json_string_list(str(row[14] or "").strip() or None),
        ]
        row_hosts = {_url_host(value) for value in row_scope_values if value}
        row_hosts.discard("")
        if row_hosts & scope_hosts:
            scoped_rows.append(row[:31])
    return scoped_rows


def _url_host(value: str | None) -> str:
    try:
        return str(urlsplit(str(value or "").strip()).hostname or "").strip().lower()
    except ValueError:
        return ""


def _publisher_inventory_route_policy_signals(
    history_rows: list[tuple],
) -> List[PublisherInventoryRoutePolicySignal]:
    grouped: dict[str, dict[str, object]] = {}
    for row in history_rows:
        route_kind = str(row[0] or "").strip()
        outcome = str(row[1] or "").strip()
        status = str(row[2] or "").strip()
        quality_band = str(row[3] or "").strip()
        requires_review = _bool_from_db(row[4])
        scenario_class = str(row[5] or "").strip() or None
        bucket = grouped.setdefault(
            route_kind,
            {
                "route_kind": route_kind,
                "attempts": 0,
                "successful_attempts": 0,
                "review_required_attempts": 0,
                "recent_outcomes": [],
                "last_outcome": outcome,
                "last_status": status,
                "last_quality_band": quality_band,
                "last_scenario_class": scenario_class,
            },
        )
        bucket["attempts"] = _bucket_int(bucket, "attempts") + 1
        if _inventory_route_attempt_succeeded(
            outcome=outcome,
            status=status,
            quality_band=quality_band,
            requires_review=requires_review,
        ):
            bucket["successful_attempts"] = (
                _bucket_int(bucket, "successful_attempts") + 1
            )
        if requires_review:
            bucket["review_required_attempts"] = (
                _bucket_int(bucket, "review_required_attempts") + 1
            )
        recent_outcomes = bucket["recent_outcomes"]
        if isinstance(recent_outcomes, list) and outcome and len(recent_outcomes) < 5:
            recent_outcomes.append(outcome)

    signals: List[PublisherInventoryRoutePolicySignal] = []
    for bucket in grouped.values():
        route_kind = str(bucket["route_kind"] or "").strip()
        attempts = _bucket_int(bucket, "attempts")
        successful_attempts = _bucket_int(bucket, "successful_attempts")
        review_required_attempts = _bucket_int(bucket, "review_required_attempts")
        success_rate = round(successful_attempts / attempts, 3) if attempts else 0.0
        review_rate = review_required_attempts / attempts if attempts else 0.0
        confidence_score = min(
            1.0,
            max(
                0.0,
                success_rate
                + min(0.2, successful_attempts * 0.04)
                - min(0.35, review_rate * 0.35),
            ),
        )
        quality_bonus = (
            0.08 if str(bucket["last_quality_band"] or "").strip() == "high" else 0.0
        )
        rank_score = min(
            1.0,
            max(
                0.0,
                (confidence_score * 0.6)
                + (success_rate * 0.35)
                + quality_bonus
                - min(0.2, review_rate * 0.2),
            ),
        )
        recent_outcomes = bucket["recent_outcomes"]
        signals.append(
            PublisherInventoryRoutePolicySignal(
                schema_version="1.0",
                route_kind=route_kind,
                attempts=attempts,
                successful_attempts=successful_attempts,
                review_required_attempts=review_required_attempts,
                success_rate=success_rate,
                confidence_score=round(confidence_score, 3),
                rank_score=round(rank_score, 3),
                last_outcome=str(bucket["last_outcome"] or "").strip(),
                last_status=str(bucket["last_status"] or "").strip(),
                last_quality_band=str(bucket["last_quality_band"] or "").strip(),
                last_scenario_class=str(bucket["last_scenario_class"] or "").strip()
                or None,
                recent_outcomes=(
                    list(recent_outcomes) if isinstance(recent_outcomes, list) else []
                ),
            )
        )
    return sorted(
        signals,
        key=lambda signal: (
            signal.rank_score,
            signal.confidence_score,
            signal.success_rate,
            signal.successful_attempts,
            -signal.review_required_attempts,
        ),
        reverse=True,
    )


def _inventory_route_attempt_succeeded(
    *,
    outcome: str,
    status: str,
    quality_band: str,
    requires_review: bool,
) -> bool:
    normalized_status = str(status or "").strip().lower()
    normalized_outcome = str(outcome or "").strip().lower()
    normalized_quality = str(quality_band or "").strip().lower()
    if normalized_status.startswith("failed:"):
        return False
    if requires_review and normalized_quality == "low":
        return False
    return normalized_outcome in {
        "accepted",
        "no_report_assets",
        "unreachable_delta_tolerated",
    } and normalized_status.startswith("passed")


def _publisher_inventory_route_policy_rows(
    *,
    conn: sqlite3.Connection,
    normalized_url: str,
) -> list[tuple]:
    source_host = _url_host(normalized_url)
    if not source_host:
        return []
    return conn.execute(
        """
        SELECT
            route_kind,
            outcome,
            status,
            quality_band,
            requires_review,
            scenario_class
        FROM publisher_inventory_route_history
        WHERE source_host = ?
          AND normalized_url <> ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 200
        """,
        (source_host, normalized_url),
    ).fetchall()


def _bucket_int(bucket: dict[str, object], key: str) -> int:
    value = bucket.get(key, 0)
    if isinstance(value, int):
        return value
    return int(cast(str, value))


def _default_route_family_for_kind(route_kind: str) -> str:
    normalized_route_kind = str(route_kind or "").strip()
    if normalized_route_kind == "email_delivery":
        return "browser_email_form"
    if normalized_route_kind == "onsite_report":
        return "browser_onsite_report"
    return "browser_pdf_click"


def _bool_from_db(value: object) -> bool:
    return bool(int(str(value or 0)))


def _parse_json_string_list(payload: Optional[str]) -> List[str]:
    token = str(payload or "").strip()
    if not token:
        return []
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return clean_string_list(parsed)
