from __future__ import annotations

# Compatibility facade imports are consumed by decomposed browser runtime modules.
# ruff: noqa: F401
import asyncio
import inspect
import json
import logging
import os
import re
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
from typing import Any, Mapping
from urllib.parse import urlsplit

import psutil

from src.contracts._browser_download.session_reuse import (
    BrowserDownloadSessionReuseDecision,
)
from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadDialogEvidence,
    BrowserDownloadNetworkEvent,
    BrowserDownloadRouteStep,
    BrowserReportDownloadRequest,
    BrowserRoutePlaybook,
    BrowserRoutePlaybookExecutionRequest,
)
from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIUsageAccountingRequest
from src.contracts.pdf_text import PdfTextContainsRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.run_budget import (
    BudgetDecision,
    BudgetRequest,
    BudgetReservationReconcileRequest,
    BudgetSideEffectFinalizeRequest,
    RunBudget,
    RunBudgetUsage,
)
from src.contracts.run_context import RunContext
from src.services import llm_service, pdf_service, prompt_service
from src.services._browser_report_download._artifact.classification import (
    _build_confirmation_evidence,
    _confirmation_evidence_verifies_email_delivery,
    _upgrade_confirmation_evidence_from_terminal_html,
)
from src.services._browser_report_download._browser_runtime import (
    _AGENT_COMPLETED_HISTORY_POLL_SECONDS,
    _AGENT_RUN_TIMEOUT_MAX_BUFFER_SECONDS,
    _AGENT_RUN_TIMEOUT_MIN_BUFFER_SECONDS,
    _AGENT_RUN_TIMEOUT_STEP_BUFFER_SECONDS,
    _ANSI_ESCAPE_PATTERN,
    _BROWSER_AGENT_USE_JUDGE,
    _BROWSER_AGENT_WORKER_ENV,
    _BROWSER_AGENT_WORKER_OUTPUT_MAX_CHARS,
    _BROWSER_AGENT_WORKER_TIMEOUT_BUFFER_SECONDS,
    _BROWSER_CLEANUP_GRACE_SECONDS,
    _BROWSER_KILL_TIMEOUT_SECONDS,
    _BROWSER_PROFILE_DIR_PREFIX,
    _BROWSER_RESET_TIMEOUT_SECONDS,
    _BROWSER_USE_TEMP_DIR_PATTERNS,
    _EMAIL_DOMAIN_BLOCK_MARKERS,
    _EMAIL_DOMAIN_FAILURE_MARKERS,
    _LOOKUP_FAILURE_MARKERS,
    _LOOKUP_FIELD_MARKERS,
    _LOOKUP_SUBMIT_MARKERS,
    _PARTIAL_HISTORY_TEXT_MAX_CHARS,
    _STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS,
    _TEMP_CLEANUP_LOG_SAMPLE_LIMIT,
    _TERMINAL_REPORT_TEXT_MARKERS,
    _TERMINAL_STABILIZATION_DEFAULT_POLL_SCHEDULE_SECONDS,
    _TERMINAL_STABILIZATION_EMAIL_POLL_SCHEDULE_SECONDS,
    _TERMINAL_SUCCESS_TEXT_MARKERS,
    _TERMINAL_SUCCESS_URL_MARKERS,
    _TERMINAL_TEXT_EXCERPT_MAX_CHARS,
    _TERMINAL_TRANSIENT_MARKERS,
    _TIMED_OUT_COMPLETED_HISTORY_GRACE_SECONDS,
    _TIMED_OUT_RECOVERY_OPERATION_TIMEOUT_SECONDS,
)
from src.services._browser_report_download._browser_runtime.action_evidence import (
    capture_browser_execution_route_steps,
)
from src.services._browser_report_download._browser_runtime.no_progress import (
    BrowserNoProgressDetector,
    BrowserNoProgressObservation,
    mark_browser_teardown_intentional,
)
from src.services._browser_report_download._browser_runtime.runtime import (
    browser_runtime_identity,
    load_browser_use_runtime,
)
from src.services._browser_report_download._browser_runtime.session_lifecycle import (
    BrowserAgentHistoryResult,
    _cleanup_browser_profile_dir,
    _cleanup_managed_browser_profile_dirs,
    _cleanup_new_browser_use_temp_dirs,
    _cleanup_stale_browser_use_temp_dirs,
    _collect_agent_history_text,
    _default_session_reuse_base_dir,
    _force_stop_local_browser_process,
    _infer_encountered_form_fields,
    _kill_browser,
    _kill_browser_with_timeout,
    _list_browser_use_temp_dirs,
    _log_browser_cleanup_failure,
    _new_managed_browser_profile_dir,
    _prepare_browser_for_shutdown,
    _prime_agent_timing_fields,
    _read_completed_agent_history,
    _read_distinct_history_urls,
    _read_email_domain_blocker_partial_history,
    _read_lookup_blocker_partial_history,
    _read_terminal_blocker_partial_history,
    _remove_browser_use_temp_dirs,
    _resolve_agent_run_timeout_seconds,
    _resolve_lookup_blocker_label,
    _run_agent_history_async_with_timeout,
    _run_agent_history_with_timeout,
    _serialize_history_fragment,
    _signal_agent_stop,
    _SyntheticActionResult,
    _SyntheticAgentHistory,
    _SyntheticHistoryEntry,
    _SyntheticHistoryState,
    _truncate_partial_history_excerpt,
)
from src.services._browser_report_download._browser_runtime.terminal_assets import (
    _await_browser_task,
    _browser_rendered_pdf_capture_path,
    _browser_text_has_non_report_marker,
    _browser_visible_text_from_html,
    _capture_completed_history_terminal_assets,
    _capture_terminal_assets,
    _capture_terminal_dialog_evidence,
    _classify_network_signal_kind,
    _coerce_evaluate_list,
    _collect_dom_candidate_urls,
    _collect_network_events,
    _collect_network_events_via_cdp,
    _collect_network_resource_urls,
    _collect_page_resource_urls,
    _copy_external_artifact,
    _copy_history_screenshot,
    _dedupe_browser_dialog_evidence,
    _ensure_terminal_target_hygiene,
    _extract_documentish_urls_from_html,
    _is_within_directory,
    _local_artifact_candidate_paths,
    _looks_like_documentish_url,
    _looks_like_pdf_resource_url,
    _materialize_external_artifacts,
    _maybe_await,
    _maybe_capture_print_pdf_fallback,
    _merge_network_events,
    _network_events_from_raw_events,
    _parse_closed_popup_message,
    _parse_raw_model_response,
    _pdf_prefetch_destination_path,
    _prefetch_structured_pdf_artifact,
    _read_browser_closed_popup_dialog_evidence,
    _read_browser_current_page_title,
    _read_browser_current_page_url,
    _read_history_attachment_paths,
    _read_history_final_page_title,
    _read_history_final_page_url,
    _read_history_final_state,
    _read_page_html,
    _read_page_title,
    _read_page_url,
    _resolve_current_page,
    _run_awaitable,
    _safe_resolve_path,
    _should_capture_print_pdf_fallback,
    _structured_pdf_candidate_urls,
    _try_screenshot_call,
    _write_terminal_html_snapshot,
    _write_terminal_screenshot,
)
from src.services._browser_report_download._browser_runtime.terminal_state import (
    TerminalQuorumAssessment,
    TerminalSnapshot,
    TerminalStabilizationPolicy,
    _assess_terminal_snapshot_quorum,
    _assessment_meets_terminal_quorum,
    _capture_terminal_snapshot,
    _contains_transient_terminal_marker,
    _dedupe_labels,
    _merge_terminal_snapshots,
    _resolve_terminal_stabilization_policy,
    _stabilize_terminal_snapshot,
    _terminal_quorum_text,
    _terminal_stabilization_reason,
)
from src.services._browser_report_download._browser_runtime.timeout_recovery import (
    _attempt_lookup_submission_assist,
    _attempt_lookup_submission_assist_with_timeout,
    _attempt_standard_form_submit_assist_with_timeout,
    _browser_form_identity_field_values,
    _browser_standard_form_identity_field_values,
    _build_cached_timed_out_browser_run,
    _payload_has_lookup_submission_recovery_signal,
    _salvage_timed_out_browser_run,
    _salvage_timed_out_browser_run_unbounded,
    _should_attempt_lookup_submission_assist,
    _should_attempt_standard_form_submit_assist,
    _should_attempt_timeout_standard_form_submit_assist,
)
from src.services._browser_report_download._browser_runtime.worker_protocol import (
    BrowserAgentWorkerPayload,
    BrowserAgentWorkerResponse,
    _deserialize_browser_agent_run_result,
    _discard_browser_agent_worker_payload,
    _normalize_browser_worker_output_excerpt,
    _run_browser_report_download_agent_subprocess,
    _should_run_browser_agent_in_subprocess,
)
from src.services._browser_report_download._http.config import (
    _TERMINAL_NOT_FOUND_BODY_MARKERS,
)
from src.services._browser_report_download.cdp import (
    capture_print_pdf_via_cdp,
    capture_print_pdf_via_cdp_async,
    collect_terminal_dialog_evidence_via_cdp,
    collect_terminal_network_entries_via_cdp,
    ensure_browser_download_target_hygiene_via_cdp,
    wait_for_browser_document_text_async,
)
from src.services._browser_report_download.helpers import (
    browser_helper_capture_screenshot,
    browser_helper_form_autocomplete,
    browser_helper_js,
    browser_helper_page_info,
    browser_helper_standard_form_submit,
    browser_helper_standard_form_submit_async,
)
from src.services._browser_report_download.http import (
    download_pdf_from_url,
    extract_embedded_pdf_urls,
    is_pdf_file,
)
from src.services._browser_report_download.models import (
    BrowserAgentRunResult,
    BrowserUseAgentResult,
)
from src.services._browser_report_download.playbooks import (
    execute_browser_route_playbook,
    execute_browser_route_playbook_async,
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
from src.services._browser_report_download.usage_writer import BrowserUsageWriter
from src.services._llm_service.policy import spend_reservation_key
from src.services.llm_usage_ledger_service import (
    evaluate_budget_request,
    finalize_budget_side_effect,
    reconcile_budget_reservation,
)
from src.utils.coercion import normalize_optional_bool_signal
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

_ASYNC_DETERMINISTIC_POST_SUBMIT_SETTLE_SECONDS = 3.0

_STANDARD_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
_PREFLIGHT_RUNNER_SHUTDOWN_SECONDS = 2.0
_PREFLIGHT_LIFECYCLE_OUTCOME_TO_BUDGET_OUTCOME = {
    "deterministic_handoff": "completed",
    "deterministic_isolation": "completed",
}


@dataclass
class BrowserPreflightSession:
    """Process-local browser lifecycle transferred from preflight to the agent."""

    browser_use: Any
    browser: Any
    launch_budget: RunBudget
    launch_decision: BudgetDecision
    launch_started_at: float
    session_reuse_decision: BrowserDownloadSessionReuseDecision
    profile_dir: Path
    preexisting_temp_dirs: set[str]
    event_loop_runner: asyncio.Runner | None = None
    closed: bool = False


@dataclass
class BrowserAgentRunSetup:
    agent: Any
    no_progress_detector: BrowserNoProgressDetector
    usage_writer: BrowserUsageWriter | None
    spend_reservation_key: str


@dataclass
class BrowserAsyncFormAgentExecution:
    pre_llm_result: BrowserAgentRunResult | None
    setup: BrowserAgentRunSetup | None
    history_result: BrowserAgentHistoryResult | None


def start_browser_preflight_session(
    *,
    browser_use: Any,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
) -> BrowserPreflightSession:
    """Create the canonical browser lifecycle before a retained preflight probe."""
    launch_budget, launch_decision = _reserve_browser_launch(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    launch_started_at = time.monotonic()
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
    browser_kwargs: dict[str, Any] = {
        "downloads_path": str(download_dir),
        "user_data_dir": str(profile_dir),
        "headless": not request.settings.headed,
        "auto_download_pdfs": True,
        "keep_alive": True,
    }
    if _browser_constructor_accepts_parameter(browser_use.Browser, "user_agent"):
        browser_kwargs["user_agent"] = _STANDARD_BROWSER_USER_AGENT
    try:
        browser = browser_use.Browser(
            **browser_kwargs,
        )
    except Exception:
        _finalize_browser_launch(
            budget=launch_budget,
            decision=launch_decision,
            ctx=ctx,
            started=False,
            outcome="failed",
            error_code="browser_download_agent_failed",
            runtime_seconds=max(0, int(time.monotonic() - launch_started_at)),
        )
        if session_reuse_decision.accepted:
            finalize_browser_session_reuse(
                decision=session_reuse_decision,
                ctx=ctx,
                normalized_url=normalized_url,
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
        raise
    return BrowserPreflightSession(
        browser_use=browser_use,
        browser=browser,
        launch_budget=launch_budget,
        launch_decision=launch_decision,
        launch_started_at=launch_started_at,
        session_reuse_decision=session_reuse_decision,
        profile_dir=profile_dir,
        preexisting_temp_dirs=preexisting_temp_dirs,
        event_loop_runner=_new_preflight_event_loop_runner(),
    )


def close_browser_preflight_session(
    *,
    session: BrowserPreflightSession,
    ctx: RunContext,
    normalized_url: str,
    outcome: str,
    error_code: str = "",
    verified_artifact_count: int = 0,
) -> None:
    """Release a preflight-owned browser that was not transferred to the agent."""
    if session.closed:
        return
    session.closed = True
    try:
        _prepare_browser_for_shutdown(
            session.browser,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        _kill_browser_with_timeout(
            session.browser,
            ctx=ctx,
            normalized_url=normalized_url,
        )
    finally:
        _close_preflight_event_loop_runner(session)
    _finalize_browser_launch(
        budget=session.launch_budget,
        decision=session.launch_decision,
        ctx=ctx,
        started=True,
        outcome=_PREFLIGHT_LIFECYCLE_OUTCOME_TO_BUDGET_OUTCOME.get(outcome, outcome),
        error_code=error_code,
        runtime_seconds=max(0, int(time.monotonic() - session.launch_started_at)),
    )
    if session.session_reuse_decision.accepted:
        finalize_browser_session_reuse(
            decision=session.session_reuse_decision,
            ctx=ctx,
            normalized_url=normalized_url,
            verified_artifact_count=verified_artifact_count,
        )
    else:
        _cleanup_browser_profile_dir(
            session.profile_dir,
            ctx=ctx,
            normalized_url=normalized_url,
        )
    _cleanup_new_browser_use_temp_dirs(
        ctx=ctx,
        normalized_url=normalized_url,
        preexisting_temp_dirs=session.preexisting_temp_dirs,
    )


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
    payload["route_summary"] = str(payload.get("route_summary") or "").strip() or (
        "Recovered standard required form controls and submitted the report "
        "request form."
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
    blocked_fields: list[str] | None = None,
    post_submit_message: str = "",
    confirmation_url_changed: bool = False,
    submit_button_state: str = "submitted",
    form_disappeared: bool = False,
    terminal_verified: bool = False,
) -> str:
    blocker_fields = list(blocked_fields or [])
    blocked_reason = "blocked_unknown_required_enum" if blocker_fields else None
    blocked_detail = (
        "Required form values are not configured: " + ", ".join(blocker_fields)
        if blocker_fields
        else None
    )

    return json.dumps(
        {
            "route_kind": "email_delivery",
            "route_family": "browser_email_form",
            "route_summary": (
                "Required browser form values are not configured."
                if blocker_fields
                else (
                    "Filled configured identity fields and submitted "
                    "the report request form through deterministic "
                    "pre-LLM form autofill before invoking browser-use."
                )
            ),
            "final_page_url": final_url,
            "resolved_target_url": final_url,
            "email_submission_completed": not blocker_fields,
            "post_submit_message": post_submit_message,
            "confirmation_url_changed": confirmation_url_changed,
            "submit_button_state": (
                "not_submitted" if blocker_fields else submit_button_state
            ),
            "form_disappeared": False if blocker_fields else form_disappeared,
            "encountered_form_fields": [*resolved_fields, *blocker_fields],
            "blocked_reason": blocked_reason,
            "blocked_reason_detail": blocked_detail,
            "route_steps": [
                {
                    "index": 0,
                    "action": "inspect" if blocker_fields else "submit",
                    "target_text": (
                        ", ".join(blocker_fields)
                        if blocker_fields
                        else "Configured identity and consent fields"
                    ),
                    "target_role": "browser_helper_standard_form_submit",
                    "target_url": final_url,
                    "result": (
                        "Did not submit because required values are not configured."
                        if blocker_fields
                        else "Submitted deterministically before browser-use."
                    ),
                    "expected_evidence": ["confirmation_text", "page_info"],
                    "observed_evidence": ["page_info"],
                    "verification_status": (
                        "blocked"
                        if blocker_fields
                        else (
                            "verified"
                            if terminal_verified
                            else "pending_terminal_verification"
                        )
                    ),
                }
            ],
        },
        ensure_ascii=True,
    )


def _new_preflight_event_loop_runner() -> asyncio.Runner | None:
    """Create a reusable loop only when this synchronous worker owns the thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.Runner()
    return None


def _close_preflight_event_loop_runner(session: BrowserPreflightSession) -> None:
    runner = session.event_loop_runner
    session.event_loop_runner = None
    if runner is not None:
        loop = runner.get_loop()
        pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in pending:
            task.cancel()
        if pending:

            async def wait_for_pending_tasks() -> None:
                await asyncio.wait(
                    pending,
                    timeout=_PREFLIGHT_RUNNER_SHUTDOWN_SECONDS,
                )

            runner.run(wait_for_pending_tasks())
        if any(not task.done() for task in pending):
            return
        runner.close()


def _browser_constructor_accepts_parameter(browser_factory: Any, name: str) -> bool:
    """Keep the Browser Use boundary compatible with installed runtime versions."""

    try:
        parameters = inspect.signature(browser_factory).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(parameter.name == name for parameter in parameters)


def _pre_llm_embedded_pdf_raw_response(
    *,
    final_url: str,
    resolved_fields: list[str],
    embedded_pdf_url: str,
) -> str:
    """Describe a submitted form's observed PDF for normal artifact verification."""

    return json.dumps(
        {
            "route_kind": "pdf_download",
            "route_family": "browser_email_form",
            "route_summary": (
                "Submitted a standard report form and found an embedded PDF on the "
                "post-submit page before invoking browser-use."
            ),
            "final_page_url": final_url,
            "resolved_target_url": embedded_pdf_url,
            "email_submission_completed": True,
            "encountered_form_fields": resolved_fields,
            "route_steps": [
                {
                    "index": 0,
                    "action": "submit",
                    "target_text": "Configured identity and consent fields",
                    "target_role": "browser_helper_standard_form_submit",
                    "target_url": final_url,
                    "result": "Submitted deterministically before browser-use.",
                    "expected_evidence": ["page_info"],
                    "observed_evidence": ["page_info"],
                    "verification_status": "pending_terminal_verification",
                },
                {
                    "index": 1,
                    "action": "open",
                    "target_text": embedded_pdf_url,
                    "target_role": "embedded_pdf_url",
                    "target_url": embedded_pdf_url,
                    "result": "Observed embedded PDF after form submission.",
                    "expected_evidence": ["artifact"],
                    "observed_evidence": ["page_info"],
                    "verification_status": "pending_artifact_verification",
                },
            ],
        },
        ensure_ascii=True,
    )


def _is_terminal_not_found_snapshot(snapshot: TerminalSnapshot) -> bool:
    """Recognize only the configured publisher not-found body evidence."""

    lowered_html = str(snapshot.html or "").casefold()
    return any(marker in lowered_html for marker in _TERMINAL_NOT_FOUND_BODY_MARKERS)


def _pre_llm_terminal_not_found_raw_response(*, final_url: str) -> str:
    """Describe a browser-observed terminal 404 without invoking the Agent."""

    return json.dumps(
        {
            "route_kind": "email_delivery",
            "route_family": "browser_email_form",
            "route_summary": "The target report was not found on a terminal publisher page.",
            "final_page_url": final_url,
            "resolved_target_url": final_url,
            "email_submission_completed": False,
            "blocked_reason": "blocked_static_archive",
            "blocked_reason_detail": (
                "The publisher rendered configured terminal not-found evidence."
            ),
            "route_steps": [
                {
                    "index": 0,
                    "action": "inspect",
                    "target_text": "terminal not-found page",
                    "target_role": "browser_pre_llm_terminal_check",
                    "target_url": final_url,
                    "result": "Observed configured terminal not-found page evidence.",
                    "expected_evidence": ["page_info"],
                    "observed_evidence": ["page_info"],
                    "verification_status": "blocked",
                }
            ],
        },
        ensure_ascii=True,
    )


def _post_submit_embedded_pdf_urls(*, html: str, document_url: str) -> list[str]:
    """Return PDFs exposed by an actual post-submit embed, not incidental links."""

    candidates: list[str] = []
    seen: set[str] = set()
    for tag in re.findall(
        r"<(?:iframe|embed|object)\b[^>]*>", str(html or ""), flags=re.IGNORECASE
    ):
        for candidate in extract_embedded_pdf_urls(
            wrapper_html=tag,
            document_url=document_url,
        ):
            marker = candidate.casefold()
            if marker in seen:
                continue
            seen.add(marker)
            candidates.append(candidate)
    return candidates


def _pre_llm_standard_form_confirmation_evidence(
    *,
    execution_url: str,
    final_url: str,
    snapshot: TerminalSnapshot,
    resolved_fields: list[str],
) -> BrowserDownloadConfirmationEvidence:
    """Build the canonical email-delivery evidence from the live terminal page."""

    evidence = _build_confirmation_evidence(
        agent_result=BrowserUseAgentResult(
            route_kind="email_delivery",
            final_page_url=execution_url,
            email_submission_completed=True,
            encountered_form_fields=resolved_fields,
            post_submit_message=_browser_visible_text_from_html(snapshot.html),
            confirmation_url_changed=bool(final_url and final_url != execution_url),
            submit_button_state="submitted",
            form_disappeared=False,
        ),
        final_url=final_url,
        network_events=[],
    )
    return _upgrade_confirmation_evidence_from_terminal_html(
        confirmation_evidence=evidence,
        email_submission_completed=True,
        encountered_form_fields=resolved_fields,
        html=snapshot.html,
    )


def _derive_grounded_form_option(
    *, request: BrowserReportDownloadRequest, helper_result: Any, ctx: RunContext
) -> dict[str, object] | None:
    options = dict(getattr(helper_result, "unresolved_options", {}) or {})
    configured = _browser_standard_form_identity_field_values(request)
    if not options or not configured or not request.settings.openai_api_key:
        return None

    try:
        prompt_set = prompt_service.load_prompt_set(
            PromptLoadRequest(
                schema_version="1.0",
                namespace="browser_report_download/form_value_derivation",
            ),
            ctx,
        )
        variables = {
            "configured_identity_json": json.dumps(configured, ensure_ascii=True),
            "required_options_json": json.dumps(options, ensure_ascii=True),
        }
        system_prompt = prompt_service.render_prompt(
            PromptRenderRequest(
                schema_version="1.0", template=prompt_set.system, variables=variables
            ),
            ctx,
        ).text
        user_prompt = prompt_service.render_prompt(
            PromptRenderRequest(
                schema_version="1.0", template=prompt_set.user, variables=variables
            ),
            ctx,
        ).text
        response = llm_service.openai_chat_json(
            OpenAIJSONPromptRequest(
                schema_version="1.0",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=request.settings.model,
                temperature=0.0,
                max_output_tokens=400,
                timeout_seconds=request.settings.timeout_seconds,
                api_key=request.settings.openai_api_key,
                cost_ledger_path=request.settings.cost_ledger_path,
                cost_daily_path=request.settings.cost_daily_path,
                model_pricing=request.settings.model_pricing,
                usage_db_path=request.settings.usage_db_path,
                run_budget=request.run_budget,
                workflow_id="browser_acquisition",
                publisher_name=request.publisher_name,
                report_name=_browser_usage_report_name(request),
                source_url=request.url,
                prompt_namespace="browser_report_download/form_value_derivation",
                prompt_hash=prompt_set.system.sha256,
                prompt_content_hash=prompt_set.prompt_content_hash,
                prompt_dependency_manifest=(
                    asdict(prompt_set.dependency_manifest)
                    if prompt_set.dependency_manifest is not None
                    else {}
                ),
                structured_output_schema=_FORM_VALUE_DERIVATION_SCHEMA,
                structured_output_schema_identity="form_value_derivation_v1",
            ),
            ctx,
        )
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_form_value_derivation_unavailable",
                module=logger.name,
                fields={"error_code": exc.code, "normalized_url": request.url},
            )
        )
        return None
    selection = getattr(response, "parsed_json", None)
    if not isinstance(selection, dict):
        return None
    return _validated_grounded_form_option(
        selection=selection, options=options, configured=configured
    )


_FORM_VALUE_DERIVATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "field_label": {"type": "string"},
        "option_value": {"type": "string"},
        "evidence_key": {"type": "string"},
        "evidence_value": {"type": "string"},
    },
    "required": ["field_label", "option_value", "evidence_key", "evidence_value"],
}


def _validated_grounded_form_option(
    *,
    selection: dict[str, object],
    options: dict[str, object],
    configured: list[dict[str, object]],
) -> dict[str, object] | None:
    """Permit only a model selection grounded in configured and visible values."""
    label, option = (
        str(selection.get("field_label") or "").strip(),
        str(selection.get("option_value") or "").strip(),
    )
    evidence_key = str(selection.get("evidence_key") or "").strip()
    evidence_value = str(selection.get("evidence_value") or "").strip()
    visible_options = options.get(label)
    if not isinstance(visible_options, (list, tuple)) or option not in visible_options:
        return None
    if not any(
        str(item.get("key") or "") == evidence_key
        and str(item.get("value") or "") == evidence_value
        for item in configured
    ):
        return None
    return {
        "key": f"derived_{evidence_key}",
        "label": label,
        "value": option,
        "aliases": [label],
        "option_aliases": [option],
    }


def _open_current_page_for_pre_llm_autofill(
    *,
    browser: Any,
    execution_url: str,
    ctx: RunContext,
    normalized_url: str,
) -> Any | None:
    page = _resolve_current_page(browser)
    if page is None:
        start = getattr(browser, "start", None)
        if callable(start):
            try:
                _maybe_await(start())
            except (
                Exception
            ) as exc:  # pragma: no cover - provider-dependent runtime failure
                logger.info(
                    "browser_report_download_pre_llm_autofill_navigation_failed",
                    extra={
                        "event": (
                            "browser_report_download_pre_llm_autofill_navigation_failed"
                        ),
                        "error": str(exc),
                    },
                )
                return None
        page = _resolve_current_page(browser)

    if page is None:
        new_page = getattr(browser, "new_page", None)
        if not callable(new_page):
            return None
        try:
            return _maybe_await(new_page(execution_url))
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
    if inspect.iscoroutinefunction(getattr(browser, "start", None)):
        return asyncio.run(
            _try_pre_llm_standard_form_submit_async(
                request=request,
                browser=browser,
                ctx=ctx,
                normalized_url=normalized_url,
                execution_url=execution_url,
                field_values=field_values,
            )
        )
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
                fields={
                    "normalized_url": normalized_url,
                    "reason": "page_unavailable",
                },
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
    snapshot = _capture_terminal_snapshot(
        browser, ctx=ctx, normalized_url=normalized_url
    )
    return _resolve_pre_llm_standard_form_submit_result(
        helper_result=helper_result,
        snapshot=snapshot,
        execution_url=execution_url,
        ctx=ctx,
        normalized_url=normalized_url,
    )


async def _try_pre_llm_standard_form_submit_async(
    *,
    request: BrowserReportDownloadRequest,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    field_values: list[dict[str, object]],
) -> BrowserAgentRunResult | None:
    """Use the current BrowserSession page without creating a second session."""

    await browser.start()
    get_current_page = getattr(browser, "get_current_page", None)
    page = (
        await _await_browser_session_value(get_current_page())
        if callable(get_current_page)
        else None
    )
    get_current_page_url = getattr(browser, "get_current_page_url", None)
    current_url = str(
        (
            await _await_browser_session_value(get_current_page_url())
            if callable(get_current_page_url)
            else getattr(browser, "url", "")
        )
        or ""
    ).strip()
    if page is None or current_url in {"", "about:blank"}:
        navigate_to = getattr(browser, "navigate_to", None)
        if callable(navigate_to):
            await _await_browser_session_value(navigate_to(execution_url))
        else:
            new_page = getattr(browser, "new_page", None)
            if not callable(new_page):
                return None
            page = await _await_browser_session_value(new_page(execution_url))
        if page is None and callable(get_current_page):
            page = await _await_browser_session_value(get_current_page())
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
    helper_result = await browser_helper_standard_form_submit_async(
        page=page,
        field_values=field_values,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    evaluated_html = await _await_browser_session_value(
        page.evaluate("() => document.documentElement?.outerHTML || ''")
    )
    terminal_html = (
        evaluated_html
        if isinstance(evaluated_html, str)
        else str(getattr(browser, "html", "") or "")
    )
    get_current_page_title = getattr(browser, "get_current_page_title", None)
    snapshot = TerminalSnapshot(
        page=page,
        url=str(
            (
                await _await_browser_session_value(get_current_page_url())
                if callable(get_current_page_url)
                else getattr(browser, "url", "")
            )
            or ""
        ).strip(),
        title=str(
            (
                await _await_browser_session_value(get_current_page_title())
                if callable(get_current_page_title)
                else getattr(browser, "title", "")
            )
            or ""
        ).strip(),
        html=terminal_html,
    )
    return _resolve_pre_llm_standard_form_submit_result(
        helper_result=helper_result,
        snapshot=snapshot,
        execution_url=execution_url,
        ctx=ctx,
        normalized_url=normalized_url,
    )


def _build_browser_agent_run_setup(
    *,
    browser_use: Any,
    browser: Any,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    prompt_bundle: BrowserDownloadPromptBundle,
) -> BrowserAgentRunSetup:
    spend_reservation_key = _reserve_browser_use_spend(
        request=request,
        ctx=ctx,
        prompt_bundle=prompt_bundle,
    )
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
    no_progress_detector = BrowserNoProgressDetector(browser=browser)
    if _agent_accepts_parameter(agent_parameters, "register_new_step_callback"):
        agent_kwargs["register_new_step_callback"] = (
            no_progress_detector.observe_callback
        )
    if _agent_accepts_parameter(agent_parameters, "register_should_stop_callback"):
        agent_kwargs["register_should_stop_callback"] = (
            no_progress_detector.should_stop_callback
        )
    if "calculate_cost" in agent_parameters:
        agent_kwargs["calculate_cost"] = True
    if llm_clients.fallback_llm is not None and "fallback_llm" in agent_parameters:
        agent_kwargs["fallback_llm"] = llm_clients.fallback_llm
    agent = browser_use.Agent(**agent_kwargs)
    return BrowserAgentRunSetup(
        agent=agent,
        no_progress_detector=no_progress_detector,
        usage_writer=_configure_browser_use_usage_recorder(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            prompt_bundle=prompt_bundle,
            llm_clients=llm_clients,
            agent=agent,
        ),
        spend_reservation_key=spend_reservation_key,
    )


async def _run_async_form_preflight_then_agent(
    *,
    browser_use: Any,
    browser: Any,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    prompt_bundle: BrowserDownloadPromptBundle,
) -> BrowserAsyncFormAgentExecution:
    """Run async browser work while suppressing teardown-time CDP reconnects."""

    try:
        return await _execute_async_form_preflight_then_agent(
            browser_use=browser_use,
            browser=browser,
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            execution_url=execution_url,
            prompt_bundle=prompt_bundle,
        )
    finally:
        # This runs before asyncio.run() cancels BrowserSession background tasks.
        # Without it, CDP cancellation looks like a dropped connection and the
        # session starts a reconnect task after the cancellation snapshot.
        mark_browser_teardown_intentional(browser)


async def _execute_async_form_preflight_then_agent(
    *,
    browser_use: Any,
    browser: Any,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    prompt_bundle: BrowserDownloadPromptBundle,
) -> BrowserAsyncFormAgentExecution:
    """Keep deterministic form work and Agent fallback on one BrowserSession loop."""

    pre_llm_result = None
    if str(request.route_family_hint or "").strip() in {
        "browser_email_form",
        "browser_pdf_click",
    }:
        field_values = _browser_standard_form_identity_field_values(request)
        if field_values:
            pre_llm_result = await _try_pre_llm_standard_form_submit_async(
                request=request,
                browser=browser,
                ctx=ctx,
                normalized_url=normalized_url,
                execution_url=execution_url,
                field_values=field_values,
            )
        else:
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
    if pre_llm_result is not None:
        return BrowserAsyncFormAgentExecution(
            pre_llm_result=pre_llm_result,
            setup=None,
            history_result=None,
        )
    setup = _build_browser_agent_run_setup(
        browser_use=browser_use,
        browser=browser,
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        prompt_bundle=prompt_bundle,
    )
    run_async = getattr(setup.agent, "run", None)
    if not inspect.iscoroutinefunction(run_async):
        history_result = await asyncio.to_thread(
            _run_agent_history_with_timeout,
            agent=setup.agent,
            browser=browser,
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            no_progress_detector=setup.no_progress_detector,
        )
    else:
        history_result = await _run_agent_history_async_with_timeout(
            agent=setup.agent,
            browser=browser,
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            no_progress_detector=setup.no_progress_detector,
        )
    return BrowserAsyncFormAgentExecution(
        pre_llm_result=None,
        setup=setup,
        history_result=history_result,
    )


async def _await_browser_session_value(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _resolve_pre_llm_standard_form_submit_result(
    *,
    helper_result: Any,
    snapshot: TerminalSnapshot,
    execution_url: str,
    ctx: RunContext,
    normalized_url: str,
) -> BrowserAgentRunResult | None:
    final_url = snapshot.url or helper_result.final_url or execution_url
    if _is_terminal_not_found_snapshot(snapshot):
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_pre_llm_terminal_not_found",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "final_url": final_url,
                    "avoided_llm_call": True,
                },
            )
        )
        return BrowserAgentRunResult(
            schema_version="1.0",
            raw_model_response=_pre_llm_terminal_not_found_raw_response(
                final_url=final_url,
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
    if helper_result.status == "blocked" and helper_result.unresolved_fields:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_pre_llm_autofill_blocked",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "unresolved_fields": list(helper_result.unresolved_fields),
                    "blocker_code": helper_result.blocker_code
                    or "blocked_unknown_required_enum",
                    "avoided_llm_call": True,
                },
            )
        )
        return BrowserAgentRunResult(
            schema_version="1.0",
            raw_model_response=_pre_llm_standard_form_raw_response(
                final_url=final_url,
                resolved_fields=list(helper_result.resolved_fields),
                blocked_fields=list(helper_result.unresolved_fields),
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
    embedded_pdf_urls = _post_submit_embedded_pdf_urls(
        html=snapshot.html,
        document_url=final_url,
    )
    if embedded_pdf_urls:
        embedded_pdf_url = embedded_pdf_urls[0]
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_pre_llm_embedded_pdf_detected",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "embedded_pdf_url": embedded_pdf_url,
                    "avoided_llm_call": True,
                },
            )
        )
        return BrowserAgentRunResult(
            schema_version="1.0",
            raw_model_response=_pre_llm_embedded_pdf_raw_response(
                final_url=final_url,
                resolved_fields=list(helper_result.resolved_fields),
                embedded_pdf_url=embedded_pdf_url,
            ),
            final_page_url=final_url,
            final_page_title=snapshot.title,
            final_page_html=snapshot.html,
            downloaded_files=[],
            attachment_paths=[],
            network_resource_urls=[embedded_pdf_url],
            network_events=[],
            html_snapshot_path="",
            screenshot_path="",
            print_pdf_capture_path="",
            print_pdf_capture_provenance="",
            dialog_evidence=[],
        )
    confirmation_evidence = _pre_llm_standard_form_confirmation_evidence(
        execution_url=execution_url,
        final_url=final_url,
        snapshot=snapshot,
        resolved_fields=list(helper_result.resolved_fields),
    )
    if not _confirmation_evidence_verifies_email_delivery(confirmation_evidence):
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_pre_llm_autofill_escalated",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "reason": "terminal_verification_unconfirmed",
                    "confirmation_signal_labels": list(
                        confirmation_evidence.signal_labels
                    ),
                    "browser_session_preserved": True,
                },
            )
        )
        return None
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_pre_llm_autofill_verified",
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
                "confirmation_signal_labels": list(confirmation_evidence.signal_labels),
            },
        )
    )
    return BrowserAgentRunResult(
        schema_version="1.0",
        raw_model_response=_pre_llm_standard_form_raw_response(
            final_url=final_url,
            resolved_fields=list(helper_result.resolved_fields),
            post_submit_message=confirmation_evidence.visible_confirmation_text,
            confirmation_url_changed=confirmation_evidence.url_changed,
            submit_button_state=confirmation_evidence.submit_button_state,
            form_disappeared=confirmation_evidence.form_disappeared,
            terminal_verified=True,
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


def _rendered_pdf_contains_text(
    path: Path | None, text: str, ctx: RunContext | None = None
) -> bool:
    if path is None or not path.is_file() or not str(text or "").strip():
        return False
    try:
        return pdf_service.pdf_contains_text(
            PdfTextContainsRequest(
                schema_version="1.0", path=path.as_posix(), text=str(text)
            ),
            ctx,
        ).contains_text
    except Exception:
        return False


def _playbook_renders_current_page_to_pdf(playbook: BrowserRoutePlaybook) -> bool:
    return any(step.action.strip().lower() == "save_as_pdf" for step in playbook.steps)


class _DeterministicPlaybookPageDriver:
    """Small synchronous adapter over the current browser-use page."""

    def __init__(
        self,
        *,
        browser: Any,
        page: Any,
        download_dir: Path | None = None,
        ctx: RunContext | None = None,
        normalized_url: str = "",
        rendered_pdf_path: Path | None = None,
    ) -> None:
        self._browser = browser
        self._page = page
        self._download_dir = download_dir
        self._ctx = ctx
        self._normalized_url = normalized_url
        self._rendered_pdf_path = rendered_pdf_path

    def open(self, url: str) -> str:
        navigate = getattr(self._browser, "navigate_to", None)
        if not callable(navigate):
            navigate = getattr(self._page, "goto", None)
        if not callable(navigate):
            raise RuntimeError("deterministic_playbook_navigation_unavailable")
        _maybe_await(navigate(url))
        return "opened"

    def click_css(self, selector: str) -> str:
        return self._click_expression(
            "document.querySelector(" + json.dumps(selector) + ")"
        )

    def click_text(self, text: str) -> str:
        return self._click_expression(
            "Array.from(document.querySelectorAll('a,button,input[type=submit]'))"
            ".find((node) => (node.innerText || node.value || '').trim() === "
            + json.dumps(text)
            + ")"
        )

    def click_role(self, role: str, name: str) -> str:
        return self._click_expression(_role_locator_expression(role, name))

    def click_label(self, label: str) -> str:
        return self._click_expression(self._label_control_expression(label))

    def click_name(self, name: str) -> str:
        return self._click_expression(
            "document.querySelector('[name=' + " + json.dumps(name) + " + ']')"
        )

    def click_data_attribute(self, selector: str) -> str:
        expression = (
            "document.querySelector("
            + json.dumps(_data_attribute_selector(selector))
            + ")"
        )
        return self._click_expression(expression)

    def fill_css(self, selector: str, value: str) -> str:
        expression = "document.querySelector(" + json.dumps(selector) + ")"
        return self._set_value(expression, value)

    def fill_role(self, role: str, name: str, value: str) -> str:
        return self._set_textbox_value(_role_locator_expression(role, name), value)

    def fill_label(self, label: str, value: str) -> str:
        return self._set_value(self._label_control_expression(label), value)

    def fill_name(self, name: str, value: str) -> str:
        return self._set_value(
            "document.querySelector('[name=' + " + json.dumps(name) + " + ']')", value
        )

    def fill_data_attribute(self, selector: str, value: str) -> str:
        return self._set_value(
            "document.querySelector("
            + json.dumps(_data_attribute_selector(selector))
            + ")",
            value,
        )

    def select_css(self, selector: str, value: str) -> str:
        return self._select_value(
            "document.querySelector(" + json.dumps(selector) + ")", value
        )

    def select_role(self, role: str, name: str, value: str) -> str:
        return self._select_value(_role_locator_expression(role, name), value)

    def select_label(self, label: str, value: str) -> str:
        return self._select_value(self._label_control_expression(label), value)

    def select_name(self, name: str, value: str) -> str:
        return self._select_value(
            "document.querySelector('[name=' + " + json.dumps(name) + " + ']')", value
        )

    def select_data_attribute(self, selector: str, value: str) -> str:
        return self._select_value(
            "document.querySelector("
            + json.dumps(_data_attribute_selector(selector))
            + ")",
            value,
        )

    def current_url(self) -> str:
        reader = getattr(self._browser, "get_current_page_url", None)
        if callable(reader):
            return str(_maybe_await(reader()) or "")
        return str(getattr(self._page, "url", "") or "")

    def contains_text(self, text: str) -> bool:
        if _rendered_pdf_contains_text(self._rendered_pdf_path, text, self._ctx):
            return True
        return bool(
            self._evaluate(
                "() => (document.body?.innerText || '').includes("
                + json.dumps(text)
                + ")"
            )
        )

    def save_as_pdf(self, target_url: str) -> str:
        if self._download_dir is None or self._ctx is None:
            raise RuntimeError("deterministic_playbook_pdf_capture_unavailable")
        pdf_path = self._download_dir / "browser-route-playbook-rendered.pdf"
        if not capture_print_pdf_via_cdp(
            browser=self._browser,
            pdf_path=pdf_path,
            ctx=self._ctx,
            normalized_url=self._normalized_url,
            required=True,
            target_url=target_url or self._normalized_url,
        ):
            raise RuntimeError("deterministic_playbook_pdf_capture_failed")
        self._rendered_pdf_path = pdf_path
        return str(pdf_path)

    def _click_expression(self, element_expression: str) -> str:
        return self._evaluate_action(
            "() => { const element = "
            + element_expression
            + "; if (!element) throw new Error('deterministic_locator_not_found'); "
            "element.click(); return 'clicked'; }"
        )

    def _set_value(self, element_expression: str, value: str) -> str:
        return self._evaluate_action(
            "() => { const element = "
            + element_expression
            + "; if (!element) throw new Error('deterministic_locator_not_found'); "
            "element.focus(); element.value = "
            + json.dumps(value)
            + "; element.dispatchEvent(new Event('input', {bubbles: true})); "
            "element.dispatchEvent(new Event('change', {bubbles: true})); "
            "return 'filled'; }"
        )

    def _set_textbox_value(self, element_expression: str, value: str) -> str:
        return self._evaluate_action(
            "() => { const element = "
            + element_expression
            + "; const tag = element?.tagName; const type = "
            "(element?.getAttribute('type') || 'text').toLowerCase(); "
            "if (!element || !['INPUT', 'TEXTAREA'].includes(tag) || "
            "['button', 'checkbox', 'file', 'hidden', 'image', 'radio', 'reset', "
            "'submit'].includes(type)) throw new Error("
            "'deterministic_textbox_not_found'); "
            "element.focus(); element.value = "
            + json.dumps(value)
            + "; element.dispatchEvent(new Event('input', {bubbles: true})); "
            "element.dispatchEvent(new Event('change', {bubbles: true})); "
            "return 'filled'; }"
        )

    def _select_value(self, element_expression: str, value: str) -> str:
        return self._evaluate_action(
            "() => { const element = "
            + element_expression
            + "; if (!element || element.tagName !== 'SELECT') throw new Error("
            "'deterministic_select_not_found'); const option = "
            "Array.from(element.options).find((item) => item.value === "
            + json.dumps(value)
            + " || (item.textContent || '').trim() === "
            + json.dumps(value)
            + "); if (!option) throw new Error("
            "'deterministic_select_option_not_found'); element.value = option.value; "
            "element.dispatchEvent(new Event('change', {bubbles: true})); "
            "return 'selected'; }"
        )

    def _label_control_expression(self, label: str) -> str:
        return (
            "(() => { const label = Array.from(document.querySelectorAll('label'))"
            ".find((node) => (node.innerText || '').trim() === "
            + json.dumps(label)
            + "); if (!label) return null; return label.control || "
            "document.getElementById(label.htmlFor) || "
            "label.querySelector('input,select,textarea,button'); })()"
        )

    def _evaluate_action(self, expression: str) -> str:
        result = self._evaluate(expression)
        return str(result or "executed")

    def _evaluate(self, expression: str) -> Any:
        evaluate = getattr(self._page, "evaluate", None)
        if not callable(evaluate):
            raise RuntimeError("deterministic_playbook_evaluate_unavailable")
        return _maybe_await(evaluate(expression))


class _AsyncDeterministicPlaybookPageDriver:
    """Async adapter over the already-open Browser Use page."""

    def __init__(
        self,
        *,
        browser: Any,
        page: Any,
        download_dir: Path | None = None,
        ctx: RunContext | None = None,
        normalized_url: str = "",
        rendered_pdf_path: Path | None = None,
    ) -> None:
        self._browser = browser
        self._page = page
        self._download_dir = download_dir
        self._ctx = ctx
        self._normalized_url = normalized_url
        self._rendered_pdf_path = rendered_pdf_path

    async def open(self, url: str) -> str:
        navigate = getattr(self._browser, "navigate_to", None)
        if not callable(navigate):
            navigate = getattr(self._page, "goto", None)
        if not callable(navigate):
            raise RuntimeError("deterministic_playbook_navigation_unavailable")
        await self._await_value(navigate(url))
        return "opened"

    async def click_css(self, selector: str) -> str:
        return await self._click_expression(
            "document.querySelector(" + json.dumps(selector) + ")"
        )

    async def _set_textbox_value(self, element_expression: str, value: str) -> str:
        return await self._evaluate_action(
            "() => { const element = "
            + element_expression
            + "; const tag = element?.tagName; const type = "
            "(element?.getAttribute('type') || 'text').toLowerCase(); "
            "if (!element || !['INPUT', 'TEXTAREA'].includes(tag) || "
            "['button', 'checkbox', 'file', 'hidden', 'image', 'radio', 'reset', "
            "'submit'].includes(type)) throw new Error("
            "'deterministic_textbox_not_found'); "
            "element.focus(); element.value = "
            + json.dumps(value)
            + "; element.dispatchEvent(new Event('input', {bubbles: true})); "
            "element.dispatchEvent(new Event('change', {bubbles: true})); "
            "return 'filled'; }"
        )

    async def click_text(self, text: str) -> str:
        return await self._click_expression(
            "Array.from(document.querySelectorAll('a,button,input[type=submit]'))"
            ".find((node) => (node.innerText || node.value || '').trim() === "
            + json.dumps(text)
            + ")"
        )

    async def click_role(self, role: str, name: str) -> str:
        return await self._click_expression(_role_locator_expression(role, name))

    async def click_label(self, label: str) -> str:
        return await self._click_expression(self._label_control_expression(label))

    async def click_name(self, name: str) -> str:
        return await self._click_expression(
            "document.querySelector('[name=' + " + json.dumps(name) + " + ']')"
        )

    async def click_data_attribute(self, selector: str) -> str:
        return await self._click_expression(
            "document.querySelector("
            + json.dumps(_data_attribute_selector(selector))
            + ")"
        )

    async def wait_for_post_submit(self) -> None:
        """Allow client-side form submission handlers to update the current page."""

        await asyncio.sleep(_ASYNC_DETERMINISTIC_POST_SUBMIT_SETTLE_SECONDS)

    async def fill_css(self, selector: str, value: str) -> str:
        return await self._set_value(
            "document.querySelector(" + json.dumps(selector) + ")", value
        )

    async def fill_role(self, role: str, name: str, value: str) -> str:
        return await self._set_textbox_value(
            _role_locator_expression(role, name), value
        )

    async def fill_label(self, label: str, value: str) -> str:
        return await self._set_value(self._label_control_expression(label), value)

    async def fill_name(self, name: str, value: str) -> str:
        return await self._set_value(
            "document.querySelector('[name=' + " + json.dumps(name) + " + ']')", value
        )

    async def fill_data_attribute(self, selector: str, value: str) -> str:
        return await self._set_value(
            "document.querySelector("
            + json.dumps(_data_attribute_selector(selector))
            + ")",
            value,
        )

    async def select_css(self, selector: str, value: str) -> str:
        return await self._select_value(
            "document.querySelector(" + json.dumps(selector) + ")", value
        )

    async def select_role(self, role: str, name: str, value: str) -> str:
        return await self._select_value(_role_locator_expression(role, name), value)

    async def select_label(self, label: str, value: str) -> str:
        return await self._select_value(self._label_control_expression(label), value)

    async def select_name(self, name: str, value: str) -> str:
        return await self._select_value(
            "document.querySelector('[name=' + " + json.dumps(name) + " + ']')", value
        )

    async def select_data_attribute(self, selector: str, value: str) -> str:
        return await self._select_value(
            "document.querySelector("
            + json.dumps(_data_attribute_selector(selector))
            + ")",
            value,
        )

    async def current_url(self) -> str:
        reader = getattr(self._browser, "get_current_page_url", None)
        if callable(reader):
            return str(await self._await_value(reader()) or "")
        return str(getattr(self._page, "url", "") or "")

    async def contains_text(self, text: str) -> bool:
        if _rendered_pdf_contains_text(self._rendered_pdf_path, text, self._ctx):
            return True
        return bool(
            await self._evaluate(
                "() => (document.body?.innerText || '').includes("
                + json.dumps(text)
                + ")"
            )
        )

    async def save_as_pdf(self, target_url: str) -> str:
        if self._download_dir is None or self._ctx is None:
            raise RuntimeError("deterministic_playbook_pdf_capture_unavailable")
        pdf_path = self._download_dir / "browser-route-playbook-rendered.pdf"
        if not capture_print_pdf_via_cdp(
            browser=self._browser,
            pdf_path=pdf_path,
            ctx=self._ctx,
            normalized_url=self._normalized_url,
            required=True,
            target_url=target_url or self._normalized_url,
        ):
            raise RuntimeError("deterministic_playbook_pdf_capture_failed")
        self._rendered_pdf_path = pdf_path
        return str(pdf_path)

    async def _click_expression(self, element_expression: str) -> str:
        return await self._evaluate_action(
            "() => { const element = "
            + element_expression
            + "; if (!element) throw new Error('deterministic_locator_not_found'); "
            "element.click(); return 'clicked'; }"
        )

    async def _set_value(self, element_expression: str, value: str) -> str:
        return await self._evaluate_action(
            "() => { const element = "
            + element_expression
            + "; if (!element) throw new Error('deterministic_locator_not_found'); "
            "element.focus(); element.value = "
            + json.dumps(value)
            + "; element.dispatchEvent(new Event('input', {bubbles: true})); "
            "element.dispatchEvent(new Event('change', {bubbles: true})); "
            "return 'filled'; }"
        )

    async def _select_value(self, element_expression: str, value: str) -> str:
        return await self._evaluate_action(
            "() => { const element = "
            + element_expression
            + "; if (!element || element.tagName !== 'SELECT') throw new Error("
            "'deterministic_select_not_found'); const option = "
            "Array.from(element.options).find((item) => item.value === "
            + json.dumps(value)
            + " || (item.textContent || '').trim() === "
            + json.dumps(value)
            + "); if (!option) throw new Error("
            "'deterministic_select_option_not_found'); element.value = option.value; "
            "element.dispatchEvent(new Event('change', {bubbles: true})); "
            "return 'selected'; }"
        )

    def _label_control_expression(self, label: str) -> str:
        return (
            "(() => { const label = Array.from(document.querySelectorAll('label'))"
            ".find((node) => (node.innerText || '').trim() === "
            + json.dumps(label)
            + "); if (!label) return null; return label.control || "
            "document.getElementById(label.htmlFor) || "
            "label.querySelector('input,select,textarea,button'); })()"
        )

    async def _evaluate_action(self, expression: str) -> str:
        result = await self._evaluate(expression)
        return str(result or "executed")

    async def _evaluate(self, expression: str) -> Any:
        evaluate = getattr(self._page, "evaluate", None)
        if not callable(evaluate):
            raise RuntimeError("deterministic_playbook_evaluate_unavailable")
        return await self._await_value(evaluate(expression))

    async def _await_value(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value


def _data_attribute_selector(selector: str) -> str:
    token = str(selector or "").strip()
    if token.startswith("["):
        return token
    attribute, separator, value = token.partition("=")
    if not separator or not attribute.strip() or not value.strip():
        raise ValueError("invalid_data_attribute_selector")
    return f"[{attribute.strip()}={json.dumps(value.strip())}]"


def _role_locator_expression(role: str, name: str) -> str:
    """Resolve exactly one native or explicitly-role-bearing accessible element."""

    return (
        "(() => { const normalise = (value) => "
        "String(value || '').replace(/\\s+/g, ' ').trim(); "
        "const labelText = (label) => { const clone = label.cloneNode(true); "
        "clone.querySelectorAll('input,textarea,select,button')"
        ".forEach((control) => control.remove()); "
        "return normalise(clone.textContent); }; "
        "const accessibleName = (node) => { const labelledBy = "
        "(node.getAttribute('aria-labelledby') || '').trim().split(/\\s+/)"
        ".filter(Boolean).map((id) => "
        "normalise(document.getElementById(id)?.innerText)).filter(Boolean)"
        ".join(' '); const labels = Array.from(node.labels || []).map(labelText)"
        ".filter(Boolean).join(' '); return normalise(node.getAttribute('aria-label') "
        "|| labelledBy || labels || node.innerText || node.value); }; "
        "const implicitRole = (node) => { const tag = node.tagName; "
        "if (tag === 'TEXTAREA') return 'textbox'; "
        "if (tag === 'SELECT') return node.multiple ? 'listbox' : 'combobox'; "
        "if (tag === 'BUTTON') return 'button'; "
        "if (tag === 'A' && node.hasAttribute('href')) return 'link'; "
        "if (tag !== 'INPUT') return ''; "
        "const type = (node.getAttribute('type') || 'text').toLowerCase(); "
        "if (type === 'search') return 'searchbox'; "
        "if (['button', 'image', 'reset', 'submit'].includes(type)) return 'button'; "
        "return ['checkbox', 'radio', 'file', 'hidden'].includes(type) ? '' : "
        "'textbox'; "
        "}; const matches = Array.from(document.querySelectorAll("
        "'input,textarea,select,button,a,[role]')).filter((node) => "
        "(node.getAttribute('role') || implicitRole(node)) === "
        + json.dumps(role)
        + " && accessibleName(node) === "
        + json.dumps(" ".join(name.split()))
        + "); if (matches.length !== 1) throw new Error(matches.length ? "
        "'deterministic_role_locator_ambiguous' : 'deterministic_locator_not_found'); "
        "return matches[0]; })()"
    )


def run_deterministic_browser_route_playbook(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    browser: Any | None,
    playbook: BrowserRoutePlaybook,
) -> BrowserAgentRunResult | None:
    """Execute one fully-verifiable publisher playbook without constructing an Agent."""

    if browser is None and _should_run_browser_agent_in_subprocess(
        object(), request=request
    ):
        return _run_browser_report_download_agent_subprocess(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            execution_url=execution_url,
            download_dir=download_dir,
            prompt_bundle=BrowserDownloadPromptBundle(
                schema_version="1.0",
                namespace="",
                system_prompt_path="",
                user_prompt_path="",
                system_prompt_sha256="",
                user_prompt_sha256="",
                rendered_system_prompt="",
                rendered_user_prompt="",
                task_prompt="",
            ),
            deterministic_playbook=playbook,
        )
    if browser is None:
        return None

    if type(browser).__module__.startswith("browser_use"):
        return asyncio.run(
            _run_async_deterministic_browser_route_playbook(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                execution_url=execution_url,
                download_dir=download_dir,
                browser=browser,
                playbook=playbook,
            )
        )

    start = getattr(browser, "start", None)
    if callable(start):
        _maybe_await(start())
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
                event="browser_route_playbook_deterministic_escalated",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "playbook_id": playbook.playbook_id,
                    "reason": "current_page_unavailable",
                },
            )
        )
        return None
    identity_values = {
        str(field.key): str(field.value)
        for field in resolve_effective_identity_fields(request)
        if str(field.key or "").strip() and str(field.value or "").strip()
    }
    if not _playbook_renders_current_page_to_pdf(playbook):
        _dismiss_explicit_cookie_banner(page)
    execution = execute_browser_route_playbook(
        BrowserRoutePlaybookExecutionRequest(
            schema_version="1.0",
            playbook=playbook,
            normalized_url=normalized_url,
            page_driver=_DeterministicPlaybookPageDriver(
                browser=browser,
                page=page,
                download_dir=download_dir,
                ctx=ctx,
                normalized_url=normalized_url,
            ),
            identity_values=identity_values,
        ),
        ctx,
    )
    if execution.status != "completed":
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_route_playbook_deterministic_escalated",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "playbook_id": playbook.playbook_id,
                    "reason": execution.status,
                    "drift_reasons": list(execution.drift_reasons),
                },
            )
        )
        return None
    page_info = browser_helper_page_info(
        browser=browser,
        page=page,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    final_url = page_info.url or execution_url
    final_text = next(
        (
            step.expected_text
            for step in reversed(playbook.steps)
            if step.expected_text.strip()
        ),
        "",
    )
    raw_result = {
        "route_kind": playbook.route_kind,
        "route_family": playbook.route_family,
        "route_summary": playbook.summary,
        "resolved_target_url": final_url,
        "final_page_url": final_url,
        "final_page_title": page_info.title,
        "email_submission_completed": (
            True
            if playbook.route_kind == "email_delivery"
            and any(step.action.strip().lower() == "submit" for step in playbook.steps)
            else None
        ),
        "post_submit_message": final_text or None,
        "confirmation_url_changed": None,
        "form_disappeared": None,
        "terminal_text_excerpt": final_text or None,
        "traversed_page_urls": [final_url],
        "route_steps": [
            {
                "index": step.index,
                "action": step.action,
                "target_text": step.target,
                "target_url": final_url,
                "result": "Deterministic playbook action and postcondition verified.",
                "expected_evidence": [playbook.steps[step.index].verification],
                "observed_evidence": ["deterministic_postcondition_verified"],
                "verification_status": "verified",
                "expected_url_contains": (
                    playbook.steps[step.index].expected_url_contains or None
                ),
                "expected_text": playbook.steps[step.index].expected_text or None,
            }
            for step in execution.step_results
        ],
    }
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_route_playbook_deterministic_completed",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "playbook_id": playbook.playbook_id,
                "playbook_version": playbook.version,
                "route_kind": playbook.route_kind,
                "step_count": len(execution.step_results),
                "avoided_browser_use_model_call": True,
            },
        )
    )
    local_files = [
        str(path) for path in sorted(download_dir.iterdir()) if path.is_file()
    ]
    rendered_pdf_path = next(
        (
            path
            for path in local_files
            if Path(path).name == "browser-route-playbook-rendered.pdf"
        ),
        "",
    )
    return BrowserAgentRunResult(
        schema_version="1.0",
        raw_model_response=json.dumps(raw_result, ensure_ascii=True),
        final_page_url=final_url,
        final_page_title=page_info.title,
        final_page_html=page_info.html,
        downloaded_files=local_files,
        attachment_paths=[],
        network_resource_urls=[],
        network_events=[],
        html_snapshot_path="",
        screenshot_path="",
        print_pdf_capture_path=rendered_pdf_path,
        print_pdf_capture_provenance=(
            "browser_route_playbook_print_to_pdf" if rendered_pdf_path else ""
        ),
        dialog_evidence=[],
    )


async def _run_async_deterministic_browser_route_playbook(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    browser: Any,
    playbook: BrowserRoutePlaybook,
    browser_started: bool = False,
) -> BrowserAgentRunResult | None:
    """Run a deterministic playbook without leaving Browser Use's event loop."""
    if not browser_started:
        await browser.start()
    if _playbook_renders_current_page_to_pdf(playbook):
        return await _run_cdp_rendered_pdf_playbook(
            browser=browser,
            ctx=ctx,
            normalized_url=normalized_url,
            execution_url=execution_url,
            download_dir=download_dir,
            playbook=playbook,
        )
    page = await browser.get_current_page()
    if page is None:
        return None
    identity_values = {
        str(field.key): str(field.value)
        for field in resolve_effective_identity_fields(request)
        if str(field.key or "").strip() and str(field.value or "").strip()
    }
    if not _playbook_renders_current_page_to_pdf(playbook):
        await _dismiss_explicit_cookie_banner_async(page)
    execution = await execute_browser_route_playbook_async(
        BrowserRoutePlaybookExecutionRequest(
            schema_version="1.0",
            playbook=playbook,
            normalized_url=normalized_url,
            page_driver=_AsyncDeterministicPlaybookPageDriver(
                browser=browser,
                page=page,
                download_dir=download_dir,
                ctx=ctx,
                normalized_url=normalized_url,
            ),
            identity_values=identity_values,
        ),
        ctx,
    )
    if execution.status != "completed":
        return None
    page = await browser.get_current_page()
    if page is None:
        return None
    final_url = str(await browser.get_current_page_url() or execution_url)
    final_title = str(await browser.get_current_page_title() or "")
    final_html = str(
        await page.evaluate("() => document.documentElement.outerHTML") or ""
    )
    final_text = _browser_visible_text_from_html(final_html)
    raw_result = {
        "route_kind": playbook.route_kind,
        "route_family": playbook.route_family,
        "route_summary": playbook.summary,
        "resolved_target_url": final_url,
        "final_page_url": final_url,
        "final_page_title": final_title,
        "email_submission_completed": (
            True
            if playbook.route_kind == "email_delivery"
            and any(step.action.strip().lower() == "submit" for step in playbook.steps)
            else None
        ),
        "post_submit_message": final_text or None,
        "confirmation_url_changed": None,
        "form_disappeared": None,
        "terminal_text_excerpt": final_text or None,
        "traversed_page_urls": [final_url],
        "route_steps": [
            {
                "index": step.index,
                "action": step.action,
                "target_text": step.target,
                "target_url": final_url,
                "result": "Deterministic playbook action and postcondition verified.",
                "expected_evidence": [playbook.steps[step.index].verification],
                "observed_evidence": ["deterministic_postcondition_verified"],
                "verification_status": "verified",
                "expected_url_contains": (
                    playbook.steps[step.index].expected_url_contains or None
                ),
                "expected_text": playbook.steps[step.index].expected_text or None,
            }
            for step in execution.step_results
        ],
    }
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_route_playbook_deterministic_completed",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "playbook_id": playbook.playbook_id,
                "playbook_version": playbook.version,
                "route_kind": playbook.route_kind,
                "step_count": len(execution.step_results),
                "avoided_browser_use_model_call": True,
            },
        )
    )
    local_files = [
        str(path) for path in sorted(download_dir.iterdir()) if path.is_file()
    ]
    rendered_pdf_path = next(
        (
            path
            for path in local_files
            if Path(path).name == "browser-route-playbook-rendered.pdf"
        ),
        "",
    )
    return BrowserAgentRunResult(
        schema_version="1.0",
        raw_model_response=json.dumps(raw_result, ensure_ascii=True),
        final_page_url=final_url,
        final_page_title=final_title,
        final_page_html=final_html,
        downloaded_files=local_files,
        attachment_paths=[],
        network_resource_urls=[],
        network_events=[],
        html_snapshot_path="",
        screenshot_path="",
        print_pdf_capture_path=rendered_pdf_path,
        print_pdf_capture_provenance=(
            "browser_route_playbook_print_to_pdf" if rendered_pdf_path else ""
        ),
        dialog_evidence=[],
    )


async def _run_cdp_rendered_pdf_playbook(
    *,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    playbook: BrowserRoutePlaybook,
) -> BrowserAgentRunResult | None:
    """Render an already-open public page without Browser Use page evaluation."""

    step = next(
        (
            item
            for item in playbook.steps
            if item.action.strip().lower() == "save_as_pdf"
        ),
        None,
    )
    if step is None:
        return None
    target_url = str(step.selector or execution_url or normalized_url).strip()
    if step.expected_url_contains.strip() and (
        step.expected_url_contains.strip() not in target_url
    ):
        return None
    if not await wait_for_browser_document_text_async(
        browser=browser,
        target_url=target_url,
        expected_text=step.expected_text,
        timeout_seconds=30.0,
    ):
        return None
    pdf_path = download_dir / "browser-route-playbook-rendered.pdf"
    if not await capture_print_pdf_via_cdp_async(
        browser=browser,
        pdf_path=pdf_path,
        ctx=ctx,
        normalized_url=normalized_url,
        target_url=target_url,
    ):
        return None
    if step.expected_text.strip() and not _rendered_pdf_contains_text(
        pdf_path, step.expected_text, ctx
    ):
        pdf_path.unlink(missing_ok=True)
        return None
    raw_result = {
        "route_kind": "onsite_report",
        "route_family": playbook.route_family,
        "route_summary": playbook.summary,
        "resolved_target_url": target_url,
        "final_page_url": target_url,
        "final_page_title": step.expected_text or "",
        "terminal_text_excerpt": step.expected_text or "",
        "traversed_page_urls": [target_url],
        "onsite_capture_path": str(pdf_path),
        "onsite_capture_format": "browser_rendered_pdf",
        "onsite_completeness_status": "complete",
        "route_steps": [
            {
                "index": 0,
                "action": step.action,
                "target_text": step.target,
                "target_url": target_url,
                "result": "Rendered local PDF and verified the playbook postcondition.",
                "expected_evidence": [step.verification],
                "observed_evidence": [
                    "browser_rendered_print_to_pdf",
                    "deterministic_postcondition_verified",
                ],
                "verification_status": "verified",
                "expected_url_contains": step.expected_url_contains or None,
                "expected_text": step.expected_text or None,
            }
        ],
    }
    route_step = BrowserDownloadRouteStep(
        schema_version="1.0",
        index=0,
        action=step.action,
        target_text=step.target,
        target_role="page",
        target_url=target_url,
        result="Rendered local PDF and verified the playbook postcondition.",
        expected_evidence=[step.verification],
        observed_evidence=[
            "browser_rendered_print_to_pdf",
            "deterministic_postcondition_verified",
        ],
        verification_status="verified",
        expected_url_contains=step.expected_url_contains or "",
        expected_text=step.expected_text or "",
    )
    return BrowserAgentRunResult(
        schema_version="1.0",
        raw_model_response=json.dumps(raw_result, ensure_ascii=True),
        final_page_url=target_url,
        final_page_title=step.expected_text or "",
        final_page_html="",
        downloaded_files=[str(pdf_path)],
        attachment_paths=[],
        network_resource_urls=[],
        network_events=[],
        html_snapshot_path="",
        screenshot_path="",
        print_pdf_capture_path=str(pdf_path),
        print_pdf_capture_provenance="browser_route_playbook_print_to_pdf",
        dialog_evidence=[],
        execution_route_steps=[route_step],
    )


_REJECT_ALL_COOKIE_BANNER_EXPRESSION = """() => {
  const normalizedText = (element) => String(
    element.innerText || element.value || element.getAttribute('aria-label') || ''
  ).replace(/\\s+/g, ' ').trim().toLowerCase();
  const isVisible = (element) => {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const reject = Array.from(document.querySelectorAll(
    'button, input[type=button], input[type=submit], [role=button]'
  )).find((element) => isVisible(element) && normalizedText(element) === 'reject all');
  if (!reject) return 'absent';
  reject.click();
  return 'rejected';
}"""


def _dismiss_explicit_cookie_banner(page: Any) -> str:
    """Reject an explicit all-cookies banner without making consent a playbook step."""
    evaluate = getattr(page, "evaluate", None)
    if not callable(evaluate):
        return "unavailable"
    try:
        return str(_maybe_await(evaluate(_REJECT_ALL_COOKIE_BANNER_EXPRESSION)) or "")
    except Exception:
        return "unavailable"


async def _dismiss_explicit_cookie_banner_async(page: Any) -> str:
    """Async counterpart for Browser Use's event-loop-bound page API."""
    evaluate = getattr(page, "evaluate", None)
    if not callable(evaluate):
        return "unavailable"
    try:
        value = evaluate(_REJECT_ALL_COOKIE_BANNER_EXPRESSION)
        if inspect.isawaitable(value):
            value = await value
        return str(value or "")
    except Exception:
        return "unavailable"


def _agent_accepts_parameter(
    parameters: Mapping[str, inspect.Parameter], name: str
) -> bool:
    return name in parameters


def _no_progress_raw_model_response(
    observation: BrowserNoProgressObservation,
    *,
    route_family_hint: str,
) -> str:
    return json.dumps(
        {
            "route_kind": "email_delivery",
            "route_family": route_family_hint or "browser_pdf_click",
            "route_summary": (
                "Open the report page and stop after repeated equivalent browser "
                "states without a verified route advance."
            ),
            "email_submission_completed": False,
            "blocked_reason": "blocked_no_progress",
            "blocked_reason_detail": (
                "Browser Use observed "
                f"{observation.consecutive_equivalent_turns} equivalent turns "
                "without a material route advance."
            ),
            "final_page_url": observation.url,
        },
        ensure_ascii=True,
    )


def _no_progress_log_fields(
    observation: BrowserNoProgressObservation,
    *,
    normalized_url: str,
) -> dict[str, Any]:
    return {
        "normalized_url": normalized_url,
        "state_fingerprint": observation.state_fingerprint,
        "consecutive_equivalent_turns": observation.consecutive_equivalent_turns,
        "step_number": observation.step_number,
        "blocker_state": observation.blocker_state,
        "document_candidate_count": observation.document_candidate_count,
        "artifact_count": observation.artifact_count,
        "network_document_count": observation.network_document_count,
        "confirmation_observed": observation.confirmation_observed,
    }


def run_browser_report_download_agent(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    prompt_bundle: BrowserDownloadPromptBundle,
    preflight_session: BrowserPreflightSession | None = None,
    inside_worker: bool = False,
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
    if preflight_session is None:
        launch_budget, launch_decision = _reserve_browser_launch(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        browser_use = _load_browser_use_runtime(normalized_url, ctx)
        launch_started = False
        launch_started_at = time.monotonic()
    else:
        browser_use = preflight_session.browser_use
        launch_budget = preflight_session.launch_budget
        launch_decision = preflight_session.launch_decision
        launch_started = True
        launch_started_at = preflight_session.launch_started_at
    launch_outcome = "completed"
    launch_error_code = ""
    if preflight_session is None and _should_run_browser_agent_in_subprocess(
        browser_use, request=request, inside_worker=inside_worker
    ):
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
        try:
            launch_started = True
            return _run_browser_report_download_agent_subprocess(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                execution_url=execution_url,
                download_dir=download_dir,
                prompt_bundle=prompt_bundle,
            )
        except AppError as exc:
            launch_outcome = "failed"
            launch_error_code = exc.code
            raise
        finally:
            _finalize_browser_launch(
                budget=launch_budget,
                decision=launch_decision,
                ctx=ctx,
                started=launch_started,
                outcome=launch_outcome,
                error_code=launch_error_code,
                runtime_seconds=max(0, int(time.monotonic() - launch_started_at)),
            )
    browser: Any | None = (
        preflight_session.browser if preflight_session is not None else None
    )
    usage_writer: BrowserUsageWriter | None = None
    if preflight_session is None:
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
    else:
        preexisting_temp_dirs = preflight_session.preexisting_temp_dirs
        session_reuse_decision = preflight_session.session_reuse_decision
        profile_dir = preflight_session.profile_dir
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
    execution_route_steps: list[BrowserDownloadRouteStep] = []
    browser_spend_reservation_key = ""
    no_progress_stopped = False
    try:
        if browser is None:
            launch_started = True
            browser = browser_use.Browser(
                downloads_path=str(download_dir),
                user_data_dir=str(profile_dir),
                headless=not request.settings.headed,
                auto_download_pdfs=True,
                keep_alive=True,
            )
        if inspect.iscoroutinefunction(getattr(browser, "start", None)):
            async_operation = _run_async_form_preflight_then_agent(
                browser_use=browser_use,
                browser=browser,
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                execution_url=execution_url,
                prompt_bundle=prompt_bundle,
            )
            async_execution = (
                preflight_session.event_loop_runner.run(async_operation)
                if preflight_session is not None
                and preflight_session.event_loop_runner is not None
                else asyncio.run(async_operation)
            )
            if async_execution.pre_llm_result is not None:
                return async_execution.pre_llm_result
            if async_execution.setup is None or async_execution.history_result is None:
                raise AppError(
                    code="browser_download_agent_missing_history",
                    message="browser-use completed without returning agent history",
                    retryable=True,
                    context={"normalized_url": normalized_url},
                )
            usage_writer = async_execution.setup.usage_writer
            browser_spend_reservation_key = async_execution.setup.spend_reservation_key
            history_result = async_execution.history_result
        else:
            pre_llm_form_result = _try_pre_llm_standard_form_submit(
                request=request,
                browser=browser,
                ctx=ctx,
                normalized_url=normalized_url,
                execution_url=execution_url,
            )
            if pre_llm_form_result is not None:
                return pre_llm_form_result
            setup = _build_browser_agent_run_setup(
                browser_use=browser_use,
                browser=browser,
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                prompt_bundle=prompt_bundle,
            )
            usage_writer = setup.usage_writer
            browser_spend_reservation_key = setup.spend_reservation_key
            history_result = _run_agent_history_with_timeout(
                agent=setup.agent,
                browser=browser,
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                no_progress_detector=setup.no_progress_detector,
            )
        history = history_result.history
        no_progress_observation = history_result.no_progress_observation
        no_progress_stopped = no_progress_observation is not None
        raw_model_response = str(history.final_result() or "").strip()
        if no_progress_observation is not None:
            raw_model_response = _no_progress_raw_model_response(
                no_progress_observation,
                route_family_hint=str(request.route_family_hint or "").strip(),
            )
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_no_progress_stopped",
                    module=logger.name,
                    fields=_no_progress_log_fields(
                        no_progress_observation,
                        normalized_url=normalized_url,
                    ),
                )
            )
        history_final_page_url = _read_history_final_page_url(history)
        history_final_page_title = _read_history_final_page_title(history)
        if no_progress_observation is not None:
            action_evidence_snapshot = TerminalSnapshot(
                page=None,
                url=str(no_progress_observation.url or ""),
                title="",
                html="",
            )
        else:
            action_evidence_snapshot = _capture_terminal_snapshot(
                browser,
                ctx=ctx,
                normalized_url=normalized_url,
            )
        execution_route_steps = capture_browser_execution_route_steps(
            history=history,
            final_page_url=(action_evidence_snapshot.url or history_final_page_url),
            final_page_title=(
                action_evidence_snapshot.title or history_final_page_title
            ),
            identity_value_references={
                str(field.value): f"identity.{field.key}"
                for field in resolve_effective_identity_fields(request)
                if str(field.value or "").strip() and str(field.key or "").strip()
            },
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_action_evidence_captured",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "action_count": len(execution_route_steps),
                    "verified_action_count": sum(
                        step.verification_status == "verified"
                        for step in execution_route_steps
                    ),
                },
            )
        )
        attachment_paths = _read_history_attachment_paths(history)
        history_screenshot_path = _copy_history_screenshot(
            history=history,
            download_dir=download_dir,
        )
        downloaded_files = [
            str(path) for path in getattr(browser, "downloaded_files", [])
        ]
        materialized_paths = (
            []
            if no_progress_stopped
            else _materialize_external_artifacts(
                raw_model_response=raw_model_response,
                attachment_paths=attachment_paths,
                downloaded_files=downloaded_files,
                download_dir=download_dir,
                ctx=ctx,
                normalized_url=normalized_url,
            )
        )
        for materialized_path in materialized_paths:
            if materialized_path not in attachment_paths:
                attachment_paths.append(materialized_path)
            if materialized_path not in downloaded_files:
                downloaded_files.append(materialized_path)
        prefetched_pdf_path = (
            ""
            if no_progress_stopped
            else _prefetch_structured_pdf_artifact(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                download_dir=download_dir,
                raw_model_response=raw_model_response,
                history_final_page_url=history_final_page_url,
            )
        )
        if prefetched_pdf_path and prefetched_pdf_path not in downloaded_files:
            downloaded_files.append(prefetched_pdf_path)
        lookup_submission_assisted = False
        if not no_progress_stopped and _should_attempt_lookup_submission_assist(
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
            not no_progress_stopped
            and not lookup_submission_assisted
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
        if no_progress_observation is not None:
            final_page_url = (
                str(no_progress_observation.url or "") or history_final_page_url
            )
            final_page_title = history_final_page_title
            screenshot_path = history_screenshot_path
        elif (
            history_result.salvaged_completed_history
            and not lookup_submission_assisted
            and not standard_form_submit_assisted
        ):
            final_page_url = history_final_page_url
            final_page_title = history_final_page_title
            screenshot_path = history_screenshot_path
            if no_progress_observation is None:
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
        launch_outcome = "failed"
        launch_error_code = exc.code
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
        launch_outcome = "failed"
        launch_error_code = "browser_download_agent_failed"
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
                message=(
                    "browser-use timed out while starting the local browser session"
                ),
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
        if usage_writer is not None:
            usage_writer.flush(
                timeout_seconds=request.settings.accounting_flush_timeout_seconds
            )
        if browser_spend_reservation_key:
            _release_browser_use_spend(
                request=request,
                ctx=ctx,
                reservation_key=browser_spend_reservation_key,
            )
        _finalize_browser_launch(
            budget=launch_budget,
            decision=launch_decision,
            ctx=ctx,
            started=launch_started,
            outcome=launch_outcome,
            error_code=launch_error_code,
            runtime_seconds=max(0, int(time.monotonic() - launch_started_at)),
        )
        if browser is not None:
            if not no_progress_stopped:
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
        if preflight_session is not None:
            preflight_session.closed = True
            _close_preflight_event_loop_runner(preflight_session)
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
        execution_route_steps=execution_route_steps,
    )


def _load_browser_use_runtime(normalized_url: str, ctx: RunContext) -> Any:
    os.environ.setdefault("BROWSER_USE_SETUP_LOGGING", "false")
    # Keep the process-local import seam at the canonical browser facade.  This
    # makes the ordinary installed runtime explicit and preserves the existing
    # public-boundary fake used by the browser fallback contract tests.  The
    # shared resolver remains responsible for the supported vendored fallback.
    try:
        runtime = import_module("browser_use")
    except ModuleNotFoundError:
        runtime = load_browser_use_runtime(normalized_url=normalized_url)
    runtime_identity = browser_runtime_identity(runtime)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_runtime_resolved",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "interpreter_path": runtime_identity.interpreter_path,
                "python_version": runtime_identity.python_version,
                "virtualenv_path": runtime_identity.virtualenv_path,
                "browser_use_module_path": runtime_identity.browser_use_module_path,
                "runtime_source": runtime_identity.runtime_source,
                "vendored_checksum": runtime_identity.vendored_checksum,
            },
        )
    )
    return runtime


def _reserve_browser_use_spend(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    prompt_bundle: BrowserDownloadPromptBundle,
) -> str:
    settings = request.settings
    provider = "openai" if str(settings.openai_api_key or "").strip() else "openrouter"
    model = settings.model if provider == "openai" else settings.openrouter_model
    reservation_key = spend_reservation_key(
        ctx,
        provider=provider,
        operation="browser_use_llm_call",
    )
    authority_budget = request.run_budget or RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name=request.publisher_name,
        usage_db_path=settings.usage_db_path,
        max_spend_usd=settings.daily_spend_stop_usd,
        limit_decision="stop",
        policy_version=settings.run_budget_policy_version,
        reservation_ttl_seconds=settings.run_budget_reservation_ttl_seconds,
        run_limits=settings.run_budget_limits_run,
        day_limits=settings.run_budget_limits_day,
        publisher_limits=settings.run_budget_limits_publisher,
        enabled_effect_kinds=settings.run_budget_enabled_effect_kinds,
    )
    authority = evaluate_budget_request(
        BudgetRequest(
            schema_version="1.0",
            budget=authority_budget,
            run_id=ctx.run_id,
            workflow_id="browser_acquisition",
            publisher_id=request.publisher_name,
            report_id=_browser_usage_report_name(request),
            resource_type="browser_use_model",
            operation="browser_use_llm_call",
            provider=provider,
            model=model,
            prompt_namespace=prompt_bundle.namespace,
            forecast_method="historical_median",
            idempotency_key=reservation_key,
            reserve_in_flight=True,
        ),
        ctx,
    )
    if authority.decision in {"defer", "pause", "stop"}:
        raise AppError(
            code=f"browser_use_budget_{authority.decision}",
            message=(
                "Browser Use provider call blocked by the canonical budget authority"
            ),
            retryable=False,
            context={
                "reason_code": authority.reason_code,
                "affected_limit": authority.affected_limit,
                "retry_decision": (
                    "defer" if authority.decision == "defer" else "abort"
                ),
                "next_action": authority.next_action,
            },
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_spend_decision",
            module=logger.name,
            fields={
                "provider": provider,
                "model": model,
                "decision": authority.decision,
                "projected_spend_usd": authority.projected_usage.spend_usd,
                "forecast_status": authority.reason_code,
                "reservation_created": authority.reservation_created,
            },
        )
    )
    return reservation_key


def _release_browser_use_spend(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    reservation_key: str,
) -> None:
    try:
        reconcile_budget_reservation(
            BudgetReservationReconcileRequest(
                schema_version="1.0",
                usage_db_path=request.settings.usage_db_path,
                reservation_key=reservation_key,
                actual_cost_usd=0.0,
            ),
            ctx,
        )
    except AppError as exc:
        logger.error(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_spend_release_failed",
                module=logger.name,
                fields={"code": exc.code, "reservation_key": reservation_key},
            )
        )


def _reserve_browser_launch(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    idempotency_suffix: str = "",
) -> tuple[RunBudget, BudgetDecision]:
    """Reserve the browser-launch ceiling immediately before browser startup."""
    budget = request.run_budget or RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name=request.publisher_name,
        usage_db_path=request.settings.usage_db_path,
        max_spend_usd=request.settings.daily_spend_stop_usd,
        max_browser_launches=request.settings.run_budget_max_browser_launches,
        limit_decision=request.settings.run_budget_limit_decision,
        policy_version=request.settings.run_budget_policy_version,
        reservation_ttl_seconds=request.settings.run_budget_reservation_ttl_seconds,
        run_limits=request.settings.run_budget_limits_run,
        day_limits=request.settings.run_budget_limits_day,
        publisher_limits=request.settings.run_budget_limits_publisher,
        enabled_effect_kinds=request.settings.run_budget_enabled_effect_kinds,
    )
    decision = evaluate_budget_request(
        BudgetRequest(
            schema_version="1.0",
            budget=budget,
            run_id=ctx.run_id,
            workflow_id="browser_acquisition",
            publisher_id=request.publisher_name,
            report_id=_browser_usage_report_name(request) or normalized_url,
            resource_type="browser_launch",
            operation="browser_launch",
            estimated_duration_seconds=int(request.settings.timeout_seconds),
            forecast_method="explicit",
            idempotency_key=(
                f"browser-launch:{ctx.run_id}:{ctx.task_id}:{ctx.span_id}"
                f":{idempotency_suffix.strip()}"
                if idempotency_suffix.strip()
                else f"browser-launch:{ctx.run_id}:{ctx.task_id}:{ctx.span_id}"
            ),
            reserve_in_flight=True,
        ),
        ctx,
    )
    if decision.decision in {"defer", "pause", "stop"}:
        raise AppError(
            code=f"browser_budget_{decision.decision}",
            message="Browser launch was blocked by the canonical budget authority",
            retryable=False,
            context={
                "reason_code": decision.reason_code,
                "affected_limit": decision.affected_limit,
                "retry_decision": "defer" if decision.decision == "defer" else "abort",
                "next_action": decision.next_action,
            },
        )
    return budget, decision


def _finalize_browser_launch(
    *,
    budget: RunBudget,
    decision: BudgetDecision,
    ctx: RunContext,
    started: bool,
    outcome: str,
    error_code: str,
    runtime_seconds: int,
) -> None:
    if not decision.reservation_key:
        return
    finalize_budget_side_effect(
        BudgetSideEffectFinalizeRequest(
            schema_version="1.0",
            usage_db_path=budget.usage_db_path,
            reservation_key=decision.reservation_key,
            actual_usage=RunBudgetUsage(
                schema_version="1.0",
                browser_launches=1 if started else 0,
                runtime_seconds=max(0, runtime_seconds),
            ),
            outcome=outcome,
            error_code=error_code,
        ),
        ctx,
    )


def _configure_browser_use_usage_recorder(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    prompt_bundle: BrowserDownloadPromptBundle,
    llm_clients: Any,
    agent: Any,
) -> BrowserUsageWriter | None:
    token_cost_service = getattr(agent, "token_cost_service", None)
    set_usage_callback = getattr(token_cost_service, "set_usage_callback", None)
    if not callable(set_usage_callback):
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_llm_usage_callback_unavailable",
                module=logger.name,
                fields={"normalized_url": normalized_url},
            )
        )
        return None
    writer = BrowserUsageWriter(
        ctx=ctx,
        queue_size=request.settings.accounting_queue_size,
        normalized_url=normalized_url,
    )
    entry_index = 0

    def _record_entry(entry: Any) -> None:
        nonlocal entry_index
        usage = getattr(entry, "usage", None)
        if usage is None:
            return
        entry_index += 1
        model_name = str(getattr(entry, "model", "") or "")
        usage_request = _record_browser_use_usage_row(
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
            total_tokens=_optional_usage_int(getattr(usage, "total_tokens", None)),
            cached_tokens=_optional_usage_int(
                getattr(usage, "prompt_cached_tokens", None)
            ),
            request_id=str(getattr(entry, "request_id", "") or "") or None,
            extra={
                "browser_usage_entry_index": entry_index,
                "browser_usage_timestamp": str(getattr(entry, "timestamp", "") or ""),
            },
        )
        writer.enqueue(usage_request)

    set_usage_callback(_record_entry)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_llm_usage_callback_configured",
            module=logger.name,
            fields={"normalized_url": normalized_url},
        )
    )
    return writer


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
    request_id: str | None,
    extra: dict[str, Any],
) -> OpenAIUsageAccountingRequest:
    row_extra = {
        "route_family_hint": request.route_family_hint or "",
        "route_kind_hint": request.route_kind_hint or "",
        "primary_provider": getattr(llm_clients, "primary_provider", ""),
        "fallback_provider": (getattr(llm_clients, "fallback_provider", "") or ""),
        **extra,
    }
    return OpenAIUsageAccountingRequest(
        schema_version="1.0",
        step_name="browser_use_llm_call",
        model=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_tokens,
        tool_calls=0,
        cost_ledger_path=request.settings.cost_ledger_path,
        cost_daily_path=request.settings.cost_daily_path,
        emit_cost_ledger=False,
        model_pricing=request.settings.model_pricing,
        request_id=request_id,
        provider=_browser_usage_provider(
            model=model_name,
            llm_clients=llm_clients,
        ),
        action="browser_use_llm_call",
        usage_db_path=request.settings.usage_db_path,
        publisher_name=request.publisher_name,
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
        call_ordinal=int(extra.get("browser_usage_entry_index") or 0),
        extra=row_extra,
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
    return str(request.report_title or "").strip()


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
