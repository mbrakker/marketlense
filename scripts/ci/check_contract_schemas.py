from __future__ import annotations

import argparse
import enum
import importlib
import json
import pkgutil
import sys
from dataclasses import MISSING, fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.contracts as contracts_pkg


def _contract_dataclasses() -> list[type]:
    discovered: dict[str, type] = {}
    for module_info in pkgutil.walk_packages(
        contracts_pkg.__path__, f"{contracts_pkg.__name__}."
    ):
        if not all(part.isidentifier() for part in module_info.name.split(".")):
            continue
        module = importlib.import_module(module_info.name)
        for candidate in vars(module).values():
            if (
                isinstance(candidate, type)
                and is_dataclass(candidate)
                and candidate.__module__ == module.__name__
            ):
                discovered[f"{candidate.__module__}.{candidate.__name__}"] = candidate
    return sorted(discovered.values(), key=lambda cls: f"{cls.__module__}.{cls.__name__}")


def _schema_for_type(annotation: Any) -> dict[str, Any]:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if annotation in {Any, object}:
        return {}
    if (
        annotation is str
        or isinstance(annotation, type)
        and issubclass(annotation, str)
    ):
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is bytes:
        return {"type": "string", "contentEncoding": "base64"}
    if annotation is Path:
        return {"type": "string"}
    if annotation is datetime:
        return {"type": "string", "format": "date-time"}
    if annotation is type(None):
        return {"type": "null"}
    if origin is Literal:
        return {"enum": list(args)}
    if origin in {Union, getattr(__import__("types"), "UnionType", Union)}:
        return {"anyOf": [_schema_for_type(arg) for arg in args]}
    if origin is list:
        return {"type": "array", "items": _schema_for_type(args[0] if args else Any)}
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return {"type": "array", "items": _schema_for_type(args[0])}
        return {
            "type": "array",
            "prefixItems": [_schema_for_type(arg) for arg in args],
            "minItems": len(args),
            "maxItems": len(args),
        }
    if origin is set:
        return {
            "type": "array",
            "uniqueItems": True,
            "items": _schema_for_type(args[0] if args else Any),
        }
    if origin is dict:
        return {
            "type": "object",
            "additionalProperties": _schema_for_type(args[1] if len(args) > 1 else Any),
        }
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return {"enum": [item.value for item in annotation]}
    if isinstance(annotation, type) and is_dataclass(annotation):
        return {"$ref": f"#/$defs/{annotation.__module__}.{annotation.__name__}"}
    return {"type": "string"}


def build_contract_schema_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {"schema_version": "1.0", "contracts": {}}
    for contract_cls in _contract_dataclasses():
        hints = get_type_hints(contract_cls, include_extras=True)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for field_def in fields(contract_cls):
            annotation = hints.get(field_def.name, field_def.type)
            properties[field_def.name] = _schema_for_type(annotation)
            if field_def.default is MISSING and field_def.default_factory is MISSING:
                required.append(field_def.name)
        key = f"{contract_cls.__module__}.{contract_cls.__name__}"
        snapshot["contracts"][key] = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
    return snapshot


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate or verify the dataclass contract schema snapshot."
    )
    parser.add_argument(
        "--snapshot",
        default="docs/quality/contract_schemas.json",
        help="Committed schema snapshot path.",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Rewrite the committed snapshot instead of checking it.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    snapshot_path = ROOT / args.snapshot
    current = build_contract_schema_snapshot()
    rendered = json.dumps(current, ensure_ascii=True, indent=2, sort_keys=True) + "\n"

    if args.update:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(rendered, encoding="utf-8")
        print(f"Contract schema snapshot updated: {args.snapshot}")
        return 0

    if not snapshot_path.exists():
        print(f"Contract schema snapshot missing: {args.snapshot}")
        return 1
    expected = snapshot_path.read_text(encoding="utf-8")
    if expected != rendered:
        print("Contract schema snapshot is stale.")
        print(f"Run: {sys.executable} scripts/ci/check_contract_schemas.py --update")
        return 1
    print("Contract schema snapshot gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
