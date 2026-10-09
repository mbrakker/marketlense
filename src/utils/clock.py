from __future__ import annotations

from datetime import datetime, timezone


def _utc_value(value: datetime | None) -> datetime:
    return value if value is not None else datetime.now(timezone.utc)


def utc_now_iso(value: datetime | None = None) -> str:
    return _utc_value(value).isoformat()


def utc_now_seconds_iso(value: datetime | None = None) -> str:
    return _utc_value(value).replace(microsecond=0).isoformat()


def utc_now_seconds_z(value: datetime | None = None) -> str:
    return utc_now_seconds_iso(value).replace("+00:00", "Z")


def is_utc_timestamp_z(value: str) -> bool:
    token = str(value or "").strip()
    if not token.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(token[:-1] + "+00:00")
    except ValueError:
        return False
    return True
