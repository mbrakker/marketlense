from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.semantic_ids import ReportId, SemanticIdContract


@dataclass(frozen=True)
class VectorStoreMetadata(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Vector store metadata schema version."}
    )
    report_id: ReportId = field(
        metadata={"doc": "Report identifier associated with this vector store."}
    )
    report_name: str = field(
        metadata={
            "doc": "Human-friendly report name associated with this vector store."
        }
    )
    taxonomy: List[str] = field(
        default_factory=list, metadata={"doc": "Taxonomy tags applied to the report."}
    )
    categories: List[str] = field(
        default_factory=list, metadata={"doc": "Assigned category IDs for the report."}
    )
    region: str = field(
        default="", metadata={"doc": "Primary region/market focus for the report."}
    )
    time_period: str = field(
        default="", metadata={"doc": "Primary time period covered by the report."}
    )


@dataclass(frozen=True)
class VectorStoreCreateRequest:
    schema_version: str = field(
        metadata={"doc": "Vector store create request schema version."}
    )
    name: str = field(metadata={"doc": "Human-readable name for the vector store."})
    metadata: VectorStoreMetadata = field(
        metadata={"doc": "Metadata to attach to the vector store."}
    )


@dataclass(frozen=True)
class VectorStoreCreateResponse:
    schema_version: str = field(
        metadata={"doc": "Vector store create response schema version."}
    )
    vector_store_id: str = field(
        metadata={"doc": "Identifier of the created vector store."}
    )


@dataclass(frozen=True)
class VectorStoreUploadFileRequest:
    schema_version: str = field(
        metadata={"doc": "Vector store upload file request schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Target vector store identifier."})
    file_path: str = field(metadata={"doc": "Path to the file to upload."})


@dataclass(frozen=True)
class VectorStoreUploadFileResponse:
    schema_version: str = field(
        metadata={"doc": "Vector store upload file response schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Target vector store identifier."})
    openai_file_id: str = field(metadata={"doc": "Provider-specific file identifier."})


@dataclass(frozen=True)
class VectorStoreAttachFileRequest:
    schema_version: str = field(
        metadata={"doc": "Vector store attach file request schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Target vector store identifier."})
    openai_file_id: str = field(
        metadata={"doc": "Provider-specific file identifier to attach."}
    )


@dataclass(frozen=True)
class VectorStoreAttachFileResponse:
    schema_version: str = field(
        metadata={"doc": "Vector store attach file response schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Target vector store identifier."})
    openai_file_id: str = field(
        metadata={"doc": "Provider-specific file identifier that was attached."}
    )


@dataclass(frozen=True)
class VectorStoreStatusRequest:
    schema_version: str = field(
        metadata={"doc": "Vector store status request schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Vector store identifier."})


@dataclass(frozen=True)
class VectorStoreStatusResponse:
    schema_version: str = field(
        metadata={"doc": "Vector store status response schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Vector store identifier."})
    status: str = field(
        metadata={"doc": "Current status string reported by the provider."}
    )
    indexed_at_utc: Optional[str] = field(
        default=None,
        metadata={"doc": "ISO-8601 UTC timestamp when indexing completed, if known."},
    )
    last_error: Optional[str] = field(
        default=None, metadata={"doc": "Last error message, if any."}
    )


@dataclass(frozen=True)
class VectorStoreUpdateMetadataRequest:
    schema_version: str = field(
        metadata={"doc": "Vector store metadata update request schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Vector store identifier to update."})
    metadata: VectorStoreMetadata = field(
        metadata={"doc": "Updated metadata for the vector store."}
    )


@dataclass(frozen=True)
class VectorStoreUpdateMetadataResponse:
    schema_version: str = field(
        metadata={"doc": "Vector store metadata update response schema version."}
    )
    vector_store_id: str = field(
        metadata={"doc": "Vector store identifier that was updated."}
    )
