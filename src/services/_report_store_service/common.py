from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from typing import Optional

from src.utils.coercion import clean_string_list
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.report_store_service")

ACCESS_TIMEOUT_SECONDS = 0.0
LOCK_ERROR_MARKERS = ("database is locked", "database is busy")
DEFAULT_BUSY_TIMEOUT_SECONDS = 5.0
_REPORT_CONN_LOCK = threading.Lock()


def _optional_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_metadata(metadata: dict[str, str]) -> dict[str, str]:
    if not metadata:
        return {}
    cleaned: dict[str, str] = {}
    for key, value in metadata.items():
        key_str = str(key).strip()
        if not key_str:
            continue
        val_str = str(value).strip() if value is not None else ""
        if not val_str:
            continue
        cleaned[key_str] = val_str
    return cleaned


def _is_lock_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in LOCK_ERROR_MARKERS)


def _normalize_publisher_key(name: str) -> str:
    token = str(name).strip().lower()
    if not token:
        return ""
    token = token.replace("&", " and ")
    token = re.sub(r"[^a-z0-9]+", "", token)
    return token


def _normalize_optional_url_key(url: str) -> str:
    token = str(url).strip()
    if not token:
        return ""
    return normalize_url(token)


def _configure_sqlite_connection(
    conn: sqlite3.Connection,
    *,
    busy_timeout_seconds: float,
) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={max(0, int(busy_timeout_seconds * 1000))}")
    conn.execute("PRAGMA synchronous=NORMAL")
