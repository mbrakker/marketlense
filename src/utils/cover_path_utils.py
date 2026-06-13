from __future__ import annotations

from pathlib import Path

from src.utils.slugify import slugify

_FILE_ID_MAX = 24
_REPORT_SLUG_MAX = 56
_FILENAME_SLUG_MAX = 56


def _bounded_slug(value: str, max_len: int) -> str:
    slug = slugify(value)
    return slug[:max_len] if len(slug) > max_len else slug


def build_cover_asset_path(
    output_dir: str,
    file_id: str,
    title: str,
    publisher: str,
    report_slug: str | None = None,
) -> Path:
    file_slug = _bounded_slug(file_id, _FILE_ID_MAX)
    filename_base = _bounded_slug(f"{publisher} {title}", _FILENAME_SLUG_MAX)
    normalized_report_slug = slugify(report_slug) if report_slug else ""
    if normalized_report_slug:
        report_slug_final = normalized_report_slug
    else:
        report_base = _bounded_slug(f"{title}.pdf", _REPORT_SLUG_MAX)
        report_slug_final = (
            f"{report_base}-{file_slug}"
            if not report_base.endswith(file_slug)
            else report_base
        )
    filename_slug = (
        f"{filename_base}-{file_slug}"
        if not filename_base.endswith(file_slug)
        else filename_base
    )

    return Path(output_dir) / report_slug_final / "assets" / f"{filename_slug}.png"


def build_report_card_asset_path(
    output_dir: str,
    file_id: str,
    title: str,
    report_slug: str | None,
    size: str,
) -> Path:
    normalized_report_slug = slugify(report_slug) if report_slug else ""
    if not normalized_report_slug:
        file_slug = _bounded_slug(file_id, _FILE_ID_MAX)
        report_base = _bounded_slug(f"{title}.pdf", _REPORT_SLUG_MAX)
        normalized_report_slug = (
            f"{report_base}-{file_slug}"
            if not report_base.endswith(file_slug)
            else report_base
        )
    return (
        Path(output_dir) / normalized_report_slug / "assets" / f"report-card-{size}.png"
    )
