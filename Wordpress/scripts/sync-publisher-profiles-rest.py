#!/usr/bin/env python3
from __future__ import annotations

import base64
import os
from pathlib import Path

import requests

from publisher_profiles_common import (
    build_term_payload,
    load_profile_rows,
    resolve_icon_download_url,
)
from wp_rest_common import WordPressRestClient, fail, load_rest_settings_from_env


PROFILE_CONFIG_ENV = "PUBLISHER_PROFILE_PATH"
DEFAULT_CONFIG_NAME = "publisher-profiles.json"
PUBLISHER_TAXONOMY = "ml_publisher"
REQUIRED_PROFILE_META_KEYS = {
    "ml_publisher_homepage",
    "ml_publisher_insights_url",
    "ml_publisher_icon_source",
    "ml_publisher_notion_page_id",
    "ml_publisher_notion_page_url",
}
ICON_FETCH_HEADERS = {"User-Agent": "Market Lense Publisher Sync/1.0"}
MAX_ICON_BYTES = 2_000_000


def ensure_term(client: WordPressRestClient, *, slug: str, name: str) -> int:
    existing = client.get(
        f"wp/v2/{PUBLISHER_TAXONOMY}",
        params={
            "slug": slug,
            "per_page": 1,
            "context": "edit",
            "_fields": "id,name,slug",
        },
    )
    if isinstance(existing, list) and existing:
        term_id = int(existing[0].get("id", 0))
        if term_id > 0:
            print(f"Using publisher term: {name} -> ID {term_id}")
            return term_id

    by_name = client.get(
        f"wp/v2/{PUBLISHER_TAXONOMY}",
        params={
            "search": name,
            "per_page": 100,
            "context": "edit",
            "_fields": "id,name,slug",
        },
    )
    if isinstance(by_name, list):
        wanted = name.casefold()
        for item in by_name:
            if str(item.get("name", "")).strip().casefold() == wanted:
                term_id = int(item.get("id", 0))
                if term_id > 0:
                    print(f"Using publisher term: {name} -> ID {term_id}")
                    return term_id

    created = client.post(
        f"wp/v2/{PUBLISHER_TAXONOMY}",
        payload={"name": name, "slug": slug},
    )
    term_id = int(created.get("id", 0))
    if term_id <= 0:
        raise RuntimeError(f"Failed to create publisher term '{name}'")
    print(f"Created publisher term: {name} -> ID {term_id}")
    return term_id


def update_term_profile(
    client: WordPressRestClient, *, term_id: int, payload: dict[str, object], name: str
) -> None:
    updated = client.post(f"wp/v2/{PUBLISHER_TAXONOMY}/{term_id}", payload=payload)
    updated_id = int(updated.get("id", 0))
    if updated_id != term_id:
        raise RuntimeError(f"Failed to update publisher profile for '{name}'")
    print(f"Updated publisher profile: {name} -> ID {term_id}")


def main() -> None:
    script_root = Path(__file__).resolve().parent.parent
    config_path = Path(
        os.getenv(PROFILE_CONFIG_ENV, str(script_root / "config" / DEFAULT_CONFIG_NAME))
    )

    try:
        settings = load_rest_settings_from_env()
        client = WordPressRestClient(settings)
        ensure_publisher_taxonomy_ready(client)
        assert_publisher_profile_meta_ready(client)
        rows = load_profile_rows(config_path)
        for row in rows:
            term_id = ensure_term(client, slug=row.slug, name=row.name)
            payload = build_term_payload(row)
            payload["meta"]["ml_publisher_icon_source"] = inline_icon_source(
                raw_icon_source=row.icon_source,
                download_url=resolve_icon_download_url(row),
                publisher_name=row.name,
            )
            update_term_profile(
                client,
                term_id=term_id,
                payload=payload,
                name=row.name,
            )
    except RuntimeError as exc:
        fail(str(exc))

    print("Publisher profile sync complete.")


def ensure_publisher_taxonomy_ready(client: WordPressRestClient) -> None:
    try:
        client.get(f"wp/v2/taxonomies/{PUBLISHER_TAXONOMY}")
        return
    except RuntimeError as exc:
        message = str(exc)
        if "rest_taxonomy_invalid" not in message and "404" not in message:
            raise

    plugin_slug = resolve_marketlense_plugin_slug(client)
    if plugin_slug is None:
        raise RuntimeError(
            "Taxonomy 'ml_publisher' is unavailable and plugin 'marketlense-core' "
            "was not found via REST. Upload or activate marketlense-core first."
        )

    plugin = client.get(f"wp/v2/plugins/{plugin_slug}")
    status = str(plugin.get("status", "")).strip().lower()
    if status != "active":
        updated = client.post(
            f"wp/v2/plugins/{plugin_slug}",
            payload={"status": "active"},
        )
        if str(updated.get("status", "")).strip().lower() != "active":
            raise RuntimeError(
                "Failed to activate marketlense-core plugin via REST. "
                "Activate it in WP Admin and rerun the sync."
            )
        print(f"Activated plugin: {plugin_slug}")

    client.get(f"wp/v2/taxonomies/{PUBLISHER_TAXONOMY}")


def resolve_marketlense_plugin_slug(client: WordPressRestClient) -> str | None:
    payload = client.get("wp/v2/plugins", params={"search": "marketlense-core"})
    if not isinstance(payload, list):
        return None
    for item in payload:
        slug = str(item.get("plugin", "")).strip()
        if slug.startswith("marketlense-core/"):
            return slug
    return None


def assert_publisher_profile_meta_ready(client: WordPressRestClient) -> None:
    sample_terms = client.get(
        f"wp/v2/{PUBLISHER_TAXONOMY}",
        params={"per_page": 1, "context": "edit", "_fields": "id,meta"},
    )
    if not isinstance(sample_terms, list) or sample_terms == []:
        return

    meta = sample_terms[0].get("meta") if isinstance(sample_terms[0], dict) else {}
    if not isinstance(meta, dict):
        meta = {}

    missing_keys = sorted(REQUIRED_PROFILE_META_KEYS.difference(meta.keys()))
    if missing_keys:
        raise RuntimeError(
            "Configured WordPress site is missing publisher profile REST meta keys: "
            + ", ".join(missing_keys)
            + ". Deploy the updated marketlense-core plugin before running profile sync."
        )


def inline_icon_source(
    *, raw_icon_source: str, download_url: str, publisher_name: str
) -> str:
    if raw_icon_source == "" or raw_icon_source.startswith("data:image/"):
        return raw_icon_source
    if not download_url.startswith(("http://", "https://")):
        return raw_icon_source

    try:
        response = requests.get(
            download_url,
            headers=ICON_FETCH_HEADERS,
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException:
        print(
            f"Keeping remote icon source for {publisher_name}: "
            f"could not fetch {download_url}"
        )
        return raw_icon_source

    content_type = str(response.headers.get("content-type", "")).split(";", 1)[0].lower()
    if not content_type.startswith("image/"):
        print(
            f"Keeping remote icon source for {publisher_name}: "
            f"unexpected content type {content_type or 'unknown'}"
        )
        return raw_icon_source

    if len(response.content) > MAX_ICON_BYTES:
        print(
            f"Keeping remote icon source for {publisher_name}: "
            f"image payload exceeds {MAX_ICON_BYTES} bytes"
        )
        return raw_icon_source

    encoded = base64.b64encode(response.content).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


if __name__ == "__main__":
    main()
