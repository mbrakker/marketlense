from __future__ import annotations

from urllib.parse import parse_qs, urlsplit


def extract_drive_folder_id(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if "/" not in token and "?" not in token:
        return token
    parts = urlsplit(token)
    path_tokens = [segment for segment in parts.path.split("/") if segment]
    if "folders" in path_tokens:
        index = path_tokens.index("folders")
        if index + 1 < len(path_tokens):
            return path_tokens[index + 1]
    query = parse_qs(parts.query)
    for key in ("id", "folder_id"):
        values = query.get(key)
        if values:
            candidate = str(values[0] or "").strip()
            if candidate:
                return candidate
    return token
