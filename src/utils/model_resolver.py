from __future__ import annotations

from typing import Dict


def _normalize_namespace(namespace: str) -> str:
    if not isinstance(namespace, str):
        return ""
    normalized = namespace.replace(".", "/").strip()
    return normalized.strip("/")


def resolve_model(namespace: str, overrides: Dict[str, str], default_model: str) -> str:
    """
    Resolve the model for a prompt namespace using longest-prefix match.

    Examples:
    - namespace: "report_vs/validate/grounding"
    - overrides keys allowed: "report_vs/validate/grounding", "report_vs/validate", "report_vs"
    """
    base = _normalize_namespace(namespace)
    if not base:
        return default_model
    mapping: Dict[str, str] = {}
    if isinstance(overrides, dict):
        for raw_key, raw_value in overrides.items():
            key = _normalize_namespace(str(raw_key))
            val = str(raw_value).strip()
            if key and val:
                mapping[key] = val
    parts = base.split("/")
    for idx in range(len(parts), 0, -1):
        candidate = "/".join(parts[:idx])
        if candidate in mapping:
            return mapping[candidate]
    return default_model
