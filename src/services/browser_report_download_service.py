from __future__ import annotations

import logging
from dataclasses import asdict, replace

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
from src.services._browser_report_download.prediction import (
    predict_pre_browser_doc_type,
)
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


def _with_augmented_error_context(
    exc: AppError,
    *,
    normalized_url: str,
    execution_url: str,
    download_dir: str,
    route_family_hint: str | None,
    browser_run=None,
) -> AppError:
    context = dict(exc.context or {})
    context.setdefault("normalized_url", normalized_url)
    context.setdefault("execution_url", execution_url)
    context.setdefault("download_dir", download_dir)
    context.setdefault("route_family_hint", str(route_family_hint or "").strip())
    if browser_run is not None:
        context.setdefault("final_page_url", str(browser_run.final_page_url or "").strip())
        context.setdefault(
            "final_page_title", str(browser_run.final_page_title or "").strip()
        )
        context.setdefault(
            "html_snapshot_path", str(browser_run.html_snapshot_path or "").strip()
        )
        context.setdefault(
            "screenshot_path", str(browser_run.screenshot_path or "").strip()
        )
        context.setdefault(
            "network_events",
            [
                {
                    "schema_version": event.schema_version,
                    "url": event.url,
                    "initiator_type": event.initiator_type,
                    "signal_kind": event.signal_kind,
                }
                for event in browser_run.network_events
            ],
        )
        context.setdefault(
            "network_event_count",
            len(browser_run.network_events),
        )
    return AppError(
        code=exc.code,
        message=exc.message,
        cause=exc.cause,
        retryable=exc.retryable,
        severity=exc.severity,
        context=context,
    )


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
    doc_type_prediction = predict_pre_browser_doc_type(
        request=request,
        normalized_url=normalized_url,
        normalized_execution_url=normalized_execution_url,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_doc_type_prediction",
            module=logger.name,
            fields=asdict(doc_type_prediction),
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

    predicted_direct_pdf_probe_url = (
        doc_type_prediction.probe_url
        if doc_type_prediction.predicted_doc_type == "direct_pdf"
        else normalized_execution_url
    )
    should_try_direct_pdf_fetch = (
        request.route_family_hint == "direct_pdf_probe"
        or url_looks_like_direct_pdf(normalized_execution_url)
        or doc_type_prediction.predicted_doc_type == "direct_pdf"
    )
    if should_try_direct_pdf_fetch:
        direct_pdf_result = try_direct_pdf_download(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
            probe_url=predicted_direct_pdf_probe_url,
            route_family=(
                request.route_family_hint
                if request.route_family_hint == "direct_pdf_probe"
                else "direct_pdf_probe"
            ),
            used_candidate_pdf_url=bool(
                request.candidate_trace is not None
                and request.candidate_trace.pdf_url
                and predicted_direct_pdf_probe_url
                == validate_and_normalize_url(request.candidate_trace.pdf_url)
            ),
            used_candidate_source_page=bool(
                request.source_page_url_hint
                and predicted_direct_pdf_probe_url
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

    report_page_link_request = request
    if (
        doc_type_prediction.predicted_doc_type == "report_page_pdf_link"
        and request.route_family_hint
        not in {
            "http_pdf_probe",
            "browser_email_form",
            "browser_pdf_click",
            "browser_tracker_redirect",
            "browser_listing_hub",
        }
    ):
        report_page_link_request = replace(
            request, route_family_hint="browser_pdf_click"
        )
    report_page_pdf_link_result = try_report_page_pdf_link_download(
        request=report_page_link_request,
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
        raise _with_augmented_error_context(
            exc,
            normalized_url=normalized_url,
            execution_url=normalized_execution_url,
            download_dir=str(download_dir),
            route_family_hint=request.route_family_hint,
        ) from exc
    try:
        response = finalize_browser_report_download_result(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            delivery_email=delivery_email_value,
            download_dir=download_dir,
            browser_run=browser_run,
        )
    except AppError as exc:
        raise _with_augmented_error_context(
            exc,
            normalized_url=normalized_url,
            execution_url=normalized_execution_url,
            download_dir=str(download_dir),
            route_family_hint=request.route_family_hint,
            browser_run=browser_run,
        ) from exc
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
