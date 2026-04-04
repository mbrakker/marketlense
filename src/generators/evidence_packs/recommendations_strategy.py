from __future__ import annotations

from src.generators.evidence_packs.base import (
    build_list_pack_strategy,
)
from src.generators.evidence_packs.common import (
    coerce_pack_items,
    first_non_empty_text,
    to_dict,
)
def normalize_recommendations(
    raw_recommendations: object,
) -> list[dict[str, object]]:
    recommendations: list[dict[str, object]] = []
    for idx, entry in enumerate(coerce_pack_items(raw_recommendations)):
        if isinstance(entry, str):
            text_value = entry.strip()
            if not text_value:
                continue
            recommendations.append(
                {
                    "id": f"recommendation_{idx + 1}",
                    "recommendation": text_value,
                    "rationale": "",
                    "evidence_id": "",
                }
            )
            continue
        if not isinstance(entry, dict):
            continue
        item = to_dict(entry)
        recommendation = first_non_empty_text(
            item.get("recommendation"),
            item.get("action"),
            item.get("text"),
            item.get("title"),
        )
        rationale = first_non_empty_text(
            item.get("rationale"), item.get("reason"), item.get("evidence")
        )
        evidence_id = first_non_empty_text(
            item.get("evidence_id"),
            item.get("reference_id"),
            item.get("finding_id"),
        )
        if not (recommendation or rationale or evidence_id):
            continue
        recommendations.append(
            {
                "id": first_non_empty_text(item.get("id"), f"recommendation_{idx + 1}"),
                "recommendation": recommendation,
                "rationale": rationale,
                "evidence_id": evidence_id,
            }
        )
    return recommendations


RECOMMENDATIONS_STRATEGY = build_list_pack_strategy(
    pack_name="recommendations",
    prompt_namespace_suffix="evidence_packs/recommendations",
    schema_name="recommendations_pack",
    root_key="recommendations",
    source_aliases=("actions",),
    normalize_items=normalize_recommendations,
)
