from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.contracts.wordpress import WordPressAuthSettings


@dataclass(frozen=True)
class PublishSettings:
    schema_version: str = field(metadata={"doc": "Publish settings schema version."})
    output_dir: str = field(metadata={"doc": "Output directory containing HTML files."})
    state_db: str = field(metadata={"doc": "SQLite path for publishing state."})
    wp: WordPressAuthSettings = field(metadata={"doc": "WordPress auth settings."})


@dataclass(frozen=True)
class PublishRequest:
    schema_version: str = field(metadata={"doc": "Publish request schema version."})
    html_path: str = field(metadata={"doc": "Filesystem path to HTML file."})
    file_id: Optional[str] = field(default=None, metadata={"doc": "Drive file ID, if known."})


@dataclass(frozen=True)
class PublishOutcome:
    schema_version: str = field(metadata={"doc": "Publish outcome schema version."})
    html_path: str = field(metadata={"doc": "Filesystem path to HTML file."})
    file_id: Optional[str] = field(metadata={"doc": "Drive file ID, if available."})
    status: str = field(metadata={"doc": "Outcome status: published|skipped|error."})
    post_id: Optional[int] = field(default=None, metadata={"doc": "WordPress post ID, if created."})
    post_url: Optional[str] = field(default=None, metadata={"doc": "WordPress post URL, if created."})
    error: Optional[str] = field(default=None, metadata={"doc": "Error code/message when status=error or skipped."})
