from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from src.contracts.config import ConfigLoadRequest
from src.contracts.prompts import (
    PromptDryRunRequest,
    PromptLoadRequest,
    PromptNamespaceListRequest,
)
from src.contracts.run_context import RunContext
from src.services import prompt_service
from src.services.config_service import load_settings
from src.services.prompt_service import list_prompt_namespaces, validate_prompt_dry_run
from src.utils.errors import AppError
from src.utils.model_resolver import (
    execution_policies_from_config,
    resolve_execution_policy,
)


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


def test_final_insights_regeneration_prompt_requires_decision_implications() -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/regenerate/insights_final",
            force_reload=True,
        ),
        _ctx(),
    )

    assert "so_what" in prompt_set.user.text
    assert "now_what" in prompt_set.user.text


@pytest.mark.parametrize(
    "namespace",
    [
        "report_vs/evidence_packs/findings",
        "report_vs/artifacts/insights_candidates",
        "report_vs/artifacts/insights_final",
        "report_vs/artifacts/summary",
        "report_vs/artifacts/expert_comment",
        "report_vs/artifacts/linkedin_post",
        "report_vs/artifacts/regenerate/insights_candidates",
        "report_vs/artifacts/regenerate/insights_final",
        "report_vs/artifacts/regenerate/summary",
        "report_vs/artifacts/regenerate/expert_comment",
        "report_vs/artifacts/regenerate/linkedin_post",
    ],
)
def test_editorial_prompts_require_distinct_temporal_qualifiers(namespace: str) -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=namespace, force_reload=True),
        _ctx(),
    )

    assert "distinct temporal qualifiers" in (
        f"{prompt_set.system.text}\n{prompt_set.user.text}"
    )


@pytest.mark.parametrize(
    ("namespace", "scope"),
    [
        ("report_vs/artifacts/linkedin_post", "Broad report scope"),
        ("report_vs/artifacts/regenerate/linkedin_post", "Narrow report scope"),
    ],
)
def test_linkedin_prompt_materializes_editorial_plan_and_report_scope(
    namespace: str, scope: str
) -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=namespace, force_reload=True),
        _ctx(),
    )
    variables = {
        "editorial_plan_json": '{"report_thesis":"Retention is the angle."}',
        "doc_map_json": json.dumps({"scope": scope, "publisher": "Source Co."}),
        "summary_json": '{"executive_summary":"Secondary context."}',
        "insights_final_json": '[{"text":"Supporting insight."}]',
        "metric_spine_json": '[]',
        "attempt_index": 1,
        "target_section": "linkedin_post",
        "current_section_text": "Current post.",
        "failure_reasons_json": "[]",
        "fix_checklist_json": "[]",
        "grounding_package_json": "{}",
    }

    rendered = prompt_service.render_prompt(
        prompt_service.PromptRenderRequest(
            schema_version="1.0", template=prompt_set.user, variables=variables
        ),
        _ctx(),
    )

    assert "Retention is the angle." in rendered.text
    assert scope in rendered.text
    assert "Secondary context." not in rendered.text
    assert "180–280 words" in rendered.text
    assert "no more than four quantitative proof points" in rendered.text
    assert (
        "Select the four or fewer quantitative proof points before drafting"
        in rendered.text
    )
    assert "no more than four distinct numerical values" in rendered.text
    assert "Do not use bullets" in rendered.text
    assert "The evidence points to" in rendered.text


@pytest.mark.parametrize(
    "namespace",
    [
        "report_vs/artifacts/linkedin_post",
        "report_vs/artifacts/regenerate/linkedin_post",
    ],
)
def test_linkedin_prompts_require_plain_text_paragraphs_without_markdown_or_bullets(
    namespace: str,
) -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=namespace, force_reload=True),
        _ctx(),
    )

    prompt_text = f"{prompt_set.system.text}\n{prompt_set.user.text}"

    assert "Do not use bullets" in prompt_text
    assert "Markdown formatting" in prompt_text
    assert "plain-text short paragraphs separated by blank lines" in prompt_text
    assert "two newline characters" in prompt_text
    assert "Do not return fewer than 180 words" in prompt_text
    assert "optional bullets" not in prompt_text


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


def test_prompt_dry_run_uses_the_runtime_execution_policy() -> None:
    response = validate_prompt_dry_run(
        PromptDryRunRequest(
            schema_version="1.0", namespaces=["report_vs/artifacts/summary"]
        ),
        _ctx(),
    )
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), _ctx())
    expected = resolve_execution_policy(
        "report_vs/artifacts/summary",
        execution_policies_from_config(
            settings.llm_execution_policies,
            model_overrides=settings.openai_models,
            legacy_routing=settings.llm_routing,
            default_model=settings.openai_model,
            default_temperature=settings.temperature,
            default_seed=settings.openai_seed,
            default_timeout_seconds=settings.openai_timeout_seconds,
        ),
        default_model=settings.openai_model,
        default_temperature=settings.temperature,
        default_seed=settings.openai_seed,
        default_timeout_seconds=settings.openai_timeout_seconds,
    )

    result = response.results[0]
    assert result.model == expected.policy.model
    assert result.temperature == expected.policy.temperature
    assert result.execution_policy_hash == expected.policy_hash


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
                "    test_only_execution_override: true",
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


def test_prompt_service_composes_shared_include_and_schema_snippet(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    prompts_root = tmp_path / "prompts"
    schemas_root = tmp_path / "schemas"
    (prompts_root / "_partials").mkdir(parents=True)
    schemas_root.mkdir(parents=True)
    (prompts_root / "_partials" / "evidence.yaml").write_text(
        "text: |\n  Shared evidence rule.\n",
        encoding="utf-8",
    )
    namespace_dir = prompts_root / "alpha"
    namespace_dir.mkdir(parents=True)
    (namespace_dir / "system.yaml").write_text(
        "\n".join(
            [
                "includes:",
                '  - "_partials/evidence.yaml"',
                "schema_snippets:",
                "  artifact_schema:",
                '    schema: "artifact.schema.json"',
                '    pointer: "/properties/summary"',
                "text: |",
                "  Local instruction.",
                "  {{ artifact_schema }}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (namespace_dir / "user.yaml").write_text("text: User prompt.\n", encoding="utf-8")
    (schemas_root / "artifact.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "object",
                        "required": ["tldr", "claim_evidence_map"],
                        "properties": {
                            "tldr": {"type": "string", "minLength": 1},
                            "claim_evidence_map": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "required": ["claim", "evidence_id"],
                                    "properties": {
                                        "claim": {"type": "string"},
                                        "evidence_id": {"type": "string"},
                                    },
                                },
                            },
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)
    external_boundary_mocks_only.setattr(prompt_service, "SCHEMAS_ROOT", schemas_root)

    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace="alpha", force_reload=True),
        _ctx(),
    )
    rendered = prompt_service.render_prompt(
        prompt_service.PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.system,
            variables={},
        ),
        _ctx(),
    )

    assert prompt_set.system.include_paths == [
        str((prompts_root / "_partials" / "evidence.yaml").resolve())
    ]
    assert "Shared evidence rule." in rendered.text
    assert "Local instruction." in rendered.text
    assert "Schema source: artifact.schema.json#/properties/summary" in rendered.text
    assert "- tldr: string, required, minLength=1" in rendered.text
    assert "- claim_evidence_map: array, required, minItems=1" in rendered.text
    assert "claim: string, required" in rendered.text
