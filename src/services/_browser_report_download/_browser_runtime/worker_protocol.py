# ruff: noqa: F401
from __future__ import annotations

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
from typing import Any
from urllib.parse import urlsplit

import psutil

from src.contracts.browser_download import (
    BrowserDownloadDialogEvidence,
    BrowserDownloadNetworkEvent,
    BrowserDownloadRouteStep,
    BrowserReportDownloadRequest,
    BrowserRoutePlaybook,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.cdp import (
    capture_print_pdf_via_cdp,
    collect_terminal_dialog_evidence_via_cdp,
    collect_terminal_network_entries_via_cdp,
    ensure_browser_download_target_hygiene_via_cdp,
)
from src.services._browser_report_download.helpers import (
    browser_helper_capture_screenshot,
    browser_helper_form_autocomplete,
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
from src.services._browser_report_download._browser_runtime.session_lifecycle import (
    _resolve_agent_run_timeout_seconds,
)

logger = logging.getLogger("market_lense.browser_report_download_service")


@dataclass(frozen=True)
class BrowserAgentWorkerPayload:
    schema_version: str
    request: dict[str, Any]
    ctx: dict[str, Any]
    normalized_url: str
    execution_url: str
    download_dir: str
    prompt_bundle: dict[str, Any]
    execution_mode: str = "agent"
    deterministic_playbook: dict[str, Any] | None = None


@dataclass(frozen=True)
class BrowserAgentWorkerResponse:
    schema_version: str
    status: str
    result: dict[str, Any] | None
    error: dict[str, Any] | None


def _should_run_browser_agent_in_subprocess(
    browser_use: Any,
    request: BrowserReportDownloadRequest | None = None,
    *,
    inside_worker: bool = False,
) -> bool:
    if inside_worker:
        return False
    if os.environ.get(_BROWSER_AGENT_WORKER_ENV) == "1":
        return False
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    if request is not None and request.settings.headed:
        return False
    return True


def _run_browser_report_download_agent_subprocess(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    prompt_bundle: BrowserDownloadPromptBundle,
    deterministic_playbook: BrowserRoutePlaybook | None = None,
) -> BrowserAgentRunResult:
    warm_pool_policy = request.settings.warm_worker_pool_policy
    if warm_pool_policy.enabled:
        from src.services._browser_report_download.worker_pool import (
            default_warm_worker_pool,
        )

        try:
            pooled_result = default_warm_worker_pool().run(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                execution_url=execution_url,
                download_dir=download_dir,
                prompt_bundle=prompt_bundle,
            )
        except AppError as exc:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_warm_worker_pool_failed",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "error_code": exc.code,
                        "fallback_to_subprocess": (
                            warm_pool_policy.fallback_to_subprocess
                        ),
                    },
                )
            )
            if not warm_pool_policy.fallback_to_subprocess:
                raise
        else:
            if pooled_result is not None:
                return pooled_result

    download_dir.mkdir(parents=True, exist_ok=True)
    payload = BrowserAgentWorkerPayload(
        schema_version="1.0",
        request=asdict(request),
        ctx=asdict(ctx),
        normalized_url=normalized_url,
        execution_url=execution_url,
        download_dir=str(download_dir),
        prompt_bundle=asdict(prompt_bundle),
        execution_mode=("deterministic_playbook" if deterministic_playbook else "agent"),
        deterministic_playbook=(
            asdict(deterministic_playbook) if deterministic_playbook else None
        ),
    )
    payload_path = download_dir / "browser_agent_worker_request.json"
    response_path = download_dir / "browser_agent_worker_response.json"
    payload_path.write_text(
        json.dumps(asdict(payload), ensure_ascii=True),
        encoding="utf-8",
    )
    response_path.unlink(missing_ok=True)
    env = dict(os.environ)
    env[_BROWSER_AGENT_WORKER_ENV] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.setdefault("NO_COLOR", "1")
    env.setdefault("RICH_DISABLE", "1")
    # The worker owns browser-process teardown after Agent completion. Do not
    # wait for its independent telemetry EventBus to drain while a stopped
    # Agent is holding acquisition completion open.
    env["TIMEOUT_AgentEventBusStop"] = "0"
    timeout_seconds = (
        _resolve_agent_run_timeout_seconds(request)
        + _BROWSER_AGENT_WORKER_TIMEOUT_BUFFER_SECONDS
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_worker_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "payload_path": str(payload_path),
                "response_path": str(response_path),
                "timeout_seconds": timeout_seconds,
            },
        )
    )
    try:
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.services._browser_report_download.browser_worker",
                    str(payload_path),
                    str(response_path),
                ],
                check=False,
                cwd=str(Path.cwd()),
                env=env,
                # Chrome inherits worker handles.  A PIPE makes communicate()
                # wait for the browser child to close that pipe even after the
                # disposable worker has written its canonical response file.
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            worker_output_excerpt = _normalize_browser_worker_output_excerpt(
                exc.stdout if isinstance(exc.stdout, str) else ""
            )
            raise AppError(
                code="browser_download_agent_timeout",
                message="browser-use did not return within the configured execution budget",
                cause=exc,
                retryable=True,
                context={
                    "normalized_url": normalized_url,
                    "timeout_seconds": timeout_seconds,
                    "max_steps": request.settings.max_steps,
                    "worker_output_excerpt": worker_output_excerpt,
                },
            ) from exc
    finally:
        _discard_browser_agent_worker_payload(
            payload_path=payload_path,
            ctx=ctx,
            normalized_url=normalized_url,
        )
    worker_output_excerpt = ""
    completion_fields: dict[str, Any] = {
        "normalized_url": normalized_url,
        "payload_path": str(payload_path),
        "payload_retained": False,
        "response_path": str(response_path),
        "return_code": completed.returncode,
        "response_exists": response_path.exists(),
        "worker_output_captured": False,
    }
    if worker_output_excerpt:
        completion_fields["worker_output_excerpt"] = worker_output_excerpt
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_worker_complete",
            module=logger.name,
            fields=completion_fields,
        )
    )
    if not response_path.exists():
        raise AppError(
            code="browser_download_agent_missing_result",
            message="browser-use worker completed without writing a response payload",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "return_code": completed.returncode,
                "worker_output_excerpt": worker_output_excerpt,
            },
        )
    raw_response = json.loads(response_path.read_text(encoding="utf-8"))
    response = BrowserAgentWorkerResponse(
        schema_version=str(raw_response.get("schema_version", "1.0")),
        status=str(raw_response.get("status", "")).strip(),
        result=raw_response.get("result")
        if isinstance(raw_response.get("result"), dict)
        else None,
        error=raw_response.get("error")
        if isinstance(raw_response.get("error"), dict)
        else None,
    )
    if response.status == "drifted" and deterministic_playbook is not None:
        return None  # type: ignore[return-value]
    if response.status == "ok" and response.result is not None:
        return _deserialize_browser_agent_run_result(response.result)
    if response.error is not None:
        raise AppError(
            code=str(response.error.get("code") or "browser_download_agent_failed"),
            message=str(
                response.error.get("message")
                or "browser-use worker failed to complete the report download task"
            ),
            retryable=bool(response.error.get("retryable", True)),
            severity=str(response.error.get("severity") or "error"),
            context=response.error.get("context")
            if isinstance(response.error.get("context"), dict)
            else {"normalized_url": normalized_url},
        )
    raise AppError(
        code="browser_download_agent_failed",
        message="browser-use worker failed to complete the report download task",
        retryable=True,
        context={"normalized_url": normalized_url},
    )


def _discard_browser_agent_worker_payload(
    *,
    payload_path: Path,
    ctx: RunContext,
    normalized_url: str,
) -> None:
    payload_existed = payload_path.exists()
    try:
        payload_path.unlink(missing_ok=True)
    except OSError as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_worker_payload_cleanup_failed",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "payload_path": str(payload_path),
                    "payload_existed": payload_existed,
                    "error": str(exc),
                },
            )
        )
        raise AppError(
            code="browser_download_worker_payload_cleanup_failed",
            message="Browser worker request payload could not be removed",
            cause=exc,
            retryable=False,
            context={
                "normalized_url": normalized_url,
                "payload_path": str(payload_path),
            },
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_worker_payload_discarded",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "payload_path": str(payload_path),
                "payload_existed": payload_existed,
            },
        )
    )


def _normalize_browser_worker_output_excerpt(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    without_ansi = _ANSI_ESCAPE_PATTERN.sub("", value)
    normalized = without_ansi.replace("\r\n", "\n").replace("\r", "\n")
    ascii_only = "".join(
        character
        if character == "\n" or character == "\t" or 32 <= ord(character) <= 126
        else " "
        for character in normalized
    )
    collapsed_lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in ascii_only.splitlines()
        if line.strip()
    ]
    excerpt = "\n".join(collapsed_lines).strip()
    if len(excerpt) <= _BROWSER_AGENT_WORKER_OUTPUT_MAX_CHARS:
        return excerpt
    return excerpt[: _BROWSER_AGENT_WORKER_OUTPUT_MAX_CHARS - 3].rstrip() + "..."


def _deserialize_browser_agent_run_result(
    payload: dict[str, Any],
) -> BrowserAgentRunResult:
    network_events_payload = payload.get("network_events")
    network_events: list[BrowserDownloadNetworkEvent] = []
    if isinstance(network_events_payload, list):
        for item in network_events_payload:
            if not isinstance(item, dict):
                continue
            network_events.append(
                BrowserDownloadNetworkEvent(
                    schema_version=str(item.get("schema_version", "1.0")),
                    url=str(item.get("url") or "").strip(),
                    initiator_type=str(item.get("initiator_type") or "other").strip()
                    or "other",
                    signal_kind=str(item.get("signal_kind") or "other").strip()
                    or "other",
                )
            )
    dialog_evidence_payload = payload.get("dialog_evidence")
    dialog_evidence: list[BrowserDownloadDialogEvidence] = []
    if isinstance(dialog_evidence_payload, list):
        for item in dialog_evidence_payload:
            if not isinstance(item, dict):
                continue
            dialog_evidence.append(
                BrowserDownloadDialogEvidence(
                    schema_version=str(item.get("schema_version", "1.0")),
                    dialog_type=str(item.get("dialog_type") or "unknown").strip()
                    or "unknown",
                    message=str(item.get("message") or "").strip(),
                    page_url=str(item.get("page_url") or "").strip(),
                    action_taken=str(item.get("action_taken") or "none").strip()
                    or "none",
                    validation_status=str(
                        item.get("validation_status") or "failed"
                    ).strip()
                    or "failed",
                    target_id=str(item.get("target_id") or "").strip(),
                    session_id=str(item.get("session_id") or "").strip(),
                )
            )
    execution_route_steps = _deserialize_execution_route_steps(
        payload.get("execution_route_steps")
    )
    return BrowserAgentRunResult(
        schema_version=str(payload.get("schema_version", "1.0")),
        raw_model_response=str(payload.get("raw_model_response") or ""),
        final_page_url=str(payload.get("final_page_url") or ""),
        final_page_title=str(payload.get("final_page_title") or ""),
        final_page_html=str(payload.get("final_page_html") or ""),
        downloaded_files=[
            str(item)
            for item in payload.get("downloaded_files", [])
            if str(item or "").strip()
        ],
        attachment_paths=[
            str(item)
            for item in payload.get("attachment_paths", [])
            if str(item or "").strip()
        ],
        network_resource_urls=[
            str(item)
            for item in payload.get("network_resource_urls", [])
            if str(item or "").strip()
        ],
        network_events=network_events,
        html_snapshot_path=str(payload.get("html_snapshot_path") or ""),
        screenshot_path=str(payload.get("screenshot_path") or ""),
        print_pdf_capture_path=str(payload.get("print_pdf_capture_path") or ""),
        print_pdf_capture_provenance=str(
            payload.get("print_pdf_capture_provenance") or ""
        ),
        dialog_evidence=dialog_evidence,
        execution_route_steps=execution_route_steps,
    )


def _deserialize_execution_route_steps(
    raw_value: Any,
) -> list[BrowserDownloadRouteStep]:
    if not isinstance(raw_value, list):
        return []
    steps: list[BrowserDownloadRouteStep] = []
    for item in raw_value:
        if not isinstance(item, dict):
            continue
        steps.append(
            BrowserDownloadRouteStep(
                schema_version=str(item.get("schema_version", "1.0")),
                index=int(item.get("index", len(steps))),
                action=str(item.get("action") or "").strip(),
                target_text=str(item.get("target_text") or "").strip(),
                target_role=str(item.get("target_role") or "").strip(),
                target_url=str(item.get("target_url") or "").strip(),
                result=str(item.get("result") or "").strip(),
                expected_evidence=_string_list(item.get("expected_evidence")),
                observed_evidence=_string_list(item.get("observed_evidence")),
                locator_evidence=_string_list(item.get("locator_evidence")),
                postcondition_evidence=_string_list(
                    item.get("postcondition_evidence")
                ),
                verification_status=str(item.get("verification_status") or "").strip(),
                locator_role=str(item.get("locator_role") or "").strip(),
                locator_name=str(item.get("locator_name") or "").strip(),
                locator_label=str(item.get("locator_label") or "").strip(),
                locator_field_name=str(item.get("locator_field_name") or "").strip(),
                locator_data_attribute=str(
                    item.get("locator_data_attribute") or ""
                ).strip(),
                locator_css=str(item.get("locator_css") or "").strip(),
                locator_text=str(item.get("locator_text") or "").strip(),
                identity_field_reference=str(
                    item.get("identity_field_reference") or ""
                ).strip(),
                expected_url_contains=str(
                    item.get("expected_url_contains") or ""
                ).strip(),
                expected_text=str(item.get("expected_text") or "").strip(),
            )
        )
    return steps


def _string_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    return [str(item).strip() for item in raw_value if str(item or "").strip()]
