from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.contracts.ui_run_replay import (
    UiRunArtifactFingerprintRequest,
    UiRunReplayCaptureRequest,
    UiRunReplayReadRequest,
    UiRunWorkspaceFingerprintRequest,
)
from src.services import ui_run_replay_service
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="test_ui_run_replay_service")


def _registry_path(tmp_path: Path) -> str:
    return str((tmp_path / "state" / "ui_runs.sqlite").resolve())


def test_ui_run_replay_manifest_roundtrip_and_fingerprints(
    tmp_path: Path,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    caplog.set_level(logging.INFO)
    source_root = tmp_path / "workspace" / "src"
    prompt_root = source_root / "prompts" / "report_download"
    artifact_path = tmp_path / "workspace" / "out" / "report.pdf"
    source_root.mkdir(parents=True, exist_ok=True)
    prompt_root.mkdir(parents=True, exist_ok=True)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    (source_root / "sample.py").write_text("print('ok')\n", encoding="utf-8")
    (prompt_root / "system.yaml").write_text("system: test\n", encoding="utf-8")
    artifact_path.write_bytes(b"%PDF-1.4 replay\n")

    capture = ui_run_replay_service.write_ui_run_replay_manifest(
        UiRunReplayCaptureRequest(
            schema_version="1.0",
            registry_path=_registry_path(tmp_path),
            run_id="run-1",
            run_type="report_download",
            status="succeeded",
            recorded_at_utc="2026-04-23T10:00:00+00:00",
            request_payload={"url": "https://example.com/report.pdf"},
            config_snapshot={"run_type": "report_download", "settings": {"headed": False}},
            config_fingerprint="cfg-sha",
            source_tree_root=str(source_root),
            prompt_tree_root=str(source_root / "prompts"),
            artifact_paths=[str(artifact_path)],
            result_summary={"outcome": "downloaded"},
        ),
        _ctx(),
    )
    read_back = ui_run_replay_service.read_ui_run_replay_manifest(
        UiRunReplayReadRequest(
            schema_version="1.0",
            registry_path=_registry_path(tmp_path),
            run_id="run-1",
        ),
        _ctx(),
    )
    workspace = ui_run_replay_service.fingerprint_ui_run_workspace(
        UiRunWorkspaceFingerprintRequest(
            schema_version="1.0",
            run_id="run-1",
            source_tree_root=str(source_root),
            prompt_tree_root=str(source_root / "prompts"),
        ),
        _ctx(),
    )
    artifacts = ui_run_replay_service.fingerprint_ui_run_artifacts(
        UiRunArtifactFingerprintRequest(
            schema_version="1.0",
            run_id="run-1",
            artifact_paths=[str(artifact_path)],
        ),
        _ctx(),
    )

    assert capture.manifest_path == read_back.manifest_path
    assert read_back.manifest == capture.manifest
    assert_no_defaulted_required_fields(capture.manifest)
    assert capture.manifest.source_tree_fingerprint == workspace.source_tree_fingerprint
    assert capture.manifest.prompt_tree_fingerprint == workspace.prompt_tree_fingerprint
    assert artifacts.artifact_fingerprints[0] == capture.manifest.artifact_fingerprints[0]
    assert artifacts.artifact_fingerprints[0].exists is True
    assert artifacts.artifact_fingerprints[0].sha256
    assert_logs_have_required_fields(
        [
            record
            for record in caplog.records
            if record.name == "market_lense.ui_run_replay_service"
        ]
    )


def test_read_ui_run_replay_manifest_missing_returns_typed_error(
    tmp_path: Path, assert_app_error
) -> None:
    with pytest.raises(Exception) as exc_info:
        ui_run_replay_service.read_ui_run_replay_manifest(
            UiRunReplayReadRequest(
                schema_version="1.0",
                registry_path=_registry_path(tmp_path),
                run_id="missing-run",
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="ui_run_replay_manifest_missing",
        retryable=False,
    )
