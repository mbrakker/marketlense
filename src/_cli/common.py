from __future__ import annotations

import os


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _default_log_path() -> str:
    from datetime import datetime

    return os.path.join("logs", f"market_lense_{datetime.now().date().isoformat()}.log")
