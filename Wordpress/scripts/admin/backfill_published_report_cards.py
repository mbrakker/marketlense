#!/usr/bin/env python3
"""Restore report-card contracts from content already published in WordPress."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import os
from pathlib import Path
import re
import time
from typing import Mapping

from bs4 import BeautifulSoup

from src.contracts.config import ConfigLoadRequest
from src.contracts.cover_images import CoverImageGenerationRequest, CoverImageReport
from src.contracts.publish import PublishRequest
from src.contracts.report_cards import (
    CardCoverAssetSet,
    CoverFingerprintProjectionRequest,
    ReportCardManifestRequest,
    ReportCardManifestWriteRequest,
)
from src.generators.cover_image_generator import generate_cover_images
from src.generators.publish_generator import publish_html
from src.generators.report_card_projection import (
    build_cover_fingerprint,
    build_report_card_manifest,
)
from src.services.config_service import load_publish_settings, load_settings
from src.services.file_service import write_report_card_manifest
from src.services.report_store_service import get_metadata
from src.contracts.report_store import ReportMetadataGetRequest
from src.utils.errors import AppError
from src.utils.logging import child_context, new_run_context
from src.utils.slugify import slugify
from src.utils.wp_auth import build_auth_header

from ..wp_rest_common import WordPressRestClient, fail, load_rest_settings_from_env


REPORT_POST_TYPES = ("posts", "ml_report")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class PublishedReportTarget:
    """An existing WordPress report that must receive a card contract in place."""

    schema_version: str
    post_type: str
    post_id: int
    file_id: str


@dataclass(frozen=True)
class LegacyCardContent:
    """Validated card inputs recovered from published report content and taxonomy."""

    schema_version: str
    title: str
    publisher: str
    published_date: str
    covered_period: str
    region: str
    categories: tuple[str, ...]
    tldr_compact: str
    tldr_standard: str
    key_insights: tuple[str, str]


def targets_from_posts(
    post_type: str, posts: list[object]
) -> list[PublishedReportTarget]:
    """Return valid existing post targets without collapsing shared Drive sources."""
    targets: list[PublishedReportTarget] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        post_id = int(post.get("id", 0) or 0)
        meta = post.get("meta")
        file_id = str(meta.get("ml_file_id", "")).strip() if isinstance(meta, dict) else ""
        if post_id <= 0 or not file_id:
            continue
        targets.append(
            PublishedReportTarget(
                schema_version="1.0",
                post_type="post" if post_type == "posts" else post_type,
                post_id=post_id,
                file_id=file_id,
            )
        )
    return targets


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _legacy_display_title(value: object) -> str:
    title = _text(value)
    if "_" not in title:
        return title
    normalized = title.replace("_", " ")
    normalized = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", normalized)
    return _text(normalized)


def _post_text(post: Mapping[str, object]) -> tuple[str, BeautifulSoup]:
    content = post.get("content")
    html = str(content.get("raw", "")) if isinstance(content, dict) else ""
    soup = BeautifulSoup(html, "html.parser")
    return _text(soup.get_text(" ", strip=True)), soup


def _taxonomy_names(
    post: Mapping[str, object],
    key: str,
    names: Mapping[int, str],
) -> tuple[str, ...]:
    raw_ids = post.get(key)
    if not isinstance(raw_ids, list):
        return ()
    return tuple(
        name
        for raw_id in raw_ids
        if (name := _text(names.get(int(raw_id), "")))
    )


def _labelled_value(text: str, label: str) -> str:
    match = re.search(
        rf"{re.escape(label)}:\s*(.+?)(?=\s+(?:Publisher|Time Period|Geography|Region):|$)",
        text,
        flags=re.IGNORECASE,
    )
    return _text(match.group(1)) if match else ""


def _sentences(text: str) -> tuple[str, ...]:
    return tuple(
        sentence
        for sentence in (_text(value) for value in _SENTENCE_RE.split(text))
        if sentence.endswith((".", "!", "?")) and len(sentence.split()) >= 4
    )


def _contains_term(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        escaped = re.escape(term.casefold()).replace("\\ ", r"\s+")
        if re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text):
            return True
    return False


def _summary_candidates(soup: BeautifulSoup, text: str) -> tuple[str, ...]:
    candidates: list[str] = []
    for selector in (
        ".hero-thesis",
        ".report-summary",
        ".tldr",
        ".lead",
        ".summary-list li",
        "#section-summary li",
    ):
        for node in soup.select(selector):
            candidate = _text(node.get_text(" ", strip=True))
            if candidate and candidate not in candidates:
                candidates.append(candidate)
    return tuple(candidates) + _sentences(text)


def _complete_sentence(value: str) -> str:
    normalized = _text(value)
    if normalized.endswith(("...", "…")):
        return ""
    return normalized if normalized.endswith((".", "!", "?")) else normalized + "."


def legacy_cover_semantics(
    text: str,
    *,
    title: str = "",
    publisher: str = "",
    categories: tuple[str, ...] = (),
) -> dict[str, str]:
    """Select a deterministic cover geometry from the report's published copy."""
    normalized_body = _text(text).casefold()
    normalized_title = _text(title).casefold()
    normalized_header = _text(" ".join((title, publisher, " ".join(categories)))).casefold()
    normalized = _text(
        " ".join((normalized_header, normalized_body[:2000]))
    ).casefold()
    forecast = _contains_term(
        normalized,
        (
            "forecast",
            "outlook",
            "projection",
            "prediction",
            "predictions",
            "trend",
            "trends",
            "planning",
            "through 20",
            "by 20",
        ),
    )
    if _contains_term(
        normalized,
        ("m&a", "merger", "acquisition", "deal", "payments landscape"),
    ):
        shape = "flow"
    elif normalized_title.startswith("digital ") or _contains_term(
        normalized,
        (
            "penetration",
            "statistics",
            "digital payments",
        ),
    ):
        shape = "distribution"
    elif _contains_term(
        normalized,
        (
            "network",
            "ecosystem",
            "connected",
            "channel",
            "channels",
            "search",
            "ecommerce",
        ),
    ):
        shape = "network"
    elif _contains_term(normalized, ("risk", "uncertain", "uncertainty")):
        shape = "uncertainty"
    elif _contains_term(
        normalized,
        (
            "survey",
            "compare",
            "compares",
            "compared",
            "comparison",
            "versus",
            "responses",
            "reactions",
            "pulse",
        ),
    ):
        shape = "comparison"
    elif _contains_term(
        normalized,
        ("ranking", "ranked", "rankings", "top", "leading", "footprint", "guide"),
    ):
        shape = "hierarchy"
    elif _contains_term(
        normalized,
        ("distribution", "segment", "share of", "consumer groups"),
    ):
        shape = "distribution"
    else:
        shape = "trend"
    if _contains_term(
        normalized,
        (
            "increase",
            "increasing",
            "growth",
            "rising",
            "accelerate",
            "accelerating",
            "accelerated",
            "winning",
            "opportunity",
            "opportunities",
            "adoption",
        ),
    ):
        direction = "rising"
    elif _contains_term(
        normalized,
        (
            "decline",
            "declining",
            "falling",
            "decrease",
            "decreasing",
            "contract",
            "contracting",
            "retention challenge",
            "leaky bucket",
        ),
    ):
        direction = "falling"
    elif _contains_term(normalized, ("volatile", "uncertain", "uncertainty", "risk")):
        direction = "volatile"
    elif shape == "comparison":
        direction = "diverging"
    elif shape == "hierarchy":
        direction = "stable"
    elif shape in {"flow", "network"}:
        direction = "rising"
    else:
        direction = "neutral"
    if shape == "trend" and direction == "neutral" and not forecast:
        shape = "cycle" if normalized_header else "system"
    density = "metric_rich" if len(re.findall(r"\d", normalized)) >= 8 else "balanced"
    return {
        "evidence_shape": shape,
        "direction": direction,
        "evidence_density": density,
        "domain_layer": "forecast" if forecast else "grid",
        "selection_reason": "Derived deterministically from the published report copy during legacy card migration.",
    }


def _insights(soup: BeautifulSoup, text: str) -> tuple[str, str]:
    candidates: list[str] = []
    for selector in (".key-insights li", ".insights li", ".finding li", ".report li"):
        for node in soup.select(selector):
            candidate = _text(node.get_text(" ", strip=True))
            if 8 <= len(candidate.split()) <= 55 and candidate not in candidates:
                candidates.append(candidate)
    for sentence in _sentences(text):
        if 8 <= len(sentence.split()) <= 55 and sentence not in candidates:
            candidates.append(sentence)
    if len(candidates) < 2:
        raise AppError(
            code="legacy_card_insights_missing",
            message="Published report content does not contain two usable insights",
            retryable=False,
        )
    return candidates[0], candidates[1]


def legacy_card_content(
    post: Mapping[str, object],
    *,
    publisher_names: Mapping[int, str],
    category_names: Mapping[int, str],
    fallback_publisher: str = "",
) -> LegacyCardContent:
    """Recover a complete card contract only from existing published report data."""
    title_payload = post.get("title")
    title = (
        _legacy_display_title(title_payload.get("raw", ""))
        if isinstance(title_payload, dict)
        else ""
    )
    meta = post.get("meta")
    meta = meta if isinstance(meta, dict) else {}
    text, soup = _post_text(post)
    publishers = _taxonomy_names(post, "ml_publisher", publisher_names)
    publisher = _text(meta.get("ml_publisher_name")) or (
        publishers[0] if publishers else _labelled_value(text, "Publisher")
    ) or _text(fallback_publisher)
    if not title or not publisher:
        raise AppError(
            code="legacy_card_metadata_missing",
            message="Published report needs a title and publisher for a card contract",
            retryable=False,
        )
    date = _text(post.get("date"))[:10]
    period = _text(meta.get("ml_time_period")) or _labelled_value(text, "Time Period")
    if not period:
        period = date[:4]
    if not date or not period:
        raise AppError(
            code="legacy_card_metadata_missing",
            message="Published report needs a publication date and covered period",
            retryable=False,
        )
    region = _text(meta.get("ml_region")) or _labelled_value(text, "Geography")
    insights = _insights(soup, text)
    standard = next(
        (
            _complete_sentence(sentence)
            for sentence in (*_summary_candidates(soup, text), *insights)
            if _complete_sentence(sentence)
            and len(_complete_sentence(sentence).split()) <= 45
        ),
        "",
    )
    if not standard:
        raise AppError(
            code="legacy_card_summary_missing",
            message="Published report content does not contain a usable report summary",
            retryable=False,
        )
    compact = next(
        (
            _complete_sentence(sentence)
            for sentence in (*_summary_candidates(soup, text), *insights)
            if _complete_sentence(sentence)
            and len(_complete_sentence(sentence).split()) <= 18
        ),
        "This published report presents its key findings.",
    )
    return LegacyCardContent(
        schema_version="1.0",
        title=title,
        publisher=publisher,
        published_date=date,
        covered_period=period,
        region=region,
        categories=_taxonomy_names(post, "categories", category_names),
        tldr_compact=compact,
        tldr_standard=standard,
        key_insights=insights,
    )


def _term_names(client: WordPressRestClient, endpoint: str) -> dict[int, str]:
    terms = client.get(
        f"wp/v2/{endpoint}",
        params={"per_page": 100, "context": "edit", "_fields": "id,name"},
    )
    if not isinstance(terms, list):
        raise RuntimeError(f"WordPress {endpoint} response must be a list")
    return {
        int(term.get("id", 0)): _text(term.get("name"))
        for term in terms
        if isinstance(term, dict) and int(term.get("id", 0)) > 0
    }


def _published_posts(client: WordPressRestClient) -> dict[str, list[object]]:
    fields = "id,title,content,date,meta,categories,ml_publisher"
    posts: dict[str, list[object]] = {}
    for endpoint in REPORT_POST_TYPES:
        response = client.get(
            f"wp/v2/{endpoint}",
            params={"status": "publish", "per_page": 100, "context": "edit", "_fields": fields},
        )
        if not isinstance(response, list):
            raise RuntimeError(f"WordPress published {endpoint} response must be a list")
        posts[endpoint] = response
    return posts


def _staging_html_path(output_dir: Path, target: PublishedReportTarget) -> Path:
    stem = slugify(f"legacy-card-{target.file_id}")
    return output_dir / f"{stem}.html"


def _card_needs_legacy_refresh(post: Mapping[str, object]) -> bool:
    meta = post.get("meta")
    meta = meta if isinstance(meta, dict) else {}
    if _text(meta.get("ml_card_schema_version")) != "1.0":
        return True
    for key in (
        "ml_card_cover_small_id",
        "ml_card_cover_medium_id",
        "ml_card_cover_large_id",
    ):
        try:
            if int(str(meta.get(key) or 0)) <= 0:
                return True
        except ValueError:
            return True
    fingerprint = meta.get("ml_card_cover_fingerprint")
    geometry = fingerprint.get("geometry_family") if isinstance(fingerprint, dict) else ""
    return _text(geometry) == "system_matrix"


def _positive_number_from_env(name: str, default: float) -> float:
    raw_value = _text(os.environ.get(name))
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be numeric") from exc
    if value < 0:
        raise RuntimeError(f"{name} must be zero or greater")
    return value


def _positive_int_from_env(name: str) -> int | None:
    raw_value = _text(os.environ.get(name))
    if not raw_value:
        return None
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


def limit_targets(
    targets: list[PublishedReportTarget], limit: int | None
) -> list[PublishedReportTarget]:
    """Return the first migration targets allowed by a positive optional limit."""
    if limit is None:
        return targets
    return targets[:limit]


def skip_targets_from_env(
    targets: list[PublishedReportTarget], raw_value: str
) -> list[PublishedReportTarget]:
    """Remove explicitly skipped post IDs from a live migration batch."""
    tokens = {_text(token) for token in raw_value.split(",") if _text(token)}
    if not tokens:
        return targets
    skipped_numeric_ids: set[int] = set()
    skipped_typed_ids: set[tuple[str, int]] = set()
    for token in tokens:
        if ":" in token:
            raw_type, raw_id = token.split(":", 1)
            try:
                skipped_typed_ids.add((_text(raw_type), int(raw_id)))
            except ValueError as exc:
                raise RuntimeError(
                    "MARKETLENSE_REPORT_CARD_BACKFILL_SKIP_IDS entries must "
                    "be numeric IDs or post_type:ID pairs"
                ) from exc
            continue
        try:
            skipped_numeric_ids.add(int(token))
        except ValueError as exc:
            raise RuntimeError(
                "MARKETLENSE_REPORT_CARD_BACKFILL_SKIP_IDS entries must "
                "be numeric IDs or post_type:ID pairs"
            ) from exc
    return [
        target
        for target in targets
        if target.post_id not in skipped_numeric_ids
        and (target.post_type, target.post_id) not in skipped_typed_ids
    ]


def main() -> None:
    ctx = new_run_context(task_id="wordpress_published_report_card_backfill")
    try:
        rest_settings = load_rest_settings_from_env()
        client = WordPressRestClient(rest_settings)
        posts_by_type = _published_posts(client)
        targets = [
            target
            for endpoint, posts in posts_by_type.items()
            for target in targets_from_posts(endpoint, posts)
        ]
        posts_by_target = {
            ("post" if endpoint == "posts" else endpoint, int(post.get("id", 0))): post
            for endpoint, posts in posts_by_type.items()
            for post in posts
            if isinstance(post, dict)
        }
        targets = [
            target
            for target in targets
            if _card_needs_legacy_refresh(
                posts_by_target[(target.post_type, target.post_id)]
            )
        ]
        limit = _positive_int_from_env("MARKETLENSE_REPORT_CARD_BACKFILL_LIMIT")
        sleep_seconds = _positive_number_from_env(
            "MARKETLENSE_REPORT_CARD_BACKFILL_SLEEP_SECONDS", 0.0
        )
        targets = skip_targets_from_env(
            targets, os.environ.get("MARKETLENSE_REPORT_CARD_BACKFILL_SKIP_IDS", "")
        )
        total_targets = len(targets)
        targets = limit_targets(targets, limit)
        if not targets:
            print("Published report-card migration complete: every report is canonical")
            return
        publisher_names = _term_names(client, "ml_publisher")
        category_names = _term_names(client, "categories")
        publish_settings = load_publish_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        app_settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
        source_publishers = {}
        for target in targets:
            metadata = get_metadata(
                ReportMetadataGetRequest(
                    schema_version="1.0",
                    db_path=app_settings.reports_db,
                    file_id=target.file_id,
                ),
                child_context(ctx, task_id=f"legacy_card_metadata:{target.post_id}"),
            )
            if metadata and metadata.publisher:
                source_publishers[target.file_id] = _text(metadata.publisher)
        auth_header = build_auth_header(
            username=publish_settings.wp.username,
            app_password=publish_settings.wp.app_password,
            bearer_token=publish_settings.wp.bearer_token,
        )
        staging_dir = Path(publish_settings.output_dir).resolve() / "legacy-report-cards"
        staging_dir.mkdir(parents=True, exist_ok=True)
        updated = 0
        failures: list[str] = []
        for target in targets:
            post = posts_by_target[(target.post_type, target.post_id)]
            card = legacy_card_content(
                post,
                publisher_names=publisher_names,
                category_names=category_names,
                fallback_publisher=source_publishers.get(target.file_id, ""),
            )
            html_path = _staging_html_path(staging_dir, target)
            content = post.get("content")
            html = str(content.get("raw", "")) if isinstance(content, dict) else ""
            html_path.write_text(html, encoding="utf-8")
            report_dir = html_path.with_suffix("")
            report_slug = slugify(report_dir.name)
            fingerprint = build_cover_fingerprint(
                CoverFingerprintProjectionRequest(
                    schema_version="1.0",
                    file_id=target.file_id,
                    artifact_hash=target.file_id,
                    region=card.region,
                    cover_semantics=legacy_cover_semantics(
                        _post_text(post)[0],
                        title=card.title,
                        publisher=card.publisher,
                        categories=card.categories,
                    ),
                )
            )
            print(
                "Updating published report card "
                f"{target.post_type}:{target.post_id} "
                f"geometry={fingerprint.geometry_family} "
                f"remaining_batch={len(targets)}/{total_targets}"
            )
            cover_outcome = generate_cover_images(
                CoverImageGenerationRequest(
                    schema_version="2.0",
                    output_dir=str(staging_dir),
                    style_config_path=app_settings.cover_style_path,
                    reports=[
                        CoverImageReport(
                            schema_version="2.0",
                            file_id=target.file_id,
                            title=card.title,
                            publisher=card.publisher,
                            report_slug=report_slug,
                            categories=list(card.categories),
                            time_period=card.covered_period,
                            region=card.region,
                            fingerprint=fingerprint,
                        )
                    ],
                ),
                child_context(ctx, task_id=f"legacy_card_cover:{target.post_id}"),
            )[0]
            if cover_outcome.status != "generated" or cover_outcome.assets is None:
                raise AppError(
                    code="cover_asset_set_incomplete",
                    message=cover_outcome.error or "Legacy report-card covers were not generated",
                    retryable=False,
                )
            relative_assets = asdict(cover_outcome.assets)
            for size in ("small", "medium", "large"):
                relative_assets[size]["output_path"] = str(
                    Path(relative_assets[size]["output_path"])
                    .resolve()
                    .relative_to(report_dir.resolve())
                    .as_posix()
                )
            manifest = build_report_card_manifest(
                ReportCardManifestRequest(
                    schema_version="1.0",
                    title=card.title,
                    publisher=card.publisher,
                    published_date=card.published_date,
                    region=card.region,
                    covered_period=card.covered_period,
                    tldr_compact=card.tldr_compact,
                    tldr_standard=card.tldr_standard,
                    insights_final=tuple({"text": item} for item in card.key_insights),
                    fingerprint=fingerprint,
                    covers=CardCoverAssetSet.from_dict(relative_assets),
                )
            )
            write_report_card_manifest(
                ReportCardManifestWriteRequest(
                    schema_version="1.0", output_dir=str(report_dir), manifest=manifest
                ),
                child_context(ctx, task_id=f"legacy_card_manifest:{target.post_id}"),
            )
            target_settings = replace(
                publish_settings,
                wp=replace(publish_settings.wp, post_type=target.post_type),
            )
            outcome = publish_html(
                PublishRequest(
                    schema_version="1.0",
                    html_path=str(html_path),
                    auth_header=auth_header,
                    file_id=target.file_id,
                    existing_post_id=target.post_id,
                ),
                target_settings,
                child_context(ctx, task_id=f"legacy_card_publish:{target.post_id}"),
            )
            if outcome.status != "published" or outcome.post_id != target.post_id:
                failures.append(f"{target.post_type}:{target.post_id}={outcome.error or outcome.status}")
                continue
            updated += 1
            if sleep_seconds:
                time.sleep(sleep_seconds)
        if failures:
            raise RuntimeError("Report-card updates failed: " + ", ".join(failures))
        print(f"Published report-card migration complete: reports={len(targets)} updated={updated}")
    except (AppError, RuntimeError, ValueError) as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
