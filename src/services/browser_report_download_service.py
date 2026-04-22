from __future__ import annotations

import logging
from dataclasses import asdict

from src.contracts.browser_download import (
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.artifact import (
    finalize_browser_report_download_result,
)
from src.services._browser_report_download.browser import (
    run_browser_report_download_agent,
)
from src.services._browser_report_download.http import try_direct_pdf_download
from src.services._browser_report_download.http import try_direct_onsite_capture
from src.services._browser_report_download.http import try_http_access_challenge_probe
from src.services._browser_report_download.http import try_report_page_pdf_link_download
from src.services._browser_report_download.http import try_static_email_gate_probe
from src.services._browser_report_download.prompt import (
    render_browser_report_download_prompt,
)
from src.services._browser_report_download.request import (
    prepare_download_dir,
    resolve_delivery_email_value,
    url_looks_like_direct_pdf,
    validate_and_normalize_url,
    validate_browser_runtime_settings,
    validate_common_request,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")


def download_report_with_browser_use(
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
) -> BrowserReportDownloadResult:
    normalized_url = validate_and_normalize_url(request.url)
    execution_url = str(request.attempt_url or request.url).strip()
    normalized_execution_url = validate_and_normalize_url(execution_url)
    validate_common_request(request, normalized_url)
    if request.attempt_url and not normalized_execution_url:
        validate_common_request(request, normalized_execution_url)
    delivery_email_value = resolve_delivery_email_value(request)
    download_dir = prepare_download_dir(
        root_dir=request.settings.output_dir,
        normalized_url=normalized_url,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_start",
            module=logger.name,
            fields={
                "url": request.url,
                "normalized_url": normalized_url,
                "execution_url": execution_url,
                "normalized_execution_url": normalized_execution_url,
                "output_dir": request.settings.output_dir,
                "download_dir": str(download_dir),
                "state_db": request.settings.state_db,
                "identity_config_path": request.settings.identity_config_path,
                "identity_field_count": len(request.settings.identity_profile.fields),
                "model": request.settings.model,
                "temperature": request.settings.temperature,
                "timeout_seconds": request.settings.timeout_seconds,
                "max_steps": request.settings.max_steps,
                "headed": request.settings.headed,
                "has_delivery_email": bool(request.delivery_email),
                "has_effective_delivery_email": bool(delivery_email_value),
                "has_route_hint": bool(request.route_hint),
                "route_family_hint": request.route_family_hint or "",
                "has_candidate_trace": request.candidate_trace is not None,
                "publisher_discovery_route_kind": request.publisher_discovery_route_kind
                or "",
                "publisher_recommended_discovery_route_kind": (
                    request.publisher_recommended_discovery_route_kind or ""
                ),
            },
        )
    )

    if request.route_family_hint == "http_pdf_probe":
        report_page_pdf_link_result = try_report_page_pdf_link_download(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
            page_url=normalized_execution_url,
        )
        if report_page_pdf_link_result is not None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_complete",
                    module=logger.name,
                    fields=asdict(report_page_pdf_link_result),
                )
            )
            return report_page_pdf_link_result
        raise AppError(
            code="browser_download_http_probe_failed",
            message="The planned HTTP probe did not produce a valid PDF artifact",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "execution_url": normalized_execution_url,
                "route_family_hint": request.route_family_hint,
            },
        )

    should_try_direct_pdf_fetch = (
        request.route_family_hint == "direct_pdf_probe"
        or url_looks_like_direct_pdf(normalized_execution_url)
    )
    if should_try_direct_pdf_fetch:
        direct_pdf_result = try_direct_pdf_download(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
            probe_url=normalized_execution_url,
            route_family=request.route_family_hint or "direct_pdf_probe",
            used_candidate_pdf_url=bool(
                request.candidate_trace is not None
                and request.candidate_trace.pdf_url
                and normalized_execution_url
                == validate_and_normalize_url(request.candidate_trace.pdf_url)
            ),
            used_candidate_source_page=bool(
                request.source_page_url_hint
                and normalized_execution_url
                == validate_and_normalize_url(request.source_page_url_hint)
            ),
        )
        if direct_pdf_result is not None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_complete",
                    module=logger.name,
                    fields=asdict(direct_pdf_result),
                )
            )
            return direct_pdf_result
        report_page_pdf_link_result = try_report_page_pdf_link_download(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
            page_url=normalized_execution_url,
        )
        if report_page_pdf_link_result is not None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_complete",
                    module=logger.name,
                    fields=asdict(report_page_pdf_link_result),
                )
            )
            return report_page_pdf_link_result
        if request.route_family_hint == "direct_pdf_probe":
            raise AppError(
                code="browser_download_http_probe_failed",
                message="The planned HTTP probe did not produce a valid PDF artifact",
                retryable=True,
                context={
                    "normalized_url": normalized_url,
                    "execution_url": normalized_execution_url,
                    "route_family_hint": request.route_family_hint,
                },
            )
        download_dir = prepare_download_dir(
            root_dir=request.settings.output_dir,
            normalized_url=normalized_url,
        )

    report_page_pdf_link_result = try_report_page_pdf_link_download(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
        page_url=normalized_execution_url,
    )
    if report_page_pdf_link_result is not None:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_complete",
                module=logger.name,
                fields=asdict(report_page_pdf_link_result),
            )
        )
        return report_page_pdf_link_result

    direct_onsite_result = try_direct_onsite_capture(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
        page_url=normalized_execution_url,
    )
    if direct_onsite_result is not None:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_complete",
                module=logger.name,
                fields=asdict(direct_onsite_result),
            )
        )
        return direct_onsite_result

    static_email_gate_result = try_static_email_gate_probe(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        page_url=normalized_execution_url,
    )
    if static_email_gate_result is not None:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_complete",
                module=logger.name,
                fields=asdict(static_email_gate_result),
            )
        )
        return static_email_gate_result

    if request.route_family_hint == "browser_email_form":
        access_challenge_result = try_http_access_challenge_probe(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            page_url=normalized_execution_url,
            preflight=True,
        )
        if access_challenge_result is not None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_complete",
                    module=logger.name,
                    fields=asdict(access_challenge_result),
                )
            )
            return access_challenge_result

    validate_browser_runtime_settings(request)
    prompt_bundle = render_browser_report_download_prompt(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        execution_url=normalized_execution_url,
        download_dir=download_dir,
        delivery_email=delivery_email_value,
    )
    try:
        browser_run = run_browser_report_download_agent(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            execution_url=normalized_execution_url,
            download_dir=download_dir,
            prompt_bundle=prompt_bundle,
        )
    except AppError as exc:
        if (
            exc.code == "browser_download_agent_timeout"
            and request.route_family_hint == "browser_email_form"
        ):
            access_challenge_result = try_http_access_challenge_probe(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                page_url=normalized_execution_url,
            )
            if access_challenge_result is not None:
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="browser_report_download_complete",
                        module=logger.name,
                        fields=asdict(access_challenge_result),
                    )
                )
                return access_challenge_result
        raise
    response = finalize_browser_report_download_result(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        delivery_email=delivery_email_value,
        download_dir=download_dir,
        browser_run=browser_run,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_complete",
            module=logger.name,
            fields=asdict(response),
        )
    )
    return response
