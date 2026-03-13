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
    return build_list_pack_empty_payload(root_key="contradictions", reason=reason)


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
        wrapped = payload.get("contradictions")
        if wrapped is None:
            wrapped = payload.get("evidence_pack")
        if wrapped is None:
            wrapped = payload.get("evidencePack")
        if wrapped is not None:
            source = wrapped

    root = to_dict(source)
    normalized = build_empty_payload("")
    raw_contradictions = (
        root.get("contradictions") if isinstance(source, dict) else source
    )
    if raw_contradictions is None:
        raw_contradictions = root.get("conflicts")
    normalized["contradictions"] = normalize_contradictions(raw_contradictions)
    if cache_meta:
        normalized["_cache"] = cache_meta
    return PackNormalizationResult(payload=normalized, changed=normalized != payload)


CONTRADICTIONS_STRATEGY = EvidencePackStrategy(
    pack_name="contradictions",
    prompt_namespace_suffix="evidence_packs/contradictions",
    schema_name="contradictions_pack",
    normalize_payload=normalize_payload,
    empty_payload=build_empty_payload,
)
