from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class VectorStoreCreateRequest:
    schema_version: str = field(metadata={"doc": "Vector store create request schema version."})
    name: str = field(metadata={"doc": "Human-readable name for the vector store."})


@dataclass(frozen=True)
class VectorStoreCreateResponse:
    schema_version: str = field(metadata={"doc": "Vector store create response schema version."})
    vector_store_id: str = field(metadata={"doc": "Identifier of the created vector store."})


@dataclass(frozen=True)
class VectorStoreUploadFileRequest:
    schema_version: str = field(metadata={"doc": "Vector store upload file request schema version."})
    vector_store_id: str = field(metadata={"doc": "Target vector store identifier."})
    file_path: str = field(metadata={"doc": "Path to the file to upload."})


@dataclass(frozen=True)
class VectorStoreUploadFileResponse:
    schema_version: str = field(metadata={"doc": "Vector store upload file response schema version."})
    vector_store_id: str = field(metadata={"doc": "Target vector store identifier."})
    openai_file_id: str = field(metadata={"doc": "Provider-specific file identifier."})


@dataclass(frozen=True)
class VectorStoreAttachFileRequest:
    schema_version: str = field(metadata={"doc": "Vector store attach file request schema version."})
    vector_store_id: str = field(metadata={"doc": "Target vector store identifier."})
    openai_file_id: str = field(metadata={"doc": "Provider-specific file identifier to attach."})


@dataclass(frozen=True)
class VectorStoreAttachFileResponse:
    schema_version: str = field(metadata={"doc": "Vector store attach file response schema version."})
    vector_store_id: str = field(metadata={"doc": "Target vector store identifier."})
    openai_file_id: str = field(metadata={"doc": "Provider-specific file identifier that was attached."})


@dataclass(frozen=True)
class VectorStoreStatusResponse:
    schema_version: str = field(metadata={"doc": "Vector store status response schema version."})
    vector_store_id: str = field(metadata={"doc": "Vector store identifier."})
    status: str = field(metadata={"doc": "Current status string reported by the provider."})
    indexed_at_utc: Optional[str] = field(default=None, metadata={"doc": "ISO-8601 UTC timestamp when indexing completed, if known."})
    last_error: Optional[str] = field(default=None, metadata={"doc": "Last error message, if any."})
