"""Security regression tests for vendored Browser-Use credential handling."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_KEY_MODULE = (
    REPOSITORY_ROOT
    / "tools"
    / "browser-use"
    / "browser_use"
    / "skill_cli"
    / "api_key.py"
)


def _run_api_key_module(
    script: str,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script, str(API_KEY_MODULE)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_api_key_is_available_only_from_the_environment(tmp_path: Path) -> None:
    environment = {
        **os.environ,
        "BROWSER_USE_API_KEY": "test-browser-use-api-key",
        "APPDATA": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path),
    }
    result = _run_api_key_module(
        """
import importlib.util
import sys
spec = importlib.util.spec_from_file_location('vendored_api_key', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.require_api_key() == 'test-browser-use-api-key'
assert module.check_api_key()['source'] == 'env'
""",
        environment,
    )

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_api_key_persistence_is_refused_without_creating_a_config_file(
    tmp_path: Path,
) -> None:
    environment = {
        **os.environ,
        "APPDATA": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path),
    }
    environment.pop("BROWSER_USE_API_KEY", None)
    result = _run_api_key_module(
        """
import importlib.util
import sys
spec = importlib.util.spec_from_file_location('vendored_api_key', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
try:
    module.save_api_key('test-browser-use-api-key')
except module.APIKeyPersistenceDisabled:
    persistence_was_refused = True
else:
    persistence_was_refused = False
assert persistence_was_refused
""",
        environment,
    )

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []
