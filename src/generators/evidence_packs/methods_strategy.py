from __future__ import annotations

from src.generators.evidence_packs.base import (
    EvidencePackStrategy,
    PackNormalizationResult,
    build_list_pack_empty_payload,
)
from src.generators.evidence_packs.common import coerce_pack_items, text, to_dict


def build_empty_payload(reason: str) -> dict[str, object]:
    return build_list_pack_empty_payload(root_key="methods", reason=reason)


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
        wrapped = payload.get("methods")
        if wrapped is None:
            wrapped = payload.get("evidence_pack")
        if wrapped is None:
            wrapped = payload.get("evidencePack")
        if wrapped is not None:
            source = wrapped

    root = to_dict(source)
    normalized = build_empty_payload("")
    raw_methods = root.get("methods") if isinstance(source, dict) else source
    if raw_methods is None:
        raw_methods = root.get("methodology")
    if raw_methods is None:
        raw_methods = root.get("approach")
    normalized["methods"] = normalize_methods(raw_methods)
    if cache_meta:
        normalized["_cache"] = cache_meta
    return PackNormalizationResult(payload=normalized, changed=normalized != payload)


METHODS_STRATEGY = EvidencePackStrategy(
    pack_name="methods",
    prompt_namespace_suffix="evidence_packs/methods",
    schema_name="methods_pack",
    normalize_payload=normalize_payload,
    empty_payload=build_empty_payload,
)
