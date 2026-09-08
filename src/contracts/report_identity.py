from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReportTitleCandidate:
    """One bounded, source-provenanced candidate for a report's public title."""

    value: str = field(metadata={"doc": "Candidate title text after normalization."})
    source: str = field(
        metadata={"doc": "Evidence class that supplied the candidate title."}
    )
    score: float = field(
        default=0.0, metadata={"doc": "Deterministic preference score."}
    )
    page_number: int = field(
        default=0, metadata={"doc": "One-based source page, when applicable."}
    )
    evidence: str = field(
        default="", metadata={"doc": "Bounded source locator or excerpt."}
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Title-candidate schema version."}
    )


@dataclass(frozen=True)
class ReportTitleResolution:
    """Canonical report identity selected from bounded source evidence."""

    title: str = field(default="", metadata={"doc": "Canonical public report title."})
    edition: str = field(
        default="", metadata={"doc": "Edition or year retained from title evidence."}
    )
    publisher_candidate: str = field(
        default="", metadata={"doc": "Publisher observed alongside title evidence."}
    )
    confidence: str = field(
        default="unknown", metadata={"doc": "high, medium, low, or unknown."}
    )
    evidence: tuple[str, ...] = field(
        default_factory=tuple,
        metadata={"doc": "Bounded evidence locators supporting the identity."},
    )
    candidate_source: str = field(
        default="", metadata={"doc": "Evidence class selected for the title."}
    )
    explicit_source_title: str = field(
        default="",
        metadata={
            "doc": (
                "Visible cover/title-page title that public output must not contradict."
            )
        },
    )
    candidates: tuple[ReportTitleCandidate, ...] = field(
        default_factory=tuple,
        metadata={"doc": "Ranked deterministic candidates retained for audit."},
    )
    issues: tuple[str, ...] = field(
        default_factory=tuple,
        metadata={"doc": "Stable resolution limitations or validation failures."},
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Resolved title-identity schema version."}
    )
