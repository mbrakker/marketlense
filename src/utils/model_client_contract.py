from __future__ import annotations

from typing import Any

from src.utils.errors import AppError


def require_injected_model_client(client: Any, *, scope: str) -> Any:
    """Validate model-client injection at generator boundaries."""
    if client is not None:
        return client
    raise AppError(
        code="model_client_required",
        message="Model-backed generator requires an injected model client",
        retryable=False,
        severity="error",
        context={"scope": scope},
    )
