from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Optional

from src.contracts.analytics_projection import (
    PROJECTION_SCHEMA_VERSION,
    PROJECTION_VERSION,
    ProjectionLineage,
)
from src.contracts.semantic_ids import EntityUid, PublisherId, ReportId

_SAFE_TOKEN_RX = re.compile(r"[^A-Za-z0-9._:-]+")

def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

def _clean_string_list(values: Iterable[Any]) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        item = _clean_text(value)
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned

def _clean_int_list(values: Iterable[Any]) -> list[int]:
    cleaned: list[int] = []
    for value in values or []:
        if isinstance(value, bool):
            continue
        try:
            item = int(value)
        except (TypeError, ValueError):
            continue
        if item not in cleaned:
            cleaned.append(item)
    return cleaned

def _hash_payload(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()

def _safe_token(value: str) -> str:
    cleaned = _SAFE_TOKEN_RX.sub("-", str(value or "").strip()).strip("-")
    return cleaned[:96] if cleaned else ""

def _uid(
    report_id: ReportId, entity_type: str, local_id: str, payload: Any
) -> EntityUid:
    token = _safe_token(local_id)
    if not token:
        token = _hash_payload(payload)[:16]
    return EntityUid(f"{report_id}:{entity_type}:{token}")

def _publisher_id(publisher: str) -> Optional[PublisherId]:
    token = _safe_token(publisher.lower())
    if not token:
        return None
    return PublisherId(f"publisher:{token}")

def _lineage(
    *,
    source_pack: str,
    source_ref: str,
    generated_at_utc: str,
    analysis_run_id: str,
    model: str = "",
) -> ProjectionLineage:
    return ProjectionLineage(
        schema_version=PROJECTION_SCHEMA_VERSION,
        projection_version=PROJECTION_VERSION,
        source_pack=source_pack,
        source_ref=source_ref,
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
        model=model,
    )

def _unwrap_doc_map(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload
    for key in ("doc_map", "docmap", "docMap"):
        wrapped = payload.get(key)
        if isinstance(wrapped, dict):
            candidate = wrapped
            break
    return candidate

def _source_pack_model(payload: dict[str, Any]) -> str:
    raw_cache = payload.get("_cache")
    cache: dict[str, Any] = raw_cache if isinstance(raw_cache, dict) else {}
    return _clean_text(payload.get("model") or cache.get("model"))
