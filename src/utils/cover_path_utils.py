from __future__ import annotations

from pathlib import Path

from src.utils.slugify import slugify

_FILE_ID_MAX = 24
_REPORT_SLUG_MAX = 56
_FILENAME_SLUG_MAX = 56


def _bounded_slug(value: str, max_len: int) -> str:
    slug = slugify(value)
    return slug[:max_len] if len(slug) > max_len else slug


def build_cover_asset_path(output_dir: str, file_id: str, title: str, publisher: str) -> Path:
    file_slug = _bounded_slug(file_id, _FILE_ID_MAX)
    report_base = _bounded_slug(f"{title}.pdf", _REPORT_SLUG_MAX)
    filename_base = _bounded_slug(f"{publisher} {title}", _FILENAME_SLUG_MAX)

    report_slug = f"{report_base}-{file_slug}" if not report_base.endswith(file_slug) else report_base
    filename_slug = f"{filename_base}-{file_slug}" if not filename_base.endswith(file_slug) else filename_base

    return Path(output_dir) / report_slug / "assets" / f"{filename_slug}.png"
