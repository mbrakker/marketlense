from __future__ import annotations

from typing import Mapping
from urllib.parse import urlsplit

from src.services._publisher_inventory_service._discovery_activity.constants import (
    _GENERIC_CTA_LABELS,
)

def _is_generic_icon_label(lowered_title: str) -> bool:
    token = str(lowered_title or "").strip()
    return (
        token.startswith("02_elements/")
        or token.startswith(".st")
        or token in {"close", "arrowright", "arrowleft"}
    )

def _looks_like_human_report_title(title: str) -> bool:
    token = str(title or "").strip()
    if not token:
        return False
    if any(char in token for char in {"{", "}", "<", ">", "\\", "/", "_"}):
        return False
    alpha_count = sum(1 for char in token if char.isalpha())
    return alpha_count >= 3

def _is_generic_insights_hub_title(lowered_title: str) -> bool:
    if not lowered_title or not lowered_title.endswith(" insights"):
        return False
    stem = lowered_title[: -len(" insights")].strip()
    if not stem:
        return False
    return all(char.isalpha() or char in {" ", "&", "-"} for char in stem)

def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()

def _select_anchor_title(item: Mapping[str, object]) -> str:
    text = _normalize_text(str(item.get("text") or ""))
    heading_text = _normalize_text(str(item.get("heading_text") or ""))
    aria_label = _normalize_text(str(item.get("aria_label") or ""))
    title_attr = _normalize_text(str(item.get("title_attr") or ""))
    img_alt = _normalize_text(str(item.get("img_alt") or ""))
    context_text = _normalize_text(str(item.get("context_text") or ""))
    if heading_text:
        if not text or text.casefold() in _GENERIC_CTA_LABELS:
            return heading_text
        lowered_text = text.casefold()
        lowered_heading = heading_text.casefold()
        if lowered_heading == lowered_text:
            return heading_text
        if lowered_heading in lowered_text and len(text) >= len(heading_text) + 24:
            return heading_text
    if text and text.casefold() not in _GENERIC_CTA_LABELS:
        return text
    if aria_label and aria_label.casefold() not in _GENERIC_CTA_LABELS:
        return aria_label
    if title_attr and title_attr.casefold() not in _GENERIC_CTA_LABELS:
        return title_attr
    if img_alt and img_alt.casefold() not in _GENERIC_CTA_LABELS:
        return img_alt
    context_title = _card_context_title(context_text)
    if context_title:
        return context_title
    return heading_text or aria_label or title_attr or img_alt or text

def _card_context_title(context_text: str) -> str:
    normalized = _normalize_text(context_text)
    if not normalized:
        return ""
    lowered = normalized.casefold()
    for label in sorted(_GENERIC_CTA_LABELS, key=len, reverse=True):
        if lowered.endswith(label):
            normalized = normalized[: -len(label)].rstrip(" -:>|")
            lowered = normalized.casefold()
            break
    if len(normalized) <= 180:
        return normalized
    return normalized[:180].rsplit(" ", 1)[0].rstrip(" -:>|")

def _fallback_title_from_url(url: str) -> str:
    path = urlsplit(url).path.rsplit("/", 1)[-1]
    token = path.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").strip()
    return _normalize_text(token) or url
