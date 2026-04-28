from __future__ import annotations

from typing import Optional

from src.generators.evidence_packs.base import (
    build_list_pack_strategy,
)
from src.generators.evidence_packs.common import (
    coerce_pack_items,
    coerce_pages,
    first_non_empty_text,
    to_dict,
)


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


QUOTE_CANDIDATES_STRATEGY = build_list_pack_strategy(
    pack_name="quote_candidates",
    prompt_namespace_suffix="evidence_packs/quote_candidates",
    schema_name="quote_candidates_pack",
    root_key="quote_candidates",
    source_aliases=("quotes", "quoteCandidates"),
    normalize_items=normalize_quote_candidates,
)
