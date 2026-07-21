from __future__ import annotations

import html
import json
import logging
import mimetypes
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from src.contracts.categories import CategoryMappingLoadRequest
from src.contracts.files import FileExistsRequest, ReadBytesRequest, ReadTextRequest
from src.contracts.publish import (
    PublishHtmlSnapshot,
    PublishOutcome,
    PublishRequest,
    PublishResolvedTerms,
    PublishSettings,
)
from src.contracts.report_cards import ReportCardManifest
from src.contracts.report_store import ReportMetadataGetRequest
from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressCardUpdateRequest,
    WordPressMediaPrepareRequest,
    WordPressMediaUploadRequest,
    WordPressPostCreateRequest,
    WordPressTagEnsureRequest,
    WordPressTaxonomyEnsureRequest,
    WordPressTaxonomyTerm,
)
from src.services.category_mapping_service import (
    load_mappings as load_category_mappings,
)
from src.services.file_service import file_exists, read_bytes, read_text
from src.services.report_store_service import get_metadata
from src.services.wordpress_service import (
    create_post,
    ensure_tags,
    ensure_taxonomy_terms,
    prepare_media_upload,
    update_card,
    upload_media,
)
from src.utils.errors import AppError
from src.utils.html_utils import (
    build_publish_html_snapshot,
    replace_image_sources,
    strip_image_srcset_and_sizes,
    strip_publication_internal_metadata,
)
from src.utils.logging import log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.publish_generator")
EDITORIAL_CONTRACT_VERSION = "public-report-editorial-v1"


@dataclass(frozen=True)
class _MediaUploadJob:
    src: str
    local_path: str
    is_preview: bool


@dataclass(frozen=True)
class _MediaUploadResult:
    src: str
    media_id: int


def publish_html(
    request: PublishRequest,
    settings: PublishSettings,
    ctx: RunContext,
) -> PublishOutcome:
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_start",
            module=logger.name,
            fields={"html_path": request.html_path},
        )
    )

    html_snapshot, html_source = _resolve_html_snapshot(request, ctx)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_html_source",
            module=logger.name,
            fields={
                "html_path": request.html_path,
                "source": html_source,
                "length": len(html_snapshot.html_text),
            },
        )
    )
    file_id = request.file_id or html_snapshot.file_id
    if not file_id:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="publish_missing_file_id",
                module=logger.name,
                fields={"html_path": request.html_path},
            )
        )
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=None,
            status="error",
            error="missing_file_id",
        )

    auth_header = str(request.auth_header or "").strip()
    if not auth_header:
        raise AppError(
            code="wp_auth_missing",
            message="Publish request must include a resolved WordPress auth header",
            retryable=False,
        )
    editorial_issues = _validate_publish_editorial_contract(html_snapshot.html_text)
    blocking_editorial_issues = _blocking_editorial_issues(editorial_issues)
    if editorial_issues:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event=(
                    "publish_editorial_contract_failed"
                    if blocking_editorial_issues
                    else "publish_editorial_contract_warned"
                ),
                module=logger.name,
                fields={
                    "html_path": request.html_path,
                    "policy": settings.validation_policy,
                    "rule_ids": [
                        issue.split("|", 1)[0] for issue in editorial_issues if issue
                    ],
                },
            )
        )
        if settings.validation_policy == "block" and blocking_editorial_issues:
            return PublishOutcome(
                schema_version="1.0",
                html_path=request.html_path,
                file_id=file_id,
                status="skipped",
                error="publish_editorial_contract_failed",
                validation_status="fail",
                validation_issues=editorial_issues,
                publication_outcome="preflight_blocked",
            )
    base_url = settings.wp.site_url.rstrip("/")
    card_manifest = None
    if settings.wp.post_type in {
        "ml_report",
        "post",
        "posts",
    } and not file_id.startswith("cross-report:"):
        card_manifest = _load_report_card_manifest(
            request.html_path,
            settings.output_dir,
            ctx,
        )
    briefing_card = (
        html_snapshot.briefing_card if settings.wp.post_type == "ml_briefing" else {}
    )
    signal_card = (
        html_snapshot.signal_card if settings.wp.post_type == "ml_signal" else {}
    )
    if briefing_card:
        _validate_briefing_card(briefing_card)
    if signal_card:
        _validate_signal_card(signal_card)
    if request.existing_post_id is not None:
        if card_manifest is not None:
            backfill_media_ids = _upload_report_card_covers(
                manifest=card_manifest,
                html_path=request.html_path,
                output_dir=settings.output_dir,
                base_url=base_url,
                auth_header=auth_header,
                ssl_verify=settings.wp.ssl_verify,
                ca_bundle_path=settings.wp.ca_bundle_path,
                ctx=ctx,
                sequential=True,
            )
            card_meta = _report_card_post_meta(
                card_manifest,
                backfill_media_ids,
                has_public_intelligence=_has_public_intelligence_surface(
                    html_snapshot.body_html
                ),
            )
        elif briefing_card:
            backfill_media_ids = _upload_briefing_card_covers(
                card=briefing_card,
                html_path=request.html_path,
                output_dir=settings.output_dir,
                base_url=base_url,
                auth_header=auth_header,
                ssl_verify=settings.wp.ssl_verify,
                ca_bundle_path=settings.wp.ca_bundle_path,
                ctx=ctx,
                sequential=True,
            )
            card_meta = _briefing_card_post_meta(briefing_card, backfill_media_ids)
        elif signal_card:
            backfill_media_ids = _upload_signal_card_covers(
                card=signal_card,
                html_path=request.html_path,
                output_dir=settings.output_dir,
                base_url=base_url,
                auth_header=auth_header,
                ssl_verify=settings.wp.ssl_verify,
                ca_bundle_path=settings.wp.ca_bundle_path,
                ctx=ctx,
                sequential=True,
            )
            card_meta = _signal_card_post_meta(signal_card, backfill_media_ids)
        else:
            raise AppError(
                code="card_contract_required",
                message="An existing card update requires a complete card contract",
                retryable=False,
            )
        update_resp = update_card(
            WordPressCardUpdateRequest(
                schema_version="1.0",
                base_url=base_url,
                auth_header=auth_header,
                post_id=request.existing_post_id,
                featured_media=backfill_media_ids["large"],
                meta=card_meta,
                ssl_verify=settings.wp.ssl_verify,
                ca_bundle_path=settings.wp.ca_bundle_path,
                post_type=settings.wp.post_type,
                run_budget=request.run_budget,
                run_budget_usage=request.run_budget_usage,
            ),
            ctx,
        )
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=file_id,
            status="published",
            post_id=update_resp.post_id,
            post_url=str(update_resp.link or ""),
            publication_outcome="post_updated",
            requested_write_count=1,
            actual_write_count=1,
        )

    metadata = None
    if request.resolved_terms is None:
        reports_db_exists = file_exists(
            FileExistsRequest(schema_version="1.0", path=settings.reports_db),
            ctx,
        ).exists
        if reports_db_exists:
            metadata = get_metadata(
                ReportMetadataGetRequest(
                    schema_version="1.1", db_path=settings.reports_db, file_id=file_id
                ),
                ctx,
            )
    resolved_terms = request.resolved_terms or _resolve_term_assignments(
        metadata=metadata,
        settings=settings,
        base_url=base_url,
        auth_header=auth_header,
        ctx=ctx,
    )
    category_ids_for_wp = list(resolved_terms.category_ids)
    tag_ids_for_wp = list(resolved_terms.tag_ids)

    image_map, featured_media_id = _upload_images(
        html_snapshot=html_snapshot,
        html_path=request.html_path,
        output_dir=settings.output_dir,
        base_url=base_url,
        auth_header=auth_header,
        ssl_verify=settings.wp.ssl_verify,
        ca_bundle_path=settings.wp.ca_bundle_path,
        media_upload_workers=settings.media_upload_workers,
        ctx=ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_images_uploaded",
            module=logger.name,
            fields={"count": len(image_map), "featured_media": featured_media_id or 0},
        )
    )
    card_media_ids: dict[str, int] = {}
    if card_manifest is not None:
        card_media_ids = _upload_report_card_covers(
            manifest=card_manifest,
            html_path=request.html_path,
            output_dir=settings.output_dir,
            base_url=base_url,
            auth_header=auth_header,
            ssl_verify=settings.wp.ssl_verify,
            ca_bundle_path=settings.wp.ca_bundle_path,
            ctx=ctx,
        )
        featured_media_id = card_media_ids["large"]
    if briefing_card:
        card_media_ids = _upload_briefing_card_covers(
            card=briefing_card,
            html_path=request.html_path,
            output_dir=settings.output_dir,
            base_url=base_url,
            auth_header=auth_header,
            ssl_verify=settings.wp.ssl_verify,
            ca_bundle_path=settings.wp.ca_bundle_path,
            ctx=ctx,
        )
        featured_media_id = card_media_ids["large"]
    if signal_card:
        card_media_ids = _upload_signal_card_covers(
            card=signal_card,
            html_path=request.html_path,
            output_dir=settings.output_dir,
            base_url=base_url,
            auth_header=auth_header,
            ssl_verify=settings.wp.ssl_verify,
            ca_bundle_path=settings.wp.ca_bundle_path,
            ctx=ctx,
        )
        featured_media_id = card_media_ids["large"]
    rendered_body_html = replace_image_sources(html_snapshot.body_html, image_map)
    # Proxy-backed digest images stay more reliable on the WP frontend without
    # responsive srcset/sizes candidates that still point at synthetic query URLs.
    rendered_body_html = strip_image_srcset_and_sizes(rendered_body_html)
    body_html = strip_publication_internal_metadata(rendered_body_html)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_public_content_redacted",
            module=logger.name,
            fields={
                "file_id": file_id,
                "removed_internal_publication_metadata": body_html != rendered_body_html,
            },
        )
    )

    title = (
        card_manifest.title
        if card_manifest is not None
        else str(html_snapshot.title or "").strip() or Path(request.html_path).stem
    )
    slug = str(request.slug or "").strip() or slugify(title)

    card_post_meta = (
        _report_card_post_meta(
            card_manifest,
            card_media_ids,
            has_public_intelligence=_has_public_intelligence_surface(body_html),
        )
        if card_manifest is not None
        else _briefing_card_post_meta(briefing_card, card_media_ids)
        if briefing_card
        else _signal_card_post_meta(signal_card, card_media_ids)
        if signal_card
        else None
    )
    post_meta = {"ml_file_id": file_id, **(card_post_meta or {})}
    create_resp = create_post(
        WordPressPostCreateRequest(
            schema_version="1.0",
            base_url=base_url,
            auth_header=auth_header,
            title=title,
            content_html=body_html,
            status=settings.wp.post_status,
            ssl_verify=settings.wp.ssl_verify,
            ca_bundle_path=settings.wp.ca_bundle_path,
            slug=slug,
            featured_media=featured_media_id,
            categories=category_ids_for_wp if category_ids_for_wp else None,
            tags=tag_ids_for_wp if tag_ids_for_wp else None,
            taxonomy_terms=resolved_terms.taxonomy_terms or None,
            meta=post_meta,
            post_type=settings.wp.post_type,
            run_budget=request.run_budget,
            run_budget_usage=request.run_budget_usage,
        ),
        ctx,
    )
    post_id = create_resp.post_id
    post_url = create_resp.link

    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_complete",
            module=logger.name,
            fields={
                "file_id": file_id,
                "post_id": post_id,
                "post_url": post_url,
            },
        )
    )

    return PublishOutcome(
        schema_version="1.0",
        html_path=request.html_path,
        file_id=file_id,
        status="published",
        post_id=post_id,
        post_url=post_url,
        validation_status="fail" if editorial_issues else "pass",
        validation_issues=editorial_issues,
        publication_outcome="post_created",
        requested_write_count=1,
        actual_write_count=1,
    )


def _editorial_issue(
    *,
    rule_id: str,
    field: str,
    severity: str,
    remediation: str,
) -> str:
    return f"{rule_id}|field={field}|severity={severity}|remediation={remediation}"


def _blocking_editorial_issues(issues: list[str]) -> list[str]:
    return [issue for issue in issues if "|severity=blocker|" in f"{issue}|"]


def _validate_publish_editorial_contract(html_text: str) -> list[str]:
    issues: list[str] = []
    if (
        f'name="editorial-contract-version" content="{EDITORIAL_CONTRACT_VERSION}"'
        not in html_text
    ):
        issues.append(
            _editorial_issue(
                rule_id="editorial.contract_version_missing",
                field="head.meta.editorial-contract-version",
                severity="warning",
                remediation=(
                    "Regenerate the public HTML with the current editorial contract."
                ),
            )
        )
    text_content = _visible_text_for_editorial_checks(html_text)
    lowered_text = text_content.casefold()
    generic_patterns = (
        "valuable insights",
        "in today's rapidly evolving",
        "it is important to note",
        "overall, this report",
    )
    if any(pattern in lowered_text for pattern in generic_patterns):
        issues.append(
            _editorial_issue(
                rule_id="editorial.generic_phrasing",
                field="body",
                severity="blocker",
                remediation=(
                    "Regenerate the affected public copy with source-specific wording."
                ),
            )
        )
    if re.search(
        r"\b(?:canonical_claim_id|report:[a-z0-9_.:-]+|[a-z]+-internal-\d+)\b",
        text_content,
    ):
        issues.append(
            _editorial_issue(
                rule_id="editorial.internal_reference",
                field="body",
                severity="blocker",
                remediation=(
                    "Render public source labels instead of internal claim or "
                    "evidence identifiers."
                ),
            )
        )
    if re.search(
        r"\b(?:will|must|proves?|transform)\b.{0,80}\b(?:without source support|without evidence|unsupported)\b",
        lowered_text,
    ):
        issues.append(
            _editorial_issue(
                rule_id="editorial.unsupported_implication",
                field="body",
                severity="warning",
                remediation=(
                    "Add source support or soften the implication before publishing."
                ),
            )
        )
    if _has_duplicate_sentence(text_content):
        issues.append(
            _editorial_issue(
                rule_id="editorial.duplicate_insight",
                field="body",
                severity="warning",
                remediation="Remove duplicated public insight wording.",
            )
        )
    if re.search(r"\b(?:no caveats|without caveats|no limitations)\b", lowered_text):
        issues.append(
            _editorial_issue(
                rule_id="editorial.missing_caveat",
                field="body",
                severity="warning",
                remediation=(
                    "Restore caveat-aware wording or limitation context for the claim."
                ),
            )
        )
    if re.search(r"\b(?:monitor the trend|act now|take action)\b", lowered_text):
        issues.append(
            _editorial_issue(
                rule_id="editorial.weak_actionability",
                field="body",
                severity="warning",
                remediation="Replace generic action language with a concrete next step.",
            )
        )
    if re.search(
        r"\b(?:revenue|growth|share|market|percentage|metric)\b", lowered_text
    ) and re.search(
        r"\b(?:no metric support|without metric support|without quantified support)\b",
        lowered_text,
    ):
        issues.append(
            _editorial_issue(
                rule_id="editorial.missing_metric_support",
                field="body",
                severity="warning",
                remediation="Attach a source-backed metric or remove the metric claim.",
            )
        )
    if re.search(
        r"\b(?:awesome|everyone must|game[- ]changing|revolutionary)\b", lowered_text
    ):
        issues.append(
            _editorial_issue(
                rule_id="editorial.tone_defect",
                field="body",
                severity="warning",
                remediation="Use neutral, evidence-led editorial tone.",
            )
        )
    return issues


def _visible_text_for_editorial_checks(html_text: str) -> str:
    document = BeautifulSoup(html_text, "html.parser")
    for node in document(("script", "style")):
        node.decompose()
    return html.unescape(" ".join(document.get_text(" ", strip=True).split()))


def _has_duplicate_sentence(text: str) -> bool:
    sentences = [
        sentence.strip().casefold()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if len(sentence.strip()) >= 18
    ]
    seen: set[str] = set()
    for sentence in sentences:
        normalized = re.sub(r"[^a-z0-9 ]+", "", sentence)
        normalized = " ".join(normalized.split())
        if not normalized:
            continue
        if normalized in seen:
            return True
        seen.add(normalized)
    return False


def _load_report_card_manifest(
    html_path: str,
    output_dir: str,
    ctx: RunContext,
) -> ReportCardManifest:
    source = Path(html_path)
    if not source.is_absolute():
        source = Path(output_dir) / source.name
    manifest_path = source.with_suffix("") / "report-card-manifest.json"
    if not file_exists(
        FileExistsRequest(schema_version="1.0", path=str(manifest_path)), ctx
    ).exists:
        raise AppError(
            code="cover_asset_set_incomplete",
            message="Report-card manifest is required before WordPress publication",
            retryable=False,
            context={"expected_path": str(manifest_path)},
        )
    content = read_text(
        ReadTextRequest(schema_version="1.0", path=str(manifest_path)), ctx
    ).content
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="cover_asset_set_incomplete",
            message="Report-card manifest must contain valid JSON",
            cause=exc,
            retryable=False,
            context={"manifest_path": str(manifest_path)},
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="cover_asset_set_incomplete",
            message="Report-card manifest must contain a JSON object",
            retryable=False,
            context={"manifest_path": str(manifest_path)},
        )
    return ReportCardManifest.from_dict(payload)


def _upload_report_card_covers(
    *,
    manifest: ReportCardManifest,
    html_path: str,
    output_dir: str,
    base_url: str,
    auth_header: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    ctx: RunContext,
    sequential: bool = False,
) -> dict[str, int]:
    source = Path(html_path)
    if not source.is_absolute():
        source = Path(output_dir) / source.name
    report_dir = source.with_suffix("").resolve()
    output_root = Path(output_dir).resolve()
    jobs: dict[str, _MediaUploadJob] = {}
    for size in ("small", "medium", "large"):
        asset = getattr(manifest.covers, size)
        asset_path = Path(asset.output_path)
        if asset_path.is_absolute():
            local_path = asset_path.resolve()
        elif asset_path.parts and asset_path.parts[0] == output_root.name:
            local_path = (output_root.parent / asset_path).resolve()
        else:
            local_path = (report_dir / asset_path).resolve()
        try:
            local_path.relative_to(report_dir)
        except ValueError as exc:
            raise AppError(
                code="cover_asset_set_incomplete",
                message="Report-card cover path escapes the report directory",
                cause=exc,
                retryable=False,
                context={"size": size, "output_path": asset.output_path},
            ) from exc
        if not file_exists(
            FileExistsRequest(schema_version="1.0", path=str(local_path)), ctx
        ).exists:
            raise AppError(
                code="cover_asset_set_incomplete",
                message="Report-card cover file is missing",
                retryable=False,
                context={"size": size, "output_path": str(local_path)},
            )
        jobs[size] = _MediaUploadJob(
            src=asset.output_path,
            local_path=str(local_path),
            is_preview=size == "large",
        )
    ids: dict[str, int] = {}
    if sequential:
        for size, job in jobs.items():
            ids[size] = _upload_single_media(
                job=job,
                base_url=base_url,
                auth_header=auth_header,
                ssl_verify=ssl_verify,
                ca_bundle_path=ca_bundle_path,
                ctx=ctx,
            ).media_id
    else:
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_size = {
                executor.submit(
                    _upload_single_media,
                    job=job,
                    base_url=base_url,
                    auth_header=auth_header,
                    ssl_verify=ssl_verify,
                    ca_bundle_path=ca_bundle_path,
                    ctx=ctx,
                ): size
                for size, job in jobs.items()
            }
            for future in as_completed(future_to_size):
                ids[future_to_size[future]] = future.result().media_id
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_report_card_covers_uploaded",
            module=logger.name,
            fields={
                "small_id": ids["small"],
                "medium_id": ids["medium"],
                "large_id": ids["large"],
            },
        )
    )
    return ids


def _upload_briefing_card_covers(
    *,
    card: dict[str, object],
    html_path: str,
    output_dir: str,
    base_url: str,
    auth_header: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    ctx: RunContext,
    sequential: bool = False,
) -> dict[str, int]:
    return _upload_entity_card_covers(
        card=card,
        card_label="Briefing",
        event="publish_briefing_card_covers_uploaded",
        html_path=html_path,
        output_dir=output_dir,
        base_url=base_url,
        auth_header=auth_header,
        ssl_verify=ssl_verify,
        ca_bundle_path=ca_bundle_path,
        ctx=ctx,
        sequential=sequential,
    )


def _upload_signal_card_covers(
    *,
    card: dict[str, object],
    html_path: str,
    output_dir: str,
    base_url: str,
    auth_header: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    ctx: RunContext,
    sequential: bool = False,
) -> dict[str, int]:
    return _upload_entity_card_covers(
        card=card,
        card_label="Signal",
        event="publish_signal_card_covers_uploaded",
        html_path=html_path,
        output_dir=output_dir,
        base_url=base_url,
        auth_header=auth_header,
        ssl_verify=ssl_verify,
        ca_bundle_path=ca_bundle_path,
        ctx=ctx,
        sequential=sequential,
    )


def _upload_entity_card_covers(
    *,
    card: dict[str, object],
    card_label: str,
    event: str,
    html_path: str,
    output_dir: str,
    base_url: str,
    auth_header: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    ctx: RunContext,
    sequential: bool = False,
) -> dict[str, int]:
    covers = card.get("covers")
    if not isinstance(covers, dict):
        raise AppError(
            code="cover_asset_set_incomplete",
            message=f"{card_label} card covers are required",
            retryable=False,
        )
    source_dir = Path(html_path).resolve().parent
    output_root = Path(output_dir).resolve()
    jobs: dict[str, _MediaUploadJob] = {}
    for size in ("small", "medium", "large"):
        raw_path = str(covers.get(size) or "").strip()
        if not raw_path:
            raise AppError(
                code="cover_asset_set_incomplete",
                message=f"{card_label} card covers are required",
                retryable=False,
                context={"size": size},
            )
        asset_path = Path(raw_path)
        candidates = (
            [asset_path.resolve()]
            if asset_path.is_absolute()
            else [
                asset_path.resolve(),
                (source_dir / asset_path).resolve(),
                (output_root / asset_path).resolve(),
                (output_root.parent / asset_path).resolve(),
            ]
        )
        local_path = next(
            (
                candidate
                for candidate in candidates
                if file_exists(
                    FileExistsRequest(schema_version="1.0", path=str(candidate)),
                    ctx,
                ).exists
            ),
            None,
        )
        if local_path is None:
            raise AppError(
                code="cover_asset_set_incomplete",
                message=f"{card_label} card cover file is missing",
                retryable=False,
                context={"size": size, "output_path": raw_path},
            )
        jobs[size] = _MediaUploadJob(
            src=raw_path,
            local_path=str(local_path),
            is_preview=size == "large",
        )
    ids: dict[str, int] = {}
    if sequential:
        for size, job in jobs.items():
            ids[size] = _upload_single_media(
                job=job,
                base_url=base_url,
                auth_header=auth_header,
                ssl_verify=ssl_verify,
                ca_bundle_path=ca_bundle_path,
                ctx=ctx,
            ).media_id
    else:
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_size = {
                executor.submit(
                    _upload_single_media,
                    job=job,
                    base_url=base_url,
                    auth_header=auth_header,
                    ssl_verify=ssl_verify,
                    ca_bundle_path=ca_bundle_path,
                    ctx=ctx,
                ): size
                for size, job in jobs.items()
            }
            for future in as_completed(future_to_size):
                ids[future_to_size[future]] = future.result().media_id
    logger.info(
        log_event(
            ctx,
            role="generator",
            event=event,
            module=logger.name,
            fields={
                "small_id": ids["small"],
                "medium_id": ids["medium"],
                "large_id": ids["large"],
            },
        )
    )
    return ids


def _report_card_post_meta(
    manifest: ReportCardManifest,
    media_ids: dict[str, int],
    *,
    has_public_intelligence: bool = False,
) -> dict[str, object]:
    return {
        "ml_publisher_name": manifest.publisher,
        "ml_time_period": manifest.covered_period,
        "ml_region": manifest.geography_label,
        "ml_public_intelligence": "1" if has_public_intelligence else "0",
        "ml_card_schema_version": manifest.schema_version,
        "ml_card_title_scale": manifest.title_scale,
        "ml_card_tldr_compact": manifest.tldr_compact,
        "ml_card_tldr_standard": manifest.tldr_standard,
        "ml_card_key_insights": list(manifest.key_insights),
        "ml_card_geography_scope": manifest.geography_scope,
        "ml_card_cover_fingerprint": {
            "geometry_family": manifest.fingerprint.geometry_family,
            "seed": manifest.fingerprint.seed,
        },
        "ml_card_cover_small_id": media_ids["small"],
        "ml_card_cover_medium_id": media_ids["medium"],
        "ml_card_cover_large_id": media_ids["large"],
        "ml_source_title": manifest.source_title,
        "ml_source_url": manifest.source_url,
        "ml_source_note": manifest.source_note,
        "ml_source_publication_date": manifest.published_date,
    }


def _has_public_intelligence_surface(html: str) -> bool:
    return (
        "report-intelligence-panel" in html
        or 'id="report-intelligence"' in html
        or "id='report-intelligence'" in html
    )


def _validate_briefing_card(card: dict[str, object]) -> None:
    required_text = (
        "summary_compact",
        "summary_standard",
        "decision_focus",
    )
    missing = [key for key in required_text if not str(card.get(key) or "").strip()]
    raw_takeaways = card.get("takeaways")
    takeaways = (
        [str(value).strip() for value in raw_takeaways]
        if isinstance(raw_takeaways, list)
        else []
    )
    if len(takeaways) != 2 or any(not value for value in takeaways):
        missing.append("takeaways")
    source_count = int(str(card.get("source_count") or 0))
    evidence_count = int(str(card.get("evidence_count") or 0))
    if source_count <= 0:
        missing.append("source_count")
    if evidence_count <= 0:
        missing.append("evidence_count")
    if missing:
        raise AppError(
            code="briefing_card_contract_invalid",
            message="Briefing card metadata is incomplete",
            retryable=False,
            context={"missing_fields": sorted(set(missing))},
        )


def _briefing_card_post_meta(
    card: dict[str, object], media_ids: dict[str, int]
) -> dict[str, object]:
    raw_takeaways = card["takeaways"]
    takeaways = (
        [str(value).strip() for value in raw_takeaways]
        if isinstance(raw_takeaways, list)
        else []
    )
    return {
        "ml_briefing_card_schema_version": "1.0",
        "ml_briefing_card_summary_compact": str(card["summary_compact"]),
        "ml_briefing_card_summary_standard": str(card["summary_standard"]),
        "ml_briefing_card_decision_focus": str(card["decision_focus"]),
        "ml_briefing_card_takeaways": list(takeaways),
        "ml_briefing_source_count": int(str(card["source_count"])),
        "ml_briefing_evidence_count": int(str(card["evidence_count"])),
        "ml_briefing_card_cover_small_id": media_ids["small"],
        "ml_briefing_card_cover_medium_id": media_ids["medium"],
        "ml_briefing_card_cover_large_id": media_ids["large"],
    }


def _validate_signal_card(card: dict[str, object]) -> None:
    required_text = ("summary", "uncertainty")
    missing = [key for key in required_text if not str(card.get(key) or "").strip()]
    try:
        confidence = float(str(card.get("confidence") or ""))
    except (TypeError, ValueError):
        confidence = -1.0
    if confidence < 0 or confidence > 1:
        missing.append("confidence")
    for key in ("source_count", "evidence_count"):
        try:
            value = int(str(card.get(key) or "0"))
        except (TypeError, ValueError):
            value = 0
        if value < 1:
            missing.append(key)
    if missing:
        raise AppError(
            code="signal_card_contract_invalid",
            message="Signal card metadata is incomplete",
            retryable=False,
            context={"missing_fields": sorted(set(missing))},
        )


def _signal_card_post_meta(
    card: dict[str, object], media_ids: dict[str, int]
) -> dict[str, object]:
    return {
        "ml_signal_card_schema_version": "1.0",
        "ml_signal_card_summary": str(card["summary"]),
        "ml_signal_card_uncertainty": str(card["uncertainty"]),
        "ml_signal_card_confidence": float(str(card["confidence"])),
        "ml_signal_source_count": int(str(card["source_count"])),
        "ml_signal_evidence_count": int(str(card["evidence_count"])),
        "ml_signal_card_cover_small_id": media_ids["small"],
        "ml_signal_card_cover_medium_id": media_ids["medium"],
        "ml_signal_card_cover_large_id": media_ids["large"],
    }


def _resolve_html_snapshot(
    request: PublishRequest, ctx: RunContext
) -> tuple[PublishHtmlSnapshot, str]:
    if request.html_snapshot is not None:
        return request.html_snapshot, "request_snapshot"
    if request.html_text is not None:
        return build_publish_html_snapshot(request.html_text), "request_html_text"
    html_text = read_text(
        ReadTextRequest(schema_version="1.0", path=request.html_path), ctx
    ).content
    return build_publish_html_snapshot(html_text), "path"


def _resolve_term_assignments(
    *,
    metadata,
    settings: PublishSettings,
    base_url: str,
    auth_header: str,
    ctx: RunContext,
) -> PublishResolvedTerms:
    category_ids_for_wp: list[int] = []
    tag_ids_for_wp: list[int] = []
    taxonomy_terms: dict[str, list[int]] = {}
    if metadata and metadata.categories:
        mappings_resp = load_category_mappings(
            CategoryMappingLoadRequest(
                schema_version="1.0",
                path=settings.category_mapping_path,
                reload_if_changed=True,
            ),
            ctx,
        )
        id_to_category = {cat.id: cat for cat in mappings_resp.mappings.categories}
        terms = [
            WordPressTaxonomyTerm(
                schema_version="1.1",
                slug=cat_id,
                name=(id_to_category[cat_id].label or cat_id)
                if cat_id in id_to_category
                else cat_id,
                description=id_to_category[cat_id].description
                if cat_id in id_to_category
                else "",
                definition=id_to_category[cat_id].definition
                if cat_id in id_to_category
                else "",
                include_when=list(id_to_category[cat_id].include_when)
                if cat_id in id_to_category
                else [],
                exclude_when=list(id_to_category[cat_id].exclude_when)
                if cat_id in id_to_category
                else [],
                semantics_version=id_to_category[cat_id].schema_version
                if cat_id in id_to_category
                else "",
            )
            for cat_id in metadata.categories
        ]
        if terms:
            ensure_resp = ensure_taxonomy_terms(
                WordPressTaxonomyEnsureRequest(
                    schema_version="1.0",
                    base_url=base_url,
                    auth_header=auth_header,
                    taxonomy_rest_base="categories",
                    terms=terms,
                    ssl_verify=settings.wp.ssl_verify,
                    ca_bundle_path=settings.wp.ca_bundle_path,
                ),
                ctx,
            )
            category_ids_for_wp = [
                ensure_resp.slug_to_id[term.slug]
                for term in terms
                if term.slug in ensure_resp.slug_to_id
            ]
    if metadata and metadata.publisher and metadata.publisher.strip():
        publisher_name = metadata.publisher.strip()
        publisher_slug = slugify(publisher_name)
        if publisher_slug:
            publisher_terms = [
                WordPressTaxonomyTerm(
                    schema_version="1.0",
                    slug=publisher_slug,
                    name=publisher_name,
                )
            ]
            ensure_publishers_resp = ensure_taxonomy_terms(
                WordPressTaxonomyEnsureRequest(
                    schema_version="1.0",
                    base_url=base_url,
                    auth_header=auth_header,
                    taxonomy_rest_base="ml_publisher",
                    terms=publisher_terms,
                    ssl_verify=settings.wp.ssl_verify,
                    ca_bundle_path=settings.wp.ca_bundle_path,
                ),
                ctx,
            )
            publisher_term_ids_for_wp = [
                ensure_publishers_resp.slug_to_id[term.slug]
                for term in publisher_terms
                if term.slug in ensure_publishers_resp.slug_to_id
            ]
            if publisher_term_ids_for_wp:
                taxonomy_terms["ml_publisher"] = publisher_term_ids_for_wp
    if metadata and metadata.taxonomy:
        tag_slugs: list[str] = []
        seen_tag_slugs: set[str] = set()
        for tag in metadata.taxonomy:
            slug = slugify(tag)
            if not slug or slug in seen_tag_slugs:
                continue
            seen_tag_slugs.add(slug)
            tag_slugs.append(slug)
        if tag_slugs:
            ensure_tags_resp = ensure_tags(
                WordPressTagEnsureRequest(
                    schema_version="1.0",
                    base_url=base_url,
                    auth_header=auth_header,
                    tags=tag_slugs,
                    ssl_verify=settings.wp.ssl_verify,
                    ca_bundle_path=settings.wp.ca_bundle_path,
                ),
                ctx,
            )
            tag_ids_for_wp = [
                ensure_tags_resp.slug_to_id[slug]
                for slug in tag_slugs
                if slug in ensure_tags_resp.slug_to_id
            ]
    return PublishResolvedTerms(
        schema_version="1.0",
        category_ids=category_ids_for_wp,
        tag_ids=tag_ids_for_wp,
        taxonomy_terms=taxonomy_terms,
    )


def _upload_images(
    *,
    html_snapshot: PublishHtmlSnapshot,
    html_path: str,
    output_dir: str,
    base_url: str,
    auth_header: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    media_upload_workers: int,
    ctx: RunContext,
) -> Tuple[Dict[str, str], Optional[int]]:
    sources = list(html_snapshot.image_sources)
    if not sources:
        return {}, None

    preview_src = html_snapshot.preview_image_src
    jobs = _collect_media_upload_jobs(
        sources=sources,
        preview_src=preview_src,
        html_path=html_path,
        output_dir=output_dir,
        ctx=ctx,
    )
    if not jobs:
        return {}, None

    max_workers = max(1, min(int(media_upload_workers), len(jobs)))
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_media_upload_plan",
            module=logger.name,
            fields={
                "job_count": len(jobs),
                "worker_count": max_workers,
                "has_preview_src": bool(preview_src),
            },
        )
    )

    results_by_src: Dict[str, _MediaUploadResult] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_job = {
            executor.submit(
                _upload_single_media,
                job=job,
                base_url=base_url,
                auth_header=auth_header,
                ssl_verify=ssl_verify,
                ca_bundle_path=ca_bundle_path,
                ctx=ctx,
            ): job
            for job in jobs
        }
        for future in as_completed(future_to_job):
            result = future.result()
            results_by_src[result.src] = result

    mapping: Dict[str, str] = {}
    media_ids: Dict[str, int] = {}
    featured_media_id: Optional[int] = None
    for job in jobs:
        result = results_by_src[job.src]
        mapping[job.src] = _wordpress_media_proxy_url(result.media_id)
        media_ids[job.src] = result.media_id
        if job.is_preview:
            featured_media_id = result.media_id

    if not featured_media_id and media_ids:
        first_src = sources[0]
        featured_media_id = media_ids.get(first_src)

    return mapping, featured_media_id


def _collect_media_upload_jobs(
    *,
    sources: list[str],
    preview_src: str | None,
    html_path: str,
    output_dir: str,
    ctx: RunContext,
) -> list[_MediaUploadJob]:
    jobs: list[_MediaUploadJob] = []
    seen: set[str] = set()
    for src in sources:
        if src in seen:
            continue
        seen.add(src)
        local_path = _resolve_local_path(src, html_path, output_dir, ctx)
        if not local_path:
            if not src.startswith("http://") and not src.startswith("https://"):
                logger.info(
                    log_event(
                        ctx,
                        role="generator",
                        event="publish_image_missing",
                        module=logger.name,
                        fields={"src": src},
                    )
                )
            continue
        jobs.append(
            _MediaUploadJob(
                src=src,
                local_path=local_path,
                is_preview=bool(preview_src and src == preview_src),
            )
        )
    return jobs


def _upload_single_media(
    *,
    job: _MediaUploadJob,
    base_url: str,
    auth_header: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    ctx: RunContext,
) -> _MediaUploadResult:
    upload_resp = upload_media(
        _media_upload_request(
            job.local_path,
            job.src,
            base_url,
            auth_header,
            ssl_verify,
            ca_bundle_path,
            ctx,
        ),
        ctx,
    )
    return _MediaUploadResult(src=job.src, media_id=upload_resp.media_id)


def _wordpress_media_proxy_url(media_id: int) -> str:
    # Same-origin proxy URLs avoid mixed-scheme failures when WP still emits
    # frontend pages on http while media proxy requests are forced to https.
    return f"/?ml_media={int(media_id)}"


def _media_upload_request(
    local_path: str,
    src: str,
    base_url: str,
    auth_header: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    ctx: RunContext,
) -> WordPressMediaUploadRequest:
    data_resp = read_bytes(ReadBytesRequest(schema_version="1.0", path=local_path), ctx)
    mime_type, _ = mimetypes.guess_type(local_path)
    prepared = prepare_media_upload(
        WordPressMediaPrepareRequest(
            schema_version="1.0",
            filename=Path(local_path).name,
            mime_type=mime_type or "image/png",
            data=data_resp.content,
        ),
        ctx,
    )
    alt_text = Path(src).stem.replace("-", " ")
    return WordPressMediaUploadRequest(
        schema_version="1.0",
        base_url=base_url,
        auth_header=auth_header,
        filename=prepared.filename,
        mime_type=prepared.mime_type,
        data=prepared.data,
        ssl_verify=ssl_verify,
        ca_bundle_path=ca_bundle_path,
        alt_text=alt_text,
    )


def _resolve_local_path(
    src: str,
    html_path: str,
    output_dir: str,
    ctx: RunContext,
) -> Optional[str]:
    parsed = urlparse(src)
    if parsed.scheme in {"http", "https", "data"}:
        return None

    raw_path = unquote((parsed.path or src).strip())
    if not raw_path:
        return None

    normalized = raw_path.replace("\\", "/")
    candidates: list[Path] = []
    candidate_path = Path(normalized)

    if candidate_path.is_absolute():
        candidates.append(candidate_path)

    relative = normalized.lstrip("/")
    if relative:
        candidates.append(Path(output_dir) / relative)
        candidates.append(Path(html_path).resolve().parent / relative)

    for candidate in candidates:
        exists_resp = file_exists(
            FileExistsRequest(schema_version="1.0", path=str(candidate)), ctx
        )
        if exists_resp.exists:
            return str(candidate)

    return None
