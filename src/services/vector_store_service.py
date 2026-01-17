from __future__ import annotations

import json
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
    VectorStoreMetadata,
    VectorStoreStatusResponse,
    VectorStoreStatusRequest,
    VectorStoreUpdateMetadataRequest,
    VectorStoreUpdateMetadataResponse,
    VectorStoreUploadFileRequest,
    VectorStoreUploadFileResponse,
    VectorStoreWaitRequest,
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


def _require_non_empty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AppError(
            code="vector_store_invalid_request",
            message=f"{name} is required",
            retryable=False,
        )
    return value.strip()


def _clean_list(values: list[str]) -> list[str]:
    cleaned = []
    seen = set()
    for item in values or []:
        item_s = str(item or "").strip()
        if not item_s:
            continue
        key = item_s.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item_s)
    return cleaned


def _serialize_metadata(metadata: VectorStoreMetadata) -> Dict[str, str]:
    report_id = _require_non_empty(metadata.report_id, "metadata.report_id")
    report_name = _require_non_empty(metadata.report_name, "metadata.report_name")
    taxonomy = _clean_list(metadata.taxonomy)
    categories = _clean_list(metadata.categories)
    payload = {
        "schema_version": str(metadata.schema_version or "1.0").strip() or "1.0",
        "report_id": report_id,
        "report_name": report_name,
        "taxonomy_json": json.dumps(taxonomy, ensure_ascii=True),
        "categories_json": json.dumps(categories, ensure_ascii=True),
        "region": str(metadata.region or "").strip(),
        "time_period": str(metadata.time_period or "").strip(),
    }
    return {key: value for key, value in payload.items() if value != ""}


def create_vector_store(request: VectorStoreCreateRequest, ctx: Optional[RunContext] = None) -> VectorStoreCreateResponse:
    ctx = _ctx_or_new(ctx)
    name = _require_non_empty(request.name, "name")
    metadata_payload = _serialize_metadata(request.metadata)
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_create_start",
        module=logger.name,
        fields={
            "name": name,
            "metadata_keys": list(metadata_payload.keys()),
            "taxonomy_count": len(request.metadata.taxonomy or []),
            "categories_count": len(request.metadata.categories or []),
        },
    ))
    try:
        resp = _client().vector_stores.create(name=name, metadata=metadata_payload)
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
        fields={"name": name, "vector_store_id": vector_store_id},
    ))
    return VectorStoreCreateResponse(schema_version="1.0", vector_store_id=vector_store_id)


def upload_file(request: VectorStoreUploadFileRequest, ctx: Optional[RunContext] = None) -> VectorStoreUploadFileResponse:
    ctx = _ctx_or_new(ctx)
    vector_store_id = _require_non_empty(request.vector_store_id, "vector_store_id")
    file_path = _require_non_empty(request.file_path, "file_path")
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_upload_start",
        module=logger.name,
        fields={"pdf_path": file_path, "vector_store_id": vector_store_id},
    ))
    try:
        with open(file_path, "rb") as f:
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
            message=f"File not found: {file_path}",
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
        fields={"pdf_path": file_path, "openai_file_id": file_id, "vector_store_id": vector_store_id},
    ))
    return VectorStoreUploadFileResponse(schema_version="1.0", vector_store_id=vector_store_id, openai_file_id=file_id)


def attach_file(request: VectorStoreAttachFileRequest, ctx: Optional[RunContext] = None) -> VectorStoreAttachFileResponse:
    ctx = _ctx_or_new(ctx)
    vector_store_id = _require_non_empty(request.vector_store_id, "vector_store_id")
    file_id = _require_non_empty(request.openai_file_id, "openai_file_id")
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


def get_vector_store_status(request: VectorStoreStatusRequest, ctx: Optional[RunContext] = None) -> VectorStoreStatusResponse:
    ctx = _ctx_or_new(ctx)
    vector_store_id = _require_non_empty(request.vector_store_id, "vector_store_id")
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


def wait_until_indexed(request: VectorStoreWaitRequest, ctx: Optional[RunContext] = None) -> VectorStoreStatusResponse:
    ctx = _ctx_or_new(ctx)
    vector_store_id = _require_non_empty(request.vector_store_id, "vector_store_id")
    timeout_s = int(request.timeout_s)
    poll_interval_s = int(request.poll_interval_s)
    if timeout_s <= 0:
        raise AppError(
            code="vector_store_invalid_request",
            message="timeout_s must be positive",
            retryable=False,
        )
    if poll_interval_s <= 0:
        raise AppError(
            code="vector_store_invalid_request",
            message="poll_interval_s must be positive",
            retryable=False,
        )
    deadline = time.time() + timeout_s
    last_resp: Optional[VectorStoreStatusResponse] = None
    while time.time() < deadline:
        last_resp = get_vector_store_status(
            VectorStoreStatusRequest(schema_version="1.0", vector_store_id=vector_store_id),
            ctx,
        )
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


def update_metadata(request: VectorStoreUpdateMetadataRequest, ctx: Optional[RunContext] = None) -> VectorStoreUpdateMetadataResponse:
    ctx = _ctx_or_new(ctx)
    vector_store_id = _require_non_empty(request.vector_store_id, "vector_store_id")
    metadata_payload = _serialize_metadata(request.metadata)
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_metadata_update_start",
        module=logger.name,
        fields={
            "vector_store_id": vector_store_id,
            "metadata_keys": list(metadata_payload.keys()),
            "taxonomy_count": len(request.metadata.taxonomy or []),
            "categories_count": len(request.metadata.categories or []),
        },
    ))
    try:
        resp = _client().vector_stores.update(vector_store_id=vector_store_id, metadata=metadata_payload)
        updated_id = getattr(resp, "id", None) or resp.get("id")  # type: ignore[union-attr]
        if not updated_id:
            raise AppError(
                code="vector_store_metadata_update_failed",
                message="Vector store metadata update did not return an id",
                retryable=True,
            )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="vector_store_metadata_update_failed",
            message="Vector store metadata update request failed",
            cause=exc,
            retryable=True,
        ) from exc
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_metadata_update_complete",
        module=logger.name,
        fields={"vector_store_id": updated_id},
    ))
    return VectorStoreUpdateMetadataResponse(schema_version="1.0", vector_store_id=updated_id)
