# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath
__file__ = str(_SplitPath(__file__).resolve().parent.parent / "test_config_service.py")

import os

import tempfile

import unittest

from pathlib import Path

from unittest.mock import patch

import yaml

from src.contracts.config import ConfigLoadRequest

from src.contracts.publisher_inventory import PublisherInventorySettings

from src.contracts.run_context import RunContext

from src.services.config_service import (
    load_browser_download_settings,
    load_publisher_inventory_settings,
    load_publish_settings,
    load_settings,
)

from src.utils.errors import AppError

if __name__ == "__main__":
    unittest.main()

class _TestConfigServiceBase(unittest.TestCase):
    def _write_config(
        self,
        tmp_dir: str,
        include_analysis: bool = False,
        include_publish: bool = False,
    ) -> str:
        config_path = Path(tmp_dir) / "app.yaml"
        acronyms_path = Path(tmp_dir) / "html-tag-acronyms.yaml"
        identity_path = Path(tmp_dir) / "browser_download_identity.yaml"
        publisher_profiles_path = Path(tmp_dir) / "publisher-profiles.json"
        acronyms_path.write_text(
            yaml.safe_dump(
                {
                    "schema_version": "1.0",
                    "html_tag_acronyms": ["AI", "ROI", "CPC"],
                }
            ),
            encoding="utf-8",
        )
        identity_path.write_text(
            yaml.safe_dump(
                {
                    "schema_version": "1.0",
                    "fields": [
                        {
                            "schema_version": "1.0",
                            "key": "work_email",
                            "label": "Work email",
                            "value": "ops@example.com",
                            "aliases": ["email", "email address"],
                        },
                        {
                            "schema_version": "1.0",
                            "key": "company",
                            "label": "Company",
                            "value": "Market Lense",
                            "aliases": ["company", "business"],
                        },
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        publisher_profiles_path.write_text(
            '{"schema_version":"1.0","source_page_url":"https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d","publisher_count":0,"publishers":[]}',
            encoding="utf-8",
        )
        config = {
            "schema_version": "1.0",
            "paths": {
                "output_dir": str(Path(tmp_dir, "out")),
                "cache_dir": str(Path(tmp_dir, "cache")),
                "state_db": str(Path(tmp_dir, "state", "index.sqlite")),
                "reports_db": str(Path(tmp_dir, "state", "reports.sqlite")),
                "publisher_profiles": str(publisher_profiles_path),
                "html_tag_acronyms": str(acronyms_path),
            },
            "ingest": {
                "google_sa_path": str(Path(tmp_dir, "sa.json")),
                "gdrive_folder_id": "folder",
                "openai_model": "gpt-5",
                "temperature": 0.5,
            },
            "browser_download": {
                "identity_config_path": str(identity_path),
            },
        }
        if include_analysis:
            config["analysis"] = {
                "vector_store_keep": True,
                "cost_ledger_path": "./out/cost-ledger.jsonl",
            }
        if include_publish:
            config["publish"] = {
                "wp": {
                    "username": "admin",
                }
            }
        config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
        return str(config_path)



__all__ = [
    name
    for name in globals()
    if name
    not in {
        '__name__', '__annotations__', '__doc__', '__spec__',
        '__file__', '__package__', '__loader__', '__cached__',
        '__builtins__', '_SplitPath',
    }
]
