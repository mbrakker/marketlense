from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(filename=".env", usecwd=True))


@dataclass(frozen=True)
class Settings:
    google_sa_path: str
    gdrive_folder_id: str
    openai_api_key: str
    openai_model: str
    batch_limit: int
    output_dir: str
    cache_dir: str
    state_db: str
    temperature: float

def load_settings() -> Settings:
    missing = []
    def need(k): 
        v = os.getenv(k)
        if not v: missing.append(k)
        return v
    s = Settings(
        google_sa_path = need("GOOGLE_SERVICE_ACCOUNT_JSON"),
        gdrive_folder_id = need("GDRIVE_FOLDER_ID"),
        openai_api_key = need("OPENAI_API_KEY"),
        openai_model = os.getenv("OPENAI_MODEL", "gpt-5"),
        batch_limit = int(os.getenv("BATCH_LIMIT", "20")),
        output_dir = os.getenv("OUTPUT_DIR", "./out"),
        cache_dir = os.getenv("CACHE_DIR", "./cache"),
        state_db = os.getenv("STATE_DB", "./state/index.sqlite"),
        temperature = float(os.getenv("TEMPERATURE", "1")),
    )
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    Path(s.output_dir).mkdir(parents=True, exist_ok=True)
    Path(s.cache_dir).mkdir(parents=True, exist_ok=True)
    Path(s.state_db).parent.mkdir(parents=True, exist_ok=True)
    return s
