from __future__ import annotations

from pathlib import Path

import yaml

import src.contracts.config as config_contracts
import src.contracts.ingest as ingest_contracts


def test_cover_cache_flag_is_removed_from_contracts_and_config() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    app_yaml = yaml.safe_load(
        (repo_root / "src" / "config" / "app.yaml").read_text(encoding="utf-8")
    )

    assert not hasattr(config_contracts.AppSettings, "cover_cache_enabled")
    assert not hasattr(ingest_contracts.IngestSettings, "cover_cache_enabled")
    assert "cover_cache_enabled" not in (app_yaml.get("ingest") or {})


def test_cover_cache_flag_is_removed_from_loader_ui_and_docs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    searched_files = [
        repo_root / "src" / "services" / "_config_service" / "ingest.py",
        repo_root / "src" / "services" / "_config_service" / "app_settings.py",
        repo_root / "src" / "ui" / "_streamlit_pages" / "structured_config.py",
        repo_root / "docs" / "ops" / "configuration.md",
        repo_root / "docs" / "generated" / "configuration-reference.md",
        repo_root / "CONSOLIDATED_TODO.md",
    ]

    for path in searched_files:
        text = path.read_text(encoding="utf-8")
        assert "cover_cache_enabled" not in text
        assert "Cover Cache Enabled" not in text
