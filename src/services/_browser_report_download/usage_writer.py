from __future__ import annotations

import logging
import queue
import time
from threading import Event, Thread

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
        self._thread = Thread(
            target=self._run,
            name="browser-usage-writer",
            daemon=True,
        )
        self._thread.start()

    def enqueue(self, request: OpenAIUsageAccountingRequest) -> bool:
        if self._closed.is_set():
            return False
        try:
            self._queue.put_nowait(request)
            return True
        except queue.Full:
            logger.warning(
                log_event(
                    self._ctx,
                    role="service",
                    event="browser_usage_accounting_queue_overflow",
                    module=logger.name,
                    fields={
                        "normalized_url": self._normalized_url,
                        "queue_size": self._queue.maxsize,
                        "queued_events": self._queue.qsize(),
                    },
                )
            )
            return False

    def flush(self, *, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        drained = not self._queue.unfinished_tasks
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
        self._closed.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            return drained
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
        return drained

    def _run(self) -> None:
        while True:
            item = self._queue.get()
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
            finally:
                self._queue.task_done()
