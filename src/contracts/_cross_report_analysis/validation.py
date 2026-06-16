from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any, cast, get_type_hints

from src.contracts.schema_validation import (
    empty_required_value as _empty_required_value,
    field_is_list_typed as _field_is_list_typed,
    field_is_required as _field_is_required,
)
from src.utils.errors import AppError

from src.contracts._cross_report_analysis import CROSS_REPORT_ANALYSIS_SCHEMA_VERSION

_CONTRACT_MODULE_PREFIX = "src.contracts._cross_report_analysis."


def validate_cross_report_contract(contract: object) -> None:
    contract_type = type(contract)
    if (
        not is_dataclass(contract)
        or not contract_type.__module__.startswith(_CONTRACT_MODULE_PREFIX)
        or not contract_type.__name__.startswith("CrossReport")
    ):
        _raise_invalid(
            contract_type.__name__,
            "<root>",
            "expected cross-report dataclass contract",
        )
        return
    _validate_contract_value(contract, path=contract_type.__name__)


def _raise_invalid(path: str, field_name: str, reason: str) -> None:
    raise AppError(
        code="cross_report_contract_invalid",
        message=f"Invalid cross-report contract field {path}: {reason}",
        retryable=False,
        severity="error",
        context={"path": path, "field": field_name, "reason": reason},
    )


def _validate_contract_value(value: object, *, path: str) -> None:
    if is_dataclass(value):
        _validate_dataclass_instance(value, path=path)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_contract_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_contract_value(item, path=f"{path}.{key}")


def _validate_dataclass_instance(instance: object, *, path: str) -> None:
    type_hints = get_type_hints(type(instance))
    for field_def in fields(cast(Any, instance)):
        field_value = getattr(instance, field_def.name)
        field_path = f"{path}.{field_def.name}"
        field_annotation = type_hints.get(field_def.name, field_def.type)
        if field_def.name == "schema_version":
            if field_value != CROSS_REPORT_ANALYSIS_SCHEMA_VERSION:
                _raise_invalid(field_path, field_def.name, "unsupported schema version")
        if _field_is_list_typed(field_annotation) and field_value is None:
            _raise_invalid(field_path, field_def.name, "list field cannot be null")
        if _field_is_required(field_def) and _empty_required_value(field_value):
            _raise_invalid(field_path, field_def.name, "required value is empty")
        _validate_contract_value(field_value, path=field_path)
