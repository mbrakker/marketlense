"""Deterministic publisher-imprint extraction from bounded document-pack text."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Mapping

_EXPLICIT_IMPRINT_PATTERNS = (
    re.compile(r"^\s*published\s+by\s*[:\-]?\s*(?P<value>[^\r\n]{2,96})", re.I),
    re.compile(r"^\s*a\s+report\s+by\s*[:\-]?\s*(?P<value>[^\r\n]{2,96})", re.I),
    re.compile(
        r"^\s*(?:copyright\s*)?(?:©|\(c\))\s*"
        r"(?:\d{4}(?:\s*[-–]\s*\d{4})?\s*)?(?P<value>[^\r\n]{2,96})",
        re.I,
    ),
)
_HEADER_DOMAIN_PATTERN = re.compile(
    r"^www\.(?P<domain>[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+)$",
    re.I,
)
_PLACEHOLDERS = {"", "unknown", "not specified", "n/a", "na"}
_TITLE_SEPARATOR = re.compile(r"\s*(?:[|—–]|\ufffd)\s*")
_PUBLISHER_LINE = re.compile(
    r"^\s*(?:published\s+by|a\s+report\s+by)\s*[:\-]?\s*(?P<value>[^\r\n]{2,96})",
    re.I,
)
_BYLINE_LINE = re.compile(
    r"^\s*(?:by|author|written\s+by)\s*[:\-]?\s*(?P<value>[^\r\n]{2,96})",
    re.I,
)
_DATED_BYLINE = re.compile(
    r"^\s*\d{1,2}\s+[A-Z]{3,9}\s+\d{4}\s*(?:[·•—–]|\ufffd)\s*(?P<value>[A-Z][A-Z .'-]{2,96})\s*$",
    re.I,
)
_COPYRIGHT = re.compile(
    r"(?:copyright\s*)?(?:©|\(c\)|\ufffd)\s*(?:\d{4}(?:\s*[-–]\s*\d{4})?\s*)?(?P<value>[^\r\n]{2,96})",
    re.I,
)
_PROVIDER_PATTERNS = (
    re.compile(r"\b(?P<value>[A-Z][A-Za-z0-9&.' -]{1,80}?)\s+analysis\b"),
    re.compile(
        r"\bdata\s+(?:from|published\s+by)\s+(?P<value>[A-Z][A-Za-z0-9&.' -]{1,80}?)(?:\s+(?:show|shows|indicate|indicates|reveal|reveals|support|supports|suggest|suggests)\b|[.\n]|$)",
        re.I,
    ),
    re.compile(
        r"^\s*source\s*:\s*(?P<value>[A-Z][A-Za-z0-9&.' -]{1,80})\s*$",
        re.I | re.M,
    ),
)


@dataclass(frozen=True)
class PublisherImprintObservation:
    publisher_name: str
    evidence_locator: str
    evidence_hash: str
    resolution_method: str = "document_imprint_extraction"


@dataclass(frozen=True)
class ProvenanceEvidence:
    """One bounded, source-visible role assertion."""

    role: str
    name: str
    evidence_kind: str
    evidence_locator: str
    evidence_hash: str


@dataclass(frozen=True)
class SourceProvenanceObservation:
    """Deterministic source-visible publication roles, all optional."""

    publication_name: str = ""
    publisher_name: str = ""
    author_names: tuple[str, ...] = ()
    author_kind: str = "unknown"
    data_provider_names: tuple[str, ...] = ()
    source_organization_names: tuple[str, ...] = ()
    report_owner_name: str = ""
    status: str = "ambiguous"
    resolution_method: str = "deterministic_source_visible_evidence"
    issues: tuple[str, ...] = ()
    evidence: tuple[ProvenanceEvidence, ...] = ()


def _normalize_candidate(value: str) -> str:
    normalized = " ".join(value.split())
    normalized = re.split(
        r"\s+(?:all rights reserved|©|copyright)\b",
        normalized,
        maxsplit=1,
        flags=re.I,
    )[0]
    return normalized.strip(" .,:;—–-")


def _hash_evidence(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean_role_name(value: str) -> str:
    cleaned = _normalize_candidate(value)
    cleaned = re.sub(r"^data\s+(?:from|published\s+by)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+\d{4}$", "", cleaned)
    cleaned = re.split(
        r"\s+(?:show|shows|indicate|indicates|reveal|reveals|support|supports|suggest|suggests)\b",
        cleaned,
        maxsplit=1,
        flags=re.I,
    )[0]
    cleaned = cleaned.strip(" .,:;—–-")
    if cleaned.isupper() and len(cleaned.split()) > 1:
        return cleaned.title()
    return cleaned


def _unique_names(values: list[str]) -> tuple[str, ...]:
    names: dict[str, str] = {}
    for value in values:
        name = _clean_role_name(value)
        if not name or name.casefold() in _PLACEHOLDERS:
            continue
        names.setdefault(name.casefold(), name)
    return tuple(names.values())


def _publisher_from_pdf_title(pdf_metadata: Mapping[str, object] | None) -> str:
    title = str((pdf_metadata or {}).get("Title") or "").strip()
    parts = [part.strip() for part in _TITLE_SEPARATOR.split(title) if part.strip()]
    # A report title followed by a branded publication name is source-visible
    # metadata. Do not use filenames or taxonomy labels.
    return _clean_role_name(parts[1]) if len(parts) >= 2 else ""


def _is_person_name(value: str) -> bool:
    words = [word for word in re.split(r"\s+", value.strip()) if word]
    if not 2 <= len(words) <= 5:
        return False
    if {word.casefold() for word in words} & {
        "team",
        "research",
        "group",
        "department",
        "institute",
        "foundation",
    }:
        return False
    return all(re.fullmatch(r"[A-Z][A-Za-z'’-]*\.?", word) for word in words)


def _is_provider_name(value: str) -> bool:
    words = [word for word in value.split() if word]
    if not words:
        return False
    return all(
        word.isupper() or re.fullmatch(r"[A-Z][A-Za-z0-9&.'’-]*", word)
        for word in words
    )


def extract_source_provenance(
    text: str, *, pdf_metadata: Mapping[str, object] | None = None
) -> SourceProvenanceObservation:
    """Resolve optional publication roles from explicit source-visible evidence.

    Publisher candidates are ranked: report/PDF branding, explicit publisher
    wording, then copyright owner. Citation and data-source wording exclusively
    populate ``data_provider_names`` and cannot populate ``publisher_name``.
    """
    raw_text = str(text or "")
    lines = raw_text.splitlines()
    evidence: list[ProvenanceEvidence] = []
    publisher_candidates: dict[int, list[str]] = {0: [], 1: [], 2: []}

    metadata_publisher = _publisher_from_pdf_title(pdf_metadata)
    if metadata_publisher:
        publisher_candidates[0].append(metadata_publisher)
        evidence.append(
            ProvenanceEvidence(
                "publisher",
                metadata_publisher,
                "pdf_metadata_title_brand",
                "pdf_metadata:Title",
                _hash_evidence(metadata_publisher),
            )
        )

    report_by_names: list[str] = []
    author_names: list[str] = []
    owner_names: list[str] = []
    for index, line in enumerate(lines):
        publisher_match = _PUBLISHER_LINE.match(line)
        if publisher_match:
            value = _clean_role_name(publisher_match.group("value"))
            if value:
                publisher_candidates[1].append(value)
                if re.match(r"^\s*a\s+report\s+by", line, re.I):
                    report_by_names.append(value)
                evidence.append(
                    ProvenanceEvidence(
                        "publisher",
                        value,
                        "explicit_report_brand",
                        f"document_pack:line:{index + 1}",
                        _hash_evidence(line),
                    )
                )
        byline_match = _BYLINE_LINE.match(line) or _DATED_BYLINE.match(line)
        if byline_match:
            value = _clean_role_name(byline_match.group("value"))
            if value and value[0].isupper():
                author_names.append(value)
                evidence.append(
                    ProvenanceEvidence(
                        "author",
                        value,
                        "explicit_byline",
                        f"document_pack:line:{index + 1}",
                        _hash_evidence(line),
                    )
                )
        copyright_match = _COPYRIGHT.search(line)
        if copyright_match:
            value = _clean_role_name(copyright_match.group("value"))
            if value:
                owner_names.append(value)
                publisher_candidates[2].append(value)
                evidence.append(
                    ProvenanceEvidence(
                        "report_owner",
                        value,
                        "copyright",
                        f"document_pack:line:{index + 1}",
                        _hash_evidence(line),
                    )
                )

    ranked_publishers = {
        rank: _unique_names(values) for rank, values in publisher_candidates.items()
    }
    selected_rank = next(
        (rank for rank in sorted(ranked_publishers) if ranked_publishers[rank]), None
    )
    issues: list[str] = []
    if selected_rank is None:
        publisher = ""
        issues.append("publisher_missing")
    elif len(ranked_publishers[selected_rank]) != 1:
        publisher = ""
        issues.append("publisher_conflict")
    else:
        publisher = ranked_publishers[selected_rank][0]

    normalized_authors = _unique_names(author_names)
    if not normalized_authors and report_by_names:
        normalized_authors = _unique_names(report_by_names)
        for name in normalized_authors:
            evidence.append(
                ProvenanceEvidence(
                    "author",
                    name,
                    "explicit_corporate_byline",
                    "document_pack:report_by",
                    _hash_evidence(name),
                )
            )
    author_kind = (
        "unknown"
        if not normalized_authors
        else "person"
        if all(_is_person_name(name) for name in normalized_authors)
        else "organization"
    )

    providers: list[str] = []
    for pattern in _PROVIDER_PATTERNS:
        for match in pattern.finditer(raw_text):
            value = _clean_role_name(match.group("value"))
            if value and _is_provider_name(value):
                providers.append(value)
                line_number = raw_text[: match.start()].count("\n") + 1
                evidence.append(
                    ProvenanceEvidence(
                        "data_provider",
                        value,
                        "explicit_data_or_source_citation",
                        f"document_pack:line:{line_number}",
                        _hash_evidence(match.group(0)),
                    )
                )
    normalized_providers = _unique_names(providers)
    normalized_owners = _unique_names(owner_names)
    status = (
        "conflicting"
        if "publisher_conflict" in issues
        else "resolved"
        if publisher
        else "ambiguous"
    )
    return SourceProvenanceObservation(
        publication_name=publisher,
        publisher_name=publisher,
        author_names=normalized_authors,
        author_kind=author_kind,
        data_provider_names=normalized_providers,
        source_organization_names=normalized_providers,
        report_owner_name=normalized_owners[0] if len(normalized_owners) == 1 else "",
        status=status,
        issues=tuple(sorted(set(issues))),
        evidence=tuple(evidence),
    )


def extract_publisher_imprint(text: str) -> PublisherImprintObservation | None:
    """Return one explicit publisher imprint, rejecting weak or conflicting text."""
    candidates: dict[str, str] = {}
    lines = str(text or "").splitlines()
    for line in lines:
        for pattern in _EXPLICIT_IMPRINT_PATTERNS:
            match = pattern.match(line)
            if match is None:
                continue
            publisher = _normalize_candidate(match.group("value"))
            folded = publisher.casefold()
            if (
                folded in _PLACEHOLDERS
                or len(publisher) > 80
                or len(publisher.split()) > 10
                or not any(character.isalpha() for character in publisher)
            ):
                continue
            candidates[folded] = publisher
    if len(candidates) == 1:
        publisher = next(iter(candidates.values()))
        return PublisherImprintObservation(
            publisher_name=publisher,
            evidence_locator="document_pack:first_pages",
            evidence_hash=hashlib.sha256(publisher.encode("utf-8")).hexdigest(),
        )
    if candidates:
        return None

    header_domains: dict[str, int] = {}
    for line in lines:
        match = _HEADER_DOMAIN_PATTERN.fullmatch(line.strip().rstrip("."))
        if match is not None:
            domain = match.group("domain").casefold()
            header_domains[domain] = header_domains.get(domain, 0) + 1
    repeated_domains = [
        domain for domain, count in header_domains.items() if count >= 2
    ]
    if len(repeated_domains) != 1:
        return None
    publisher = repeated_domains[0]
    return PublisherImprintObservation(
        publisher_name=publisher,
        evidence_locator="document_pack:first_pages:repeated_domain",
        evidence_hash=hashlib.sha256(publisher.encode("utf-8")).hexdigest(),
        resolution_method="document_repeated_header_domain",
    )
