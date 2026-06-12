from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

from typing import Any

from src.contracts.ui_run_control import UiRunWorkerRequest
from src.contracts.ui_run_replay import UiRunExecutionResponse
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError

from .shared import *  # noqa: F401,F403
from .shared import PROMPT_TREE_ROOT, SOURCE_TREE_ROOT


def _invalid_payload_config_snapshot(
    *,
    worker_request: UiRunWorkerRequest,
    error: AppError,
) -> dict[str, Any]:
    return {
        "run_type": worker_request.run_type,
        "request_payload_keys": sorted(worker_request.request_payload.keys()),
        "source_tree_root": str(SOURCE_TREE_ROOT),
        "prompt_tree_root": str(PROMPT_TREE_ROOT),
        "payload_error": {
            "code": error.code,
            "field": error.context.get("field", ""),
        },
    }


def _execution_response(
    *,
    worker_request: UiRunWorkerRequest,
    status: str,
    result_summary: dict[str, Any],
    artifact_paths: list[str],
    config_snapshot: dict[str, Any],
    error_code: str = "",
    error_message: str = "",
    error_retryable: bool = False,
    error_severity: str = "error",
) -> UiRunExecutionResponse:
    return UiRunExecutionResponse(
        schema_version="1.0",
        run_id=worker_request.run_id,
        run_type=worker_request.run_type,
        status=status,
        result_summary=result_summary,
        artifact_paths=artifact_paths,
        config_snapshot=config_snapshot,
        config_fingerprint=sha256_json(config_snapshot),
        error_code=error_code,
        error_message=error_message,
        error_retryable=error_retryable,
        error_severity=error_severity,
    )


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
