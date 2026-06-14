from __future__ import annotations

from pathlib import Path


def ui_run_state_dir(registry_path: str) -> Path:
    registry = Path(registry_path).expanduser().resolve()
    return registry.parent / "ui_runs"


def ui_run_dir(registry_path: str, run_id: str) -> Path:
    return ui_run_state_dir(registry_path) / str(run_id).strip()
