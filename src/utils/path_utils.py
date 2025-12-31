from __future__ import annotations

import os
import re
import unicodedata


_SAFE_NAME_RX = re.compile(r"[^A-Za-z0-9._ ()-]")


def safe_pdf_name(raw_name: str) -> str:
    name = os.path.basename(raw_name)
    name = unicodedata.normalize("NFKD", name)
    name = _SAFE_NAME_RX.sub("_", name).strip()
    if not name.lower().endswith(".pdf"):
        name = name + ".pdf"
    return name
