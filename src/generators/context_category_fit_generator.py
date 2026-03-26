from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from src.contracts.categories import CategoryMappingLoadRequest
from src.contracts.context_category_fit import (
    CategoryFitCandidate,
    ContextCategoryFitRequest,
    ContextCategoryFitResponse,
    ReportCategoryContext,
)
from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseResult
from src.contracts.schema_validation import SchemaValidateRequest
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.services import llm_service, openai_service, prompt_service
from src.services.category_mapping_service import load_mappings as load_category_mappings
from src.services.schema_validator_service import validate_schema
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.context_category_fit_generator")


def fit_report_categories_from_context(
    request: ContextCategoryFitRequest,
    ctx,
    *,
    openai_client=None,
    prompt_client=prompt_service,
    mapping_client=load_category_mappings,
) -> ContextCategoryFitResponse:
    openai_client = openai_client or llm_service.build_openai_client(
        base_client=openai_service,
        policy=llm_service.openai_client_policy_from_settings(
            request.settings,
            scope="context_category_fit",
        ),
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="context_category_fit_start",
            module=logger.name,
            fields={
                "report_id": request.context.report_id,
                "title": request.context.title,
                "prompt_namespace": request.prompt_namespace,
                "category_mapping_path": request.category_mapping_path,
            },
        )
    )
    mappings_resp = mapping_client(
        CategoryMappingLoadRequest(
            schema_version="1.0",
            path=request.category_mapping_path,
            reload_if_changed=True,
        ),
        ctx,
    )
    category_profiles = [
        {
            "id": category.id,
            "label": category.label,
            "description": category.description,
            "definition": category.definition or category.description,
            "include_when": list(category.include_when or []),
            "exclude_when": list(category.exclude_when or []),
        }
        for category in mappings_resp.mappings.categories
        if category.portal_exposed
    ]
    prompt_bundle = prepare_prompt_bundle(
        namespace=request.prompt_namespace,
        settings=request.settings,
        ctx=ctx,
        prompt_client=prompt_client,
        system_variables={},
        user_variables={
            "report_context_json": json.dumps(
                _serialize_context(request.context), ensure_ascii=True, indent=2
            ),
            "category_profiles_json": json.dumps(
                category_profiles, ensure_ascii=True, indent=2
            ),
        },
        reload_if_changed=True,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="context_category_fit_prompt_rendered",
            module=logger.name,
            fields={
                "namespace": request.prompt_namespace,
                "system_path": prompt_bundle.prompt_set.system.path,
                "system_sha256": prompt_bundle.prompt_set.system.sha256,
                "user_path": prompt_bundle.prompt_set.user.path,
                "user_sha256": prompt_bundle.prompt_set.user.sha256,
                "resolved_model": prompt_bundle.resolved_model,
                "system_prompt": prompt_bundle.system_prompt,
                "user_prompt": prompt_bundle.user_prompt,
            },
        )
    )
    try:
        response: OpenAIResponseResult = openai_client.openai_chat_json(
            OpenAIJSONPromptRequest(
                schema_version="1.0",
                system_prompt=prompt_bundle.system_prompt,
                user_prompt=prompt_bundle.user_prompt,
                model=prompt_bundle.resolved_model,
                temperature=float(getattr(request.settings, "temperature", 1.0)),
                api_key=request.settings.openai_api_key,
                seed=request.settings.openai_seed,
                timeout_seconds=request.settings.openai_timeout_seconds,
                cost_ledger_path=request.settings.cost_ledger_path,
                cost_daily_path=request.settings.cost_daily_path,
                model_pricing=request.settings.model_pricing,
            ),
            ctx,
        )
    except AppError:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise AppError(
            code="context_category_fit_failed",
            message="Context-first category fit request failed",
            cause=exc,
            retryable=True,
            context={"report_id": request.context.report_id},
        ) from exc

    payload = response.parsed_json if isinstance(response.parsed_json, dict) else None
    if payload is None:
        raise AppError(
            code="context_category_fit_invalid_json",
            message="Context-first category fit returned no JSON object",
            retryable=False,
            context={
                "report_id": request.context.report_id,
                "response_preview": (response.text or "")[:400],
            },
        )
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0",
            payload=payload,
            schema_name="context_category_fit",
        ),
        ctx,
    )
    fit_response = _coerce_fit_response(
        payload=payload,
        report_id=request.context.report_id,
        category_profiles=category_profiles,
        model=str(response.model or prompt_bundle.resolved_model or ""),
        raw_response=str(response.text or ""),
        request_id=str(response.request_id or "") or None,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="context_category_fit_complete",
            module=logger.name,
            fields={
                "report_id": fit_response.report_id,
                "categories": fit_response.categories,
                "candidate_count": len(fit_response.fits),
                "request_id": fit_response.request_id or "",
                "model": fit_response.model,
            },
        )
    )
    return fit_response


def _serialize_context(context: ReportCategoryContext) -> Dict[str, Any]:
    return {
        "report_id": context.report_id,
        "title": context.title,
        "publisher": context.publisher,
        "region": context.region,
        "time_period": context.time_period,
        "overview": context.overview,
        "methods": list(context.methods),
        "key_findings": list(context.key_findings),
        "limitations": list(context.limitations),
        "sections": [
            {
                "section_label": section.section_label,
                "source_pack": section.source_pack,
                "summary": section.summary,
                "key_points": list(section.key_points),
            }
            for section in context.sections
        ],
    }


def _coerce_fit_response(
    *,
    payload: dict,
    report_id: str,
    category_profiles: List[dict[str, str]],
    model: str,
    raw_response: str,
    request_id: str | None,
) -> ContextCategoryFitResponse:
    profile_by_id = {str(item["id"]): item for item in category_profiles}
    fits: List[CategoryFitCandidate] = []
    for item in payload.get("category_fits") or []:
        if not isinstance(item, dict):
            continue
        category_id = str(item.get("category_id") or "").strip()
        if category_id not in profile_by_id:
            continue
        label = str(item.get("label") or profile_by_id[category_id]["label"]).strip()
        decision = str(item.get("decision") or "").strip().lower()
        if decision not in {"primary", "secondary", "reject"}:
            decision = "reject"
        try:
            fit_score = float(item.get("fit_score"))
        except (TypeError, ValueError):
            fit_score = 0.0
        fit_score = max(0.0, min(1.0, fit_score))
        evidence_sections = []
        for value in item.get("evidence_sections") or []:
            text = str(value or "").strip()
            if text and text not in evidence_sections:
                evidence_sections.append(text)
        fits.append(
            CategoryFitCandidate(
                schema_version="1.0",
                category_id=category_id,
                label=label or profile_by_id[category_id]["label"],
                fit_score=fit_score,
                decision=decision,
                why_fit=str(item.get("why_fit") or "").strip(),
                why_not_fit=str(item.get("why_not_fit") or "").strip(),
                evidence_sections=evidence_sections,
            )
        )
    fits.sort(
        key=lambda item: (
            0
            if item.decision == "primary"
            else 1 if item.decision == "secondary" else 2,
            -item.fit_score,
            item.category_id,
        )
    )
    selected_ids: List[str] = []
    for category_id in payload.get("selected_category_ids") or []:
        text = str(category_id or "").strip()
        if text in profile_by_id and text not in selected_ids:
            selected_ids.append(text)
    if not selected_ids:
        for fit in fits:
            if fit.decision in {"primary", "secondary"} and fit.category_id not in selected_ids:
                selected_ids.append(fit.category_id)
            if len(selected_ids) >= 2:
                break
    selected_ids = selected_ids[:2]
    labels = [profile_by_id[item]["label"] for item in selected_ids]
    return ContextCategoryFitResponse(
        schema_version="1.0",
        report_id=report_id,
        categories=selected_ids,
        category_labels=labels,
        fits=fits,
        request_id=request_id,
        model=model,
        raw_response=raw_response,
    )
