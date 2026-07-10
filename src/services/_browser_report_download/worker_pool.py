from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Callable
from urllib.parse import urlsplit

import psutil

from src.contracts.browser_download import (
    BrowserDownloadDialogEvidence,
    BrowserDownloadNetworkEvent,
    BrowserDownloadWarmWorkerPoolDecision,
    BrowserReportDownloadRequest,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.models import BrowserAgentRunResult
from src.services._browser_report_download.prompt import BrowserDownloadPromptBundle
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service.worker_pool")

_WORKER_RESPONSE_POLL_SECONDS = 0.05
_WORKER_RESPONSE_SCHEMA_VERSION = "1.0"


class _WarmWorkerSlot:
    def __init__(self, process: Any, started_at: float) -> None:
        self.process = process
        self.started_at = started_at
        self.last_used_at = started_at
        self.run_count = 0


class BrowserWarmWorkerPool:
    def __init__(
        self,
        *,
        process_factory: Callable[..., Any] | None = None,
        memory_reader: Callable[[int], int] | None = None,
        monotonic_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._process_factory = process_factory or subprocess.Popen
        self._memory_reader = memory_reader or _process_rss_bytes
        self._monotonic_fn = monotonic_fn
        self._sleep_fn = sleep_fn
        self._slots: dict[str, _WarmWorkerSlot] = {}
        self._lock = RLock()

    def run(
        self,
        *,
        request: BrowserReportDownloadRequest,
        ctx: RunContext,
        normalized_url: str,
        execution_url: str,
        download_dir: Path,
        prompt_bundle: BrowserDownloadPromptBundle,
    ) -> BrowserAgentRunResult | None:
        decision = resolve_warm_worker_pool_decision(
            request=request,
            normalized_url=normalized_url,
        )
        if not decision.accepted:
            _log_decision(ctx=ctx, normalized_url=normalized_url, decision=decision)
            return None
        _log_decision(ctx=ctx, normalized_url=normalized_url, decision=decision)
        with self._lock:
            slot = self._slot_for_decision(decision, request, ctx, normalized_url)
            try:
                result = self._dispatch_to_slot(
                    slot=slot,
                    request=request,
                    ctx=ctx,
                    normalized_url=normalized_url,
                    execution_url=execution_url,
                    download_dir=download_dir,
                    prompt_bundle=prompt_bundle,
                )
            except AppError:
                self._stop_slot(decision.pool_key_hash)
                raise
            slot.run_count += 1
            slot.last_used_at = self._monotonic_fn()
            if slot.run_count >= decision.max_runs_per_worker:
                self._stop_slot(decision.pool_key_hash)
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="browser_warm_worker_pool_restart_after_run_limit",
                        module=logger.name,
                        fields={
                            "normalized_url": normalized_url,
                            "pool_key_hash": decision.pool_key_hash,
                            "run_count": slot.run_count,
                            "max_runs_per_worker": decision.max_runs_per_worker,
                        },
                    )
                )
            return result

    def _slot_for_decision(
        self,
        decision: BrowserDownloadWarmWorkerPoolDecision,
        request: BrowserReportDownloadRequest,
        ctx: RunContext,
        normalized_url: str,
    ) -> _WarmWorkerSlot:
        existing = self._slots.get(decision.pool_key_hash)
        if existing is not None and not self._slot_requires_restart(
            existing, request=request
        ):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_warm_worker_pool_reused",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "pool_key_hash": decision.pool_key_hash,
                        "pid": int(getattr(existing.process, "pid", 0) or 0),
                        "run_count": existing.run_count,
                    },
                )
            )
            return existing
        if existing is not None:
            self._stop_slot(decision.pool_key_hash)
        self._enforce_max_workers(request)
        process = self._start_process()
        slot = _WarmWorkerSlot(process=process, started_at=self._monotonic_fn())
        self._slots[decision.pool_key_hash] = slot
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_warm_worker_pool_started",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "pool_key_hash": decision.pool_key_hash,
                    "pid": int(getattr(process, "pid", 0) or 0),
                },
            )
        )
        return slot

    def _enforce_max_workers(self, request: BrowserReportDownloadRequest) -> None:
        max_workers = max(int(request.settings.warm_worker_pool_policy.max_workers), 1)
        while len(self._slots) >= max_workers:
            oldest_key = min(
                self._slots,
                key=lambda key: self._slots[key].last_used_at,
            )
            self._stop_slot(oldest_key)

    def _slot_requires_restart(
        self,
        slot: _WarmWorkerSlot,
        *,
        request: BrowserReportDownloadRequest,
    ) -> bool:
        if slot.process.poll() is not None:
            return True
        policy = request.settings.warm_worker_pool_policy
        if slot.run_count >= int(policy.max_runs_per_worker):
            return True
        idle_seconds = self._monotonic_fn() - slot.last_used_at
        if idle_seconds > float(policy.idle_ttl_seconds):
            return True
        pid = int(getattr(slot.process, "pid", 0) or 0)
        if pid and self._memory_reader(pid) > int(policy.max_memory_mb) * 1024 * 1024:
            return True
        return False

    def _dispatch_to_slot(
        self,
        *,
        slot: _WarmWorkerSlot,
        request: BrowserReportDownloadRequest,
        ctx: RunContext,
        normalized_url: str,
        execution_url: str,
        download_dir: Path,
        prompt_bundle: BrowserDownloadPromptBundle,
    ) -> BrowserAgentRunResult:
        download_dir.mkdir(parents=True, exist_ok=True)
        payload_path = download_dir / "browser_agent_worker_request.json"
        response_path = download_dir / "browser_agent_worker_response.json"
        payload = {
            "schema_version": "1.0",
            "request": asdict(request),
            "ctx": asdict(ctx),
            "normalized_url": normalized_url,
            "execution_url": execution_url,
            "download_dir": str(download_dir),
            "prompt_bundle": asdict(prompt_bundle),
        }
        payload_path.write_text(
            json.dumps(payload, ensure_ascii=True), encoding="utf-8"
        )
        response_path.unlink(missing_ok=True)
        stdin = getattr(slot.process, "stdin", None)
        if stdin is None:
            raise AppError(
                code="browser_warm_worker_stdin_missing",
                message="Warm browser worker process has no command pipe",
                retryable=True,
                context={"normalized_url": normalized_url},
            )
        timeout_seconds = _warm_worker_timeout_seconds(request)
        command = json.dumps(
            {"payload_path": str(payload_path), "response_path": str(response_path)},
            ensure_ascii=True,
        )
        stdin.write(f"{command}\n")
        stdin.flush()
        started = self._monotonic_fn()
        try:
            while not response_path.exists():
                if slot.process.poll() is not None:
                    raise AppError(
                        code="browser_warm_worker_exited",
                        message="Warm browser worker exited before writing a response",
                        retryable=True,
                        context={"normalized_url": normalized_url},
                    )
                if self._monotonic_fn() - started > timeout_seconds:
                    raise AppError(
                        code="browser_download_agent_timeout",
                        message=(
                            "browser-use warm worker did not return within the "
                            "configured execution budget"
                        ),
                        retryable=True,
                        context={
                            "normalized_url": normalized_url,
                            "timeout_seconds": timeout_seconds,
                            "max_steps": request.settings.max_steps,
                        },
                    )
                self._sleep_fn(_WORKER_RESPONSE_POLL_SECONDS)
            return _read_worker_response(response_path, normalized_url=normalized_url)
        finally:
            try:
                payload_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _start_process(self) -> Any:
        env = dict(os.environ)
        env["BROWSER_AGENT_WORKER"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env.setdefault("NO_COLOR", "1")
        env.setdefault("RICH_DISABLE", "1")
        return self._process_factory(
            [
                sys.executable,
                "-m",
                "src.services._browser_report_download.browser_worker",
                "--serve",
            ],
            cwd=str(Path.cwd()),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def _stop_slot(self, pool_key_hash: str) -> None:
        slot = self._slots.pop(pool_key_hash, None)
        if slot is None:
            return
        process = slot.process
        try:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5.0)
        except Exception:
            try:
                process.kill()
            except Exception:
                return


def resolve_warm_worker_pool_decision(
    *,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
) -> BrowserDownloadWarmWorkerPoolDecision:
    policy = request.settings.warm_worker_pool_policy
    session_policy = request.settings.session_reuse_policy
    publisher_scope = _normalize_scope(session_policy.publisher_scope)
    if not policy.enabled:
        return _decision(policy, False, publisher_scope, "", "disabled")
    if request.settings.headed:
        return _decision(policy, False, publisher_scope, "", "headed_browser")
    if not session_policy.enabled:
        return _decision(policy, False, publisher_scope, "", "session_reuse_disabled")
    if str(session_policy.mode or "").strip() != "same_publisher_batch":
        return _decision(policy, False, publisher_scope, "", "unsupported_session_mode")
    if session_policy.allow_cross_publisher:
        return _decision(
            policy,
            False,
            publisher_scope,
            "",
            "cross_publisher_reuse_not_allowed",
        )
    if not publisher_scope:
        return _decision(policy, False, publisher_scope, "", "missing_publisher_scope")
    url_scope = _normalize_scope(normalized_url)
    if (
        url_scope
        and url_scope != publisher_scope
        and not url_scope.endswith(f".{publisher_scope}")
    ):
        return _decision(policy, False, publisher_scope, "", "publisher_scope_mismatch")
    session_key = str(session_policy.session_key or "").strip()
    if not session_key:
        return _decision(policy, False, publisher_scope, "", "missing_session_key")
    pool_key_hash = sha256(
        f"{publisher_scope}\n{session_key}".encode("utf-8")
    ).hexdigest()[:16]
    return _decision(policy, True, publisher_scope, pool_key_hash, "")


def default_warm_worker_pool() -> BrowserWarmWorkerPool:
    return _DEFAULT_POOL


def _decision(
    policy: Any,
    accepted: bool,
    publisher_scope: str,
    pool_key_hash: str,
    rejection_reason: str,
) -> BrowserDownloadWarmWorkerPoolDecision:
    return BrowserDownloadWarmWorkerPoolDecision(
        schema_version=_WORKER_RESPONSE_SCHEMA_VERSION,
        enabled=bool(getattr(policy, "enabled", False)),
        accepted=accepted,
        publisher_scope=publisher_scope,
        pool_key_hash=pool_key_hash,
        max_runs_per_worker=max(int(getattr(policy, "max_runs_per_worker", 1) or 1), 1),
        max_memory_mb=max(int(getattr(policy, "max_memory_mb", 128) or 128), 128),
        rejection_reason=rejection_reason,
    )


def _normalize_scope(value: object) -> str:
    token = str(value or "").strip().casefold()
    if "://" in token:
        token = str(urlsplit(token).netloc or "").strip().casefold()
    return token[4:] if token.startswith("www.") else token


def _warm_worker_timeout_seconds(request: BrowserReportDownloadRequest) -> float:
    return max(
        float(request.settings.timeout_seconds),
        1.0,
    ) + max(5.0, float(request.settings.max_steps) * 2.0)


def _read_worker_response(
    response_path: Path,
    *,
    normalized_url: str,
) -> BrowserAgentRunResult:
    raw_response = json.loads(response_path.read_text(encoding="utf-8"))
    status = str(raw_response.get("status") or "").strip()
    result = raw_response.get("result")
    error = raw_response.get("error")
    if status == "ok" and isinstance(result, dict):
        return _deserialize_browser_agent_run_result(result)
    if isinstance(error, dict):
        raise AppError(
            code=str(error.get("code") or "browser_download_agent_failed"),
            message=str(
                error.get("message")
                or "Warm browser worker failed to complete the report download task"
            ),
            retryable=bool(error.get("retryable", True)),
            severity=str(error.get("severity") or "error"),
            context=error.get("context")
            if isinstance(error.get("context"), dict)
            else {"normalized_url": normalized_url},
        )
    raise AppError(
        code="browser_download_agent_failed",
        message="Warm browser worker failed to complete the report download task",
        retryable=True,
        context={"normalized_url": normalized_url},
    )


def _deserialize_browser_agent_run_result(
    payload: dict[str, Any],
) -> BrowserAgentRunResult:
    network_events = [
        BrowserDownloadNetworkEvent(
            schema_version=str(item.get("schema_version", "1.0")),
            url=str(item.get("url") or "").strip(),
            initiator_type=str(item.get("initiator_type") or "other").strip()
            or "other",
            signal_kind=str(item.get("signal_kind") or "other").strip() or "other",
        )
        for item in payload.get("network_events", [])
        if isinstance(item, dict)
    ]
    dialog_evidence = [
        BrowserDownloadDialogEvidence(
            schema_version=str(item.get("schema_version", "1.0")),
            dialog_type=str(item.get("dialog_type") or "unknown").strip() or "unknown",
            message=str(item.get("message") or "").strip(),
            page_url=str(item.get("page_url") or "").strip(),
            action_taken=str(item.get("action_taken") or "none").strip() or "none",
            validation_status=str(item.get("validation_status") or "failed").strip()
            or "failed",
            target_id=str(item.get("target_id") or "").strip(),
            session_id=str(item.get("session_id") or "").strip(),
        )
        for item in payload.get("dialog_evidence", [])
        if isinstance(item, dict)
    ]
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
    )


def _process_rss_bytes(pid: int) -> int:
    try:
        return int(psutil.Process(pid).memory_info().rss)
    except (psutil.Error, OSError, ValueError):
        return 0


def _log_decision(
    *,
    ctx: RunContext,
    normalized_url: str,
    decision: BrowserDownloadWarmWorkerPoolDecision,
) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_warm_worker_pool_decision",
            module=logger.name,
            fields={"normalized_url": normalized_url, **asdict(decision)},
        )
    )


_DEFAULT_POOL = BrowserWarmWorkerPool()
