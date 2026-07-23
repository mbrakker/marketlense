from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from src.contracts.config import ConfigLoadRequest
from src.contracts.run_context import RunContext
from src.services._config_service.common import (
    _ConfigResolver,
    _resolve_optional_path,
    _resolve_runtime_base_path,
)
from src.services._config_service.paths import _resolve_paths_settings
from src.services.config_service import load_settings


def test_workspace_relative_paths_do_not_depend_on_nested_config_location() -> None:
    workspace = Path(__file__).resolve().parents[1]
    nested_config = workspace / "operator" / "profiles" / "app.yaml"
    resolver = _ConfigResolver()

    resolved = _resolve_paths_settings(
        {
            "output_dir": "out/isolated",
            "cache_dir": "cache/isolated",
            "state_db": "state/isolated/index.sqlite",
            "reports_db": "state/isolated/reports.sqlite",
        },
        resolver,
        runtime_base_path=_resolve_runtime_base_path(nested_config),
    )

    assert resolver.missing == []
    assert _resolve_runtime_base_path(nested_config) == workspace
    assert resolved["output_dir"] == str(workspace / "out" / "isolated")
    assert resolved["state_db"] == str(
        workspace / "state" / "isolated" / "index.sqlite"
    )
    assert resolved["reports_db"] == str(
        workspace / "state" / "isolated" / "reports.sqlite"
    )


def test_absolute_paths_are_preserved_by_the_canonical_resolver(tmp_path: Path) -> None:
    explicit_path = tmp_path / "absolute" / "ledger.sqlite"

    assert _resolve_optional_path(
        explicit_path,
        base_path=Path(__file__).resolve().parents[1],
    ) == str(explicit_path.resolve())


def test_committed_configuration_has_no_pdf_count_budget() -> None:
    workspace = Path(__file__).resolve().parents[1]
    request = ConfigLoadRequest(
        schema_version="1.0", path=str(workspace / "src" / "config" / "app.yaml")
    )
    ctx = RunContext(
        schema_version="1.0", run_id="config-budget", task_id="test", span_id="test"
    )

    settings = load_settings(request, ctx)

    assert settings.run_budget_max_pdfs is None
    assert settings.run_budget_max_spend_usd == 6.0


def test_committed_configuration_loads_without_live_credentials(tmp_path: Path) -> None:
    workspace = Path(__file__).resolve().parents[1]
    script = (
        """
from src.contracts.config import ConfigLoadRequest
from src.contracts.run_context import RunContext
from src.services.config_service import load_settings

request = ConfigLoadRequest(schema_version='1.0', path=r'"""
        + str(workspace / "src" / "config" / "app.yaml")
        + """')
ctx = RunContext(schema_version='1.0', run_id='credential-free-config', task_id='test', span_id='test')
settings = load_settings(request, ctx)
assert settings.gdrive_folder_id == ''
assert settings.openai_api_key == ''
"""
    )
    environment = dict(os.environ)
    for key in (
        "GDRIVE_FOLDER_ID",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "MARKET_LENSE_CONFIG_PATH",
        "MARKET_LENSE_CONFIG_PROFILE",
    ):
        environment.pop(key, None)
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(workspace), environment.get("PYTHONPATH", "")) if value
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
