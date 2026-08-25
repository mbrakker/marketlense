from __future__ import annotations

import logging
import re
from dataclasses import replace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.contracts.browser_download import (
    BrowserDownloadRouteStep,
    PublisherDownloadRouteMemory,
    PublisherDownloadRoutePolicySignal,
    ReportDownloadRoutePlanRequest,
    ReportDownloadRoutePlanResponse,
    ReportDownloadRoutePlanStep,
)
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

from .policy import (
    _apply_policy_route_family,
    _canonical_memory_route_family,
    _has_actionable_email_memory_hint,
    _preferred_policy_signal,
    _preferred_publisher_policy_signal,
    _should_reuse_memory_route,
)
from .recovery import (
    _annotate_recovery_steps,
    _browser_to_http_recovery_decision,
    _dedupe_steps,
)
from .url_rules import (
    _classify_redirect_target,
    _clean_string_list,
    _extract_tracker_target_url,
    _looks_like_direct_onsite_report_url,
    _looks_like_email_form_url,
    _looks_like_listing_url,
    _looks_like_onsite_longread_url,
    _looks_like_pdf,
    _looks_like_tracker_url,
    _onsite_capture_route_steps,
)

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
_TRACKER_SHORT_PATH_MARKERS = {
    "go",
    "lnk",
    "trk",
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
    "guide",
    "guides",
    "insight",
    "insights",
    "playbook",
    "research",
    "analysis",
    "study",
    "survey",
    "trend",
    "trends",
    "whitepaper",
    "whitepapers",
}
_BROWSER_TO_HTTP_RECOVERY_CLASS = "browser_to_http_pdf_probe"
_DIRECT_PDF_RECOVERY_CLASS = "direct_pdf_probe"
_HTTP_PDF_RECOVERY_CLASS = "http_pdf_probe"
_REPORT_DETAIL_SIGNAL_MARKERS = {
    "benchmark",
    "download",
    "ebook",
    "e-book",
    "guide",
    "market",
    "outlook",
    "playbook",
    "predictions",
    "report",
    "research",
    "study",
    "survey",
    "trend",
    "trends",
    "whitepaper",
    "white paper",
}
_EMAIL_GATE_PATH_MARKERS = {
    "gated-content-form",
    "download",
    "downloads",
    "ebook",
    "ebooks",
    "whitepaper",
    "whitepapers",
    "asset",
    "assets",
    "register",
    "form",
}
_EMAIL_GATE_PARENT_SEGMENTS = {
    "report",
    "reports",
    "resources",
}
_EMAIL_GATE_DETAIL_TITLE_MARKERS = {
    "benchmark",
    "ebook",
    "e-book",
    "guide",
    "outlook",
    "predictions",
    "report",
    "research",
    "study",
    "trends",
    "whitepaper",
    "white paper",
}
_ONSITE_LONGREAD_SEGMENTS = {
    "insight",
    "insights",
    "research",
    "analysis",
    "survey",
    "outlook",
}
_DIRECT_ONSITE_REPORT_SEGMENTS = {
    "guide",
    "guides",
    "insight",
    "playbook",
    "playbooks",
    "research",
    "analysis",
    "survey",
    "outlook",
}
_DIRECT_ONSITE_REPORT_PATH_PHRASES = {
    "year-in-review",
}
_DIRECT_ONSITE_DIGITAL_YEAR_SEGMENT_RX = re.compile(
    r"^(?:digital|global-digital)-20\d{2}(?:-|$)"
)
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
_EMAIL_QUERY_KEYS = {"email", "e-mail"}


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
                "recovery_classes": [
                    step.recovery_class or step.route_family for step in response.steps
                ],
                "recovery_decisions": [
                    step.recovery_decision for step in response.steps
                ],
                "blocked_recovery_classes": list(response.blocked_recovery_classes),
                "route_policy_order": [
                    signal.route_family
                    for signal in (
                        request.remembered_route.route_policy
                        if request.remembered_route is not None
                        else []
                    )
                ],
                "publisher_route_policy_order": [
                    signal.route_family
                    for signal in (
                        request.remembered_route.publisher_route_policy
                        if request.remembered_route is not None
                        else []
                    )
                ],
            },
        )
    )
    if response.blocked_recovery_classes:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_recovery_policy_blocked",
                module=logger.name,
                fields={
                    "normalized_url": request.normalized_url,
                    "blocked_recovery_classes": list(response.blocked_recovery_classes),
                },
            )
        )
    return response


def _build_plan(
    request: ReportDownloadRoutePlanRequest,
) -> ReportDownloadRoutePlanResponse:
    steps: list[ReportDownloadRoutePlanStep] = []
    blocked_recovery_classes: list[str] = []
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
    policy_signal = _preferred_policy_signal(remembered_route)
    policy_scope = "exact_url" if policy_signal is not None else ""
    if policy_signal is None:
        policy_signal = _preferred_publisher_policy_signal(
            remembered_route=remembered_route,
            normalized_url=request.normalized_url,
            candidate=candidate,
        )
        policy_scope = "publisher_scope" if policy_signal is not None else ""
    policy_route_family = policy_signal.route_family if policy_signal else ""
    redirect_target_url = _extract_tracker_target_url(request.normalized_url)
    redirect_target_kind = _classify_redirect_target(redirect_target_url)

    direct_pdf_request = _looks_like_pdf(request.normalized_url)

    if (
        remembered_route is not None
        and _should_reuse_memory_route(remembered_route)
        and not direct_pdf_request
    ):
        remembered_route_family = _canonical_memory_route_family(
            route_kind=remembered_route.route_kind,
            route_family=remembered_route.route_family,
        )
        remembered_attempt_url = _remembered_attempt_url(
            normalized_url=request.normalized_url,
            remembered_route=remembered_route,
            remembered_route_family=remembered_route_family,
            delivery_email=request.delivery_email,
        )
        steps.append(
            ReportDownloadRoutePlanStep(
                schema_version="1.0",
                step_name="report_download_with_memory_route",
                route_family=remembered_route_family,
                attempt_url=remembered_attempt_url or None,
                route_hint=remembered_route.route_summary,
                route_step_hints=_memory_route_step_hints(
                    remembered_route=remembered_route,
                    route_family=remembered_route_family,
                ),
                route_kind_hint=remembered_route.route_kind,
                uses_memory_route=True,
                fallback_on_retryable_error=True,
                recovery_class=remembered_route_family,
                recovery_decision="primary",
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
                recovery_class=_DIRECT_PDF_RECOVERY_CLASS,
                recovery_decision="primary",
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
                recovery_class=_DIRECT_PDF_RECOVERY_CLASS,
                recovery_decision="primary",
            )
        )
    elif direct_pdf_request:
        steps.append(
            ReportDownloadRoutePlanStep(
                schema_version="1.0",
                step_name="report_download_direct_pdf_probe",
                route_family="direct_pdf_probe",
                attempt_url=request.normalized_url,
                route_kind_hint="pdf_download",
                uses_memory_route=False,
                fallback_on_retryable_error=True,
                recovery_class=_DIRECT_PDF_RECOVERY_CLASS,
                recovery_decision="primary",
            )
        )

    browser_step = _build_browser_step(
        normalized_url=request.normalized_url,
        source_page_urls=source_page_urls,
        candidate_title=str(candidate.title or "") if candidate is not None else "",
        provenances=provenances,
        redirect_target_url=redirect_target_url,
        redirect_target_kind=redirect_target_kind,
        remembered_route=remembered_route,
    )
    if policy_route_family.startswith("browser_"):
        browser_step = _apply_policy_route_family(
            browser_step,
            policy_signal=policy_signal,
        )
    http_step = ReportDownloadRoutePlanStep(
        schema_version="1.0",
        step_name="report_download_http_probe",
        route_family="http_pdf_probe",
        attempt_url=request.normalized_url,
        route_kind_hint="pdf_download",
        uses_memory_route=False,
        fallback_on_retryable_error=True,
        recovery_class=_HTTP_PDF_RECOVERY_CLASS,
        recovery_decision="primary",
    )

    browser_first = recommended_route_kind == "browser_render" or bool(
        provenances & _BROWSER_DISCOVERY_PROVENANCES
    )
    pdf_first = recommended_route_kind == "http_parse" or bool(
        provenances & _PDF_FIRST_DISCOVERY_PROVENANCES
    )
    if policy_route_family in {"direct_pdf_probe", "http_pdf_probe"}:
        browser_first = False
        pdf_first = True
    elif policy_route_family.startswith("browser_"):
        browser_first = True
        pdf_first = False
    policy_prefers_pdf_probe = policy_route_family in {
        "direct_pdf_probe",
        "http_pdf_probe",
    }
    browser_step_is_email_delivery = browser_step.route_kind_hint == "email_delivery"
    if browser_step_is_email_delivery and not policy_prefers_pdf_probe:
        steps.append(browser_step)
    elif browser_first and not pdf_first:
        steps.append(browser_step)
        recovery_decision, recovery_reason = _browser_to_http_recovery_decision(
            normalized_url=request.normalized_url,
            candidate=candidate,
            browser_step=browser_step,
            source_page_urls=source_page_urls,
            provenances=provenances,
            recommended_route_kind=recommended_route_kind,
            policy_route_family=policy_route_family,
        )
        if recovery_decision == "allowed":
            steps.append(
                replace(
                    http_step,
                    recovery_class=_BROWSER_TO_HTTP_RECOVERY_CLASS,
                    recovery_decision="allowed",
                )
            )
        else:
            blocked_recovery_classes.append(
                f"{_BROWSER_TO_HTTP_RECOVERY_CLASS}:{recovery_decision}:{recovery_reason}"
            )
    else:
        steps.append(http_step)
        steps.append(browser_step)

    if direct_pdf_request:
        steps = _pdf_route_steps_only(
            steps=steps,
            blocked_recovery_classes=blocked_recovery_classes,
        )
    deduped_steps = _dedupe_steps(_annotate_recovery_steps(steps))
    planning_reason = _planning_reason(
        remembered_route=remembered_route,
        candidate_pdf_url=candidate_pdf_url,
        browser_first=browser_first,
        source_page_urls=source_page_urls,
        policy_signal=policy_signal,
        policy_scope=policy_scope,
    )
    return ReportDownloadRoutePlanResponse(
        schema_version="1.0",
        steps=deduped_steps,
        planning_reason=planning_reason,
        blocked_recovery_classes=blocked_recovery_classes,
    )


def _prioritize_direct_pdf_steps(
    steps: list[ReportDownloadRoutePlanStep],
) -> list[ReportDownloadRoutePlanStep]:
    direct_steps = [step for step in steps if step.route_family == "direct_pdf_probe"]
    other_steps = [step for step in steps if step.route_family != "direct_pdf_probe"]
    return [*direct_steps, *other_steps]


def _pdf_route_steps_only(
    *,
    steps: list[ReportDownloadRoutePlanStep],
    blocked_recovery_classes: list[str],
) -> list[ReportDownloadRoutePlanStep]:
    pdf_steps = [
        step
        for step in _prioritize_direct_pdf_steps(steps)
        if step.route_family in {"direct_pdf_probe", "http_pdf_probe"}
    ]
    blocked_browser_families = [
        step.route_family for step in steps if step.route_family.startswith("browser_")
    ]
    blocked_recovery_classes.extend(
        f"{route_family}:blocked:direct_pdf_request"
        for route_family in blocked_browser_families
    )
    return pdf_steps


def _remembered_attempt_url(
    *,
    normalized_url: str,
    remembered_route: PublisherDownloadRouteMemory,
    remembered_route_family: str,
    delivery_email: str | None,
) -> str:
    target_url = str(remembered_route.resolved_target_url or "").strip()
    if (
        str(remembered_route.route_kind or "").strip() == "email_delivery"
        and remembered_route_family == "browser_email_form"
        and not _has_email_query_key(target_url)
    ):
        return str(normalized_url or "").strip() or target_url
    return _refresh_remembered_email_query_value(
        target_url,
        delivery_email=delivery_email,
    )


def _has_email_query_key(url: str) -> bool:
    target_url = str(url or "").strip()
    if not target_url:
        return False
    parsed = urlsplit(target_url)
    if not parsed.query:
        return False
    return any(
        key.strip().casefold() in _EMAIL_QUERY_KEYS
        for key, _value in parse_qsl(parsed.query, keep_blank_values=True)
    )


def _refresh_remembered_email_query_value(
    url: str,
    *,
    delivery_email: str | None,
) -> str:
    target_url = str(url or "").strip()
    current_delivery_email = str(delivery_email or "").strip()
    if not target_url or not current_delivery_email:
        return target_url
    parsed = urlsplit(target_url)
    if not parsed.query:
        return target_url
    rewritten_pairs: list[tuple[str, str]] = []
    changed = False
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.strip().casefold() in _EMAIL_QUERY_KEYS:
            rewritten_pairs.append((key, current_delivery_email))
            changed = True
            continue
        rewritten_pairs.append((key, value))
    if not changed:
        return target_url
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(rewritten_pairs, doseq=True),
            parsed.fragment,
        )
    )


def _build_browser_step(
    *,
    normalized_url: str,
    source_page_urls: list[str],
    candidate_title: str,
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
        _memory_route_step_hints(
            remembered_route=remembered_route,
            route_family=remembered_route.route_family,
        )
        if remembered_route is not None
        and str(remembered_route.outcome or "").strip().lower()
        in {"downloaded", "email_requested", "captured"}
        else []
    )
    remembered_route_family = _canonical_memory_route_family(
        route_kind=remembered_route_kind,
        route_family=remembered_route.route_family
        if remembered_route is not None
        else "",
    )
    reusable_memory_route = _should_reuse_memory_route(remembered_route)
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
        if not redirect_target_url and _tracker_host_url_has_report_detail_signal(
            normalized_url=normalized_url,
            candidate_title=candidate_title,
        ):
            return ReportDownloadRoutePlanStep(
                schema_version="1.0",
                step_name="report_download_browser_email_form",
                route_family="browser_email_form",
                attempt_url=normalized_url,
                route_kind_hint="email_delivery",
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
    if _looks_like_email_form_url(
        normalized_url,
        candidate_title=candidate_title,
        source_page_urls=source_page_urls,
    ) and not (
        (
            remembered_route_kind == "email_delivery"
            or remembered_route_family == "browser_email_form"
        )
        and (
            reusable_memory_route or _has_actionable_email_memory_hint(remembered_route)
        )
    ):
        return ReportDownloadRoutePlanStep(
            schema_version="1.0",
            step_name="report_download_browser_email_form",
            route_family="browser_email_form",
            attempt_url=normalized_url,
            route_kind_hint="email_delivery",
            source_page_url_hint=source_page_url,
            uses_memory_route=False,
            fallback_on_retryable_error=False,
        )
    if source_page_url and _is_same_origin_detail_under_source_page(
        detail_url=normalized_url,
        source_page_url=source_page_url,
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
    if (
        remembered_route_kind == "email_delivery"
        or remembered_route_family == "browser_email_form"
    ) and (
        reusable_memory_route or _has_actionable_email_memory_hint(remembered_route)
    ):
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
    if _looks_like_direct_onsite_report_url(redirect_target_url or normalized_url):
        attempt_url = redirect_target_url or normalized_url
        return ReportDownloadRoutePlanStep(
            schema_version="1.0",
            step_name="report_download_browser_onsite_report",
            route_family="browser_onsite_report",
            attempt_url=attempt_url,
            route_step_hints=_onsite_capture_route_steps(attempt_url),
            route_kind_hint="onsite_report",
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
        attempt_url = redirect_target_url or normalized_url
        return ReportDownloadRoutePlanStep(
            schema_version="1.0",
            step_name="report_download_browser_onsite_report",
            route_family="browser_onsite_report",
            attempt_url=attempt_url,
            route_step_hints=_onsite_capture_route_steps(attempt_url),
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


def _is_same_origin_detail_under_source_page(
    *, detail_url: str, source_page_url: str
) -> bool:
    """Recognize an exact report detail page beneath a retained listing URL."""
    detail = urlsplit(str(detail_url or "").strip())
    source = urlsplit(str(source_page_url or "").strip())
    if (
        detail.scheme not in {"http", "https"}
        or source.scheme not in {"http", "https"}
        or detail.netloc.casefold() != source.netloc.casefold()
    ):
        return False
    source_path = source.path.rstrip("/")
    detail_path = detail.path.rstrip("/")
    return bool(
        source_path
        and detail_path != source_path
        and detail_path.startswith(source_path + "/")
    )


def _memory_route_step_hints(
    *,
    remembered_route: PublisherDownloadRouteMemory,
    route_family: str,
) -> list[BrowserDownloadRouteStep]:
    if _is_email_memory_route(
        remembered_route=remembered_route, route_family=route_family
    ):
        return [
            step
            for step in remembered_route.route_steps
            if not _route_step_enters_remembered_form_value(step)
        ]
    return list(remembered_route.route_steps)


def _is_email_memory_route(
    *,
    remembered_route: PublisherDownloadRouteMemory,
    route_family: str,
) -> bool:
    return (
        str(remembered_route.route_kind or "").strip() == "email_delivery"
        or str(route_family or "").strip() == "browser_email_form"
    )


def _route_step_enters_remembered_form_value(step: BrowserDownloadRouteStep) -> bool:
    action = str(step.action or "").strip().casefold()
    if action in {"input", "type", "fill", "select", "select_dropdown"}:
        return True
    text = " ".join(
        [
            str(step.result or ""),
            str(step.target_role or ""),
        ]
    ).casefold()
    return "typed " in text or "current value" in text or "selected dropdown" in text


def _tracker_host_url_has_report_detail_signal(
    *,
    normalized_url: str,
    candidate_title: str,
) -> bool:
    path = str(urlsplit(str(normalized_url or "").strip()).path or "").strip().lower()
    title = str(candidate_title or "").strip().lower()
    if not path or _looks_like_pdf(path):
        return False
    path_tokens = {token for token in re.split(r"[^a-z0-9]+", path) if token}
    title_tokens = {token for token in re.split(r"[^a-z0-9]+", title) if token}
    report_tokens = path_tokens & _REPORT_DETAIL_SIGNAL_MARKERS
    if not report_tokens:
        return False
    if title_tokens and report_tokens & title_tokens:
        return True
    return len(path_tokens) >= 3


def _planning_reason(
    *,
    remembered_route: PublisherDownloadRouteMemory | None,
    candidate_pdf_url: str,
    browser_first: bool,
    source_page_urls: list[str],
    policy_signal: PublisherDownloadRoutePolicySignal | None,
    policy_scope: str,
) -> str:
    if _should_reuse_memory_route(remembered_route):
        if candidate_pdf_url:
            return "Reuse the verified remembered route first, then verify the discovery-provided candidate PDF before broader fallback."
        return "Reuse the verified remembered route first, then fall back to discovery-aware HTTP and browser attempts only on retryable failure."
    if policy_signal is not None:
        scope_label = (
            "Publisher-domain route-policy history"
            if policy_scope == "publisher_scope"
            else "Publisher route-policy history"
        )
        return (
            f"{scope_label} prefers "
            f"{policy_signal.route_family} "
            f"(success rate {policy_signal.success_rate:.3f}, confidence {policy_signal.confidence_score:.3f}), "
            "so rank acquisition strategies by learned success before static fallback."
        )
    if candidate_pdf_url:
        return "The discovery phase already exposed a candidate PDF URL, so verify that target before broader HTTP or browser exploration."
    if browser_first and source_page_urls:
        return "Discovery evidence points to a browser-derived route from a source page, so revisit that page before generic PDF probing."
    if browser_first:
        return "Discovery evidence points to a browser-derived route, so prefer browser execution before generic PDF probing."
    return "No verified remembered route is available, so start with discovery-aware PDF probing before falling back to browser execution."


__all__ = [
    "plan_report_download_routes",
    "_build_plan",
    "_build_browser_step",
    "_tracker_host_url_has_report_detail_signal",
    "_planning_reason",
]
