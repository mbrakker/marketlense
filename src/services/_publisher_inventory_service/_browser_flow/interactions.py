from __future__ import annotations

"""Interactions operations for publisher-inventory browser traversal."""

import asyncio
import json
import logging
from typing import Any
from src.contracts.publisher_inventory import (
    PublisherInventoryRawCandidate,
)
from src.contracts.run_context import RunContext
from src.services._publisher_inventory_service.browser_scripts import (
    _browser_apply_report_filter_script,
    _browser_click_archive_expander_script,
    _browser_click_cookie_banner_script,
    _browser_click_named_control_script,
    _browser_click_pagination_next_script,
    _browser_click_tab_script,
    _browser_inventory_growth_probe_script,
    _browser_inventory_settle_probe_script,
    _browser_inventory_state_script,
    _browser_nested_scroll_probe_script,
    _browser_scroll_to_ratio_script,
)
from src.services._publisher_inventory_service.browser_traversal_state import (
    _BrowserScrollProbeResult,
    _BrowserTraversalMetrics,
    _RenderedInventoryState,
    _browser_scroll_probe_result_from_payload,
    _increment_browser_traversal_metrics,
    _rendered_inventory_state_from_payload,
)
from src.services._publisher_inventory_service.discovery_activity import (
    _extract_candidates_from_html,
    _normalize_absolute_url,
    _normalize_text,
    _rendered_state_anchor_fingerprint,
    _resolve_next_page_url,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_service")


async def _extract_rendered_inventory_state(page: Any) -> _RenderedInventoryState:
    payload = json.loads(await page.evaluate(_browser_inventory_state_script()))
    return _rendered_inventory_state_from_payload(
        payload,
        page_url_fallback=str(await page.get_url() or ""),
    )


async def _dismiss_cookie_banner(page: Any) -> bool:
    clicked = await page.evaluate(_browser_click_cookie_banner_script())
    return str(clicked).strip().lower() == "true"


async def _reset_empty_results_filters(page: Any, labels: list[str]) -> bool:
    clicked = await page.evaluate(_browser_click_named_control_script(), labels)
    return str(clicked).strip().lower() == "true"


async def _click_tab(page: Any, tab_label: str) -> bool:
    clicked = await page.evaluate(_browser_click_tab_script(), tab_label)
    return str(clicked).strip().lower() == "true"


async def _click_load_more(
    page: Any,
    labels: list[str],
    *,
    page_candidates: list[PublisherInventoryRawCandidate],
    require_candidate_surface_match: bool,
) -> str:
    result = (
        str(
            await page.evaluate(
                _browser_click_named_control_script(),
                {
                    "labels": labels,
                    "candidate_urls": [
                        candidate.url for candidate in page_candidates if candidate.url
                    ],
                    "require_candidate_surface": require_candidate_surface_match,
                },
            )
        )
        .strip()
        .lower()
    )
    if result == "not_relevant":
        return "not_relevant"
    return "clicked" if result == "true" else "missing"


async def _click_pagination_next(page: Any) -> bool:
    clicked = await page.evaluate(_browser_click_pagination_next_script())
    return str(clicked).strip().lower() == "true"


async def _click_archive_expander(page: Any) -> bool:
    clicked = await page.evaluate(_browser_click_archive_expander_script())
    return str(clicked).strip().lower() == "true"


async def _apply_report_filter(page: Any) -> bool:
    clicked = await page.evaluate(_browser_apply_report_filter_script())
    return str(clicked).strip().lower() == "true"


async def _wait_for_tab_activation(page: Any, tab_label: str) -> None:
    expected = _normalize_text(tab_label).casefold()
    for _ in range(20):
        await _browser_wait_for_settle(page=page, delay_seconds=0.35)
        state = await _extract_rendered_inventory_state(page)
        if str(state.active_tab_label or "").casefold() == expected:
            return
    raise AppError(
        code="publisher_inventory_browser_tab_activation_timeout",
        message="Browser-render inventory discovery did not observe the requested tab become active",
        retryable=True,
        context={"tab_label": tab_label},
    )


async def _wait_for_inventory_growth(
    page: Any,
    *,
    previous_state: _RenderedInventoryState,
    current_candidate_count: int,
) -> None:
    previous_candidate_urls = {
        candidate.url
        for candidate in _extract_candidates_from_html(
            anchors=previous_state.anchors,
            page_url=previous_state.page_url,
            page_number=1,
            next_page_url=None,
        )
    }
    previous_anchor_fingerprint = _rendered_state_anchor_fingerprint(previous_state)
    for _ in range(20):
        await _browser_wait_for_settle(page=page, delay_seconds=0.35)
        state = await _extract_rendered_inventory_state(page)
        if state.page_url != previous_state.page_url:
            return
        if (
            state.result_range_end is not None
            and previous_state.result_range_end is not None
            and (
                state.result_range_end != previous_state.result_range_end
                or state.result_range_total != previous_state.result_range_total
            )
        ):
            return
        next_page_url = _resolve_next_page_url(
            current_page_url=state.page_url,
            page_number=1,
            anchors=state.anchors,
            rel_next_hrefs=[],
        )
        current_candidates = _extract_candidates_from_html(
            anchors=state.anchors,
            page_url=state.page_url,
            page_number=1,
            next_page_url=next_page_url,
        )
        current_candidate_urls = {candidate.url for candidate in current_candidates}
        if (
            len(current_candidates) > current_candidate_count
            or current_candidate_urls != previous_candidate_urls
        ):
            return
        if _rendered_state_anchor_fingerprint(state) != previous_anchor_fingerprint:
            return
    raise AppError(
        code="publisher_inventory_browser_growth_timeout",
        message="Browser-render inventory discovery did not observe new inventory items after interaction",
        retryable=True,
    )


async def _wait_for_inventory_growth_probe(
    page: Any,
    *,
    previous_state: _RenderedInventoryState,
    delay_seconds: float = 0.2,
    timeout_seconds: float = 4.0,
) -> bool:
    previous_url = (
        _normalize_absolute_url(previous_state.page_url) or previous_state.page_url
    )
    previous_anchor_count = len(previous_state.anchors)
    max_attempts = max(1, int(timeout_seconds / delay_seconds))
    for _ in range(max_attempts):
        await asyncio.sleep(delay_seconds)
        try:
            payload = json.loads(
                await page.evaluate(_browser_inventory_growth_probe_script())
            )
        except Exception:
            continue
        current_url = _normalize_absolute_url(str(payload.get("pageUrl") or "")) or ""
        if current_url and current_url != previous_url:
            return True
        if int(payload.get("anchorCount") or 0) > previous_anchor_count:
            return True
    return False


async def _wait_for_inventory_transition(
    page: Any,
    *,
    previous_state: _RenderedInventoryState,
    current_candidate_count: int,
) -> None:
    previous_urls = {
        candidate.url
        for candidate in _extract_candidates_from_html(
            anchors=previous_state.anchors,
            page_url=previous_state.page_url,
            page_number=1,
            next_page_url=None,
        )
    }
    for _ in range(20):
        await _browser_wait_for_settle(page=page, delay_seconds=0.35)
        state = await _extract_rendered_inventory_state(page)
        if state.page_url != previous_state.page_url:
            return
        if (
            state.result_range_end is not None
            and previous_state.result_range_end is not None
            and (
                state.result_range_end != previous_state.result_range_end
                or state.result_range_total != previous_state.result_range_total
            )
        ):
            return
        next_page_url = _resolve_next_page_url(
            current_page_url=state.page_url,
            page_number=1,
            anchors=state.anchors,
            rel_next_hrefs=[],
        )
        current_candidates = _extract_candidates_from_html(
            anchors=state.anchors,
            page_url=state.page_url,
            page_number=1,
            next_page_url=next_page_url,
        )
        current_urls = {candidate.url for candidate in current_candidates}
        if previous_state.result_range_end is None and (
            len(current_candidates) > current_candidate_count
            or current_urls != previous_urls
        ):
            return
    raise AppError(
        code="publisher_inventory_browser_transition_timeout",
        message="Browser-render inventory discovery did not observe a page transition after pagination click",
        retryable=True,
    )


async def _prime_browser_inventory_surface(
    page: Any,
    *,
    ctx: RunContext | None = None,
    normalized_url: str = "",
) -> _BrowserScrollProbeResult:
    for ratio in (0.0, 0.35, 0.7, 0.95):
        await page.evaluate(_browser_scroll_to_ratio_script(), ratio)
        await _browser_wait_for_settle(page=page, delay_seconds=0.35)
    try:
        payload = json.loads(await page.evaluate(_browser_nested_scroll_probe_script()))
    except Exception as exc:
        if ctx is not None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_inventory_browser_scroll_probe_failed",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "error": str(exc),
                    },
                )
            )
        return _BrowserScrollProbeResult(
            schema_version="1.0",
            scroll_surface="document",
            best_surface_label="document",
            probed_surface_count=0,
            consumed_surface_count=0,
            candidate_growth=False,
            virtualized_list_detected=False,
            anchor_count_before=0,
            anchor_count_after=0,
        )
    result = _browser_scroll_probe_result_from_payload(payload)
    if result.consumed_surface_count > 0:
        await _browser_wait_for_settle(page=page, delay_seconds=0.35)
    if ctx is not None and (
        result.probed_surface_count > 0
        or result.consumed_surface_count > 0
        or result.virtualized_list_detected
    ):
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_scroll_probe",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "scroll_surface": result.scroll_surface,
                    "best_surface_label": result.best_surface_label,
                    "probed_surface_count": result.probed_surface_count,
                    "consumed_surface_count": result.consumed_surface_count,
                    "candidate_growth": result.candidate_growth,
                    "virtualized_list_detected": result.virtualized_list_detected,
                    "anchor_count_before": result.anchor_count_before,
                    "anchor_count_after": result.anchor_count_after,
                },
            )
        )
    return result


def _record_browser_scroll_probe_metrics(
    metrics: _BrowserTraversalMetrics,
    result: _BrowserScrollProbeResult,
) -> _BrowserTraversalMetrics:
    if (
        result.scroll_surface == "document"
        and not result.candidate_growth
        and not result.virtualized_list_detected
    ):
        return metrics
    return _increment_browser_traversal_metrics(
        metrics,
        nested_scroll_probes=1 if result.consumed_surface_count > 0 else 0,
        nested_scroll_candidate_growth=1 if result.candidate_growth else 0,
        virtualized_list_detected=1 if result.virtualized_list_detected else 0,
        scroll_surface=result.scroll_surface,
    )


async def _browser_wait_for_settle(
    *,
    page: Any | None = None,
    delay_seconds: float = 1.0,
    timeout_seconds: float = 15.0,
) -> None:
    if page is None:
        await asyncio.sleep(delay_seconds)
        return
    max_attempts = max(1, int(timeout_seconds / delay_seconds))
    for _ in range(max_attempts):
        await asyncio.sleep(delay_seconds)
        try:
            payload = json.loads(
                await page.evaluate(_browser_inventory_settle_probe_script())
            )
        except Exception:
            continue
        ready_state = str(payload.get("readyState") or "").strip().lower()
        title = str(payload.get("title") or "").strip()
        anchor_count = int(payload.get("anchorCount") or 0)
        if ready_state == "complete" and (title or anchor_count > 0):
            return
