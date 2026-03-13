from __future__ import annotations

from src.generators.evidence_packs.base import (
    EvidencePackStrategy,
    PackNormalizationResult,
    build_scalar_pack_empty_payload,
)
from src.generators.evidence_packs.common import text, to_dict


def build_empty_payload(reason: str) -> dict[str, object]:
    return build_scalar_pack_empty_payload(
        root_key="scope", default_value="", reason=reason
    )


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
        wrapped = payload.get("scope")
        if wrapped is None:
            wrapped = payload.get("evidence_pack")
        if wrapped is None:
            wrapped = payload.get("evidencePack")
        if wrapped is not None:
            source = wrapped

    root = to_dict(source)
    normalized = build_empty_payload("")
    scope_value = root.get("scope") if isinstance(source, dict) else source
    if scope_value is None:
        scope_value = ""
    if isinstance(scope_value, (str, dict)):
        normalized["scope"] = scope_value
    else:
        normalized["scope"] = text(scope_value)
    if cache_meta:
        normalized["_cache"] = cache_meta
    return PackNormalizationResult(payload=normalized, changed=normalized != payload)


SCOPE_STRATEGY = EvidencePackStrategy(
    pack_name="scope",
    prompt_namespace_suffix="evidence_packs/scope",
    schema_name="scope_pack",
    normalize_payload=normalize_payload,
    empty_payload=build_empty_payload,
)
