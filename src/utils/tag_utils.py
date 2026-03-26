from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_slug_tag(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    normalized = re.sub(r"[\W]+", "_", normalized)
    return normalized.strip("_")
