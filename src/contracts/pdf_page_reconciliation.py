from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, cast

PDF_PAGE_RECONCILIATION_SCHEMA_VERSION = "1.0"
PDF_PAGE_RECONCILIATION_ALGORITHM_VERSION = "pdf-page-reconciliation-v1"
_MD5_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_STATUS_VALUES = {"verified", "inferred", "unresolved"}
_METHOD_VALUES = {
    "visible_header",
    "visible_footer",
    "sequence_inference",
    "unresolved",
}
_EVIDENCE_KINDS = {
    "visible_header",
    "visible_footer",
    "native_pdf_metadata",
    "sequence_inference",
    "conflict",
    "unreadable",
    "no_visible_label",
}
EvidenceKind = Literal[
    "visible_header",
    "visible_footer",
    "native_pdf_metadata",
    "sequence_inference",
    "conflict",
    "unreadable",
    "no_visible_label",
]
MappingStatus = Literal["verified", "inferred", "unresolved"]
MappingMethod = Literal[
    "visible_header", "visible_footer", "sequence_inference", "unresolved"
]


@dataclass(frozen=True)
class PdfPageReconciliationRequest:
    """Input identity for one standalone PDF reconciliation run."""

    schema_version: str = field(
        metadata={"doc": "PDF page reconciliation request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path to the input PDF."})

    def __post_init__(self) -> None:
        if self.schema_version != PDF_PAGE_RECONCILIATION_SCHEMA_VERSION:
            raise ValueError("unsupported reconciliation schema version")
        if not isinstance(self.path, str) or not self.path.strip():
            raise ValueError("path must be non-empty")


@dataclass(frozen=True)
class PdfPageReconciliationEvidence:
    """Bounded evidence retained for one page-label decision."""

    kind: EvidenceKind = field(metadata={"doc": "Deterministic evidence kind."})
    detail: str = field(metadata={"doc": "Short bounded evidence detail."})
    anchor_physical_pages: tuple[int, ...] = field(
        default=(),
        metadata={"doc": "Physical pages used as verified anchors for an inference."},
    )

    def __post_init__(self) -> None:
        if self.kind not in _EVIDENCE_KINDS:
            raise ValueError("evidence kind is invalid")
        if (
            not isinstance(self.detail, str)
            or not self.detail.strip()
            or len(self.detail) > 240
        ):
            raise ValueError("evidence detail must be non-empty and bounded")
        if not isinstance(self.anchor_physical_pages, tuple):
            raise ValueError("evidence anchors must be a tuple")
        if len(self.anchor_physical_pages) > 2 or any(
            not isinstance(page, int) or isinstance(page, bool) or page <= 0
            for page in self.anchor_physical_pages
        ):
            raise ValueError("evidence anchors must contain at most two positive pages")


@dataclass(frozen=True)
class PdfPageLabelMapping:
    """One physical page and its visible printed-label reconciliation."""

    physical_page: int = field(metadata={"doc": "One-based physical PDF page."})
    printed_label: str | None = field(
        metadata={"doc": "Visible printed page label, preserving its string form."}
    )
    status: MappingStatus = field(metadata={"doc": "Mapping confidence state."})
    method: MappingMethod = field(
        metadata={"doc": "Deterministic reconciliation method."}
    )
    native_pdf_label: str | None = field(
        metadata={"doc": "Native PDF label metadata, never proof by itself."}
    )
    evidence: tuple[PdfPageReconciliationEvidence, ...] = field(
        metadata={"doc": "Bounded evidence for the mapping decision."}
    )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.physical_page, int)
            or isinstance(self.physical_page, bool)
            or self.physical_page <= 0
        ):
            raise ValueError("physical_page must be positive")
        if self.status not in _STATUS_VALUES:
            raise ValueError("status is invalid")
        if self.method not in _METHOD_VALUES:
            raise ValueError("method is invalid")
        if self.printed_label is not None and (
            not isinstance(self.printed_label, str) or not self.printed_label.strip()
        ):
            raise ValueError("printed_label must be non-empty when present")
        if self.native_pdf_label is not None and (
            not isinstance(self.native_pdf_label, str)
            or not self.native_pdf_label.strip()
        ):
            raise ValueError("native_pdf_label must be non-empty when present")
        if (
            not isinstance(self.evidence, tuple)
            or not self.evidence
            or len(self.evidence) > 4
        ):
            raise ValueError("mapping evidence must be present and bounded")
        if not all(
            isinstance(item, PdfPageReconciliationEvidence) for item in self.evidence
        ):
            raise ValueError("mapping evidence must use the typed evidence contract")

        direct_kinds = {"visible_header", "visible_footer"}
        evidence_kinds = {item.kind for item in self.evidence}
        if self.status == "verified":
            if self.printed_label is None or self.method not in direct_kinds:
                raise ValueError("verified mapping requires direct visible evidence")
            if self.method not in evidence_kinds:
                raise ValueError(
                    "verified mapping evidence must name its visible method"
                )
        elif self.status == "inferred":
            if self.printed_label is None or self.method != "sequence_inference":
                raise ValueError("inferred mapping requires sequence_inference")
            anchors = [
                item for item in self.evidence if item.kind == "sequence_inference"
            ]
            if len(anchors) != 1 or len(anchors[0].anchor_physical_pages) != 2:
                raise ValueError("inferred mapping requires two anchor pages")
        else:
            if self.printed_label is not None or self.method != "unresolved":
                raise ValueError("unresolved mapping cannot retain a printed label")
            if "sequence_inference" in evidence_kinds:
                raise ValueError("unresolved mapping cannot retain inference evidence")


@dataclass(frozen=True)
class PdfPageReconciliationCoverage:
    """Count and percentage summary for all physical pages."""

    verified_count: int = field(metadata={"doc": "Number of verified mappings."})
    inferred_count: int = field(metadata={"doc": "Number of inferred mappings."})
    unresolved_count: int = field(metadata={"doc": "Number of unresolved mappings."})
    verified_percentage: float = field(
        metadata={"doc": "Verified mappings as a percentage of physical pages."}
    )
    inferred_percentage: float = field(
        metadata={"doc": "Inferred mappings as a percentage of physical pages."}
    )
    unresolved_percentage: float = field(
        metadata={"doc": "Unresolved mappings as a percentage of physical pages."}
    )

    def __post_init__(self) -> None:
        counts = (self.verified_count, self.inferred_count, self.unresolved_count)
        if any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in counts
        ):
            raise ValueError("coverage counts must be nonnegative integers")
        percentages = (
            self.verified_percentage,
            self.inferred_percentage,
            self.unresolved_percentage,
        )
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 100.0
            for value in percentages
        ):
            raise ValueError("coverage percentages must be finite values from 0 to 100")


@dataclass(frozen=True)
class PdfPageReconciliationResponse:
    """Source-bound ordered reconciliation for every physical PDF page."""

    schema_version: str = field(
        metadata={"doc": "PDF page reconciliation response schema version."}
    )
    algorithm_version: str = field(
        metadata={"doc": "Deterministic reconciliation algorithm version."}
    )
    input_pdf_md5: str = field(metadata={"doc": "MD5 of the exact input PDF bytes."})
    physical_page_count: int = field(
        metadata={"doc": "Number of physical pages in the input PDF."}
    )
    mappings: tuple[PdfPageLabelMapping, ...] = field(
        metadata={"doc": "Mappings ordered by one-based physical page."}
    )
    coverage_statistics: PdfPageReconciliationCoverage = field(
        metadata={"doc": "Coverage counts and percentages."}
    )

    def __post_init__(self) -> None:
        if self.schema_version != PDF_PAGE_RECONCILIATION_SCHEMA_VERSION:
            raise ValueError("unsupported reconciliation schema version")
        if self.algorithm_version != PDF_PAGE_RECONCILIATION_ALGORITHM_VERSION:
            raise ValueError("unsupported reconciliation algorithm version")
        if not isinstance(self.input_pdf_md5, str) or not _MD5_PATTERN.fullmatch(
            self.input_pdf_md5
        ):
            raise ValueError("input_pdf_md5 must be a lowercase 32-character MD5")
        if (
            not isinstance(self.physical_page_count, int)
            or isinstance(self.physical_page_count, bool)
            or self.physical_page_count <= 0
        ):
            raise ValueError("physical_page_count must be positive")
        if len(self.mappings) != self.physical_page_count:
            raise ValueError("one mapping for every physical page is required")
        expected_pages = tuple(range(1, self.physical_page_count + 1))
        actual_pages = tuple(mapping.physical_page for mapping in self.mappings)
        if actual_pages != expected_pages:
            raise ValueError("mappings must cover physical pages exactly once in order")

        counts = {
            "verified": sum(item.status == "verified" for item in self.mappings),
            "inferred": sum(item.status == "inferred" for item in self.mappings),
            "unresolved": sum(item.status == "unresolved" for item in self.mappings),
        }
        coverage = self.coverage_statistics
        if (
            coverage.verified_count,
            coverage.inferred_count,
            coverage.unresolved_count,
        ) != (
            counts["verified"],
            counts["inferred"],
            counts["unresolved"],
        ):
            raise ValueError("coverage counts do not match mappings")
        expected_percentages = tuple(
            round(counts[key] * 100.0 / self.physical_page_count, 2)
            for key in ("verified", "inferred", "unresolved")
        )
        actual_percentages = (
            coverage.verified_percentage,
            coverage.inferred_percentage,
            coverage.unresolved_percentage,
        )
        if actual_percentages != expected_percentages:
            raise ValueError("coverage percentages do not match mappings")


def response_from_payload(payload: Mapping[str, Any]) -> PdfPageReconciliationResponse:
    """Rehydrate and semantically validate a cache payload."""

    if not isinstance(payload, Mapping):
        raise ValueError("reconciliation payload must be an object")
    raw_mappings = payload.get("mappings")
    raw_coverage = payload.get("coverage_statistics")
    if not isinstance(raw_mappings, list) or not isinstance(raw_coverage, Mapping):
        raise ValueError(
            "reconciliation payload has invalid mapping or coverage fields"
        )

    mappings: list[PdfPageLabelMapping] = []
    for raw_mapping in raw_mappings:
        if not isinstance(raw_mapping, Mapping):
            raise ValueError("mapping payload must be an object")
        raw_evidence = raw_mapping.get("evidence")
        if not isinstance(raw_evidence, list):
            raise ValueError("mapping evidence payload must be an array")
        evidence = tuple(
            PdfPageReconciliationEvidence(
                kind=cast(EvidenceKind, str(item.get("kind") or "")),
                detail=str(item.get("detail") or ""),
                anchor_physical_pages=tuple(item.get("anchor_physical_pages") or ()),
            )
            for item in raw_evidence
            if isinstance(item, Mapping)
        )
        if len(evidence) != len(raw_evidence):
            raise ValueError("mapping evidence payload contains a non-object")
        mappings.append(
            PdfPageLabelMapping(
                physical_page=int(raw_mapping["physical_page"]),
                printed_label=raw_mapping.get("printed_label"),
                status=cast(MappingStatus, str(raw_mapping["status"])),
                method=cast(MappingMethod, str(raw_mapping["method"])),
                native_pdf_label=raw_mapping.get("native_pdf_label"),
                evidence=evidence,
            )
        )
    return PdfPageReconciliationResponse(
        schema_version=str(payload["schema_version"]),
        algorithm_version=str(payload["algorithm_version"]),
        input_pdf_md5=str(payload["input_pdf_md5"]),
        physical_page_count=int(payload["physical_page_count"]),
        mappings=tuple(mappings),
        coverage_statistics=PdfPageReconciliationCoverage(
            verified_count=int(raw_coverage["verified_count"]),
            inferred_count=int(raw_coverage["inferred_count"]),
            unresolved_count=int(raw_coverage["unresolved_count"]),
            verified_percentage=float(raw_coverage["verified_percentage"]),
            inferred_percentage=float(raw_coverage["inferred_percentage"]),
            unresolved_percentage=float(raw_coverage["unresolved_percentage"]),
        ),
    )
