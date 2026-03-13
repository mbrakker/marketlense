from __future__ import annotations

from src.generators.evidence_packs.base import (
    EvidencePackStrategy,
    PackNormalizationResult,
    build_list_pack_empty_payload,
)
from src.generators.evidence_packs.common import (
    coerce_pack_items,
    first_non_empty_text,
    text,
    to_dict,
)


def build_empty_payload(reason: str) -> dict[str, object]:
    return build_list_pack_empty_payload(root_key="limitations", reason=reason)


def normalize_limitations(raw_limitations: object) -> list[str]:
    limitations: list[str] = []
    for entry in coerce_pack_items(raw_limitations):
        if isinstance(entry, str):
            text_value = entry.strip()
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
            limitations.append(f"{description} Mitigation: {mitigation}")
            continue
        if description:
            limitations.append(description)
            continue
        if mitigation:
            limitations.append(f"Mitigation: {mitigation}")
    return limitations


def normalize_payload(
    payload: object, report_id: str, report_name: str
) -> PackNormalizationResult:
    del report_id, report_name
    cache_meta = None
    source = payload
    if isinstance(payload, dict):
        cache_meta = (
            payload.get("_cache") if isinstance(payload.get("_cache"), dict) else None
        )
        wrapped = payload.get("limitations")
        if wrapped is None:
            wrapped = payload.get("evidence_pack")
        if wrapped is None:
            wrapped = payload.get("evidencePack")
        if wrapped is not None:
            source = wrapped

    root = to_dict(source)
    normalized = build_empty_payload("")
    raw_limitations = root.get("limitations") if isinstance(source, dict) else source
    if raw_limitations is None:
        raw_limitations = root.get("risks")
    if raw_limitations is None:
        raw_limitations = root.get("challenges")
    normalized["limitations"] = normalize_limitations(raw_limitations)
    if cache_meta:
        normalized["_cache"] = cache_meta
    return PackNormalizationResult(payload=normalized, changed=normalized != payload)


LIMITATIONS_STRATEGY = EvidencePackStrategy(
    pack_name="limitations",
    prompt_namespace_suffix="evidence_packs/limitations",
    schema_name="limitations_pack",
    normalize_payload=normalize_payload,
    empty_payload=build_empty_payload,
)
