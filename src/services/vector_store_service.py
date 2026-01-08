from __future__ import annotations

import logging
import os
import time
from typing import Dict, Optional

from openai import OpenAI

from src.contracts.run_context import RunContext
from src.contracts.vector_store import (
    VectorStoreAttachFileRequest,
    VectorStoreAttachFileResponse,
    VectorStoreCreateRequest,
    VectorStoreCreateResponse,
    VectorStoreStatusResponse,
    VectorStoreUploadFileRequest,
    VectorStoreUploadFileResponse,
)
from src.utils.errors import AppError
from src.utils.logging import log_event, new_run_context

logger = logging.getLogger("market_lense.vector_store_service")


def _ctx_or_new(ctx: Optional[RunContext]) -> RunContext:
    return ctx or new_run_context(task_id="vector_store")


def _client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise AppError(
            code="vector_store_missing_api_key",
            message="OPENAI_API_KEY is required for vector store operations",
            retryable=False,
        )
    return OpenAI(api_key=api_key)


def create_vector_store(report_id: str, metadata: Dict[str, str], ctx: Optional[RunContext] = None) -> VectorStoreCreateResponse:
    ctx = _ctx_or_new(ctx)
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_create_start",
        module=logger.name,
        fields={"report_id": report_id},
    ))
    try:
        resp = _client().vector_stores.create(name=report_id, metadata=metadata or {})
        vector_store_id = getattr(resp, "id", None) or resp.get("id")  # type: ignore[union-attr]
        if not vector_store_id:
            raise AppError(
                code="vector_store_create_failed",
                message="Vector store create did not return an id",
                retryable=True,
            )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="vector_store_create_failed",
            message="Vector store create request failed",
            cause=exc,
            retryable=True,
        ) from exc
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_create_complete",
        module=logger.name,
        fields={"report_id": report_id, "vector_store_id": vector_store_id},
    ))
    return VectorStoreCreateResponse(schema_version="1.0", vector_store_id=vector_store_id)


def upload_file(pdf_path: str, ctx: Optional[RunContext] = None) -> VectorStoreUploadFileResponse:
    ctx = _ctx_or_new(ctx)
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_upload_start",
        module=logger.name,
        fields={"pdf_path": pdf_path},
    ))
    try:
        with open(pdf_path, "rb") as f:
            resp = _client().files.create(file=f, purpose="assistants")
        file_id = getattr(resp, "id", None) or resp.get("id")  # type: ignore[union-attr]
        if not file_id:
            raise AppError(
                code="vector_store_upload_failed",
                message="Vector store file upload did not return an id",
                retryable=True,
            )
    except FileNotFoundError as exc:
        raise AppError(
            code="vector_store_upload_missing_file",
            message=f"File not found: {pdf_path}",
            cause=exc,
            retryable=False,
        ) from exc
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="vector_store_upload_failed",
            message="Vector store file upload failed",
            cause=exc,
            retryable=True,
        ) from exc
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_upload_complete",
        module=logger.name,
        fields={"pdf_path": pdf_path, "openai_file_id": file_id},
    ))
    return VectorStoreUploadFileResponse(schema_version="1.0", vector_store_id="", openai_file_id=file_id)


def attach_file(vector_store_id: str, file_id: str, ctx: Optional[RunContext] = None) -> VectorStoreAttachFileResponse:
    ctx = _ctx_or_new(ctx)
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_attach_start",
        module=logger.name,
        fields={"vector_store_id": vector_store_id, "openai_file_id": file_id},
    ))
    try:
        resp = _client().vector_stores.files.create(vector_store_id=vector_store_id, file_id=file_id)
        attached_id = getattr(resp, "id", None) or resp.get("id")  # type: ignore[union-attr]
        if not attached_id:
            raise AppError(
                code="vector_store_attach_failed",
                message="Vector store attach did not return an id",
                retryable=True,
            )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="vector_store_attach_failed",
            message="Vector store attach request failed",
            cause=exc,
            retryable=True,
        ) from exc
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_attach_complete",
        module=logger.name,
        fields={"vector_store_id": vector_store_id, "openai_file_id": file_id},
    ))
    return VectorStoreAttachFileResponse(schema_version="1.0", vector_store_id=vector_store_id, openai_file_id=file_id)


def get_vector_store_status(vector_store_id: str, ctx: Optional[RunContext] = None) -> VectorStoreStatusResponse:
    ctx = _ctx_or_new(ctx)
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_status_start",
        module=logger.name,
        fields={"vector_store_id": vector_store_id},
    ))
    try:
        resp = _client().vector_stores.retrieve(vector_store_id)
        status = getattr(resp, "status", None)
        if status is None and isinstance(resp, dict):
            status = resp.get("status")
        indexed_at = getattr(resp, "created_at", None)
        if indexed_at is None and isinstance(resp, dict):
            indexed_at = resp.get("created_at")
        last_error = getattr(resp, "last_error", None)
        if last_error is None and isinstance(resp, dict):
            last_error = resp.get("last_error")
    except Exception as exc:
        raise AppError(
            code="vector_store_status_failed",
            message="Vector store status request failed",
            cause=exc,
            retryable=True,
        ) from exc
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_status_complete",
        module=logger.name,
        fields={"vector_store_id": vector_store_id, "status": status},
    ))
    return VectorStoreStatusResponse(
        schema_version="1.0",
        vector_store_id=vector_store_id,
        status=status or "",
        indexed_at_utc=str(indexed_at) if indexed_at is not None else None,
        last_error=str(last_error) if last_error else None,
    )


def wait_until_indexed(vector_store_id: str, timeout_s: int = 300, poll_interval_s: int = 5, ctx: Optional[RunContext] = None) -> VectorStoreStatusResponse:
    ctx = _ctx_or_new(ctx)
    deadline = time.time() + timeout_s
    last_resp: Optional[VectorStoreStatusResponse] = None
    while time.time() < deadline:
        last_resp = get_vector_store_status(vector_store_id, ctx)
        if last_resp.status in {"completed", "ready", "indexed"}:
            return last_resp
        if last_resp.status in {"failed", "errored"}:
            raise AppError(
                code="vector_store_index_failed",
                message=f"Vector store indexing failed: {last_resp.last_error or last_resp.status}",
                retryable=False,
            )
        time.sleep(poll_interval_s)
    raise AppError(
        code="vector_store_index_timeout",
        message="Timed out waiting for vector store indexing",
        retryable=True,
        context={"vector_store_id": vector_store_id, "last_status": last_resp.status if last_resp else None},
    )
