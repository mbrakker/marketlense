from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from src.contracts.files import FileStatRequest
from src.contracts.pdf_context import PdfContextBuildRequest
from src.contracts.pdf_page_reconciliation import (
    PDF_PAGE_RECONCILIATION_ALGORITHM_VERSION,
    PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
    EvidenceKind,
    GeometryLocation,
    MappingMethod,
    PdfPageLabelMapping,
    PdfPageReconciliationCoverage,
    PdfPageReconciliationEvidence,
    PdfPageReconciliationGeometry,
    PdfPageReconciliationRequest,
    PdfPageReconciliationResponse,
)
from src.contracts.run_context import RunContext
from src.services import file_service
from src.utils.errors import AppError
from src.utils.logging import log_event

from .page_artifacts import get_page_text_line_records
from .shared import logger
from .text import build_pdf_context

_PAGE_TOKEN = r"(?:[A-Za-z]{1,8}(?:[-–—]?)\d{1,4}|\d{1,4}|[IVXLCDM]{1,12})"
_PAGE_TOKEN_RE = re.compile(rf"^{_PAGE_TOKEN}$", re.IGNORECASE)
_PAGE_PREFIX_RE = re.compile(
    r"^(?P<prefix>[A-Za-z]{1,8}(?:[-–—])?)(?P<number>\d{1,4})$"
)
_ARABIC_RE = re.compile(r"^\d{1,4}$")
_ROMAN_RE = re.compile(r"^[IVXLCDM]{1,12}$", re.IGNORECASE)
_EXPLICIT_PAGE_RE = re.compile(
    rf"^(?:page|p\.)\s*(?P<label>{_PAGE_TOKEN})(?:\s+of\s+\d{{1,4}})?$",
    re.IGNORECASE,
)
_COPYRIGHT_RE = re.compile(
    rf"^(?P<label>{_PAGE_TOKEN})\s*[©�]\s*\d{{4}}\s+copyright\b.*$",
    re.IGNORECASE,
)
_TRAILING_LABEL_RE = re.compile(
    rf"(?:[•·|]|[-–—])\s*(?P<label>{_PAGE_TOKEN})$", re.IGNORECASE
)
_STRUCTURED_FOOTER_RE = re.compile(
    r"^(?P<marker>[A-Za-z0-9][A-Za-z0-9 &'\-]{2,80}\bREPORT)\s*\|\s*"
    r"(?P<label>\d{1,4})?$",
    re.IGNORECASE,
)
_EXTRACTION_ARTIFACT_START_RE = re.compile(r"^\s*[\uFFFC\uFFFD]")
_EXTRACTION_ARTIFACT_TOKEN_RE = re.compile(
    r"^\s*[\uFFFC\uFFFD]\s*(?P<label>\d{1,4})\s*$", re.IGNORECASE
)
_MAX_INFERENCE_PHYSICAL_GAP = 4
_MAX_MARGIN_LINE_LENGTH = 120


@dataclass(frozen=True)
class _LabelToken:
    label: str
    style: str
    number: int


@dataclass(frozen=True)
class _Candidate:
    token: _LabelToken
    band: str
    detail: str
    strong: bool
    bounding_box: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class _PageObservation:
    physical_page: int
    native_pdf_label: str | None
    candidates: tuple[_Candidate, ...]
    unreadable: bool = False
    artifact_ambiguous: bool = False


@dataclass(frozen=True)
class _TextLine:
    text: str
    line_bbox: tuple[float, float, float, float]
    block_bbox: tuple[float, float, float, float]
    artifact_prefixed: bool = False
    artifact_ambiguous: bool = False


@dataclass(frozen=True)
class _Confirmed:
    candidate: _Candidate
    status: str
    anchors: tuple[int, ...] = ()


def reconcile_pdf_pages(
    request: PdfPageReconciliationRequest, ctx: RunContext
) -> PdfPageReconciliationResponse:
    """Reconcile visible printed page labels against physical PDF pages."""

    stat = file_service.file_stat(
        FileStatRequest(schema_version="1.0", path=request.path, compute_md5=True),
        ctx,
    )
    if not stat.exists or not stat.is_file or not stat.md5:
        raise AppError(
            code="pdf_not_found",
            message=f"Input PDF is not a readable file: {request.path}",
            retryable=False,
        )

    context_response = build_pdf_context(
        PdfContextBuildRequest(
            schema_version="1.0",
            path=request.path,
            load_fitz=True,
            load_pypdf=False,
        ),
        ctx,
    )
    pdf_context = context_response.context
    document = pdf_context.fitz_doc
    if document is None:
        pdf_context.close()
        raise AppError(
            code="pdf_open_failed",
            message=f"Failed to open PDF with PyMuPDF: {request.path}",
            retryable=False,
            context={"fitz_error": str(context_response.fitz_error or "")},
        )

    try:
        try:
            page_count = int(document.page_count)
        except (AttributeError, RuntimeError, ValueError, TypeError) as exc:
            raise AppError(
                code="pdf_page_count_failed",
                message=f"Failed to determine PDF page count: {request.path}",
                cause=exc,
                retryable=False,
            ) from exc
        if page_count <= 0:
            raise AppError(
                code="pdf_zero_pages",
                message=f"PDF contains no readable pages: {request.path}",
                retryable=False,
            )

        observations = tuple(
            _observe_page(document, page_number)
            for page_number in range(1, page_count + 1)
        )
        confirmed = _confirm_direct_labels(observations)
        inferred = _infer_missing_labels(observations, confirmed)
        mappings = tuple(
            _mapping_for_observation(
                observation,
                confirmed.get(observation.physical_page),
                inferred.get(observation.physical_page),
            )
            for observation in observations
        )
        coverage = _coverage(mappings)
        response = PdfPageReconciliationResponse(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            algorithm_version=PDF_PAGE_RECONCILIATION_ALGORITHM_VERSION,
            input_pdf_md5=stat.md5.lower(),
            physical_page_count=page_count,
            mappings=mappings,
            coverage_statistics=coverage,
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="pdf_page_reconciliation_complete",
                module=logger.name,
                fields={
                    "physical_page_count": page_count,
                    "verified_count": coverage.verified_count,
                    "inferred_count": coverage.inferred_count,
                    "unresolved_count": coverage.unresolved_count,
                    "algorithm_version": PDF_PAGE_RECONCILIATION_ALGORITHM_VERSION,
                },
            )
        )
        return response
    finally:
        pdf_context.close()


def _observe_page(document: Any, physical_page: int) -> _PageObservation:
    try:
        page = document[physical_page - 1]
    except (RuntimeError, ValueError, IndexError, TypeError):
        return _PageObservation(physical_page, None, (), unreadable=True)

    native_pdf_label = _native_pdf_label(page)
    try:
        line_records = get_page_text_line_records(page, cache=None)
        height = float(page.rect.height)
    except (RuntimeError, ValueError, AttributeError, TypeError):
        return _PageObservation(physical_page, native_pdf_label, (), unreadable=True)

    lines = tuple(
        _TextLine(
            _normalize_extracted_line_text(text),
            (
                float(line_rect.x0),
                float(line_rect.y0),
                float(line_rect.x1),
                float(line_rect.y1),
            ),
            (
                float(block_rect.x0),
                float(block_rect.y0),
                float(block_rect.x1),
                float(block_rect.y1),
            ),
            _EXTRACTION_ARTIFACT_TOKEN_RE.fullmatch(text) is not None,
            (
                _EXTRACTION_ARTIFACT_START_RE.match(text) is not None
                and _EXTRACTION_ARTIFACT_TOKEN_RE.fullmatch(text) is None
            ),
        )
        for line_rect, block_rect, text in line_records
    )
    line_counts_by_block: dict[tuple[float, float, float, float], int] = {}
    for line in lines:
        line_counts_by_block[line.block_bbox] = (
            line_counts_by_block.get(line.block_bbox, 0) + 1
        )

    candidates: list[_Candidate] = []
    for line in lines:
        band = _margin_band(line.line_bbox[1], line.line_bbox[3], height)
        if band is None:
            continue
        artifact_prefixed = line.artifact_prefixed
        if line.artifact_ambiguous:
            continue
        line_text = re.sub(r"\s+", " ", line.text).strip()
        if not line_text or len(line_text) > _MAX_MARGIN_LINE_LENGTH:
            continue
        candidate = _parse_candidate(
            line_text,
            band,
            bounding_box=line.block_bbox,
            artifact_prefixed=artifact_prefixed,
        )
        if candidate is not None and not (
            not candidate.strong
            and not artifact_prefixed
            and line_counts_by_block.get(line.block_bbox, 0) > 2
        ):
            candidates.append(candidate)

    for candidate in _structured_footer_candidates(lines, height):
        matching_indexes = [
            index
            for index, existing in enumerate(candidates)
            if existing.token.style == candidate.token.style
            and existing.token.number == candidate.token.number
        ]
        if not matching_indexes:
            candidates.append(candidate)
        elif any(not candidates[index].strong for index in matching_indexes):
            candidates[:] = [
                existing
                for existing in candidates
                if not (
                    existing.token.style == candidate.token.style
                    and existing.token.number == candidate.token.number
                )
            ]
            candidates.append(candidate)
    unique: dict[tuple[str, str, bool], _Candidate] = {}
    for candidate in candidates:
        unique[(candidate.token.label, candidate.band, candidate.strong)] = candidate
    return _PageObservation(
        physical_page=physical_page,
        native_pdf_label=native_pdf_label,
        candidates=tuple(unique.values()),
        artifact_ambiguous=any(
            line.artifact_ambiguous
            and _margin_band(line.line_bbox[1], line.line_bbox[3], height) is not None
            for line in lines
        ),
    )


def _normalize_extracted_line_text(text: str) -> str:
    """Remove known marked-content artifacts before page-token parsing."""

    artifact_match = _EXTRACTION_ARTIFACT_TOKEN_RE.fullmatch(text)
    if artifact_match is not None:
        text = artifact_match.group("label")
    return re.sub(r"\s+", " ", text).strip()


def _structured_footer_candidates(
    lines: tuple[_TextLine, ...], height: float
) -> tuple[_Candidate, ...]:
    if height <= 0:
        return ()

    footer_lines = tuple(
        line
        for line in lines
        if _margin_band(line.line_bbox[1], line.line_bbox[3], height)
        == "visible_footer"
    )

    candidates: list[_Candidate] = []
    for marker_line in footer_lines:
        match = _STRUCTURED_FOOTER_RE.fullmatch(marker_line.text)
        if match is None:
            continue
        label = match.group("label")
        if label is None:
            matching_numeric_lines = [
                line
                for line in footer_lines
                if _ARABIC_RE.fullmatch(line.text)
                and line.line_bbox[0] >= marker_line.line_bbox[2] - 2.0
                and abs(line.line_bbox[3] - marker_line.line_bbox[3]) <= 3.5
            ]
            if len(matching_numeric_lines) != 1:
                continue
            numeric_line = matching_numeric_lines[0]
            label = numeric_line.text
            detail = numeric_line.text
            bounding_box = numeric_line.block_bbox
        else:
            detail = marker_line.text
            bounding_box = marker_line.block_bbox

        token = _parse_label_token(label)
        if token is None or (token.style == "arabic" and 1900 <= token.number <= 2100):
            continue
        candidates.append(
            _Candidate(token, "visible_footer", detail[:240], True, bounding_box)
        )
    return tuple(candidates)


def _native_pdf_label(page: Any) -> str | None:
    get_label = getattr(page, "get_label", None)
    if not callable(get_label):
        return None
    try:
        value = str(get_label() or "").strip()
    except (RuntimeError, ValueError, AttributeError, TypeError):
        return None
    return value or None


def _margin_band(y0: float, y1: float, height: float) -> str | None:
    if height <= 0:
        return None
    if y1 / height <= 0.14:
        return "visible_header"
    if y0 / height >= 0.86:
        return "visible_footer"
    return None


def _parse_candidate(
    line: str,
    band: str,
    *,
    bounding_box: tuple[float, float, float, float] | None = None,
    artifact_prefixed: bool = False,
) -> _Candidate | None:
    explicit = _EXPLICIT_PAGE_RE.fullmatch(line)
    if explicit:
        token = _parse_label_token(explicit.group("label"))
        if token is not None:
            return _Candidate(token, band, line[:240], True, bounding_box)

    copyright_match = _COPYRIGHT_RE.fullmatch(line)
    if copyright_match:
        token = _parse_label_token(copyright_match.group("label"))
        if token is not None:
            return _Candidate(token, band, line[:240], True, bounding_box)

    if _PAGE_TOKEN_RE.fullmatch(line):
        token = _parse_label_token(line)
        if token is None or (token.style == "arabic" and 1900 <= token.number <= 2100):
            return None
        return _Candidate(
            token,
            band,
            line[:240],
            token.style == "roman" or artifact_prefixed,
            bounding_box,
        )

    trailing = _TRAILING_LABEL_RE.search(line)
    if trailing:
        token = _parse_label_token(trailing.group("label"))
        if token is not None:
            return _Candidate(token, band, line[:240], False, bounding_box)
    return None


def _parse_label_token(raw_label: str) -> _LabelToken | None:
    label = str(raw_label or "").strip()
    if not label:
        return None
    if _ARABIC_RE.fullmatch(label):
        number = int(label)
        return _LabelToken(label, "arabic", number) if number > 0 else None
    prefix_match = _PAGE_PREFIX_RE.fullmatch(label)
    if prefix_match:
        number = int(prefix_match.group("number"))
        prefix = prefix_match.group("prefix").replace("–", "-").replace("—", "-")
        return _LabelToken(label, f"prefix:{prefix.casefold()}", number)
    if _ROMAN_RE.fullmatch(label):
        number = _roman_to_int(label)
        if number > 0:
            return _LabelToken(label, "roman", number)
    return None


def _roman_to_int(value: str) -> int:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    previous = 0
    for character in reversed(value.upper()):
        current = values[character]
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return total


def _confirm_direct_labels(
    observations: tuple[_PageObservation, ...],
) -> dict[int, _Confirmed]:
    confirmed: dict[int, _Confirmed] = {}
    candidates_by_page: dict[int, tuple[_Candidate, ...]] = {}
    weak_candidates: dict[int, tuple[_Candidate, ...]] = {}
    for observation in observations:
        labels = {
            (candidate.token.style, candidate.token.number)
            for candidate in observation.candidates
        }
        if not observation.candidates:
            continue
        ordered_candidates = list(observation.candidates)
        ordered_candidates.sort(key=lambda item: (not item.strong, item.band))
        if len(labels) == 1:
            candidate = ordered_candidates[0]
            candidates_by_page[observation.physical_page] = (candidate,)
            if candidate.strong:
                confirmed[observation.physical_page] = _Confirmed(candidate, "verified")
            else:
                weak_candidates[observation.physical_page] = (candidate,)
            continue

        if any(candidate.strong for candidate in ordered_candidates):
            continue

        weak_options = tuple(
            candidate for candidate in ordered_candidates if not candidate.strong
        )
        if weak_options:
            candidates_by_page[observation.physical_page] = weak_options
            weak_candidates[observation.physical_page] = weak_options

    for page_number, candidate_options in weak_candidates.items():
        supported = [
            (
                candidate,
                _weak_candidate_sequence_anchors(
                    page_number, candidate, candidates_by_page
                ),
            )
            for candidate in candidate_options
            if _weak_candidate_has_adjacent_sequence(
                page_number, candidate, candidates_by_page
            )
        ]
        if len(supported) == 1:
            candidate, anchors = supported[0]
            confirmed[page_number] = _Confirmed(candidate, "verified", anchors)
    return confirmed


def _weak_candidate_has_adjacent_sequence(
    page_number: int,
    candidate: _Candidate,
    candidates_by_page: dict[int, tuple[_Candidate, ...]],
) -> bool:
    return bool(
        _weak_candidate_sequence_anchors(page_number, candidate, candidates_by_page)
    )


def _weak_candidate_sequence_anchors(
    page_number: int,
    candidate: _Candidate,
    candidates_by_page: dict[int, tuple[_Candidate, ...]],
) -> tuple[int, ...]:
    sequence_candidates = _consistent_local_sequence_candidates(
        page_number, candidate, candidates_by_page
    )
    sequence_pages = tuple(sorted(sequence_candidates))
    if len(sequence_pages) >= 3:
        return (sequence_pages[0], sequence_pages[-1])
    strong_pages = tuple(
        page
        for page in sequence_pages
        if page != page_number and sequence_candidates[page].strong
    )
    return strong_pages[:2]


def _consistent_local_sequence_candidates(
    page_number: int,
    candidate: _Candidate,
    candidates_by_page: dict[int, tuple[_Candidate, ...]],
) -> dict[int, _Candidate]:
    selected = {page_number: candidate}
    for direction in (-1, 1):
        current_page = page_number
        current_candidate = candidate
        while True:
            neighbor_page = current_page + direction
            neighbor_options = candidates_by_page.get(neighbor_page, ())
            matches = tuple(
                neighbor
                for neighbor in neighbor_options
                if _follows_sequence(
                    current_page, current_candidate, neighbor_page, neighbor
                )
            )
            if len(matches) != 1:
                break
            neighbor = matches[0]
            selected[neighbor_page] = neighbor
            current_page = neighbor_page
            current_candidate = neighbor
    return selected


def _follows_sequence(
    left_page: int,
    left: _Candidate,
    right_page: int,
    right: _Candidate,
) -> bool:
    return (
        left.band == right.band
        and left.token.style == right.token.style
        and right.token.number - left.token.number == right_page - left_page
    )


def _infer_missing_labels(
    observations: tuple[_PageObservation, ...],
    confirmed: dict[int, _Confirmed],
) -> dict[int, _Confirmed]:
    proposals: dict[int, dict[str, set[tuple[str, int, int]]]] = {}
    verified = sorted(confirmed.items())
    for left_index, (left_page, left) in enumerate(verified):
        for right_page, right in verified[left_index + 1 :]:
            if right_page - left_page <= 1:
                continue
            if right_page - left_page > _MAX_INFERENCE_PHYSICAL_GAP:
                break
            if left.candidate.token.style != right.candidate.token.style:
                continue
            if right.candidate.token.number - left.candidate.token.number != (
                right_page - left_page
            ):
                continue
            for physical_page in range(left_page + 1, right_page):
                observation = observations[physical_page - 1]
                if (
                    observation.candidates
                    or observation.unreadable
                    or observation.artifact_ambiguous
                ):
                    continue
                number = left.candidate.token.number + (physical_page - left_page)
                label = _format_inferred_label(
                    left.candidate.token.style, left.candidate.token.label, number
                )
                proposals.setdefault(physical_page, {}).setdefault(label, set()).add(
                    (left.candidate.token.style, left_page, right_page)
                )

    inferred: dict[int, _Confirmed] = {}
    for physical_page, proposal_labels in proposals.items():
        if len(proposal_labels) != 1 or physical_page in confirmed:
            continue
        label, anchor_options = next(iter(proposal_labels.items()))
        style, left_page, right_page = min(anchor_options)
        parsed_label = _parse_label_token(label)
        if parsed_label is None:
            continue
        candidate = _Candidate(
            _LabelToken(label, style, parsed_label.number),
            "visible_footer",
            f"between physical pages {left_page} and {right_page}",
            True,
            None,
        )
        inferred[physical_page] = _Confirmed(
            candidate, "inferred", (left_page, right_page)
        )
    return inferred


def _format_inferred_label(style: str, exemplar: str, number: int) -> str:
    if style == "roman":
        rendered = _int_to_roman(number)
        return rendered.upper() if exemplar.isupper() else rendered.lower()
    if style.startswith("prefix:"):
        match = _PAGE_PREFIX_RE.fullmatch(exemplar)
        if match is not None:
            width = len(match.group("number"))
            return f"{match.group('prefix')}{number:0{width}d}"
    if _ARABIC_RE.fullmatch(exemplar):
        return f"{number:0{len(exemplar)}d}"
    return str(number)


def _int_to_roman(number: int) -> str:
    values = (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    )
    result: list[str] = []
    remaining = number
    for value, token in values:
        count, remaining = divmod(remaining, value)
        result.append(token * count)
    return "".join(result)


def _mapping_for_observation(
    observation: _PageObservation,
    direct: _Confirmed | None,
    inferred: _Confirmed | None,
) -> PdfPageLabelMapping:
    evidence: list[PdfPageReconciliationEvidence] = []
    if observation.native_pdf_label:
        evidence.append(
            PdfPageReconciliationEvidence(
                kind="native_pdf_metadata",
                detail=f"native PDF label {observation.native_pdf_label[:160]}",
            )
        )
    if direct is not None:
        if direct.candidate.bounding_box is None:
            raise ValueError("direct candidate is missing source geometry")
        evidence.insert(
            0,
            PdfPageReconciliationEvidence(
                kind=cast(EvidenceKind, direct.candidate.band),
                detail=direct.candidate.detail,
                anchor_physical_pages=direct.anchors,
            ),
        )
        return PdfPageLabelMapping(
            physical_page=observation.physical_page,
            printed_label=direct.candidate.token.label,
            status="verified",
            method=cast(MappingMethod, direct.candidate.band),
            native_pdf_label=observation.native_pdf_label,
            evidence=tuple(evidence),
            source_geometry=(
                PdfPageReconciliationGeometry(
                    physical_page=observation.physical_page,
                    label_text=direct.candidate.detail,
                    location=cast(GeometryLocation, direct.candidate.band),
                    bounding_box=direct.candidate.bounding_box,
                )
            ),
        )
    if inferred is not None:
        evidence.insert(
            0,
            PdfPageReconciliationEvidence(
                kind="sequence_inference",
                detail=inferred.candidate.detail,
                anchor_physical_pages=inferred.anchors,
            ),
        )
        return PdfPageLabelMapping(
            physical_page=observation.physical_page,
            printed_label=inferred.candidate.token.label,
            status="inferred",
            method="sequence_inference",
            native_pdf_label=observation.native_pdf_label,
            evidence=tuple(evidence),
            source_geometry=None,
        )

    if observation.unreadable:
        evidence.insert(
            0,
            PdfPageReconciliationEvidence(
                kind="unreadable", detail="page text or geometry was unreadable"
            ),
        )
    elif observation.artifact_ambiguous:
        evidence.insert(
            0,
            PdfPageReconciliationEvidence(
                kind="conflict",
                detail="ambiguous marked-content margin token",
            ),
        )
    elif len({candidate.token.label for candidate in observation.candidates}) > 1:
        labels = ", ".join(
            sorted({candidate.token.label for candidate in observation.candidates})[:3]
        )
        evidence.insert(
            0,
            PdfPageReconciliationEvidence(
                kind="conflict", detail=f"conflicting visible labels: {labels}"
            ),
        )
    elif observation.candidates:
        candidate = observation.candidates[0]
        evidence.insert(
            0,
            PdfPageReconciliationEvidence(
                kind="no_visible_label",
                detail=(
                    "weak standalone margin token was not corroborated: "
                    f"{candidate.detail}"
                ),
            ),
        )
    else:
        evidence.insert(
            0,
            PdfPageReconciliationEvidence(
                kind="no_visible_label", detail="no visible page label in margin bands"
            ),
        )
    return PdfPageLabelMapping(
        physical_page=observation.physical_page,
        printed_label=None,
        status="unresolved",
        method="unresolved",
        native_pdf_label=observation.native_pdf_label,
        evidence=tuple(evidence),
        source_geometry=None,
    )


def _coverage(
    mappings: tuple[PdfPageLabelMapping, ...],
) -> PdfPageReconciliationCoverage:
    counts = {
        status: sum(mapping.status == status for mapping in mappings)
        for status in ("verified", "inferred", "unresolved")
    }
    total = len(mappings)
    return PdfPageReconciliationCoverage(
        verified_count=counts["verified"],
        inferred_count=counts["inferred"],
        unresolved_count=counts["unresolved"],
        verified_percentage=round(counts["verified"] * 100.0 / total, 2),
        inferred_percentage=round(counts["inferred"] * 100.0 / total, 2),
        unresolved_percentage=round(counts["unresolved"] * 100.0 / total, 2),
    )
