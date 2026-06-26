#!/usr/bin/env python3
from __future__ import annotations

import base64
import os
from pathlib import Path

import requests

from src.contracts.config import ConfigLoadRequest
from src.contracts.report_store import PublicPublisherReportValueAggregateRequest
from src.services.config_service import load_settings
from src.services.report_store_service import (
    list_public_publisher_report_value_aggregates,
)
from src.utils.logging import new_run_context

from ..publisher_profiles_common import (
    build_term_payload,
    load_profile_rows,
    resolve_icon_download_url,
)
from ..wp_rest_common import WordPressRestClient, fail, load_rest_settings_from_env


PROFILE_CONFIG_ENV = "PUBLISHER_PROFILE_PATH"
DEFAULT_CONFIG_NAME = "publisher-profiles.json"
ICON_INLINE_FETCH_ENV = "PUBLISHER_ICON_INLINE_FETCH"
PUBLISHER_TAXONOMY = "ml_publisher"
REQUIRED_PROFILE_META_KEYS = {
    "ml_publisher_homepage",
    "ml_publisher_insights_url",
    "ml_publisher_icon_source",
    "ml_publisher_notion_page_id",
    "ml_publisher_notion_page_url",
    "ml_publisher_report_value_score",
    "ml_publisher_report_value_band",
    "ml_publisher_report_value_sample_size",
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
    try:
        updated = client.post(f"wp/v2/{PUBLISHER_TAXONOMY}/{term_id}", payload=payload)
    except RuntimeError as exc:
        if "ml_publisher_homepage" not in str(exc):
            raise
        retry_payload = dict(payload)
        retry_meta = dict(payload.get("meta", {}))
        retry_meta.pop("ml_publisher_homepage", None)
        retry_payload["meta"] = retry_meta
        updated = client.post(
            f"wp/v2/{PUBLISHER_TAXONOMY}/{term_id}", payload=retry_payload
        )
        print(f"Retried publisher profile without homepage meta: {name}")
    updated_id = int(updated.get("id", 0))
    if updated_id != term_id:
        raise RuntimeError(f"Failed to update publisher profile for '{name}'")
    print(f"Updated publisher profile: {name} -> ID {term_id}")


def published_file_ids_by_term(posts: list[object]) -> dict[int, list[str]]:
    file_ids_by_term: dict[int, set[str]] = {}
    for post in posts:
        if not isinstance(post, dict):
            continue
        meta = post.get("meta")
        file_id = (
            str(meta.get("ml_file_id", "")).strip() if isinstance(meta, dict) else ""
        )
        term_ids = post.get(PUBLISHER_TAXONOMY)
        if not file_id or not isinstance(term_ids, list):
            continue
        for raw_term_id in term_ids:
            term_id = int(raw_term_id)
            if term_id > 0:
                file_ids_by_term.setdefault(term_id, set()).add(file_id)
    return {term_id: sorted(file_ids) for term_id, file_ids in file_ids_by_term.items()}


def report_value_band(score: float) -> str:
    return (
        "high"
        if score >= 78
        else "medium"
        if score >= 60
        else "low"
        if score >= 40
        else "weak"
    )


def update_term_quality(
    client: WordPressRestClient,
    *,
    term_id: int,
    score: float,
    sample_size: int,
) -> None:
    updated = client.post(
        f"wp/v2/{PUBLISHER_TAXONOMY}/{term_id}",
        payload={
            "meta": {
                "ml_publisher_report_value_score": score,
                "ml_publisher_report_value_band": report_value_band(score),
                "ml_publisher_report_value_sample_size": sample_size,
            }
        },
    )
    if int(updated.get("id", 0)) != term_id:
        raise RuntimeError(f"Failed to update publisher quality for term ID {term_id}")
    print(f"Updated publisher quality: ID {term_id} ({sample_size} reports)")


def main() -> None:
    script_root = Path(__file__).resolve().parent.parent
    config_path = Path(
        os.getenv(
            PROFILE_CONFIG_ENV, str(script_root.parent / "config" / DEFAULT_CONFIG_NAME)
        )
    )

    try:
        settings = load_rest_settings_from_env()
        client = WordPressRestClient(settings)
        ensure_publisher_taxonomy_ready(client)
        assert_publisher_profile_meta_ready(client)
        rows = load_profile_rows(config_path)
        score_ctx = new_run_context(task_id="wordpress_publisher_report_value_sync")
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), score_ctx
        )
        term_ids: dict[str, int] = {}
        for row in rows:
            term_id = ensure_term(client, slug=row.slug, name=row.name)
            term_ids[row.name.casefold()] = term_id
        inline_icons = should_inline_icon_sources()
        for row in rows:
            term_id = term_ids[row.name.casefold()]
            payload = build_term_payload(row)
            payload["meta"]["ml_publisher_icon_source"] = (
                inline_icon_source(
                    raw_icon_source=row.icon_source,
                    download_url=resolve_icon_download_url(row),
                    publisher_name=row.name,
                )
                if inline_icons
                else row.icon_source
            )
            update_term_profile(
                client,
                term_id=term_id,
                payload=payload,
                name=row.name,
            )
        published_posts = client.get(
            "wp/v2/posts",
            params={
                "status": "publish",
                "per_page": 100,
                "context": "edit",
                "_fields": f"meta,{PUBLISHER_TAXONOMY}",
            },
        )
        if not isinstance(published_posts, list):
            raise RuntimeError("WordPress published-post response must be a list")
        quality_updates = 0
        quality_unavailable = 0
        for term_id, file_ids in published_file_ids_by_term(published_posts).items():
            aggregate_response = list_public_publisher_report_value_aggregates(
                PublicPublisherReportValueAggregateRequest(
                    schema_version="1.0",
                    db_path=app_settings.reports_db,
                    published_file_ids=file_ids,
                ),
                score_ctx,
            )
            sample_size = sum(
                item.sample_size for item in aggregate_response.aggregates
            )
            if sample_size == 0:
                quality_unavailable += 1
                continue
            score = round(
                sum(
                    item.average_score * item.sample_size
                    for item in aggregate_response.aggregates
                )
                / sample_size,
                3,
            )
            update_term_quality(
                client,
                term_id=term_id,
                score=score,
                sample_size=sample_size,
            )
            quality_updates += 1
        print(
            "Publisher quality migration: "
            f"inspected={len(rows)} updated={quality_updates} unavailable={quality_unavailable}"
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


def should_inline_icon_sources() -> bool:
    return os.getenv(ICON_INLINE_FETCH_ENV, "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


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

    content_type = (
        str(response.headers.get("content-type", "")).split(";", 1)[0].lower()
    )
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
