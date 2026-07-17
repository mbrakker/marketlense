from __future__ import annotations

import logging
import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.contracts.browser_download import (
    BrowserDeveloperDiagnosticsRequest,
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadRouteStep,
    BrowserDeveloperDiagnosticsResult,
    BrowserRoutePlaybookExecutionRequest,
    DownloadTerminalEvidence,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    BrowserRoutePrivateApiPromotionRequest,
)
from src.contracts.report_store import (
    SourcePublicationMetadataExtractionRequest,
    SourcePublicationMetadataExtractionResponse,
)
from src.contracts.state import (
    StateArtifactAcquisitionCacheGetRequest,
    StateArtifactAcquisitionCacheRecordRequest,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.artifact import (
    finalize_browser_report_download_result,
)
from src.services._browser_report_download._artifact.pdf import _build_pdf_result
from src.services._browser_report_download.browser import (
    run_browser_report_download_agent,
)
from src.services._browser_report_download.dev_diagnostics import (
    default_browser_doctor_verification_url as _default_browser_doctor_verification_url,
    run_browser_developer_diagnostics as _run_browser_developer_diagnostics,
)
from src.services._browser_report_download import http as http_runtime
from src.services._browser_report_download.budgets import apply_browser_route_budget
from src.services._browser_report_download.http import try_direct_pdf_download
from src.services._browser_report_download.http import try_direct_onsite_capture
from src.services._browser_report_download.http import try_http_access_challenge_probe
from src.services._browser_report_download.http import try_report_page_pdf_link_download
from src.services._browser_report_download.http import try_static_email_gate_probe
from src.services._browser_report_download.logging import (
    browser_download_result_log_fields,
    pre_browser_doc_type_prediction_log_fields,
)
from src.services._browser_report_download.prediction import (
    predict_pre_browser_doc_type,
)
from src.services._browser_report_download.playbooks import (
    execute_browser_route_playbook as _execute_browser_route_playbook,
    load_browser_route_playbooks,
    promote_private_api_evidence_to_browser_playbook as _promote_private_api_evidence_to_browser_playbook,
    promote_validated_browser_route_result_to_playbook as _promote_validated_browser_route_result_to_playbook,
)
from src.services._browser_report_download.private_api import (
    try_private_api_playbook_download,
)
from src.services._browser_report_download.private_api_auto_promotion import (
    detect_private_api_promotion_candidates as _detect_private_api_promotion_candidates,
)
from src.services._browser_report_download.publication_metadata import (
    extract_source_publication_metadata as _extract_source_publication_metadata,
)
from src.services._browser_report_download.preflight import (
    observe_browser_preflight_agent_outcome,
    try_browser_preflight_probe,
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
from src.services.state_service import (
    get_artifact_acquisition_cache,
    record_artifact_acquisition_cache,
)
from src.utils.errors import AppError
from src.utils.browser_route_playbooks import (
    select_browser_route_playbooks,
    serialize_playbook_selection_for_log,
)
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")
ARTIFACT_ACQUISITION_CACHE_VERSION = "browser_artifact_cache_v1"
ARTIFACT_ACQUISITION_CACHE_TTL_DAYS = 30


def extract_source_publication_metadata(
    request: SourcePublicationMetadataExtractionRequest,
    ctx: RunContext,
) -> SourcePublicationMetadataExtractionResponse:
    """Extract bounded source provenance from browser-captured HTML without a model call."""
    response = _extract_source_publication_metadata(request)
    metadata = response.metadata
    logger.info(
        log_event(
            ctx,
            role="service",
            event="source_publication_metadata_extracted",
            module=logger.name,
            fields={
                "evidence_status": metadata.evidence_status,
                "contradiction_status": metadata.contradiction_status,
                "evidence_kind": metadata.evidence_kind,
                "evidence_locator": metadata.evidence_locator,
                "evidence_value_hash": metadata.evidence_value_hash,
                "observed_value_count": len(metadata.observed_values),
            },
        )
    )
    return response


def _artifact_cache_key(
    *,
    normalized_url: str,
    publisher_scope: str,
    report_title: str,
) -> str:
    payload = {
        "schema_version": "1.0",
        "normalized_url": normalized_url,
        "publisher_scope": publisher_scope,
        "report_title": report_title,
        "cache_version": ARTIFACT_ACQUISITION_CACHE_VERSION,
    }
    return hashlib.sha256(repr(sorted(payload.items())).encode("utf-8")).hexdigest()


def _publisher_scope(normalized_url: str) -> str:
    host = urlsplit(str(normalized_url or "").strip()).netloc.casefold()
    return host[4:] if host.startswith("www.") else host


def _normalized_report_title(request: BrowserReportDownloadRequest) -> str:
    title = str(request.report_title or "").strip()
    if not title and request.candidate_trace is not None:
        title = str(request.candidate_trace.title or "").strip()
    return " ".join(title.casefold().split())


def _hash_file(path: Path) -> tuple[str, str, int]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest(), size


def _try_reuse_artifact_acquisition_cache(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
) -> BrowserReportDownloadResult | None:
    publisher_scope = _publisher_scope(normalized_url)
    report_title = _normalized_report_title(request)
    cache_key = _artifact_cache_key(
        normalized_url=normalized_url,
        publisher_scope=publisher_scope,
        report_title=report_title,
    )
    cached = get_artifact_acquisition_cache(
        StateArtifactAcquisitionCacheGetRequest(
            schema_version="1.0",
            state_db=request.settings.state_db,
            cache_key=cache_key,
        ),
        ctx,
    )
    if cached is None:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="artifact_acquisition_cache_miss",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "cache_key": cache_key,
                    "reason": "missing",
                },
            )
        )
        return None
    now = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        expires_at = datetime.fromisoformat(
            cached.expires_at_utc.replace("Z", "+00:00")
        )
    except ValueError:
        expires_at = now - timedelta(seconds=1)
    path = Path(cached.artifact_path)
    if expires_at < now or not path.exists() or not path.is_file():
        reason = "expired" if expires_at < now else "artifact_missing"
        logger.info(
            log_event(
                ctx,
                role="service",
                event="artifact_acquisition_cache_rejected",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "cache_key": cache_key,
                    "reason": reason,
                    "artifact_path": str(path),
                },
            )
        )
        return None
    md5, sha256, size = _hash_file(path)
    if (
        md5 != cached.artifact_md5
        or sha256 != cached.artifact_sha256
        or size != cached.size_bytes
    ):
        logger.info(
            log_event(
                ctx,
                role="service",
                event="artifact_acquisition_cache_rejected",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "cache_key": cache_key,
                    "reason": "hash_mismatch",
                    "artifact_path": str(path),
                    "cached_md5": cached.artifact_md5,
                    "observed_md5": md5,
                },
            )
        )
        return None
    try:
        http_runtime.validate_downloaded_pdf_artifact(
            downloaded_path=path,
            downloaded_mime_type=cached.downloaded_mime_type,
            normalized_url=normalized_url,
        )
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="artifact_acquisition_cache_rejected",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "cache_key": cache_key,
                    "reason": exc.code,
                    "artifact_path": str(path),
                },
            )
        )
        return None
    logger.info(
        log_event(
            ctx,
            role="service",
            event="artifact_acquisition_cache_hit",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "cache_key": cache_key,
                "artifact_path": str(path),
                "artifact_md5": md5,
                "avoided_browser_or_http_acquisition": True,
            },
        )
    )
    return _build_pdf_result(
        request=request,
        normalized_url=normalized_url,
        final_url=cached.final_artifact_url or normalized_url,
        resolved_target_url=cached.final_artifact_url or normalized_url,
        downloaded_path=path,
        downloaded_mime_type=cached.downloaded_mime_type,
        browser_had_structured_result=False,
        used_candidate_pdf_url=False,
        terminal_text_excerpt="Reused validated artifact acquisition cache.",
    )


def _record_artifact_acquisition_cache(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    result: BrowserReportDownloadResult,
) -> dict[str, Any]:
    if result.outcome != "downloaded" or not result.downloaded_file_path:
        return {}
    path = Path(result.downloaded_file_path)
    if not path.exists() or not path.is_file():
        return {}
    try:
        http_runtime.validate_downloaded_pdf_artifact(
            downloaded_path=path,
            downloaded_mime_type=result.downloaded_mime_type,
            normalized_url=normalized_url,
        )
    except AppError:
        return {}
    md5, sha256, size = _hash_file(path)
    publisher_scope = _publisher_scope(normalized_url)
    report_title = _normalized_report_title(request)
    cache_key = _artifact_cache_key(
        normalized_url=normalized_url,
        publisher_scope=publisher_scope,
        report_title=report_title,
    )
    expires_at = (
        (
            datetime.now(timezone.utc).replace(microsecond=0)
            + timedelta(days=ARTIFACT_ACQUISITION_CACHE_TTL_DAYS)
        )
        .isoformat()
        .replace("+00:00", "Z")
    )
    record_artifact_acquisition_cache(
        StateArtifactAcquisitionCacheRecordRequest(
            schema_version="1.0",
            state_db=request.settings.state_db,
            cache_key=cache_key,
            normalized_url=normalized_url,
            publisher_scope=publisher_scope,
            report_title=report_title,
            final_artifact_url=result.resolved_target_url or result.final_page_url,
            artifact_path=str(path),
            artifact_md5=md5,
            artifact_sha256=sha256,
            route_kind=result.route_kind,
            route_family=result.route_family,
            outcome=result.outcome,
            downloaded_mime_type=result.downloaded_mime_type or "",
            size_bytes=size,
            cache_version=ARTIFACT_ACQUISITION_CACHE_VERSION,
            expires_at_utc=expires_at,
        ),
        ctx,
    )
    return {
        "artifact_sha256": sha256,
        "artifact_size_bytes": size,
    }


def _complete_browser_download_result(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    result: BrowserReportDownloadResult,
) -> BrowserReportDownloadResult:
    artifact_metadata = _record_artifact_acquisition_cache(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        result=result,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_complete",
            module=logger.name,
            fields=browser_download_result_log_fields(
                result,
                **artifact_metadata,
            ),
        )
    )
    return result


def _remembered_unattended_blocker_result(
    *,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
    execution_url: str,
) -> BrowserReportDownloadResult | None:
    if str(request.route_family_hint or "").strip() != "browser_email_form":
        return None
    remembered_text = " ".join(
        [
            str(request.route_hint or ""),
            " ".join(
                f"{step.action} {step.target_text} {step.result}"
                for step in request.route_step_hints
            ),
        ]
    ).casefold()
    is_interactive_captcha = (
        "captcha" in remembered_text or "recaptcha" in remembered_text
    ) and any(
        marker in remembered_text
        for marker in (
            "interactive",
            "challenge",
            "not a robot",
            "human verification",
            "verify you are human",
        )
    )
    is_access_forbidden = (
        "http 403" in remembered_text or "403 forbidden" in remembered_text
    ) and any(
        marker in remembered_text
        for marker in ("access", "forbidden", "inaccessible", "prevented")
    )
    if is_interactive_captcha:
        detail = (
            "Remembered exact route is blocked by an interactive CAPTCHA challenge."
        )
        target_text = "interactive CAPTCHA"
        blocker_title = "Interactive CAPTCHA blocker"
        signal_labels = ["remembered_interactive_captcha"]
        evidence_labels = [
            "blocked",
            "remembered_interactive_captcha",
            "blocked_captcha",
        ]
        blocked_reason = "blocked_captcha"
    elif is_access_forbidden:
        detail = (
            "Remembered exact route is blocked by HTTP 403 Forbidden access control."
        )
        target_text = "HTTP 403 Forbidden"
        blocker_title = "HTTP 403 access blocker"
        signal_labels = ["remembered_access_forbidden"]
        evidence_labels = [
            "blocked",
            "remembered_access_forbidden",
            "blocked_static_archive",
        ]
        blocked_reason = "blocked_static_archive"
    else:
        return None
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind="email_delivery",
        route_family="browser_email_form",
        route_status="inferred",
        outcome="email_required",
        route_summary=detail,
        final_page_url=execution_url,
        resolved_target_url=execution_url,
        used_route_hint=True,
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="memory_blocker",
                target_text=target_text,
                target_role="remembered_route",
                target_url=execution_url,
                result=detail,
            )
        ],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=False,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=execution_url,
            confirmation_score=0,
            signal_labels=signal_labels,
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=execution_url,
            final_page_title=blocker_title,
            terminal_text_excerpt=detail,
            artifact_url=execution_url,
            artifact_kind="email_delivery",
            artifact_validation_status="blocked",
            artifact_validation_detail=detail,
            confirmation_signal_count=0,
            traversed_page_urls=[execution_url],
            evidence_labels=evidence_labels,
        ),
        browser_had_structured_result=False,
        used_candidate_pdf_url=False,
        used_candidate_source_page=False,
        encountered_form_fields=[],
        blocked_reason=blocked_reason,
        blocked_reason_detail=detail,
        downloaded_file_path=None,
        downloaded_file_name=None,
        downloaded_mime_type=None,
        downloaded_size_bytes=None,
        onsite_capture_path=None,
        onsite_capture_format=None,
        onsite_page_count=None,
        onsite_completeness_status=None,
    )


def _captcha_handoff_enabled(request: BrowserReportDownloadRequest) -> bool:
    policy = request.settings.captcha_handoff_policy
    return bool(policy.enabled) and float(policy.timeout_seconds) > 0


def _result_is_blocked_captcha(result: BrowserReportDownloadResult) -> bool:
    if str(result.blocked_reason or "").strip() == "blocked_captcha":
        return True
    labels = set(result.terminal_evidence.evidence_labels)
    return "blocked_captcha" in labels


def _with_captcha_handoff_request(
    request: BrowserReportDownloadRequest,
) -> BrowserReportDownloadRequest:
    policy = request.settings.captcha_handoff_policy
    handoff_timeout_seconds = max(float(policy.timeout_seconds), 1.0)
    runtime_timeout_seconds = max(
        float(request.settings.timeout_seconds),
        handoff_timeout_seconds + 60.0,
    )
    instruction = (
        "CAPTCHA manual handoff is enabled for this attempt. Re-run the normal "
        "report acquisition route in the visible headed browser until a CAPTCHA "
        "challenge is actually visible. Do not wait on the initial landing page "
        "or an unsubmitted form. When a CAPTCHA challenge appears, stop "
        "automation and wait up to "
        f"{handoff_timeout_seconds:.0f} seconds for the operator to complete it. "
        "Do not solve or bypass CAPTCHA automatically. Do not finish the task, "
        "call done, or return blocked_captcha when the CAPTCHA first appears. "
        "Poll the visible page until the challenge iframe disappears, a verified "
        "state appears, or the handoff window expires. If the operator completes "
        "the challenge, continue the report request flow and verify the terminal "
        "state. Return blocked_captcha only after the full handoff window expires "
        "without operator completion, with manual_captcha_handoff_timeout "
        "evidence."
    )
    route_hint = str(request.route_hint or "").strip()
    if route_hint:
        route_hint = f"{route_hint}\n\n{instruction}"
    else:
        route_hint = instruction
    return replace(
        request,
        route_hint=route_hint,
        route_family_hint=request.route_family_hint or "browser_email_form",
        settings=replace(
            request.settings,
            headed=True,
            timeout_seconds=runtime_timeout_seconds,
            captcha_handoff_policy=replace(policy, enabled=False),
        ),
    )


def _captcha_handoff_timeout_result(
    *,
    fallback_result: BrowserReportDownloadResult,
    timeout_seconds: float,
    detail: str | None = None,
) -> BrowserReportDownloadResult:
    message = detail or (
        "Manual CAPTCHA handoff timed out after "
        f"{timeout_seconds:.0f} seconds; no operator completion was observed."
    )
    route_steps = list(fallback_result.route_steps)
    route_steps.append(
        BrowserDownloadRouteStep(
            schema_version="1.0",
            index=len(route_steps),
            action="manual_handoff",
            target_text="CAPTCHA challenge",
            target_role="headed_browser_operator_handoff",
            target_url=fallback_result.final_page_url,
            result=message,
            expected_evidence=["confirmation_text", "page_info"],
            observed_evidence=["page_info"],
            verification_status="missing",
        )
    )
    confirmation_labels = [
        *fallback_result.confirmation_evidence.signal_labels,
        "manual_captcha_handoff_timeout",
    ]
    terminal_labels = [
        *fallback_result.terminal_evidence.evidence_labels,
        "manual_captcha_handoff_timeout",
        "blocked_captcha",
    ]
    return replace(
        fallback_result,
        route_summary=message,
        route_steps=route_steps,
        confirmation_evidence=replace(
            fallback_result.confirmation_evidence,
            signal_labels=list(dict.fromkeys(confirmation_labels)),
        ),
        terminal_evidence=replace(
            fallback_result.terminal_evidence,
            artifact_validation_status="blocked",
            artifact_validation_detail=message,
            terminal_text_excerpt=message,
            evidence_labels=list(dict.fromkeys(terminal_labels)),
        ),
        blocked_reason="blocked_captcha",
        blocked_reason_detail=message,
        browser_had_structured_result=False,
    )


def _attempt_captcha_manual_handoff(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    delivery_email: str | None,
    browser_preflight_response: Any,
    fallback_result: BrowserReportDownloadResult,
) -> BrowserReportDownloadResult:
    timeout_seconds = max(
        float(request.settings.captcha_handoff_policy.timeout_seconds), 1.0
    )
    handoff_request = _with_captcha_handoff_request(request)
    if not handoff_request.selected_playbooks:
        handoff_request = attach_browser_route_playbooks(
            request=handoff_request,
            ctx=ctx,
            normalized_url=normalized_url,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_captcha_handoff_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "execution_url": execution_url,
                "timeout_seconds": timeout_seconds,
                "headed": handoff_request.settings.headed,
            },
        )
    )
    prompt_bundle = render_browser_report_download_prompt(
        request=handoff_request,
        ctx=ctx,
        normalized_url=normalized_url,
        execution_url=execution_url,
        download_dir=download_dir,
        delivery_email=delivery_email,
    )
    try:
        browser_run = run_browser_report_download_agent(
            request=handoff_request,
            ctx=ctx,
            normalized_url=normalized_url,
            execution_url=execution_url,
            download_dir=download_dir,
            prompt_bundle=prompt_bundle,
        )
        response = finalize_browser_report_download_result(
            request=handoff_request,
            ctx=ctx,
            normalized_url=normalized_url,
            delivery_email=delivery_email,
            download_dir=download_dir,
            browser_run=browser_run,
        )
        observe_browser_preflight_agent_outcome(
            probe=browser_preflight_response.probe,
            result=response,
            ctx=ctx,
            normalized_url=normalized_url,
        )
    except AppError as exc:
        response = _captcha_handoff_timeout_result(
            fallback_result=fallback_result,
            timeout_seconds=timeout_seconds,
            detail=(
                f"Manual CAPTCHA handoff failed before completion: {exc.message}"
                if exc.code != "browser_download_agent_timeout"
                else None
            ),
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_captcha_handoff_complete",
            module=logger.name,
            fields=browser_download_result_log_fields(response),
        )
    )
    return response


def default_browser_doctor_verification_url() -> str:
    return _default_browser_doctor_verification_url()


def run_browser_developer_diagnostics(
    request: BrowserDeveloperDiagnosticsRequest,
    ctx: RunContext,
    *,
    browser_session_class=None,
) -> BrowserDeveloperDiagnosticsResult:
    return _run_browser_developer_diagnostics(
        request,
        ctx,
        browser_session_class=browser_session_class,
    )


def promote_validated_browser_route_result_to_playbook(
    *,
    playbook_dir: str,
    result: BrowserReportDownloadResult,
    ctx: RunContext,
    observed_at: str = "",
    write_file: bool = True,
):
    return _promote_validated_browser_route_result_to_playbook(
        playbook_dir=playbook_dir,
        result=result,
        ctx=ctx,
        observed_at=observed_at,
        write_file=write_file,
    )


def promote_private_api_evidence_to_browser_playbook(
    *,
    request: BrowserRoutePrivateApiPromotionRequest,
    ctx: RunContext,
):
    return _promote_private_api_evidence_to_browser_playbook(
        request=request,
        ctx=ctx,
    )


def detect_private_api_promotion_candidates(request, ctx):
    return _detect_private_api_promotion_candidates(request, ctx)


def execute_browser_route_playbook(
    request: BrowserRoutePlaybookExecutionRequest,
    ctx: RunContext,
):
    return _execute_browser_route_playbook(request, ctx)


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
        context.setdefault(
            "final_page_url", str(browser_run.final_page_url or "").strip()
        )
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
    cached_result = _try_reuse_artifact_acquisition_cache(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
    )
    if cached_result is not None:
        return _complete_browser_download_result(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            result=cached_result,
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
            fields=pre_browser_doc_type_prediction_log_fields(doc_type_prediction),
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
            return _complete_browser_download_result(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                result=report_page_pdf_link_result,
            )
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
            return _complete_browser_download_result(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                result=direct_pdf_result,
            )
        report_page_pdf_link_result = try_report_page_pdf_link_download(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
            page_url=normalized_execution_url,
        )
        if report_page_pdf_link_result is not None:
            return _complete_browser_download_result(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                result=report_page_pdf_link_result,
            )
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
        return _complete_browser_download_result(
            request=report_page_link_request,
            ctx=ctx,
            normalized_url=normalized_url,
            result=report_page_pdf_link_result,
        )

    static_email_gate_result = None
    if request.route_family_hint == "browser_email_form" and not delivery_email_value:
        static_email_gate_result = try_static_email_gate_probe(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            page_url=normalized_execution_url,
        )
    if static_email_gate_result is not None:
        return _complete_browser_download_result(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            result=static_email_gate_result,
        )

    direct_onsite_result = try_direct_onsite_capture(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
        page_url=normalized_execution_url,
    )
    if direct_onsite_result is not None:
        return _complete_browser_download_result(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            result=direct_onsite_result,
        )

    if static_email_gate_result is None:
        static_email_gate_result = try_static_email_gate_probe(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            page_url=normalized_execution_url,
        )
        if static_email_gate_result is not None:
            return _complete_browser_download_result(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                result=static_email_gate_result,
            )

    if request.route_family_hint == "browser_email_form":
        access_challenge_result = try_http_access_challenge_probe(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            page_url=normalized_execution_url,
            preflight=True,
        )
        if access_challenge_result is not None:
            return _complete_browser_download_result(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                result=access_challenge_result,
            )

    request = apply_browser_route_budget(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    validate_browser_runtime_settings(request)
    browser_preflight_response = try_browser_preflight_probe(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        execution_url=normalized_execution_url,
        download_dir=download_dir,
    )
    if browser_preflight_response.result is not None:
        return _complete_browser_download_result(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            result=browser_preflight_response.result,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_browser_preflight_escalation",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "execution_url": normalized_execution_url,
                "probe_status": browser_preflight_response.probe.status,
                "escalation_reason": browser_preflight_response.probe.escalation_reason,
                "candidate_pdf_url_count": len(
                    browser_preflight_response.probe.candidate_pdf_urls
                ),
                "observed_event_url_count": len(
                    browser_preflight_response.probe.observed_event_urls
                ),
                "preflight_duration_seconds": (
                    browser_preflight_response.probe.duration_seconds
                ),
                "avoided_agent_call": False,
                "false_negative_rate_sample": (
                    browser_preflight_response.probe.false_negative_rate_sample
                ),
                "evidence_labels": list(
                    browser_preflight_response.probe.evidence_labels
                ),
            },
        )
    )
    remembered_blocker_result = _remembered_unattended_blocker_result(
        request=request,
        normalized_url=normalized_url,
        execution_url=normalized_execution_url,
    )
    if remembered_blocker_result is not None:
        if _result_is_blocked_captcha(
            remembered_blocker_result
        ) and _captcha_handoff_enabled(request):
            response = _attempt_captcha_manual_handoff(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                execution_url=normalized_execution_url,
                download_dir=download_dir,
                delivery_email=delivery_email_value,
                browser_preflight_response=browser_preflight_response,
                fallback_result=remembered_blocker_result,
            )
            return _complete_browser_download_result(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                result=response,
            )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_remembered_blocker_complete",
                module=logger.name,
                fields=browser_download_result_log_fields(remembered_blocker_result),
            )
        )
        return remembered_blocker_result
    request = attach_browser_route_playbooks(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    private_api_result = try_private_api_playbook_download(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        execution_url=normalized_execution_url,
        download_dir=download_dir,
    )
    if private_api_result is not None:
        return _complete_browser_download_result(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            result=private_api_result,
        )
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
                return _complete_browser_download_result(
                    request=request,
                    ctx=ctx,
                    normalized_url=normalized_url,
                    result=access_challenge_result,
                )
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
        observe_browser_preflight_agent_outcome(
            probe=browser_preflight_response.probe,
            result=response,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        if _result_is_blocked_captcha(response) and _captcha_handoff_enabled(request):
            response = _attempt_captcha_manual_handoff(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                execution_url=normalized_execution_url,
                download_dir=download_dir,
                delivery_email=delivery_email_value,
                browser_preflight_response=browser_preflight_response,
                fallback_result=response,
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
    return _complete_browser_download_result(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        result=response,
    )


def attach_browser_route_playbooks(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
) -> BrowserReportDownloadRequest:
    if request.selected_playbooks:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_route_playbook_selection_preserved",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "selected_playbook_ids": [
                        item.playbook_id for item in request.selected_playbooks
                    ],
                },
            )
        )
        return request
    playbooks = load_browser_route_playbooks(
        playbook_dir=request.settings.route_playbook_dir,
        ctx=ctx,
    )
    selection = select_browser_route_playbooks(
        playbooks=playbooks,
        normalized_url=normalized_url,
        route_family_hint=request.route_family_hint or "",
        now=datetime.now(timezone.utc),
    )
    fields = {
        "normalized_url": normalized_url,
        "route_family_hint": request.route_family_hint or "",
        "route_playbook_dir": request.settings.route_playbook_dir,
        "route_playbook_stale_policy": request.settings.route_playbook_stale_policy,
        **serialize_playbook_selection_for_log(selection),
    }
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_route_playbook_selection",
            module=logger.name,
            fields=fields,
        )
    )
    stale_policy = str(request.settings.route_playbook_stale_policy or "").strip()
    if selection.stale_playbook_ids and stale_policy == "fail":
        raise AppError(
            code="browser_route_playbook_stale",
            message="A matching browser route playbook is stale",
            retryable=False,
            context=fields,
        )
    return replace(request, selected_playbooks=list(selection.selected_playbooks))
