"""Deterministic, Windows-safe paths used by browser acquisition artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

from src.utils.errors import AppError
from src.utils.path_utils import bounded_artifact_filename, safe_path_segment

WINDOWS_PATH_BUDGET = 240
WINDOWS_COMPONENT_BUDGET = 255
IDENTITY_HASH_LENGTH = 12

_WINDOWS_RESERVED_COMPONENT_BASES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"com{superscript}" for superscript in ("¹", "²", "³")),
    *(f"lpt{index}" for index in range(1, 10)),
    *(f"lpt{superscript}" for superscript in ("¹", "²", "³")),
}

_BROWSER_FIXED_ARTIFACTS = (
    "browser-route-playbook-rendered.pdf",
    "onsite_capture.html",
    "onsite_capture.rendered.pdf",
    "terminal_snapshot.html",
    "terminal_screenshot.png",
)
_BROWSER_PROFILE_DESCENDANTS = (
    "Local State",
    "Default/Network/Cookies",
    "Default/Local Storage/leveldb/LOG",
    "Default/Service Worker/Database/LOG",
)
_MANAGED_PROFILE_COMPONENT = "browser-use-user-data-dir-profile-00000000-0000000000000"


def windows_path_units(value: str | Path) -> int:
    """Return the UTF-16 code-unit length used by the Windows path budget."""

    return len(str(value).encode("utf-16-le", errors="surrogatepass")) // 2


def resolve_browser_artifact_path(
    *,
    parent_dir: Path,
    source_name: str,
    extension: str | None = None,
    identity: str = "",
    fixed_name: str | None = None,
    force_identity_hash: bool = False,
    temporary_suffixes: tuple[str, ...] = (),
) -> Path:
    """Build and validate one artifact path before any external I/O occurs."""

    parent = _resolve_path(parent_dir, role="artifact parent directory")
    max_name_units = _available_name_units(parent, temporary_suffixes)
    if max_name_units <= 0:
        raise _path_error(
            role="artifact path",
            path=parent,
            next_action="Set a shorter writable browser output directory",
        )

    if fixed_name is not None:
        filename = _fixed_filename(
            fixed_name,
            extension=extension,
            max_name_units=max_name_units,
            parent=parent,
            temporary_suffixes=temporary_suffixes,
        )
    else:
        filename = _bounded_filename(
            source_name,
            extension=extension,
            identity=identity,
            force_identity_hash=force_identity_hash,
            max_name_units=max_name_units,
            parent=parent,
        )

    return validate_browser_artifact_path(
        parent / filename,
        parent_dir=parent,
        temporary_suffixes=temporary_suffixes,
    )


def validate_browser_artifact_path(
    path: Path,
    *,
    temporary_suffixes: tuple[str, ...] = (),
    parent_dir: Path | None = None,
) -> Path:
    """Validate an already-selected artifact path without creating it."""

    lexical_path = Path(path).expanduser()
    intended_parent = _resolve_path(
        parent_dir if parent_dir is not None else lexical_path.parent,
        role="browser artifact parent directory",
    )
    resolved = _resolve_path(lexical_path, role="browser artifact path")
    try:
        resolved.relative_to(intended_parent)
    except ValueError as exc:
        raise _path_error(
            role="browser artifact path",
            path=resolved,
            cause=exc,
            next_action="Use a destination beneath the browser output directory",
        ) from exc
    _validate_component(resolved.name, path=resolved, role="browser artifact")
    _validate_path_budget(resolved, role="browser artifact")
    for suffix in temporary_suffixes:
        if not suffix or "/" in suffix or "\\" in suffix:
            raise _path_error(
                role="browser temporary artifact path",
                path=resolved,
                next_action="Use a simple temporary suffix such as .part",
            )
        _validate_component(
            f"{resolved.name}{suffix}",
            path=resolved,
            role="browser temporary artifact",
        )
        _validate_path_budget(
            resolved.with_name(f"{resolved.name}{suffix}"),
            role="browser temporary artifact",
        )
    return resolved


def validate_browser_profile_path(
    profile_dir: Path,
    *,
    profile_directory: str = "Default",
    include_session_ledger: bool = False,
) -> Path:
    """Validate a Chromium user-data directory and important descendants."""

    resolved = _resolve_path(profile_dir, role="browser profile directory")
    _validate_component(
        resolved.name,
        path=resolved,
        role="browser profile directory",
    )
    _validate_path_budget(resolved, role="browser profile directory")

    safe_profile_directory = safe_path_segment(
        profile_directory,
        fallback="Default",
    )
    if safe_profile_directory != profile_directory or _is_reserved_component(
        safe_profile_directory
    ):
        raise _path_error(
            role="browser profile directory",
            path=resolved,
            next_action="Use a short safe Chromium profile directory name",
        )
    _validate_component(
        safe_profile_directory,
        path=resolved,
        role="Chromium profile directory name",
    )
    descendants = [
        resolved / relative_path for relative_path in _BROWSER_PROFILE_DESCENDANTS
    ]
    descendants.append(resolved / safe_profile_directory / "Preferences")
    if include_session_ledger:
        descendants.extend(
            (
                resolved / "session_reuse_ledger.json",
                resolved.parent / "session_key_index.json",
            )
        )
    for descendant in descendants:
        _validate_component(
            descendant.name,
            path=descendant,
            role="browser profile descendant",
        )
        _validate_path_budget(descendant, role="browser profile descendant")
    return resolved


def bounded_browser_directory_component(
    *,
    parent_dir: Path,
    raw_name: str,
    identity: str,
    trailing_components: Iterable[str] = (),
    fallback: str = "unknown_host",
) -> str:
    """Return a safe directory component while retaining identity on compaction."""

    parent = _resolve_path(parent_dir, role="browser output root")
    raw = str(raw_name or "").strip() or fallback
    safe_name = safe_path_segment(raw, fallback=fallback)
    identity_value = str(identity or raw)
    needs_hash = (
        safe_name != raw or not raw.isascii() or _is_reserved_component(safe_name)
    )
    suffixes = tuple(str(component) for component in trailing_components)
    available = _directory_component_budget(parent, suffixes)
    if available <= 0:
        raise _path_error(
            role="browser output directory",
            path=parent,
            next_action="Set a shorter writable browser output root",
        )
    if not needs_hash and windows_path_units(safe_name) <= available:
        return safe_name

    digest = hashlib.sha256(identity_value.encode("utf-8")).hexdigest()[
        :IDENTITY_HASH_LENGTH
    ]
    prefix_budget = available - IDENTITY_HASH_LENGTH - 1
    prefix = safe_name[:prefix_budget].rstrip(" ._-") if prefix_budget > 0 else ""
    candidate = f"{prefix}-{digest}" if prefix else digest
    if (
        windows_path_units(candidate) > available
        or windows_path_units(candidate) > WINDOWS_COMPONENT_BUDGET
        or _is_reserved_component(candidate)
    ):
        raise _path_error(
            role="browser output directory",
            path=parent,
            next_action="Set a shorter writable browser output root",
        )
    return candidate


def select_browser_pdf_destination_path(
    *,
    parent_dir: Path,
    source_name: str,
    target_url: str,
) -> Path:
    """Select a deterministic PDF path without trusting an ordinary basename."""

    url_name = Path(urlsplit(str(target_url).strip()).path).name
    original_name = url_name or str(source_name or "").strip() or "download.pdf"
    if not original_name.casefold().endswith(".pdf"):
        original_name = f"{original_name}.pdf"
    normal_path = resolve_browser_artifact_path(
        parent_dir=parent_dir,
        source_name=original_name,
        extension=".pdf",
        identity=target_url,
        temporary_suffixes=(".part",),
    )
    if not normal_path.exists():
        return normal_path
    return resolve_browser_artifact_path(
        parent_dir=parent_dir,
        source_name=original_name,
        extension=".pdf",
        identity=target_url,
        force_identity_hash=True,
        temporary_suffixes=(".part",),
    )


def validate_browser_download_directory(download_dir: Path) -> Path:
    """Validate fixed artifacts and managed-profile descendants below a URL dir."""

    resolved = _resolve_path(download_dir, role="browser download directory")
    try:
        _validate_path_budget(resolved, role="browser download directory")
        for fixed_name in _BROWSER_FIXED_ARTIFACTS:
            validate_browser_artifact_path(
                resolved / fixed_name,
                temporary_suffixes=(".part",),
            )
        validate_browser_profile_path(resolved / _MANAGED_PROFILE_COMPONENT)
    except AppError as exc:
        raise AppError(
            code="browser_download_output_dir_invalid",
            message=(
                "Browser download output directory cannot fit the supported "
                "Windows path policy"
            ),
            cause=exc,
            retryable=False,
            context={
                "windows_path_budget": WINDOWS_PATH_BUDGET,
                "windows_component_budget": WINDOWS_COMPONENT_BUDGET,
                "next_action": "Set a shorter writable browser output_dir",
            },
        ) from exc
    return resolved


def validate_browser_session_reuse_base_path(base_dir: Path) -> Path:
    """Validate the persistent session-reuse root before reads or writes."""

    resolved = _resolve_path(base_dir, role="browser session-reuse directory")
    _validate_path_budget(resolved, role="browser session-reuse directory")
    validate_browser_artifact_path(resolved / "session_key_index.json")
    return resolved


def ensure_browser_directory(
    path: Path,
    *,
    role: str = "browser artifact directory",
    profile: bool = False,
    include_session_ledger: bool = False,
) -> Path:
    """Validate and create a browser-owned directory with typed failures."""

    resolved = (
        validate_browser_profile_path(
            path,
            include_session_ledger=include_session_ledger,
        )
        if profile
        else _resolve_path(path, role=role)
    )
    if not profile:
        _validate_path_budget(resolved, role=role)
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _path_error(
            role=role,
            path=resolved,
            cause=exc,
            next_action="Choose a shorter writable browser directory and retry",
        ) from exc
    return resolved


def _bounded_filename(
    source_name: str,
    *,
    extension: str | None,
    identity: str,
    force_identity_hash: bool,
    max_name_units: int,
    parent: Path,
) -> str:
    raw = str(source_name or "").strip()
    raw_basename = raw.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    safe_name = safe_path_segment(raw_basename, fallback="artifact")
    lossy = safe_name != raw_basename or not raw_basename.isascii()
    normalized_extension = _normalize_extension(extension)
    if normalized_extension and not safe_name.casefold().endswith(
        normalized_extension.casefold()
    ):
        safe_name = f"{safe_name}{normalized_extension}"
    if not safe_name:
        safe_name = f"artifact{normalized_extension}"

    reserved = _is_reserved_component(safe_name) or _has_reserved_alias(safe_name)
    if reserved:
        compact_stem = "artifact"
    else:
        compact_stem = _filename_stem(safe_name, normalized_extension)
    actual_extension = _filename_extension(safe_name, normalized_extension)
    generated_identity = _generated_identity_matches(
        safe_name,
        actual_extension,
        identity,
    )
    hash_like = _has_hash_suffix(safe_name, actual_extension)
    needs_hash = (
        force_identity_hash
        or lossy
        or reserved
        or (hash_like and not generated_identity)
        or windows_path_units(safe_name) > max_name_units
    )
    if generated_identity and not (lossy or reserved):
        if windows_path_units(safe_name) <= max_name_units:
            return safe_name
        compact_stem = compact_stem[: -(IDENTITY_HASH_LENGTH + 1)].rstrip(" ._-")
    if needs_hash:
        digest_source = str(identity or raw_basename or safe_name)
        digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[
            :IDENTITY_HASH_LENGTH
        ]
        if identity:
            safe_name = _identity_bounded_filename(
                compact_stem,
                digest=digest,
                extension=actual_extension,
                max_name_units=max_name_units,
                parent=parent,
            )
        else:
            safe_name = bounded_artifact_filename(
                compact_stem,
                compact_stem=compact_stem or "artifact",
                extension=actual_extension,
                max_length=max_name_units,
            )

    if windows_path_units(safe_name) <= max_name_units:
        return safe_name
    if identity:
        return _identity_bounded_filename(
            _filename_stem(safe_name, actual_extension),
            digest=hashlib.sha256(identity.encode("utf-8")).hexdigest()[
                :IDENTITY_HASH_LENGTH
            ],
            extension=actual_extension,
            max_name_units=max_name_units,
            parent=parent,
        )
    return bounded_artifact_filename(
        _filename_stem(safe_name, actual_extension),
        compact_stem=compact_stem or "artifact",
        extension=actual_extension,
        max_length=max_name_units,
    )


def _identity_bounded_filename(
    stem: str,
    *,
    digest: str,
    extension: str,
    max_name_units: int,
    parent: Path,
) -> str:
    suffix = f"-{digest}{extension}"
    prefix_budget = max_name_units - windows_path_units(suffix)
    if prefix_budget <= 0:
        raise _path_error(
            role="browser artifact path",
            path=parent / suffix,
            next_action="Set a shorter writable browser output directory",
        )
    safe_stem = safe_path_segment(stem, fallback="artifact")
    bounded_stem = _truncate_path_units(
        safe_stem,
        max_units=prefix_budget,
    ).rstrip(" ._-")
    if not bounded_stem:
        bounded_stem = "a"
    return f"{bounded_stem}{suffix}"


def _truncate_path_units(value: str, *, max_units: int) -> str:
    if max_units <= 0:
        return ""
    total = 0
    result: list[str] = []
    for character in value:
        units = windows_path_units(character)
        if total + units > max_units:
            break
        result.append(character)
        total += units
    return "".join(result)


def _fixed_filename(
    fixed_name: str,
    *,
    extension: str | None,
    max_name_units: int,
    parent: Path,
    temporary_suffixes: tuple[str, ...],
) -> str:
    filename = str(fixed_name or "")
    normalized_extension = _normalize_extension(extension)
    if normalized_extension and not filename.casefold().endswith(
        normalized_extension.casefold()
    ):
        filename = f"{filename}{normalized_extension}"
    if (
        not filename
        or "/" in filename
        or "\\" in filename
        or safe_path_segment(filename, fallback="") != filename
        or _is_reserved_component(filename)
        or windows_path_units(filename) > max_name_units
    ):
        raise _path_error(
            role="fixed browser artifact path",
            path=parent / filename,
            next_action="Use a shorter safe fixed artifact name",
        )
    for suffix in temporary_suffixes:
        if windows_path_units(filename + suffix) > WINDOWS_COMPONENT_BUDGET:
            raise _path_error(
                role="fixed browser temporary artifact path",
                path=parent / filename,
                next_action="Use a shorter safe fixed artifact name",
            )
    return filename


def _available_name_units(parent: Path, temporary_suffixes: tuple[str, ...]) -> int:
    suffix_units = max(
        (windows_path_units(suffix) for suffix in temporary_suffixes),
        default=0,
    )
    return min(
        WINDOWS_COMPONENT_BUDGET - suffix_units,
        WINDOWS_PATH_BUDGET - windows_path_units(parent) - 1 - suffix_units,
    )


def _directory_component_budget(parent: Path, suffixes: tuple[str, ...]) -> int:
    if not suffixes:
        suffixes = ("artifact",)
    max_relative_units = 0
    for relative in _BROWSER_FIXED_ARTIFACTS:
        max_relative_units = max(
            max_relative_units,
            windows_path_units("/".join((*suffixes, relative))),
        )
    for relative in _BROWSER_PROFILE_DESCENDANTS:
        max_relative_units = max(
            max_relative_units,
            windows_path_units(
                "/".join((*suffixes, _MANAGED_PROFILE_COMPONENT, relative))
            ),
        )
    return WINDOWS_PATH_BUDGET - windows_path_units(parent) - 1 - max_relative_units


def _filename_stem(filename: str, extension: str) -> str:
    if extension and filename.casefold().endswith(extension.casefold()):
        return filename[: -len(extension)] or "artifact"
    return Path(filename).stem or "artifact"


def _filename_extension(filename: str, extension: str) -> str:
    if extension and filename.casefold().endswith(extension.casefold()):
        return filename[-len(extension) :]
    suffix = Path(filename).suffix
    return suffix if suffix and suffix != filename else ""


def _has_hash_suffix(filename: str, extension: str) -> bool:
    stem = _filename_stem(filename, extension)
    if len(stem) < IDENTITY_HASH_LENGTH + 1:
        return False
    candidate = stem[-IDENTITY_HASH_LENGTH:]
    return (
        stem[-IDENTITY_HASH_LENGTH - 1] == "-"
        and len(candidate) == IDENTITY_HASH_LENGTH
        and all(character in "0123456789abcdefABCDEF" for character in candidate)
    )


def _generated_identity_matches(
    filename: str,
    extension: str,
    identity: str,
) -> bool:
    if not identity or not _has_hash_suffix(filename, extension):
        return False
    stem = _filename_stem(filename, extension)
    expected = hashlib.sha256(identity.encode("utf-8")).hexdigest()[
        :IDENTITY_HASH_LENGTH
    ]
    return stem[-IDENTITY_HASH_LENGTH:].casefold() == expected.casefold()


def _normalize_extension(extension: str | None) -> str:
    value = str(extension or "").strip()
    if not value:
        return ""
    if "/" in value or "\\" in value:
        raise AppError(
            code="browser_download_artifact_path_invalid",
            message="Browser artifact extension contains a path separator",
            retryable=False,
            context={
                "path_role": "browser artifact extension",
                "next_action": "Use a simple file extension such as .pdf",
            },
        )
    return value if value.startswith(".") else f".{value}"


def _resolve_path(value: Path, *, role: str) -> Path:
    try:
        return Path(value).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise _path_error(
            role=role,
            path=value,
            cause=exc,
            next_action="Set a shorter writable browser output directory",
        ) from exc


def _validate_path_budget(path: Path, *, role: str) -> None:
    if windows_path_units(path) > WINDOWS_PATH_BUDGET:
        raise _path_error(
            role=role,
            path=path,
            next_action="Set a shorter writable browser output directory",
        )


def _validate_component(component: str, *, path: Path, role: str) -> None:
    if (
        not component
        or windows_path_units(component) > WINDOWS_COMPONENT_BUDGET
        or "/" in component
        or "\\" in component
        or safe_path_segment(component, fallback="") != component
        or _is_reserved_component(component)
    ):
        raise _path_error(
            role=role,
            path=path,
            next_action="Use a shorter safe browser artifact or profile name",
        )


def _is_reserved_component(value: str) -> bool:
    base_name = str(value or "").split(".", maxsplit=1)[0].rstrip(" .")
    return base_name.casefold() in _WINDOWS_RESERVED_COMPONENT_BASES


def _has_reserved_alias(value: str) -> bool:
    stem = str(value or "").split(".", maxsplit=1)[0]
    token = stem.split("_", maxsplit=1)[0].rstrip(" .")
    return token.casefold() in _WINDOWS_RESERVED_COMPONENT_BASES


def _path_error(
    *,
    role: str,
    path: str | Path,
    cause: Exception | None = None,
    next_action: str,
) -> AppError:
    return AppError(
        code="browser_download_artifact_path_invalid",
        message=f"{role} cannot fit the supported Windows path policy",
        cause=cause,
        retryable=False,
        context={
            "path_role": role,
            "path_units": windows_path_units(path),
            "windows_path_budget": WINDOWS_PATH_BUDGET,
            "windows_component_budget": WINDOWS_COMPONENT_BUDGET,
            "next_action": next_action,
        },
    )


__all__ = [
    "WINDOWS_PATH_BUDGET",
    "WINDOWS_COMPONENT_BUDGET",
    "bounded_browser_directory_component",
    "ensure_browser_directory",
    "resolve_browser_artifact_path",
    "select_browser_pdf_destination_path",
    "validate_browser_artifact_path",
    "validate_browser_download_directory",
    "validate_browser_profile_path",
    "validate_browser_session_reuse_base_path",
    "windows_path_units",
]
