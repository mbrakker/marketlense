from __future__ import annotations

import hashlib
import os
from pathlib import Path

from src.utils.errors import AppError
from src.utils.path_utils import (
    WINDOWS_COMPONENT_BUDGET,
    WINDOWS_PATH_BUDGET,
    is_windows_reserved_component,
    safe_path_segment,
    windows_path_units,
)
from src.utils.slugify import slugify

_FILE_ID_MAX = 24
_REPORT_SLUG_MAX = 56
_FILENAME_SLUG_MAX = 56
_ASSET_DIRECTORY = "assets"
_COMPACT_SUFFIX_LENGTH = 12
_PNG_SUFFIX = ".png"


def _bounded_slug(value: str, max_len: int) -> str:
    slug = slugify(value)
    return slug[:max_len] if len(slug) > max_len else slug


def _cover_path_error(
    destination: Path,
    root: Path,
    reason: str,
    violated_limit: str,
) -> AppError:
    return AppError(
        code="cover_asset_path_invalid",
        message=(
            f"Cover asset destination is invalid: {destination} ({reason}). "
            f"Configured root: {root}. Violated limit: {violated_limit}. "
            "Please shorten output_dir."
        ),
        retryable=False,
        context={
            "destination": str(destination),
            "configured_root": str(root),
            "violated_limit": violated_limit,
            "recommendation": "shorten output_dir",
        },
    )


def _absolute_path(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(Path(path).expanduser())))


def _resolved_root(output_dir: str | Path) -> tuple[Path, Path]:
    display_root = Path(output_dir).expanduser()
    return display_root, _absolute_path(display_root)


def _path_parts(path: Path) -> tuple[str, ...]:
    return tuple(part for part in path.parts if part not in {path.anchor, "", "."})


def _validate_root(display_root: Path, resolved_root: Path) -> None:
    if windows_path_units(str(resolved_root)) > WINDOWS_PATH_BUDGET:
        raise _cover_path_error(
            resolved_root,
            resolved_root,
            "the configured root is already too long",
            f"absolute root path > {WINDOWS_PATH_BUDGET} UTF-16 units",
        )
    for component in _path_parts(resolved_root):
        if windows_path_units(component) > WINDOWS_COMPONENT_BUDGET:
            raise _cover_path_error(
                resolved_root,
                resolved_root,
                f"root component {component!r} is too long",
                f"component > {WINDOWS_COMPONENT_BUDGET} UTF-16 units",
            )
        if is_windows_reserved_component(component):
            raise _cover_path_error(
                resolved_root,
                resolved_root,
                f"root component {component!r} is a Windows reserved name",
                "reserved Windows component",
            )


def _validate_destination(
    destination: Path,
    resolved_root: Path,
) -> tuple[bool, str, str]:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    resolved_destination = _absolute_path(destination)
    resolved_temporary = _absolute_path(temporary)

    for candidate, label in (
        (resolved_destination, "final PNG path"),
        (resolved_temporary, "temporary PNG path"),
    ):
        try:
            candidate.relative_to(resolved_root)
        except ValueError:
            return (
                False,
                f"{label} escapes the configured output root",
                "root containment",
            )
        if windows_path_units(candidate) > WINDOWS_PATH_BUDGET:
            return (
                False,
                f"{label} is too long",
                f"{label} > {WINDOWS_PATH_BUDGET} UTF-16 units",
            )
        for component in _path_parts(candidate):
            if windows_path_units(component) > WINDOWS_COMPONENT_BUDGET:
                return (
                    False,
                    f"{label} contains an oversized component {component!r}",
                    f"component > {WINDOWS_COMPONENT_BUDGET} UTF-16 units",
                )
            if is_windows_reserved_component(component):
                return (
                    False,
                    f"{label} contains reserved component {component!r}",
                    "reserved Windows component",
                )
    return True, "", ""


def _validate_or_raise(destination: Path, resolved_root: Path) -> Path:
    valid, reason, violated_limit = _validate_destination(destination, resolved_root)
    if not valid:
        raise _cover_path_error(destination, resolved_root, reason, violated_limit)
    return destination


def validate_cover_asset_output_path(output_path: str | Path) -> tuple[Path, Path]:
    """Validate deterministic path budgets before a service performs filesystem I/O."""

    destination = Path(output_path)
    display_root, resolved_root = _resolved_root(destination.parent)
    _validate_root(display_root, resolved_root)
    _validate_or_raise(destination, resolved_root)
    return destination, destination.with_suffix(destination.suffix + ".tmp")


def _identity_suffix(identity: str) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:_COMPACT_SUFFIX_LENGTH]


def _truncate_to_units(value: str, budget: int) -> str:
    if budget <= 0:
        return ""
    result: list[str] = []
    used = 0
    for character in value:
        units = windows_path_units(character)
        if used + units > budget:
            break
        result.append(character)
        used += units
    return "".join(result)


def _compact_component(component: str, identity: str, prefix_units: int) -> str:
    extension = Path(component).suffix
    stem = component[: -len(extension)] if extension else component
    suffix = f"-{_identity_suffix(identity)}{extension}"
    prefix_budget = max(
        0,
        min(
            prefix_units,
            WINDOWS_COMPONENT_BUDGET - windows_path_units(suffix),
        ),
    )
    prefix = _truncate_to_units(stem, prefix_budget).rstrip(" .-_")
    return f"{prefix}{suffix}" if prefix else suffix[1:]


def _candidate(
    display_root: Path,
    resolved_root: Path,
    report_component: str,
    filename: str,
) -> Path | None:
    destination = display_root / report_component / _ASSET_DIRECTORY / filename
    valid, _, _ = _validate_destination(destination, resolved_root)
    return destination if valid else None


def _compact_path(
    display_root: Path,
    resolved_root: Path,
    report_component: str,
    filename: str,
    report_identity: str,
    filename_identity: str,
) -> Path:
    report_requires_compaction = is_windows_reserved_component(report_component)
    filename_requires_compaction = is_windows_reserved_component(filename)

    if not report_requires_compaction:
        for prefix_units in range(windows_path_units(report_component), -1, -1):
            compacted_report = _compact_component(
                report_component, report_identity, prefix_units
            )
            candidate = _candidate(
                display_root, resolved_root, compacted_report, filename
            )
            if candidate is not None:
                return candidate

    if not filename_requires_compaction:
        for prefix_units in range(windows_path_units(filename), -1, -1):
            compacted_filename = _compact_component(
                filename, filename_identity, prefix_units
            )
            candidate = _candidate(
                display_root, resolved_root, report_component, compacted_filename
            )
            if candidate is not None:
                return candidate

    compacted_report = _compact_component(report_component, report_identity, 0)
    compacted_filename = _compact_component(filename, filename_identity, 0)
    minimum = _candidate(
        display_root, resolved_root, compacted_report, compacted_filename
    )
    if minimum is None:
        destination = display_root / report_component / _ASSET_DIRECTORY / filename
        raise _cover_path_error(
            destination,
            resolved_root,
            "the minimum deterministic compact path does not fit",
            f"final or temporary path > {WINDOWS_PATH_BUDGET} UTF-16 units",
        )

    best_report = compacted_report
    for prefix_units in range(
        1, min(windows_path_units(report_component), WINDOWS_COMPONENT_BUDGET) + 1
    ):
        candidate_report = _compact_component(
            report_component, report_identity, prefix_units
        )
        if (
            _candidate(
                display_root, resolved_root, candidate_report, compacted_filename
            )
            is not None
        ):
            best_report = candidate_report

    best_filename = compacted_filename
    for prefix_units in range(
        1, min(windows_path_units(filename), WINDOWS_COMPONENT_BUDGET) + 1
    ):
        candidate_filename = _compact_component(
            filename, filename_identity, prefix_units
        )
        if (
            _candidate(display_root, resolved_root, best_report, candidate_filename)
            is not None
        ):
            best_filename = candidate_filename

    resolved = _candidate(display_root, resolved_root, best_report, best_filename)
    if resolved is None:
        destination = display_root / report_component / _ASSET_DIRECTORY / filename
        raise _cover_path_error(
            destination,
            resolved_root,
            "compacted path validation failed",
            f"final or temporary path > {WINDOWS_PATH_BUDGET} UTF-16 units",
        )
    return resolved


def _compact_filename_for_report(
    display_root: Path,
    resolved_root: Path,
    report_component: str,
    filename: str,
    filename_identity: str,
) -> Path:
    original = _candidate(display_root, resolved_root, report_component, filename)
    if original is not None:
        return original
    for prefix_units in range(windows_path_units(filename), -1, -1):
        compacted_filename = _compact_component(
            filename, filename_identity, prefix_units
        )
        candidate = _candidate(
            display_root, resolved_root, report_component, compacted_filename
        )
        if candidate is not None:
            return candidate
    destination = display_root / report_component / _ASSET_DIRECTORY / filename
    raise _cover_path_error(
        destination,
        resolved_root,
        "the filename cannot be compacted to a valid destination",
        f"final or temporary path > {WINDOWS_PATH_BUDGET} UTF-16 units",
    )


def _resolve_cover_path(
    output_dir: str,
    report_component: str,
    filename: str,
    *,
    report_identity: str,
    filename_identity: str,
    compaction_filename: str | None = None,
) -> Path:
    display_root, resolved_root = _resolved_root(output_dir)
    _validate_root(display_root, resolved_root)
    resolution_filename = compaction_filename or filename
    resolved = _candidate(
        display_root, resolved_root, report_component, resolution_filename
    )
    if resolved is None:
        resolved = _compact_path(
            display_root,
            resolved_root,
            report_component,
            resolution_filename,
            report_identity,
            filename_identity,
        )
    stable_report_component = resolved.parent.parent.name
    return _compact_filename_for_report(
        display_root,
        resolved_root,
        stable_report_component,
        filename,
        filename_identity,
    )


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
    return _resolve_cover_path(
        output_dir,
        report_slug_final,
        f"{filename_slug}{_PNG_SUFFIX}",
        report_identity=f"report:{report_slug or ''}\x1f{title}\x1f{file_id}",
        filename_identity=(
            f"cover:{publisher}\x1f{title}\x1f{file_id}\x1f{report_slug or ''}"
        ),
    )


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
    safe_size = safe_path_segment(size, fallback="medium")
    return _resolve_cover_path(
        output_dir,
        normalized_report_slug,
        f"report-card-{safe_size}{_PNG_SUFFIX}",
        report_identity=f"report-card:{report_slug or ''}\x1f{title}\x1f{file_id}",
        filename_identity=f"report-card-file:{file_id}\x1f{title}\x1f{size}",
        compaction_filename="report-card-medium.png",
    )
