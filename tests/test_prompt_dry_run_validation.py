from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from src.contracts.prompts import (
    PromptDryRunRequest,
    PromptLoadRequest,
    PromptNamespaceListRequest,
)
from src.contracts.run_context import RunContext
from src.services import prompt_service
from src.services.prompt_service import list_prompt_namespaces, validate_prompt_dry_run
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _events(caplog) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != "market_lense.prompt_service":
            continue
        try:
            payload = json.loads(record.message)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _write_prompt_namespace(
    prompts_root: Path, namespace: str, system: str, user: str
) -> None:
    namespace_dir = prompts_root / namespace
    namespace_dir.mkdir(parents=True, exist_ok=True)
    (namespace_dir / "system.yaml").write_text(f"text: {system}", encoding="utf-8")
    (namespace_dir / "user.yaml").write_text(f"text: {user}", encoding="utf-8")


def test_validate_prompt_dry_run_repository_covers_all_discovered_namespaces(
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.prompt_service")
    response = validate_prompt_dry_run(
        PromptDryRunRequest(schema_version="1.0", reload_if_changed=True),
        _ctx(),
    )
    namespace_response = list_prompt_namespaces(
        PromptNamespaceListRequest(schema_version="1.0", reload_if_changed=True),
        _ctx(),
    )

    assert {item.namespace for item in response.results} == {
        item.namespace for item in namespace_response.namespaces
    }
    assert {"report", "validation", "ranking", "browser_download", "publishing"} <= {
        item.family for item in response.results
    }
    events = _events(caplog)
    namespace_events = [
        item
        for item in events
        if item.get("event") == "prompt_dry_run_namespace_validated"
    ]
    assert len(namespace_events) == len(response.results)
    assert_logs_have_required_fields(events)


def test_validate_prompt_dry_run_rejects_missing_fixture(
    tmp_path: Path,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    prompts_root = tmp_path / "prompts"
    _write_prompt_namespace(prompts_root, "alpha", "system-a", "user-a")
    fixture_path = prompts_root / "_dry_run_fixtures.yaml"
    fixture_path.write_text(
        'schema_version: "1.0"\nfixtures: []\n',
        encoding="utf-8",
    )

    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)
    external_boundary_mocks_only.setattr(
        prompt_service,
        "PROMPT_DRY_RUN_FIXTURE_PATH",
        fixture_path,
    )

    with pytest.raises(AppError) as err:
        validate_prompt_dry_run(
            PromptDryRunRequest(schema_version="1.0", reload_if_changed=True),
            _ctx(),
        )

    assert_app_error(
        err.value,
        code="prompt_dry_run_fixture_registry_invalid",
        retryable=False,
    )


def test_validate_prompt_dry_run_surfaces_missing_variable(
    tmp_path: Path,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    prompts_root = tmp_path / "prompts"
    _write_prompt_namespace(
        prompts_root,
        "alpha",
        "system-a",
        "hello {{ required_name }}",
    )
    fixture_path = prompts_root / "_dry_run_fixtures.yaml"
    fixture_path.write_text(
        "\n".join(
            [
                'schema_version: "1.0"',
                "fixtures:",
                '  - namespace: "alpha"',
                '    family: "report"',
                "    system_variables: {}",
                "    user_variables: {}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)
    external_boundary_mocks_only.setattr(
        prompt_service,
        "PROMPT_DRY_RUN_FIXTURE_PATH",
        fixture_path,
    )

    with pytest.raises(AppError) as err:
        validate_prompt_dry_run(
            PromptDryRunRequest(schema_version="1.0", reload_if_changed=True),
            _ctx(),
        )

    assert_app_error(
        err.value,
        code="prompt_render_missing_variable",
        retryable=False,
    )
