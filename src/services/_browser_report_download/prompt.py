from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.contracts.browser_download import BrowserReportDownloadRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.run_context import RunContext
from src.services import prompt_service
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

PROMPT_NAMESPACE = "browser_report_download/browser_route"


@dataclass(frozen=True)
class BrowserDownloadPromptBundle:
    schema_version: str
    namespace: str
    system_prompt_path: str
    user_prompt_path: str
    system_prompt_sha256: str
    user_prompt_sha256: str
    rendered_system_prompt: str
    rendered_user_prompt: str
    task_prompt: str


def render_browser_report_download_prompt(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    delivery_email: str | None,
) -> BrowserDownloadPromptBundle:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace=PROMPT_NAMESPACE,
        ),
        ctx,
    )
    variables = {
        "normalized_url": normalized_url,
        "execution_url": execution_url,
        "download_dir": str(download_dir),
        "identity_prompt": _render_identity_prompt(
            request=request,
            delivery_email=delivery_email,
        ),
        "route_hint_text": _render_route_hint_text(
            route_hint=request.route_hint,
            route_kind_hint=request.route_kind_hint,
        ),
        "delivery_instruction": _render_delivery_instruction(
            delivery_email=delivery_email,
        ),
        "route_family_guidance": _render_route_family_guidance(request=request),
        "discovery_context": _render_discovery_context(request=request),
    }
    rendered_system = prompt_service.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.system,
            variables=variables,
        ),
        ctx,
    )
    rendered_user = prompt_service.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.user,
            variables=variables,
        ),
        ctx,
    )
    task_prompt = (
        f"{rendered_system.text.strip()}\n\n{rendered_user.text.strip()}"
    ).strip()
    bundle = BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace=PROMPT_NAMESPACE,
        system_prompt_path=prompt_set.system.path,
        user_prompt_path=prompt_set.user.path,
        system_prompt_sha256=prompt_set.system.sha256,
        user_prompt_sha256=prompt_set.user.sha256,
        rendered_system_prompt=rendered_system.text,
        rendered_user_prompt=rendered_user.text,
        task_prompt=task_prompt,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_prompt_prepared",
            module=logger.name,
            fields={
                "prompt_namespace": bundle.namespace,
                "system_prompt_path": bundle.system_prompt_path,
                "user_prompt_path": bundle.user_prompt_path,
                "system_prompt_sha256": bundle.system_prompt_sha256,
                "user_prompt_sha256": bundle.user_prompt_sha256,
                "rendered_system_prompt": bundle.rendered_system_prompt,
                "rendered_user_prompt": bundle.rendered_user_prompt,
                "task_prompt": bundle.task_prompt,
                "model": request.settings.model,
                "temperature": request.settings.temperature,
                "timeout_seconds": request.settings.timeout_seconds,
                "max_steps": request.settings.max_steps,
                "candidate_canonical_url": (
                    request.candidate_trace.canonical_url
                    if request.candidate_trace is not None
                    else ""
                ),
                "candidate_pdf_url": (
                    request.candidate_trace.pdf_url
                    if request.candidate_trace is not None
                    and request.candidate_trace.pdf_url
                    else ""
                ),
                "candidate_source_page_urls": (
                    list(request.candidate_trace.source_page_urls)
                    if request.candidate_trace is not None
                    else []
                ),
                "candidate_discovery_provenances": (
                    list(request.candidate_trace.discovery_provenances)
                    if request.candidate_trace is not None
                    else []
                ),
                "publisher_discovery_route_kind": request.publisher_discovery_route_kind
                or "",
                "publisher_recommended_discovery_route_kind": (
                    request.publisher_recommended_discovery_route_kind or ""
                ),
                "route_family_hint": request.route_family_hint or "",
                "route_family_guidance": variables["route_family_guidance"],
                "source_page_url_hint": request.source_page_url_hint or "",
            },
        )
    )
    return bundle


def _render_identity_prompt(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
) -> str:
    lines = [
        "Use the following configured identity values when a matching form field is available. Do not invent missing values."
    ]
    for field in request.settings.identity_profile.fields:
        aliases = ", ".join(field.aliases)
        value = str(field.value or "").strip()
        if field.key == "work_email" and delivery_email:
            value = delivery_email.strip()
        if not value:
            continue
        alias_text = f" (aliases: {aliases})" if aliases else ""
        lines.append(f"- {field.label}{alias_text}: {value}")
    if len(lines) == 1:
        lines.append("- No non-empty identity values are configured.")
    lines.append(
        "If a required field has no configured value, stop before submission, still report encountered_form_fields, and do not invent replacement values."
    )
    return "\n".join(lines)


def _render_route_hint_text(
    *,
    route_hint: str | None,
    route_kind_hint: str | None,
) -> str:
    if not route_hint:
        return "No previously successful route summary is available for this URL."
    hint_prefix = (
        f"Previously successful route kind: {route_kind_hint}. "
        if route_kind_hint
        else ""
    )
    return (
        f"{hint_prefix}Previously successful route summary for this URL: {route_hint}"
    )


def _render_delivery_instruction(*, delivery_email: str | None) -> str:
    if delivery_email:
        return (
            "If an email form is required, use this email address and confirm "
            f"submission: {delivery_email}"
        )
    return (
        "If the site requires email delivery and no configured email value is "
        "available, do not invent one. Classify the route as `email_delivery` "
        "and set email_submission_completed to false."
    )


def _render_route_family_guidance(*, request: BrowserReportDownloadRequest) -> str:
    route_family = str(request.route_family_hint or "").strip()
    if route_family == "browser_pdf_click":
        return "\n".join(
            [
                "Route-family guidance for `browser_pdf_click`:",
                "- Stay tightly scoped to the candidate page and visible report CTAs.",
                "- Prefer direct PDF links or obvious download buttons over generic navigation.",
                "- If the page forces a form instead of producing a PDF, classify that as `email_delivery` rather than pretending the PDF path worked.",
                "- Do not wander across unrelated resources, blog posts, or site navigation.",
            ]
        )
    if route_family == "browser_email_form":
        return "\n".join(
            [
                "Route-family guidance for `browser_email_form`:",
                "- Inspect the form before submission and capture all encountered field labels.",
                "- Use only configured identity values. If a required field is missing, stop and return the correct blocker code instead of guessing.",
                "- After submission, inspect confirmation text, URL change, button state, and whether the form disappeared.",
                "- A submit click alone is not enough; only classify success when the confirmation evidence is real.",
            ]
        )
    if route_family == "browser_tracker_redirect":
        return "\n".join(
            [
                "Route-family guidance for `browser_tracker_redirect`:",
                "- Let the redirect resolve first and record the resolved target URL.",
                "- If the redirect lands on a listing/source page, switch to the exact matching report candidate rather than exploring broadly.",
                "- Avoid loops through tracking wrappers, share dialogs, or marketing overlays.",
            ]
        )
    if route_family == "browser_listing_hub":
        return "\n".join(
            [
                "Route-family guidance for `browser_listing_hub`:",
                "- Start from the source/listing page and find the exact candidate title or URL from discovery context.",
                "- Open only the most likely matching report candidate; ignore unrelated resources, blog cards, and marketing content.",
                "- If the destination is an on-site longread instead of a PDF, classify it as `onsite_report` and capture it locally.",
            ]
        )
    if route_family == "browser_onsite_report":
        return "\n".join(
            [
                "Route-family guidance for `browser_onsite_report`:",
                "- Treat the report as on-site content, not a failed PDF download.",
                "- Capture the article locally, return `onsite_capture_path`, and record `traversed_page_urls`.",
                "- For pagination or infinite scroll, traverse only until the report is complete or clearly bounded; avoid endless scrolling.",
                "- Deduplicate repeated sections and set `onsite_completeness_status` honestly.",
            ]
        )
    return "\n".join(
        [
            "Route-family guidance for the current attempt:",
            "- Stay tightly scoped to the candidate and the most direct report-acquisition path.",
            "- Prefer deterministic download paths over exploratory browsing.",
            "- If the route is blocked or becomes an on-site longread, classify that explicitly instead of forcing a PDF outcome.",
        ]
    )


def _render_discovery_context(*, request: BrowserReportDownloadRequest) -> str:
    candidate = request.candidate_trace
    lines = [
        f"Planned route family for this attempt: {request.route_family_hint or 'unspecified'}."
    ]
    if request.publisher_discovery_route_kind:
        lines.append(
            f"Publisher discovery route kind from the discovery/diff phase: {request.publisher_discovery_route_kind}."
        )
    if request.publisher_recommended_discovery_route_kind:
        lines.append(
            "Publisher recommended discovery route kind from the discovery/diff "
            f"phase: {request.publisher_recommended_discovery_route_kind}."
        )
    if candidate is None:
        lines.append("No discovery candidate trace is available for this attempt.")
        return "\n".join(lines)
    lines.append(f"Candidate title: {candidate.title}")
    lines.append(f"Candidate canonical URL: {candidate.canonical_url}")
    if candidate.pdf_url:
        lines.append(
            f"Discovery observed a candidate PDF URL for this report: {candidate.pdf_url}"
        )
        lines.append(
            "Verify that candidate PDF target before exploring alternate download routes."
        )
    if candidate.source_page_urls:
        lines.append(
            "Discovery source pages where this candidate was observed: "
            + ", ".join(candidate.source_page_urls)
        )
    if request.source_page_url_hint:
        lines.append(
            "If the candidate URL is thin, gated, or tracker-like, revisit this "
            f"source page first: {request.source_page_url_hint}"
        )
    if candidate.discovery_provenances:
        lines.append(
            "Discovery provenance labels for this candidate: "
            + ", ".join(candidate.discovery_provenances)
        )
    if candidate.max_confidence is not None:
        lines.append(
            f"Discovery maximum candidate confidence: {candidate.max_confidence:.3f}"
        )
    return "\n".join(lines)
