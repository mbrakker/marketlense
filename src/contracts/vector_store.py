from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.run_budget import RunBudget
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
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional canonical budget governing this provider call."},
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
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional canonical budget governing this provider call."},
    )


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
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional canonical budget governing this provider call."},
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
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional canonical budget governing this provider call."},
    )


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
class VectorStoreDeleteRequest:
    schema_version: str = field(
        metadata={"doc": "Vector store delete request schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Vector store identifier."})
    missing_ok: bool = field(
        default=True,
        metadata={
            "doc": "When true, missing remote vector stores are treated as already cleaned up."
        },
    )
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional canonical budget governing this provider call."},
    )


@dataclass(frozen=True)
class VectorStoreDeleteResponse:
    schema_version: str = field(
        metadata={"doc": "Vector store delete response schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Vector store identifier."})
    deleted: bool = field(metadata={"doc": "True when the remote store was deleted."})
    missing_remote: bool = field(
        default=False,
        metadata={"doc": "True when the provider reported the store was already absent."},
    )


@dataclass(frozen=True)
class VectorStorePruneItem:
    schema_version: str = field(
        metadata={"doc": "Vector store prune item schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Vector store identifier to prune."})
    reason: str = field(metadata={"doc": "Cleanup reason, e.g. retention_expired."})
    file_id: str = field(
        default="", metadata={"doc": "Optional source Drive file ID for audit logs."}
    )


@dataclass(frozen=True)
class VectorStorePruneRequest:
    schema_version: str = field(
        metadata={"doc": "Vector store prune request schema version."}
    )
    items: List[VectorStorePruneItem] = field(
        metadata={"doc": "Vector store cleanup candidates."}
    )
    missing_ok: bool = field(
        default=True,
        metadata={
            "doc": "When true, missing remote vector stores are treated as already cleaned up."
        },
    )
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional canonical budget governing each provider delete."},
    )


@dataclass(frozen=True)
class VectorStorePruneResponse:
    schema_version: str = field(
        metadata={"doc": "Vector store prune response schema version."}
    )
    requested_count: int = field(metadata={"doc": "Number of requested prune items."})
    deleted_vector_store_ids: List[str] = field(
        metadata={"doc": "Vector store IDs deleted by this prune call."}
    )
    missing_vector_store_ids: List[str] = field(
        metadata={"doc": "Vector store IDs already absent remotely."}
    )
    skipped_duplicate_vector_store_ids: List[str] = field(
        metadata={"doc": "Duplicate vector store IDs skipped within the request."}
    )


@dataclass(frozen=True)
class VectorStoreRetentionCleanupResponse:
    schema_version: str = field(
        metadata={"doc": "Vector store retention cleanup response schema version."}
    )
    scanned_count: int = field(metadata={"doc": "Number of state rows scanned."})
    candidate_count: int = field(metadata={"doc": "Number of cleanup candidates."})
    pruned_vector_store_ids: List[str] = field(
        metadata={"doc": "Vector store IDs deleted or already absent remotely."}
    )
    retention_days: int = field(metadata={"doc": "Retention window used in days."})


@dataclass(frozen=True)
class VectorStoreUpdateMetadataRequest:
    schema_version: str = field(
        metadata={"doc": "Vector store metadata update request schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Vector store identifier to update."})
    metadata: VectorStoreMetadata = field(
        metadata={"doc": "Updated metadata for the vector store."}
    )
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional canonical budget governing this provider call."},
    )


@dataclass(frozen=True)
class VectorStoreUpdateMetadataResponse:
    schema_version: str = field(
        metadata={"doc": "Vector store metadata update response schema version."}
    )
    vector_store_id: str = field(
        metadata={"doc": "Vector store identifier that was updated."}
    )
