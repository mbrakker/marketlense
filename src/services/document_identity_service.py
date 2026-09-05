"""Deterministic publisher-imprint extraction from bounded document-pack text."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

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


@dataclass(frozen=True)
class PublisherImprintObservation:
    publisher_name: str
    evidence_locator: str
    evidence_hash: str
    resolution_method: str = "document_imprint_extraction"


def _normalize_candidate(value: str) -> str:
    normalized = " ".join(value.split())
    normalized = re.split(
        r"\s+(?:all rights reserved|©|copyright)\b",
        normalized,
        maxsplit=1,
        flags=re.I,
    )[0]
    return normalized.strip(" .,:;—–-")


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
