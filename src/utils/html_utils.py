from __future__ import annotations

import html
import re
from typing import Dict, List, Optional


_IMG_SRC_RX = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_TITLE_RX = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1_RX = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_BODY_RX = re.compile(r"<body[^>]*>(.*?)</body>", re.IGNORECASE | re.DOTALL)
_FILE_ID_RX = re.compile(r"Drive fileId:\s*([A-Za-z0-9_\-]+)", re.IGNORECASE)
_PREVIEW_BLOCK_RX = re.compile(r'<div class="preview".*?</div>', re.IGNORECASE | re.DOTALL)


def extract_image_sources(html_text: str) -> List[str]:
    return [m.group(1) for m in _IMG_SRC_RX.finditer(html_text)]


def replace_image_sources(html_text: str, mapping: Dict[str, str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        src = match.group(1)
        if src not in mapping:
            return match.group(0)
        return match.group(0).replace(src, mapping[src])

    return _IMG_SRC_RX.sub(_replace, html_text)


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
    m = _FILE_ID_RX.search(html_text)
    if m:
        return m.group(1)
    return None


def extract_preview_image(html_text: str) -> Optional[str]:
    m = _PREVIEW_BLOCK_RX.search(html_text)
    if not m:
        return None
    imgs = extract_image_sources(m.group(0))
    return imgs[0] if imgs else None


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value)
