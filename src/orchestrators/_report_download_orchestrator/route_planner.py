from __future__ import annotations

import logging
import re
from dataclasses import replace
from urllib.parse import parse_qs, unquote, urlsplit

from src.contracts.browser_download import (
    PublisherDownloadRouteMemory,
    PublisherDownloadRoutePolicySignal,
    ReportDownloadRoutePlanRequest,
    ReportDownloadRoutePlanResponse,
    ReportDownloadRoutePlanStep,
)
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
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
                    "blocked_recovery_classes": list(
                        response.blocked_recovery_classes
                    ),
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

    if remembered_route is not None and _should_reuse_memory_route(remembered_route):
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
        list(remembered_route.route_steps)
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
    if _looks_like_email_form_url(
        normalized_url,
        candidate_title=candidate_title,
        source_page_urls=source_page_urls,
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
    if _looks_like_direct_onsite_report_url(redirect_target_url or normalized_url):
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


def _preferred_policy_signal(
    remembered_route: PublisherDownloadRouteMemory | None,
) -> PublisherDownloadRoutePolicySignal | None:
    if remembered_route is None:
        return None
    for signal in remembered_route.route_policy:
        if signal.attempts < 2:
            continue
        if signal.verified_successes < 1:
            continue
        if signal.rank_score < 0.45:
            continue
        if signal.confidence_score < 0.45 and signal.success_rate < 0.5:
            continue
        return signal
    return None


def _preferred_publisher_policy_signal(
    *,
    remembered_route: PublisherDownloadRouteMemory | None,
    normalized_url: str,
    candidate: PublisherInventoryCandidateTrace | None,
) -> PublisherDownloadRoutePolicySignal | None:
    if remembered_route is None:
        return None
    candidate_pdf_url = str(candidate.pdf_url or "").strip() if candidate else ""
    source_page_urls = _clean_string_list(
        candidate.source_page_urls if candidate is not None else []
    )
    candidate_title = (
        str(candidate.title or "").strip() if candidate is not None else ""
    )
    for signal in remembered_route.publisher_route_policy:
        if signal.attempts < 3:
            continue
        if signal.verified_successes < 2:
            continue
        if signal.success_rate < 0.667:
            continue
        if signal.rank_score < 0.65:
            continue
        if signal.confidence_score < 0.65:
            continue
        if (
            signal.blocked_attempts
            and (signal.blocked_attempts / signal.attempts) > 0.25
        ):
            continue
        if not _publisher_policy_signal_matches_context(
            signal=signal,
            normalized_url=normalized_url,
            candidate_pdf_url=candidate_pdf_url,
            candidate_title=candidate_title,
            source_page_urls=source_page_urls,
        ):
            continue
        return signal
    return None


def _publisher_policy_signal_matches_context(
    *,
    signal: PublisherDownloadRoutePolicySignal,
    normalized_url: str,
    candidate_pdf_url: str,
    candidate_title: str,
    source_page_urls: list[str],
) -> bool:
    route_family = str(signal.route_family or "").strip()
    if candidate_pdf_url and route_family not in {"direct_pdf_probe", "http_pdf_probe"}:
        return False
    if _looks_like_pdf(normalized_url) and route_family not in {
        "direct_pdf_probe",
        "http_pdf_probe",
    }:
        return False
    if route_family == "browser_onsite_report":
        return not _looks_like_email_form_url(
            normalized_url,
            candidate_title=candidate_title,
            source_page_urls=source_page_urls,
        )
    return True


def _apply_policy_route_family(
    step: ReportDownloadRoutePlanStep,
    *,
    policy_signal: PublisherDownloadRoutePolicySignal | None,
) -> ReportDownloadRoutePlanStep:
    if policy_signal is None:
        return step
    route_family = str(policy_signal.route_family or "").strip()
    if route_family not in {
        "browser_email_form",
        "browser_onsite_report",
        "browser_pdf_click",
        "browser_tracker_redirect",
        "browser_listing_hub",
    }:
        return step
    return replace(
        step,
        step_name=_policy_step_name(route_family),
        route_family=route_family,
        route_kind_hint=_route_kind_hint_for_policy_family(route_family),
        fallback_on_retryable_error=False,
    )


def _policy_step_name(route_family: str) -> str:
    if route_family == "browser_email_form":
        return "report_download_policy_browser_email_form"
    if route_family == "browser_onsite_report":
        return "report_download_policy_browser_onsite_report"
    if route_family == "browser_listing_hub":
        return "report_download_policy_browser_listing_hub"
    if route_family == "browser_tracker_redirect":
        return "report_download_policy_browser_tracker_redirect"
    return "report_download_policy_browser_candidate"


def _route_kind_hint_for_policy_family(route_family: str) -> str | None:
    if route_family == "browser_email_form":
        return "email_delivery"
    if route_family == "browser_onsite_report":
        return "onsite_report"
    return None


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
    if not remembered_route.exact_route_found:
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
    if not remembered_route.browser_had_structured_result and route_family not in {
        "direct_pdf_probe",
        "http_pdf_probe",
    }:
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
    required_successes = (
        1
        if route_family in {"direct_pdf_probe", "http_pdf_probe", "browser_email_form"}
        else 2
    )
    if remembered_route.verified_successes >= required_successes:
        return True
    return (
        remembered_route.confidence_score >= 0.75
        and remembered_route.verified_successes >= 1
    )


def _has_actionable_email_memory_hint(
    remembered_route: PublisherDownloadRouteMemory | None,
) -> bool:
    if remembered_route is None:
        return False
    if remembered_route.route_kind != "email_delivery":
        return False
    if remembered_route.outcome not in {"email_required", "email_requested"}:
        return False
    if not remembered_route.browser_had_structured_result:
        return False
    summary = str(remembered_route.route_summary or "").casefold()
    if "not found" in summary:
        return False
    if "capture" in summary and "onsite" in summary and "form" not in summary:
        return False
    action_text = " ".join(
        " ".join(
            [
                str(step.action or ""),
                str(step.target_text or ""),
                str(step.target_role or ""),
                str(step.result or ""),
            ]
        )
        for step in remembered_route.route_steps
    ).casefold()
    form_markers = {
        "download",
        "email",
        "form",
        "request",
        "submit",
    }
    if action_text and any(marker in action_text for marker in form_markers):
        return True
    return any(marker in summary for marker in {"fill", "form", "submit"})


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


def _browser_to_http_recovery_decision(
    *,
    normalized_url: str,
    candidate: PublisherInventoryCandidateTrace | None,
    browser_step: ReportDownloadRoutePlanStep,
    source_page_urls: list[str],
    provenances: set[str],
    recommended_route_kind: str,
    policy_route_family: str,
) -> tuple[str, str]:
    if policy_route_family in {"direct_pdf_probe", "http_pdf_probe"}:
        return "allowed", "policy_pdf_probe"
    if recommended_route_kind == "http_parse":
        return "allowed", "publisher_recommended_http"
    if "direct_pdf_source" in provenances:
        return "allowed", "direct_pdf_source"
    if browser_step.route_family in {
        "browser_listing_hub",
        "browser_tracker_redirect",
        "browser_email_form",
    }:
        return "blocked", f"terminal_browser_family:{browser_step.route_family}"
    if browser_step.route_family == "browser_onsite_report":
        return "deferred", "onsite_report_capture_preferred"
    if _looks_like_listing_url(normalized_url):
        return "blocked", "candidate_listing_surface"
    candidate_title = str(candidate.title or "").strip() if candidate else ""
    if _has_http_probe_signal(
        normalized_url=normalized_url,
        candidate_title=candidate_title,
        source_page_urls=source_page_urls,
    ):
        return "allowed", "candidate_has_pdf_probe_signal"
    return "deferred", "browser_route_without_http_signal"


def _has_http_probe_signal(
    *,
    normalized_url: str,
    candidate_title: str,
    source_page_urls: list[str],
) -> bool:
    path = str(urlsplit(str(normalized_url or "").strip()).path or "").casefold()
    title = str(candidate_title or "").casefold()
    if "download" in path or "pdf" in path:
        return True
    if any(marker in title for marker in _REPORT_DETAIL_SIGNAL_MARKERS):
        segments = [segment for segment in path.split("/") if segment]
        if segments:
            token_count = len([token for token in segments[-1].split("-") if token])
            if token_count >= 3 or re.search(r"\b20\d{2}\b", path):
                return True
    for source_page_url in source_page_urls:
        source_path = str(
            urlsplit(str(source_page_url or "").strip()).path or ""
        ).casefold()
        if source_path and source_path != path and "download" in path:
            return True
    return False


def _annotate_recovery_steps(
    steps: list[ReportDownloadRoutePlanStep],
) -> list[ReportDownloadRoutePlanStep]:
    annotated: list[ReportDownloadRoutePlanStep] = []
    for step in steps:
        if step.recovery_class:
            annotated.append(step)
            continue
        annotated.append(
            replace(
                step,
                recovery_class=step.route_family,
                recovery_decision=step.recovery_decision or "primary",
            )
        )
    return annotated


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
    return (
        str(urlsplit(str(url or "").strip()).path or "")
        .strip()
        .lower()
        .endswith(".pdf")
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
        return slug_token_count < 2
    return False


def _looks_like_tracker_url(url: str) -> bool:
    parsed = urlsplit(str(url or "").strip())
    hostname = str(parsed.hostname or "").strip().lower()
    path = str(parsed.path or "").strip().lower()
    query = str(parsed.query or "").strip().lower()
    host_labels = [label for label in hostname.split(".") if label]
    tracker_host = any(label in _TRACKER_HOST_MARKERS for label in host_labels)
    if tracker_host:
        return True
    path_query_tokens = _tracker_path_query_tokens(path=path, query=query)
    for marker in _TRACKER_HOST_MARKERS:
        if marker in _TRACKER_SHORT_PATH_MARKERS:
            if marker in path_query_tokens:
                return True
            continue
        if marker in path or marker in query:
            return True
    return False


def _tracker_path_query_tokens(*, path: str, query: str) -> set[str]:
    text = f"{path} {query}"
    return {token for token in re.split(r"[^a-z0-9]+", text) if token}


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
    if _path_has_email_gate_marker(lowered):
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


def _looks_like_email_form_url(
    url: str | None,
    *,
    candidate_title: str = "",
    source_page_urls: list[str] | None = None,
) -> bool:
    path = str(urlsplit(str(url or "").strip()).path or "").strip().lower()
    if not path or _looks_like_pdf(path):
        return False
    if _path_has_email_gate_marker(path):
        return True
    if _looks_like_probable_gated_report_detail_url(
        path=path,
        candidate_title=candidate_title,
        source_page_urls=source_page_urls or [],
    ):
        return True
    if _looks_like_direct_onsite_report_url(url):
        return False
    return False


def _looks_like_direct_onsite_report_url(url: str | None) -> bool:
    parsed = urlsplit(str(url or "").strip())
    path = str(parsed.path or "").strip().lower()
    if not path or _looks_like_pdf(path):
        return False
    if _path_has_email_gate_marker(path):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    if any(segment in _ONSITE_EXCLUDED_SEGMENTS for segment in segments):
        return False
    if any(phrase in path for phrase in _DIRECT_ONSITE_REPORT_PATH_PHRASES):
        return True
    return any(
        segment in _DIRECT_ONSITE_REPORT_SEGMENTS
        or any(
            segment.startswith(f"{marker}-")
            for marker in _DIRECT_ONSITE_REPORT_SEGMENTS
        )
        for segment in segments
    )


def _path_has_email_gate_marker(path: str) -> bool:
    token = str(path or "").strip().lower()
    if not token:
        return False
    if "gated-content-form" in token:
        return True
    segments = [segment for segment in token.split("/") if segment]
    split_tokens = {part for part in re.split(r"[^a-z0-9]+", token) if part}
    for marker in _EMAIL_GATE_PATH_MARKERS:
        if marker == "gated-content-form":
            continue
        if marker in split_tokens:
            return True
        for segment in segments:
            if (
                segment == marker
                or segment.startswith(f"{marker}-")
                or segment.endswith(f"-{marker}")
            ):
                return True
    return False


def _looks_like_probable_gated_report_detail_url(
    *,
    path: str,
    candidate_title: str,
    source_page_urls: list[str],
) -> bool:
    segments = [segment for segment in str(path or "").split("/") if segment]
    if len(segments) < 2:
        return False
    split_tokens = {part for part in re.split(r"[^a-z0-9]+", str(path or "")) if part}
    title = str(candidate_title or "").strip().lower()
    title_has_asset_marker = any(
        marker in title for marker in _EMAIL_GATE_DETAIL_TITLE_MARKERS
    )
    slug_has_asset_marker = bool(
        split_tokens
        & {
            "benchmark",
            "ebook",
            "guide",
            "outlook",
            "predictions",
            "report",
            "research",
            "study",
            "trends",
            "whitepaper",
        }
    )
    source_path_text = " ".join(
        str(urlsplit(str(source_url or "").strip()).path or "").strip().lower()
        for source_url in source_page_urls
    )
    source_is_report_listing = any(
        segment in _EMAIL_GATE_PARENT_SEGMENTS
        for segment in re.split(r"[^a-z0-9]+", source_path_text)
        if segment
    )
    if "resources" in segments and "reports" in segments:
        return True
    if (
        source_is_report_listing
        and title_has_asset_marker
        and slug_has_asset_marker
        and any(re.fullmatch(r"\d{4}", segment) for segment in segments)
    ):
        return True
    for index, segment in enumerate(segments[:-1]):
        if segment not in {"report", "reports"}:
            continue
        detail_slug = segments[index + 1]
        if not detail_slug or detail_slug in _LISTING_PATH_MARKERS:
            continue
        if title_has_asset_marker or slug_has_asset_marker:
            return True
        if source_is_report_listing and re.match(r"^\d{3,}", detail_slug):
            return True
    return False
