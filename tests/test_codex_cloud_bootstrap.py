from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_SCRIPT = REPOSITORY_ROOT / "scripts" / "bootstrap_codex_cloud.sh"


def test_bootstrap_rejects_non_python_312(tmp_path: Path) -> None:
    fake_python = tmp_path / "python"
    fake_python.write_text("#!/bin/sh\necho 3.11\n", encoding="utf-8")
    fake_python.chmod(0o755)
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHON_BIN": str(fake_python),
            "CODEX_CLOUD_VENV_DIR": str(tmp_path / ".venv"),
        }
    )

    result = subprocess.run(
        [str(BOOTSTRAP_SCRIPT)],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Python 3.12 is required" in result.stderr
    assert not (tmp_path / ".venv").exists()
