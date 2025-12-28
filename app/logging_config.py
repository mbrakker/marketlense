import logging
import os
import sys
from rich.logging import RichHandler


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging to use RichHandler for pretty console logs.

    Calling this multiple times is safe (idempotent) - it reconfigures the root handlers.
    """
    # Remove existing handlers to avoid duplicate logs when reloading
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    use_rich = os.getenv("RICH_DISABLE", "").lower() not in ("1", "true", "yes")
    if use_rich and hasattr(sys.stdout, "isatty") and not sys.stdout.isatty():
        use_rich = False

    handlers = []
    if use_rich:
        handlers = [RichHandler(show_time=False, rich_tracebacks=True)]
    else:
        handlers = [logging.StreamHandler()]

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


__all__ = ["setup_logging"]
