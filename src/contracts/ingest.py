from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class IngestSettings:
    schema_version: str
    google_sa_path: str
    gdrive_folder_id: str
    openai_api_key: str
    openai_model: str
    batch_limit: int
    output_dir: str
    cache_dir: str
    state_db: str
    temperature: float


@dataclass(frozen=True)
class IngestOutcome:
    schema_version: str
    file_id: str
    name: str
    md5: Optional[str]
    html_path: Optional[str]
    status: str  # processed|skipped|error
    error: Optional[str] = None
