from __future__ import annotations


def pdf_has_eof_marker(data: bytes, tail_bytes: int = 2048) -> bool:
    if not data:
        return False
    window = data[-tail_bytes:] if len(data) > tail_bytes else data
    return b"%%EOF" in window
