from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from src.contracts.files import (
    ListHtmlRequest,
    ListHtmlResponse,
    ReadBytesRequest,
    ReadBytesResponse,
    ReadTextRequest,
    ReadTextResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.file_service")


def read_text(request: ReadTextRequest, ctx: RunContext) -> ReadTextResponse:
    log_event(
        logger,
        ctx,
        role="service",
        event="read_text_start",
        fields={"path": request.path},
    )
    try:
        content = Path(request.path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AppError(
            code="file_not_found",
            message=f"File not found: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    except Exception as exc:
        raise AppError(
            code="file_read_failed",
            message=f"Failed to read text file: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc

    log_event(
        logger,
        ctx,
        role="service",
        event="read_text_complete",
        fields={"path": request.path, "length": len(content)},
    )
    return ReadTextResponse(schema_version="1.0", path=request.path, content=content)


def read_bytes(request: ReadBytesRequest, ctx: RunContext) -> ReadBytesResponse:
    log_event(
        logger,
        ctx,
        role="service",
        event="read_bytes_start",
        fields={"path": request.path},
    )
    try:
        content = Path(request.path).read_bytes()
    except FileNotFoundError as exc:
        raise AppError(
            code="file_not_found",
            message=f"File not found: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    except Exception as exc:
        raise AppError(
            code="file_read_failed",
            message=f"Failed to read binary file: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc

    log_event(
        logger,
        ctx,
        role="service",
        event="read_bytes_complete",
        fields={"path": request.path, "length": len(content)},
    )
    return ReadBytesResponse(schema_version="1.0", path=request.path, content=content)


def list_html(request: ListHtmlRequest, ctx: RunContext) -> ListHtmlResponse:
    log_event(
        logger,
        ctx,
        role="service",
        event="list_html_start",
        fields={"root_dir": request.root_dir},
    )
    root = Path(request.root_dir)
    if not root.exists():
        raise AppError(
            code="output_dir_missing",
            message=f"Output dir does not exist: {request.root_dir}",
            retryable=False,
        )
    html_paths: List[str] = [str(p) for p in sorted(root.glob("*.html"))]
    log_event(
        logger,
        ctx,
        role="service",
        event="list_html_complete",
        fields={"count": len(html_paths)},
    )
    return ListHtmlResponse(
        schema_version="1.0",
        root_dir=request.root_dir,
        html_paths=html_paths,
    )
