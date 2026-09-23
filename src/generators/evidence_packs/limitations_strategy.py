from __future__ import annotations

import re

from src.generators.evidence_packs.base import (
    build_list_pack_strategy,
)
from src.generators.evidence_packs.common import (
    coerce_pack_items,
    first_non_empty_text,
    text,
    to_dict,
)

_FILE_CITATION = re.compile(
    r"\ue200filecite(?:\ue202turn\d+file\d+)+\ue201", re.IGNORECASE
)


def _public_limitation_text(value: str) -> str:
    return " ".join(_FILE_CITATION.sub("", value).split())


def normalize_limitations(raw_limitations: object) -> list[str]:
    limitations: list[str] = []
    for entry in coerce_pack_items(raw_limitations):
        if isinstance(entry, str):
            text_value = _public_limitation_text(entry)
            if text_value:
                limitations.append(text_value)
            continue
        if not isinstance(entry, dict):
            continue
        item = to_dict(entry)
        description = first_non_empty_text(
            item.get("description"),
            item.get("text"),
            item.get("summary"),
            item.get("limitation"),
            item.get("title"),
            item.get("type"),
        )
        mitigation = text(item.get("mitigation"))
        if description and mitigation:
            limitations.append(
                _public_limitation_text(f"{description} Mitigation: {mitigation}")
            )
            continue
        if description:
            limitations.append(_public_limitation_text(description))
            continue
        if mitigation:
            limitations.append(_public_limitation_text(f"Mitigation: {mitigation}"))
    return limitations


LIMITATIONS_STRATEGY = build_list_pack_strategy(
    pack_name="limitations",
    prompt_namespace_suffix="evidence_packs/limitations",
    schema_name="limitations_pack",
    root_key="limitations",
    source_aliases=("risks", "challenges"),
    normalize_items=normalize_limitations,
)
