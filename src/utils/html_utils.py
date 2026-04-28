from __future__ import annotations

import html
import re
from typing import Dict, List, Optional


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
_FILE_ID_TEXT_RX = re.compile(r"Drive fileId:\s*([A-Za-z0-9._-]+)", re.IGNORECASE)
_PREVIEW_BLOCK_RX = re.compile(
    r'<div class="preview".*?</div>', re.IGNORECASE | re.DOTALL
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


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value)
