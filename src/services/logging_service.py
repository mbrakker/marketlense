from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

from rich.logging import RichHandler

from src.contracts.logging import LoggingSetupRequest, LoggingSetupResponse
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

DEFAULT_LOG_DIR = "logs"
LOG_DIR_ENV = "MARKET_LENSE_LOG_DIR"
LOG_FILE_PREFIX = "market_lense"
SERVICE_LOGGER_NAME = "market_lense.logging_service"


def _force_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if not stream:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            continue


def setup_logging(request: LoggingSetupRequest, ctx: RunContext) -> LoggingSetupResponse:
    logger = logging.getLogger(SERVICE_LOGGER_NAME)
    logger.info(log_event(
        ctx,
        role="service",
        event="logging_setup_start",
        module=SERVICE_LOGGER_NAME,
        fields={"level": request.level},
    ))

    _force_utf8_stdio()
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    use_rich = os.getenv("RICH_DISABLE", "").lower() not in ("1", "true", "yes")
    if use_rich and hasattr(sys.stdout, "isatty") and not sys.stdout.isatty():
        use_rich = False

    log_dir = os.getenv(LOG_DIR_ENV, DEFAULT_LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)
    log_date = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(log_dir, f"{LOG_FILE_PREFIX}_{log_date}.log")

    handlers = []
    if use_rich:
        handlers = [RichHandler(show_time=False, rich_tracebacks=True)]
    else:
        handlers = [logging.StreamHandler()]

    handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=request.level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
    logger = logging.getLogger(SERVICE_LOGGER_NAME)
    logger.info(log_event(
        ctx,
        role="service",
        event="logging_setup_complete",
        module=SERVICE_LOGGER_NAME,
        fields={
            "level": request.level,
            "log_dir": log_dir,
            "log_path": log_path,
            "use_rich": use_rich,
        },
    ))
    return LoggingSetupResponse(
        schema_version="1.0",
        level=request.level,
        log_dir=log_dir,
        log_path=log_path,
        use_rich=use_rich,
    )
