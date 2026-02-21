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
    one_of = schema.get("oneOf")
    if isinstance(one_of, list) and one_of:
        first_error: AppError | None = None
        for candidate_schema in one_of:
            if not isinstance(candidate_schema, dict):
                continue
            try:
                _validate(value, candidate_schema, path)
                return
            except AppError as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    expected_types = schema.get("type")
    if isinstance(expected_types, str):
        expected_types = [expected_types]
    elif not isinstance(expected_types, list):
        expected_types = []

    if expected_types:
        if not _matches_any_type(value, expected_types):
            expected = ", ".join(expected_types)
            raise AppError(
                code="schema_type_mismatch",
                message=f"{path} should be one of [{expected}]",
                retryable=False,
            )
        if value is None:
            # Nothing else to validate for null values once type is satisfied.
            return

    if isinstance(value, dict):
        if "object" not in expected_types:
            return
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
    elif isinstance(value, list):
        if "array" not in expected_types:
            return
        item_schema = schema.get("items", {})
        for idx, item in enumerate(value):
            _validate(item, item_schema, f"{path}[{idx}]")
    elif isinstance(value, str):
        if "string" not in expected_types:
            return
        enum = schema.get("enum")
        if enum and value not in enum:
            raise AppError(
                code="schema_enum_mismatch",
                message=f"{path} must be one of {enum}",
                retryable=False,
            )
    elif isinstance(value, bool):
        return
    elif isinstance(value, int):
        return
    elif isinstance(value, float):
        return
    else:
        # Unknown types are treated as pass-through.
        return


def _matches_any_type(value: Any, expected_types: list[str]) -> bool:
    for expected_type in expected_types:
        if expected_type == "null" and value is None:
            return True
        if expected_type == "object" and isinstance(value, dict):
            return True
        if expected_type == "array" and isinstance(value, list):
            return True
        if expected_type == "string" and isinstance(value, str):
            return True
        if expected_type == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if expected_type == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if expected_type == "boolean" and isinstance(value, bool):
            return True
    return False
