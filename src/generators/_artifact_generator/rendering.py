from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.contracts.analysis_family import AnalysisFamilyStatus
from src.contracts.config import AppSettings
from src.contracts.ingest import IngestSettings
from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseRequest
from src.contracts.prompts import PromptLoadRequest
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import ReportId
from src.contracts.schema_validation import SchemaValidateRequest
from src.generators.artifact_normalization import (
    artifact_base_variables,
    bind_artifact_evidence_spans,
    artifact_quote_candidates,
    artifact_retrieval_mode,
    normalize_artifact_toc_entries,
    artifact_vector_store_enabled,
    normalize_artifact_evidence_ids,
    normalize_artifact_insights,
    normalize_artifact_quotes,
    normalize_artifact_source_status,
    normalize_artifact_summary,
    normalize_expert_domain,
    pad_artifact_insights,
    strip_artifact_inline_reference_ids,
)
from src.generators.analysis_pack_cache import (
    CachedPackAdaptResult,
    load_cached_pack,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.analysis_store_adapter import (
    resolve_pack_path as resolve_analysis_pack_path,
    store_pack as store_analysis_pack,
)
from src.services import (
    file_service,
    llm_service,
    prompt_service,
    report_analysis_store_service,
)
from src.utils.errors import AppError
from src.utils.json_utils import safe_json_dumps
from src.utils.model_resolver import resolve_model
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.coercion import coerce_int
from src.services.schema_validator_service import (
    validate_evidence_references,
    validate_schema,
)
from src.utils.analysis_family import (
    family_is_abstained,
    serialize_family_status,
)
from src.utils.cache_utils import sha256_json

logger = logging.getLogger("market_lense.artifact_generator")

def render_artifact_json_model(
    *,
    namespace: str,
    variables: Dict[str, Any],
    settings: AppSettings | IngestSettings,
    ctx: RunContext,
    openai_client,
    prompt_client,
    allow_vector_store: bool,
    vector_store_id: Optional[str],
) -> Dict[str, Any]:
    prompt_bundle = prepare_prompt_bundle(
        namespace=namespace,
        settings=settings,
        ctx=ctx,
        prompt_client=prompt_client,
        system_variables=variables,
        user_variables=variables,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_prompt_rendered",
            module=logger.name,
            fields={
                "namespace": namespace,
                "system_path": prompt_bundle.prompt_set.system.path,
                "user_path": prompt_bundle.prompt_set.user.path,
                "prompt_system_sha256": prompt_bundle.prompt_set.system.sha256,
                "prompt_user_sha256": prompt_bundle.prompt_set.user.sha256,
                "system_prompt": prompt_bundle.system_prompt,
                "user_prompt": prompt_bundle.user_prompt,
            },
        )
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="model_resolved",
            module=logger.name,
            fields={
                "namespace": namespace,
                "resolved_model": prompt_bundle.resolved_model,
                "default_model": settings.openai_model,
            },
        )
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_model_request",
            module=logger.name,
            fields={
                "namespace": namespace,
                "model": prompt_bundle.resolved_model,
                "temperature": settings.temperature,
                "seed": settings.openai_seed,
                "retrieval_mode": (
                    "vector_store"
                    if allow_vector_store and vector_store_id
                    else "chat_json"
                ),
                "vector_store_id": vector_store_id or "",
            },
        )
    )
    if allow_vector_store and vector_store_id:
        resp = openai_client.openai_respond_with_vector_store(
            OpenAIResponseRequest(
                schema_version="1.0",
                system_prompt=prompt_bundle.system_prompt,
                user_prompt=prompt_bundle.user_prompt,
                vector_store_id=vector_store_id,
                model=prompt_bundle.resolved_model,
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
    else:
        resp = openai_client.openai_chat_json(
            OpenAIJSONPromptRequest(
                schema_version="1.0",
                system_prompt=prompt_bundle.system_prompt,
                user_prompt=prompt_bundle.user_prompt,
                model=prompt_bundle.resolved_model,
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
    parsed = resp.parsed_json if isinstance(resp.parsed_json, dict) else {}
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_model_complete",
            module=logger.name,
            fields={
                "namespace": namespace,
                "model": getattr(resp, "model", prompt_bundle.resolved_model),
                "has_json": bool(resp.parsed_json),
                "request_id": getattr(resp, "request_id", "") or "",
                "raw_response": getattr(resp, "text", "") or "",
            },
        )
    )
    return parsed



def _dump_json(data: Any) -> str:
    return safe_json_dumps(data, ensure_ascii=False, fallback="")


def _s(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)
