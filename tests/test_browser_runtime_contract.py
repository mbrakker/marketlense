from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.services._browser_report_download._browser_runtime.runtime import (
    browser_runtime_identity,
    load_browser_session_class,
    load_browser_use_runtime,
)


def test_browser_worker_uses_the_same_supported_runtime_as_the_parent() -> None:
    runtime = load_browser_use_runtime()
    parent_identity = browser_runtime_identity(runtime)
    session_class = load_browser_session_class()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.services._browser_report_download.browser_worker",
            "--runtime-probe",
        ],
        check=False,
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30.0,
    )

    assert session_class.__name__ == "BrowserSession"
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == parent_identity.__dict__
    assert Path(parent_identity.interpreter_path) == Path(sys.executable).resolve()
    assert parent_identity.browser_use_module_path
    assert parent_identity.runtime_source in {"installed", "vendored"}
