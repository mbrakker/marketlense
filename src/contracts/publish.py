from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.contracts.wordpress import WordPressAuthSettings


@dataclass(frozen=True)
class PublishSettings:
    schema_version: str
    output_dir: str
    state_db: str
    wp: WordPressAuthSettings


@dataclass(frozen=True)
class PublishRequest:
    schema_version: str
    html_path: str
    file_id: Optional[str] = None


@dataclass(frozen=True)
class PublishOutcome:
    schema_version: str
    html_path: str
    file_id: Optional[str]
    status: str  # published|skipped|error
    post_id: Optional[int] = None
    post_url: Optional[str] = None
    error: Optional[str] = None
