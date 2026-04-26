from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.contracts.config import AppSettings
from src.contracts.ingest import IngestSettings
from src.utils.json_utils import safe_json_dumps

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
        normalized.append(
            {
                "text": _s(item.get("text")),
                "speaker": _s(item.get("speaker") or "Unknown"),
                "citation": _s(item.get("citation")),
                "page": page,
                "evidence_id": evidence_id,
            }
        )
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


def _dump_json(data: Any) -> str:
    return safe_json_dumps(data, ensure_ascii=False, fallback="{}")


def _s(value: Any) -> str:
    return str(value or "").strip()


def _to_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}
