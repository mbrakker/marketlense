from __future__ import annotations

import json
import logging
from typing import Callable, Dict, NoReturn, Optional, TypeVar

from src.contracts.openai import (
    OpenAIVectorStoreAttachFileRequest,
    OpenAIVectorStoreCreateRequest,
    OpenAIVectorStoreDeleteRequest,
    OpenAIVectorStoreFileUploadRequest,
    OpenAIVectorStoreStatusRequest,
    OpenAIVectorStoreUpdateMetadataRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.config import OpenAICredentialResolveRequest
from src.contracts.vector_store import (
    VectorStoreAttachFileRequest,
    VectorStoreAttachFileResponse,
    VectorStoreCreateRequest,
    VectorStoreCreateResponse,
    VectorStoreDeleteRequest,
    VectorStoreDeleteResponse,
    VectorStoreMetadata,
    VectorStorePruneRequest,
    VectorStorePruneResponse,
    VectorStoreStatusResponse,
    VectorStoreStatusRequest,
    VectorStoreUpdateMetadataRequest,
    VectorStoreUpdateMetadataResponse,
    VectorStoreUploadFileRequest,
    VectorStoreUploadFileResponse,
)
from src.services import config_service, llm_service
from src.utils.coercion import clean_string_list
from src.utils.errors import AppError
from src.utils.logging import log_event, new_run_context

logger = logging.getLogger("market_lense.vector_store_service")
_T = TypeVar("_T")


def _ctx_or_new(ctx: Optional[RunContext]) -> RunContext:
    return ctx or new_run_context(task_id="vector_store")


def _resolve_api_key(ctx: RunContext) -> str:
    return config_service.resolve_openai_credential(
        OpenAICredentialResolveRequest(schema_version="1.0"),
        ctx,
    ).api_key


def _raise_vector_store_error(exc: AppError, *, code: str, message: str) -> NoReturn:
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


def _is_missing_remote_error(exc: AppError) -> bool:
    if "not_found" in str(exc.code or "").lower():
        return True
    cause = exc.cause
    status_code = getattr(cause, "status_code", None)
    if status_code == 404:
        return True
    text = f"{exc.message} {cause}".lower()
    return "not found" in text or "no such vector store" in text


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


def create_vector_store(
    request: VectorStoreCreateRequest, ctx: Optional[RunContext] = None
) -> VectorStoreCreateResponse:
    ctx = _ctx_or_new(ctx)
    name = _require_non_empty(request.name, "name")
    metadata_payload = _serialize_metadata(request.metadata)
    api_key = _resolve_api_key(ctx)
    logger.info(
        log_event(
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
        )
    )
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
    logger.info(
        log_event(
            ctx,
            role="service",
            event="vector_store_create_complete",
            module=logger.name,
            fields={"name": name, "vector_store_id": vector_store_id},
        )
    )
    return VectorStoreCreateResponse(
        schema_version="1.0", vector_store_id=vector_store_id
    )


def upload_file(
    request: VectorStoreUploadFileRequest, ctx: Optional[RunContext] = None
) -> VectorStoreUploadFileResponse:
    ctx = _ctx_or_new(ctx)
    vector_store_id = _require_non_empty(request.vector_store_id, "vector_store_id")
    file_path = _require_non_empty(request.file_path, "file_path")
    api_key = _resolve_api_key(ctx)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="vector_store_upload_start",
            module=logger.name,
            fields={"pdf_path": file_path, "vector_store_id": vector_store_id},
        )
    )
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
    logger.info(
        log_event(
            ctx,
            role="service",
            event="vector_store_upload_complete",
            module=logger.name,
            fields={
                "pdf_path": file_path,
                "openai_file_id": file_id,
                "vector_store_id": vector_store_id,
            },
        )
    )
    return VectorStoreUploadFileResponse(
        schema_version="1.0", vector_store_id=vector_store_id, openai_file_id=file_id
    )


def attach_file(
    request: VectorStoreAttachFileRequest, ctx: Optional[RunContext] = None
) -> VectorStoreAttachFileResponse:
    ctx = _ctx_or_new(ctx)
    vector_store_id = _require_non_empty(request.vector_store_id, "vector_store_id")
    file_id = _require_non_empty(request.openai_file_id, "openai_file_id")
    api_key = _resolve_api_key(ctx)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="vector_store_attach_start",
            module=logger.name,
            fields={"vector_store_id": vector_store_id, "openai_file_id": file_id},
        )
    )
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
    logger.info(
        log_event(
            ctx,
            role="service",
            event="vector_store_attach_complete",
            module=logger.name,
            fields={"vector_store_id": vector_store_id, "openai_file_id": file_id},
        )
    )
    return VectorStoreAttachFileResponse(
        schema_version="1.0", vector_store_id=vector_store_id, openai_file_id=file_id
    )


def get_vector_store_status(
    request: VectorStoreStatusRequest, ctx: Optional[RunContext] = None
) -> VectorStoreStatusResponse:
    ctx = _ctx_or_new(ctx)
    vector_store_id = _require_non_empty(request.vector_store_id, "vector_store_id")
    api_key = _resolve_api_key(ctx)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="vector_store_status_start",
            module=logger.name,
            fields={"vector_store_id": vector_store_id},
        )
    )
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
    logger.info(
        log_event(
            ctx,
            role="service",
            event="vector_store_status_complete",
            module=logger.name,
            fields={"vector_store_id": vector_store_id, "status": status},
        )
    )
    return VectorStoreStatusResponse(
        schema_version="1.0",
        vector_store_id=vector_store_id,
        status=status or "",
        indexed_at_utc=str(indexed_at) if indexed_at is not None else None,
        last_error=str(last_error) if last_error else None,
    )


def delete_vector_store(
    request: VectorStoreDeleteRequest, ctx: Optional[RunContext] = None
) -> VectorStoreDeleteResponse:
    ctx = _ctx_or_new(ctx)
    vector_store_id = _require_non_empty(request.vector_store_id, "vector_store_id")
    api_key = _resolve_api_key(ctx)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="vector_store_delete_start",
            module=logger.name,
            fields={
                "vector_store_id": vector_store_id,
                "missing_ok": bool(request.missing_ok),
            },
        )
    )
    try:
        resp = llm_service.openai_vector_store_delete(
            OpenAIVectorStoreDeleteRequest(
                schema_version="1.0",
                api_key=api_key,
                vector_store_id=vector_store_id,
            ),
            ctx,
        )
    except AppError as exc:
        if request.missing_ok and _is_missing_remote_error(exc):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="vector_store_delete_missing_remote",
                    module=logger.name,
                    fields={"vector_store_id": vector_store_id},
                )
            )
            return VectorStoreDeleteResponse(
                schema_version="1.0",
                vector_store_id=vector_store_id,
                deleted=False,
                missing_remote=True,
            )
        _raise_vector_store_error(
            exc,
            code="vector_store_delete_failed",
            message="Vector store delete request failed",
        )
    response = VectorStoreDeleteResponse(
        schema_version="1.0",
        vector_store_id=vector_store_id,
        deleted=bool(resp.deleted),
        missing_remote=False,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="vector_store_delete_complete",
            module=logger.name,
            fields={
                "vector_store_id": response.vector_store_id,
                "deleted": response.deleted,
                "missing_remote": response.missing_remote,
            },
        )
    )
    return response


def prune_vector_stores(
    request: VectorStorePruneRequest, ctx: Optional[RunContext] = None
) -> VectorStorePruneResponse:
    ctx = _ctx_or_new(ctx)
    requested_count = len(request.items or [])
    logger.info(
        log_event(
            ctx,
            role="service",
            event="vector_store_prune_start",
            module=logger.name,
            fields={"requested_count": requested_count},
        )
    )
    seen: set[str] = set()
    deleted: list[str] = []
    missing: list[str] = []
    duplicates: list[str] = []
    for item in request.items or []:
        vector_store_id = _require_non_empty(item.vector_store_id, "vector_store_id")
        if vector_store_id in seen:
            duplicates.append(vector_store_id)
            continue
        seen.add(vector_store_id)
        result = delete_vector_store(
            VectorStoreDeleteRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
                missing_ok=request.missing_ok,
            ),
            ctx,
        )
        if result.missing_remote:
            missing.append(vector_store_id)
        elif result.deleted:
            deleted.append(vector_store_id)
    response = VectorStorePruneResponse(
        schema_version="1.0",
        requested_count=requested_count,
        deleted_vector_store_ids=deleted,
        missing_vector_store_ids=missing,
        skipped_duplicate_vector_store_ids=duplicates,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="vector_store_prune_complete",
            module=logger.name,
            fields={
                "requested_count": requested_count,
                "deleted_count": len(deleted),
                "missing_count": len(missing),
                "duplicate_count": len(duplicates),
            },
        )
    )
    return response


def update_metadata(
    request: VectorStoreUpdateMetadataRequest, ctx: Optional[RunContext] = None
) -> VectorStoreUpdateMetadataResponse:
    ctx = _ctx_or_new(ctx)
    vector_store_id = _require_non_empty(request.vector_store_id, "vector_store_id")
    metadata_payload = _serialize_metadata(request.metadata)
    api_key = _resolve_api_key(ctx)
    logger.info(
        log_event(
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
        )
    )
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
    logger.info(
        log_event(
            ctx,
            role="service",
            event="vector_store_metadata_update_complete",
            module=logger.name,
            fields={"vector_store_id": updated_id},
        )
    )
    return VectorStoreUpdateMetadataResponse(
        schema_version="1.0", vector_store_id=updated_id
    )
