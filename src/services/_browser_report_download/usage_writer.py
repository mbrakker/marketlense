from __future__ import annotations

import logging
import queue
import time
from threading import Event, Lock, Thread

from src.contracts._browser_download.usage import BrowserUsageWriterShutdownResponse
from src.contracts.openai import OpenAIUsageAccountingRequest
from src.contracts.run_context import RunContext
from src.services import openai_accounting_service
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")


class BrowserUsageWriter:
    """Bounded callback sink that keeps browser-use token callbacks off the agent path."""

    def __init__(
        self, *, ctx: RunContext, queue_size: int, normalized_url: str
    ) -> None:
        self._ctx = ctx
        self._normalized_url = normalized_url
        self._queue: queue.Queue[OpenAIUsageAccountingRequest | None] = queue.Queue(
            maxsize=max(1, queue_size)
        )
        self._closed = Event()
        self._stop_requested = Event()
        self._counter_lock = Lock()
        self._written_events = 0
        self._dropped_events = 0
        self._thread = Thread(
            target=self._run,
            name="browser-usage-writer",
            daemon=True,
        )
        self._thread.start()

    def enqueue(self, request: OpenAIUsageAccountingRequest) -> bool:
        if self._closed.is_set():
            self._record_drop("closed")
            return False
        try:
            self._queue.put_nowait(request)
            return True
        except queue.Full:
            self._record_drop("queue_full")
            return False

    def flush(self, *, timeout_seconds: float) -> BrowserUsageWriterShutdownResponse:
        """Close intake first, then drain only until the caller's bounded deadline."""
        self._closed.set()
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        drained = not self._queue.unfinished_tasks
        pending_events = self._queue.unfinished_tasks
        if not drained:
            logger.warning(
                log_event(
                    self._ctx,
                    role="service",
                    event="browser_usage_accounting_flush_timeout",
                    module=logger.name,
                    fields={
                        "normalized_url": self._normalized_url,
                        "timeout_seconds": timeout_seconds,
                        "remaining_events": self._queue.unfinished_tasks,
                    },
                )
            )
        self._stop_requested.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            # The worker observes stop_requested once it drains this bounded queue.
            pass
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
        with self._counter_lock:
            written_events = self._written_events
            dropped_events = self._dropped_events
        response = BrowserUsageWriterShutdownResponse(
            schema_version="1.0",
            drained=drained,
            written_events=written_events,
            pending_events=pending_events,
            dropped_events=dropped_events,
        )
        logger.info(
            log_event(
                self._ctx,
                role="service",
                event="browser_usage_accounting_shutdown_complete",
                module=logger.name,
                fields={
                    "normalized_url": self._normalized_url,
                    "drained": response.drained,
                    "written_events": response.written_events,
                    "pending_events": response.pending_events,
                    "dropped_events": response.dropped_events,
                },
            )
        )
        return response

    def _run(self) -> None:
        while True:
            try:
                item = self._queue.get(timeout=0.05)
            except queue.Empty:
                if self._stop_requested.is_set():
                    return
                continue
            try:
                if item is None:
                    return
                response = openai_accounting_service.record_usage(item, self._ctx)
                if response.error:
                    logger.warning(
                        log_event(
                            self._ctx,
                            role="service",
                            event="browser_usage_accounting_write_failed",
                            module=logger.name,
                            fields={
                                "normalized_url": self._normalized_url,
                                "error": response.error,
                                "event_key": response.event_key,
                            },
                        )
                    )
                else:
                    with self._counter_lock:
                        self._written_events += 1
            finally:
                self._queue.task_done()

    def _record_drop(self, reason: str) -> None:
        with self._counter_lock:
            self._dropped_events += 1
            dropped_events = self._dropped_events
        logger.warning(
            log_event(
                self._ctx,
                role="service",
                event="browser_usage_accounting_event_dropped",
                module=logger.name,
                fields={
                    "normalized_url": self._normalized_url,
                    "reason": reason,
                    "queue_size": self._queue.maxsize,
                    "queued_events": self._queue.qsize(),
                    "dropped_events": dropped_events,
                },
            )
        )
