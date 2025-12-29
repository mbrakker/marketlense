from __future__ import annotations

from pathlib import Path


def pdf_has_eof_marker(path: str, tail_bytes: int = 2048) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    try:
        with p.open("rb") as fh:
            if p.stat().st_size <= tail_bytes:
                data = fh.read()
            else:
                fh.seek(-tail_bytes, 2)
                data = fh.read()
        return b"%%EOF" in data
    except Exception:
        return False
