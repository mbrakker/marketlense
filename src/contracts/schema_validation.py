from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SchemaValidateRequest:
    schema_version: str = field(metadata={"doc": "Schema validation request schema version."})
    payload: Any = field(metadata={"doc": "Payload to validate against a named schema."})
    schema_name: str = field(metadata={"doc": "Schema name without .schema.json suffix."})


@dataclass(frozen=True)
class SchemaValidateResponse:
    schema_version: str = field(metadata={"doc": "Schema validation response schema version."})
    schema_name: str = field(metadata={"doc": "Schema name that was validated."})
    valid: bool = field(metadata={"doc": "True when validation passes."})
