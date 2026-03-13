from __future__ import annotations

from src.generators.evidence_packs.base import (
    EvidencePackStrategy,
    PackNormalizationResult,
    build_list_pack_empty_payload,
)
from src.generators.evidence_packs.common import (
    coerce_pack_items,
    coerce_pages,
    first_non_empty_text,
    to_dict,
)


def build_empty_payload(reason: str) -> dict[str, object]:
    return build_list_pack_empty_payload(root_key="key_metrics", reason=reason)


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
        wrapped = payload.get("key_metrics")
        if wrapped is None:
            wrapped = payload.get("evidence_pack")
        if wrapped is None:
            wrapped = payload.get("evidencePack")
        if wrapped is not None:
            source = wrapped

    root = to_dict(source)
    normalized = build_empty_payload("")
    raw_metrics = root.get("key_metrics") if isinstance(source, dict) else source
    if raw_metrics is None:
        raw_metrics = root.get("metrics")
    normalized["key_metrics"] = normalize_key_metrics(raw_metrics)
    if cache_meta:
        normalized["_cache"] = cache_meta
    return PackNormalizationResult(payload=normalized, changed=normalized != payload)


KEY_METRICS_STRATEGY = EvidencePackStrategy(
    pack_name="key_metrics",
    prompt_namespace_suffix="evidence_packs/key_metrics",
    schema_name="key_metrics_pack",
    normalize_payload=normalize_payload,
    empty_payload=build_empty_payload,
)
