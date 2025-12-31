from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

from rich.logging import RichHandler

DEFAULT_LOG_DIR = "logs"
LOG_DIR_ENV = "MARKET_LENSE_LOG_DIR"
LOG_FILE_PREFIX = "market_lense"


def setup_logging(level: int = logging.INFO) -> None:
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
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
