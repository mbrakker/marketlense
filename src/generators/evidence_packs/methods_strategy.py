from __future__ import annotations

from src.generators.evidence_packs.base import (
    build_list_pack_strategy,
)
from src.generators.evidence_packs.common import coerce_pack_items, text


def normalize_methods(raw_methods: object) -> list[object]:
    methods: list[object] = []
    for entry in coerce_pack_items(raw_methods):
        if isinstance(entry, dict):
            methods.append(entry)
            continue
        text_value = text(entry)
        if text_value:
            methods.append(text_value)
    return methods


METHODS_STRATEGY = build_list_pack_strategy(
    pack_name="methods",
    prompt_namespace_suffix="evidence_packs/methods",
    schema_name="methods_pack",
    root_key="methods",
    source_aliases=("methodology", "approach"),
    normalize_items=normalize_methods,
)
