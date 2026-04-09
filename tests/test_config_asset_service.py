from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.contracts.config_assets import (
    ConfigAssetReadRequest,
    ConfigAssetWriteRequest,
)
from src.services.config_asset_service import read_config_asset, write_config_asset
from src.utils.errors import AppError
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="test_config_asset_service")


def test_config_asset_service_roundtrip_yaml_with_backup(
    tmp_path: Path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    target = tmp_path / "category-mappings.yaml"
    target.write_text("categories:\n  retail: Retail\n", encoding="utf-8")
    caplog.set_level(logging.INFO)

    write_response = write_config_asset(
        ConfigAssetWriteRequest(
            schema_version="1.0",
            path=str(target),
            format="yaml",
            expected_root_type="mapping",
            content="categories:\n  retail: Retail\n  finance: Finance\n",
            make_backup=True,
        ),
        _ctx(),
    )
    read_response = read_config_asset(
        ConfigAssetReadRequest(
            schema_version="1.0",
            path=str(target),
            format="yaml",
            expected_root_type="mapping",
        ),
        _ctx(),
    )

    assert write_response.path == str(target.resolve())
    assert write_response.backup_path
    assert Path(str(write_response.backup_path)).exists()
    assert read_response.payload == {
        "categories": {"retail": "Retail", "finance": "Finance"}
    }
    assert read_response.sha256 == write_response.sha256
    assert read_response.content.endswith("\n")
    assert_logs_have_required_fields(caplog.records)


def test_config_asset_service_invalid_json_returns_typed_error(
    tmp_path: Path,
    assert_app_error,
) -> None:
    target = tmp_path / "publisher-profiles.json"

    with pytest.raises(AppError) as exc_info:
        write_config_asset(
            ConfigAssetWriteRequest(
                schema_version="1.0",
                path=str(target),
                format="json",
                expected_root_type="any",
                content='{"broken": true',
                make_backup=False,
            ),
            _ctx(),
        )

    assert_app_error(exc_info.value, code="config_asset_json_invalid", retryable=False)


def test_config_asset_service_rejects_root_type_mismatch(
    tmp_path: Path,
    assert_app_error,
) -> None:
    target = tmp_path / "browser_download_identity.yaml"

    with pytest.raises(AppError) as exc_info:
        write_config_asset(
            ConfigAssetWriteRequest(
                schema_version="1.0",
                path=str(target),
                format="yaml",
                expected_root_type="mapping",
                content="- just\n- a\n- list\n",
                make_backup=False,
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="config_asset_root_type_mismatch",
        retryable=False,
    )
