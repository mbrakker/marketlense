from __future__ import annotations

from typing import Optional

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
    return build_list_pack_empty_payload(root_key="quote_candidates", reason=reason)


def normalize_quote_candidates(raw_quotes: object) -> list[dict[str, object]]:
    quotes: list[dict[str, object]] = []
    for idx, entry in enumerate(coerce_pack_items(raw_quotes)):
        if isinstance(entry, str):
            text_value = entry.strip()
            if text_value:
                quotes.append(
                    {
                        "id": f"quote_{idx + 1}",
                        "text": text_value,
                        "source": "",
                        "page": None,
                    }
                )
            continue
        if not isinstance(entry, dict):
            continue
        item = to_dict(entry)
        text_value = first_non_empty_text(
            item.get("text"),
            item.get("quote"),
            item.get("snippet"),
            item.get("excerpt"),
            item.get("content"),
        )
        if not text_value:
            continue
        source_value = first_non_empty_text(
            item.get("source"),
            item.get("citation"),
            item.get("speaker"),
            item.get("author"),
            item.get("evidence_id"),
        )
        pages = coerce_pages(item.get("page"))
        if not pages:
            pages = coerce_pages(item.get("pages"))
        page_value: Optional[int] = pages[0] if pages else None
        quotes.append(
            {
                "id": first_non_empty_text(
                    item.get("id"), item.get("evidence_id"), f"quote_{idx + 1}"
                ),
                "text": text_value,
                "source": source_value,
                "page": page_value,
            }
        )
    return quotes


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
        wrapped = payload.get("quote_candidates")
        if wrapped is None:
            wrapped = payload.get("evidence_pack")
        if wrapped is None:
            wrapped = payload.get("evidencePack")
        if wrapped is not None:
            source = wrapped

    root = to_dict(source)
    normalized = build_empty_payload("")
    raw_quotes = root.get("quote_candidates") if isinstance(source, dict) else source
    if raw_quotes is None:
        raw_quotes = root.get("quotes")
    if raw_quotes is None:
        raw_quotes = root.get("quoteCandidates")
    normalized["quote_candidates"] = normalize_quote_candidates(raw_quotes)
    if cache_meta:
        normalized["_cache"] = cache_meta
    return PackNormalizationResult(payload=normalized, changed=normalized != payload)


QUOTE_CANDIDATES_STRATEGY = EvidencePackStrategy(
    pack_name="quote_candidates",
    prompt_namespace_suffix="evidence_packs/quote_candidates",
    schema_name="quote_candidates_pack",
    normalize_payload=normalize_payload,
    empty_payload=build_empty_payload,
)
