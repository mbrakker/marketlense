from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class StateCheckRequest:
    schema_version: str = field(metadata={"doc": "State check request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})


@dataclass(frozen=True)
class StateBatchCheckItem:
    schema_version: str = field(metadata={"doc": "State batch-check item schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})


@dataclass(frozen=True)
class StateBatchCheckRequest:
    schema_version: str = field(metadata={"doc": "State batch-check request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    items: List[StateBatchCheckItem] = field(metadata={"doc": "List of file_id+md5 pairs to check."})


@dataclass(frozen=True)
class StateBatchCheckResponse:
    schema_version: str = field(metadata={"doc": "State batch-check response schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    processed_items: List[StateBatchCheckItem] = field(metadata={"doc": "Pairs found in processed state."})


@dataclass(frozen=True)
class StateRecordRequest:
    schema_version: str = field(metadata={"doc": "State record request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})
    openai_file_id: Optional[str] = field(default=None, metadata={"doc": "OpenAI file ID, if any."})
    vector_store_id: Optional[str] = field(default=None, metadata={"doc": "Vector store ID associated with the file, if any."})
    vector_store_status: Optional[str] = field(default=None, metadata={"doc": "Vector store status, if any."})
    indexed_at_utc: Optional[str] = field(default=None, metadata={"doc": "ISO-8601 UTC timestamp when the file was indexed, if known."})
    last_error: Optional[str] = field(default=None, metadata={"doc": "Last error encountered during vector store operations, if any."})
    text_validation_status: Optional[str] = field(default=None, metadata={"doc": "Extractable text validation status: pass|fail, if evaluated."})
    text_validation_reason: Optional[str] = field(default=None, metadata={"doc": "Extractable text validation failure reason, if any."})
    text_validation_pages: Optional[List[int]] = field(default=None, metadata={"doc": "Page numbers sampled for extractable text validation."})
    doc_map_summary: Optional[Dict[str, object]] = field(default=None, metadata={"doc": "DocMap validation summary when doc_map is empty, if available."})


@dataclass(frozen=True)
class StateDbAccessRequest:
    schema_version: str = field(metadata={"doc": "State DB access check request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    timeout_seconds: float = field(default=0.0, metadata={"doc": "SQLite connection timeout in seconds for lock detection."})


@dataclass(frozen=True)
class StateDbAccessResponse:
    schema_version: str = field(metadata={"doc": "State DB access check response schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    accessible: bool = field(metadata={"doc": "True when the state DB can be opened for writing."})
    locked: bool = field(metadata={"doc": "True when the state DB is locked by another process."})
    message: str = field(default="", metadata={"doc": "Additional detail for the access check result."})


@dataclass(frozen=True)
class StateIngestCursorGetRequest:
    schema_version: str = field(metadata={"doc": "Ingest cursor get request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})


@dataclass(frozen=True)
class StateIngestCursorGetResponse:
    schema_version: str = field(metadata={"doc": "Ingest cursor get response schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    last_successful_ingest_utc: Optional[str] = field(default=None, metadata={"doc": "RFC3339 timestamp of last successful ingest run."})


@dataclass(frozen=True)
class StateIngestCursorSetRequest:
    schema_version: str = field(metadata={"doc": "Ingest cursor set request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    last_successful_ingest_utc: str = field(metadata={"doc": "RFC3339 timestamp of last successful ingest run."})


@dataclass(frozen=True)
class StateGetRequest:
    schema_version: str = field(metadata={"doc": "State get request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})


@dataclass(frozen=True)
class StateGetResponse:
    schema_version: str = field(metadata={"doc": "State get response schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})
    processed_at: int = field(metadata={"doc": "Unix timestamp of processing."})
    openai_file_id: Optional[str] = field(default=None, metadata={"doc": "OpenAI file ID, if any."})
    vector_store_id: Optional[str] = field(default=None, metadata={"doc": "Vector store ID associated with the file, if any."})
    vector_store_status: Optional[str] = field(default=None, metadata={"doc": "Vector store status, if any."})
    indexed_at_utc: Optional[str] = field(default=None, metadata={"doc": "ISO-8601 UTC timestamp when the file was indexed, if known."})
    last_error: Optional[str] = field(default=None, metadata={"doc": "Last error encountered during vector store operations, if any."})
    text_validation_status: Optional[str] = field(default=None, metadata={"doc": "Extractable text validation status: pass|fail, if evaluated."})
    text_validation_reason: Optional[str] = field(default=None, metadata={"doc": "Extractable text validation failure reason, if any."})
    text_validation_pages: Optional[List[int]] = field(default=None, metadata={"doc": "Page numbers sampled for extractable text validation."})
    doc_map_summary: Optional[Dict[str, object]] = field(default=None, metadata={"doc": "DocMap validation summary when doc_map is empty, if available."})


@dataclass(frozen=True)
class StatePublishCheckRequest:
    schema_version: str = field(metadata={"doc": "Publish check request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for publishing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    post_type: str = field(
        metadata={"doc": "WordPress post type slug tracked for this publish target."}
    )


@dataclass(frozen=True)
class StatePublishRecordRequest:
    schema_version: str = field(metadata={"doc": "Publish record request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for publishing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})
    wp_post_id: int = field(metadata={"doc": "WordPress post ID."})
    wp_post_url: str = field(metadata={"doc": "WordPress post URL."})
    post_type: str = field(
        metadata={"doc": "WordPress post type slug used for this publish record."}
    )


@dataclass(frozen=True)
class StatePublishGetResponse:
    schema_version: str = field(metadata={"doc": "Publish get response schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})
    published_at: int = field(metadata={"doc": "Unix timestamp of publish time."})
    wp_post_id: int = field(metadata={"doc": "WordPress post ID."})
    wp_post_url: str = field(metadata={"doc": "WordPress post URL."})
    post_type: str = field(
        metadata={"doc": "WordPress post type slug used for this publish record."}
    )


@dataclass(frozen=True)
class StateProcessedListRequest:
    schema_version: str = field(metadata={"doc": "Processed-state list request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    limit: int = field(default=200, metadata={"doc": "Maximum number of rows to return."})


@dataclass(frozen=True)
class StateProcessedRow:
    schema_version: str = field(metadata={"doc": "Processed-state row schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the processed PDF."})
    processed_at: int = field(metadata={"doc": "Unix timestamp when processing completed."})
    openai_file_id: Optional[str] = field(default=None, metadata={"doc": "OpenAI file ID, if any."})
    vector_store_id: Optional[str] = field(default=None, metadata={"doc": "Vector store ID, if any."})
    vector_store_status: Optional[str] = field(default=None, metadata={"doc": "Vector store indexing status, if any."})
    indexed_at_utc: Optional[str] = field(default=None, metadata={"doc": "Vector store indexed timestamp, if known."})
    last_error: Optional[str] = field(default=None, metadata={"doc": "Last error recorded for this file, if any."})
    text_validation_status: Optional[str] = field(default=None, metadata={"doc": "Extractable text validation status: pass|fail, if evaluated."})
    text_validation_reason: Optional[str] = field(default=None, metadata={"doc": "Extractable text validation failure reason, if any."})
    text_validation_pages: Optional[List[int]] = field(default=None, metadata={"doc": "Page numbers sampled for extractable text validation."})
    doc_map_summary: Optional[Dict[str, object]] = field(default=None, metadata={"doc": "DocMap summary payload when processing halted on doc_map_empty, if any."})


@dataclass(frozen=True)
class StateProcessedListResponse:
    schema_version: str = field(metadata={"doc": "Processed-state list response schema version."})
    rows: List[StateProcessedRow] = field(metadata={"doc": "Processed-state rows ordered by recency."})


@dataclass(frozen=True)
class StatePublishedListRequest:
    schema_version: str = field(metadata={"doc": "Published-state list request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for publishing state."})
    limit: int = field(default=200, metadata={"doc": "Maximum number of rows to return."})


@dataclass(frozen=True)
class StatePublishedRow:
    schema_version: str = field(metadata={"doc": "Published-state row schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum recorded at publish time."})
    published_at: int = field(metadata={"doc": "Unix timestamp when publishing completed."})
    wp_post_id: int = field(metadata={"doc": "WordPress post ID."})
    wp_post_url: str = field(metadata={"doc": "WordPress post URL."})
    post_type: str = field(
        metadata={"doc": "WordPress post type slug used for this publish record."}
    )


@dataclass(frozen=True)
class StatePublishedListResponse:
    schema_version: str = field(metadata={"doc": "Published-state list response schema version."})
    rows: List[StatePublishedRow] = field(metadata={"doc": "Published-state rows ordered by recency."})
