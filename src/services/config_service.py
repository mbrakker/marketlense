from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

from src.contracts.config import AppSettings


def load_settings() -> AppSettings:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))

    missing = []

    def need(k: str) -> str:
        v = os.getenv(k)
        if not v:
            missing.append(k)
        return v or ""

    settings = AppSettings(
        schema_version="1.0",
        google_sa_path=need("GOOGLE_SERVICE_ACCOUNT_JSON"),
        gdrive_folder_id=need("GDRIVE_FOLDER_ID"),
        openai_api_key=need("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5"),
        batch_limit=int(os.getenv("BATCH_LIMIT", "20")),
        output_dir=os.getenv("OUTPUT_DIR", "./out"),
        cache_dir=os.getenv("CACHE_DIR", "./cache"),
        state_db=os.getenv("STATE_DB", "./state/index.sqlite"),
        temperature=float(os.getenv("TEMPERATURE", "1")),
    )

    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.state_db).parent.mkdir(parents=True, exist_ok=True)
    return settings
