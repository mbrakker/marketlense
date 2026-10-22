from __future__ import annotations

import hashlib
import os
import re
import unicodedata

_SAFE_NAME_RX = re.compile(r"[^A-Za-z0-9._ ()-]")
_PATH_SEPARATOR_RX = re.compile(r"[\\/]+")
WINDOWS_PATH_BUDGET = 240
WINDOWS_COMPONENT_BUDGET = 255
_WINDOWS_RESERVED_COMPONENT_BASES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
    *(f"com{superscript}" for superscript in ("¹", "²", "³")),
    *(f"lpt{superscript}" for superscript in ("¹", "²", "³")),
}


def windows_path_units(value: str | os.PathLike[str]) -> int:
    """Return the UTF-16 code-unit length used by the Windows path budget."""

    return len(os.fspath(value).encode("utf-16-le", errors="surrogatepass")) // 2


def is_windows_reserved_component(value: str) -> bool:
    """Return whether a filename component uses a reserved Windows device name."""

    base_name = str(value or "").split(".", maxsplit=1)[0].rstrip(" .")
    return base_name.casefold() in _WINDOWS_RESERVED_COMPONENT_BASES


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


def bounded_artifact_filename(
    stem: str,
    *,
    compact_stem: str,
    extension: str,
    max_length: int = 96,
) -> str:
    normalized_extension = extension if extension.startswith(".") else f".{extension}"
    filename = f"{stem}{normalized_extension}"
    if len(filename) <= max_length:
        return filename

    digest = hashlib.sha256(filename.encode("utf-8")).hexdigest()[:12]
    safe_compact_stem = safe_path_segment(compact_stem, fallback="artifact")
    suffix = f"-{digest}{normalized_extension}"
    compact_budget = max_length - len(suffix)
    bounded_stem = safe_compact_stem[:compact_budget].rstrip(" .-_") or "artifact"
    return f"{bounded_stem}{suffix}"
