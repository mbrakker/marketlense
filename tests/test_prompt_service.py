import hashlib
import logging
import os
from pathlib import Path

import pytest

from src.contracts.prompts import PromptLoadRequest
from src.contracts.prompts import PromptNamespaceListRequest
from src.contracts.run_context import RunContext
from src.services.prompt_service import list_prompt_namespaces, load_prompt_set
from src.services import prompt_service
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _write_prompt_namespace(
    prompts_root: Path, namespace: str, system: str, user: str
) -> None:
    namespace_dir = prompts_root / namespace
    namespace_dir.mkdir(parents=True, exist_ok=True)
    (namespace_dir / "system.yaml").write_text(f"text: {system}", encoding="utf-8")
    (namespace_dir / "user.yaml").write_text(f"text: {user}", encoding="utf-8")
    os.utime(namespace_dir, None)
    os.utime(namespace_dir.parent, None)


def test_load_prompt_set_hashes(caplog):
    caplog.set_level(logging.INFO, logger="market_lense.prompt_service")
    prompt_set = load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace="report_vs/doc_map"), _ctx()
    )
    assert prompt_set.system.text
    assert prompt_set.user.text
    sys_hash = hashlib.sha256(prompt_set.system.text.encode("utf-8")).hexdigest()
    usr_hash = hashlib.sha256(prompt_set.user.text.encode("utf-8")).hexdigest()
    assert prompt_set.system.sha256 == sys_hash
    assert prompt_set.user.sha256 == usr_hash
    # ensure logs mention paths and hashes
    loaded_logs = [
        rec.message for rec in caplog.records if "prompt_load_complete" in rec.message
    ]
    assert loaded_logs, "expected load logs"


def test_list_prompt_namespaces_returns_hashes() -> None:
    response = list_prompt_namespaces(
        PromptNamespaceListRequest(
            schema_version="1.0", reload_if_changed=True, force_reload=False
        ),
        _ctx(),
    )
    assert response.namespaces
    first = response.namespaces[0]
    assert first.namespace
    assert first.system_sha256
    assert first.user_sha256


def test_list_prompt_namespaces_cache_invalidates_for_add_remove_and_rename(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    prompts_root = tmp_path / "prompts"
    _write_prompt_namespace(prompts_root, "alpha", "system-a", "user-a")
    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)

    first = list_prompt_namespaces(
        PromptNamespaceListRequest(schema_version="1.0", reload_if_changed=True),
        _ctx(),
    )
    assert [item.namespace for item in first.namespaces] == ["alpha"]

    _write_prompt_namespace(prompts_root, "beta", "system-b", "user-b")
    added = list_prompt_namespaces(
        PromptNamespaceListRequest(schema_version="1.0", reload_if_changed=True),
        _ctx(),
    )
    assert [item.namespace for item in added.namespaces] == ["alpha", "beta"]

    (prompts_root / "alpha").rename(prompts_root / "gamma")
    os.utime(prompts_root, None)
    renamed = list_prompt_namespaces(
        PromptNamespaceListRequest(schema_version="1.0", reload_if_changed=True),
        _ctx(),
    )
    assert [item.namespace for item in renamed.namespaces] == ["beta", "gamma"]

    for path in (prompts_root / "beta").iterdir():
        path.unlink()
    (prompts_root / "beta").rmdir()
    os.utime(prompts_root, None)
    removed = list_prompt_namespaces(
        PromptNamespaceListRequest(schema_version="1.0", reload_if_changed=True),
        _ctx(),
    )
    assert [item.namespace for item in removed.namespaces] == ["gamma"]


def test_list_prompt_namespaces_refreshes_stale_prompt_hash(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    prompts_root = tmp_path / "prompts"
    _write_prompt_namespace(prompts_root, "alpha", "system-a", "user-a")
    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)

    first = list_prompt_namespaces(
        PromptNamespaceListRequest(schema_version="1.0", reload_if_changed=True),
        _ctx(),
    )
    user_path = prompts_root / "alpha" / "user.yaml"
    user_path.write_text("text: user-a-updated", encoding="utf-8")
    os.utime(user_path, None)

    updated = list_prompt_namespaces(
        PromptNamespaceListRequest(schema_version="1.0", reload_if_changed=True),
        _ctx(),
    )

    assert updated.namespaces[0].namespace == "alpha"
    assert updated.namespaces[0].user_sha256 != first.namespaces[0].user_sha256


def test_load_prompt_set_rejects_namespace_traversal(
    tmp_path: Path,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    prompts_root = tmp_path / "prompts"
    safe_prompt = prompts_root / "safe"
    safe_prompt.mkdir(parents=True, exist_ok=True)
    (safe_prompt / "system.yaml").write_text("text: system", encoding="utf-8")
    (safe_prompt / "user.yaml").write_text("text: user", encoding="utf-8")

    outside_prompt = tmp_path / "outside"
    outside_prompt.mkdir(parents=True, exist_ok=True)
    (outside_prompt / "system.yaml").write_text(
        "text: outside-system", encoding="utf-8"
    )
    (outside_prompt / "user.yaml").write_text("text: outside-user", encoding="utf-8")

    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)

    with pytest.raises(AppError) as err:
        load_prompt_set(
            PromptLoadRequest(
                schema_version="1.0",
                namespace="../outside",
                reload_if_changed=True,
                force_reload=True,
            ),
            _ctx(),
        )

    assert_app_error(err.value, code="prompt_namespace_invalid", retryable=False)


def test_load_prompt_set_rejects_non_mapping_yaml_root(
    tmp_path: Path,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    prompts_root = tmp_path / "prompts"
    broken_prompt = prompts_root / "broken"
    broken_prompt.mkdir(parents=True, exist_ok=True)
    (broken_prompt / "system.yaml").write_text("- not-a-mapping", encoding="utf-8")
    (broken_prompt / "user.yaml").write_text("text: user", encoding="utf-8")

    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)

    with pytest.raises(AppError) as err:
        load_prompt_set(
            PromptLoadRequest(
                schema_version="1.0",
                namespace="broken",
                reload_if_changed=True,
                force_reload=True,
            ),
            _ctx(),
        )

    assert_app_error(err.value, code="prompt_yaml_invalid", retryable=False)
