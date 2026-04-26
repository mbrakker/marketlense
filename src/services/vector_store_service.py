from __future__ import annotations

import json
import logging
import os
from typing import Callable, Dict, Optional, TypeVar

from src.contracts.openai import (
    OpenAIVectorStoreAttachFileRequest,
    OpenAIVectorStoreCreateRequest,
    OpenAIVectorStoreFileUploadRequest,
    OpenAIVectorStoreStatusRequest,
    OpenAIVectorStoreUpdateMetadataRequest,
)
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
)
from src.services import llm_service
from src.utils.coercion import clean_string_list
from src.utils.errors import AppError
from src.utils.logging import log_event, new_run_context

logger = logging.getLogger("market_lense.vector_store_service")
_T = TypeVar("_T")
openai_service = llm_service


def _ctx_or_new(ctx: Optional[RunContext]) -> RunContext:
    return ctx or new_run_context(task_id="vector_store")


def _api_key_from_env() -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise AppError(
            code="vector_store_missing_api_key",
            message="OPENAI_API_KEY is required for vector store operations",
            retryable=False,
        )
    return api_key


def _raise_vector_store_error(exc: AppError, *, code: str, message: str) -> None:
    raise AppError(
        code=code,
        message=message,
        cause=exc,
        retryable=exc.retryable,
        severity=exc.severity,
        context=exc.context,
    ) from exc


def _call_openai(*, call: Callable[[], _T], code: str, message: str) -> _T:
    try:
        return call()
    except AppError as exc:
        _raise_vector_store_error(exc, code=code, message=message)


def _require_non_empty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AppError(
            code="vector_store_invalid_request",
            message=f"{name} is required",
            retryable=False,
        )
    return value.strip()


def _require_response_id(value: str, *, code: str, message: str) -> str:
    resolved = str(value or "").strip()
    if not resolved:
        raise AppError(code=code, message=message, retryable=True)
    return resolved


def _serialize_metadata(metadata: VectorStoreMetadata) -> Dict[str, str]:
    report_id = _require_non_empty(metadata.report_id, "metadata.report_id")
    report_name = _require_non_empty(metadata.report_name, "metadata.report_name")
    taxonomy = clean_string_list(metadata.taxonomy or [], dedupe_casefold=True)
    categories = clean_string_list(metadata.categories or [], dedupe_casefold=True)
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
    api_key = _api_key_from_env()
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
    resp = _call_openai(
        call=lambda: llm_service.openai_vector_store_create(
            OpenAIVectorStoreCreateRequest(
                schema_version="1.0",
                api_key=api_key,
                name=name,
                metadata=metadata_payload,
            ),
            ctx,
        ),
        code="vector_store_create_failed",
        message="Vector store create request failed",
    )
    vector_store_id = _require_response_id(
        resp.vector_store_id,
        code="vector_store_create_failed",
        message="Vector store create did not return an id",
    )
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
    api_key = _api_key_from_env()
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_upload_start",
        module=logger.name,
        fields={"pdf_path": file_path, "vector_store_id": vector_store_id},
    ))
    try:
        resp = llm_service.openai_vector_store_upload_file(
            OpenAIVectorStoreFileUploadRequest(
                schema_version="1.0",
                api_key=api_key,
                file_path=file_path,
                purpose="assistants",
            ),
            ctx,
        )
    except AppError as exc:
        if exc.code == "openai_file_missing":
            raise AppError(
                code="vector_store_upload_missing_file",
                message=f"File not found: {file_path}",
                cause=exc,
                retryable=False,
                severity=exc.severity,
                context=exc.context,
            ) from exc
        _raise_vector_store_error(
            exc,
            code="vector_store_upload_failed",
            message="Vector store file upload failed",
        )
    file_id = _require_response_id(
        resp.openai_file_id,
        code="vector_store_upload_failed",
        message="Vector store file upload did not return an id",
    )
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
    api_key = _api_key_from_env()
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_attach_start",
        module=logger.name,
        fields={"vector_store_id": vector_store_id, "openai_file_id": file_id},
    ))
    resp = _call_openai(
        call=lambda: llm_service.openai_vector_store_attach_file(
            OpenAIVectorStoreAttachFileRequest(
                schema_version="1.0",
                api_key=api_key,
                vector_store_id=vector_store_id,
                openai_file_id=file_id,
            ),
            ctx,
        ),
        code="vector_store_attach_failed",
        message="Vector store attach request failed",
    )
    _require_response_id(
        resp.openai_file_id,
        code="vector_store_attach_failed",
        message="Vector store attach did not return an id",
    )
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
    api_key = _api_key_from_env()
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_status_start",
        module=logger.name,
        fields={"vector_store_id": vector_store_id},
    ))
    resp = _call_openai(
        call=lambda: llm_service.openai_vector_store_status(
            OpenAIVectorStoreStatusRequest(
                schema_version="1.0",
                api_key=api_key,
                vector_store_id=vector_store_id,
            ),
            ctx,
        ),
        code="vector_store_status_failed",
        message="Vector store status request failed",
    )
    status = resp.status
    indexed_at = resp.indexed_at_utc
    last_error = resp.last_error
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


def update_metadata(request: VectorStoreUpdateMetadataRequest, ctx: Optional[RunContext] = None) -> VectorStoreUpdateMetadataResponse:
    ctx = _ctx_or_new(ctx)
    vector_store_id = _require_non_empty(request.vector_store_id, "vector_store_id")
    metadata_payload = _serialize_metadata(request.metadata)
    api_key = _api_key_from_env()
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
    resp = _call_openai(
        call=lambda: llm_service.openai_vector_store_update_metadata(
            OpenAIVectorStoreUpdateMetadataRequest(
                schema_version="1.0",
                api_key=api_key,
                vector_store_id=vector_store_id,
                metadata=metadata_payload,
            ),
            ctx,
        ),
        code="vector_store_metadata_update_failed",
        message="Vector store metadata update request failed",
    )
    updated_id = _require_response_id(
        resp.vector_store_id,
        code="vector_store_metadata_update_failed",
        message="Vector store metadata update did not return an id",
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="vector_store_metadata_update_complete",
        module=logger.name,
        fields={"vector_store_id": updated_id},
    ))
    return VectorStoreUpdateMetadataResponse(schema_version="1.0", vector_store_id=updated_id)
