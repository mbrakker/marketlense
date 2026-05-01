from __future__ import annotations

from dataclasses import asdict
import json
from typing import List, Optional, cast

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadNetworkEvent,
    BrowserDownloadRouteStep,
    DownloadTerminalEvidence,
)
from src.contracts.publisher_inventory import (
    PublisherInventoryRouteTrace,
    PublisherInventoryRunQualitySummary,
    PublisherInventoryScenarioSummary,
)
from src.utils.coercion import clean_string_list

from .common import _optional_int

def _serialize_inventory_run_quality_summary(summary) -> Optional[str]:
    if summary is None:
        return None
    return json.dumps(
        asdict(summary),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _serialize_dataclass_payload(payload) -> Optional[str]:
    if payload is None:
        return None
    return json.dumps(
        asdict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_inventory_route_trace(payload: Optional[str]):
    token = str(payload or "").strip()
    if not token:
        return None
    from src.contracts.publisher_inventory import PublisherInventoryRouteTrace
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    try:
        return PublisherInventoryRouteTrace(
            schema_version=str(parsed.get("schema_version") or "1.0"),
            followed_report_listing=bool(parsed.get("followed_report_listing", False)),
            applied_report_filter=bool(parsed.get("applied_report_filter", False)),
            selected_filters=clean_string_list(parsed.get("selected_filters", [])),
            selected_tab_labels=clean_string_list(
                parsed.get("selected_tab_labels", [])
            ),
            pagination_mode=str(parsed.get("pagination_mode") or "none").strip()
            or "none",
            preferred_control_labels=clean_string_list(
                parsed.get("preferred_control_labels", [])
            ),
            candidate_surface_guard=str(
                parsed.get("candidate_surface_guard") or "none"
            ).strip()
            or "none",
            surface_class=str(parsed.get("surface_class") or "unknown").strip()
            or "unknown",
        )
    except (TypeError, ValueError):
        return None


def _parse_inventory_scenario_summary(payload: Optional[str]):
    token = str(payload or "").strip()
    if not token:
        return None
    from src.contracts.publisher_inventory import PublisherInventoryScenarioSummary
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    try:
        return PublisherInventoryScenarioSummary(
            schema_version=str(parsed.get("schema_version") or "1.0"),
            scenario_class=str(parsed.get("scenario_class") or "unknown").strip()
            or "unknown",
            source_surface_class=str(
                parsed.get("source_surface_class") or "unknown"
            ).strip()
            or "unknown",
            confidence=float(parsed.get("confidence") or 0.0),
            direct_detail_eligible=bool(parsed.get("direct_detail_eligible", False)),
            browser_preferred=bool(parsed.get("browser_preferred", False)),
            notes=str(parsed.get("notes") or "").strip(),
        )
    except (TypeError, ValueError):
        return None


def _parse_inventory_run_quality_summary(payload: Optional[str]):
    token = str(payload or "").strip()
    if not token:
        return None
    from src.contracts.publisher_inventory import PublisherInventoryRunQualitySummary
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    try:
        return PublisherInventoryRunQualitySummary(
            schema_version=str(parsed.get("schema_version") or "1.0"),
            outcome=str(parsed["outcome"]).strip(),
            status=str(parsed["status"]).strip(),
            quality_band=str(parsed["quality_band"]).strip(),
            route_kind=str(parsed["route_kind"]).strip(),
            recommended_route_kind=str(parsed["recommended_route_kind"]).strip(),
            used_memory_route=bool(parsed["used_memory_route"]),
            page_count=int(parsed["page_count"]),
            raw_candidate_count=int(parsed["raw_candidate_count"]),
            current_report_count=int(parsed["current_report_count"]),
            previous_report_count=int(parsed["previous_report_count"]),
            raw_new_report_count=int(parsed["raw_new_report_count"]),
            screened_new_report_count=int(parsed["screened_new_report_count"]),
            qualified_new_report_count=int(parsed["qualified_new_report_count"]),
            snapshot_changed=bool(parsed["snapshot_changed"]),
            requires_review=bool(parsed["requires_review"]),
            recommended_route_reason=str(parsed["recommended_route_reason"]).strip(),
            summary=str(parsed["summary"]).strip(),
            candidate_provenance_counts={
                str(key).strip(): int(value)
                for key, value in dict(
                    parsed.get("candidate_provenance_counts") or {}
                ).items()
                if str(key).strip()
            },
            scenario_class=str(parsed.get("scenario_class") or "").strip() or None,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _serialize_route_steps(steps: List[BrowserDownloadRouteStep]) -> str:
    return json.dumps(
        [asdict(step) for step in steps],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_route_steps(payload: Optional[str]) -> List[BrowserDownloadRouteStep]:
    token = str(payload or "").strip()
    if not token:
        return []
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    steps: List[BrowserDownloadRouteStep] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            continue
        try:
            steps.append(
                BrowserDownloadRouteStep(
                    schema_version=str(item.get("schema_version") or "1.0"),
                    index=int(
                        str(
                            item.get("index")
                            if item.get("index") is not None
                            else index
                        )
                    ),
                    action=str(item.get("action") or "").strip(),
                    target_text=str(item.get("target_text") or "").strip(),
                    target_role=str(item.get("target_role") or "").strip(),
                    target_url=str(item.get("target_url") or "").strip(),
                    result=str(item.get("result") or "").strip(),
                )
            )
        except (TypeError, ValueError):
            continue
    return steps


def _serialize_confirmation_evidence(
    evidence: BrowserDownloadConfirmationEvidence,
) -> str:
    return json.dumps(
        asdict(evidence),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _serialize_terminal_evidence(
    evidence: DownloadTerminalEvidence,
) -> str:
    return json.dumps(
        asdict(evidence),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_confirmation_evidence(
    payload: Optional[str],
    *,
    final_page_url: str = "",
) -> BrowserDownloadConfirmationEvidence:
    token = str(payload or "").strip()
    if not token:
        return _empty_confirmation_evidence(final_page_url=final_page_url)
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return _empty_confirmation_evidence(final_page_url=final_page_url)
    if not isinstance(parsed, dict):
        return _empty_confirmation_evidence(final_page_url=final_page_url)
    try:
        return BrowserDownloadConfirmationEvidence(
            schema_version=str(parsed.get("schema_version") or "1.0"),
            url_changed=bool(parsed.get("url_changed")),
            visible_confirmation_text=str(
                parsed.get("visible_confirmation_text") or ""
            ).strip(),
            submit_button_state=str(parsed.get("submit_button_state") or "").strip()
            or "unchanged",
            form_disappeared=bool(parsed.get("form_disappeared")),
            final_page_url=str(parsed.get("final_page_url") or final_page_url).strip(),
            confirmation_score=int(parsed.get("confirmation_score") or 0),
            signal_labels=clean_string_list(parsed.get("signal_labels") or []),
        )
    except (TypeError, ValueError):
        return _empty_confirmation_evidence(final_page_url=final_page_url)


def _empty_confirmation_evidence(
    *,
    final_page_url: str,
) -> BrowserDownloadConfirmationEvidence:
    return BrowserDownloadConfirmationEvidence(
        schema_version="1.0",
        url_changed=False,
        visible_confirmation_text="",
        submit_button_state="unchanged",
        form_disappeared=False,
        final_page_url=final_page_url,
        confirmation_score=0,
        signal_labels=[],
    )


def _parse_terminal_evidence(
    payload: Optional[str],
    *,
    final_page_url: str = "",
) -> DownloadTerminalEvidence:
    token = str(payload or "").strip()
    if not token:
        return _empty_terminal_evidence(final_page_url=final_page_url)
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return _empty_terminal_evidence(final_page_url=final_page_url)
    if not isinstance(parsed, dict):
        return _empty_terminal_evidence(final_page_url=final_page_url)
    try:
        return DownloadTerminalEvidence(
            schema_version=str(parsed.get("schema_version") or "1.0"),
            final_page_url=str(parsed.get("final_page_url") or final_page_url).strip(),
            final_page_title=str(parsed.get("final_page_title") or "").strip(),
            terminal_text_excerpt=str(
                parsed.get("terminal_text_excerpt") or ""
            ).strip(),
            artifact_url=str(parsed.get("artifact_url") or "").strip(),
            artifact_kind=str(parsed.get("artifact_kind") or "none").strip() or "none",
            artifact_validation_status=str(
                parsed.get("artifact_validation_status") or "none"
            ).strip()
            or "none",
            artifact_validation_detail=str(
                parsed.get("artifact_validation_detail") or ""
            ).strip(),
            confirmation_signal_count=int(parsed.get("confirmation_signal_count") or 0),
            traversed_page_urls=clean_string_list(
                parsed.get("traversed_page_urls") or []
            ),
            visited_url_timeline=clean_string_list(
                parsed.get("visited_url_timeline") or []
            ),
            observed_document_urls=clean_string_list(
                parsed.get("observed_document_urls") or []
            ),
            network_events=_parse_network_events(parsed.get("network_events")),
            html_snapshot_path=str(parsed.get("html_snapshot_path") or "").strip(),
            screenshot_path=str(parsed.get("screenshot_path") or "").strip(),
            dom_snapshot_sha256=str(parsed.get("dom_snapshot_sha256") or "").strip(),
            evidence_labels=clean_string_list(parsed.get("evidence_labels") or []),
        )
    except (TypeError, ValueError):
        return _empty_terminal_evidence(final_page_url=final_page_url)


def _empty_terminal_evidence(
    *,
    final_page_url: str,
) -> DownloadTerminalEvidence:
    return DownloadTerminalEvidence(
        schema_version="1.0",
        final_page_url=final_page_url,
        final_page_title="",
        terminal_text_excerpt="",
        artifact_url="",
        artifact_kind="none",
        artifact_validation_status="none",
        artifact_validation_detail="",
        confirmation_signal_count=0,
        traversed_page_urls=[],
        visited_url_timeline=[],
        observed_document_urls=[],
        network_events=[],
        html_snapshot_path="",
        screenshot_path="",
        dom_snapshot_sha256="",
        evidence_labels=[],
    )


def _parse_network_events(payload: object) -> List[BrowserDownloadNetworkEvent]:
    if not isinstance(payload, list):
        return []
    events: List[BrowserDownloadNetworkEvent] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        events.append(
            BrowserDownloadNetworkEvent(
                schema_version=str(item.get("schema_version") or "1.0"),
                url=url,
                initiator_type=str(item.get("initiator_type") or "other").strip()
                or "other",
                signal_kind=str(item.get("signal_kind") or "other").strip() or "other",
            )
        )
    return events


def _bool_from_db(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    token = str(value).strip().lower()
    return token in {"1", "true", "yes", "y", "on"}


def _parse_json_string_list(payload: Optional[str]) -> List[str]:
    if not payload:
        return []
    try:
        parsed = json.loads(payload)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [
        str(item).strip()
        for item in cast(list[object], parsed)
        if str(item).strip()
    ]
