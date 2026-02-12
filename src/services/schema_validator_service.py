from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest, SchemaValidateResponse
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.schema_validator_service")
SCHEMAS_ROOT = Path(__file__).resolve().parents[1] / "schemas"
_SCHEMA_CACHE: Dict[str, dict] = {}


def _load_schema(name: str) -> dict:
    if name in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[name]
    path = SCHEMAS_ROOT / f"{name}.schema.json"
    if not path.exists():
        raise AppError(
            code="schema_not_found",
            message=f"Schema not found: {path}",
            retryable=False,
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError(
            code="schema_invalid_json",
            message=f"Schema JSON invalid: {path}",
            cause=exc,
            retryable=False,
        ) from exc
    _SCHEMA_CACHE[name] = data
    return data


def validate_schema(request: SchemaValidateRequest, ctx: RunContext) -> SchemaValidateResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="schema_validation_start",
        module=logger.name,
        fields={"schema": request.schema_name},
    ))
    schema = _load_schema(request.schema_name)
    try:
        _validate(request.payload, schema, path="root")
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="schema_validation_failed",
            message=str(exc),
            cause=exc,
            retryable=False,
            context={"schema": request.schema_name},
        ) from exc
    logger.info(log_event(
        ctx,
        role="service",
        event="schema_validation_complete",
        module=logger.name,
        fields={"schema": request.schema_name},
    ))
    return SchemaValidateResponse(schema_version="1.0", schema_name=request.schema_name, valid=True)


def _validate(value: Any, schema: dict, path: str) -> None:
    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        expected_type = expected_type[0]
    if expected_type == "object":
        if not isinstance(value, dict):
            raise AppError(
                code="schema_type_mismatch",
                message=f"{path} should be object",
                retryable=False,
            )
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise AppError(
                    code="schema_missing_required",
                    message=f"{path}.{key} is required",
                    retryable=False,
                )
        props = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                _validate(v, props[k], f"{path}.{k}")
    elif expected_type == "array":
        if not isinstance(value, list):
            raise AppError(
                code="schema_type_mismatch",
                message=f"{path} should be array",
                retryable=False,
            )
        item_schema = schema.get("items", {})
        for idx, item in enumerate(value):
            _validate(item, item_schema, f"{path}[{idx}]")
    elif expected_type == "string":
        if not isinstance(value, str):
            raise AppError(
                code="schema_type_mismatch",
                message=f"{path} should be string",
                retryable=False,
            )
        enum = schema.get("enum")
        if enum and value not in enum:
            raise AppError(
                code="schema_enum_mismatch",
                message=f"{path} must be one of {enum}",
                retryable=False,
            )
    elif expected_type == "integer":
        if not isinstance(value, int):
            raise AppError(
                code="schema_type_mismatch",
                message=f"{path} should be integer",
                retryable=False,
            )
    elif expected_type == "number":
        if not isinstance(value, (int, float)):
            raise AppError(
                code="schema_type_mismatch",
                message=f"{path} should be number",
                retryable=False,
            )
    elif expected_type == "boolean":
        if not isinstance(value, bool):
            raise AppError(
                code="schema_type_mismatch",
                message=f"{path} should be boolean",
                retryable=False,
            )
    else:
        # Unknown types are treated as pass-through.
        return
