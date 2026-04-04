from __future__ import annotations

from src.generators.evidence_packs.base import (
    build_list_pack_strategy,
)
from src.generators.evidence_packs.common import (
    coerce_pack_items,
    coerce_pages,
    first_non_empty_text,
    to_dict,
)
def normalize_key_metrics(raw_metrics: object) -> list[dict[str, object]]:
    metrics: list[dict[str, object]] = []
    for idx, entry in enumerate(coerce_pack_items(raw_metrics)):
        if isinstance(entry, str):
            text_value = entry.strip()
            if not text_value:
                continue
            metrics.append(
                {
                    "id": f"metric_{idx + 1}",
                    "metric": text_value,
                    "value": "",
                    "unit": "",
                    "evidence_id": "",
                    "pages": [],
                }
            )
            continue
        if not isinstance(entry, dict):
            continue
        item = to_dict(entry)
        metric = first_non_empty_text(
            item.get("metric"),
            item.get("name"),
            item.get("label"),
            item.get("title"),
        )
        value = first_non_empty_text(
            item.get("value"), item.get("amount"), item.get("measure")
        )
        unit = first_non_empty_text(item.get("unit"), item.get("units"))
        evidence_id = first_non_empty_text(
            item.get("evidence_id"),
            item.get("finding_id"),
            item.get("reference_id"),
        )
        pages = coerce_pages(item.get("pages")) or coerce_pages(item.get("page"))
        if not (metric or value or evidence_id or pages):
            continue
        metrics.append(
            {
                "id": first_non_empty_text(item.get("id"), f"metric_{idx + 1}"),
                "metric": metric,
                "value": value,
                "unit": unit,
                "evidence_id": evidence_id,
                "pages": pages,
            }
        )
    return metrics


KEY_METRICS_STRATEGY = build_list_pack_strategy(
    pack_name="key_metrics",
    prompt_namespace_suffix="evidence_packs/key_metrics",
    schema_name="key_metrics_pack",
    root_key="key_metrics",
    source_aliases=("metrics",),
    normalize_items=normalize_key_metrics,
)
