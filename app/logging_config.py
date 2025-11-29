import logging
from rich.logging import RichHandler


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging to use RichHandler for pretty console logs.

    Calling this multiple times is safe (idempotent) — it reconfigures the root handlers.
    """
    # Remove existing handlers to avoid duplicate logs when reloading
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[RichHandler(show_time=False, rich_tracebacks=True)],
    )


__all__ = ["setup_logging"]
