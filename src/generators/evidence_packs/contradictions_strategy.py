from __future__ import annotations

from src.generators.evidence_packs.base import (
    build_list_pack_strategy,
)
from src.generators.evidence_packs.common import (
    coerce_pack_items,
    first_non_empty_text,
    to_dict,
)
def normalize_contradictions(raw_contradictions: object) -> list[dict[str, object]]:
    contradictions: list[dict[str, object]] = []
    for idx, entry in enumerate(coerce_pack_items(raw_contradictions)):
        if isinstance(entry, str):
            text_value = entry.strip()
            if not text_value:
                continue
            contradictions.append(
                {
                    "id": f"contradiction_{idx + 1}",
                    "statement_a": text_value,
                    "statement_b": "",
                    "explanation": "",
                    "evidence_ids": [],
                }
            )
            continue
        if not isinstance(entry, dict):
            continue
        item = to_dict(entry)
        statement_a = first_non_empty_text(
            item.get("statement_a"),
            item.get("claim_a"),
            item.get("point_a"),
        )
        statement_b = first_non_empty_text(
            item.get("statement_b"),
            item.get("claim_b"),
            item.get("point_b"),
        )
        explanation = first_non_empty_text(
            item.get("explanation"), item.get("context"), item.get("reason")
        )
        evidence_ids = [
            token
            for token in (
                coerce_pack_items(item.get("evidence_ids") or item.get("evidence_id"))
            )
            if isinstance(token, str) and token.strip()
        ]
        if not (statement_a or statement_b or explanation or evidence_ids):
            continue
        contradictions.append(
            {
                "id": first_non_empty_text(item.get("id"), f"contradiction_{idx + 1}"),
                "statement_a": statement_a,
                "statement_b": statement_b,
                "explanation": explanation,
                "evidence_ids": evidence_ids,
            }
        )
    return contradictions


CONTRADICTIONS_STRATEGY = build_list_pack_strategy(
    pack_name="contradictions",
    prompt_namespace_suffix="evidence_packs/contradictions",
    schema_name="contradictions_pack",
    root_key="contradictions",
    source_aliases=("conflicts",),
    normalize_items=normalize_contradictions,
)
