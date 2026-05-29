from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


WORDPRESS_ENTITY_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class SignalPublishProjection:
    schema_version: str = field(
        metadata={"doc": "Signal publish projection schema version."}
    )
    title: str = field(metadata={"doc": "Public Signal title."})
    slug: str = field(metadata={"doc": "Deterministic WordPress Signal slug."})
    summary_html: str = field(
        metadata={"doc": "Escaped summary HTML approved for archive cards."}
    )
    body_html: str = field(
        metadata={"doc": "Escaped body HTML approved for the Signal detail page."}
    )
    evidence_ids: List[str] = field(
        metadata={"doc": "Projected evidence IDs grounding this Signal."}
    )
    source_report_ids: List[str] = field(
        metadata={"doc": "Source report IDs that contributed evidence."}
    )
    topic_ids: List[str] = field(
        metadata={"doc": "Canonical topic/category IDs assigned to the Signal."}
    )
    confidence: float = field(
        metadata={"doc": "Validated confidence score in the inclusive range 0..1."}
    )
    uncertainty: str = field(
        metadata={"doc": "Operator-visible uncertainty or coverage limitation note."}
    )
    validation_status: str = field(
        metadata={"doc": "Signal validation status, for example approved or blocked."}
    )
    target_route: str = field(
        default="wordpress:ml_signal",
        metadata={"doc": "Canonical WordPress route for durable Signal posts."},
    )
