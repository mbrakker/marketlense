from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class YamlMappingError(RuntimeError):
    kind: str
    label: str
    path: str
    root_type: str | None = None
    cause: Exception | None = None

    def __post_init__(self) -> None:
        message = _mapping_error_message(
            kind=self.kind,
            label=self.label,
            path=self.path,
            root_type=self.root_type,
        )
        RuntimeError.__init__(self, message)


def _mapping_error_message(
    *,
    kind: str,
    label: str,
    path: str,
    root_type: str | None,
) -> str:
    if kind == "not_found":
        return f"{label} YAML not found: {path}"
    if kind == "invalid":
        return f"{label} YAML invalid: {path}"
    if kind == "root_invalid":
        return f"{label} YAML must be a mapping: {path}"
    if kind == "read_failed":
        return f"Failed to read {label} YAML: {path}"
    return f"{label} YAML error: {path}"


def parse_yaml_mapping(
    content: str,
    *,
    label: str,
    path: str | Path,
) -> dict[str, Any]:
    path_str = str(path)
    try:
        payload = yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        raise YamlMappingError(
            kind="invalid",
            label=label,
            path=path_str,
            cause=exc,
        ) from exc
    if not isinstance(payload, dict):
        raise YamlMappingError(
            kind="root_invalid",
            label=label,
            path=path_str,
            root_type=type(payload).__name__,
        )
    return payload


def load_yaml_mapping(path: str | Path, *, label: str) -> dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise YamlMappingError(kind="not_found", label=label, path=str(cfg_path))
    try:
        content = cfg_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise YamlMappingError(
            kind="read_failed",
            label=label,
            path=str(cfg_path),
            cause=exc,
        ) from exc
    return parse_yaml_mapping(content, label=label, path=cfg_path)


def deep_merge_mappings(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, overlay_value in overlay.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            merged[key] = deep_merge_mappings(base_value, overlay_value)
            continue
        merged[key] = deepcopy(overlay_value)
    return merged
