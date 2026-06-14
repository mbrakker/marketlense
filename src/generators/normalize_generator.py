from __future__ import annotations

import logging
from typing import Any, List

from src.contracts.report_models import Figure, Quote, ReportFigureAsset, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.utils.logging import log_event
from src.utils.coercion import coerce_int, string_value as _s
from src.services.schema_validator_service import validate_schema

logger = logging.getLogger("market_lense.normalize_generator")


def normalize_report(payload: ReportPayload, ctx: RunContext) -> ReportPayload:
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="normalize_report_start",
            module=logger.name,
            fields={"payload": payload.to_dict()},
        )
    )
    normalized = _normalize_report_payload(payload)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="normalize_report_complete",
            module=logger.name,
            fields={"payload": normalized.to_dict()},
        )
    )
    return normalized


def validate_with_schema(payload: dict, schema_name: str, ctx: RunContext) -> None:
    """Validate an arbitrary payload against a named schema."""
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0", payload=payload, schema_name=schema_name
        ),
        ctx,
    )


def _first_text(*values: Any) -> str:
    for value in values:
        text = _s(value).strip()
        if text:
            return text
    return ""


def _primary_figure_asset(
    assets: list[ReportFigureAsset],
) -> ReportFigureAsset | None:
    for asset in assets:
        if bool(asset.is_primary):
            return asset
    return assets[0] if assets else None


def _figure_image_name(*paths: str) -> str:
    for path in paths:
        normalized = _s(path).strip().replace("\\", "/")
        if normalized:
            return normalized.rsplit("/", 1)[-1]
    return ""


def _derive_figure_contract(
    *,
    figure: Figure,
    report_title: str,
    assets: list[ReportFigureAsset],
    figure_top: str,
    figure_image: str,
    enabled: bool,
) -> Figure:
    if not enabled:
        return figure
    primary_asset = _primary_figure_asset(assets)
    asset_page = primary_asset.page if primary_asset is not None else -1
    image_name = _figure_image_name(
        primary_asset.image_path if primary_asset is not None else "",
        figure_top,
        figure_image,
    )
    has_visual = bool(primary_asset or figure_top or figure_image)
    if not has_visual:
        return figure

    source_name = report_title or "source report"
    title = _first_text(
        figure.title,
        primary_asset.display_caption if primary_asset is not None else "",
        primary_asset.generated_caption if primary_asset is not None else "",
        primary_asset.detected_caption if primary_asset is not None else "",
        primary_asset.preview_text[:140] if primary_asset is not None else "",
        f"Figure from {source_name}",
    )
    if asset_page >= 0:
        location = f"page {asset_page + 1}"
    else:
        location = f"the {source_name}"
    evidence = _first_text(
        figure.evidence,
        primary_asset.preview_text if primary_asset is not None else "",
        primary_asset.detected_caption if primary_asset is not None else "",
        primary_asset.display_caption if primary_asset is not None else "",
        primary_asset.generated_caption if primary_asset is not None else "",
        f"Visual asset {image_name} extracted from {location}.",
    )
    return Figure(title=title, evidence=evidence)


def _normalize_report_payload(data: ReportPayload) -> ReportPayload:
    tldr = _s(data.tldr)
    title = _s(data.title).strip()
    commentary = _s(data.commentary)
    source = _s(data.source)
    publisher = _s(data.publisher).strip()
    region = _s(data.region).strip()
    time_period = _s(data.time_period).strip()
    taxonomy_raw = data.taxonomy or []
    taxonomy = []
    seen = set()
    for item in taxonomy_raw:
        item_s = _s(item).strip()
        if not item_s:
            continue
        key = item_s.lower()
        if key in seen:
            continue
        seen.add(key)
        taxonomy.append(item_s)
    categories_raw = data.categories or []
    categories = []
    seen_categories = set()
    for item in categories_raw:
        item_s = _s(item).strip()
        if not item_s:
            continue
        key = item_s.lower()
        if key in seen_categories:
            continue
        seen_categories.add(key)
        categories.append(item_s)

    insights: List[str] = data.insights or []
    if len(insights) < 5:
        insights = insights + [""] * (5 - len(insights))
    insights = insights[:5]
    insights = [_s(insight) for insight in insights]

    quote = Quote(
        text=_s(data.quote.text),
        author=_s(data.quote.author),
    )

    contents_page_number = (
        data.contents_page_number
        if isinstance(data.contents_page_number, int) and data.contents_page_number >= 0
        else 0
    )
    contents_heading = _s(data.contents_heading)

    _figure_gallery = data._figure_gallery or []
    _figure_top = _s(data._figure_top)
    _figure_image = _s(data._figure_image)
    _figure_assets = []
    for asset in getattr(data, "_figure_assets", []) or []:
        if isinstance(asset, ReportFigureAsset):
            _figure_assets.append(asset)
            continue
        if isinstance(asset, dict):
            _figure_assets.append(
                ReportFigureAsset(
                    image_path=_s(asset.get("image_path")).strip(),
                    page=coerce_int(asset.get("page"), -1),
                    candidate_id=_s(asset.get("candidate_id")).strip(),
                    kind=_s(asset.get("kind")).strip() or "image",
                    is_primary=bool(asset.get("is_primary")),
                    detected_caption=_s(asset.get("detected_caption")).strip(),
                    preview_text=_s(asset.get("preview_text")).strip(),
                    generated_caption=_s(asset.get("generated_caption")).strip(),
                    display_caption=_s(asset.get("display_caption")).strip(),
                    caption_source=_s(asset.get("caption_source")).strip(),
                    schema_version=_s(asset.get("schema_version")).strip() or "1.0",
                )
            )
    _figure_section_enabled = bool(getattr(data, "_figure_section_enabled", True))
    _contents_image = _s(data._contents_image)
    _vector_store_id = _s(getattr(data, "_vector_store_id", "")).strip()
    evidence_packs_raw = getattr(data, "_evidence_packs", {})
    _evidence_packs = (
        dict(evidence_packs_raw) if isinstance(evidence_packs_raw, dict) else {}
    )
    text_density_raw = getattr(data, "_text_density", 0.0)
    _text_density = (
        float(text_density_raw) if isinstance(text_density_raw, (int, float)) else 0.0
    )
    _text_pages_sampled = max(0, coerce_int(getattr(data, "_text_pages_sampled", 0), 0))
    _text_char_count = max(0, coerce_int(getattr(data, "_text_char_count", 0), 0))
    _text_not_available = bool(getattr(data, "_text_not_available", False))
    schema_version = _s(getattr(data, "schema_version", "")).strip() or "1.1"

    if not _figure_top and _figure_image:
        _figure_top = _figure_image
    figure = _derive_figure_contract(
        figure=Figure(
            title=_s(data.figure.title).strip(),
            evidence=_s(data.figure.evidence).strip(),
        ),
        report_title=title,
        assets=_figure_assets,
        figure_top=_figure_top,
        figure_image=_figure_image,
        enabled=_figure_section_enabled,
    )

    return ReportPayload(
        tldr=tldr,
        title=title,
        insights=insights,
        quote=quote,
        figure=figure,
        publisher=publisher,
        taxonomy=taxonomy,
        categories=categories,
        region=region,
        time_period=time_period,
        commentary=commentary,
        source=source,
        _figure_image=_figure_image,
        _figure_gallery=_figure_gallery,
        _figure_top=_figure_top,
        _figure_assets=_figure_assets,
        _figure_section_enabled=_figure_section_enabled,
        contents_page_number=contents_page_number,
        contents_heading=contents_heading,
        _contents_image=_contents_image,
        _vector_store_id=_vector_store_id,
        _evidence_packs=_evidence_packs,
        _text_density=_text_density,
        _text_pages_sampled=_text_pages_sampled,
        _text_char_count=_text_char_count,
        _text_not_available=_text_not_available,
        schema_version=schema_version,
    )
