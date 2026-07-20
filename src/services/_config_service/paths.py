from __future__ import annotations

from pathlib import Path
from typing import Any

from src.services._config_service.common import (
    DEFAULT_HTML_TAG_ACRONYMS_PATH,
    _ConfigResolver,
    _env_value,
    _is_missing,
    _resolve_optional_path,
)


def _resolve_paths_settings(
    paths: dict[str, Any],
    resolver: _ConfigResolver,
    *,
    runtime_base_path: Path,
) -> dict[str, str]:
    output_dir = resolver.need_path(
        paths,
        "output_dir",
        "paths.output_dir",
        base_path=runtime_base_path,
        env_key="OUTPUT_DIR",
    )
    cache_dir = resolver.need_path(
        paths,
        "cache_dir",
        "paths.cache_dir",
        base_path=runtime_base_path,
        env_key="CACHE_DIR",
    )
    state_db = resolver.need_path(
        paths,
        "state_db",
        "paths.state_db",
        base_path=runtime_base_path,
        env_key="STATE_DB",
    )
    reports_db = resolver.need_path(
        paths,
        "reports_db",
        "paths.reports_db",
        base_path=runtime_base_path,
        env_key="REPORTS_DB",
    )
    signal_store_db = _resolve_optional_path(
        paths.get("signal_store_db") or _env_value("SIGNAL_STORE_DB"),
        base_path=runtime_base_path,
    )
    if _is_missing(signal_store_db):
        signal_store_db = str(Path(state_db).parent / "signals.sqlite")
    lock_path_raw = paths.get("ingest_lock")
    if _is_missing(lock_path_raw):
        lock_path_raw = _env_value("INGEST_LOCK_PATH")
    if _is_missing(lock_path_raw):
        lock_path_raw = str(Path(state_db).parent / "ingest.lock")
    return {
        "output_dir": output_dir,
        "cache_dir": cache_dir,
        "state_db": state_db,
        "reports_db": reports_db,
        "signal_store_db": signal_store_db,
        "publisher_profiles_path": _resolve_optional_path(
            paths.get("publisher_profiles")
            or str(
                Path(__file__).resolve().parents[3]
                / "Wordpress"
                / "config"
                / "publisher-profiles.json"
            ),
            base_path=runtime_base_path,
        ),
        "category_mapping_path": _resolve_optional_path(
            paths.get("category_mappings")
            or str(
                Path(__file__).resolve().parents[2]
                / "config"
                / "category-mappings.yaml"
            ),
            base_path=runtime_base_path,
        ),
        "html_tag_acronyms_path": _resolve_optional_path(
            paths.get("html_tag_acronyms") or str(DEFAULT_HTML_TAG_ACRONYMS_PATH),
            base_path=runtime_base_path,
        ),
        "cover_style_path": _resolve_optional_path(
            paths.get("cover_styles")
            or str(
                Path(__file__).resolve().parents[2] / "config" / "cover-styles.yaml"
            ),
            base_path=runtime_base_path,
        ),
        "ingest_lock_path": _resolve_optional_path(
            lock_path_raw,
            base_path=runtime_base_path,
        ),
    }


__all__ = [name for name in globals() if not name.startswith("__")]
