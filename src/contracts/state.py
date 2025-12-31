from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class StateCheckRequest:
    schema_version: str = field(metadata={"doc": "State check request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})


@dataclass(frozen=True)
class StateRecordRequest:
    schema_version: str = field(metadata={"doc": "State record request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})
    openai_file_id: Optional[str] = field(metadata={"doc": "OpenAI file ID, if any."})


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
    openai_file_id: Optional[str] = field(metadata={"doc": "OpenAI file ID, if any."})


@dataclass(frozen=True)
class StatePublishCheckRequest:
    schema_version: str = field(metadata={"doc": "Publish check request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for publishing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})


@dataclass(frozen=True)
class StatePublishRecordRequest:
    schema_version: str = field(metadata={"doc": "Publish record request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for publishing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})
    wp_post_id: int = field(metadata={"doc": "WordPress post ID."})
    wp_post_url: str = field(metadata={"doc": "WordPress post URL."})


@dataclass(frozen=True)
class StatePublishGetResponse:
    schema_version: str = field(metadata={"doc": "Publish get response schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})
    published_at: int = field(metadata={"doc": "Unix timestamp of publish time."})
    wp_post_id: int = field(metadata={"doc": "WordPress post ID."})
    wp_post_url: str = field(metadata={"doc": "WordPress post URL."})
