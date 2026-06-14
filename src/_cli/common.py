from __future__ import annotations

import os

from src.utils.clock import utc_now_iso as _utc_now


def _default_log_path() -> str:
    from datetime import datetime

    return os.path.join("logs", f"market_lense_{datetime.now().date().isoformat()}.log")
