from __future__ import annotations

from src.generators.evidence_packs.base import (
    EvidencePackStrategy,
    PackNormalizationResult,
    build_list_pack_empty_payload,
)
from src.generators.evidence_packs.common import (
    coerce_confidence,
    coerce_pack_items,
    coerce_pages,
    extract_evidence_text,
    first_non_empty_text,
    to_dict,
)


def build_empty_payload(reason: str) -> dict[str, object]:
    return build_list_pack_empty_payload(root_key="findings", reason=reason)


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
        wrapped = payload.get("findings")
        if wrapped is None:
            wrapped = payload.get("evidence_pack")
        if wrapped is None:
            wrapped = payload.get("evidencePack")
        if wrapped is not None:
            source = wrapped

    root = to_dict(source)
    normalized = build_empty_payload("")
    raw_findings = root.get("findings") if isinstance(source, dict) else source
    if raw_findings is None:
        raw_findings = root.get("insights")
    if raw_findings is None:
        raw_findings = root.get("claims")
    normalized["findings"] = normalize_findings(raw_findings)
    if cache_meta:
        normalized["_cache"] = cache_meta
    return PackNormalizationResult(payload=normalized, changed=normalized != payload)


FINDINGS_STRATEGY = EvidencePackStrategy(
    pack_name="findings",
    prompt_namespace_suffix="evidence_packs/findings",
    schema_name="findings_pack",
    normalize_payload=normalize_payload,
    empty_payload=build_empty_payload,
)
