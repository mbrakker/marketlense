from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from src.contracts.ui_run_control import UiRunRecord, UiRunRecordWriteRequest
from src.contracts.ui_run_replay import (
    UiRunArtifactFingerprintResponse,
    UiRunExecutionResponse,
    UiRunReplayCaptureRequest,
    UiRunReplayRequest,
    UiRunWorkspaceFingerprintResponse,
)
from src.orchestrators import ui_run_replay_orchestrator as orchestrator
from src.services.run_registry_service import write_ui_run_record
from src.services.ui_run_replay_service import write_ui_run_replay_manifest
from src.utils.cache_utils import sha256_json
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="test_ui_run_replay_orchestrator")


def _registry_path(tmp_path: Path) -> str:
    return str((tmp_path / "state" / "ui_runs.sqlite").resolve())


def _record() -> UiRunRecord:
    return UiRunRecord(
        schema_version="1.0",
        run_id="run-1",
        run_type="report_download",
        display_name="Report download",
        status="succeeded",
        request_payload={"url": "https://example.com/report.pdf"},
        command=["python", "-m", "src.cli", "ui-run-worker"],
        created_at_utc="2026-04-23T10:00:00+00:00",
        updated_at_utc="2026-04-23T10:00:01+00:00",
        started_at_utc="2026-04-23T10:00:01+00:00",
        finished_at_utc="2026-04-23T10:00:05+00:00",
        output_path="out.log",
        request_path="request.json",
        artifact_paths=["artifact.pdf"],
        result_summary={"outcome": "downloaded"},
    )


def _seed_manifest(tmp_path: Path):
    source_root = tmp_path / "workspace" / "src"
    prompt_root = source_root / "prompts" / "report_download"
    artifact_path = tmp_path / "workspace" / "artifacts" / "artifact.pdf"
    config_snapshot = {
        "run_type": "report_download",
        "settings": {"headed": False},
    }
    source_root.mkdir(parents=True, exist_ok=True)
    prompt_root.mkdir(parents=True, exist_ok=True)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    (source_root / "sample.py").write_text("print('ok')\n", encoding="utf-8")
    (prompt_root / "system.yaml").write_text("system: test\n", encoding="utf-8")
    artifact_path.write_bytes(b"artifact")
    return write_ui_run_replay_manifest(
        UiRunReplayCaptureRequest(
            schema_version="1.0",
            registry_path=_registry_path(tmp_path),
            run_id="run-1",
            run_type="report_download",
            status="succeeded",
            recorded_at_utc="2026-04-23T10:00:05+00:00",
            request_payload={"url": "https://example.com/report.pdf"},
            config_snapshot=config_snapshot,
            config_fingerprint=sha256_json(config_snapshot),
            source_tree_root=str(source_root),
            prompt_tree_root=str(source_root / "prompts"),
            artifact_paths=[str(artifact_path)],
            result_summary={"outcome": "downloaded"},
        ),
        _ctx(),
    )


def test_replay_ui_run_writes_match_report(
    tmp_path: Path,
    monkeypatch,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO)
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=_registry_path(tmp_path),
            record=_record(),
        ),
        _ctx(),
    )
    manifest = _seed_manifest(tmp_path).manifest
    monkeypatch.setattr(
        orchestrator,
        "resolve_ui_run_config_snapshot",
        lambda worker_request, ctx: {
            "run_type": "report_download",
            "settings": {"headed": False},
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "fingerprint_ui_run_workspace",
        lambda request, ctx: UiRunWorkspaceFingerprintResponse(
            schema_version="1.0",
            source_tree_root=request.source_tree_root,
            source_tree_fingerprint=manifest.source_tree_fingerprint,
            prompt_tree_root=request.prompt_tree_root,
            prompt_tree_fingerprint=manifest.prompt_tree_fingerprint,
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "execute_ui_run",
        lambda worker_request, ctx: UiRunExecutionResponse(
            schema_version="1.0",
            run_id=worker_request.run_id,
            run_type=worker_request.run_type,
            status="succeeded",
            result_summary={"outcome": "downloaded"},
            artifact_paths=["artifact.pdf"],
            config_snapshot={
                "run_type": "report_download",
                "settings": {"headed": False},
            },
            config_fingerprint=sha256_json(
                {"run_type": "report_download", "settings": {"headed": False}}
            ),
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "fingerprint_ui_run_artifacts",
        lambda request, ctx: UiRunArtifactFingerprintResponse(
            schema_version="1.0",
            artifact_fingerprints=manifest.artifact_fingerprints,
        ),
    )

    result = orchestrator.replay_ui_run(
        UiRunReplayRequest(
            schema_version="1.0",
            registry_path=_registry_path(tmp_path),
            run_id="run-1",
        ),
        _ctx(),
    )

    assert result.report.matched is True
    assert result.report.replay_status == "succeeded"
    assert Path(result.report_path).exists()
    assert_logs_have_required_fields(
        [
            record
            for record in caplog.records
            if record.name == "market_lense.ui_run_replay_orchestrator"
        ]
    )


def test_replay_ui_run_blocks_on_environment_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=_registry_path(tmp_path),
            record=_record(),
        ),
        _ctx(),
    )
    _seed_manifest(tmp_path)
    monkeypatch.setattr(
        orchestrator,
        "resolve_ui_run_config_snapshot",
        lambda worker_request, ctx: {
            "run_type": "report_download",
            "settings": {"headed": True},
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "fingerprint_ui_run_workspace",
        lambda request, ctx: UiRunWorkspaceFingerprintResponse(
            schema_version="1.0",
            source_tree_root=request.source_tree_root,
            source_tree_fingerprint="source-sha",
            prompt_tree_root=request.prompt_tree_root,
            prompt_tree_fingerprint="different-prompt",
        ),
    )
    called = {"count": 0}

    def _unexpected_execute(worker_request, ctx):
        called["count"] += 1
        return SimpleNamespace()

    monkeypatch.setattr(orchestrator, "execute_ui_run", _unexpected_execute)

    result = orchestrator.replay_ui_run(
        UiRunReplayRequest(
            schema_version="1.0",
            registry_path=_registry_path(tmp_path),
            run_id="run-1",
        ),
        _ctx(),
    )

    assert result.report.matched is False
    assert result.report.replay_status == "blocked_drift"
    assert called["count"] == 0
