from __future__ import annotations

import os
import re
import unicodedata


_SAFE_NAME_RX = re.compile(r"[^A-Za-z0-9._ ()-]")
_PATH_SEPARATOR_RX = re.compile(r"[\\/]+")


def safe_pdf_name(raw_name: str) -> str:
    name = os.path.basename(raw_name)
    name = unicodedata.normalize("NFKD", name)
    name = _SAFE_NAME_RX.sub("_", name).strip()
    if not name.lower().endswith(".pdf"):
        name = name + ".pdf"
    return name


def safe_path_segment(raw_name: str, *, fallback: str) -> str:
    raw = str(raw_name or "")
    parts = _PATH_SEPARATOR_RX.split(raw)
    name = parts[-1] if parts else raw
    name = unicodedata.normalize("NFKD", name)
    name = _SAFE_NAME_RX.sub("_", name).strip(" .")
    if not name or name in {".", ".."}:
        return fallback
    return name
