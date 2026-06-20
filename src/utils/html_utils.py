from __future__ import annotations

import html
import json
import re
from typing import Dict, List, Optional

from src.contracts.publish import PublishEntityMetadata, PublishHtmlSnapshot


_IMG_SRC_RX = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_IMG_SRCSET_RX = re.compile(r'(<img[^>]+srcset=["\'])([^"\']+)(["\'])', re.IGNORECASE)
_IMG_SRCSET_OR_SIZES_ATTR_RX = re.compile(
    r'\s(?:srcset|sizes)=["\'][^"\']*["\']',
    re.IGNORECASE,
)
_TITLE_RX = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1_RX = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_BODY_RX = re.compile(r"<body[^>]*>(.*?)</body>", re.IGNORECASE | re.DOTALL)
_FILE_ID_META_RX = re.compile(
    r'<meta[^>]+name=["\']drive-file-id["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_FILE_ID_TEXT_RX = re.compile(r"Drive fileId:\s*([A-Za-z0-9._:-]+)", re.IGNORECASE)
_PREVIEW_BLOCK_RX = re.compile(
    r'<div class="preview".*?</div>', re.IGNORECASE | re.DOTALL
)
_PUBLISH_ENTITY_METADATA_RX = re.compile(
    r'<script\b[^>]*data-market-lense-publish-entity=["\']true["\'][^>]*>'
    r"(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_CROSS_REPORT_METADATA_RX = re.compile(
    r'<script\b[^>]*data-market-lense-cross-report-metadata=["\']true["\'][^>]*>'
    r"(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def extract_image_sources(html_text: str) -> List[str]:
    return [m.group(1) for m in _IMG_SRC_RX.finditer(html_text)]


def replace_image_sources(html_text: str, mapping: Dict[str, str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        src = match.group(1)
        if src not in mapping:
            return match.group(0)
        return match.group(0).replace(src, mapping[src])

    updated = _IMG_SRC_RX.sub(_replace, html_text)

    def _replace_srcset(match: re.Match[str]) -> str:
        prefix, value, suffix = match.groups()
        entries: list[str] = []
        for raw_entry in value.split(","):
            entry = raw_entry.strip()
            if not entry:
                continue
            parts = entry.split()
            if not parts:
                continue
            url = parts[0]
            mapped = mapping.get(url, url)
            if len(parts) > 1:
                entries.append(" ".join([mapped, *parts[1:]]))
            else:
                entries.append(mapped)
        if not entries:
            return match.group(0)
        return f"{prefix}{', '.join(entries)}{suffix}"

    return _IMG_SRCSET_RX.sub(_replace_srcset, updated)


def strip_image_srcset_and_sizes(html_text: str) -> str:
    def _strip_attrs(match: re.Match[str]) -> str:
        tag = match.group(0)
        stripped = _IMG_SRCSET_OR_SIZES_ATTR_RX.sub("", tag)
        return stripped

    return re.sub(r"<img\b[^>]*>", _strip_attrs, html_text, flags=re.IGNORECASE)


def extract_title(html_text: str) -> Optional[str]:
    for rx in (_H1_RX, _TITLE_RX):
        m = rx.search(html_text)
        if m:
            return html.unescape(_strip_tags(m.group(1))).strip() or None
    return None


def extract_body_html(html_text: str) -> str:
    m = _BODY_RX.search(html_text)
    if m:
        return m.group(1).strip()
    return html_text.strip()


def extract_file_id(html_text: str) -> Optional[str]:
    m_meta = _FILE_ID_META_RX.search(html_text)
    if m_meta:
        return m_meta.group(1)
    m_text = _FILE_ID_TEXT_RX.search(html_text)
    if m_text:
        return m_text.group(1)
    return None


def extract_preview_image(html_text: str) -> Optional[str]:
    m = _PREVIEW_BLOCK_RX.search(html_text)
    if not m:
        return None
    imgs = extract_image_sources(m.group(0))
    return imgs[0] if imgs else None


def publish_entity_metadata_script(metadata: PublishEntityMetadata) -> str:
    payload = {
        "schema_version": metadata.schema_version,
        "entity_type": metadata.entity_type,
        "source_artifact_id": metadata.source_artifact_id,
        "canonical_route_intent": metadata.canonical_route_intent,
        "publish_eligible": metadata.publish_eligible,
    }
    metadata_json = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        '<script type="application/json" '
        'data-market-lense-publish-entity="true">'
        f"{html.escape(metadata_json, quote=False)}</script>"
    )


def extract_publish_entity_metadata(html_text: str) -> Optional[PublishEntityMetadata]:
    m = _PUBLISH_ENTITY_METADATA_RX.search(html_text)
    if not m:
        return None
    try:
        payload = json.loads(html.unescape(m.group(1)).strip())
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        schema_version = str(payload.get("schema_version") or "").strip()
        entity_type = str(payload.get("entity_type") or "").strip()
        source_artifact_id = str(payload.get("source_artifact_id") or "").strip()
        canonical_route_intent = str(
            payload.get("canonical_route_intent") or ""
        ).strip()
        publish_eligible = bool(payload["publish_eligible"])
    except KeyError:
        return None
    if not (
        schema_version and entity_type and source_artifact_id and canonical_route_intent
    ):
        return None
    return PublishEntityMetadata(
        schema_version=schema_version,
        entity_type=entity_type,
        source_artifact_id=source_artifact_id,
        canonical_route_intent=canonical_route_intent,
        publish_eligible=publish_eligible,
    )


def extract_briefing_card(html_text: str) -> Dict[str, object]:
    return _extract_cross_report_card(html_text, "briefing_card")


def extract_signal_card(html_text: str) -> Dict[str, object]:
    return _extract_cross_report_card(html_text, "signal_card")


def _extract_cross_report_card(html_text: str, field_name: str) -> Dict[str, object]:
    match = _CROSS_REPORT_METADATA_RX.search(html_text)
    if not match:
        return {}
    try:
        payload = json.loads(html.unescape(match.group(1)).strip())
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    card = payload.get(field_name)
    return dict(card) if isinstance(card, dict) else {}


def ensure_publish_entity_metadata_html(
    html_text: str, metadata: PublishEntityMetadata
) -> str:
    if extract_publish_entity_metadata(html_text) is not None:
        return html_text
    script = publish_entity_metadata_script(metadata)
    head_close = re.search(r"</head\s*>", html_text, re.IGNORECASE)
    if head_close:
        return (
            html_text[: head_close.start()] + script + html_text[head_close.start() :]
        )
    body_open = re.search(r"<body\b[^>]*>", html_text, re.IGNORECASE)
    if body_open:
        return html_text[: body_open.end()] + script + html_text[body_open.end() :]
    return script + html_text


def build_publish_html_snapshot(html_text: str) -> PublishHtmlSnapshot:
    return PublishHtmlSnapshot(
        schema_version="1.0",
        html_text=html_text,
        file_id=extract_file_id(html_text),
        title=extract_title(html_text),
        body_html=extract_body_html(html_text),
        image_sources=extract_image_sources(html_text),
        preview_image_src=extract_preview_image(html_text),
        entity_metadata=extract_publish_entity_metadata(html_text),
        briefing_card=extract_briefing_card(html_text),
        signal_card=extract_signal_card(html_text),
    )


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value)
