"""Deterministic publication-date extraction from already captured browser HTML."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from html.parser import HTMLParser

from src.contracts.report_store import (
    SourcePublicationMetadata,
    SourcePublicationMetadataExtractionRequest,
    SourcePublicationMetadataExtractionResponse,
    SourcePublicationObservedValue,
)

_DATE_PATTERN = re.compile(
    r"^(?P<year>\d{4})(?:-(?P<month>\d{2})(?:-(?P<day>\d{2}))?)?"
)
_META_DATE_NAMES = {
    "datepublished",
    "date_published",
    "publication_date",
    "publish-date",
    "published_at",
}
_PRECISION_ORDER = {"year": 1, "month": 2, "day": 3}
_KIND_ORDER = {
    "json_ld_date_published": 0,
    "open_graph_article_published_time": 1,
    "html_meta_published_time": 2,
    "visible_publication_label": 3,
}


class _SourcePublicationHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._script_index = -1
        self._active_json_ld_index: int | None = None
        self._active_json_ld_parts: list[str] = []
        self.meta_candidates: list[tuple[str, str, str]] = []
        self.visible_candidates: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {
            str(key).casefold(): str(value or "").strip() for key, value in attrs
        }
        if tag.casefold() == "script":
            self._script_index += 1
            if attributes.get("type", "").casefold() == "application/ld+json":
                self._active_json_ld_index = self._script_index
                self._active_json_ld_parts = []
            return
        if tag.casefold() == "meta":
            raw_value = attributes.get("content", "")
            property_name = attributes.get("property", "").casefold()
            name = attributes.get("name", "").casefold()
            if property_name == "article:published_time":
                self.meta_candidates.append(
                    (
                        "open_graph_article_published_time",
                        "meta[property=article:published_time]",
                        raw_value,
                    )
                )
            elif name in _META_DATE_NAMES:
                self.meta_candidates.append(
                    ("html_meta_published_time", f"meta[name={name}]", raw_value)
                )
            return
        if tag.casefold() == "time":
            raw_value = attributes.get("datetime", "")
            semantic_text = " ".join(
                attributes.get(key, "")
                for key in ("class", "id", "itemprop", "aria-label")
            ).casefold()
            if raw_value and "publish" in semantic_text:
                self.visible_candidates.append(("time[publication]", raw_value))

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._active_json_ld_index is not None:
            self.meta_candidates.extend(
                _json_ld_candidates(
                    "".join(self._active_json_ld_parts), self._active_json_ld_index
                )
            )
            self._active_json_ld_index = None
            self._active_json_ld_parts = []

    def handle_data(self, data: str) -> None:
        if self._active_json_ld_index is not None:
            self._active_json_ld_parts.append(data)


def _json_ld_candidates(raw_json: str, script_index: int) -> list[tuple[str, str, str]]:
    try:
        payload = json.loads(raw_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    candidates: list[tuple[str, str, str]] = []

    def visit(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if str(key).casefold() == "datepublished" and isinstance(child, str):
                    candidates.append(("json_ld_date_published", child_path, child))
                visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(payload, f"json_ld[{script_index}]")
    return candidates


def _normalize_publication_date(value: str) -> tuple[str, str]:
    match = _DATE_PATTERN.match(str(value or "").strip())
    if match is None:
        return "", ""
    year = int(match.group("year"))
    month = match.group("month")
    day = match.group("day")
    try:
        if day is not None:
            date(year, int(month or 0), int(day))
            return f"{year:04d}-{int(month):02d}-{int(day):02d}", "day"
        if month is not None:
            if not 1 <= int(month) <= 12:
                return "", ""
            return f"{year:04d}-{int(month):02d}", "month"
        return f"{year:04d}", "year"
    except ValueError:
        return "", ""


def _observation(
    *,
    source_url: str,
    retrieved_at_utc: str,
    evidence_kind: str,
    evidence_locator: str,
    raw_value: str,
) -> SourcePublicationObservedValue:
    normalized, precision = _normalize_publication_date(raw_value)
    return SourcePublicationObservedValue(
        schema_version="1.0",
        publication_date=normalized,
        publication_date_precision=precision,
        source_url=source_url,
        retrieved_at_utc=retrieved_at_utc,
        evidence_kind=evidence_kind,
        evidence_locator=evidence_locator,
        evidence_value_hash=hashlib.sha256(
            str(raw_value or "").strip().encode("utf-8")
        ).hexdigest(),
        evidence_status="verified" if normalized else "invalid",
    )


def _dates_are_compatible(left: str, right: str) -> bool:
    return left == right or left.startswith(f"{right}-") or right.startswith(f"{left}-")


def _select_metadata(
    observations: tuple[SourcePublicationObservedValue, ...],
    *,
    source_url: str,
    retrieved_at_utc: str,
) -> SourcePublicationMetadata:
    verified = [
        observation
        for observation in observations
        if observation.evidence_status == "verified" and observation.publication_date
    ]
    conflicting = any(
        not _dates_are_compatible(left.publication_date, right.publication_date)
        for index, left in enumerate(verified)
        for right in verified[index + 1 :]
    )
    selected = (
        min(
            verified,
            key=lambda item: (
                _KIND_ORDER.get(item.evidence_kind, 99),
                -_PRECISION_ORDER.get(item.publication_date_precision, 0),
                item.publication_date,
                item.evidence_locator,
            ),
        )
        if verified
        else next(
            (item for item in observations if item.evidence_status == "invalid"), None
        )
    )
    status = (
        "conflicting"
        if conflicting
        else "verified"
        if verified
        else "invalid"
        if observations
        else "unknown"
    )
    return SourcePublicationMetadata(
        schema_version="1.0",
        publication_date=selected.publication_date if selected else "",
        publication_date_precision=(
            selected.publication_date_precision if selected else ""
        ),
        source_url=selected.source_url if selected else source_url,
        retrieved_at_utc=selected.retrieved_at_utc if selected else retrieved_at_utc,
        evidence_kind=selected.evidence_kind if selected else "",
        evidence_locator=selected.evidence_locator if selected else "",
        evidence_value_hash=selected.evidence_value_hash if selected else "",
        evidence_status=status,
        contradiction_status="conflicting"
        if conflicting
        else "none"
        if verified
        else "not_applicable",
        observed_values=observations,
    )


def extract_source_publication_metadata(
    request: SourcePublicationMetadataExtractionRequest,
) -> SourcePublicationMetadataExtractionResponse:
    """Read only structured publisher metadata from an existing HTML capture."""
    parser = _SourcePublicationHtmlParser()
    parser.feed(request.html)
    parser.close()
    candidates = [
        *parser.meta_candidates,
        *(
            ("visible_publication_label", locator, value)
            for locator, value in parser.visible_candidates
        ),
    ]
    observations = tuple(
        _observation(
            source_url=request.source_url,
            retrieved_at_utc=request.retrieved_at_utc,
            evidence_kind=kind,
            evidence_locator=locator,
            raw_value=value,
        )
        for kind, locator, value in candidates
        if str(value or "").strip()
    )
    return SourcePublicationMetadataExtractionResponse(
        schema_version="1.0",
        metadata=_select_metadata(
            observations,
            source_url=request.source_url,
            retrieved_at_utc=request.retrieved_at_utc,
        ),
    )
