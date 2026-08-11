from __future__ import annotations

"""Coordinator for publisher-inventory discovery routes.

The public service boundary remains src.services.publisher_inventory_service.
This module coordinates route selection, direct responses, HTTP/browser handoff,
validation, runtime loading, and internal compatibility exports.
"""

import asyncio
import json
import logging
import os
import re
import sys
from hashlib import sha1
from importlib import import_module
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.publisher_inventory import (
    PublisherInventoryLandingPageInspectionRequest,
    PublisherInventoryLandingPageInspectionResponse,
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
    PublisherInventoryRouteTrace,
    PublisherInventoryScenarioSummary,
    PublisherInventoryServiceRequest,
    PublisherInventoryServiceResponse,
)
from src.contracts.run_context import RunContext
from src.services._http_acquisition import execute_http_acquisition
from src.services._publisher_inventory_service.browser_flow import (
    _HTTP_SUPPLEMENT_HTML_MAX_BYTES,
    _apply_report_filter,
    _browser_wait_for_settle,
    _click_archive_expander,
    _click_load_more,
    _click_pagination_next,
    _click_tab,
    _close_unexpected_blank_pages,
    _collect_browser_inventory_pages,
    _dismiss_cookie_banner,
    _extract_browser_http_supplement_candidates,
    _extract_rendered_html_supplement_candidates,
    _extract_rendered_inventory_state,
    _is_browser_placeholder_page_url,
    _page_target_id,
    _prime_browser_inventory_surface,
    _record_browser_scroll_probe_metrics,
    _reset_empty_results_filters,
    _run_browser_traversal,
    _run_browser_traversal_with_timeout,
    _seed_initial_browser_page,
    _wait_for_inventory_growth,
    _wait_for_inventory_growth_probe,
    _wait_for_inventory_transition,
    _wait_for_tab_activation,
)
from src.services._publisher_inventory_service.browser_service import (
    BrowserInventoryAcquisitionDependencies,
    discover_inventory_via_browser,
)
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
    _browser_named_control_selector,
    _browser_nested_scroll_probe_script,
    _browser_rendered_html_script,
    _browser_scroll_to_ratio_script,
)
from src.services._publisher_inventory_service.browser_traversal_state import (
    _BrowserScrollProbeResult,
    _BrowserTraversalMetrics,
    _RenderedInventoryState,
    _build_browser_route_trace,
    _browser_scroll_probe_result_from_payload,
    _increment_browser_traversal_metrics,
    _new_browser_traversal_metrics,
    _rendered_inventory_state_from_payload,
)
from src.services._publisher_inventory_service.discovery_activity import (
    _build_browser_route_summary,
    _candidate_url_signature,
    _extract_component_link_anchors,
    _extract_candidates_from_html,
    _fallback_title_from_url,
    _is_archive_surface,
    _is_exhausted_inert_load_more,
    _is_terminal_results_page,
    _needs_additional_hydration,
    _normalize_absolute_url,
    _normalize_text,
    _positive_int_or_none,
    _rendered_state_anchor_fingerprint,
    _requires_archive_surface_recovery,
    _requires_origin_host_recovery,
    _resolve_next_page_url,
    _select_anchor_title,
    _select_tab_labels_for_traversal,
    _should_apply_report_filter,
    _should_expand_archive_library,
    _should_follow_report_listing,
)
from src.services._publisher_inventory_service.fetch_service import (
    HTTP_BROWSER_HEADERS,
    _InventoryHtmlParser,
    discover_inventory_via_http,
    inspect_inventory_landing_pages,
)
from src.services._publisher_inventory_service.preflight import (
    _ARCHIVE_URL_MARKERS,
    _DIRECT_DETAIL_URL_MARKERS,
    _DOWNLOAD_HINT_MARKERS,
    _FILTER_HINT_MARKERS,
    _PREFLIGHT_COLLECTION_ROOT_TOKENS,
    _PREFLIGHT_HTML_MAX_BYTES,
    _build_scenario_summary,
    _classify_preflight_scenario,
    _looks_like_preflight_direct_detail_path,
    _looks_like_preflight_filter_route,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_service")


_ROUTE_KINDS = {"http_parse", "browser_render"}


def discover_publisher_inventory(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
) -> PublisherInventoryServiceResponse:
    normalized_url = _validate_and_normalize_url(request.insights_url)
    _validate_request(request, normalized_url)
    scenario_summary = (
        _classify_preflight_scenario(
            request=request, normalized_url=normalized_url, ctx=ctx
        )
        if request.settings.enable_preflight_classifier_and_direct_detail
        else None
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_discovery_start",
            module=logger.name,
            fields={
                "source_url": request.insights_url,
                "normalized_url": normalized_url,
                "route_kind_hint": request.route_kind_hint or "",
                "has_route_hint": bool(request.route_hint),
                "pagination_max_pages": request.settings.pagination_max_pages,
                "http_timeout_seconds": request.settings.http_timeout_seconds,
                "model": request.settings.model,
                "timeout_seconds": request.settings.timeout_seconds,
                "max_steps": request.settings.max_steps,
                "headed": request.settings.headed,
                "force_browser": request.settings.force_browser,
                "scenario_class": (
                    scenario_summary.scenario_class
                    if scenario_summary is not None
                    else ""
                ),
            },
        )
    )
    if normalized_url.lower().endswith(".pdf"):
        return _discover_direct_pdf_source(request, ctx, normalized_url)
    if (
        scenario_summary is not None
        and scenario_summary.direct_detail_eligible
        and scenario_summary.scenario_class == "direct_detail_html"
    ):
        return _discover_direct_detail_source(
            request,
            ctx,
            normalized_url,
            scenario_summary=scenario_summary,
        )
    if request.settings.force_browser:
        return _discover_with_browser(
            request,
            ctx,
            normalized_url,
            use_hint=bool(request.route_hint),
            scenario_summary=scenario_summary,
        )
    hinted_route = str(request.route_kind_hint or "").strip()
    if hinted_route:
        _validate_route_kind(hinted_route)
        if hinted_route == "http_parse":
            return _discover_with_http(
                request,
                ctx,
                normalized_url,
                use_hint=True,
                scenario_summary=scenario_summary,
            )
        return _discover_with_browser(
            request,
            ctx,
            normalized_url,
            use_hint=True,
            scenario_summary=scenario_summary,
        )

    try:
        return _discover_with_http(
            request,
            ctx,
            normalized_url,
            use_hint=False,
            scenario_summary=scenario_summary,
        )
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_http_fallback",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "error": exc.message,
                    "code": exc.code,
                },
            )
        )
    return _discover_with_browser(
        request,
        ctx,
        normalized_url,
        use_hint=False,
        scenario_summary=scenario_summary,
    )


def inspect_publisher_inventory_landing_pages(
    request: PublisherInventoryLandingPageInspectionRequest,
    ctx: RunContext,
) -> PublisherInventoryLandingPageInspectionResponse:
    return inspect_inventory_landing_pages(
        request,
        ctx,
        requests_module=requests,
    )


def _discover_direct_pdf_source(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
) -> PublisherInventoryServiceResponse:
    candidate = PublisherInventoryRawCandidate(
        schema_version="1.0",
        url=normalized_url,
        title=_fallback_title_from_url(normalized_url),
        source_page_url=normalized_url,
        discovered_on_page_number=1,
        pdf_url=normalized_url,
        published_at_text=None,
        provenance="direct_pdf_source",
        confidence=1.0,
    )
    response = PublisherInventoryServiceResponse(
        schema_version="1.0",
        source_url=request.insights_url,
        normalized_url=normalized_url,
        route_kind="http_parse",
        route_summary="Treated the direct PDF URL as a single-item inventory source.",
        final_page_url=normalized_url,
        used_route_hint=False,
        pages=[
            PublisherInventoryPage(
                schema_version="1.0",
                page_number=1,
                page_url=normalized_url,
            )
        ],
        candidates=[candidate],
        scenario_summary=_build_scenario_summary(
            scenario_class="direct_pdf",
            source_surface_class="direct_detail",
            confidence=1.0,
            direct_detail_eligible=True,
            browser_preferred=False,
            notes="The source URL resolved directly to a PDF document.",
        ),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_direct_pdf_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "candidate_url": candidate.url,
            },
        )
    )
    return response


def _discover_direct_detail_source(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
    *,
    scenario_summary: PublisherInventoryScenarioSummary,
) -> PublisherInventoryServiceResponse:
    candidate = PublisherInventoryRawCandidate(
        schema_version="1.0",
        url=normalized_url,
        title=_fallback_title_from_url(normalized_url),
        source_page_url=normalized_url,
        discovered_on_page_number=1,
        pdf_url=None,
        published_at_text=None,
        provenance="direct_detail_source",
        confidence=max(float(scenario_summary.confidence), 0.85),
    )
    response = PublisherInventoryServiceResponse(
        schema_version="1.0",
        source_url=request.insights_url,
        normalized_url=normalized_url,
        route_kind="http_parse",
        route_summary="Short-circuited a high-confidence direct-detail report page without archive traversal.",
        final_page_url=normalized_url,
        used_route_hint=False,
        pages=[
            PublisherInventoryPage(
                schema_version="1.0",
                page_number=1,
                page_url=normalized_url,
            )
        ],
        candidates=[candidate],
        scenario_summary=scenario_summary,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_direct_detail_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "scenario_class": scenario_summary.scenario_class,
            },
        )
    )
    return response


def _discover_with_http(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
    *,
    use_hint: bool,
    scenario_summary: PublisherInventoryScenarioSummary | None,
) -> PublisherInventoryServiceResponse:
    return discover_inventory_via_http(
        request,
        ctx,
        normalized_url,
        use_hint=use_hint,
        scenario_summary=scenario_summary,
        requests_module=requests,
    )


def _discover_with_browser(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
    *,
    use_hint: bool,
    scenario_summary: PublisherInventoryScenarioSummary | None,
) -> PublisherInventoryServiceResponse:
    return discover_inventory_via_browser(
        request,
        ctx,
        normalized_url,
        use_hint=use_hint,
        scenario_summary=scenario_summary,
        dependencies=BrowserInventoryAcquisitionDependencies(
            asyncio_module=asyncio,
            prepare_session_dir=lambda root_dir, url: _prepare_session_dir(
                root_dir=root_dir,
                normalized_url=url,
            ),
            load_browser_use_runtime=_load_browser_use_runtime,
            run_browser_traversal=lambda browser, req, run_ctx, url: (
                _run_browser_traversal_with_timeout(
                    browser=browser,
                    request=req,
                    ctx=run_ctx,
                    normalized_url=url,
                )
            ),
            extract_http_supplement=lambda req, page, url, run_ctx: (
                _extract_browser_http_supplement_candidates(
                    request=req,
                    page=page,
                    normalized_url=url,
                    ctx=run_ctx,
                )
            ),
            fallback_http_discovery=lambda req, run_ctx, url, hint: _discover_with_http(
                req,
                run_ctx,
                url,
                use_hint=hint,
                scenario_summary=None,
            ),
            kill_browser=_kill_browser,
            candidate_provenance_counts=_candidate_provenance_counts,
        ),
    )


def _candidate_provenance_counts(
    candidates: list[PublisherInventoryRawCandidate],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        provenance = str(candidate.provenance or "unknown").strip() or "unknown"
        counts[provenance] = counts.get(provenance, 0) + 1
    return counts


def _validate_request(
    request: PublisherInventoryServiceRequest,
    normalized_url: str,
) -> None:
    if not normalized_url:
        raise AppError(
            code="publisher_inventory_url_invalid",
            message="A valid absolute insights URL is required for publisher inventory discovery",
            retryable=False,
        )
    if not request.settings.openrouter_api_key.strip():
        raise AppError(
            code="publisher_inventory_api_key_missing",
            message="OPENROUTER_API_KEY is required for publisher inventory discovery",
            retryable=False,
        )
    if not request.settings.model.strip():
        raise AppError(
            code="publisher_inventory_model_missing",
            message="A publisher inventory discovery model must be configured",
            retryable=False,
        )
    if request.settings.pagination_max_pages <= 0:
        raise AppError(
            code="publisher_inventory_pagination_limit_invalid",
            message="pagination_max_pages must be at least 1",
            retryable=False,
        )


def _validate_route_kind(route_kind: str) -> None:
    if str(route_kind or "").strip() not in _ROUTE_KINDS:
        raise AppError(
            code="publisher_inventory_route_kind_invalid",
            message="publisher inventory discovery returned an unsupported route kind",
            retryable=True,
            context={"route_kind": route_kind},
        )


def _validate_and_normalize_url(url: str) -> str:
    normalized = _normalize_absolute_url(url)
    return normalized


def _prepare_session_dir(*, root_dir: str, normalized_url: str) -> Path:
    root = Path(root_dir).expanduser().resolve()
    host = urlsplit(normalized_url).netloc.replace(":", "_") or "unknown_host"
    url_hash = sha1(normalized_url.encode("utf-8")).hexdigest()[:12]
    path = (root / host / url_hash).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_browser_use_runtime(normalized_url: str) -> Any:
    os.environ.setdefault("BROWSER_USE_SETUP_LOGGING", "false")
    vendored_root = (
        Path(__file__).resolve().parents[3] / "tools" / "browser-use"
    ).resolve()
    load_errors: list[tuple[str, Exception]] = []
    for import_mode, extra_path in (
        ("direct", None),
        ("vendored", vendored_root),
    ):
        if extra_path is not None:
            extra_path_str = str(extra_path)
            if extra_path_str not in sys.path:
                sys.path.insert(0, extra_path_str)
        try:
            return import_module("browser_use")
        except Exception as exc:
            load_errors.append((import_mode, exc))

    final_mode, final_error = load_errors[-1]
    missing_dependency = (
        final_error.name if isinstance(final_error, ModuleNotFoundError) else ""
    )
    raise AppError(
        code="browser_use_unavailable",
        message=(
            "The local browser_use runtime is not available in the active Python interpreter. "
            "Run publisher discovery from the project virtualenv or install the vendored browser-use dependencies."
        ),
        cause=final_error,
        retryable=False,
        context={
            "normalized_url": normalized_url,
            "current_python": sys.executable,
            "vendored_root": str(vendored_root),
            "attempted_import_modes": [mode for mode, _ in load_errors],
            "final_import_mode": final_mode,
            "missing_dependency": missing_dependency,
        },
    ) from final_error


def _kill_browser(
    browser: Any,
    ctx: RunContext,
    *,
    timeout_seconds: float = 5.0,
) -> None:
    async def _kill_with_timeout() -> None:
        await asyncio.wait_for(
            browser.kill(),
            timeout=max(float(timeout_seconds), 0.1),
        )

    try:
        asyncio.run(_kill_with_timeout())
    except Exception:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_kill_failed",
                module=logger.name,
                fields={},
            )
        )


__all__ = [name for name in globals() if not name.startswith("__")]
