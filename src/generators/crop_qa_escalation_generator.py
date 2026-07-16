from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from src.contracts.crop_qa_escalation import (
    CropQaEscalationDecision,
    CropQaEscalationPolicy,
    CropQaEscalationRequest,
    CropQaEscalationResponse,
)
from src.contracts.files import ReadTextRequest
from src.contracts.openai import OpenAIJSONImagePromptRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.run_context import RunContext
from src.services.file_service import read_text
from src.services.prompt_service import load_prompt_set, render_prompt
from src.utils.costing import estimate_cost_usd
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.model_client_contract import require_injected_model_client

logger = logging.getLogger("market_lense.crop_qa_escalation_generator")


def evaluate_crop_qa_escalation(
    crops: list[dict[str, Any]],
    policy: CropQaEscalationPolicy,
    *,
    llm_client: Any | None,
    ctx: RunContext,
) -> CropQaEscalationResponse:
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="crop_qa_escalation_start",
            module=logger.name,
            fields={
                "candidate_count": len(crops),
                "enabled": policy.enabled,
                "quality_profile": policy.quality_profile,
                "max_escalations": policy.max_escalations,
            },
        )
    )
    prompt_payload: dict[str, Any] = {}
    if policy.enabled:
        prompt_payload = _load_escalation_prompts(policy, ctx)
    decisions: list[CropQaEscalationDecision] = []
    eligible_count = 0
    model_call_count = 0
    repair_count = 0
    reject_count = 0
    for crop in crops:
        sidecar = _load_sidecar(crop, ctx)
        eligible, reason = _is_escalation_eligible(crop, sidecar, policy)
        if reason == "high_risk_defect":
            decisions.append(_deterministic_rejection(crop, sidecar, reason))
            reject_count += 1
            continue
        if not eligible or model_call_count >= max(0, policy.max_escalations):
            if eligible:
                reason = "escalation_budget_exhausted"
            decisions.append(_deterministic_decision(crop, sidecar, reason))
            continue
        eligible_count += 1
        client = require_injected_model_client(llm_client, scope="crop_qa_escalation")
        result = client.openai_chat_json_with_images(
            OpenAIJSONImagePromptRequest(
                schema_version="1.0",
                system_prompt=prompt_payload["system_prompt"],
                user_prompt=_render_user_prompt(prompt_payload, crop, sidecar, ctx),
                model=policy.model,
                temperature=policy.temperature,
                api_key=policy.api_key,
                image_paths=[_crop_image_path(crop)],
                seed=policy.seed,
                timeout_seconds=policy.timeout_seconds,
                cost_ledger_path=policy.cost_ledger_path,
                cost_daily_path=policy.cost_daily_path,
                model_pricing=dict(policy.model_pricing),
            ),
            ctx,
        )
        model_call_count += 1
        decision = _model_decision(crop, sidecar, result, policy)
        if decision.decision == "repair":
            if repair_count >= max(0, policy.max_repairs):
                decision = CropQaEscalationDecision(
                    **{
                        **asdict(decision),
                        "decision": "reject",
                        "reason": "repair_budget_exhausted",
                        "repair_instruction": "",
                    }
                )
            else:
                repair_count += 1
        if decision.decision == "reject":
            reject_count += 1
        decisions.append(decision)
    response = CropQaEscalationResponse(
        schema_version="1.0",
        decisions=decisions,
        eligible_count=eligible_count,
        model_call_count=model_call_count,
        repair_count=repair_count,
        reject_count=reject_count,
        escalation_rate=round(model_call_count / len(crops), 6) if crops else 0.0,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="crop_qa_escalation_complete",
            module=logger.name,
            fields={
                "schema_version": response.schema_version,
                "decision_count": len(response.decisions),
                "eligible_count": response.eligible_count,
                "model_call_count": response.model_call_count,
                "repair_count": response.repair_count,
                "reject_count": response.reject_count,
                "escalation_rate": response.escalation_rate,
            },
        )
    )
    return response


def _load_escalation_prompts(
    policy: CropQaEscalationPolicy,
    ctx: RunContext,
) -> dict[str, Any]:
    prompt_set = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace=policy.prompt_namespace,
            reload_if_changed=True,
        ),
        ctx,
    )
    rendered_system = render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.system,
            variables={},
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="crop_qa_escalation_prompt_selected",
            module=logger.name,
            fields={
                "prompt_namespace": policy.prompt_namespace,
                "system_path": prompt_set.system.path,
                "user_path": prompt_set.user.path,
                "system_sha256": prompt_set.system.sha256,
                "user_sha256": prompt_set.user.sha256,
            },
        )
    )
    return {
        "prompt_set": prompt_set,
        "system_prompt": rendered_system.text,
    }


def _render_user_prompt(
    prompt_payload: dict[str, Any],
    crop: dict[str, Any],
    sidecar: dict[str, Any],
    ctx: RunContext,
) -> str:
    rendered = render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_payload["prompt_set"].user,
            variables={
                "candidate_id": _candidate_id(crop),
                "deterministic_sidecar": json.dumps(
                    sidecar,
                    ensure_ascii=True,
                    sort_keys=True,
                ),
            },
        ),
        ctx,
    )
    return rendered.text


def _load_sidecar(crop: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    sidecar_path = _sidecar_path(crop)
    if not sidecar_path:
        return {}
    try:
        payload = json.loads(
            read_text(
                ReadTextRequest(schema_version="1.0", path=sidecar_path),
                ctx,
            ).content
        )
    except json.JSONDecodeError as exc:
        raise AppError(
            code="crop_qa_sidecar_invalid",
            message="Crop QA sidecar must be valid JSON",
            cause=exc,
            retryable=False,
            context={"qa_sidecar_path": sidecar_path},
        ) from exc
    return payload if isinstance(payload, dict) else {}


def _is_escalation_eligible(
    crop: dict[str, Any],
    sidecar: dict[str, Any],
    policy: CropQaEscalationPolicy,
) -> tuple[bool, str]:
    if not policy.enabled:
        return False, "policy_disabled"
    if _quality_profile(crop, sidecar) != policy.quality_profile:
        return False, "quality_profile_not_eligible"
    if not _sidecar_path(crop):
        return False, "qa_sidecar_missing"
    score = _qa_score(crop, sidecar)
    defects = set(_qa_defects(crop, sidecar))
    if defects.intersection(set(policy.high_risk_defects)):
        return False, "high_risk_defect"
    if score is not None and (
        policy.low_confidence_min_score <= score <= policy.low_confidence_max_score
    ):
        return True, "low_confidence_score"
    return False, "deterministic_qa_passed"


def _deterministic_decision(
    crop: dict[str, Any],
    sidecar: dict[str, Any],
    reason: str,
) -> CropQaEscalationDecision:
    return CropQaEscalationDecision(
        schema_version="1.0",
        candidate_id=_candidate_id(crop),
        image_path=_crop_image_path(crop),
        qa_sidecar_path=_sidecar_path(crop),
        deterministic_score=_qa_score(crop, sidecar),
        deterministic_defects=_qa_defects(crop, sidecar),
        decision="not_escalated",
        reason=reason,
        model_confidence=None,
        defects=[],
        repair_instruction="",
        provider_request_id="",
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        estimated_cost_usd=0.0,
    )


def _deterministic_rejection(
    crop: dict[str, Any],
    sidecar: dict[str, Any],
    reason: str,
) -> CropQaEscalationDecision:
    return CropQaEscalationDecision(
        schema_version="1.0",
        candidate_id=_candidate_id(crop),
        image_path=_crop_image_path(crop),
        qa_sidecar_path=_sidecar_path(crop),
        deterministic_score=_qa_score(crop, sidecar),
        deterministic_defects=_qa_defects(crop, sidecar),
        decision="reject",
        reason="high_risk_defect_deterministically_rejected",
        model_confidence=None,
        defects=[],
        repair_instruction="",
        provider_request_id="",
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        estimated_cost_usd=0.0,
    )


def _model_decision(
    crop: dict[str, Any],
    sidecar: dict[str, Any],
    result: Any,
    policy: CropQaEscalationPolicy,
) -> CropQaEscalationDecision:
    payload = result.parsed_json if isinstance(result.parsed_json, dict) else {}
    decision = str(payload.get("decision") or "reject").strip().lower()
    if decision not in {"accept", "repair", "reject"}:
        decision = "reject"
    defects = (
        [str(item).strip() for item in payload.get("defects", []) if str(item).strip()]
        if isinstance(payload.get("defects"), list)
        else []
    )
    confidence_value = payload.get("confidence")
    confidence = (
        float(confidence_value) if isinstance(confidence_value, (int, float)) else None
    )
    return CropQaEscalationDecision(
        schema_version="1.0",
        candidate_id=_candidate_id(crop),
        image_path=_crop_image_path(crop),
        qa_sidecar_path=_sidecar_path(crop),
        deterministic_score=_qa_score(crop, sidecar),
        deterministic_defects=_qa_defects(crop, sidecar),
        decision=decision,
        reason=str(payload.get("reason") or "model_escalation").strip(),
        model_confidence=confidence,
        defects=defects,
        repair_instruction=str(payload.get("repair_instruction") or "").strip(),
        provider_request_id=str(result.request_id or ""),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        total_tokens=result.total_tokens,
        estimated_cost_usd=estimate_cost_usd(
            str(getattr(result, "model", "") or policy.model),
            int(result.input_tokens or 0),
            int(result.output_tokens or 0),
            0,
            policy.model_pricing,
        ),
    )


def _candidate_id(crop: dict[str, Any]) -> str:
    return str(crop.get("candidate_id") or crop.get("id") or "").strip()


def _crop_image_path(crop: dict[str, Any]) -> str:
    return str(crop.get("path") or crop.get("image_path") or "").strip()


def _sidecar_path(crop: dict[str, Any]) -> str:
    return str(crop.get("qa_sidecar_path") or "").strip()


def _quality_profile(crop: dict[str, Any], sidecar: dict[str, Any]) -> str:
    return str(
        crop.get("quality_profile")
        or sidecar.get("quality_profile")
        or sidecar.get("mode")
        or ""
    ).strip()


def _qa_score(crop: dict[str, Any], sidecar: dict[str, Any]) -> float | None:
    raw_qa = sidecar.get("qa")
    qa: dict[str, Any] = raw_qa if isinstance(raw_qa, dict) else {}
    value = crop.get("score", sidecar.get("score", qa.get("total_score")))
    if not isinstance(value, (int, float)):
        return None
    score = float(value)
    return round(score * 100.0, 4) if 0.0 <= score <= 1.0 else score


def _qa_defects(crop: dict[str, Any], sidecar: dict[str, Any]) -> list[str]:
    raw_qa = sidecar.get("qa")
    qa: dict[str, Any] = raw_qa if isinstance(raw_qa, dict) else {}
    value = crop.get("defects", sidecar.get("defects", qa.get("defect_labels")))
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def escalate_crop_qa(
    request: CropQaEscalationRequest,
    ctx: RunContext,
    *,
    llm_client: Any | None = None,
) -> CropQaEscalationResponse:
    return evaluate_crop_qa_escalation(
        list(request.crops),
        request.policy,
        llm_client=llm_client,
        ctx=ctx,
    )


__all__ = ["escalate_crop_qa", "evaluate_crop_qa_escalation"]
