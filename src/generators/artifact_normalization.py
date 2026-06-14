from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.contracts.config import AppSettings
from src.contracts.ingest import IngestSettings
from src.utils.coercion import stripped_string_value as _s
from src.utils.json_utils import dump_json_object as _dump_json

METRIC_FIELDS = (
    "value",
    "unit",
    "trend",
    "timeframe",
    "geography",
    "segment",
    "sample_size",
    "confidence",
)
INLINE_REFERENCE_TOKEN_RE = r"[A-Z]{1,4}-\d{1,4}"
INLINE_REFERENCE_GROUP_RE = re.compile(
    rf"[\(\[]\s*{INLINE_REFERENCE_TOKEN_RE}(?:\s*[/,;|]\s*{INLINE_REFERENCE_TOKEN_RE})*\s*[\)\]]"
)
EVIDENCE_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
QUOTE_ALIAS_RE = re.compile(r"^quote[-_]?(\d+)$", re.IGNORECASE)


def artifact_base_variables(
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> Dict[str, str]:
    return {
        "doc_map_json": _dump_json(doc_map or {}),
        "evidence_json": _dump_json(evidence_packs or {}),
    }


def normalize_artifact_source_status(
    source_status: Optional[Dict[str, Any]],
    settings: AppSettings | IngestSettings,
    *,
    has_density: bool,
    vector_store_id: Optional[str] = None,
) -> Dict[str, Any]:
    status = source_status.copy() if isinstance(source_status, dict) else {}
    status.setdefault("schema_version", "1.0")
    status.setdefault("text_density", 0.0)
    status.setdefault(
        "density_threshold",
        float(getattr(settings, "pdf_text_min_density", 0.0)) if has_density else 0.0,
    )
    status.setdefault("pages_sampled", 0)
    status.setdefault("char_count", 0)
    status.setdefault("not_available", False)
    status.setdefault("reason", "")
    status.setdefault("evidence_present", True)
    if vector_store_id:
        status["density_threshold"] = 0.0
        status["not_available"] = False
        status["reason"] = ""
    return status


def artifact_vector_store_enabled(
    *, settings: AppSettings | IngestSettings, vector_store_id: Optional[str]
) -> bool:
    return bool(vector_store_id) and bool(
        getattr(settings, "artifacts_use_vector_store", False)
    )


def artifact_retrieval_mode(use_vector_store: bool) -> str:
    return "vector_store" if use_vector_store else "chat_json"


def normalize_artifact_summary(value: Any) -> Dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    claim_map = data.get("claim_evidence_map")
    return {
        "tldr": _s(data.get("tldr")),
        "card_tldr_compact": _s(data.get("card_tldr_compact")),
        "executive_summary": strip_artifact_inline_reference_ids(
            _s(data.get("executive_summary"))
        ),
        "claim_evidence_map": _normalize_claims(claim_map),
    }


def normalize_artifact_insights(items: Any, *, prefix: str) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        metric_raw = _to_dict(item.get("metric"))
        metric = {key: _s(metric_raw.get(key, "")) for key in METRIC_FIELDS}
        pages_raw_obj = item.get("pages")
        pages_raw = pages_raw_obj if isinstance(pages_raw_obj, list) else []
        pages = [int(p) for p in pages_raw if isinstance(p, int)]
        evidence_id = _s(item.get("evidence_id"))
        score_val = item.get("score")
        insight: Dict[str, Any] = {
            "id": _s(item.get("id") or f"{prefix}_{idx + 1}"),
            "text": _s(item.get("text")),
            "evidence_id": evidence_id,
            "evidence": _s(item.get("evidence")),
            "evidence_spans": _normalize_evidence_spans(
                item.get("evidence_spans"), evidence_id=evidence_id
            ),
            "metric": metric,
            "pages": pages,
        }
        if isinstance(score_val, (int, float)):
            insight["score"] = float(score_val)
        normalized.append(insight)
    return normalized


def pad_artifact_insights(
    insights_final: List[Dict[str, Any]],
    insights_candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    padded = list(insights_final)[:5]
    idx = 0
    while len(padded) < 5 and insights_candidates:
        source = insights_candidates[idx % len(insights_candidates)]
        metric_raw = _to_dict(source.get("metric"))
        source_pages_raw = source.get("pages")
        source_pages = source_pages_raw if isinstance(source_pages_raw, list) else []
        source_score = source.get("score")
        padded.append(
            {
                "id": _s(source.get("id") or f"insight_{len(padded) + 1}"),
                "text": _s(source.get("text")),
                "evidence_id": _s(source.get("evidence_id")),
                "evidence": _s(source.get("evidence")),
                "metric": {key: _s(metric_raw.get(key, "")) for key in METRIC_FIELDS},
                "pages": [int(p) for p in source_pages if isinstance(p, int)],
                **(
                    {"score": float(source_score)}
                    if isinstance(source_score, (int, float))
                    else {}
                ),
            }
        )
        idx += 1
    while len(padded) < 5:
        padded.append(_empty_insight(len(padded) + 1))
    return padded


def normalize_artifact_quotes(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            continue
        page_val = item.get("page")
        page = page_val if isinstance(page_val, int) else 0
        evidence_id = _s(item.get("evidence_id"))
        quote = {
            "text": _s(item.get("text")),
            "speaker": _s(item.get("speaker") or "Unknown"),
            "citation": _s(item.get("citation")),
            "page": page,
            "evidence_id": evidence_id,
            "evidence_spans": _normalize_evidence_spans(
                item.get("evidence_spans"), evidence_id=evidence_id
            ),
        }
        if item.get("is_paraphrase") is True or item.get("paraphrase") is True:
            quote["is_paraphrase"] = True
        for key in ("style", "mode", "label"):
            value = _s(item.get(key)).strip()
            if value:
                quote[key] = value
        normalized.append(quote)
    return normalized


def strip_artifact_inline_reference_ids(text: str) -> str:
    cleaned = INLINE_REFERENCE_GROUP_RE.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"([(\[])\s+", r"\1", cleaned)
    cleaned = re.sub(r"\s+([)\]])", r"\1", cleaned)
    return cleaned.strip(" ,;:-")


def normalize_artifact_topics(value: Any) -> List[str]:
    topics = value if isinstance(value, list) else []
    normalized: List[str] = []
    seen = set()
    for item in topics:
        text = _s(item).strip()
        if not text:
            continue
        text_key = text.casefold()
        if text_key in seen:
            continue
        seen.add(text_key)
        normalized.append(text)
    return normalized[:5]


def normalize_artifact_toc_entries(value: Any) -> List[Dict[str, Any]]:
    entries = value if isinstance(value, list) else []
    normalized: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for idx, item in enumerate(entries):
        if not isinstance(item, dict):
            continue
        section_id = _s(item.get("section_id")).strip()
        section_title = _s(item.get("section_title")).strip()
        display_title = _s(item.get("display_title")).strip()
        summary = _s(item.get("summary"))
        key_points_raw = item.get("key_points")
        key_points = []
        if isinstance(key_points_raw, list):
            key_points = [
                _s(point).strip() for point in key_points_raw if _s(point).strip()
            ]
        pages_raw = item.get("pages")
        pages = (
            [int(page) for page in pages_raw if isinstance(page, int)]
            if isinstance(pages_raw, list)
            else []
        )
        order_raw = item.get("order")
        order = int(order_raw) if isinstance(order_raw, int) else idx + 1
        dedupe_key = (
            section_id.casefold() if section_id else "",
            display_title.casefold() if display_title else section_title.casefold(),
        )
        if dedupe_key in seen_keys and any(dedupe_key):
            continue
        if any(dedupe_key):
            seen_keys.add(dedupe_key)
        normalized.append(
            {
                "section_id": section_id,
                "section_title": section_title,
                "display_title": display_title,
                "summary": summary,
                "key_points": key_points,
                "pages": pages,
                "order": order,
            }
        )
    return normalized


def normalize_artifact_evidence_ids(
    *,
    summary: Dict[str, Any],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> Dict[str, int]:
    known_ids, alias_to_id = _collect_known_evidence_ids(
        doc_map=doc_map, evidence_packs=evidence_packs
    )
    normalized_count = 0
    cleared_count = 0
    checked_count = 0

    def _normalize_item(item: Any) -> None:
        nonlocal normalized_count, cleared_count, checked_count
        if not isinstance(item, dict):
            return
        original = _s(item.get("evidence_id")).strip()
        checked_count += 1
        normalized = _canonicalize_evidence_id(
            original, known_ids=known_ids, alias_to_id=alias_to_id
        )
        if normalized != original:
            normalized_count += 1
            if not normalized:
                cleared_count += 1
        item["evidence_id"] = normalized

    claim_map = summary.get("claim_evidence_map")
    if isinstance(claim_map, list):
        for claim in claim_map:
            _normalize_item(claim)
    for item in insights_candidates:
        _normalize_item(item)
    for item in insights_final:
        _normalize_item(item)
    for item in quotes_final:
        _normalize_item(item)

    return {
        "known_reference_count": len(known_ids),
        "checked_count": checked_count,
        "normalized_count": normalized_count,
        "cleared_count": cleared_count,
    }


def bind_artifact_evidence_spans(
    *,
    summary: Dict[str, Any],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> Dict[str, int]:
    span_index = _build_evidence_span_index(
        doc_map=doc_map, evidence_packs=evidence_packs
    )
    bound_count = 0
    unbound_count = 0
    pruned_claim_count = 0

    def _bind_item(item: Any, *, page_keys: tuple[str, ...]) -> None:
        nonlocal bound_count, unbound_count
        if not isinstance(item, dict):
            return
        evidence_id = _s(item.get("evidence_id")).strip()
        if not evidence_id:
            item["evidence_spans"] = []
            return
        existing = _normalize_evidence_spans(
            item.get("evidence_spans"), evidence_id=evidence_id
        )
        derived = [dict(span) for span in span_index.get(evidence_id.casefold(), [])]
        spans = existing or derived
        if not spans:
            fallback_pages: List[int] = []
            for key in page_keys:
                raw_pages = item.get(key)
                if isinstance(raw_pages, list):
                    fallback_pages.extend(
                        int(page)
                        for page in raw_pages
                        if isinstance(page, int) and page > 0
                    )
                elif isinstance(raw_pages, int) and raw_pages > 0:
                    fallback_pages.append(raw_pages)
            deduped_pages = list(dict.fromkeys(fallback_pages))
            if deduped_pages:
                spans = [
                    {
                        "evidence_id": evidence_id,
                        "source_pack": "artifact",
                        "page": page,
                        "text": _pick_first_non_empty_text(
                            item.get("evidence"),
                            item.get("citation"),
                            item.get("text"),
                        ),
                    }
                    for page in deduped_pages
                ]
        item["evidence_spans"] = spans
        if spans:
            bound_count += 1
        else:
            unbound_count += 1

    claim_map = summary.get("claim_evidence_map")
    if isinstance(claim_map, list):
        bound_claims: List[Dict[str, Any]] = []
        for claim in claim_map:
            if not isinstance(claim, dict):
                continue
            evidence_id = _s(claim.get("evidence_id")).strip()
            claim["evidence_spans"] = []
            if not evidence_id:
                unbound_count += 1
                pruned_claim_count += 1
                continue
            existing = _normalize_evidence_spans(
                claim.get("evidence_spans"), evidence_id=evidence_id
            )
            derived = [
                dict(span) for span in span_index.get(evidence_id.casefold(), [])
            ]
            spans = existing or derived
            if not spans:
                claim_pages = [
                    int(page)
                    for page in claim.get("pages") or []
                    if isinstance(page, int) and page > 0
                ]
                if claim_pages:
                    spans = [
                        {
                            "evidence_id": evidence_id,
                            "source_pack": "artifact",
                            "page": page,
                            "text": _pick_first_non_empty_text(
                                claim.get("evidence"), claim.get("claim")
                            ),
                        }
                        for page in list(dict.fromkeys(claim_pages))
                    ]
            claim["evidence_spans"] = spans
            if spans:
                bound_count += 1
                bound_claims.append(claim)
            else:
                unbound_count += 1
                pruned_claim_count += 1
        summary["claim_evidence_map"] = bound_claims

    for item in insights_candidates:
        _bind_item(item, page_keys=("pages",))
    for item in insights_final:
        _bind_item(item, page_keys=("pages",))
    for item in quotes_final:
        _bind_item(item, page_keys=("page",))

    return {
        "bound_count": bound_count,
        "unbound_count": unbound_count,
        "pruned_claim_count": pruned_claim_count,
        "indexed_reference_count": len(span_index),
    }


def normalize_expert_domain(categories: Optional[List[str]]) -> str:
    if not isinstance(categories, (list, tuple)):
        return "industry"
    normalized: List[str] = []
    seen: set[str] = set()
    for raw in categories:
        value = _s(raw).strip()
        if not value:
            continue
        value_key = value.casefold()
        if value_key in seen:
            continue
        seen.add(value_key)
        normalized.append(value)
        if len(normalized) == 3:
            break
    if not normalized:
        return "industry"
    return ", ".join(normalized)


def artifact_quote_candidates(evidence_packs: Dict[str, Any]) -> List[Any]:
    quote_candidates: list[Any] = []
    quote_pack = evidence_packs.get("quote_candidates")
    if isinstance(quote_pack, dict):
        quote_candidates = quote_pack.get("quote_candidates") or []
    elif isinstance(quote_pack, list):
        quote_candidates = quote_pack
    return quote_candidates


def _normalize_claims(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            continue
        pages_raw_obj = item.get("pages")
        pages_raw = pages_raw_obj if isinstance(pages_raw_obj, list) else []
        pages = [int(p) for p in pages_raw if isinstance(p, int)]
        evidence_id = _s(item.get("evidence_id"))
        normalized.append(
            {
                "claim": _s(item.get("claim")),
                "evidence_id": evidence_id,
                "evidence": _s(item.get("evidence")),
                "evidence_spans": _normalize_evidence_spans(
                    item.get("evidence_spans"), evidence_id=evidence_id
                ),
                "pages": pages,
            }
        )
    return normalized


def _empty_insight(idx: int) -> Dict[str, Any]:
    return {
        "id": f"insight_{idx}",
        "text": "",
        "evidence_id": "",
        "evidence": "",
        "metric": {key: "" for key in METRIC_FIELDS},
        "pages": [],
    }


def _collect_known_evidence_ids(
    *,
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> tuple[set[str], Dict[str, str]]:
    known_ids: set[str] = set()
    alias_to_id: Dict[str, str] = {}

    def _register(value: Any) -> None:
        evidence_id = _s(value).strip()
        if not evidence_id:
            return
        known_ids.add(evidence_id)
        alias_to_id.setdefault(evidence_id.lower(), evidence_id)

    if isinstance(evidence_packs, dict):
        for pack in evidence_packs.values():
            if not isinstance(pack, dict):
                continue
            for item_key in (
                "findings",
                "quote_candidates",
                "key_metrics",
                "risk_register",
                "recommendations",
            ):
                items = pack.get(item_key)
                if not isinstance(items, list):
                    continue
                for idx, item in enumerate(items, start=1):
                    if isinstance(item, dict):
                        quote_id = _s(item.get("id")).strip()
                        _register(quote_id)
                        if item_key == "quote_candidates" and quote_id:
                            alias_to_id.setdefault(f"quote_{idx}", quote_id)
                            alias_to_id.setdefault(f"quote-{idx}", quote_id)
                            alias_to_id.setdefault(f"quote{idx}", quote_id)

    if isinstance(doc_map, dict):
        for section in doc_map.get("sections") or []:
            if isinstance(section, dict):
                _register(section.get("id"))

    for evidence_id in list(known_ids):
        match = re.match(r"^q(\d+)$", evidence_id, flags=re.IGNORECASE)
        if not match:
            continue
        quote_num = match.group(1)
        alias_to_id.setdefault(f"quote_{quote_num}", evidence_id)
        alias_to_id.setdefault(f"quote-{quote_num}", evidence_id)
        alias_to_id.setdefault(f"quote{quote_num}", evidence_id)

    return known_ids, alias_to_id


def _extract_evidence_id_candidates(raw_evidence_id: Any) -> List[str]:
    raw = _s(raw_evidence_id).strip()
    if not raw:
        return []

    candidates: List[str] = [raw]
    split_candidates = re.split(r"[,;|/]", raw)
    if len(split_candidates) > 1:
        candidates.extend(split_candidates)
    if raw.startswith("[") and raw.endswith("]"):
        candidates.extend(EVIDENCE_TOKEN_RE.findall(raw))
    if " " in raw:
        candidates.extend(EVIDENCE_TOKEN_RE.findall(raw))

    normalized: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        token = _s(candidate).strip()
        token = token.strip("\"'`")
        token = token.strip("[](){}")
        token = token.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _canonicalize_evidence_id(
    evidence_id: Any,
    *,
    known_ids: set[str],
    alias_to_id: Dict[str, str],
) -> str:
    raw = _s(evidence_id).strip()
    if not raw:
        return ""
    for candidate in _extract_evidence_id_candidates(raw):
        if not candidate:
            continue
        canonical = alias_to_id.get(candidate.lower())
        if canonical:
            return canonical
        quote_alias = QUOTE_ALIAS_RE.match(candidate)
        if quote_alias:
            alias_candidate = f"quote_{quote_alias.group(1)}"
            canonical = alias_to_id.get(alias_candidate)
            if canonical:
                return canonical
        if candidate in known_ids:
            return candidate
    return ""


def _normalize_evidence_spans(
    raw_spans: Any,
    *,
    evidence_id: str,
) -> List[Dict[str, Any]]:
    if not isinstance(raw_spans, list):
        return []
    normalized: List[Dict[str, Any]] = []
    seen: set[tuple[object, ...]] = set()
    for raw_span in raw_spans:
        if not isinstance(raw_span, dict):
            continue
        span_evidence_id = _s(raw_span.get("evidence_id") or evidence_id).strip()
        if not span_evidence_id:
            continue
        page = raw_span.get("page")
        start_offset = raw_span.get("start_offset")
        end_offset = raw_span.get("end_offset")
        normalized_span: Dict[str, Any] = {
            "evidence_id": span_evidence_id,
            "source_pack": _s(raw_span.get("source_pack")),
        }
        if isinstance(raw_span.get("section_id"), str) and _s(
            raw_span.get("section_id")
        ):
            normalized_span["section_id"] = _s(raw_span.get("section_id"))
        if isinstance(page, int) and page > 0:
            normalized_span["page"] = page
        if isinstance(start_offset, int) and start_offset >= 0:
            normalized_span["start_offset"] = start_offset
        if isinstance(end_offset, int) and end_offset >= 0:
            normalized_span["end_offset"] = end_offset
        text_value = _pick_first_non_empty_text(
            raw_span.get("text"),
            raw_span.get("evidence"),
            raw_span.get("citation"),
        )
        if text_value:
            normalized_span["text"] = text_value
        dedupe_key = (
            normalized_span.get("evidence_id"),
            normalized_span.get("source_pack"),
            normalized_span.get("section_id"),
            normalized_span.get("page"),
            normalized_span.get("start_offset"),
            normalized_span.get("end_offset"),
            normalized_span.get("text"),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(normalized_span)
    return normalized


def _build_evidence_span_index(
    *,
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    index: Dict[str, List[Dict[str, Any]]] = {}

    def _register(
        *,
        evidence_id: Any,
        source_pack: str,
        pages: List[int] | None = None,
        text: Any = "",
        section_id: Any = "",
        start_offset: Any = None,
        end_offset: Any = None,
    ) -> None:
        normalized_evidence_id = _s(evidence_id).strip()
        if not normalized_evidence_id:
            return
        normalized_text = _s(text).strip()
        normalized_section_id = _s(section_id).strip()
        normalized_pages = [
            page for page in (pages or []) if isinstance(page, int) and page > 0
        ]
        spans: List[Dict[str, Any]] = []
        if normalized_pages:
            for page in list(dict.fromkeys(normalized_pages)):
                span: Dict[str, Any] = {
                    "evidence_id": normalized_evidence_id,
                    "source_pack": source_pack,
                    "page": page,
                }
                if normalized_section_id:
                    span["section_id"] = normalized_section_id
                if normalized_text:
                    span["text"] = normalized_text
                if isinstance(start_offset, int) and start_offset >= 0:
                    span["start_offset"] = start_offset
                if isinstance(end_offset, int) and end_offset >= 0:
                    span["end_offset"] = end_offset
                spans.append(span)
        else:
            span = {
                "evidence_id": normalized_evidence_id,
                "source_pack": source_pack,
            }
            if normalized_section_id:
                span["section_id"] = normalized_section_id
            if normalized_text:
                span["text"] = normalized_text
            if isinstance(start_offset, int) and start_offset >= 0:
                span["start_offset"] = start_offset
            if isinstance(end_offset, int) and end_offset >= 0:
                span["end_offset"] = end_offset
            spans.append(span)
        bucket = index.setdefault(normalized_evidence_id.casefold(), [])
        for span in spans:
            if span not in bucket:
                bucket.append(span)

    if isinstance(evidence_packs, dict):
        findings_pack = evidence_packs.get("findings")
        if isinstance(findings_pack, dict):
            for item in findings_pack.get("findings") or []:
                if not isinstance(item, dict):
                    continue
                _register(
                    evidence_id=item.get("id"),
                    source_pack="findings",
                    pages=_coerce_span_pages(item),
                    text=_pick_first_non_empty_text(
                        item.get("evidence"), item.get("text"), item.get("statement")
                    ),
                )
        quotes_pack = evidence_packs.get("quote_candidates")
        if isinstance(quotes_pack, dict):
            for item in quotes_pack.get("quote_candidates") or []:
                if not isinstance(item, dict):
                    continue
                pages = []
                page_value = item.get("page")
                if isinstance(page_value, int) and page_value > 0:
                    pages = [page_value]
                _register(
                    evidence_id=item.get("id"),
                    source_pack="quote_candidates",
                    pages=pages,
                    text=item.get("text"),
                    start_offset=item.get("start_offset"),
                    end_offset=item.get("end_offset"),
                )
        for pack_name, root_key, text_keys in (
            ("key_metrics", "key_metrics", ("metric", "value", "unit")),
            (
                "risk_register",
                "risk_register",
                ("risk", "impact", "likelihood", "mitigation"),
            ),
            ("recommendations", "recommendations", ("recommendation", "rationale")),
        ):
            pack = evidence_packs.get(pack_name)
            if not isinstance(pack, dict):
                continue
            for item in pack.get(root_key) or []:
                if not isinstance(item, dict):
                    continue
                _register(
                    evidence_id=item.get("id") or item.get("evidence_id"),
                    source_pack=pack_name,
                    pages=_coerce_span_pages(item),
                    text=" ".join(
                        value
                        for value in (_s(item.get(key)).strip() for key in text_keys)
                        if value
                    ),
                )
        contradictions_pack = evidence_packs.get("contradictions")
        if isinstance(contradictions_pack, dict):
            for item in contradictions_pack.get("contradictions") or []:
                if not isinstance(item, dict):
                    continue
                contradiction_text = " ".join(
                    value
                    for value in (
                        _s(item.get("statement_a")).strip(),
                        _s(item.get("statement_b")).strip(),
                        _s(item.get("explanation")).strip(),
                    )
                    if value
                )
                for evidence_id in item.get("evidence_ids") or []:
                    _register(
                        evidence_id=evidence_id,
                        source_pack="contradictions",
                        pages=_coerce_span_pages(item),
                        text=contradiction_text,
                    )

    if isinstance(doc_map, dict):
        for section in doc_map.get("sections") or []:
            if not isinstance(section, dict):
                continue
            _register(
                evidence_id=section.get("id"),
                source_pack="doc_map",
                pages=_coerce_span_pages(section),
                text=_pick_first_non_empty_text(
                    section.get("summary"), section.get("title"), section.get("heading")
                ),
                section_id=section.get("id"),
            )
    return index


def _coerce_span_pages(item: Dict[str, Any]) -> List[int]:
    pages: List[int] = []
    raw_pages = item.get("pages")
    if isinstance(raw_pages, list):
        pages.extend(
            int(page) for page in raw_pages if isinstance(page, int) and page > 0
        )
    raw_page = item.get("page")
    if isinstance(raw_page, int) and raw_page > 0:
        pages.append(int(raw_page))
    return list(dict.fromkeys(pages))


def _pick_first_non_empty_text(*values: Any) -> str:
    for value in values:
        text = _s(value).strip()
        if text:
            return text
    return ""


def _to_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}
