#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from ..wp_rest_common import (
    WordPressRestClient,
    fail,
    load_rest_settings_from_env,
    normalize_homepage,
    slugify,
)


PUBLISHER_META_KEY = "ml_publisher_homepage"


@dataclass(frozen=True)
class PublisherSeedRow:
    schema_version: str
    name: str
    homepage: str
    slug: str


def load_seed_rows(path: Path) -> List[PublisherSeedRow]:
    if not path.exists():
        raise RuntimeError(f"Publisher mapping file does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: List[PublisherSeedRow] = []
    for item in payload.get("publishers", []):
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        homepage = normalize_homepage(str(item.get("homepage", "")).strip())
        rows.append(
            PublisherSeedRow(
                schema_version="1.0",
                name=name,
                homepage=homepage,
                slug=slugify(name),
            )
        )
    return rows


def ensure_term(client: WordPressRestClient, row: PublisherSeedRow) -> int:
    existing = client.get(
        "wp/v2/ml_publisher",
        params={
            "slug": row.slug,
            "per_page": 1,
            "context": "edit",
            "_fields": "id,name,slug,meta",
        },
    )
    if isinstance(existing, list) and existing:
        term_id = int(existing[0].get("id", 0))
        if term_id > 0:
            print(f"Using publisher term: {row.name} -> ID {term_id}")
            return term_id

    by_name = client.get(
        "wp/v2/ml_publisher",
        params={
            "search": row.name,
            "per_page": 100,
            "context": "edit",
            "_fields": "id,name,slug,meta",
        },
    )
    if isinstance(by_name, list):
        wanted = row.name.casefold()
        for item in by_name:
            if str(item.get("name", "")).strip().casefold() == wanted:
                term_id = int(item.get("id", 0))
                if term_id > 0:
                    print(f"Using publisher term: {row.name} -> ID {term_id}")
                    return term_id

    created = client.post(
        "wp/v2/ml_publisher",
        payload={"name": row.name, "slug": row.slug},
    )
    term_id = int(created.get("id", 0))
    if term_id <= 0:
        raise RuntimeError(f"Failed to create publisher term '{row.name}'")
    print(f"Created publisher term: {row.name} -> ID {term_id}")
    return term_id


def update_term_homepage(
    client: WordPressRestClient, term_id: int, row: PublisherSeedRow
) -> None:
    payload: Dict[str, Any] = {
        "meta": {
            PUBLISHER_META_KEY: row.homepage,
        }
    }
    updated = client.post(f"wp/v2/ml_publisher/{term_id}", payload=payload)
    updated_id = int(updated.get("id", 0))
    if updated_id != term_id:
        raise RuntimeError(f"Failed to update homepage metadata for '{row.name}'")
    if row.homepage:
        print(f"Set homepage: {row.name} -> {row.homepage}")
    else:
        print(f"Cleared homepage: {row.name}")


def main() -> None:
    script_root = Path(__file__).resolve().parent.parent
    mapping_path = Path(
        os.getenv(
            "PUBLISHER_MAP_PATH",
            str(script_root / "config" / "publisher-homepages.json"),
        )
    )
    try:
        settings = load_rest_settings_from_env()
        client = WordPressRestClient(settings)
        ensure_publisher_taxonomy_ready(client)
        rows = load_seed_rows(mapping_path)
        for row in rows:
            term_id = ensure_term(client, row)
            update_term_homepage(client, term_id, row)
    except RuntimeError as exc:
        fail(str(exc))

    print("Publisher homepage seeding complete.")


def ensure_publisher_taxonomy_ready(client: WordPressRestClient) -> None:
    try:
        client.get("wp/v2/taxonomies/ml_publisher")
        return
    except RuntimeError as exc:
        message = str(exc)
        if "rest_taxonomy_invalid" not in message and "404" not in message:
            raise

    plugin_slug = resolve_marketlense_plugin_slug(client)
    if plugin_slug is None:
        raise RuntimeError(
            "Taxonomy 'ml_publisher' is unavailable and plugin 'marketlense-core' "
            "was not found via REST. Upload/activate marketlense-core in WP Admin first."
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
                "Activate it in WP Admin and rerun seeding."
            )
        print(f"Activated plugin: {plugin_slug}")

    client.get("wp/v2/taxonomies/ml_publisher")


def resolve_marketlense_plugin_slug(client: WordPressRestClient) -> str | None:
    payload = client.get("wp/v2/plugins", params={"search": "marketlense-core"})
    if not isinstance(payload, list):
        return None
    for item in payload:
        slug = str(item.get("plugin", "")).strip()
        if slug.startswith("marketlense-core/"):
            return slug
    return None


if __name__ == "__main__":
    main()
