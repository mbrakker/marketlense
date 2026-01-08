from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIResponseRequest, OpenAIResponseResult
from src.contracts.prompts import PromptLoadRequest
from src.contracts.run_context import RunContext
from src.services import openai_service
from src.services import prompt_service
from src.services import report_analysis_store_service
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.schema_validator import validate_schema
from src.utils.errors import AppError

logger = logging.getLogger("market_lense.evidence_pack_generator")


def generate_evidence_packs(
    report_id: str,
    vector_store_id: str,
    settings: AppSettings,
    ctx: Optional[RunContext] = None,
    *,
    openai_client=openai_service,
    prompt_client=prompt_service,
    analysis_store=report_analysis_store_service,
) -> Dict[str, dict]:
    ctx = ctx or new_run_context(task_id=f"evidence_pack:{report_id}")
    logger.info(log_event(
        ctx,
        role="generator",
        event="evidence_pack_start",
        module=logger.name,
        fields={"report_id": report_id, "vector_store_id": vector_store_id},
    ))
    steps = [
        ("doc_map", "doc_map", "doc_map"),
        ("scope", "evidence_packs/scope", "evidence_pack"),
        ("methods", "evidence_packs/methods", "evidence_pack"),
        ("findings", "evidence_packs/findings", "evidence_pack"),
        ("limitations", "evidence_packs/limitations", "evidence_pack"),
        ("quote_candidates", "evidence_packs/quote_candidates", "evidence_pack"),
    ]
    results: Dict[str, dict] = {}
    for step_name, prompt_ns, schema in steps:
        step_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{step_name}")
        results[step_name] = _generate_pack(
            report_id=report_id,
            vector_store_id=vector_store_id,
            prompt_namespace=f"report_vs/{prompt_ns}",
            schema_name="doc_map" if schema == "doc_map" else "evidence_pack",
            settings=settings,
            ctx=step_ctx,
            openai_client=openai_client,
            prompt_client=prompt_client,
            analysis_store=analysis_store,
            pack_name=step_name,
        )
    logger.info(log_event(
        ctx,
        role="generator",
        event="evidence_pack_complete",
        module=logger.name,
        fields={"report_id": report_id, "packs": list(results.keys())},
    ))
    return results


def _generate_pack(
    *,
    report_id: str,
    vector_store_id: str,
    prompt_namespace: str,
    schema_name: str,
    settings: AppSettings,
    ctx: RunContext,
    openai_client,
    prompt_client,
    analysis_store,
    pack_name: str,
) -> dict:
    logger.info(log_event(
        ctx,
        role="generator",
        event="evidence_pack_step_start",
        module=logger.name,
        fields={"report_id": report_id, "pack": pack_name, "prompt_namespace": prompt_namespace},
    ))
    prompt_set = prompt_client.load_prompt_set(PromptLoadRequest(schema_version="1.0", namespace=prompt_namespace), ctx)
    system_prompt = prompt_set.system.text
    user_prompt = prompt_set.user.text
    parsed_json = None
    not_found_reason = ""
    try:
        resp: OpenAIResponseResult = openai_client.openai_respond_with_vector_store(
            OpenAIResponseRequest(
                schema_version="1.0",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                vector_store_id=vector_store_id,
                model=settings.openai_model,
                temperature=settings.temperature,
                api_key=settings.openai_api_key,
                seed=settings.openai_seed,
                timeout_seconds=settings.openai_timeout_seconds,
                cost_ledger_path=settings.cost_ledger_path,
                cost_daily_path=settings.cost_daily_path,
                model_pricing=settings.model_pricing,
            ),
            ctx,
        )
        parsed_json = resp.parsed_json
        if parsed_json is None:
            not_found_reason = "model_returned_no_json"
        else:
            try:
                validate_schema(parsed_json, schema_name, ctx)
            except AppError as exc:
                not_found_reason = f"schema_validation_failed:{exc.code}"
    except AppError as exc:
        not_found_reason = exc.code
        parsed_json = None
    result_payload = parsed_json or _empty_payload(schema_name, not_found_reason)
    analysis_store.store_pack(settings.output_dir, report_id, pack_name, result_payload, ctx)
    logger.info(log_event(
        ctx,
        role="generator",
        event="evidence_pack_step_complete",
        module=logger.name,
        fields={"report_id": report_id, "pack": pack_name, "not_found_reason": not_found_reason},
    ))
    return result_payload


def _empty_payload(schema_name: str, reason: str) -> dict:
    if schema_name == "doc_map":
        return {"doc_id": "", "title": "", "sections": [], "not_found_reason": reason}
    return {"scope": "", "methods": [], "findings": [], "limitations": [], "quote_candidates": [], "not_found_reason": reason}
