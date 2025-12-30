from __future__ import annotations

import logging
import sqlite3
from typing import Optional, Tuple
from src.contracts.run_context import RunContext
from src.contracts.state import (
    StateCheckRequest,
    StateGetRequest,
    StateGetResponse,
    StatePublishCheckRequest,
    StatePublishGetResponse,
    StatePublishRecordRequest,
    StateRecordRequest,
)
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.state_service")

DDL = """
CREATE TABLE IF NOT EXISTS processed (
  file_id TEXT PRIMARY KEY,
  md5 TEXT NOT NULL,
  processed_at INTEGER NOT NULL,
  openai_file_id TEXT
);

CREATE TABLE IF NOT EXISTS published (
  file_id TEXT PRIMARY KEY,
  md5 TEXT NOT NULL,
  published_at INTEGER NOT NULL,
  wp_post_id INTEGER NOT NULL,
  wp_post_url TEXT NOT NULL
);
"""


class StateStore:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(DDL)
        self.conn.commit()

    def already_processed(self, file_id: str, md5: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM processed WHERE file_id=? AND md5=?", (file_id, md5)
        )
        return cur.fetchone() is not None

    def record(self, file_id: str, md5: str, openai_file_id: Optional[str]):
        self.conn.execute(
            "INSERT OR REPLACE INTO processed(file_id, md5, processed_at, openai_file_id) "
            "VALUES(?, ?, strftime('%s','now'), ?)",
            (file_id, md5, openai_file_id),
        )
        self.conn.commit()

    def get(self, file_id: str) -> Optional[Tuple[str, str, int, Optional[str]]]:
        cur = self.conn.execute(
            "SELECT file_id, md5, processed_at, openai_file_id FROM processed WHERE file_id=?", (file_id,)
        )
        return cur.fetchone()

    def already_published(self, file_id: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM published WHERE file_id=?", (file_id,)
        )
        return cur.fetchone() is not None

    def record_publish(self, file_id: str, md5: str, wp_post_id: int, wp_post_url: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO published(file_id, md5, published_at, wp_post_id, wp_post_url) "
            "VALUES(?, ?, strftime('%s','now'), ?, ?)",
            (file_id, md5, wp_post_id, wp_post_url),
        )
        self.conn.commit()

    def get_publish(self, file_id: str) -> Optional[Tuple[str, str, int, int, str]]:
        cur = self.conn.execute(
            "SELECT file_id, md5, published_at, wp_post_id, wp_post_url FROM published WHERE file_id=?",
            (file_id,),
        )
        return cur.fetchone()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def already_processed(state: StateStore, request: StateCheckRequest, ctx: RunContext) -> bool:
    log_event(
        logger,
        ctx,
        role="service",
        event="state_check_start",
        fields={"file_id": request.file_id},
    )
    result = state.already_processed(request.file_id, request.md5)
    log_event(
        logger,
        ctx,
        role="service",
        event="state_check_complete",
        fields={"file_id": request.file_id, "already_processed": result},
    )
    return result


def record(state: StateStore, request: StateRecordRequest, ctx: RunContext) -> None:
    log_event(
        logger,
        ctx,
        role="service",
        event="state_record_start",
        fields={"file_id": request.file_id},
    )
    state.record(request.file_id, request.md5, request.openai_file_id)
    log_event(
        logger,
        ctx,
        role="service",
        event="state_record_complete",
        fields={"file_id": request.file_id},
    )


def get(state: StateStore, request: StateGetRequest, ctx: RunContext) -> Optional[StateGetResponse]:
    log_event(
        logger,
        ctx,
        role="service",
        event="state_get_start",
        fields={"file_id": request.file_id},
    )
    row = state.get(request.file_id)
    if not row:
        log_event(
            logger,
            ctx,
            role="service",
            event="state_get_complete",
            fields={"file_id": request.file_id, "found": False},
        )
        return None
    file_id, md5, processed_at, openai_file_id = row
    log_event(
        logger,
        ctx,
        role="service",
        event="state_get_complete",
        fields={"file_id": request.file_id, "found": True},
    )
    return StateGetResponse(
        schema_version="1.0",
        file_id=file_id,
        md5=md5,
        processed_at=processed_at,
        openai_file_id=openai_file_id,
    )


def already_published(state: StateStore, request: StatePublishCheckRequest, ctx: RunContext) -> bool:
    log_event(
        logger,
        ctx,
        role="service",
        event="state_publish_check_start",
        fields={"file_id": request.file_id},
    )
    result = state.already_published(request.file_id)
    log_event(
        logger,
        ctx,
        role="service",
        event="state_publish_check_complete",
        fields={"file_id": request.file_id, "already_published": result},
    )
    return result


def record_publish(state: StateStore, request: StatePublishRecordRequest, ctx: RunContext) -> None:
    log_event(
        logger,
        ctx,
        role="service",
        event="state_publish_record_start",
        fields={"file_id": request.file_id, "wp_post_id": request.wp_post_id},
    )
    state.record_publish(request.file_id, request.md5, request.wp_post_id, request.wp_post_url)
    log_event(
        logger,
        ctx,
        role="service",
        event="state_publish_record_complete",
        fields={"file_id": request.file_id, "wp_post_id": request.wp_post_id},
    )


def get_publish(state: StateStore, request: StatePublishCheckRequest, ctx: RunContext) -> Optional[StatePublishGetResponse]:
    log_event(
        logger,
        ctx,
        role="service",
        event="state_publish_get_start",
        fields={"file_id": request.file_id},
    )
    row = state.get_publish(request.file_id)
    if not row:
        log_event(
            logger,
            ctx,
            role="service",
            event="state_publish_get_complete",
            fields={"file_id": request.file_id, "found": False},
        )
        return None
    file_id, md5, published_at, wp_post_id, wp_post_url = row
    log_event(
        logger,
        ctx,
        role="service",
        event="state_publish_get_complete",
        fields={"file_id": file_id, "found": True},
    )
    return StatePublishGetResponse(
        schema_version="1.0",
        file_id=file_id,
        md5=md5,
        published_at=published_at,
        wp_post_id=wp_post_id,
        wp_post_url=wp_post_url,
    )
