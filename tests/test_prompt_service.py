import hashlib
import logging
import os
import shutil
from pathlib import Path

import pytest

from src.contracts.prompts import (
    PromptLoadRequest,
    PromptNamespaceListRequest,
    PromptRenderRequest,
    PromptTemplate,
)
from src.contracts.run_context import RunContext
from src.services import prompt_service
from src.services.prompt_service import (
    build_llm_execution_identity,
    list_prompt_namespaces,
    load_prompt_set,
    render_prompt,
)
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


def _copy_prompt_and_schema_roots(tmp_path: Path) -> tuple[Path, Path]:
    prompts_root = tmp_path / "prompts"
    schemas_root = tmp_path / "schemas"
    shutil.copytree(prompt_service.PROMPTS_ROOT, prompts_root)
    shutil.copytree(prompt_service.SCHEMAS_ROOT, schemas_root)
    return prompts_root, schemas_root


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


def test_prompt_render_logs_do_not_expose_rendered_content(caplog) -> None:
    marker = "confidential-rendered-prompt-marker"
    template = PromptTemplate(
        schema_version="1.0",
        path="prompts/test/system.yaml",
        text="System instruction: {{ secret }}",
        sha256="test-template-sha",
    )
    caplog.set_level(logging.INFO, logger="market_lense.prompt_service")

    response = render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=template,
            variables={"secret": marker},
        ),
        _ctx(),
    )

    assert marker in response.text
    assert marker not in caplog.text


def test_artifact_prompts_include_shared_editorial_constitution() -> None:
    prompt_set = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/expert_comment",
            force_reload=True,
        ),
        _ctx(),
    )

    assert "Market Lense editorial constitution" in prompt_set.user.text
    assert any(
        path.replace("\\", "/").endswith(
            "report_vs/artifacts/_partials/editorial_constitution.yaml"
        )
        for path in prompt_set.user.include_paths
    )


def test_summary_and_expert_prompts_prevent_first_run_readiness_failures() -> None:
    doc_map_prompt = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/doc_map",
            force_reload=True,
        ),
        _ctx(),
    )
    summary_prompt = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/summary",
            force_reload=True,
        ),
        _ctx(),
    )
    expert_prompt = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/expert_comment",
            force_reload=True,
        ),
        _ctx(),
    )

    assert (
        'do not emit labels such as "Answer:" or "Implication:"'
        in summary_prompt.user.text
    )
    assert "Do not assert causal operational outcomes" in expert_prompt.user.text
    assert "explicitly named publisher or organization" in doc_map_prompt.user.text


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


def test_load_prompt_set_reuses_validated_cache(
    tmp_path: Path,
    external_boundary_mocks_only,
    caplog,
) -> None:
    prompts_root = tmp_path / "prompts"
    _write_prompt_namespace(prompts_root, "alpha", "system-a", "user-a")
    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)
    caplog.set_level(logging.INFO, logger="market_lense.prompt_service")

    first = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="alpha",
            reload_if_changed=True,
            force_reload=True,
        ),
        _ctx(),
    )
    second = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="alpha",
            reload_if_changed=True,
            force_reload=False,
        ),
        _ctx(),
    )

    assert second.system.sha256 == first.system.sha256
    assert second.user.sha256 == first.user.sha256
    assert any(
        "prompt_load_cache_hit" in record.message
        and '"validated": true' in record.message
        for record in caplog.records
    )


def test_load_prompt_set_uses_cached_content_when_reload_not_requested(
    tmp_path: Path,
    external_boundary_mocks_only,
    caplog,
) -> None:
    prompts_root = tmp_path / "prompts"
    _write_prompt_namespace(prompts_root, "alpha", "system-a", "user-a")
    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)
    caplog.set_level(logging.INFO, logger="market_lense.prompt_service")

    first = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="alpha",
            force_reload=True,
        ),
        _ctx(),
    )
    (prompts_root / "alpha" / "user.yaml").write_text("text: user-b", encoding="utf-8")

    cached = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="alpha",
            reload_if_changed=False,
        ),
        _ctx(),
    )

    assert cached is first
    assert any(
        "prompt_load_cache_hit" in record.message
        and '"validated": false' in record.message
        for record in caplog.records
    )


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


def test_partial_change_invalidates_only_dependent_namespace_without_restart(
    tmp_path: Path,
    external_boundary_mocks_only,
    caplog,
) -> None:
    prompts_root, schemas_root = _copy_prompt_and_schema_roots(tmp_path)
    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)
    external_boundary_mocks_only.setattr(prompt_service, "SCHEMAS_ROOT", schemas_root)
    caplog.set_level(logging.INFO, logger="market_lense.prompt_service")

    dependent_before = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/expert_comment",
            force_reload=True,
        ),
        _ctx(),
    )
    unrelated_before = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/doc_map",
            force_reload=True,
        ),
        _ctx(),
    )
    partial_path = (
        prompts_root / "report_vs/artifacts/_partials/editorial_constitution.yaml"
    )
    original_stat = partial_path.stat()
    original = partial_path.read_text(encoding="utf-8")
    partial_path.write_text(
        original.replace("constitution", "constitutioN", 1), encoding="utf-8"
    )
    os.utime(partial_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    dependent_after = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/expert_comment",
            reload_if_changed=True,
        ),
        _ctx(),
    )
    unrelated_after = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/doc_map",
            reload_if_changed=True,
        ),
        _ctx(),
    )

    assert dependent_after.prompt_content_hash != dependent_before.prompt_content_hash
    assert unrelated_after is unrelated_before
    assert any(
        "prompt_cache_invalidated" in record.message
        and '"reason": "partial_content_changed"' in record.message
        for record in caplog.records
    )


def test_schema_dependency_change_invalidates_content_identity_without_restart(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    prompts_root, schemas_root = _copy_prompt_and_schema_roots(tmp_path)
    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)
    external_boundary_mocks_only.setattr(prompt_service, "SCHEMAS_ROOT", schemas_root)

    before = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/summary",
            force_reload=True,
        ),
        _ctx(),
    )
    schema_path = schemas_root / "artifacts.schema.json"
    original_stat = schema_path.stat()
    original = schema_path.read_text(encoding="utf-8")
    schema_path.write_text(original.replace('"array"', '"Array"', 1), encoding="utf-8")
    os.utime(schema_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    after = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/summary",
            reload_if_changed=True,
        ),
        _ctx(),
    )

    assert after.prompt_content_hash != before.prompt_content_hash
    assert after.dependency_manifest is not None
    assert (
        after.dependency_manifest.schema_snippets[0].path
        == "schemas/artifacts.schema.json"
    )


def test_prompt_content_identity_is_path_independent_and_execution_identity_is_sensitive(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    first_prompts, first_schemas = _copy_prompt_and_schema_roots(tmp_path / "first")
    second_prompts, second_schemas = _copy_prompt_and_schema_roots(tmp_path / "second")
    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", first_prompts)
    external_boundary_mocks_only.setattr(prompt_service, "SCHEMAS_ROOT", first_schemas)
    first = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/summary",
            force_reload=True,
        ),
        _ctx(),
    )
    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", second_prompts)
    external_boundary_mocks_only.setattr(prompt_service, "SCHEMAS_ROOT", second_schemas)
    second = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/summary",
            force_reload=True,
        ),
        _ctx(),
    )

    stable = build_llm_execution_identity(
        prompt_content_hash=first.prompt_content_hash,
        provider="openai",
        model="gpt-5-mini",
        temperature=0.1,
        seed=7,
        retrieval_mode="chat_json",
        output_contract_schema_version="artifact_json:1.0",
        validator_version="artifacts_schema:3.0",
    )
    changed_policy = build_llm_execution_identity(
        prompt_content_hash=second.prompt_content_hash,
        provider="openai",
        model="gpt-5-mini",
        temperature=0.2,
        seed=7,
        retrieval_mode="chat_json",
        output_contract_schema_version="artifact_json:1.0",
        validator_version="artifacts_schema:3.0",
    )

    assert first.prompt_content_hash == second.prompt_content_hash
    assert stable.execution_identity != changed_policy.execution_identity
