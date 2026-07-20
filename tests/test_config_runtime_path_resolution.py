from __future__ import annotations

from pathlib import Path

from src.contracts.config import ConfigLoadRequest
from src.contracts.run_context import RunContext
from src.services._config_service.common import (
    _ConfigResolver,
    _resolve_optional_path,
    _resolve_runtime_base_path,
)
from src.services._config_service.paths import _resolve_paths_settings
from src.services.config_service import load_browser_download_settings, load_settings


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
    browser_settings = load_browser_download_settings(request, ctx)

    assert settings.run_budget_max_pdfs is None
    assert settings.run_budget_max_spend_usd == 6.0
    assert browser_settings.run_budget_max_pdfs is None
