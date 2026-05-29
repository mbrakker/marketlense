from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - script execution bootstrap
    sys.path.insert(0, str(REPO_ROOT))

from src.contracts.wordpress import WordPressPublisherProfileSeed

try:  # pragma: no cover - import path differs for direct script execution
    from .wp_rest_common import normalize_homepage, slugify
except ImportError:  # pragma: no cover - fallback for python script execution
    from wp_rest_common import normalize_homepage, slugify


_URL_PATTERN = re.compile(
    r"(?i)\b(?:https?://|www\.)[^\s,]+|(?<!@)\b[a-z0-9][a-z0-9.-]+\.[a-z]{2,}(?:/[^\s,]+)?"
)
_DATA_IMAGE_PATTERN = re.compile(
    r"^data:image/[a-z0-9.+-]+;base64,[a-z0-9+/=]+$",
    re.IGNORECASE,
)
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_ICON_SOURCE_URL_OVERRIDES = {
    "157290cc-00d3-80c8-9980-e347ba67fc62": "https://www.activate.com/assets/icon-light.png",
}


def normalize_text(value: str) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    compact = re.sub(r"(?<=[.!?])(?=[A-Z])", " ", compact)
    compact = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", compact)
    return compact.strip()


def extract_external_urls(value: str) -> list[str]:
    normalized = normalize_text(value)
    if normalized == "":
        return []

    seen: set[str] = set()
    urls: list[str] = []
    for match in _URL_PATTERN.finditer(normalized):
        candidate = match.group(0).rstrip(").,;")
        try:
            resolved = normalize_homepage(candidate)
        except RuntimeError:
            continue
        if resolved not in seen:
            seen.add(resolved)
            urls.append(resolved)
    return urls


def normalize_icon_source(value: str) -> str:
    icon = value.strip()
    if icon == "":
        return ""
    if _DATA_IMAGE_PATTERN.match(icon):
        return icon
    try:
        return normalize_homepage(icon)
    except RuntimeError:
        return icon


def resolve_icon_download_url(row: WordPressPublisherProfileSeed) -> str:
    override = _ICON_SOURCE_URL_OVERRIDES.get(row.notion_page_id)
    host = str(urlsplit(str(row.icon_source or "")).hostname or "").casefold()
    if override and host == "prod-files-secure.s3.us-west-2.amazonaws.com":
        return override
    return row.icon_source


def load_profile_rows(path: Path) -> list[WordPressPublisherProfileSeed]:
    if not path.exists():
        raise RuntimeError(f"Publisher profile file does not exist: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[WordPressPublisherProfileSeed] = []
    for index, item in enumerate(payload.get("publishers", [])):
        row = _build_profile_row(item=item, index=index)
        rows.append(row)

    if rows == []:
        raise RuntimeError(f"Publisher profile file contains no usable rows: {path}")

    return rows


def build_term_payload(row: WordPressPublisherProfileSeed) -> dict[str, object]:
    return {
        "name": row.name,
        "slug": row.slug,
        "description": row.self_presentation,
        "meta": {
            "ml_publisher_homepage": row.homepage,
            "ml_publisher_insights_url": row.insights_url,
            "ml_publisher_icon_source": row.icon_source,
            "ml_publisher_notion_page_id": row.notion_page_id,
            "ml_publisher_notion_page_url": row.notion_page_url,
        },
    }


def split_multiline_urls(value: str) -> list[str]:
    values = [line.strip() for line in value.splitlines()]
    return [line for line in values if line != ""]


def _build_profile_row(
    *, item: dict[str, object], index: int
) -> WordPressPublisherProfileSeed:
    name = normalize_text(str(item.get("name", "")))
    notion_page_id = normalize_text(str(item.get("notion_page_id", ""))).lower()
    notion_page_url = normalize_text(str(item.get("notion_page_url", "")))

    if name == "":
        raise RuntimeError(f"Publisher row {index} is missing a name")
    if notion_page_id == "" or _UUID_PATTERN.match(notion_page_id) is None:
        raise RuntimeError(f"Publisher row {index} has an invalid notion_page_id")
    if notion_page_url == "":
        raise RuntimeError(f"Publisher row {index} is missing a notion_page_url")

    homepage_urls = extract_external_urls(str(item.get("homepage", "")))
    insights_urls = extract_external_urls(str(item.get("insights_url", "")))
    self_presentation = normalize_text(str(item.get("self_presentation", "")))
    icon_source = normalize_icon_source(str(item.get("icon_source", "")))

    return WordPressPublisherProfileSeed(
        schema_version="1.0",
        notion_page_id=notion_page_id,
        notion_page_url=notion_page_url,
        name=name,
        slug=slugify(name),
        homepage=homepage_urls[0] if homepage_urls else "",
        self_presentation=self_presentation,
        insights_url="\n".join(_limit_urls(insights_urls, limit=3)),
        icon_source=icon_source,
    )


def _limit_urls(values: Iterable[str], *, limit: int) -> list[str]:
    output: list[str] = []
    for value in values:
        output.append(value)
        if len(output) >= limit:
            break
    return output
