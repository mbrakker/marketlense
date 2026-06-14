from __future__ import annotations

from dataclasses import MISSING, dataclass, field
from typing import Any, List, get_origin


def field_is_required(field_def: Any) -> bool:
    if field_def.metadata.get("required") is False:
        return False
    return field_def.default is MISSING and field_def.default_factory is MISSING


def field_is_list_typed(annotation: Any) -> bool:
    return annotation in {list, List} or get_origin(annotation) in {list, List}


def empty_required_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


@dataclass(frozen=True)
class SchemaValidateRequest:
    schema_version: str = field(
        metadata={"doc": "Schema validation request schema version."}
    )
    payload: Any = field(
        metadata={"doc": "Payload to validate against a named schema."}
    )
    schema_name: str = field(
        metadata={"doc": "Schema name without .schema.json suffix."}
    )


@dataclass(frozen=True)
class SchemaValidateResponse:
    schema_version: str = field(
        metadata={"doc": "Schema validation response schema version."}
    )
    schema_name: str = field(metadata={"doc": "Schema name that was validated."})
    valid: bool = field(metadata={"doc": "True when validation passes."})
