from __future__ import annotations

import logging
from urllib.parse import parse_qs, unquote, urlsplit

from src.contracts.browser_download import (
    PublisherDownloadRouteMemory,
    ReportDownloadRoutePlanRequest,
    ReportDownloadRoutePlanResponse,
    ReportDownloadRoutePlanStep,
)
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.report_download_route_planner")

_BROWSER_DISCOVERY_PROVENANCES = {
    "browser_dom",
    "browser_rendered_html_supplement",
}
_PDF_FIRST_DISCOVERY_PROVENANCES = {
    "direct_pdf_source",
}
_TRACKER_HOST_MARKERS = {
    "lnk",
    "trk",
    "click",
    "go",
    "email",
    "hubspot",
    "pardot",
    "marketo",
}
_LISTING_PATH_MARKERS = {
    "insights",
    "reports",
    "research",
    "resources",
    "publications",
    "library",
}
_EDITORIAL_NON_REPORT_MARKERS = {
    "blog",
    "news",
    "press",
    "case-study",
    "case_study",
    "webinar",
}
_EDITORIAL_REPORT_MARKERS = {
    "report",
    "reports",
    "insight",
    "insights",
    "research",
    "analysis",
    "study",
    "survey",
}
_EMAIL_GATE_PATH_MARKERS = {
    "gated-content-form",
    "download",
    "ebook",
    "whitepaper",
    "asset",
    "register",
    "form",
}
_ONSITE_LONGREAD_SEGMENTS = {
    "insight",
    "insights",
    "research",
    "analysis",
    "survey",
    "outlook",
}
_ONSITE_EXCLUDED_SEGMENTS = {
    "resources",
    "reports",
    "report",
    "download",
    "downloads",
    "ebook",
    "whitepaper",
    "whitepapers",
    "asset",
    "assets",
    "form",
    "register",
}
_TRACKER_QUERY_KEYS = (
    "url",
    "target",
    "dest",
    "destination",
    "redirect",
    "redirect_url",
    "redirect_uri",
    "u",
    "r",
)


def plan_report_download_routes(
    request: ReportDownloadRoutePlanRequest,
    ctx: RunContext,
) -> ReportDownloadRoutePlanResponse:
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_route_plan_start",
            module=logger.name,
            fields={
                "normalized_url": request.normalized_url,
                "has_remembered_route": request.remembered_route is not None,
                "has_candidate_trace": request.candidate_trace is not None,
                "publisher_discovery_route_kind": request.publisher_discovery_route_kind
                or "",
                "publisher_recommended_discovery_route_kind": (
                    request.publisher_recommended_discovery_route_kind or ""
                ),
            },
        )
    )
    response = _build_plan(request)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_route_plan_complete",
            module=logger.name,
            fields={
                "normalized_url": request.normalized_url,
                "planning_reason": response.planning_reason,
                "step_names": [step.step_name for step in response.steps],
                "route_families": [step.route_family for step in response.steps],
                "attempt_urls": [step.attempt_url or "" for step in response.steps],
            },
        )
    )
    return response


def _build_plan(
    request: ReportDownloadRoutePlanRequest,
) -> ReportDownloadRoutePlanResponse:
    steps: list[ReportDownloadRoutePlanStep] = []
    remembered_route = request.remembered_route
    candidate = request.candidate_trace
    candidate_pdf_url = str(candidate.pdf_url or "").strip() if candidate else ""
    source_page_urls = _clean_string_list(
        candidate.source_page_urls if candidate is not None else []
    )
    provenances = {
        str(value).strip().lower()
        for value in (candidate.discovery_provenances if candidate is not None else [])
        if str(value).strip()
    }
    recommended_route_kind = str(
        request.publisher_recommended_discovery_route_kind or ""
    ).strip()
    redirect_target_url = _extract_tracker_target_url(request.normalized_url)
    redirect_target_kind = _classify_redirect_target(redirect_target_url)

    if _should_reuse_memory_route(remembered_route):
        remembered_route_family = _canonical_memory_route_family(
            route_kind=remembered_route.route_kind,
            route_family=remembered_route.route_family,
        )
        steps.append(
            ReportDownloadRoutePlanStep(
                schema_version="1.0",
                step_name="report_download_with_memory_route",
                route_family=remembered_route_family,
                attempt_url=remembered_route.resolved_target_url or None,
                route_hint=remembered_route.route_summary,
                route_step_hints=list(remembered_route.route_steps),
                route_kind_hint=remembered_route.route_kind,
                uses_memory_route=True,
                fallback_on_retryable_error=True,
            )
        )

    if candidate_pdf_url:
        steps.append(
            ReportDownloadRoutePlanStep(
                schema_version="1.0",
                step_name="report_download_candidate_pdf_probe",
                route_family="direct_pdf_probe",
                attempt_url=candidate_pdf_url,
                route_kind_hint="pdf_download",
                uses_memory_route=False,
                fallback_on_retryable_error=True,
            )
        )
    elif redirect_target_url and _looks_like_pdf(redirect_target_url):
        steps.append(
            ReportDownloadRoutePlanStep(
                schema_version="1.0",
                step_name="report_download_redirect_pdf_probe",
                route_family="direct_pdf_probe",
                attempt_url=redirect_target_url,
                route_kind_hint="pdf_download",
                uses_memory_route=False,
                fallback_on_retryable_error=True,
            )
        )
    elif _looks_like_pdf(request.normalized_url):
        steps.append(
            ReportDownloadRoutePlanStep(
                schema_version="1.0",
                step_name="report_download_direct_pdf_probe",
                route_family="direct_pdf_probe",
                attempt_url=request.normalized_url,
                route_kind_hint="pdf_download",
                uses_memory_route=False,
                fallback_on_retryable_error=True,
            )
        )

    browser_step = _build_browser_step(
        normalized_url=request.normalized_url,
        source_page_urls=source_page_urls,
        provenances=provenances,
        redirect_target_url=redirect_target_url,
        redirect_target_kind=redirect_target_kind,
        remembered_route=remembered_route,
    )
    http_step = ReportDownloadRoutePlanStep(
        schema_version="1.0",
        step_name="report_download_http_probe",
        route_family="http_pdf_probe",
        attempt_url=request.normalized_url,
        route_kind_hint="pdf_download",
        uses_memory_route=False,
        fallback_on_retryable_error=True,
    )

    browser_first = (
        recommended_route_kind == "browser_render"
        or bool(provenances & _BROWSER_DISCOVERY_PROVENANCES)
    )
    pdf_first = (
        recommended_route_kind == "http_parse"
        or bool(provenances & _PDF_FIRST_DISCOVERY_PROVENANCES)
    )
    if browser_first and not pdf_first:
        steps.append(browser_step)
        steps.append(http_step)
    else:
        steps.append(http_step)
        steps.append(browser_step)

    deduped_steps = _dedupe_steps(steps)
    planning_reason = _planning_reason(
        remembered_route=remembered_route,
        candidate_pdf_url=candidate_pdf_url,
        browser_first=browser_first,
        source_page_urls=source_page_urls,
    )
    return ReportDownloadRoutePlanResponse(
        schema_version="1.0",
        steps=deduped_steps,
        planning_reason=planning_reason,
    )


def _build_browser_step(
    *,
    normalized_url: str,
    source_page_urls: list[str],
    provenances: set[str],
    redirect_target_url: str | None,
    redirect_target_kind: str,
    remembered_route: PublisherDownloadRouteMemory | None,
) -> ReportDownloadRoutePlanStep:
    source_page_url = source_page_urls[0] if source_page_urls else None
    remembered_route_kind = str(
        remembered_route.route_kind if remembered_route is not None else ""
    ).strip()
    remembered_route_hint = (
        str(remembered_route.route_summary or "").strip()
        if remembered_route is not None
        else ""
    )
    remembered_route_step_hints = (
        list(remembered_route.route_steps)
        if remembered_route is not None
        and str(remembered_route.outcome or "").strip().lower()
        in {"downloaded", "email_requested", "captured"}
        else []
    )
    remembered_route_family = _canonical_memory_route_family(
        route_kind=remembered_route_kind,
        route_family=remembered_route.route_family if remembered_route is not None else "",
    )
    if _looks_like_tracker_url(normalized_url):
        if redirect_target_kind == "redirect_to_email_gate":
            return ReportDownloadRoutePlanStep(
                schema_version="1.0",
                step_name="report_download_browser_email_form",
                route_family="browser_email_form",
                attempt_url=redirect_target_url or source_page_url or normalized_url,
                route_kind_hint="email_delivery",
                source_page_url_hint=source_page_url,
                uses_memory_route=False,
                fallback_on_retryable_error=False,
            )
        if redirect_target_kind == "redirect_to_onsite_report":
            return ReportDownloadRoutePlanStep(
                schema_version="1.0",
                step_name="report_download_browser_onsite_report",
                route_family="browser_onsite_report",
                attempt_url=redirect_target_url or normalized_url,
                route_kind_hint="onsite_report",
                source_page_url_hint=source_page_url,
                uses_memory_route=False,
                fallback_on_retryable_error=False,
            )
        if redirect_target_kind == "redirect_to_non_report" and source_page_url:
            return ReportDownloadRoutePlanStep(
                schema_version="1.0",
                step_name="report_download_browser_listing_hub",
                route_family="browser_listing_hub",
                attempt_url=source_page_url,
                route_kind_hint=None,
                source_page_url_hint=source_page_url,
                uses_memory_route=False,
                fallback_on_retryable_error=False,
            )
        return ReportDownloadRoutePlanStep(
            schema_version="1.0",
            step_name="report_download_browser_tracker_redirect",
            route_family="browser_tracker_redirect",
            attempt_url=source_page_url or redirect_target_url or normalized_url,
            route_kind_hint=None,
            source_page_url_hint=source_page_url,
            uses_memory_route=False,
            fallback_on_retryable_error=False,
        )
    if source_page_url and _looks_like_listing_url(normalized_url):
        return ReportDownloadRoutePlanStep(
            schema_version="1.0",
            step_name="report_download_browser_listing_hub",
            route_family="browser_listing_hub",
            attempt_url=source_page_url,
            route_kind_hint=None,
            source_page_url_hint=source_page_url,
            uses_memory_route=False,
            fallback_on_retryable_error=False,
        )
    if remembered_route_kind == "email_delivery" or remembered_route_family == "browser_email_form":
        return ReportDownloadRoutePlanStep(
            schema_version="1.0",
            step_name="report_download_browser_email_form",
            route_family="browser_email_form",
            attempt_url=normalized_url,
            route_hint=remembered_route_hint or None,
            route_step_hints=remembered_route_step_hints,
            route_kind_hint="email_delivery",
            source_page_url_hint=source_page_url,
            uses_memory_route=False,
            fallback_on_retryable_error=False,
        )
    if (
        source_page_url
        and str(source_page_url).strip() != str(normalized_url).strip()
        and not _looks_like_listing_url(normalized_url)
    ):
        return ReportDownloadRoutePlanStep(
            schema_version="1.0",
            step_name="report_download_browser_candidate",
            route_family="browser_pdf_click",
            attempt_url=normalized_url,
            route_kind_hint=None,
            source_page_url_hint=source_page_url,
            uses_memory_route=False,
            fallback_on_retryable_error=False,
        )
    if _looks_like_onsite_longread_url(redirect_target_url or normalized_url):
        return ReportDownloadRoutePlanStep(
            schema_version="1.0",
            step_name="report_download_browser_onsite_report",
            route_family="browser_onsite_report",
            attempt_url=redirect_target_url or normalized_url,
            route_kind_hint="onsite_report",
            source_page_url_hint=source_page_url,
            uses_memory_route=False,
            fallback_on_retryable_error=False,
        )
    if provenances & _BROWSER_DISCOVERY_PROVENANCES:
        return ReportDownloadRoutePlanStep(
            schema_version="1.0",
            step_name="report_download_browser_candidate",
            route_family="browser_pdf_click",
            attempt_url=normalized_url,
            route_kind_hint=None,
            source_page_url_hint=source_page_url,
            uses_memory_route=False,
            fallback_on_retryable_error=False,
        )
    return ReportDownloadRoutePlanStep(
        schema_version="1.0",
        step_name="report_download_browser_candidate",
        route_family="browser_pdf_click",
        attempt_url=normalized_url,
        route_kind_hint=None,
        source_page_url_hint=source_page_url,
        uses_memory_route=False,
        fallback_on_retryable_error=False,
    )


def _planning_reason(
    *,
    remembered_route: PublisherDownloadRouteMemory | None,
    candidate_pdf_url: str,
    browser_first: bool,
    source_page_urls: list[str],
) -> str:
    if _should_reuse_memory_route(remembered_route):
        if candidate_pdf_url:
            return (
                "Reuse the verified remembered route first, then verify the discovery-provided candidate PDF before broader fallback."
            )
        return (
            "Reuse the verified remembered route first, then fall back to discovery-aware HTTP and browser attempts only on retryable failure."
        )
    if candidate_pdf_url:
        return (
            "The discovery phase already exposed a candidate PDF URL, so verify that target before broader HTTP or browser exploration."
        )
    if browser_first and source_page_urls:
        return (
            "Discovery evidence points to a browser-derived route from a source page, so revisit that page before generic PDF probing."
        )
    if browser_first:
        return (
            "Discovery evidence points to a browser-derived route, so prefer browser execution before generic PDF probing."
        )
    return (
        "No verified remembered route is available, so start with discovery-aware PDF probing before falling back to browser execution."
    )


def _default_route_family_for_kind(route_kind: str) -> str:
    if str(route_kind or "").strip() == "onsite_report":
        return "browser_onsite_report"
    if str(route_kind or "").strip() == "email_delivery":
        return "browser_email_form"
    return "browser_pdf_click"


def _should_reuse_memory_route(
    remembered_route: PublisherDownloadRouteMemory | None,
) -> bool:
    if remembered_route is None:
        return False
    if remembered_route.route_status != "verified":
        return False
    if remembered_route.outcome not in {"downloaded", "email_requested", "captured"}:
        return False
    if (
        remembered_route.route_kind == "onsite_report"
        and str(remembered_route.onsite_completeness_status or "").strip().lower()
        != "complete"
    ):
        return False
    route_family = _canonical_memory_route_family(
        route_kind=remembered_route.route_kind,
        route_family=remembered_route.route_family,
    )
    if (
        not remembered_route.browser_had_structured_result
        and route_family not in {"direct_pdf_probe", "http_pdf_probe"}
    ):
        return False
    minimum_confidence = 0.5
    if route_family in {"direct_pdf_probe", "http_pdf_probe"}:
        minimum_confidence = 0.35
    elif remembered_route.route_kind == "email_delivery":
        minimum_confidence = 0.45
    elif remembered_route.route_kind == "onsite_report":
        minimum_confidence = 0.6
    if remembered_route.confidence_score < minimum_confidence:
        return False
    required_successes = 1 if route_family in {"direct_pdf_probe", "http_pdf_probe", "browser_email_form"} else 2
    if remembered_route.verified_successes >= required_successes:
        return True
    return remembered_route.confidence_score >= 0.75 and remembered_route.verified_successes >= 1


def _canonical_memory_route_family(*, route_kind: str, route_family: str) -> str:
    token = str(route_family or "").strip()
    if route_kind == "email_delivery" and token in {
        "",
        "browser_pdf_click",
        "browser_pdf_download",
    }:
        return "browser_email_form"
    if route_kind == "onsite_report" and token in {
        "",
        "browser_pdf_click",
        "browser_pdf_download",
    }:
        return "browser_onsite_report"
    if not token:
        return _default_route_family_for_kind(route_kind)
    return token


def _dedupe_steps(
    steps: list[ReportDownloadRoutePlanStep],
) -> list[ReportDownloadRoutePlanStep]:
    deduped: list[ReportDownloadRoutePlanStep] = []
    seen: set[tuple[str, str, str, str]] = set()
    for step in steps:
        key = (
            step.step_name,
            step.route_family,
            str(step.attempt_url or "").strip(),
            str(step.source_page_url_hint or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(step)
    return deduped


def _clean_string_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value or "").strip()
        if not token:
            continue
        marker = token.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        cleaned.append(token)
    return cleaned


def _looks_like_pdf(url: str) -> bool:
    return str(urlsplit(str(url or "").strip()).path or "").strip().lower().endswith(
        ".pdf"
    )


def _looks_like_listing_url(url: str) -> bool:
    path = str(urlsplit(str(url or "").strip()).path or "").strip().lower()
    if not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False

    def is_listing_segment(segment: str) -> bool:
        return any(marker in segment for marker in _LISTING_PATH_MARKERS)

    if not any(is_listing_segment(segment) for segment in segments):
        return False
    last_segment = segments[-1]
    if len(segments) == 1:
        return is_listing_segment(last_segment)
    if is_listing_segment(last_segment):
        return True
    if len(segments) == 2 and is_listing_segment(segments[0]):
        slug_token_count = len([token for token in last_segment.split("-") if token])
        return slug_token_count < 4
    return False


def _looks_like_tracker_url(url: str) -> bool:
    parsed = urlsplit(str(url or "").strip())
    hostname = str(parsed.hostname or "").strip().lower()
    path = str(parsed.path or "").strip().lower()
    query = str(parsed.query or "").strip().lower()
    return any(marker in hostname for marker in _TRACKER_HOST_MARKERS) or any(
        marker in path or marker in query for marker in _TRACKER_HOST_MARKERS
    )


def _extract_tracker_target_url(url: str) -> str | None:
    parsed = urlsplit(str(url or "").strip())
    if not parsed.query:
        return None
    query = parse_qs(parsed.query, keep_blank_values=False)
    for key in _TRACKER_QUERY_KEYS:
        values = query.get(key)
        if not values:
            continue
        candidate = unquote(str(values[0] or "").strip())
        if candidate.startswith("http://") or candidate.startswith("https://"):
            return candidate
    return None


def _classify_redirect_target(url: str | None) -> str:
    token = str(url or "").strip()
    if not token:
        return ""
    if _looks_like_pdf(token):
        return "redirect_to_pdf"
    if _looks_like_onsite_longread_url(token):
        return "redirect_to_onsite_report"
    lowered = str(urlsplit(token).path or "").strip().lower()
    if any(marker in lowered for marker in _EMAIL_GATE_PATH_MARKERS):
        return "redirect_to_email_gate"
    if any(marker in lowered for marker in _EDITORIAL_NON_REPORT_MARKERS):
        return "redirect_to_non_report"
    return ""


def _looks_like_editorial_report_url(url: str | None) -> bool:
    path = str(urlsplit(str(url or "").strip()).path or "").strip().lower()
    if not path or _looks_like_pdf(path):
        return False
    if any(marker in path for marker in _EDITORIAL_NON_REPORT_MARKERS):
        return False
    return any(marker in path for marker in _EDITORIAL_REPORT_MARKERS)


def _looks_like_onsite_longread_url(url: str | None) -> bool:
    parsed = urlsplit(str(url or "").strip())
    path = str(parsed.path or "").strip().lower()
    if not path or _looks_like_pdf(path):
        return False
    if any(marker in path for marker in _EDITORIAL_NON_REPORT_MARKERS):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    if any(segment in _ONSITE_EXCLUDED_SEGMENTS for segment in segments):
        return False
    if any(segment in _ONSITE_LONGREAD_SEGMENTS for segment in segments):
        return True
    return any(marker in path for marker in _EDITORIAL_REPORT_MARKERS)
