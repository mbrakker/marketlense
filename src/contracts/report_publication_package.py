"""Versioned retained report publication surfaces."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReportPublicationPackage:
    """References to immutable HTML, readiness and their generation-bound manifest."""

    schema_version: str = field(metadata={"doc": "Publication package schema version."})
    html_path: str = field(metadata={"doc": "Path to the immutable report HTML."})
    readiness_path: str = field(metadata={"doc": "Path to the readiness snapshot."})
    manifest_path: str = field(metadata={"doc": "Path to the package manifest."})
    generation: str = field(metadata={"doc": "Bound analysis generation identity."})
    checksum: str = field(metadata={"doc": "Checksum of the publication package."})
