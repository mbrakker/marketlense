"""SQLite-owned counters and generation allocation for usage projections."""

from __future__ import annotations

import sqlite3


def ensure_projection_state_schema(conn: sqlite3.Connection) -> None:
    """Create durable O(1) counters and non-reusable projection generations."""
    conn.execute(
        """
        create table if not exists llm_usage_event_counter (
            singleton integer primary key check (singleton = 1),
            event_count integer not null
        )
        """
    )
    conn.execute(
        """
        insert or ignore into llm_usage_event_counter(singleton, event_count)
        select 1, count(*) from llm_usage_events
        """
    )
    conn.execute(
        """
        create table if not exists llm_usage_semantic_task_counters (
            semantic_task text primary key,
            event_count integer not null
        )
        """
    )
    conn.execute(
        """
        insert or ignore into llm_usage_semantic_task_counters(
            semantic_task, event_count
        )
        select semantic_task, count(*) from llm_usage_events
        group by semantic_task
        """
    )
    conn.execute(
        """
        create table if not exists llm_usage_projection_sequences (
            ledger_path text not null,
            daily_path text not null,
            next_generation_id integer not null,
            primary key (ledger_path, daily_path)
        )
        """
    )


def increment_event_count(conn: sqlite3.Connection) -> int:
    conn.execute(
        "update llm_usage_event_counter "
        "set event_count = event_count + 1 where singleton = 1"
    )
    row = conn.execute(
        "select event_count from llm_usage_event_counter where singleton = 1"
    ).fetchone()
    return int(row[0])


def event_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "select event_count from llm_usage_event_counter where singleton = 1"
    ).fetchone()
    return int(row[0]) if row is not None else 0


def increment_semantic_task_count(conn: sqlite3.Connection, semantic_task: str) -> int:
    conn.execute(
        """
        insert into llm_usage_semantic_task_counters(semantic_task, event_count)
        values (?, 1)
        on conflict(semantic_task) do update set event_count = event_count + 1
        """,
        (semantic_task,),
    )
    row = conn.execute(
        "select event_count from llm_usage_semantic_task_counters "
        "where semantic_task = ?",
        (semantic_task,),
    ).fetchone()
    return int(row[0])


def semantic_task_count(conn: sqlite3.Connection, semantic_task: str) -> int:
    row = conn.execute(
        "select event_count from llm_usage_semantic_task_counters "
        "where semantic_task = ?",
        (semantic_task,),
    ).fetchone()
    return int(row[0]) if row is not None else 0


def allocate_projection_generation(
    conn: sqlite3.Connection, *, ledger_path: str, daily_path: str
) -> int:
    conn.execute(
        """
        insert into llm_usage_projection_sequences(
            ledger_path, daily_path, next_generation_id
        ) values (?, ?, 2)
        on conflict(ledger_path, daily_path) do update set
            next_generation_id = next_generation_id + 1
        """,
        (ledger_path, daily_path),
    )
    row = conn.execute(
        """
        select next_generation_id - 1 from llm_usage_projection_sequences
        where ledger_path = ? and daily_path = ?
        """,
        (ledger_path, daily_path),
    ).fetchone()
    return int(row[0])
