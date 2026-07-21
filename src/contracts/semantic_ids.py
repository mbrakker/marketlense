from __future__ import annotations

from dataclasses import fields, is_dataclass
from types import UnionType
from typing import Any, ClassVar, Union, get_args, get_origin, get_type_hints


class SemanticId(str):
    """Typed string identifier that rejects cross-ID reuse at runtime."""

    kind: ClassVar[str] = "semantic_id"

    def __new__(cls, value: object) -> SemanticId:
        if isinstance(value, cls):
            return value
        if isinstance(value, SemanticId):
            raise TypeError(
                f"{cls.__name__} cannot be constructed from {type(value).__name__}"
            )
        if not isinstance(value, str):
            raise TypeError(
                f"{cls.__name__} expects a string value, got {type(value).__name__}"
            )
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{cls.__name__} requires a non-empty string value")
        return str.__new__(cls, normalized)


class RunId(SemanticId):
    kind = "run_id"


class TaskId(SemanticId):
    kind = "task_id"


class ReportId(SemanticId):
    kind = "report_id"


class EntityUid(SemanticId):
    kind = "entity_uid"


class PublisherId(SemanticId):
    kind = "publisher_id"


class ValidationRunId(SemanticId):
    kind = "validation_run_id"


class SemanticIdContract:
    """Dataclass mixin that coerces and validates semantic ID fields."""

    def __post_init__(self) -> None:
        coerce_semantic_id_fields(self)


_SEMANTIC_ID_ANNOTATIONS_CACHE: dict[type[Any], dict[str, Any]] = {}


def _semantic_id_annotations(contract_cls: type[Any]) -> dict[str, Any]:
    cached = _SEMANTIC_ID_ANNOTATIONS_CACHE.get(contract_cls)
    if cached is not None:
        return cached
    if not is_dataclass(contract_cls):
        return {}
    hints = get_type_hints(contract_cls, include_extras=True)
    annotations: dict[str, Any] = {}
    for field_def in fields(contract_cls):
        annotation = hints.get(field_def.name, field_def.type)
        if _is_supported_semantic_id_annotation(annotation):
            annotations[field_def.name] = annotation
    _SEMANTIC_ID_ANNOTATIONS_CACHE[contract_cls] = annotations
    return annotations


def _is_supported_semantic_id_annotation(annotation: Any) -> bool:
    if isinstance(annotation, type) and issubclass(annotation, SemanticId):
        return True
    origin = get_origin(annotation)
    if origin not in {Union, UnionType}:
        return False
    non_none_args = [arg for arg in get_args(annotation) if arg is not type(None)]
    return len(non_none_args) == 1 and _is_supported_semantic_id_annotation(
        non_none_args[0]
    )


def _coerce_semantic_id_value(
    annotation: Any,
    value: Any,
    *,
    contract_name: str,
    field_name: str,
) -> Any:
    if isinstance(annotation, type) and issubclass(annotation, SemanticId):
        try:
            return annotation(value)
        except (TypeError, ValueError) as exc:
            raise type(exc)(f"{contract_name}.{field_name}: {exc}") from exc

    origin = get_origin(annotation)
    if origin in {Union, UnionType}:
        non_none_args = [arg for arg in get_args(annotation) if arg is not type(None)]
        allows_none = len(non_none_args) != len(get_args(annotation))
        if value is None:
            if allows_none:
                return None
            raise TypeError(f"{contract_name}.{field_name}: value cannot be None")
        if len(non_none_args) == 1:
            return _coerce_semantic_id_value(
                non_none_args[0],
                value,
                contract_name=contract_name,
                field_name=field_name,
            )
    return value


def coerce_semantic_id_fields(instance: object) -> None:
    annotations = _semantic_id_annotations(type(instance))
    if not annotations:
        return
    contract_name = type(instance).__name__
    for field_name, annotation in annotations.items():
        current_value = getattr(instance, field_name)
        coerced_value = _coerce_semantic_id_value(
            annotation,
            current_value,
            contract_name=contract_name,
            field_name=field_name,
        )
        if type(coerced_value) is not type(current_value):
            object.__setattr__(instance, field_name, coerced_value)
