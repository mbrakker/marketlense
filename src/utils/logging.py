from __future__ import annotations

import json
import logging
from typing import Any, Dict
from uuid import uuid4

from src.contracts.run_context import RunContext


def new_run_context(task_id: str | None = None, span_id: str | None = None) -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id=str(uuid4()),
        task_id=task_id or str(uuid4()),
        span_id=span_id or str(uuid4()),
    )


def child_context(parent: RunContext, *, task_id: str | None = None) -> RunContext:
    return RunContext(
        schema_version=parent.schema_version,
        run_id=parent.run_id,
        task_id=task_id or parent.task_id,
        span_id=str(uuid4()),
    )


def log_event(
    logger: logging.Logger,
    ctx: RunContext,
    *,
    role: str,
    event: str,
    module: str | None = None,
    fields: Dict[str, Any] | None = None,
) -> None:
    payload = {
        "run_id": ctx.run_id,
        "task_id": ctx.task_id,
        "span_id": ctx.span_id,
        "module": module or logger.name,
        "role": role,
        "event": event,
        "fields": fields or {},
    }
    try:
        logger.info(json.dumps(payload, ensure_ascii=True))
    except Exception:
        logger.info(
            json.dumps(
                {
                    "run_id": ctx.run_id,
                    "task_id": ctx.task_id,
                    "span_id": ctx.span_id,
                    "module": module or logger.name,
                    "role": role,
                    "event": event,
                    "fields": {"error": "log serialization failed"},
                },
                ensure_ascii=True,
            )
        )
