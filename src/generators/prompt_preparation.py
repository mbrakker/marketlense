from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest, PromptSet
from src.contracts.run_context import RunContext
from src.utils.model_resolver import resolve_model


@dataclass(frozen=True)
class PreparedPromptBundle:
    schema_version: str = field(
        metadata={"doc": "Prepared prompt bundle schema version."}
    )
    namespace: str = field(metadata={"doc": "Prompt namespace used for loading."})
    prompt_set: PromptSet = field(
        metadata={"doc": "Loaded prompt set used to render the request."}
    )
    system_prompt: str = field(metadata={"doc": "Rendered system prompt text."})
    user_prompt: str = field(metadata={"doc": "Rendered user prompt text."})
    resolved_model: str = field(metadata={"doc": "Resolved model identifier."})


def prepare_prompt_bundle(
    *,
    namespace: str,
    settings: Any,
    ctx: RunContext,
    prompt_client: Any,
    system_variables: Optional[Dict[str, Any]] = None,
    user_variables: Optional[Dict[str, Any]] = None,
    reload_if_changed: bool = False,
    force_reload: bool = False,
    default_model: Optional[str] = None,
) -> PreparedPromptBundle:
    prompt_set = prompt_client.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace=namespace,
            reload_if_changed=reload_if_changed,
            force_reload=force_reload,
        ),
        ctx,
    )
    rendered_system = prompt_client.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.system,
            variables=dict(system_variables or {}),
        ),
        ctx,
    )
    rendered_user = prompt_client.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.user,
            variables=dict(user_variables or {}),
        ),
        ctx,
    )
    fallback_model = default_model or getattr(settings, "openai_model", "")
    resolved_model = resolve_model(
        namespace,
        getattr(settings, "openai_models", {}),
        fallback_model,
    )
    return PreparedPromptBundle(
        schema_version="1.0",
        namespace=namespace,
        prompt_set=prompt_set,
        system_prompt=rendered_system.text,
        user_prompt=rendered_user.text,
        resolved_model=resolved_model,
    )
