from __future__ import annotations

from src.services._config_service.common import *

def _resolve_paths_settings(
    paths: dict[str, Any],
    resolver: _ConfigResolver,
) -> dict[str, str]:
    output_dir = resolver.need(paths, "output_dir", "paths.output_dir", "OUTPUT_DIR")
    cache_dir = resolver.need(paths, "cache_dir", "paths.cache_dir", "CACHE_DIR")
    state_db = resolver.need(paths, "state_db", "paths.state_db", "STATE_DB")
    reports_db = resolver.need(paths, "reports_db", "paths.reports_db", "REPORTS_DB")
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
        "publisher_profiles_path": paths.get("publisher_profiles")
        or str(
            Path(__file__).resolve().parents[3]
            / "Wordpress"
            / "config"
            / "publisher-profiles.json"
        ),
        "category_mapping_path": paths.get("category_mappings")
        or str(
            Path(__file__).resolve().parents[2] / "config" / "category-mappings.yaml"
        ),
        "html_tag_acronyms_path": paths.get("html_tag_acronyms")
        or str(DEFAULT_HTML_TAG_ACRONYMS_PATH),
        "cover_style_path": paths.get("cover_styles")
        or str(Path(__file__).resolve().parents[2] / "config" / "cover-styles.yaml"),
        "ingest_lock_path": str(lock_path_raw),
    }

__all__ = [name for name in globals() if not name.startswith("__")]
