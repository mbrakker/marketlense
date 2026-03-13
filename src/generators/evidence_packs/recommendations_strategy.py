from __future__ import annotations

from src.generators.evidence_packs.base import (
    EvidencePackStrategy,
    PackNormalizationResult,
    build_list_pack_empty_payload,
)
from src.generators.evidence_packs.common import (
    coerce_pack_items,
    first_non_empty_text,
    to_dict,
)


def build_empty_payload(reason: str) -> dict[str, object]:
    return build_list_pack_empty_payload(root_key="recommendations", reason=reason)


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
        wrapped = payload.get("recommendations")
        if wrapped is None:
            wrapped = payload.get("evidence_pack")
        if wrapped is None:
            wrapped = payload.get("evidencePack")
        if wrapped is not None:
            source = wrapped

    root = to_dict(source)
    normalized = build_empty_payload("")
    raw_recommendations = (
        root.get("recommendations") if isinstance(source, dict) else source
    )
    if raw_recommendations is None:
        raw_recommendations = root.get("actions")
    normalized["recommendations"] = normalize_recommendations(raw_recommendations)
    if cache_meta:
        normalized["_cache"] = cache_meta
    return PackNormalizationResult(payload=normalized, changed=normalized != payload)


RECOMMENDATIONS_STRATEGY = EvidencePackStrategy(
    pack_name="recommendations",
    prompt_namespace_suffix="evidence_packs/recommendations",
    schema_name="recommendations_pack",
    normalize_payload=normalize_payload,
    empty_payload=build_empty_payload,
)
