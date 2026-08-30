from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, TypeAlias


@dataclass(frozen=True)
class DocMapSection:
    id: str = field(metadata={"doc": "Stable section identifier."})
    title: str = field(metadata={"doc": "Section title."})
    summary: str = field(metadata={"doc": "Section brief summary text."})
    key_points: List[str] = field(
        default_factory=list,
        metadata={"doc": "Concise bullet-like key points for the section."},
    )
    pages: List[int] = field(
        default_factory=list,
        metadata={"doc": "One-based page numbers covered by the section."},
    )
    references: List[str] = field(
        default_factory=list,
        metadata={"doc": "Reference identifiers associated with the section."},
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "DocMap section schema version."}
    )


@dataclass(frozen=True)
class DocMapPack:
    doc_id: str = field(metadata={"doc": "Document identifier used for pack linkage."})
    title: str = field(metadata={"doc": "Document title."})
    summary: str = field(default="", metadata={"doc": "Document summary text."})
    publisher: str = field(
        default="", metadata={"doc": "Document publisher/organization."}
    )
    sections: List[DocMapSection] = field(
        default_factory=list,
        metadata={"doc": "Structured section mapping for the source report."},
    )
    not_found_reason: str = field(
        default="",
        metadata={
            "doc": "Reason why pack generation did not return substantive content."
        },
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "DocMap pack schema version."}
    )


@dataclass(frozen=True)
class ScopePack:
    scope: str | Dict[str, object] = field(
        default="", metadata={"doc": "Scope narrative or structured scope object."}
    )
    not_found_reason: str = field(
        default="",
        metadata={
            "doc": "Reason why pack generation did not return substantive content."
        },
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Scope pack schema version."}
    )


@dataclass(frozen=True)
class MethodsPack:
    methods: List[str | Dict[str, object]] = field(
        default_factory=list,
        metadata={"doc": "Method entries extracted from source materials."},
    )
    not_found_reason: str = field(
        default="",
        metadata={
            "doc": "Reason why pack generation did not return substantive content."
        },
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Methods pack schema version."}
    )


@dataclass(frozen=True)
class FindingEntry:
    id: str = field(metadata={"doc": "Stable finding identifier."})
    text: str = field(metadata={"doc": "Finding statement text."})
    evidence: str = field(default="", metadata={"doc": "Supporting evidence text."})
    confidence: str = field(
        default="", metadata={"doc": "Model confidence descriptor/value."}
    )
    section_id: str = field(
        default="", metadata={"doc": "Source DocMap section identifier, if linked."}
    )
    section_title: str = field(
        default="", metadata={"doc": "Source DocMap section title, if linked."}
    )
    pages: List[int] = field(
        default_factory=list,
        metadata={"doc": "One-based page numbers supporting the finding."},
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Finding entry schema version."}
    )


@dataclass(frozen=True)
class FindingsPack:
    findings: List[FindingEntry] = field(
        default_factory=list, metadata={"doc": "Extracted findings list."}
    )
    not_found_reason: str = field(
        default="",
        metadata={
            "doc": "Reason why pack generation did not return substantive content."
        },
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Findings pack schema version."}
    )


@dataclass(frozen=True)
class LimitationsPack:
    limitations: List[str] = field(
        default_factory=list,
        metadata={"doc": "Extracted known limitations/risk notes."},
    )
    not_found_reason: str = field(
        default="",
        metadata={
            "doc": "Reason why pack generation did not return substantive content."
        },
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Limitations pack schema version."}
    )


@dataclass(frozen=True)
class QuoteCandidateEntry:
    text: str = field(metadata={"doc": "Quote text."})
    source: str = field(default="", metadata={"doc": "Speaker/source attribution."})
    page: Optional[int] = field(
        default=None, metadata={"doc": "One-based page number."}
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Quote-candidate entry schema version."}
    )


@dataclass(frozen=True)
class QuoteCandidatesPack:
    quote_candidates: List[QuoteCandidateEntry] = field(
        default_factory=list, metadata={"doc": "Extracted quote candidates."}
    )
    not_found_reason: str = field(
        default="",
        metadata={
            "doc": "Reason why pack generation did not return substantive content."
        },
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Quote candidates pack schema version."}
    )


DocPackPathMap: TypeAlias = Dict[str, str]
DocPackPayloadMap: TypeAlias = Dict[str, Dict[str, object]]
