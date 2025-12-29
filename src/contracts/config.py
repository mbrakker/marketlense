from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppSettings:
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
