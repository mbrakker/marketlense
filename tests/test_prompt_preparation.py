from types import SimpleNamespace

from src.contracts.prompts import (
    PromptDependency,
    PromptDependencyManifest,
    PromptSet,
    PromptTemplate,
)
from src.contracts.run_context import RunContext
from src.generators.artifact_prompt_provenance import (
    ARTIFACT_PROMPT_VALIDATOR_VERSION,
    artifact_prompt_identity,
    current_artifact_prompt_identity,
)
from src.generators.prompt_preparation import prepare_prompt_bundle


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


class RecordingPromptClient:
    def __init__(self) -> None:
        self.load_requests = []
        self.render_requests = []

    def load_prompt_set(self, request, ctx):
        self.load_requests.append((request, ctx))
        manifest = PromptDependencyManifest(
            schema_version="1.0",
            namespace=request.namespace,
            system_root=PromptDependency(
                schema_version="1.0",
                path=f"prompts/{request.namespace}/system.yaml",
                sha256="system-sha",
                kind="system_root",
            ),
            user_root=PromptDependency(
                schema_version="1.0",
                path=f"prompts/{request.namespace}/user.yaml",
                sha256="user-sha",
                kind="user_root",
            ),
            prompt_content_hash="a" * 64,
        )
        return PromptSet(
            schema_version="1.0",
            system=PromptTemplate(
                schema_version="1.0",
                path=f"{request.namespace}/system",
                text="System {topic}",
                sha256="system-sha",
            ),
            user=PromptTemplate(
                schema_version="1.0",
                path=f"{request.namespace}/user",
                text="User {audience}",
                sha256="user-sha",
            ),
            dependency_manifest=manifest,
            prompt_content_hash=manifest.prompt_content_hash,
        )

    def render_prompt(self, request, ctx):
        self.render_requests.append((request, ctx))
        return SimpleNamespace(text=request.template.text.format(**request.variables))


def test_prepare_prompt_bundle_loads_renders_and_resolves_model(
    assert_no_defaulted_required_fields,
) -> None:
    prompt_client = RecordingPromptClient()
    settings = SimpleNamespace(
        openai_model="gpt-default",
        openai_models={"report_vs/artifacts": "gpt-artifacts"},
    )

    bundle = prepare_prompt_bundle(
        namespace="report_vs/artifacts/summary",
        settings=settings,
        ctx=_ctx(),
        prompt_client=prompt_client,
        system_variables={"topic": "market"},
        user_variables={"audience": "analyst"},
    )

    assert bundle.system_prompt == "System market"
    assert bundle.user_prompt == "User analyst"
    assert bundle.resolved_model == "gpt-artifacts"
    assert bundle.routing_decision.policy_source == "report_vs/artifacts"
    assert bundle.routing_decision.same_provider_fallback is True
    assert prompt_client.load_requests[0][0].namespace == "report_vs/artifacts/summary"
    assert_no_defaulted_required_fields(bundle)


def test_prepare_prompt_bundle_forwards_reload_flags() -> None:
    prompt_client = RecordingPromptClient()
    settings = SimpleNamespace(openai_model="gpt-default", openai_models={})

    prepare_prompt_bundle(
        namespace="rank_candidates",
        settings=settings,
        ctx=_ctx(),
        prompt_client=prompt_client,
        system_variables={"topic": "figures"},
        user_variables={"audience": "editor"},
        reload_if_changed=True,
        force_reload=True,
    )

    load_request, load_ctx = prompt_client.load_requests[0]
    assert load_request.reload_if_changed is True
    assert load_request.force_reload is True
    assert load_ctx.task_id == "t"


def test_gpt6_artifact_checkpoint_identity_matches_producing_prompt() -> None:
    prompt_client = RecordingPromptClient()
    namespace = "report_vs/artifacts/summary"
    settings = SimpleNamespace(
        openai_model="gpt-6-luna",
        openai_models={},
        llm_routing={},
        llm_execution_policies={
            namespace: {
                "provider": "openai",
                "model": "gpt-6-luna",
                "reasoning_effort": "medium",
                "max_output_tokens": 1024,
                "retrieval_mode": "chat_json",
            }
        },
        temperature=1.0,
        openai_seed=7,
        openai_timeout_seconds=600.0,
    )
    bundle = prepare_prompt_bundle(
        namespace=namespace,
        settings=settings,
        ctx=_ctx(),
        prompt_client=prompt_client,
        system_variables={"topic": "market"},
        user_variables={"audience": "analyst"},
        retrieval_mode="chat_json",
        output_contract_schema_version="artifact_json:1.0",
        validator_version=ARTIFACT_PROMPT_VALIDATOR_VERSION,
    )

    produced = artifact_prompt_identity(
        prepared=bundle, relevant_input_hash="input-hash"
    )
    current = current_artifact_prompt_identity(
        namespace=namespace,
        prompt_set=bundle.prompt_set,
        settings=settings,
        retrieval_mode="chat_json",
        relevant_input_hash="input-hash",
    )
    assert bundle.effective_reasoning_effort == "medium"
    assert bundle.effective_temperature is None
    assert bundle.effective_seed is None
    assert produced == current
