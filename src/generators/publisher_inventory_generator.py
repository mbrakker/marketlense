from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from typing import Iterable
from urllib.parse import urljoin, urlsplit

from src.contracts.publisher_inventory import (
    PublisherInventoryBuildRequest,
    PublisherInventoryBuildResponse,
    PublisherInventoryCandidateTrace,
    PublisherInventoryDiffItem,
    PublisherInventoryItem,
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
    PublisherInventorySnapshot,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.publisher_inventory_generator")

_GENERIC_PLACEHOLDER_TITLES = {
    "",
    "download",
    "download now",
    "download pdf",
    "feature img",
    "feature-img",
    "learn more",
    "read",
    "read more",
    "view report",
}


def build_publisher_inventory_snapshot(
    request: PublisherInventoryBuildRequest,
    ctx: RunContext,
) -> PublisherInventoryBuildResponse:
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_build_start",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "insights_url": request.insights_url,
                "normalized_insights_url": request.normalized_insights_url,
                "candidate_count": len(request.candidates),
                "page_count": len(request.pages),
                "has_previous_snapshot": request.previous_snapshot is not None,
                "route_kind": request.route_kind,
            },
        )
    )
    pages = _normalize_pages(request.pages)
    items = _normalize_items(request.candidates)
    if not items:
        raise AppError(
            code="publisher_inventory_empty",
            message="Publisher inventory discovery produced no valid report items",
            retryable=False,
            severity="error",
            context={"insights_url": request.insights_url},
        )
    snapshot = PublisherInventorySnapshot(
        schema_version="1.0",
        publisher_name=request.publisher_name.strip(),
        insights_url=request.insights_url.strip(),
        normalized_insights_url=request.normalized_insights_url.strip(),
        discovered_at_utc=request.discovered_at_utc.strip(),
        route_kind=request.route_kind.strip(),
        route_summary=request.route_summary.strip(),
        final_page_url=request.final_page_url.strip(),
        pages=pages,
        items=items,
    )
    snapshot_json = _serialize_snapshot(snapshot)
    snapshot_sha256 = hashlib.sha256(
        _serialize_stable_snapshot(snapshot).encode("utf-8")
    ).hexdigest()
    current_candidates = _build_candidate_traces(
        raw_candidates=request.candidates,
        normalized_items=items,
    )
    previous_snapshot = request.previous_snapshot
    previous_urls = {
        item.canonical_url for item in (previous_snapshot.items if previous_snapshot else [])
    }
    new_items = [
        PublisherInventoryDiffItem(
            schema_version="1.0",
            canonical_url=item.canonical_url,
            title=item.title,
            discovered_on_page_number=item.discovered_on_page_number,
        )
        for item in items
        if item.canonical_url not in previous_urls
    ]
    response = PublisherInventoryBuildResponse(
        schema_version="1.0",
        snapshot=snapshot,
        new_items=new_items,
        current_report_count=len(items),
        previous_report_count=len(previous_snapshot.items) if previous_snapshot else 0,
        snapshot_sha256=snapshot_sha256,
        snapshot_json=snapshot_json,
        current_candidates=current_candidates,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_build_complete",
            module=logger.name,
            fields={
                "publisher_name": response.snapshot.publisher_name,
                "current_report_count": response.current_report_count,
                "previous_report_count": response.previous_report_count,
                "new_report_count": len(response.new_items),
                "snapshot_sha256": response.snapshot_sha256,
            },
        )
    )
    return response


def parse_publisher_inventory_snapshot(
    snapshot_json: str,
    *,
    source: str,
    ctx: RunContext,
) -> PublisherInventorySnapshot:
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_snapshot_parse_start",
            module=logger.name,
            fields={"source": source},
        )
    )
    try:
        payload = json.loads(snapshot_json)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="publisher_inventory_snapshot_invalid_json",
            message="Publisher inventory snapshot is not valid JSON",
            cause=exc,
            retryable=False,
            severity="error",
            context={"source": source},
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="publisher_inventory_snapshot_invalid_root",
            message="Publisher inventory snapshot root must be a JSON object",
            retryable=False,
            severity="error",
            context={"source": source},
        )
    try:
        pages = [
            PublisherInventoryPage(
                schema_version="1.0",
                page_number=int(page["page_number"]),
                page_url=str(page["page_url"]).strip(),
            )
            for page in payload.get("pages", [])
            if isinstance(page, dict)
        ]
        items = [
            PublisherInventoryItem(
                schema_version="1.0",
                canonical_url=str(item["canonical_url"]).strip(),
                title=str(item["title"]).strip(),
                discovered_on_page_number=int(item["discovered_on_page_number"]),
                pdf_url=(
                    str(item.get("pdf_url")).strip()
                    if item.get("pdf_url") is not None and str(item.get("pdf_url")).strip()
                    else None
                ),
                published_at_text=(
                    str(item.get("published_at_text")).strip()
                    if item.get("published_at_text") is not None
                    and str(item.get("published_at_text")).strip()
                    else None
                ),
            )
            for item in payload.get("items", [])
            if isinstance(item, dict)
        ]
        snapshot = PublisherInventorySnapshot(
            schema_version=str(payload.get("schema_version") or "1.0"),
            publisher_name=str(payload["publisher_name"]).strip(),
            insights_url=str(payload["insights_url"]).strip(),
            normalized_insights_url=str(payload["normalized_insights_url"]).strip(),
            discovered_at_utc=str(payload["discovered_at_utc"]).strip(),
            route_kind=str(payload["route_kind"]).strip(),
            route_summary=str(payload["route_summary"]).strip(),
            final_page_url=str(payload["final_page_url"]).strip(),
            pages=pages,
            items=items,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(
            code="publisher_inventory_snapshot_invalid_payload",
            message="Publisher inventory snapshot payload is invalid",
            cause=exc,
            retryable=False,
            severity="error",
            context={"source": source},
        ) from exc
    if not snapshot.publisher_name or not snapshot.normalized_insights_url or not snapshot.items:
        raise AppError(
            code="publisher_inventory_snapshot_incomplete",
            message="Publisher inventory snapshot is missing required populated fields",
            retryable=False,
            severity="error",
            context={"source": source},
        )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_snapshot_parse_complete",
            module=logger.name,
            fields={
                "source": source,
                "publisher_name": snapshot.publisher_name,
                "item_count": len(snapshot.items),
                "page_count": len(snapshot.pages),
            },
        )
    )
    return snapshot


def _normalize_pages(pages: Iterable[PublisherInventoryPage]) -> list[PublisherInventoryPage]:
    normalized: dict[tuple[int, str], PublisherInventoryPage] = {}
    for page in pages:
        page_url = _normalize_absolute_url(page.page_url)
        page_number = int(page.page_number)
        if page_number <= 0 or not page_url:
            continue
        key = (page_number, page_url)
        normalized[key] = PublisherInventoryPage(
            schema_version="1.0",
            page_number=page_number,
            page_url=page_url,
        )
    ordered = list(normalized.values())
    ordered.sort(key=lambda item: (item.page_number, item.page_url))
    return ordered


def _normalize_items(
    candidates: Iterable[PublisherInventoryRawCandidate],
) -> list[PublisherInventoryItem]:
    normalized_candidates: list[tuple[str, int, str, str, str | None, str | None]] = []
    for candidate in candidates:
        source_page_url = _normalize_absolute_url(candidate.source_page_url)
        canonical_url = _normalize_candidate_url(candidate.url, base_url=source_page_url)
        if not canonical_url:
            continue
        page_number = int(candidate.discovered_on_page_number)
        if page_number <= 0:
            continue
        title = _normalize_title(candidate.title)
        if not title:
            title = _fallback_title_from_url(canonical_url)
        pdf_url_raw = _normalize_candidate_url(candidate.pdf_url, base_url=source_page_url)
        pdf_url = pdf_url_raw or None
        if canonical_url.lower().endswith(".pdf") and not pdf_url:
            pdf_url = canonical_url
        published_at_text = _normalize_optional_text(candidate.published_at_text)
        normalized_candidates.append(
            (
                canonical_url,
                page_number,
                source_page_url,
                title,
                pdf_url,
                published_at_text,
            )
        )
    normalized_candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2],
            item[3],
            item[4] or "",
            item[5] or "",
        )
    )
    aggregated: list[PublisherInventoryItem] = []
    current_url = None
    current_item: PublisherInventoryItem | None = None
    for canonical_url, page_number, _source_page_url, title, pdf_url, published_at_text in normalized_candidates:
        if canonical_url != current_url:
            if current_item is not None:
                aggregated.append(current_item)
            current_url = canonical_url
            current_item = PublisherInventoryItem(
                schema_version="1.0",
                canonical_url=canonical_url,
                title=title,
                discovered_on_page_number=page_number,
                pdf_url=pdf_url,
                published_at_text=published_at_text,
            )
            continue
        assert current_item is not None
        if not current_item.pdf_url and pdf_url:
            current_item = PublisherInventoryItem(
                schema_version=current_item.schema_version,
                canonical_url=current_item.canonical_url,
                title=current_item.title,
                discovered_on_page_number=current_item.discovered_on_page_number,
                pdf_url=pdf_url,
                published_at_text=current_item.published_at_text,
            )
        if not current_item.published_at_text and published_at_text:
            current_item = PublisherInventoryItem(
                schema_version=current_item.schema_version,
                canonical_url=current_item.canonical_url,
                title=current_item.title,
                discovered_on_page_number=current_item.discovered_on_page_number,
                pdf_url=current_item.pdf_url,
                published_at_text=published_at_text,
            )
    if current_item is not None:
        aggregated.append(current_item)
    return aggregated


def _build_candidate_traces(
    *,
    raw_candidates: Iterable[PublisherInventoryRawCandidate],
    normalized_items: Iterable[PublisherInventoryItem],
) -> list[PublisherInventoryCandidateTrace]:
    raw_by_url: dict[
        str, dict[str, object]
    ] = {}
    for candidate in raw_candidates:
        source_page_url = _normalize_absolute_url(candidate.source_page_url)
        canonical_url = _normalize_candidate_url(candidate.url, base_url=source_page_url)
        if not canonical_url:
            continue
        entry = raw_by_url.setdefault(
            canonical_url,
            {
                "source_page_urls": set(),
                "provenances": set(),
                "max_confidence": None,
            },
        )
        if source_page_url:
            cast_source_page_urls = entry["source_page_urls"]
            assert isinstance(cast_source_page_urls, set)
            cast_source_page_urls.add(source_page_url)
        provenance = _normalize_optional_text(candidate.provenance)
        if provenance:
            cast_provenances = entry["provenances"]
            assert isinstance(cast_provenances, set)
            cast_provenances.add(provenance)
        confidence = candidate.confidence
        if confidence is not None:
            current_max = entry["max_confidence"]
            if current_max is None or float(confidence) > float(current_max):
                entry["max_confidence"] = float(confidence)

    traces: list[PublisherInventoryCandidateTrace] = []
    for item in normalized_items:
        details = raw_by_url.get(item.canonical_url, {})
        source_page_urls = sorted(
            str(value).strip()
            for value in details.get("source_page_urls", set())
            if str(value).strip()
        )
        provenances = sorted(
            str(value).strip()
            for value in details.get("provenances", set())
            if str(value).strip()
        )
        max_confidence = details.get("max_confidence")
        traces.append(
            PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url=item.canonical_url,
                title=item.title,
                discovered_on_page_number=item.discovered_on_page_number,
                source_page_urls=source_page_urls,
                discovery_provenances=provenances,
                pdf_url=item.pdf_url,
                published_at_text=item.published_at_text,
                max_confidence=float(max_confidence)
                if max_confidence is not None
                else None,
            )
        )
    return traces


def _normalize_candidate_url(raw_url: str | None, *, base_url: str) -> str:
    token = str(raw_url or "").strip()
    if not token:
        return ""
    absolute = urljoin(base_url or "", token)
    return _normalize_absolute_url(absolute)


def _normalize_absolute_url(raw_url: str) -> str:
    normalized = normalize_url(raw_url)
    parts = urlsplit(normalized)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return normalized


def _normalize_title(title: str) -> str:
    normalized = " ".join(str(title or "").split()).strip()
    lowered = normalized.casefold().replace("_", " ").replace("-", " ")
    lowered = " ".join(lowered.split())
    if lowered in _GENERIC_PLACEHOLDER_TITLES:
        return ""
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    token = " ".join(str(value or "").split()).strip()
    return token or None


def _fallback_title_from_url(url: str) -> str:
    path = urlsplit(url).path.rsplit("/", 1)[-1]
    token = path.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").strip()
    return " ".join(token.split()) or url


def _serialize_snapshot(snapshot: PublisherInventorySnapshot) -> str:
    return json.dumps(asdict(snapshot), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _serialize_stable_snapshot(snapshot: PublisherInventorySnapshot) -> str:
    stable_payload = {
        "schema_version": snapshot.schema_version,
        "publisher_name": snapshot.publisher_name,
        "insights_url": snapshot.insights_url,
        "normalized_insights_url": snapshot.normalized_insights_url,
        "pages": [asdict(page) for page in snapshot.pages],
        "items": [asdict(item) for item in snapshot.items],
    }
    return json.dumps(stable_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
