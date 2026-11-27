"""Orchestrate one independent review of an editorial coverage assessment."""

from __future__ import annotations

import json
from typing import Any

from src.contracts.artifact_generation import (
    EditorialCoverageChallengeRequest,
    EditorialCoverageChallengeResponse,
)
from src.contracts.config import AppSettings
from src.contracts.ingest import IngestSettings
from src.generators.artifact_generator import render_artifact_json_model
from src.generators.artifact_normalization import resolve_editorial_coverage_challenge
from src.generators.artifact_prompt_provenance import (
    ARTIFACT_PROMPT_VALIDATOR_VERSION,
    artifact_prompt_identity,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.services import prompt_service
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError


def challenge_editorial_coverage(
    request: EditorialCoverageChallengeRequest,
    *,
    settings: AppSettings | IngestSettings,
    openai_client: Any,
    report_id: str,
    report_name: str,
    prompt_client: Any = prompt_service,
) -> EditorialCoverageChallengeResponse:
    """Call the existing artifact renderer once with exact canonical inputs."""
    if request.schema_version != "1.0":
        raise AppError(
            code="editorial_coverage_challenge_invalid",
            message="Unsupported coverage challenge request",
            retryable=False,
        )
    variables = {
        "original_assessment_json": json.dumps(
            request.original_assessment, ensure_ascii=False, sort_keys=True
        ),
        "editorial_plan_json": json.dumps(
            request.editorial_plan, ensure_ascii=False, sort_keys=True
        ),
        "final_insights_json": json.dumps(
            request.final_insights, ensure_ascii=False, sort_keys=True
        ),
        "verified_facts_json": json.dumps(
            request.verified_facts, ensure_ascii=False, sort_keys=True
        ),
        "original_essential_obligations_json": json.dumps(
            request.original_essential_obligations, ensure_ascii=False, sort_keys=True
        ),
    }
    request_id = ""

    def observe(response: Any, _elapsed_ms: float, _mode: str) -> None:
        nonlocal request_id
        request_id = str(getattr(response, "request_id", "") or "")

    def validate(payload: dict[str, Any]) -> None:
        resolve_editorial_coverage_challenge(
            original_assessment=request.original_assessment,
            challenge=payload,
            editorial_plan=request.editorial_plan,
            candidate_insights=request.candidate_insights,
            final_insights=request.final_insights,
            original_essential_obligations=request.original_essential_obligations,
            require_original_obligation_assessment=(
                request.require_original_obligation_assessment
            ),
        )

    namespace = "report_vs/artifacts/editorial_coverage_challenge"
    prepared = prepare_prompt_bundle(
        namespace=namespace,
        settings=settings,
        ctx=request.ctx,
        prompt_client=prompt_client,
        system_variables=variables,
        user_variables=variables,
        retrieval_mode="chat_json",
        temperature=settings.temperature,
        seed=settings.openai_seed,
        timeout_seconds=settings.openai_timeout_seconds,
        output_contract_schema_version="artifact_json:1.0",
        validator_version=ARTIFACT_PROMPT_VALIDATOR_VERSION,
    )
    result = render_artifact_json_model(
        namespace=namespace,
        variables=variables,
        settings=settings,
        ctx=request.ctx,
        openai_client=openai_client,
        prompt_client=prompt_client,
        allow_vector_store=False,
        vector_store_id=None,
        report_id=report_id,
        report_name=report_name,
        payload_validator=validate,
        response_observer=observe,
        response_contract_name="editorial_coverage_challenge_output",
        response_contract_identity_version="v1",
        prepared_prompt_bundle=prepared,
    )
    return EditorialCoverageChallengeResponse(
        schema_version="1.0",
        verdicts=result["verdicts"],
        request_id=request_id,
        prompt_identity=artifact_prompt_identity(
            prepared=prepared,
            relevant_input_hash=sha256_json(variables),
            validator_version="editorial_coverage_challenge_output:v1",
        ),
    )
