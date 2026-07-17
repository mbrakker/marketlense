from __future__ import annotations

# This module deliberately preserves its pre-decomposition compatibility facade.
# ruff: noqa: F403, F405

from typing import Any

from src.services._llm_service.openai_shared import *
from src.services._llm_service.openai_client import *
from src.contracts.run_budget import (
    BudgetDecision,
    BudgetRequest,
    BudgetSideEffectFinalizeRequest,
    RunBudget,
    RunBudgetUsage,
)
from src.contracts.run_context import RunContext
from src.services.llm_usage_ledger_service import (
    evaluate_budget_request,
    finalize_budget_side_effect,
)


def _require_vector_store_budget(
    request: Any, ctx: RunContext, *, operation: str
) -> tuple[RunBudget, BudgetDecision]:
    """Admit every vector-store provider call through the canonical authority."""
    budget = getattr(request, "run_budget", None) or RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name=str(getattr(request, "publisher_name", "") or ""),
        usage_db_path=str(
            getattr(request, "usage_db_path", "./state/llm_usage.sqlite")
        ),
        max_spend_usd=float(getattr(request, "daily_spend_stop_usd", 6.0) or 6.0),
        limit_decision="stop",
    )
    decision = evaluate_budget_request(
        BudgetRequest(
            schema_version="1.0",
            budget=budget,
            run_id=ctx.run_id,
            workflow_id="vector_store",
            publisher_id=str(getattr(request, "publisher_name", "") or ""),
            resource_type="vector_store",
            operation=operation,
            provider="openai",
            model=str(getattr(request, "model", "") or "vector_store"),
            idempotency_key=f"openai:{operation}:{ctx.run_id}:{ctx.task_id}:{ctx.span_id}",
            reserve_in_flight=True,
            forecast_method="historical_median",
        ),
        ctx,
    )
    if decision.decision in {"defer", "pause", "stop"}:
        raise AppError(
            code=f"{operation}_budget_{decision.decision}",
            message="Vector-store provider call was blocked by the canonical budget authority",
            retryable=False,
            context={
                "reason_code": decision.reason_code,
                "affected_limit": decision.affected_limit,
                "retry_decision": "defer" if decision.decision == "defer" else "abort",
                "next_action": decision.next_action,
            },
        )
    return budget, decision


def _finalize_vector_store_budget(
    *,
    budget: RunBudget,
    decision: BudgetDecision,
    ctx: RunContext,
    attempted: bool,
    outcome: str,
    error_code: str = "",
) -> None:
    if not decision.reservation_key:
        return
    finalize_budget_side_effect(
        BudgetSideEffectFinalizeRequest(
            schema_version="1.0",
            usage_db_path=budget.usage_db_path,
            reservation_key=decision.reservation_key,
            actual_usage=RunBudgetUsage(
                schema_version="1.0", calls=1 if attempted else 0
            ),
            outcome=outcome,
            error_code=error_code,
        ),
        ctx,
    )


def _run_governed_vector_store_request(
    *,
    request: Any,
    ctx: RunContext,
    operation: str,
    spec: _VectorStoreOperationSpec,
    request_fn,
    error_context: dict[str, Any] | None = None,
) -> Any:
    """Reserve before a provider call and reconcile its measured call count once."""
    budget, decision = _require_vector_store_budget(request, ctx, operation=operation)
    attempted = False

    def _attempt(client: Any) -> Any:
        nonlocal attempted
        attempted = True
        return request_fn(client)

    try:
        response = _run_vector_store_request(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            spec=spec,
            ctx=ctx,
            request_fn=_attempt,
            error_context=error_context,
        )
    except AppError as exc:
        _finalize_vector_store_budget(
            budget=budget,
            decision=decision,
            ctx=ctx,
            attempted=attempted,
            outcome="failed",
            error_code=exc.code,
        )
        raise
    _finalize_vector_store_budget(
        budget=budget,
        decision=decision,
        ctx=ctx,
        attempted=attempted,
        outcome="completed",
    )
    return response


def openai_vector_store_create(
    request: OpenAIVectorStoreCreateRequest, ctx: RunContext
) -> OpenAIVectorStoreCreateResponse:
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_CREATE_OPERATION.start_event,
        fields={
            "name": request.name,
            "metadata_keys": list((request.metadata or {}).keys()),
            "timeout_seconds": request.timeout_seconds,
        },
    )
    resp = _run_governed_vector_store_request(
        request=request,
        operation="openai_vector_store_create",
        spec=_VECTOR_STORE_CREATE_OPERATION,
        ctx=ctx,
        request_fn=lambda client: client.vector_stores.create(
            name=request.name, metadata=request.metadata or {}
        ),
    )
    vector_store_id = _require_openai_id(
        resp,
        code="openai_vector_store_create_failed",
        message="OpenAI vector store create did not return an id",
    )
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_CREATE_OPERATION.complete_event,
        fields={"name": request.name, "vector_store_id": vector_store_id},
    )
    return OpenAIVectorStoreCreateResponse(
        schema_version="1.0", vector_store_id=vector_store_id
    )


def openai_vector_store_upload_file(
    request: OpenAIVectorStoreFileUploadRequest,
    ctx: RunContext,
) -> OpenAIVectorStoreFileUploadResponse:
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_UPLOAD_OPERATION.start_event,
        fields={
            "file_path": request.file_path,
            "purpose": request.purpose,
            "timeout_seconds": request.timeout_seconds,
        },
    )
    try:
        with open(request.file_path, "rb") as file_handle:
            resp = _run_governed_vector_store_request(
                request=request,
                operation="openai_vector_store_upload",
                spec=_VECTOR_STORE_UPLOAD_OPERATION,
                ctx=ctx,
                request_fn=lambda client: client.files.create(
                    file=file_handle, purpose=request.purpose
                ),
            )
    except FileNotFoundError as exc:
        raise AppError(
            code="openai_file_missing",
            message=f"File not found: {request.file_path}",
            cause=exc,
            retryable=False,
        ) from exc
    except OSError as exc:
        raise AppError(
            code="openai_file_open_failed",
            message=f"Unable to read file: {request.file_path}",
            cause=exc,
            retryable=False,
        ) from exc
    openai_file_id = _require_openai_id(
        resp,
        code="openai_vector_store_upload_failed",
        message="OpenAI file upload did not return an id",
    )
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_UPLOAD_OPERATION.complete_event,
        fields={"file_path": request.file_path, "openai_file_id": openai_file_id},
    )
    return OpenAIVectorStoreFileUploadResponse(
        schema_version="1.0", openai_file_id=openai_file_id
    )


def openai_vector_store_attach_file(
    request: OpenAIVectorStoreAttachFileRequest,
    ctx: RunContext,
) -> OpenAIVectorStoreAttachFileResponse:
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_ATTACH_OPERATION.start_event,
        fields={
            "vector_store_id": request.vector_store_id,
            "openai_file_id": request.openai_file_id,
            "timeout_seconds": request.timeout_seconds,
        },
    )
    resp = _run_governed_vector_store_request(
        request=request,
        operation="openai_vector_store_attach",
        spec=_VECTOR_STORE_ATTACH_OPERATION,
        ctx=ctx,
        request_fn=lambda client: client.vector_stores.files.create(
            vector_store_id=request.vector_store_id,
            file_id=request.openai_file_id,
        ),
    )
    attached_id = _require_openai_id(
        resp,
        code="openai_vector_store_attach_failed",
        message="OpenAI vector store attach did not return an id",
    )
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_ATTACH_OPERATION.complete_event,
        fields={
            "vector_store_id": request.vector_store_id,
            "openai_file_id": attached_id,
        },
    )
    return OpenAIVectorStoreAttachFileResponse(
        schema_version="1.0",
        vector_store_id=request.vector_store_id,
        openai_file_id=attached_id,
    )


def openai_vector_store_status(
    request: OpenAIVectorStoreStatusRequest,
    ctx: RunContext,
) -> OpenAIVectorStoreStatusResponse:
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_STATUS_OPERATION.start_event,
        fields={
            "vector_store_id": request.vector_store_id,
            "timeout_seconds": request.timeout_seconds,
        },
    )
    resp = _run_governed_vector_store_request(
        request=request,
        operation="openai_vector_store_status",
        spec=_VECTOR_STORE_STATUS_OPERATION,
        ctx=ctx,
        request_fn=lambda client: client.vector_stores.retrieve(
            request.vector_store_id
        ),
        error_context={"vector_store_id": request.vector_store_id},
    )
    status = _value_from_response(resp, "status")
    indexed_at = _value_from_response(resp, "created_at")
    last_error = _value_from_response(resp, "last_error")
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_STATUS_OPERATION.complete_event,
        fields={"vector_store_id": request.vector_store_id, "status": status},
    )
    return OpenAIVectorStoreStatusResponse(
        schema_version="1.0",
        vector_store_id=request.vector_store_id,
        status=str(status or ""),
        indexed_at_utc=str(indexed_at) if indexed_at is not None else None,
        last_error=str(last_error) if last_error else None,
    )


def openai_vector_store_delete(
    request: OpenAIVectorStoreDeleteRequest,
    ctx: RunContext,
) -> OpenAIVectorStoreDeleteResponse:
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_DELETE_OPERATION.start_event,
        fields={
            "vector_store_id": request.vector_store_id,
            "timeout_seconds": request.timeout_seconds,
        },
    )
    resp = _run_governed_vector_store_request(
        request=request,
        operation="openai_vector_store_delete",
        spec=_VECTOR_STORE_DELETE_OPERATION,
        ctx=ctx,
        request_fn=lambda client: client.vector_stores.delete(request.vector_store_id),
        error_context={"vector_store_id": request.vector_store_id},
    )
    deleted_id = _value_from_response(resp, "id") or request.vector_store_id
    deleted = bool(_value_from_response(resp, "deleted"))
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_DELETE_OPERATION.complete_event,
        fields={"vector_store_id": str(deleted_id), "deleted": deleted},
    )
    return OpenAIVectorStoreDeleteResponse(
        schema_version="1.0",
        vector_store_id=str(deleted_id),
        deleted=deleted,
    )


def openai_vector_store_update_metadata(
    request: OpenAIVectorStoreUpdateMetadataRequest,
    ctx: RunContext,
) -> OpenAIVectorStoreUpdateMetadataResponse:
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_UPDATE_METADATA_OPERATION.start_event,
        fields={
            "vector_store_id": request.vector_store_id,
            "metadata_keys": list((request.metadata or {}).keys()),
            "timeout_seconds": request.timeout_seconds,
        },
    )
    resp = _run_governed_vector_store_request(
        request=request,
        operation="openai_vector_store_update",
        spec=_VECTOR_STORE_UPDATE_METADATA_OPERATION,
        ctx=ctx,
        request_fn=lambda client: client.vector_stores.update(
            vector_store_id=request.vector_store_id,
            metadata=request.metadata or {},
        ),
        error_context={"vector_store_id": request.vector_store_id},
    )
    updated_id = _require_openai_id(
        resp,
        code="openai_vector_store_update_metadata_failed",
        message="OpenAI vector store metadata update did not return an id",
    )
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_UPDATE_METADATA_OPERATION.complete_event,
        fields={"vector_store_id": updated_id},
    )
    return OpenAIVectorStoreUpdateMetadataResponse(
        schema_version="1.0", vector_store_id=updated_id
    )


__all__ = [name for name in globals() if not name.startswith("__")]
