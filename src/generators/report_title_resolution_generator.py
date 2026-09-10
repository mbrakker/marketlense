"""Deterministic report-title identity resolution with bounded ambiguity fallback."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from pathlib import PurePath
from typing import Any

from src.contracts.report_identity import ReportTitleCandidate, ReportTitleResolution

_GENERIC_TITLES = frozenset(
    {
        "document",
        "guide",
        "microsoft powerpoint",
        "microsoft word",
        "pdf",
        "powerpoint presentation",
        "presentation",
        "report",
        "slide deck",
        "untitled",
    }
)
_IDENTIFIER_ONLY = re.compile(
    r"^(?:source[-_:])?[a-f0-9]{24,}(?:[-_.](?:pdf|report))?$", re.IGNORECASE
)
_INTERNAL_IDENTIFIER_ONLY = re.compile(
    r"^(?:file|doc|document|report|presentation|pptx?|pdf)[-_:]?(?:id[-_:]?)?[a-z0-9]{6,}$",
    re.IGNORECASE,
)
_UUID_ONLY = re.compile(
    r"^[a-f0-9]{8}(?:[-_][a-f0-9]{4}){3}[-_][a-f0-9]{12}$", re.IGNORECASE
)
_OPAQUE_ALPHANUMERIC_IDENTIFIER = re.compile(r"^[a-z0-9]{20,}$", re.IGNORECASE)
_NUMERIC_LED_OPAQUE_IDENTIFIER = re.compile(r"^\d[a-z0-9_-]{19,}$", re.IGNORECASE)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_TITLE_SIGNAL = re.compile(
    r"\b(?:report|benchmark|outlook|study|guide|index|review|survey|barometer)\b",
    re.IGNORECASE,
)
_REPORT_IDENTITY_SIGNAL = re.compile(
    r"\b(?:report|benchmark|outlook|index|review|survey|barometer)\b",
    re.IGNORECASE,
)
_SOURCE_TITLE = re.compile(
    r"(?:edition of\s+)?(?P<title>[A-Za-z0-9&'’:\- ]{3,100}?"
    r"(?:Benchmark|Outlook|Study|Guide|Index|Review|Survey|Barometer)"
    r"(?:\s+Report)?)\b",
    re.IGNORECASE,
)
_SOURCE_CONTEXT_TITLE = re.compile(
    r"\b(?:our|the)\s+(?P<title>[A-Z][A-Za-z0-9&'’:\- ]{3,80}?"
    r"(?:Guide|Report|Benchmark|Outlook|Study|Index|Review|Survey|Barometer)"
    r"(?:\s+to\s+(?:19|20)\d{2})?)\b",
    re.IGNORECASE,
)
_COLONED_EDITION_TITLE = re.compile(
    r"\b(?P<title>[A-Z][A-Za-z0-9&'’\- ]{3,70}:\s*"
    r"(?:Guide|Report|Benchmark|Outlook|Study|Index|Review|Survey|Barometer)"
    r"\s+to\s+(?:19|20)\d{2})\b"
)
_DATE_BYLINE = re.compile(
    r"^\d{1,2}\s+(?:january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+(?:19|20)\d{2}\b",
    re.IGNORECASE,
)
_FILENAME_TRAILING_DATE_OR_LABEL = re.compile(
    r"(?:\s+(?:(?:19|20)\d{2}\s+\d{1,2}\s+\d{1,2}|"
    r"(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+(?:\d{1,2}|(?:19|20)?\d{2})|"
    r"(?:updated|final|download)|v\d+))+$",
    re.IGNORECASE,
)
_WEAK_TITLE = re.compile(
    r"^(?:\d+\s+)?(?:quarterly\s+)?benchmarks?(?:\s+report)?(?:\s*[|:-].*)?$",
    re.IGNORECASE,
)
_SOURCE_WEIGHTS = {
    "cover_title_page": 1000.0,
    "repeated_header_title": 800.0,
    "source_content": 650.0,
    "filename": 400.0,
    "document_metadata": 150.0,
}


def is_generic_report_title(value: object) -> bool:
    normalized = _normalized(value)
    if not normalized or normalized in _GENERIC_TITLES:
        return True
    return bool(
        _IDENTIFIER_ONLY.fullmatch(normalized)
        or _INTERNAL_IDENTIFIER_ONLY.fullmatch(normalized)
        or _UUID_ONLY.fullmatch(normalized)
        or _OPAQUE_ALPHANUMERIC_IDENTIFIER.fullmatch(normalized)
        or _NUMERIC_LED_OPAQUE_IDENTIFIER.fullmatch(normalized)
    )


def resolve_report_title(
    *,
    file_name: str,
    pdf_metadata: Mapping[str, object] | None,
    pages: Iterable[tuple[int, str]],
    publisher_name: str = "",
    identity_resolver: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> ReportTitleResolution:
    """Resolve public report identity without allowing document metadata to dominate.

    The optional resolver is intentionally called once, only for materially
    conflicting deterministic candidates. Its output remains validated against
    the bounded candidate evidence below.
    """

    publisher = _clean(publisher_name)
    page_items = [
        (int(number), _page_text(text)) for number, text in pages if _page_text(text)
    ]
    candidates = _candidates(
        file_name=file_name,
        pdf_metadata=pdf_metadata or {},
        pages=page_items,
        publisher_name=publisher,
    )
    ranked = tuple(
        sorted(candidates, key=lambda item: (-item.score, item.value.casefold()))
    )
    explicit = next(
        (item.value for item in ranked if item.source == "cover_title_page"), ""
    )
    if not ranked:
        return ReportTitleResolution(
            explicit_source_title=explicit,
            candidates=ranked,
            issues=("generic_title_missing",),
        )
    chosen = ranked[0]
    ambiguous = _is_ambiguous(ranked)
    if ambiguous and identity_resolver is not None:
        response = identity_resolver(
            {
                "filename": _clean(file_name),
                "document_metadata": {
                    str(key): _clean(value)
                    for key, value in (pdf_metadata or {}).items()
                    if _clean(value)
                },
                "first_pages": [
                    {"page_number": page_number, "text": text[:4000]}
                    for page_number, text in page_items[:3]
                ],
                "candidates": [
                    {
                        "title": item.value,
                        "source": item.source,
                        "page_number": item.page_number,
                        "evidence": item.evidence,
                    }
                    for item in ranked[:8]
                ],
            }
        )
        resolved = _clean(response.get("title") if isinstance(response, dict) else "")
        if resolved and not is_generic_report_title(resolved):
            return ReportTitleResolution(
                title=resolved,
                edition=_clean(
                    response.get("edition") if isinstance(response, dict) else ""
                )
                or _edition(resolved),
                publisher_candidate=_clean(
                    response.get("publisher_candidate")
                    if isinstance(response, dict)
                    else ""
                )
                or publisher,
                confidence=_confidence(
                    response.get("confidence")
                    if isinstance(response, dict)
                    else "medium"
                ),
                evidence=tuple(
                    _clean(item)
                    for item in _identity_evidence_items(response)
                    if _clean(item)
                )[:4],
                candidate_source="llm_identity_resolution",
                explicit_source_title=explicit,
                candidates=ranked,
            )
    return ReportTitleResolution(
        title=chosen.value,
        edition=_edition(chosen.value),
        publisher_candidate=publisher,
        confidence="high"
        if chosen.source in {"cover_title_page", "repeated_header_title"}
        else "medium",
        evidence=(chosen.evidence,) if chosen.evidence else (),
        candidate_source=chosen.source,
        explicit_source_title=explicit,
        candidates=ranked,
        issues=("title_candidates_ambiguous",) if ambiguous else (),
    )


def _identity_evidence_items(response: object) -> list[object]:
    if not isinstance(response, dict):
        return []
    evidence = response.get("evidence")
    return evidence if isinstance(evidence, list) else []


def _candidates(
    *,
    file_name: str,
    pdf_metadata: Mapping[str, object],
    pages: list[tuple[int, str]],
    publisher_name: str,
) -> list[ReportTitleCandidate]:
    candidates: list[ReportTitleCandidate] = []
    for page_number, page_text in pages:
        lines = [
            line for line in (_clean(line) for line in page_text.splitlines()) if line
        ]
        if page_number == 1:
            for title in _cover_titles(lines, publisher_name):
                candidates.append(
                    _candidate(title, "cover_title_page", page_number, publisher_name)
                )
        else:
            for title in _source_titles(page_text, publisher_name):
                source = (
                    "repeated_header_title"
                    if _appears_on_multiple_pages(title, pages)
                    else "source_content"
                )
                candidates.append(
                    _candidate(title, source, page_number, publisher_name)
                )
            for line in lines[:3]:
                if (
                    _looks_like_title(line)
                    and _has_title_case_shape(line)
                    and _appears_on_multiple_pages(line, pages)
                ):
                    candidates.append(
                        _candidate(
                            line, "repeated_header_title", page_number, publisher_name
                        )
                    )
    filename_title = _filename_title(file_name)
    if filename_title:
        candidates.append(_candidate(filename_title, "filename", 0, publisher_name))
    metadata_title = _clean(
        pdf_metadata.get("Title") or pdf_metadata.get("title") or ""
    )
    if metadata_title and not is_generic_report_title(metadata_title):
        candidates.append(
            _candidate(metadata_title, "document_metadata", 0, publisher_name)
        )
    return _deduplicate(candidates, filename_title, pages)


def _cover_titles(lines: list[str], publisher_name: str) -> list[str]:
    title_lines = [
        line for line in lines[:6] if not re.match(r"(?:https?://|www\.)", line)
    ]
    values: list[str] = []
    combined = ""
    for line in title_lines:
        if re.fullmatch(r"\d+", line) and not combined:
            continue
        if combined and _edition(combined) and not _is_cover_subtitle(line):
            break
        if not combined and _is_cover_brand_line(line, publisher_name):
            continue
        if combined and _is_cover_brand_line(line, publisher_name):
            break
        if not combined and not _looks_like_cover_title(line):
            continue
        if _is_cover_boundary(line):
            break
        combined = _clean(f"{combined} {line}")
        if _looks_like_cover_title(combined) and not _is_cover_brand_line(
            combined, publisher_name
        ):
            values.append(combined)
    return values


def _source_titles(page_text: str, publisher_name: str) -> list[str]:
    values = []
    # A source title can appear as a standalone contents/header line after an
    # image-only cover. Keep that full visible line so punctuation and the
    # words following "Guide to" do not get truncated by a prose-oriented
    # title pattern.
    for line in page_text.splitlines():
        value = _clean(line)
        if (
            re.search(r"\bguide\s+to\b", value, re.IGNORECASE)
            and _looks_like_title(value)
            and _has_title_case_shape(value)
        ):
            values.append(value)
    for match in (
        *_COLONED_EDITION_TITLE.finditer(page_text),
        *_SOURCE_CONTEXT_TITLE.finditer(page_text),
        *_SOURCE_TITLE.finditer(page_text),
    ):
        value = re.sub(
            r"^.*?\bedition of\s+",
            "",
            _clean(match.group("title")),
            flags=re.IGNORECASE,
        )
        value = _strip_publisher_prefix(value, publisher_name)
        if _looks_like_title(value) and _has_title_case_shape(value):
            values.append(value)
    return values


def _candidate(
    value: str, source: str, page_number: int, publisher_name: str
) -> ReportTitleCandidate:
    score = _SOURCE_WEIGHTS[source]
    if page_number == 1:
        score += 80.0
    if _edition(value):
        score += 45.0
    if _REPORT_IDENTITY_SIGNAL.search(value):
        score += 120.0
    if value.casefold().endswith(" report"):
        score += 40.0
    if source == "cover_title_page":
        score += min(len(value.split()), 10)
    if re.search(r":\s*(?:guide|report)\s+to\s+(?:19|20)\d{2}\b", value, re.I):
        score += 120.0
    if publisher_name and publisher_name.casefold() in value.casefold():
        score += 20.0
    return ReportTitleCandidate(
        value=value,
        source=source,
        score=score,
        page_number=page_number,
        evidence=(f"page:{page_number}" if page_number else source),
    )


def _deduplicate(
    candidates: list[ReportTitleCandidate],
    filename_title: str,
    pages: list[tuple[int, str]],
) -> list[ReportTitleCandidate]:
    deduped: dict[str, ReportTitleCandidate] = {}
    filename_year = _edition(filename_title)
    page_years = {page_number: _page_edition(text) for page_number, text in pages}
    for candidate in candidates:
        if is_generic_report_title(candidate.value):
            continue
        value = candidate.value
        edition = filename_year or page_years.get(candidate.page_number, "")
        if (
            candidate.source in {"source_content", "repeated_header_title"}
            and edition
            and not _edition(value)
            # A full "Guide to …" heading is self-contained; a date elsewhere
            # on the same contents/header page is publication context, not a
            # missing title edition.
            and not re.search(r"\bguide\s+to\b", value, re.IGNORECASE)
        ):
            value = _insert_edition(value, edition)
            candidate = replace(candidate, value=value, score=candidate.score + 45.0)
        key = _normalized(value)
        current = deduped.get(key)
        if current is None or candidate.score > current.score:
            deduped[key] = candidate
    return [
        candidate
        for key, candidate in deduped.items()
        if not any(
            _is_title_prefix(key, other_key)
            for other_key, other in deduped.items()
            if other_key != key and other.source != "document_metadata"
        )
    ]


def _is_title_prefix(shorter: str, longer: str) -> bool:
    short_key = _YEAR.sub("", shorter.replace(":", "")).strip()
    long_key = _YEAR.sub("", longer.replace(":", "")).strip()
    return len(long_key) > len(short_key) and long_key.startswith(f"{short_key} ")


def _appears_on_multiple_pages(title: str, pages: list[tuple[int, str]]) -> bool:
    key = _normalized(title)
    return sum(key in _normalized(text) for _, text in pages) > 1


def _is_ambiguous(candidates: tuple[ReportTitleCandidate, ...]) -> bool:
    substantive = [item for item in candidates if item.source != "document_metadata"]
    if len(substantive) < 2:
        return False
    first, second = substantive[:2]
    if first.source == "cover_title_page":
        return False
    return (
        _normalized(first.value) != _normalized(second.value)
        and abs(first.score - second.score) <= 80
    )


def _looks_like_title(value: str) -> bool:
    cleaned = _clean(value)
    if is_generic_report_title(cleaned) or len(cleaned) < 4 or len(cleaned) > 120:
        return False
    if (
        len(cleaned) > 80
        or len(cleaned.split()) > 14
        or re.search(r"[.!?]", cleaned)
        or not re.match(r"(?:[A-Z0-9]|\")", cleaned)
        or _DATE_BYLINE.search(cleaned)
        or cleaned.casefold().startswith(
            (
                "as ",
                "base:",
                "method:",
                "source:",
                "the global ",
                "this guide",
                "your guide",
                "welcome ",
            )
        )
        or _WEAK_TITLE.fullmatch(cleaned)
    ):
        return False
    return bool(_TITLE_SIGNAL.search(cleaned) or _YEAR.search(cleaned))


def _looks_like_cover_title(value: str) -> bool:
    cleaned = _clean(value)
    if _looks_like_title(cleaned):
        return True
    return bool(
        4 <= len(cleaned) <= 80
        and len(cleaned.split()) <= 12
        and re.match(r"[A-Z]", cleaned)
        and not is_generic_report_title(cleaned)
        and "." not in cleaned
        and not _DATE_BYLINE.search(cleaned)
        and not _WEAK_TITLE.fullmatch(cleaned)
        and (
            _has_title_case_shape(cleaned)
            or len(cleaned.split()) == 1
            or "?" in cleaned
            or bool(_TITLE_SIGNAL.search(cleaned) or _YEAR.search(cleaned))
        )
    )


def _has_title_case_shape(value: str) -> bool:
    """Reject sentence fragments that happen to end in a report-like noun."""

    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", value)
    if not words:
        return False
    title_words = sum(word[0].isupper() for word in words)
    return title_words >= 2 and title_words / len(words) >= 0.5


def _is_cover_boundary(value: str) -> bool:
    normalized = _clean(value)
    return bool(
        not normalized
        or normalized.startswith("/")
        or normalized.casefold().startswith(
            ("advertisement", "base:", "discover ", "premier partners")
        )
        or (
            len(normalized) > 28
            and normalized.isupper()
            and not (_TITLE_SIGNAL.search(normalized) or _YEAR.search(normalized))
        )
    )


def _is_cover_subtitle(value: str) -> bool:
    return bool(value.isupper() and 1 <= len(value.split()) <= 4)


def _is_cover_brand_line(value: str, publisher_name: str) -> bool:
    normalized = _clean(value)
    compact = normalized.replace(" ", "")
    if publisher_name and _normalized(normalized) == _normalized(publisher_name):
        return True
    if re.fullmatch(r"(?:[A-Z]\s+){3,}[A-Z]", normalized):
        return True
    words = re.findall(r"[A-Za-z0-9]+", normalized)
    if (
        2 <= len(words) <= 4
        and re.fullmatch(r"[A-Z]{2,8}", words[0])
        and not (_TITLE_SIGNAL.search(normalized) or _YEAR.search(normalized))
    ):
        return True
    return bool(
        normalized.isupper()
        and not (_TITLE_SIGNAL.search(normalized) or _YEAR.search(normalized))
        and re.search(r"(?:consulting|group|inc|ltd|llc|company)$", compact, re.I)
    )


def _page_edition(text: str) -> str:
    years = Counter(match.group(0) for match in _YEAR.finditer(text))
    if not years:
        return ""
    return sorted(years, key=lambda year: (-years[year], year), reverse=False)[0]


def _filename_title(file_name: str) -> str:
    raw = PurePath(_clean(file_name).replace("\\", "/")).name
    raw = re.sub(r"\.(?:pdf|docx?|pptx?)$", "", raw, flags=re.IGNORECASE)
    if is_generic_report_title(raw):
        return ""
    raw = _clean(re.sub(r"[._-]+", " ", raw))
    raw = _clean(_FILENAME_TRAILING_DATE_OR_LABEL.sub("", raw))
    return "" if is_generic_report_title(raw) else raw


def _insert_edition(value: str, edition: str) -> str:
    if value.casefold().endswith(" report"):
        return f"{value[:-7].rstrip()} {edition} Report"
    return f"{value} {edition}"


def _strip_publisher_prefix(value: str, publisher_name: str) -> str:
    if not publisher_name:
        return value
    pattern = re.compile(rf"^{re.escape(publisher_name)}(?:'s|’s)?\s+", re.IGNORECASE)
    return _clean(pattern.sub("", value))


def _edition(value: str) -> str:
    match = _YEAR.search(value)
    return match.group(0) if match else ""


def _normalized(value: object) -> str:
    return _clean(value).casefold()


def _clean(value: object) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").split()).strip(" -–—:;")


def _page_text(value: object) -> str:
    return "\n".join(
        line
        for line in (_clean(line) for line in str(value or "").splitlines())
        if line
    )


def _confidence(value: object) -> str:
    normalized = _normalized(value)
    return normalized if normalized in {"high", "medium", "low"} else "medium"


__all__ = ["is_generic_report_title", "resolve_report_title"]
