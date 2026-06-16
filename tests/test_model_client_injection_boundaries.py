from __future__ import annotations

from pathlib import Path


FORBIDDEN_GENERATOR_CLIENT_CONSTRUCTION = (
    "llm_service.build_client(",
    "llm_service.build_client_for_settings(",
    "llm_service.build_client_from_callables(",
    "llm_service.build_openai_client(",
    "llm_service.build_openai_client_for_settings(",
    "llm_service.build_openai_client_from_callables(",
    "llm_service.client_policy_from_settings(",
    "llm_service.openai_client_policy_from_settings(",
)


def test_generators_do_not_construct_model_clients() -> None:
    generator_root = Path("src/generators")
    offenders: list[str] = []
    for path in sorted(generator_root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_GENERATOR_CLIENT_CONSTRUCTION:
            if marker in text:
                offenders.append(f"{path}:{marker}")

    assert offenders == []
