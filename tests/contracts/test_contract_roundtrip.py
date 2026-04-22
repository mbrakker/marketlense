from __future__ import annotations

import enum
import importlib
import pkgutil
from dataclasses import MISSING, asdict, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

import pytest

import src.contracts as contracts_pkg


def _contract_dataclasses() -> list[type]:
    discovered: list[type] = []
    for module_info in pkgutil.iter_modules(
        contracts_pkg.__path__, f"{contracts_pkg.__name__}."
    ):
        module = importlib.import_module(module_info.name)
        for candidate in vars(module).values():
            if (
                isinstance(candidate, type)
                and is_dataclass(candidate)
                and candidate.__module__ == module.__name__
            ):
                discovered.append(candidate)
    discovered.sort(key=lambda item: f"{item.__module__}.{item.__name__}")
    return discovered


def _build_value(annotation: Any, field_name: str, stack: tuple[type, ...]) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if annotation in {Any, object}:
        return f"{field_name}_value"
    if annotation is None or annotation is type(None):
        return None
    if origin in {Union, getattr(__import__("types"), "UnionType", Union)}:
        non_none = [arg for arg in args if arg is not type(None)]
        if len(non_none) < len(args):
            return _build_value(non_none[0], field_name, stack) if non_none else None
        return _build_value(args[0], field_name, stack)
    if origin is Literal:
        return args[0]
    if origin in {list, tuple, set, dict}:
        if origin is list:
            return (
                [_build_value(args[0], f"{field_name}_item", stack)]
                if args
                else [f"{field_name}_item"]
            )
        if origin is tuple:
            if len(args) == 2 and args[1] is Ellipsis:
                return (_build_value(args[0], f"{field_name}_item", stack),)
            return tuple(
                _build_value(arg, f"{field_name}_{idx}", stack)
                for idx, arg in enumerate(args)
            )
        if origin is set:
            return (
                {_build_value(args[0], f"{field_name}_item", stack)}
                if args
                else {f"{field_name}_item"}
            )
        key = _build_value(args[0], f"{field_name}_key", stack) if args else "key"
        value = (
            _build_value(args[1], f"{field_name}_value", stack)
            if len(args) > 1
            else "value"
        )
        return {key: value}
    if annotation is str:
        return f"{field_name}_value"
    if annotation is int:
        return 1
    if annotation is float:
        return 1.5
    if annotation is bool:
        return True
    if annotation is bytes:
        return b"bytes"
    if annotation is Path:
        return Path(f"/tmp/{field_name}")
    if annotation is datetime:
        return datetime(2024, 1, 1, tzinfo=timezone.utc)
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return next(iter(annotation))
    if isinstance(annotation, type) and is_dataclass(annotation):
        if annotation in stack:
            return None
        return _build_dataclass(annotation, stack + (annotation,))
    return f"{field_name}_value"


def _build_dataclass(contract_cls: type, stack: tuple[type, ...]) -> Any:
    hints = get_type_hints(contract_cls, include_extras=True)
    values: dict[str, Any] = {}
    for field in fields(contract_cls):
        if field.default is not MISSING:
            values[field.name] = field.default
            continue
        if field.default_factory is not MISSING:
            values[field.name] = field.default_factory()
            continue
        annotation = hints.get(field.name, field.type)
        values[field.name] = _build_value(annotation, field.name, stack)
    return contract_cls(**values)


def _from_plain(annotation: Any, raw: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if raw is None:
        return None
    if annotation in {Any, object}:
        return raw
    if origin in {Union, getattr(__import__("types"), "UnionType", Union)}:
        last_error: Exception | None = None
        for arg in args:
            if arg is type(None) and raw is None:
                return None
            try:
                return _from_plain(arg, raw)
            except Exception as exc:  # pragma: no cover - defensive fallback
                last_error = exc
                continue
        if last_error:
            raise last_error
        return raw
    if origin is Literal:
        return raw
    if origin is list:
        item_type = args[0] if args else Any
        return [_from_plain(item_type, item) for item in raw]
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_from_plain(args[0], item) for item in raw)
        return tuple(_from_plain(arg, item) for arg, item in zip(args, raw))
    if origin is set:
        item_type = args[0] if args else Any
        return {_from_plain(item_type, item) for item in raw}
    if origin is dict:
        key_type = args[0] if args else Any
        value_type = args[1] if len(args) > 1 else Any
        return {
            _from_plain(key_type, key): _from_plain(value_type, value)
            for key, value in raw.items()
        }
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return raw if isinstance(raw, annotation) else annotation(raw)
    if isinstance(annotation, type) and is_dataclass(annotation):
        hints = get_type_hints(annotation, include_extras=True)
        values: dict[str, Any] = {}
        for field in fields(annotation):
            if field.name not in raw:
                continue
            field_type = hints.get(field.name, field.type)
            values[field.name] = _from_plain(field_type, raw[field.name])
        return annotation(**values)
    return raw


@pytest.mark.parametrize(
    "contract_cls",
    _contract_dataclasses(),
    ids=lambda cls: f"{cls.__module__}.{cls.__name__}",
)
def test_contract_dataclass_roundtrip(contract_cls: type) -> None:
    instance = _build_dataclass(contract_cls, stack=(contract_cls,))
    payload = asdict(instance)
    reconstructed = _from_plain(contract_cls, payload)
    assert reconstructed == instance


@pytest.mark.parametrize(
    "contract_cls",
    _contract_dataclasses(),
    ids=lambda cls: f"{cls.__module__}.{cls.__name__}",
)
def test_contract_dataclasses_expose_schema_version(contract_cls: type) -> None:
    field_by_name = {field.name: field for field in fields(contract_cls)}

    assert "schema_version" in field_by_name
    assert "doc" in field_by_name["schema_version"].metadata
