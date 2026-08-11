from __future__ import annotations

import re

from src.utils.slugify import slugify


def text(value: object) -> str:
    if isinstance(value, dict):
        for key in ("text", "value", "title", "name", "summary", "brief", "label"):
            candidate = value.get(key)
            if candidate is None:
                continue
            token = str(candidate).strip()
            if token:
                return token
        return ""
    if value is None:
        return ""
    return str(value).strip()


def first_non_empty_text(*values: object) -> str:
    for value in values:
        candidate = text(value)
        if candidate:
            return candidate
    return ""


def normalize_report_name(report_name: str) -> str:
    token = text(report_name).replace("\\", "/").split("/")[-1]
    token = re.sub(r"\.pdf$", "", token, flags=re.IGNORECASE).strip()
    token = re.sub(r"[_-]?acig$", "", token, flags=re.IGNORECASE).strip()
    token = re.sub(r"\s+", " ", token)
    return token


def clean_publisher_token(raw_value: object) -> str:
    token = text(raw_value)
    if not token:
        return ""
    token = re.sub(r"\b(?:19|20)\d{2}\b.*$", "", token).strip()
    token = token.strip(" -_—–|,:;")
    token = re.sub(r"\s+", " ", token)
    if not token or re.fullmatch(r"\d+", token):
        return ""
    return token


def derive_publisher_from_document_title(document_title: object) -> str:
    title = text(document_title)
    if not title:
        return ""
    parts = re.split(r"\s+[—–-]\s+", title)
    if len(parts) < 2:
        return ""
    return clean_publisher_token(parts[-1])


def derive_publisher_from_report_name(report_name: str) -> str:
    normalized_name = normalize_report_name(report_name)
    if not normalized_name:
        return ""
    for separator in (" - ", " — ", " – "):
        if separator in normalized_name:
            head, _ = normalized_name.split(separator, 1)
            candidate = clean_publisher_token(head)
            if candidate:
                return candidate
    return ""


def derive_publisher_from_document_text(document_text: object) -> str:
    """Return a high-confidence publisher named in report branding text."""
    value = text(document_text)
    if not value:
        return ""
    copyright_match = re.search(
        r"(?:©|\bcopyright\b)\s*"
        r"([A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3})",
        value,
        flags=re.IGNORECASE,
    )
    if copyright_match:
        candidate = clean_publisher_token(copyright_match.group(1))
        if candidate:
            return candidate
    possessive_match = re.search(r"\b([A-Z]{2,10})[’']s\b", value)
    return clean_publisher_token(possessive_match.group(1)) if possessive_match else ""


def coerce_pages(value: object) -> list[int]:
    items = value if isinstance(value, list) else [value]
    pages: list[int] = []
    seen: set[int] = set()
    for item in items:
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            page_num = int(item)
            if page_num > 0 and page_num not in seen:
                seen.add(page_num)
                pages.append(page_num)
            continue
        tokenized = text(item).replace(";", ",").replace("|", ",")
        for token in tokenized.split(","):
            token_text = token.strip()
            if not token_text or not token_text.isdigit():
                continue
            page_num = int(token_text)
            if page_num > 0 and page_num not in seen:
                seen.add(page_num)
                pages.append(page_num)
    return pages


def coerce_text_list(value: object) -> list[str]:
    items = value if isinstance(value, list) else [value]
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        token = ""
        if isinstance(item, dict):
            token = first_non_empty_text(
                item.get("text"),
                item.get("point"),
                item.get("title"),
                item.get("label"),
                item.get("name"),
                item.get("summary"),
            )
        else:
            token = text(item)
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def coerce_pack_items(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def to_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def extract_evidence_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict):
                candidate = first_non_empty_text(
                    item.get("snippet"),
                    item.get("text"),
                    item.get("quote"),
                    item.get("evidence"),
                    item.get("description"),
                )
                if candidate:
                    return candidate
        return ""
    if isinstance(value, dict):
        return first_non_empty_text(
            value.get("snippet"),
            value.get("text"),
            value.get("quote"),
            value.get("evidence"),
            value.get("description"),
        )
    return ""


def coerce_confidence(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return text(value)


def build_section_id(title: str, *, index: int) -> str:
    slug = slugify(title) if title else ""
    return slug or f"section_{index}"
