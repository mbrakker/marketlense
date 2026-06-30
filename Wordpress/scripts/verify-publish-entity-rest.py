#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Wordpress.scripts.wp_rest_common import (
    WordPressRestClient,
    load_rest_settings_from_env,
    slugify,
)


REQUIRED_POST_TYPES = ("ml_report", "ml_briefing", "ml_signal")
ENTITY_ROUTE_SEGMENTS = {
    "ml_report": "/reports/",
    "ml_briefing": "/briefings/",
    "ml_signal": "/signals/",
}


class RestClient(Protocol):
    def get(self, path: str, params: dict[str, Any] | None = None) -> Any: ...

    def post(self, path: str, payload: dict[str, Any] | None = None) -> Any: ...


@dataclass(frozen=True)
class EntityDraftPayload:
    schema_version: str
    post_type: str
    source_artifact_path: str
    title: str
    slug: str
    content_html: str
    excerpt: str
    status: str
    meta: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class EntityReadback:
    schema_version: str
    post_type: str
    post_id: int
    slug: str
    title: str
    status: str
    link: str
    permalink_template: str
    meta: dict[str, object]


@dataclass(frozen=True)
class EntityVerification:
    schema_version: str
    post_type: str
    collection_route: str
    source_artifact_path: str
    post_id: int
    slug: str
    title: str
    status: str
    link: str
    permalink_template: str
    route_confirmed: bool
    metadata_keys: list[str]


def build_briefing_payload(
    artifact_path: Path, *, slug_suffix: str, status: str
) -> EntityDraftPayload:
    payload = _read_json_object(artifact_path)
    package = payload.get("publish_package")
    if not isinstance(package, Mapping):
        raise RuntimeError(f"Briefing artifact lacks publish_package: {artifact_path}")
    if str(package.get("target_route") or "") != "wordpress:ml_briefing":
        raise RuntimeError("Briefing artifact target_route is not wordpress:ml_briefing")

    evidence_ids = _string_list(package.get("evidence_reference_ids"), "evidence_reference_ids")
    sources = package.get("source_metadata")
    if not isinstance(sources, list) or not sources:
        raise RuntimeError("Briefing artifact lacks source_metadata")

    meta = {
        "ml_briefing_source_count": len(sources),
        "ml_briefing_evidence_count": len(evidence_ids),
    }
    return EntityDraftPayload(
        schema_version="1.0",
        post_type="ml_briefing",
        source_artifact_path=str(artifact_path),
        title=_required_text(package, "title"),
        slug=_verification_slug(_required_text(package, "slug"), slug_suffix),
        content_html=_required_text(package, "body_html"),
        excerpt=str(package.get("excerpt") or "")[:500],
        status=status,
        meta=meta,
    )


def build_report_payload(
    artifact_path: Path, *, slug_suffix: str, status: str
) -> EntityDraftPayload:
    if not artifact_path.is_file():
        raise RuntimeError(f"Report artifact path does not exist: {artifact_path}")
    html_text = artifact_path.read_text(encoding="utf-8")
    title = _html_title(html_text) or artifact_path.stem.replace("-", " ").title()
    excerpt = _strip_tags(html_text)[:500]
    return EntityDraftPayload(
        schema_version="1.0",
        post_type="ml_report",
        source_artifact_path=str(artifact_path),
        title=title,
        slug=_verification_slug(slugify(title), slug_suffix),
        content_html=html_text,
        excerpt=excerpt,
        status=status,
    )


def build_signal_payload(
    artifact_path: Path, *, slug_suffix: str, status: str
) -> EntityDraftPayload:
    payload = _read_json_object(artifact_path)
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError(f"Signal artifact lacks candidates: {artifact_path}")
    candidate = _first_approved_candidate(candidates)
    title = _required_text(candidate, "title")
    summary = _required_text(candidate, "summary")
    evidence_ids = _string_list(candidate.get("evidence_ids"), "evidence_ids")
    source_report_ids = _string_list(candidate.get("source_report_ids"), "source_report_ids")
    caveats = _string_list(candidate.get("caveats"), "caveats", allow_empty=True)
    source_refs = candidate.get("source_refs")
    if not isinstance(source_refs, list) or not source_refs:
        raise RuntimeError("Signal candidate lacks source_refs")

    body_html = _signal_body_html(
        title=title,
        summary=summary,
        source_report_ids=source_report_ids,
        evidence_ids=evidence_ids,
        caveats=caveats,
    )
    meta = {
        "ml_signal_card_schema_version": "1.0",
        "ml_signal_card_summary": summary[:500],
        "ml_signal_card_uncertainty": "; ".join(caveats)[:500],
        "ml_signal_card_confidence": float(str(candidate.get("confidence") or 0.0)),
        "ml_signal_source_count": len(source_report_ids),
        "ml_signal_evidence_count": len(evidence_ids),
    }
    return EntityDraftPayload(
        schema_version="1.0",
        post_type="ml_signal",
        source_artifact_path=str(artifact_path),
        title=title,
        slug=_verification_slug(slugify(title), slug_suffix),
        content_html=body_html,
        excerpt=summary[:500],
        status=status,
        meta=meta,
    )


def verify_remote_entities(
    client: RestClient,
    *,
    report_payload: EntityDraftPayload,
    briefing_payload: EntityDraftPayload,
    signal_payload: EntityDraftPayload,
) -> list[EntityVerification]:
    type_routes = _verify_type_exposure(client.get("wp/v2/types"))
    verifications: list[EntityVerification] = []
    for payload in (report_payload, briefing_payload, signal_payload):
        created = _create_draft(client, payload)
        readback = _read_back_post(client, payload.post_type, created)
        _assert_readback(payload, readback)
        route_segment = ENTITY_ROUTE_SEGMENTS[payload.post_type]
        route_confirmed = route_segment in (
            readback.permalink_template or readback.link
        )
        if not route_confirmed:
            raise RuntimeError(
                f"{payload.post_type} permalink route did not include {route_segment!r}"
            )
        verifications.append(
            EntityVerification(
                schema_version="1.0",
                post_type=payload.post_type,
                collection_route=type_routes[payload.post_type],
                source_artifact_path=payload.source_artifact_path,
                post_id=readback.post_id,
                slug=readback.slug,
                title=readback.title,
                status=readback.status,
                link=readback.link,
                permalink_template=readback.permalink_template,
                route_confirmed=True,
                metadata_keys=sorted(payload.meta),
            )
        )
    return verifications


def _verify_type_exposure(payload: Any) -> dict[str, str]:
    if not isinstance(payload, Mapping):
        raise RuntimeError("wp/v2/types returned a non-object response")
    routes: dict[str, str] = {}
    for post_type in REQUIRED_POST_TYPES:
        item = payload.get(post_type)
        if not isinstance(item, Mapping):
            raise RuntimeError(f"Remote wp/v2/types does not expose {post_type}")
        rest_base = str(item.get("rest_base") or "")
        if rest_base != post_type:
            raise RuntimeError(
                f"Remote {post_type} rest_base is {rest_base!r}, expected {post_type!r}"
            )
        links = item.get("_links")
        collection = []
        if isinstance(links, Mapping):
            raw_collection = links.get("wp:items")
            if isinstance(raw_collection, list):
                collection = raw_collection
        href = ""
        if collection and isinstance(collection[0], Mapping):
            href = str(collection[0].get("href") or "")
        if f"/wp/v2/{post_type}" not in href:
            raise RuntimeError(f"Remote {post_type} lacks a wp/v2 collection route")
        routes[post_type] = href
    return routes


def _create_draft(client: RestClient, payload: EntityDraftPayload) -> int:
    response = client.post(
        f"wp/v2/{payload.post_type}",
        {
            "title": payload.title,
            "slug": payload.slug,
            "content": payload.content_html,
            "excerpt": payload.excerpt,
            "status": payload.status,
            "meta": payload.meta,
        },
    )
    if not isinstance(response, Mapping):
        raise RuntimeError(f"{payload.post_type} create returned a non-object response")
    post_id = int(response.get("id") or 0)
    if post_id < 1:
        raise RuntimeError(f"{payload.post_type} create returned an invalid post id")
    return post_id


def _read_back_post(client: RestClient, post_type: str, post_id: int) -> EntityReadback:
    response = client.get(
        f"wp/v2/{post_type}/{post_id}",
        params={
            "context": "edit",
            "_fields": "id,type,slug,title,status,link,permalink_template,meta",
        },
    )
    if not isinstance(response, Mapping):
        raise RuntimeError(f"{post_type} readback returned a non-object response")
    title = response.get("title")
    rendered_title = ""
    if isinstance(title, Mapping):
        rendered_title = str(title.get("raw") or title.get("rendered") or "")
    meta = response.get("meta")
    return EntityReadback(
        schema_version="1.0",
        post_type=str(response.get("type") or ""),
        post_id=int(response.get("id") or 0),
        slug=str(response.get("slug") or ""),
        title=_strip_tags(rendered_title),
        status=str(response.get("status") or ""),
        link=str(response.get("link") or ""),
        permalink_template=str(response.get("permalink_template") or ""),
        meta=dict(meta) if isinstance(meta, Mapping) else {},
    )


def _assert_readback(payload: EntityDraftPayload, readback: EntityReadback) -> None:
    if readback.post_type != payload.post_type:
        raise RuntimeError(
            f"Readback post type {readback.post_type!r} did not match {payload.post_type!r}"
        )
    if readback.slug != payload.slug:
        raise RuntimeError(
            f"Readback slug {readback.slug!r} did not match {payload.slug!r}"
        )
    if readback.title != payload.title:
        raise RuntimeError(
            f"Readback title {readback.title!r} did not match {payload.title!r}"
        )
    if readback.status != payload.status:
        raise RuntimeError(
            f"Readback status {readback.status!r} did not match {payload.status!r}"
        )
    missing_meta = [key for key in payload.meta if key not in readback.meta]
    if missing_meta:
        raise RuntimeError(
            f"Readback metadata missing for {payload.post_type}: {', '.join(missing_meta)}"
        )


def _read_json_object(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Artifact path does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Artifact is not valid JSON: {path}") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"Artifact root must be a JSON object: {path}")
    return payload


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise RuntimeError(f"Required text field is empty: {key}")
    return value


def _string_list(value: Any, field_name: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be a list")
    normalized = [str(item).strip() for item in value if str(item).strip()]
    if not normalized and not allow_empty:
        raise RuntimeError(f"{field_name} must not be empty")
    return normalized


def _first_approved_candidate(candidates: list[Any]) -> Mapping[str, Any]:
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        if str(candidate.get("validation_status") or "") == "approved":
            return candidate
    raise RuntimeError("Signal artifact contains no approved candidate")


def _verification_slug(base_slug: str, suffix: str) -> str:
    base = slugify(base_slug)
    normalized_suffix = slugify(suffix)
    return f"{base}-{normalized_suffix}"


def _signal_body_html(
    *,
    title: str,
    summary: str,
    source_report_ids: list[str],
    evidence_ids: list[str],
    caveats: list[str],
) -> str:
    source_items = "".join(f"<li>{_escape_html(item)}</li>" for item in source_report_ids)
    evidence_items = "".join(f"<li>{_escape_html(item)}</li>" for item in evidence_ids[:10])
    caveat_text = "; ".join(caveats) if caveats else "No candidate caveats recorded."
    return (
        '<article class="market-lense-signal" data-market-lense-publish-entity="true">'
        f"<h1>{_escape_html(title)}</h1>"
        f"<p>{_escape_html(summary)}</p>"
        f"<p><strong>Coverage note:</strong> {_escape_html(caveat_text)}</p>"
        "<h2>Source reports</h2>"
        f"<ul>{source_items}</ul>"
        "<h2>Evidence references</h2>"
        f"<ol>{evidence_items}</ol>"
        "</article>"
    )


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).strip()


def _html_title(html_text: str) -> str:
    title_match = re.search(
        r"<title[^>]*>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL
    )
    if title_match:
        title = _strip_tags(title_match.group(1))
        if title:
            return title
    heading_match = re.search(
        r"<h1[^>]*>(.*?)</h1>", html_text, flags=re.IGNORECASE | re.DOTALL
    )
    if heading_match:
        return _strip_tags(heading_match.group(1))
    return ""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify live WordPress REST exposure and draft readback for "
            "ml_report, ml_briefing, and ml_signal using existing generated artifacts."
        )
    )
    parser.add_argument(
        "--report-artifact",
        required=True,
        type=Path,
        help="Existing generated report HTML artifact.",
    )
    parser.add_argument(
        "--briefing-artifact",
        required=True,
        type=Path,
        help="Existing cross-report analysis JSON containing publish_package.",
    )
    parser.add_argument(
        "--signal-artifact",
        required=True,
        type=Path,
        help="Existing generated signals.json containing approved candidates.",
    )
    parser.add_argument(
        "--status",
        default="draft",
        choices=("draft", "pending", "private"),
        help="Post status used for live verification creates.",
    )
    parser.add_argument(
        "--slug-suffix",
        default="",
        help="Unique suffix for created verification slugs.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Optional path for sanitized verification evidence JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    suffix = str(args.slug_suffix or "").strip()
    if not suffix:
        suffix = "rest-verify-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    report_payload = build_report_payload(
        args.report_artifact,
        slug_suffix=suffix,
        status=args.status,
    )
    briefing_payload = build_briefing_payload(
        args.briefing_artifact,
        slug_suffix=suffix,
        status=args.status,
    )
    signal_payload = build_signal_payload(
        args.signal_artifact,
        slug_suffix=suffix,
        status=args.status,
    )
    client = WordPressRestClient(load_rest_settings_from_env())
    verifications = verify_remote_entities(
        client,
        report_payload=report_payload,
        briefing_payload=briefing_payload,
        signal_payload=signal_payload,
    )
    output = json.dumps(
        [verification.__dict__ for verification in verifications],
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
