from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from src.contracts.config import ConfigLoadRequest
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import (
    PromptDependency,
    PromptDependencyManifest,
    PromptSet,
    PromptTemplate,
)
from src.contracts.run_context import RunContext
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.structured_output_execution import (
    invoke_structured_output_model,
    recovery_prompt_bundle,
)
from src.services.config_service import load_settings


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="policy", task_id="t", span_id="s")


class _PromptClient:
    def load_prompt_set(self, request, ctx):
        del ctx
        manifest = PromptDependencyManifest(
            schema_version="1.0",
            namespace=request.namespace,
            system_root=PromptDependency(
                schema_version="1.0",
                path=f"{request.namespace}/system.yaml",
                sha256="a" * 64,
                kind="system_root",
            ),
            user_root=PromptDependency(
                schema_version="1.0",
                path=f"{request.namespace}/user.yaml",
                sha256="b" * 64,
                kind="user_root",
            ),
            prompt_content_hash="c" * 64,
        )
        return PromptSet(
            schema_version="1.0",
            system=PromptTemplate(
                schema_version="1.0",
                path=f"{request.namespace}/system",
                text="system",
                sha256="a" * 64,
            ),
            user=PromptTemplate(
                schema_version="1.0",
                path=f"{request.namespace}/user",
                text="user",
                sha256="b" * 64,
            ),
            dependency_manifest=manifest,
            prompt_content_hash="c" * 64,
        )

    def render_prompt(self, request, ctx):
        del ctx
        return SimpleNamespace(text=request.template.text)


class _OpenAIRecorder:
    def __init__(self) -> None:
        self.requests = []

    def openai_chat_json(self, request, ctx):
        del ctx
        self.requests.append(request)
        return OpenAIResponseResult(
            schema_version="1.0", text="{}", parsed_json={}, model=request.model
        )


def test_recovery_policy_reaches_provider_request_without_call_site_override():
    workspace = Path(__file__).resolve().parents[1]
    settings = load_settings(
        ConfigLoadRequest(
            schema_version="1.0", path=str(workspace / "src" / "config" / "app.yaml")
        ),
        _ctx(),
    )
    prompt_client = _PromptClient()
    primary = prepare_prompt_bundle(
        namespace="report_vs/validate/grounding",
        settings=settings,
        ctx=_ctx(),
        prompt_client=prompt_client,
        system_variables={},
        user_variables={},
        max_output_tokens=1,
        retrieval_mode="chat_json",
    )
    repair = recovery_prompt_bundle(
        mode="model_repair",
        artifact_family="validation_grounding",
        schema_errors="coverage",
        original_response="{}",
        output_schema={"type": "object"},
        source_evidence={},
        settings=settings,
        ctx=_ctx(),
        prompt_client=prompt_client,
        vector_store_id=None,
    )
    regenerate = recovery_prompt_bundle(
        mode="regeneration",
        artifact_family="validation_grounding",
        schema_errors="coverage",
        original_response="{}",
        output_schema={"type": "object"},
        source_evidence={},
        settings=settings,
        ctx=_ctx(),
        prompt_client=prompt_client,
        vector_store_id=None,
    )
    recorder = _OpenAIRecorder()
    for attempt, bundle in enumerate((primary, repair, regenerate)):
        invoke_structured_output_model(
            openai_client=recorder,
            prompt_bundle=bundle,
            settings=settings,
            ctx=_ctx(),
            vector_store_id=None,
            report_id="policy-report",
            artifact_family="validation_grounding",
            stage="grounding",
            publisher_name="",
            report_name="",
            source_url="",
            output_schema={"type": "object"},
            output_schema_identity="grounding.v1",
            repair_attempt=attempt,
        )

    assert [request.max_output_tokens for request in recorder.requests] == [
        16384,
        16384,
        16384,
    ]
    assert [request.model for request in recorder.requests] == [
        "gpt-6-luna",
        "gpt-6-luna",
        "gpt-6-luna",
    ]
    assert [request.reasoning_effort for request in recorder.requests] == [
        "medium",
        "medium",
        "medium",
    ]
    assert primary.effective_max_output_tokens == 16384
    assert primary.execution_policy.policy_source == "report_vs/validate/grounding"
    assert repair.execution_policy.policy_source == "report_vs/structured_output/repair"
    assert regenerate.execution_policy.policy_source == (
        "report_vs/structured_output/regenerate"
    )
    assert primary.execution_policy.policy_hash
    assert repair.execution_policy.policy_hash
    assert regenerate.execution_policy.policy_hash
    assert len({request.execution_identity for request in recorder.requests}) == 3
    assert len({request.execution_policy_hash for request in recorder.requests}) == 3


def test_governed_cap_is_part_of_recovery_execution_identity():
    workspace = Path(__file__).resolve().parents[1]
    settings = load_settings(
        ConfigLoadRequest(
            schema_version="1.0", path=str(workspace / "src" / "config" / "app.yaml")
        ),
        _ctx(),
    )
    prompt_client = _PromptClient()
    current = recovery_prompt_bundle(
        mode="regeneration",
        artifact_family="validation_grounding",
        schema_errors="coverage",
        original_response="{}",
        output_schema={"type": "object"},
        source_evidence={},
        settings=settings,
        ctx=_ctx(),
        prompt_client=prompt_client,
        vector_store_id=None,
    )
    changed_policies = dict(settings.llm_execution_policies)
    changed_regeneration = dict(
        changed_policies["report_vs/structured_output/regenerate"]
    )
    changed_regeneration["max_output_tokens"] = 8192
    changed_policies["report_vs/structured_output/regenerate"] = changed_regeneration
    changed_settings = replace(settings, llm_execution_policies=changed_policies)
    changed = recovery_prompt_bundle(
        mode="regeneration",
        artifact_family="validation_grounding",
        schema_errors="coverage",
        original_response="{}",
        output_schema={"type": "object"},
        source_evidence={},
        settings=changed_settings,
        ctx=_ctx(),
        prompt_client=prompt_client,
        vector_store_id=None,
    )

    assert current.effective_max_output_tokens == 16384
    assert changed.effective_max_output_tokens == 8192
    assert current.execution_policy.policy_hash != changed.execution_policy.policy_hash
    assert current.execution_identity.execution_identity != (
        changed.execution_identity.execution_identity
    )
