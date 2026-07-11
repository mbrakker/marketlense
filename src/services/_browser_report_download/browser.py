from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlsplit

import psutil

from src.contracts.browser_download import (
    BrowserDownloadDialogEvidence,
    BrowserDownloadNetworkEvent,
    BrowserReportDownloadRequest,
)
from src.contracts.openai import OpenAIUsageAccountingRequest
from src.contracts.run_context import RunContext
from src.services import llm_service, openai_accounting_service
from src.services._browser_report_download.cdp import (
    capture_print_pdf_via_cdp,
    collect_terminal_dialog_evidence_via_cdp,
    collect_terminal_network_entries_via_cdp,
    ensure_browser_download_target_hygiene_via_cdp,
)
from src.services._browser_report_download.helpers import (
    browser_helper_capture_screenshot,
    browser_helper_form_autocomplete,
    browser_helper_standard_form_submit,
    browser_helper_js,
    browser_helper_page_info,
)
from src.services._browser_report_download.http import (
    download_pdf_from_url,
    is_pdf_file,
)
from src.services._browser_report_download.models import (
    BrowserAgentRunResult,
    BrowserUseAgentResult,
)
from src.services._browser_report_download.prompt import (
    BrowserDownloadPromptBundle,
    redact_browser_report_download_prompt_for_log,
)
from src.services._browser_report_download.request import (
    resolve_delivery_email_value,
    resolve_effective_identity_fields,
)
from src.services._browser_report_download.session_reuse import (
    finalize_browser_session_reuse,
    resolve_browser_session_reuse,
)
from src.utils.coercion import normalize_optional_bool_signal
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.services._browser_report_download._browser_runtime import (
    _TERMINAL_TRANSIENT_MARKERS,
    _TERMINAL_SUCCESS_URL_MARKERS,
    _TERMINAL_SUCCESS_TEXT_MARKERS,
    _TERMINAL_REPORT_TEXT_MARKERS,
    _TERMINAL_TEXT_EXCERPT_MAX_CHARS,
    _TERMINAL_STABILIZATION_DEFAULT_POLL_SCHEDULE_SECONDS,
    _TERMINAL_STABILIZATION_EMAIL_POLL_SCHEDULE_SECONDS,
    _AGENT_RUN_TIMEOUT_MIN_BUFFER_SECONDS,
    _AGENT_RUN_TIMEOUT_STEP_BUFFER_SECONDS,
    _AGENT_RUN_TIMEOUT_MAX_BUFFER_SECONDS,
    _BROWSER_KILL_TIMEOUT_SECONDS,
    _BROWSER_RESET_TIMEOUT_SECONDS,
    _BROWSER_CLEANUP_GRACE_SECONDS,
    _BROWSER_PROFILE_DIR_PREFIX,
    _BROWSER_USE_TEMP_DIR_PATTERNS,
    _STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS,
    _TEMP_CLEANUP_LOG_SAMPLE_LIMIT,
    _TIMED_OUT_COMPLETED_HISTORY_GRACE_SECONDS,
    _TIMED_OUT_RECOVERY_OPERATION_TIMEOUT_SECONDS,
    _AGENT_COMPLETED_HISTORY_POLL_SECONDS,
    _BROWSER_AGENT_WORKER_ENV,
    _BROWSER_AGENT_WORKER_TIMEOUT_BUFFER_SECONDS,
    _BROWSER_AGENT_WORKER_OUTPUT_MAX_CHARS,
    _ANSI_ESCAPE_PATTERN,
    _BROWSER_AGENT_USE_JUDGE,
    _LOOKUP_FIELD_MARKERS,
    _LOOKUP_FAILURE_MARKERS,
    _LOOKUP_SUBMIT_MARKERS,
    _EMAIL_DOMAIN_BLOCK_MARKERS,
    _EMAIL_DOMAIN_FAILURE_MARKERS,
    _PARTIAL_HISTORY_TEXT_MAX_CHARS,
)
from src.services._browser_report_download._browser_runtime.terminal_state import (
    TerminalSnapshot,
    TerminalStabilizationPolicy,
    TerminalQuorumAssessment,
    _capture_terminal_snapshot,
    _stabilize_terminal_snapshot,
    _terminal_stabilization_reason,
    _resolve_terminal_stabilization_policy,
    _assess_terminal_snapshot_quorum,
    _assessment_meets_terminal_quorum,
    _terminal_quorum_text,
    _dedupe_labels,
    _contains_transient_terminal_marker,
    _merge_terminal_snapshots,
)
from src.services._browser_report_download._browser_runtime.terminal_assets import (
    _parse_raw_model_response,
    _prefetch_structured_pdf_artifact,
    _materialize_external_artifacts,
    _local_artifact_candidate_paths,
    _copy_external_artifact,
    _safe_resolve_path,
    _is_within_directory,
    _structured_pdf_candidate_urls,
    _looks_like_pdf_resource_url,
    _pdf_prefetch_destination_path,
    _capture_terminal_assets,
    _capture_terminal_dialog_evidence,
    _ensure_terminal_target_hygiene,
    _read_browser_closed_popup_dialog_evidence,
    _parse_closed_popup_message,
    _dedupe_browser_dialog_evidence,
    _maybe_capture_print_pdf_fallback,
    _should_capture_print_pdf_fallback,
    _browser_visible_text_from_html,
    _browser_text_has_non_report_marker,
    _browser_rendered_pdf_capture_path,
    _capture_completed_history_terminal_assets,
    _collect_network_resource_urls,
    _collect_network_events,
    _collect_network_events_via_cdp,
    _network_events_from_raw_events,
    _merge_network_events,
    _classify_network_signal_kind,
    _collect_page_resource_urls,
    _collect_dom_candidate_urls,
    _coerce_evaluate_list,
    _extract_documentish_urls_from_html,
    _looks_like_documentish_url,
    _resolve_current_page,
    _read_history_final_page_url,
    _read_history_final_page_title,
    _copy_history_screenshot,
    _read_history_final_state,
    _read_history_attachment_paths,
    _read_page_url,
    _read_browser_current_page_url,
    _read_page_title,
    _read_browser_current_page_title,
    _read_page_html,
    _write_terminal_html_snapshot,
    _write_terminal_screenshot,
    _try_screenshot_call,
    _maybe_await,
    _await_browser_task,
    _await_in_current_or_thread,
    _run_awaitable,
)
from src.services._browser_report_download._browser_runtime.timeout_recovery import (
    _salvage_timed_out_browser_run,
    _build_cached_timed_out_browser_run,
    _salvage_timed_out_browser_run_unbounded,
    _should_attempt_lookup_submission_assist,
    _payload_has_lookup_submission_recovery_signal,
    _attempt_lookup_submission_assist,
    _browser_form_identity_field_values,
    _attempt_lookup_submission_assist_with_timeout,
    _should_attempt_standard_form_submit_assist,
    _should_attempt_timeout_standard_form_submit_assist,
    _attempt_standard_form_submit_assist_with_timeout,
    _browser_standard_form_identity_field_values,
)
from src.services._browser_report_download._browser_runtime.worker_protocol import (
    BrowserAgentWorkerPayload,
    BrowserAgentWorkerResponse,
    _should_run_browser_agent_in_subprocess,
    _run_browser_report_download_agent_subprocess,
    _discard_browser_agent_worker_payload,
    _normalize_browser_worker_output_excerpt,
    _deserialize_browser_agent_run_result,
)
from src.services._browser_report_download._browser_runtime.session_lifecycle import (
    BrowserAgentHistoryResult,
    _SyntheticHistoryState,
    _SyntheticHistoryEntry,
    _SyntheticActionResult,
    _SyntheticAgentHistory,
    _run_agent_history_with_timeout,
    _read_lookup_blocker_partial_history,
    _read_terminal_blocker_partial_history,
    _read_email_domain_blocker_partial_history,
    _collect_agent_history_text,
    _serialize_history_fragment,
    _resolve_lookup_blocker_label,
    _infer_encountered_form_fields,
    _truncate_partial_history_excerpt,
    _read_distinct_history_urls,
    _read_completed_agent_history,
    _resolve_agent_run_timeout_seconds,
    _signal_agent_stop,
    _prime_agent_timing_fields,
    _log_browser_cleanup_failure,
    _prepare_browser_for_shutdown,
    _cleanup_browser_profile_dir,
    _new_managed_browser_profile_dir,
    _default_session_reuse_base_dir,
    _cleanup_managed_browser_profile_dirs,
    _cleanup_stale_browser_use_temp_dirs,
    _cleanup_new_browser_use_temp_dirs,
    _list_browser_use_temp_dirs,
    _remove_browser_use_temp_dirs,
    _kill_browser,
    _kill_browser_with_timeout,
    _force_stop_local_browser_process,
)

logger = logging.getLogger("market_lense.browser_report_download_service")


def _mark_lookup_submission_assisted_raw_response(raw_model_response: str) -> str:
    payload = _parse_raw_model_response(raw_model_response)
    if not payload:
        return raw_model_response
    payload["route_kind"] = str(payload.get("route_kind") or "email_delivery")
    payload["route_family"] = str(payload.get("route_family") or "browser_email_form")
    payload["email_submission_completed"] = True
    payload["blocked_reason"] = None
    payload["blocked_reason_detail"] = None
    payload["route_summary"] = (
        str(payload.get("route_summary") or "").strip()
        or "Recovered a required lookup field and submitted the report request form."
    )
    route_steps = payload.get("route_steps")
    if not isinstance(route_steps, list):
        route_steps = []
    route_steps.append(
        {
            "index": len(route_steps) + 1,
            "action": "submit",
            "target_text": "Recovered required lookup field",
            "target_role": "browser_helper_form_autocomplete",
            "target_url": str(payload.get("final_page_url") or "").strip(),
            "result": "Selected the required lookup option and submitted the form.",
            "expected_evidence": ["confirmation_text", "page_info", "network_event"],
            "observed_evidence": [],
            "verification_status": "pending_terminal_verification",
        }
    )
    payload["route_steps"] = route_steps
    return json.dumps(payload, ensure_ascii=True)


def _mark_standard_form_submit_assisted_raw_response(raw_model_response: str) -> str:
    payload = _parse_raw_model_response(raw_model_response)
    if not payload:
        return raw_model_response
    payload["route_kind"] = str(payload.get("route_kind") or "email_delivery")
    payload["route_family"] = str(payload.get("route_family") or "browser_email_form")
    payload["email_submission_completed"] = True
    payload["blocked_reason"] = None
    payload["blocked_reason_detail"] = None
    payload["route_summary"] = (
        str(payload.get("route_summary") or "").strip()
        or "Recovered standard required form controls and submitted the report request form."
    )
    route_steps = payload.get("route_steps")
    if not isinstance(route_steps, list):
        route_steps = []
    route_steps.append(
        {
            "index": len(route_steps) + 1,
            "action": "submit",
            "target_text": "Recovered standard required form controls",
            "target_role": "browser_helper_standard_form_submit",
            "target_url": str(payload.get("final_page_url") or "").strip(),
            "result": (
                "Filled safe standard fields, selected required standard dropdowns, "
                "checked mandatory legal/report-delivery agreements, and submitted."
            ),
            "expected_evidence": ["confirmation_text", "page_info", "network_event"],
            "observed_evidence": [],
            "verification_status": "pending_terminal_verification",
        }
    )
    payload["route_steps"] = route_steps
    return json.dumps(payload, ensure_ascii=True)


def _pre_llm_standard_form_raw_response(
    *,
    final_url: str,
    resolved_fields: list[str],
) -> str:
    return json.dumps(
        {
            "route_kind": "email_delivery",
            "route_family": "browser_email_form",
            "route_summary": (
                "Filled configured identity fields and submitted the report request "
                "form before invoking browser-use."
            ),
            "final_page_url": final_url,
            "resolved_target_url": final_url,
            "email_submission_completed": True,
            "post_submit_message": "Submitted by deterministic pre-LLM form autofill.",
            "confirmation_url_changed": True,
            "submit_button_state": "submitted",
            "form_disappeared": True,
            "encountered_form_fields": resolved_fields,
            "route_steps": [
                {
                    "index": 0,
                    "action": "submit",
                    "target_text": "Configured identity and consent fields",
                    "target_role": "browser_helper_standard_form_submit",
                    "target_url": final_url,
                    "result": "Submitted deterministically before browser-use.",
                    "expected_evidence": ["confirmation_text", "page_info"],
                    "observed_evidence": ["page_info"],
                    "verification_status": "pending_terminal_verification",
                }
            ],
        },
        ensure_ascii=True,
    )


def _open_current_page_for_pre_llm_autofill(
    *,
    browser: Any,
    execution_url: str,
    ctx: RunContext,
    normalized_url: str,
) -> Any | None:
    page = _resolve_current_page(browser)
    if page is None:
        return None
    goto = getattr(page, "goto", None)
    if callable(goto):
        try:
            _run_awaitable(goto(execution_url))
        except Exception as exc:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_pre_llm_autofill_navigation_failed",
                    module=logger.name,
                    fields={"normalized_url": normalized_url, "error": str(exc)},
                )
            )
            return page
        return page
    try:
        browser_helper_js(
            page=page,
            expression=(
                "window.location.href = "
                f"{json.dumps(execution_url, ensure_ascii=True)}; "
                "return {status: 'navigation_requested'};"
            ),
            ctx=ctx,
            normalized_url=normalized_url,
        )
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_pre_llm_autofill_navigation_failed",
                module=logger.name,
                fields={"normalized_url": normalized_url, "error": exc.message},
            )
        )
    return page


def _try_pre_llm_standard_form_submit(
    *,
    request: BrowserReportDownloadRequest,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
) -> BrowserAgentRunResult | None:
    if str(request.route_family_hint or "").strip() != "browser_email_form":
        return None
    field_values = _browser_standard_form_identity_field_values(request)
    if not field_values:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_pre_llm_autofill_skipped",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "reason": "no_identity_fields",
                },
            )
        )
        return None
    page = _open_current_page_for_pre_llm_autofill(
        browser=browser,
        execution_url=execution_url,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if page is None:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_pre_llm_autofill_escalated",
                module=logger.name,
                fields={"normalized_url": normalized_url, "reason": "page_unavailable"},
            )
        )
        return None
    helper_result = browser_helper_standard_form_submit(
        page=page,
        field_values=field_values,
        ctx=ctx,
        normalized_url=normalized_url,
        browser=browser,
    )
    if helper_result.status != "ok" or not helper_result.submitted:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_pre_llm_autofill_escalated",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "status": helper_result.status,
                    "submitted": helper_result.submitted,
                    "unresolved_fields": list(helper_result.unresolved_fields),
                    "blocker_code": helper_result.blocker_code or "",
                },
            )
        )
        return None
    snapshot = _capture_terminal_snapshot(
        browser, ctx=ctx, normalized_url=normalized_url
    )
    final_url = helper_result.final_url or snapshot.url or execution_url
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_pre_llm_autofill_submitted",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "filled_count": helper_result.filled_count,
                "selected_count": helper_result.selected_count,
                "mandatory_agreement_checked_count": (
                    helper_result.mandatory_agreement_checked_count
                ),
                "resolved_fields": list(helper_result.resolved_fields),
                "avoided_llm_call": True,
            },
        )
    )
    return BrowserAgentRunResult(
        schema_version="1.0",
        raw_model_response=_pre_llm_standard_form_raw_response(
            final_url=final_url,
            resolved_fields=list(helper_result.resolved_fields),
        ),
        final_page_url=final_url,
        final_page_title=snapshot.title,
        final_page_html=snapshot.html,
        downloaded_files=[],
        attachment_paths=[],
        network_resource_urls=[],
        network_events=[],
        html_snapshot_path="",
        screenshot_path="",
        print_pdf_capture_path="",
        print_pdf_capture_provenance="",
        dialog_evidence=[],
    )


def run_browser_report_download_agent(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    prompt_bundle: BrowserDownloadPromptBundle,
) -> BrowserAgentRunResult:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_request",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "execution_url": execution_url,
                "route_family_hint": request.route_family_hint or "",
                "prompt_namespace": prompt_bundle.namespace,
                "task_prompt": redact_browser_report_download_prompt_for_log(
                    request=request,
                    text=prompt_bundle.task_prompt,
                    delivery_email=resolve_delivery_email_value(request),
                ),
                "agent_use_judge": _BROWSER_AGENT_USE_JUDGE,
            },
        )
    )
    browser_use = _load_browser_use_runtime(normalized_url)
    if _should_run_browser_agent_in_subprocess(browser_use, request=request):
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_worker_dispatch",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "download_dir": str(download_dir),
                },
            )
        )
        return _run_browser_report_download_agent_subprocess(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            execution_url=execution_url,
            download_dir=download_dir,
            prompt_bundle=prompt_bundle,
        )
    browser: Any | None = None
    _cleanup_stale_browser_use_temp_dirs(ctx=ctx, normalized_url=normalized_url)
    preexisting_temp_dirs = {str(path) for path in _list_browser_use_temp_dirs()}
    session_reuse_decision = resolve_browser_session_reuse(
        policy=request.settings.session_reuse_policy,
        default_base_dir=_default_session_reuse_base_dir(request, download_dir),
        normalized_url=normalized_url,
        ctx=ctx,
    )
    _cleanup_managed_browser_profile_dirs(
        download_dir=download_dir,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    profile_dir = (
        Path(session_reuse_decision.profile_path).resolve()
        if session_reuse_decision.accepted and session_reuse_decision.profile_path
        else _new_managed_browser_profile_dir(download_dir)
    )
    profile_dir.mkdir(parents=True, exist_ok=True)
    raw_model_response = ""
    final_page_url = ""
    final_page_title = ""
    final_page_html = ""
    downloaded_files: list[str] = []
    attachment_paths: list[str] = []
    network_resource_urls: list[str] = []
    network_events: list[BrowserDownloadNetworkEvent] = []
    html_snapshot_path = ""
    screenshot_path = ""
    print_pdf_capture_path = ""
    print_pdf_capture_provenance = ""
    dialog_evidence: list[BrowserDownloadDialogEvidence] = []
    try:
        browser = browser_use.Browser(
            downloads_path=str(download_dir),
            user_data_dir=str(profile_dir),
            headless=not request.settings.headed,
            auto_download_pdfs=True,
            keep_alive=True,
        )
        pre_llm_form_result = _try_pre_llm_standard_form_submit(
            request=request,
            browser=browser,
            ctx=ctx,
            normalized_url=normalized_url,
            execution_url=execution_url,
        )
        if pre_llm_form_result is not None:
            return pre_llm_form_result
        llm_clients = llm_service.build_browser_use_llm_clients(
            settings=request.settings,
            ctx=ctx,
            openai_client_factory=getattr(browser_use, "ChatOpenAI", None),
            openrouter_client_factory=getattr(browser_use, "ChatOpenRouter", None),
        )
        agent_kwargs = {
            "task": prompt_bundle.task_prompt,
            "llm": llm_clients.primary_llm,
            "browser": browser,
            "output_model_schema": BrowserUseAgentResult,
            "use_judge": _BROWSER_AGENT_USE_JUDGE,
        }
        agent_parameters = inspect.signature(browser_use.Agent).parameters
        if "calculate_cost" in agent_parameters:
            agent_kwargs["calculate_cost"] = True
        if (
            llm_clients.fallback_llm is not None
            and "fallback_llm" in agent_parameters
        ):
            agent_kwargs["fallback_llm"] = llm_clients.fallback_llm
        agent = browser_use.Agent(**agent_kwargs)
        history_result = _run_agent_history_with_timeout(
            agent=agent,
            browser=browser,
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        history = history_result.history
        _record_browser_use_agent_usage(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            prompt_bundle=prompt_bundle,
            llm_clients=llm_clients,
            agent=agent,
            history=history,
        )
        raw_model_response = str(history.final_result() or "").strip()
        history_final_page_url = _read_history_final_page_url(history)
        history_final_page_title = _read_history_final_page_title(history)
        attachment_paths = _read_history_attachment_paths(history)
        history_screenshot_path = _copy_history_screenshot(
            history=history,
            download_dir=download_dir,
        )
        downloaded_files = [
            str(path) for path in getattr(browser, "downloaded_files", [])
        ]
        materialized_paths = _materialize_external_artifacts(
            raw_model_response=raw_model_response,
            attachment_paths=attachment_paths,
            downloaded_files=downloaded_files,
            download_dir=download_dir,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        for materialized_path in materialized_paths:
            if materialized_path not in attachment_paths:
                attachment_paths.append(materialized_path)
            if materialized_path not in downloaded_files:
                downloaded_files.append(materialized_path)
        prefetched_pdf_path = _prefetch_structured_pdf_artifact(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
            raw_model_response=raw_model_response,
            history_final_page_url=history_final_page_url,
        )
        if prefetched_pdf_path and prefetched_pdf_path not in downloaded_files:
            downloaded_files.append(prefetched_pdf_path)
        lookup_submission_assisted = False
        if _should_attempt_lookup_submission_assist(
            request=request,
            raw_model_response=raw_model_response,
        ):
            lookup_submission_assisted = _attempt_lookup_submission_assist_with_timeout(
                request=request,
                browser=browser,
                ctx=ctx,
                normalized_url=normalized_url,
                raw_model_response=raw_model_response,
            )
            if lookup_submission_assisted:
                raw_model_response = _mark_lookup_submission_assisted_raw_response(
                    raw_model_response
                )
        standard_form_submit_assisted = False
        if (
            not lookup_submission_assisted
            and _should_attempt_standard_form_submit_assist(
                request=request,
                raw_model_response=raw_model_response,
            )
        ):
            standard_form_submit_assisted = (
                _attempt_standard_form_submit_assist_with_timeout(
                    request=request,
                    browser=browser,
                    ctx=ctx,
                    normalized_url=normalized_url,
                )
            )
            if standard_form_submit_assisted:
                raw_model_response = _mark_standard_form_submit_assisted_raw_response(
                    raw_model_response
                )
        if (
            history_result.salvaged_completed_history
            and not lookup_submission_assisted
            and not standard_form_submit_assisted
        ):
            final_page_url = history_final_page_url
            final_page_title = history_final_page_title
            screenshot_path = history_screenshot_path
            dialog_evidence.extend(
                _capture_terminal_dialog_evidence(
                    browser=browser,
                    ctx=ctx,
                    normalized_url=normalized_url,
                    allow_beforeunload=False,
                    target_url=final_page_url,
                )
            )
            (
                network_resource_urls,
                network_events,
                screenshot_path,
            ) = _capture_completed_history_terminal_assets(
                browser=browser,
                download_dir=download_dir,
                final_page_url=final_page_url,
                route_family=request.route_family_hint or "",
                ctx=ctx,
                normalized_url=normalized_url,
                fallback_screenshot_path=screenshot_path,
            )
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_completed_history_capture_skipped",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "history_final_page_url": history_final_page_url,
                        "history_final_page_title": history_final_page_title,
                        "downloaded_file_count": len(downloaded_files),
                        "attachment_count": len(attachment_paths),
                        "browser_network_event_count": len(network_events),
                        "browser_network_resource_url_count": len(
                            network_resource_urls
                        ),
                        "browser_screenshot_path": screenshot_path,
                    },
                )
            )
        else:
            dialog_evidence.extend(
                _capture_terminal_dialog_evidence(
                    browser=browser,
                    ctx=ctx,
                    normalized_url=normalized_url,
                    allow_beforeunload=False,
                    target_url=history_final_page_url,
                )
            )
            terminal_snapshot = _capture_terminal_snapshot(
                browser,
                ctx=ctx,
                normalized_url=normalized_url,
            )
            terminal_snapshot = _stabilize_terminal_snapshot(
                browser=browser,
                raw_model_response=raw_model_response,
                route_family_hint=request.route_family_hint,
                snapshot=terminal_snapshot,
                ctx=ctx,
                normalized_url=normalized_url,
                trigger_reason=(
                    "lookup_submission_assist"
                    if lookup_submission_assisted
                    else (
                        "standard_form_submit_assist"
                        if standard_form_submit_assisted
                        else None
                    )
                ),
            )
            current_page = terminal_snapshot.page
            final_page_url = terminal_snapshot.url or history_final_page_url
            final_page_title = terminal_snapshot.title or history_final_page_title
            final_page_html = terminal_snapshot.html
            (
                network_resource_urls,
                network_events,
                html_snapshot_path,
                screenshot_path,
            ) = _capture_terminal_assets(
                browser=browser,
                page=current_page,
                download_dir=download_dir,
                final_page_url=final_page_url,
                final_page_html=final_page_html,
                route_family=request.route_family_hint or "",
                ctx=ctx,
                normalized_url=normalized_url,
            )
            if not screenshot_path:
                screenshot_path = history_screenshot_path
            print_pdf_capture_path = _maybe_capture_print_pdf_fallback(
                request=request,
                browser=browser,
                raw_model_response=raw_model_response,
                final_page_url=final_page_url,
                final_page_title=final_page_title,
                final_page_html=final_page_html,
                download_dir=download_dir,
                ctx=ctx,
                normalized_url=normalized_url,
                downloaded_files=downloaded_files,
                attachment_paths=attachment_paths,
            )
            print_pdf_capture_provenance = (
                "browser_rendered_print_to_pdf" if print_pdf_capture_path else ""
            )
    except AppError as exc:
        if exc.code == "browser_download_agent_timeout" and browser is not None:
            timed_out_form_assisted = False
            if _should_attempt_lookup_submission_assist(
                request=request,
                raw_model_response=raw_model_response,
            ):
                timed_out_form_assisted = (
                    _attempt_lookup_submission_assist_with_timeout(
                        request=request,
                        browser=browser,
                        ctx=ctx,
                        normalized_url=normalized_url,
                        raw_model_response=raw_model_response,
                    )
                )
            if not timed_out_form_assisted and (
                _should_attempt_timeout_standard_form_submit_assist(
                    request=request,
                    browser=browser,
                    raw_model_response=raw_model_response,
                )
            ):
                timed_out_form_assisted = (
                    _attempt_standard_form_submit_assist_with_timeout(
                        request=request,
                        browser=browser,
                        ctx=ctx,
                        normalized_url=normalized_url,
                    )
                )
            if timed_out_form_assisted and raw_model_response:
                raw_model_response = _mark_standard_form_submit_assisted_raw_response(
                    raw_model_response
                )
            salvaged_run = _salvage_timed_out_browser_run(
                request=request,
                browser=browser,
                ctx=ctx,
                normalized_url=normalized_url,
                download_dir=download_dir,
            )
            if salvaged_run is not None:
                return salvaged_run
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_failed",
                module=logger.name,
                fields={"normalized_url": normalized_url, "error": exc.message},
            )
        )
        raise
    except Exception as exc:
        if _is_browser_start_timeout_error(exc):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_failed",
                    module=logger.name,
                    fields={"normalized_url": normalized_url, "error": str(exc)},
                )
            )
            raise AppError(
                code="browser_download_browser_start_timeout",
                message="browser-use timed out while starting the local browser session",
                cause=exc,
                retryable=True,
                context={"normalized_url": normalized_url},
            ) from exc
        if _is_no_space_error(exc):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_failed",
                    module=logger.name,
                    fields={"normalized_url": normalized_url, "error": str(exc)},
                )
            )
            raise AppError(
                code="browser_download_storage_full",
                message="The browser download runtime ran out of local disk space",
                cause=exc,
                retryable=True,
                context={"normalized_url": normalized_url},
            ) from exc
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_failed",
                module=logger.name,
                fields={"normalized_url": normalized_url, "error": str(exc)},
            )
        )
        raise AppError(
            code="browser_download_agent_failed",
            message="browser-use failed to complete the report download task",
            cause=exc,
            retryable=True,
            context={"normalized_url": normalized_url},
        ) from exc
    finally:
        if browser is not None:
            dialog_evidence.extend(
                _capture_terminal_dialog_evidence(
                    browser=browser,
                    ctx=ctx,
                    normalized_url=normalized_url,
                    allow_beforeunload=True,
                    target_url=final_page_url,
                )
            )
            _prepare_browser_for_shutdown(
                browser,
                ctx=ctx,
                normalized_url=normalized_url,
            )
            _kill_browser_with_timeout(
                browser,
                ctx=ctx,
                normalized_url=normalized_url,
            )
        if session_reuse_decision.accepted:
            finalize_browser_session_reuse(
                decision=session_reuse_decision,
                ctx=ctx,
                normalized_url=normalized_url,
                verified_artifact_count=len(downloaded_files),
            )
        else:
            _cleanup_browser_profile_dir(
                profile_dir,
                ctx=ctx,
                normalized_url=normalized_url,
            )
        _cleanup_new_browser_use_temp_dirs(
            ctx=ctx,
            normalized_url=normalized_url,
            preexisting_temp_dirs=preexisting_temp_dirs,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "raw_model_response": raw_model_response,
                "downloaded_files": downloaded_files,
                "attachment_paths": attachment_paths,
                "browser_final_url": final_page_url,
                "browser_final_title": final_page_title,
                "browser_final_html_size": len(final_page_html),
                "browser_network_resource_url_count": len(network_resource_urls),
                "browser_network_event_count": len(network_events),
                "browser_dialog_evidence_count": len(dialog_evidence),
                "browser_html_snapshot_path": html_snapshot_path,
                "browser_screenshot_path": screenshot_path,
            },
        )
    )
    return BrowserAgentRunResult(
        schema_version="1.0",
        raw_model_response=raw_model_response,
        final_page_url=final_page_url,
        final_page_title=final_page_title,
        final_page_html=final_page_html,
        downloaded_files=downloaded_files,
        attachment_paths=attachment_paths,
        network_resource_urls=network_resource_urls,
        network_events=network_events,
        html_snapshot_path=html_snapshot_path,
        screenshot_path=screenshot_path,
        print_pdf_capture_path=print_pdf_capture_path,
        print_pdf_capture_provenance=print_pdf_capture_provenance,
        dialog_evidence=dialog_evidence,
    )


def _load_browser_use_runtime(normalized_url: str) -> Any:
    os.environ.setdefault("BROWSER_USE_SETUP_LOGGING", "false")
    try:
        return import_module("browser_use")
    except Exception as exc:
        raise AppError(
            code="browser_use_unavailable",
            message="The local browser_use runtime is not installed in this environment",
            cause=exc,
            retryable=False,
            context={"normalized_url": normalized_url},
        ) from exc


def _record_browser_use_agent_usage(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    prompt_bundle: BrowserDownloadPromptBundle,
    llm_clients: Any,
    agent: Any,
    history: Any,
) -> None:
    usage_entries = getattr(
        getattr(agent, "token_cost_service", None), "usage_history", None
    )
    if isinstance(usage_entries, list) and usage_entries:
        for index, entry in enumerate(usage_entries, start=1):
            usage = getattr(entry, "usage", None)
            if usage is None:
                continue
            model_name = str(getattr(entry, "model", "") or "")
            _record_browser_use_usage_row(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                prompt_bundle=prompt_bundle,
                llm_clients=llm_clients,
                model_name=model_name,
                input_tokens=_optional_usage_int(getattr(usage, "prompt_tokens", None)),
                output_tokens=_optional_usage_int(
                    getattr(usage, "completion_tokens", None)
                ),
                total_tokens=None,
                cached_tokens=_optional_usage_int(
                    getattr(usage, "prompt_cached_tokens", None)
                ),
                cost_usd=0.0,
                extra={
                    "browser_usage_entry_index": index,
                    "browser_usage_timestamp": str(
                        getattr(entry, "timestamp", "") or ""
                    ),
                    "browser_usage_entry_count": len(usage_entries),
                },
            )
        return
    usage = getattr(history, "usage", None)
    if usage is None:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_llm_usage_unavailable",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "reason": "history_usage_missing",
                    "primary_provider": getattr(llm_clients, "primary_provider", ""),
                    "primary_model": getattr(llm_clients, "primary_model", ""),
                },
            )
        )
        return
    by_model = getattr(usage, "by_model", None)
    model_rows = by_model if isinstance(by_model, dict) and by_model else {}
    if not model_rows:
        model_rows = {
            str(getattr(llm_clients, "primary_model", "") or "unknown"): usage
        }
    for model, stats in model_rows.items():
        input_tokens = _optional_usage_int(
            getattr(stats, "prompt_tokens", None)
            or getattr(stats, "total_prompt_tokens", None)
        )
        output_tokens = _optional_usage_int(
            getattr(stats, "completion_tokens", None)
            or getattr(stats, "total_completion_tokens", None)
        )
        total_tokens = _optional_usage_int(getattr(stats, "total_tokens", None))
        cached_tokens = _optional_usage_int(
            getattr(stats, "prompt_cached_tokens", None)
            or getattr(usage, "total_prompt_cached_tokens", None)
        )
        model_name = str(model or getattr(llm_clients, "primary_model", "") or "")
        _record_browser_use_usage_row(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            prompt_bundle=prompt_bundle,
            llm_clients=llm_clients,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
            cost_usd=float(
                getattr(stats, "cost", None) or getattr(usage, "total_cost", 0.0) or 0.0
            ),
            extra={
                "entry_count": _optional_usage_int(getattr(usage, "entry_count", None))
            },
        )


def _record_browser_use_usage_row(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    prompt_bundle: BrowserDownloadPromptBundle,
    llm_clients: Any,
    model_name: str,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    cached_tokens: int | None,
    cost_usd: float,
    extra: dict[str, Any],
) -> None:
    row_extra = {
        "browser_reported_cost_usd": cost_usd,
        "route_family_hint": request.route_family_hint or "",
        "route_kind_hint": request.route_kind_hint or "",
        "primary_provider": getattr(llm_clients, "primary_provider", ""),
        "fallback_provider": (getattr(llm_clients, "fallback_provider", "") or ""),
        **extra,
    }
    openai_accounting_service.record_usage(
        OpenAIUsageAccountingRequest(
            schema_version="1.0",
            step_name="browser_use_agent",
            model=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_input_tokens=cached_tokens,
            tool_calls=0,
            cost_ledger_path="./out/cost-ledger.jsonl",
            cost_daily_path="./out/cost-daily.json",
            model_pricing={},
            request_id=None,
            provider=_browser_usage_provider(
                model=model_name,
                llm_clients=llm_clients,
            ),
            action="browser_use_agent",
            usage_db_path="./state/llm_usage.sqlite",
            publisher_name="",
            report_name=_browser_usage_report_name(request),
            source_url=normalized_url,
            prompt_namespace=prompt_bundle.namespace,
            prompt_hash=prompt_bundle.user_prompt_sha256,
            provider_decision=_browser_usage_provider_decision(
                model=model_name,
                llm_clients=llm_clients,
            ),
            cache_decision="disabled",
            temperature=request.settings.temperature,
            seed=None,
            timeout_seconds=request.settings.timeout_seconds,
            extra=row_extra,
        ),
        ctx,
    )


def _optional_usage_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _browser_usage_report_name(request: BrowserReportDownloadRequest) -> str:
    candidate_trace = request.candidate_trace
    if candidate_trace is not None:
        title = str(getattr(candidate_trace, "title", "") or "").strip()
        if title:
            return title
    return ""


def _browser_usage_provider(*, model: str, llm_clients: Any) -> str:
    if model and model == str(getattr(llm_clients, "fallback_model", "") or ""):
        return str(getattr(llm_clients, "fallback_provider", "") or "openrouter")
    if model and model == str(getattr(llm_clients, "primary_model", "") or ""):
        return str(getattr(llm_clients, "primary_provider", "") or "openai")
    if "/" in model:
        return "openrouter"
    return str(getattr(llm_clients, "primary_provider", "") or "openai")


def _browser_usage_provider_decision(*, model: str, llm_clients: Any) -> str:
    provider = _browser_usage_provider(model=model, llm_clients=llm_clients)
    if provider == "openrouter":
        if str(getattr(llm_clients, "primary_provider", "") or "") == "openai":
            return "openrouter_fallback"
        return "openrouter_primary"
    return "openai_primary"


def _is_no_space_error(exc: BaseException) -> bool:
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return True
    return "no space left on device" in str(exc).casefold()


def _is_browser_start_timeout_error(exc: BaseException) -> bool:
    token = str(exc).casefold()
    return "browserstartevent" in token and "timed out" in token
