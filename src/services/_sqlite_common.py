"""Shared SQLite mechanics; canonical services retain schema ownership."""

from __future__ import annotations

import sqlite3

LOCK_ERROR_MARKERS = ("database is locked", "database is busy")


def configure_sqlite_connection(
    conn: sqlite3.Connection,
    *,
    busy_timeout_seconds: float,
) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={max(0, int(busy_timeout_seconds * 1000))}")
    conn.execute("PRAGMA synchronous=NORMAL")


def is_sqlite_lock_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in LOCK_ERROR_MARKERS)


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None
