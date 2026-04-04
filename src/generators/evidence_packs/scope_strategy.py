from __future__ import annotations

from src.generators.evidence_packs.base import (
    build_scalar_pack_strategy,
)
from src.generators.evidence_packs.common import text


def normalize_scope(scope_value: object) -> object:
    if scope_value is None:
        return ""
    if isinstance(scope_value, (str, dict)):
        return scope_value
    return text(scope_value)


SCOPE_STRATEGY = build_scalar_pack_strategy(
    pack_name="scope",
    prompt_namespace_suffix="evidence_packs/scope",
    schema_name="scope_pack",
    root_key="scope",
    default_value="",
    normalize_value=normalize_scope,
)
