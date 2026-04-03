from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from src.contracts.publisher_inventory import (
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
    PublisherInventoryServiceRequest,
    PublisherInventoryServiceResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_service")


@dataclass(frozen=True)
class BrowserInventoryAcquisitionDependencies:
    asyncio_module: Any
    prepare_session_dir: Callable[[str, str], Path]
    load_browser_use_runtime: Callable[[str], Any]
    run_browser_traversal: Callable[[Any, PublisherInventoryServiceRequest, RunContext, str], Any]
    extract_http_supplement: Callable[
        [PublisherInventoryServiceRequest, PublisherInventoryPage, str, RunContext],
        list[PublisherInventoryRawCandidate],
    ]
    fallback_http_discovery: Callable[
        [PublisherInventoryServiceRequest, RunContext, str, bool],
        PublisherInventoryServiceResponse,
    ]
    kill_browser: Callable[[Any, RunContext], None]
    candidate_provenance_counts: Callable[[list[PublisherInventoryRawCandidate]], dict[str, int]]


def discover_inventory_via_browser(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
    *,
    use_hint: bool,
    dependencies: BrowserInventoryAcquisitionDependencies,
) -> PublisherInventoryServiceResponse:
    session_dir = dependencies.prepare_session_dir(
        request.settings.output_dir,
        normalized_url,
    )
    browser_use = dependencies.load_browser_use_runtime(normalized_url)
    browser = browser_use.Browser(
        downloads_path=str(session_dir),
        headless=not request.settings.headed,
        auto_download_pdfs=False,
    )
    pages: list[PublisherInventoryPage] = []
    candidates: list[PublisherInventoryRawCandidate] = []
    final_page_url = normalized_url
    route_summary = ""
    try:
        pages, candidates, final_page_url, route_summary = dependencies.asyncio_module.run(
            dependencies.run_browser_traversal(
                browser,
                request,
                ctx,
                normalized_url,
            )
        )
    except Exception as exc:
        browser_error = _coerce_browser_error(
            exc=exc,
            normalized_url=normalized_url,
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_failed",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "error": str(exc),
                    "code": browser_error.code,
                },
            )
        )
        if _should_attempt_http_recovery(browser_error):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_inventory_browser_http_recovery_start",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "browser_error_code": browser_error.code,
                    },
                )
            )
            try:
                return dependencies.fallback_http_discovery(
                    request,
                    ctx,
                    normalized_url,
                    False,
                )
            except AppError as recovery_exc:
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="publisher_inventory_browser_http_recovery_failed",
                        module=logger.name,
                        fields={
                            "normalized_url": normalized_url,
                            "code": recovery_exc.code,
                            "message": recovery_exc.message,
                            "browser_error_code": browser_error.code,
                        },
                    )
                )
        raise browser_error from exc
    finally:
        dependencies.kill_browser(browser, ctx)

    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_browser_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "browser_final_url": final_page_url,
                "page_count": len(pages),
                "candidate_count": len(candidates),
                "candidate_provenance_counts": dependencies.candidate_provenance_counts(
                    candidates
                ),
                "route_summary": route_summary,
            },
        )
    )
    if pages and not candidates:
        supplemented_candidates: list[PublisherInventoryRawCandidate] = []
        for page in pages:
            supplemented_candidates.extend(
                dependencies.extract_http_supplement(
                    request,
                    page,
                    normalized_url,
                    ctx,
                )
            )
        if supplemented_candidates:
            candidates = supplemented_candidates
    if not pages or not candidates:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_http_recovery_start",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "browser_page_count": len(pages),
                    "browser_candidate_count": len(candidates),
                },
            )
        )
        try:
            return dependencies.fallback_http_discovery(
                request,
                ctx,
                normalized_url,
                False,
            )
        except AppError as exc:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_inventory_browser_http_recovery_failed",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "code": exc.code,
                        "message": exc.message,
                    },
                )
            )
    if not pages or not candidates:
        raise AppError(
            code="publisher_inventory_browser_incomplete",
            message="Browser-render inventory discovery returned no usable pages or candidates",
            retryable=True,
            context={"normalized_url": normalized_url},
        )
    response = PublisherInventoryServiceResponse(
        schema_version="1.0",
        source_url=request.insights_url,
        normalized_url=normalized_url,
        route_kind="browser_render",
        route_summary=route_summary,
        final_page_url=str(final_page_url or normalized_url).strip(),
        used_route_hint=use_hint,
        pages=pages,
        candidates=candidates,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_browser_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "page_count": len(response.pages),
                "candidate_count": len(response.candidates),
                "candidate_provenance_counts": dependencies.candidate_provenance_counts(
                    response.candidates
                ),
                "used_route_hint": response.used_route_hint,
                "route_kind": response.route_kind,
            },
        )
    )
    return response


def _coerce_browser_error(
    *,
    exc: Exception,
    normalized_url: str,
) -> AppError:
    if isinstance(exc, AppError):
        return exc
    if exc.__class__.__name__ == "TimeoutError":
        return AppError(
            code="publisher_inventory_browser_timeout",
            message="Browser-render inventory discovery exceeded the configured timeout",
            cause=exc,
            retryable=True,
            context={"normalized_url": normalized_url},
        )
    return AppError(
        code="publisher_inventory_browser_failed",
        message="Browser-render inventory discovery failed unexpectedly",
        cause=exc,
        retryable=True,
        context={
            "normalized_url": normalized_url,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
            "host": str(urlsplit(normalized_url).hostname or "").strip().lower(),
        },
    )


def _should_attempt_http_recovery(error: AppError) -> bool:
    return error.retryable or error.code == "publisher_inventory_browser_pagination_limit"
