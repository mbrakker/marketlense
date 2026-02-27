#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from wp_rest_common import (
    WordPressRestClient,
    fail,
    load_rest_settings_from_env,
)


@dataclass(frozen=True)
class PageSpec:
    schema_version: str
    title: str
    slug: str


REQUIRED_PAGES: List[PageSpec] = [
    PageSpec(schema_version="1.0", title="About", slug="about"),
    PageSpec(schema_version="1.0", title="Methodology", slug="methodology"),
    PageSpec(schema_version="1.0", title="Topics directory", slug="topics-directory"),
    PageSpec(
        schema_version="1.0",
        title="Publishers directory",
        slug="publishers-directory",
    ),
    PageSpec(
        schema_version="1.0",
        title="Submit a Report",
        slug="submit-a-report",
    ),
    PageSpec(schema_version="1.0", title="Contact", slug="contact"),
    PageSpec(schema_version="1.0", title="Privacy", slug="privacy"),
    PageSpec(schema_version="1.0", title="Terms", slug="terms"),
]


def ensure_page(client: WordPressRestClient, spec: PageSpec) -> int:
    payload = client.get(
        "wp/v2/pages",
        params={
            "slug": spec.slug,
            "per_page": 1,
            "context": "edit",
            "_fields": "id,slug,title,status",
        },
    )
    page_id = None
    if isinstance(payload, list) and payload:
        page_id = int(payload[0].get("id", 0)) or None

    update = {
        "title": spec.title,
        "slug": spec.slug,
        "status": "publish",
        "content": "",
    }

    if page_id is None:
        created = client.post("wp/v2/pages", payload=update)
        created_id = int(created.get("id", 0))
        if created_id <= 0:
            raise RuntimeError(f"Failed to create page '{spec.slug}'")
        print(f"Created page: {spec.title} ({spec.slug}) -> ID {created_id}")
        return created_id

    updated = client.post(f"wp/v2/pages/{page_id}", payload=update)
    updated_id = int(updated.get("id", 0))
    if updated_id <= 0:
        raise RuntimeError(f"Failed to update page '{spec.slug}'")
    print(f"Updated page: {spec.title} ({spec.slug}) -> ID {updated_id}")
    return updated_id


def main() -> None:
    try:
        settings = load_rest_settings_from_env()
        client = WordPressRestClient(settings)
    except RuntimeError as exc:
        fail(str(exc))

    try:
        warn_if_marketlense_theme_inactive(client)
        for page in REQUIRED_PAGES:
            ensure_page(client, page)
    except RuntimeError as exc:
        fail(str(exc))

    print(
        "Navigation provisioning skipped in REST fallback: "
        "marketlense uses static nav links in theme template parts."
    )
    print("Provisioning complete.")


def warn_if_marketlense_theme_inactive(client: WordPressRestClient) -> None:
    try:
        payload = client.get("wp/v2/themes/marketlense")
    except RuntimeError as exc:
        print(
            f"Warning: unable to verify active theme via REST ({exc}). "
            "Proceeding with page provisioning."
        )
        return

    status = str(payload.get("status", "")).strip().lower()
    if status and status != "active":
        print(
            "Warning: theme 'marketlense' is installed but not active. "
            "Activate it in WP Admin (Appearance -> Themes) to apply template parts."
        )


if __name__ == "__main__":
    main()
