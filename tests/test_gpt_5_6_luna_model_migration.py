from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
LUNA_MODEL = "gpt-5.6-luna"
OPENROUTER_LUNA_MODEL = "openai/gpt-5.6-luna"
EMBEDDING_MODEL = "text-embedding-3-large"


def _model_values(value: object, *, path: str = "") -> Iterator[tuple[str, str]]:
    if not isinstance(value, dict):
        return
    for key, child in value.items():
        child_path = f"{path}.{key}" if path else str(key)
        if key in {"model", "openai_model", "openrouter_model"} and isinstance(
            child, str
        ):
            yield child_path, child
        yield from _model_values(child, path=child_path)


def test_canonical_configuration_routes_every_generative_call_to_gpt_5_6_luna() -> None:
    config = yaml.safe_load(
        (REPO_ROOT / "src" / "config" / "app.yaml").read_text(encoding="utf-8")
    )
    pricing = yaml.safe_load(
        (REPO_ROOT / "src" / "config" / "llm-costs.yaml").read_text(encoding="utf-8")
    )["pricing"]

    configured_models = dict(_model_values(config))
    assert configured_models["ingest.openai_model"] == LUNA_MODEL
    assert (
        configured_models["browser_download.openrouter_model"] == OPENROUTER_LUNA_MODEL
    )
    assert (
        configured_models["llm_execution_policies.claim_embedding/generate.model"]
        == EMBEDDING_MODEL
    )
    assert (
        config["llm_execution_policies"]["claim_embedding/generate"]["dimensions"]
        == 1024
    )
    assert all(
        model in {LUNA_MODEL, OPENROUTER_LUNA_MODEL, EMBEDDING_MODEL}
        for model_path, model in configured_models.items()
        if model_path != "workflow_control.concurrency.model"
    )
    assert all(
        policy["model"] == LUNA_MODEL and policy["pricing_key"] == LUNA_MODEL
        for name, policy in config["llm_execution_policies"].items()
        if name != "claim_embedding/generate"
    )
    assert pricing[LUNA_MODEL].get("disposition", "priced") == "priced"
    assert pricing[OPENROUTER_LUNA_MODEL]["disposition"] == "enabled"


def test_example_configuration_does_not_reintroduce_a_non_luna_llm_route() -> None:
    config = yaml.safe_load(
        (REPO_ROOT / "src" / "config" / "app.example.yaml").read_text(encoding="utf-8")
    )

    configured_models = dict(_model_values(config))
    assert configured_models
    assert all(
        model in {LUNA_MODEL, OPENROUTER_LUNA_MODEL}
        for model_path, model in configured_models.items()
        if model_path != "workflow_control.concurrency.model"
    )
