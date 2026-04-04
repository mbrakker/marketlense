from __future__ import annotations

from src.generators.evidence_packs.base import (
    build_list_pack_strategy,
)
from src.generators.evidence_packs.common import (
    coerce_confidence,
    coerce_pack_items,
    coerce_pages,
    extract_evidence_text,
    first_non_empty_text,
    to_dict,
)


def normalize_findings(raw_findings: object) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for idx, entry in enumerate(coerce_pack_items(raw_findings)):
        if isinstance(entry, str):
            text_value = entry.strip()
            if not text_value:
                continue
            normalized.append(
                {
                    "id": f"finding_{idx + 1}",
                    "text": text_value,
                    "evidence": "",
                    "confidence": "",
                    "pages": [],
                }
            )
            continue
        if not isinstance(entry, dict):
            continue
        item = to_dict(entry)
        text_value = first_non_empty_text(
            item.get("text"),
            item.get("summary"),
            item.get("finding"),
            item.get("claim"),
            item.get("title"),
        )
        evidence_value = first_non_empty_text(
            extract_evidence_text(item.get("evidence")),
            extract_evidence_text(item.get("supporting_evidence")),
            item.get("rationale"),
        )
        pages = coerce_pages(item.get("pages"))
        if not pages:
            pages = coerce_pages(item.get("page"))
        if not (text_value or evidence_value or pages):
            continue
        normalized.append(
            {
                "id": first_non_empty_text(item.get("id"), f"finding_{idx + 1}"),
                "text": text_value,
                "evidence": evidence_value,
                "confidence": coerce_confidence(item.get("confidence")),
                "pages": pages,
            }
        )
    return normalized


FINDINGS_STRATEGY = build_list_pack_strategy(
    pack_name="findings",
    prompt_namespace_suffix="evidence_packs/findings",
    schema_name="findings_pack",
    root_key="findings",
    source_aliases=("insights", "claims"),
    normalize_items=normalize_findings,
)
