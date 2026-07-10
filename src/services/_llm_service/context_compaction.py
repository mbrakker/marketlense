from __future__ import annotations

import logging
import re
from dataclasses import asdict, replace
from typing import Any

from src.contracts.llm import LLMContextCompactionPolicy, LLMContextCompactionResult
from src.contracts.run_context import RunContext
from src.utils.costing import estimate_cost_usd, estimate_text_tokens
from src.utils.logging import log_event

_ANCHOR_RE = re.compile(
    r"(?i)\b(metric|quote|claim|citation|evidence|validation_anchor|source|figure|table|page)\b|%"
)


def compact_prompt_request_if_needed(
    *,
    request: Any,
    ctx: RunContext,
    operation: str,
    logger: logging.Logger,
) -> tuple[Any, LLMContextCompactionResult]:
    policy = _normalize_policy(getattr(request, "context_compaction_policy", None))
    system_prompt = str(getattr(request, "system_prompt", "") or "")
    user_prompt = str(getattr(request, "user_prompt", "") or "")
    original_input_tokens = estimate_text_tokens(system_prompt) + estimate_text_tokens(
        user_prompt
    )
    original_cost = _estimate_request_cost(request, original_input_tokens, policy)
    trigger_reason = _trigger_reason(
        policy=policy,
        input_tokens=original_input_tokens,
        estimated_cost_usd=original_cost,
    )
    if not trigger_reason:
        return request, _result(
            policy=policy,
            compacted=False,
            trigger_reason="within_budget",
            original_input_tokens=original_input_tokens,
            compacted_input_tokens=original_input_tokens,
            original_cost=original_cost,
            compacted_cost=original_cost,
            retained_anchor_count=0,
            original_user_prompt=user_prompt,
            compacted_user_prompt=user_prompt,
        )

    compacted_user_prompt, retained_anchor_count = _compact_user_prompt(
        user_prompt=user_prompt,
        system_prompt_tokens=estimate_text_tokens(system_prompt),
        max_input_tokens=policy.max_input_tokens,
        max_anchor_lines=max(0, int(policy.max_anchor_lines)),
        min_tail_lines=max(0, int(policy.min_tail_lines)),
    )
    compacted_input_tokens = estimate_text_tokens(system_prompt) + estimate_text_tokens(
        compacted_user_prompt
    )
    compacted_cost = _estimate_request_cost(request, compacted_input_tokens, policy)
    compacted = compacted_user_prompt != user_prompt
    result = _result(
        policy=policy,
        compacted=compacted,
        trigger_reason=trigger_reason,
        original_input_tokens=original_input_tokens,
        compacted_input_tokens=compacted_input_tokens,
        original_cost=original_cost,
        compacted_cost=compacted_cost,
        retained_anchor_count=retained_anchor_count,
        original_user_prompt=user_prompt,
        compacted_user_prompt=compacted_user_prompt,
    )
    if compacted:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="llm_context_compaction_applied",
                module=logger.name,
                fields={"operation": operation, **asdict(result)},
            )
        )
        return replace(request, user_prompt=compacted_user_prompt), result
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_context_compaction_skipped",
            module=logger.name,
            fields={"operation": operation, **asdict(result)},
        )
    )
    return request, result


def _normalize_policy(value: object) -> LLMContextCompactionPolicy:
    if isinstance(value, LLMContextCompactionPolicy):
        return value
    return LLMContextCompactionPolicy(schema_version="1.0")


def _trigger_reason(
    *,
    policy: LLMContextCompactionPolicy,
    input_tokens: int,
    estimated_cost_usd: float,
) -> str:
    if not policy.enabled:
        return ""
    token_budget = policy.max_input_tokens
    cost_budget = policy.max_estimated_input_cost_usd
    token_exceeded = token_budget is not None and input_tokens > int(token_budget)
    cost_exceeded = cost_budget is not None and estimated_cost_usd > float(cost_budget)
    if token_exceeded and cost_exceeded:
        return "token_and_cost_budget_exceeded"
    if token_exceeded:
        return "token_budget_exceeded"
    if cost_exceeded:
        return "cost_budget_exceeded"
    return ""


def _estimate_request_cost(
    request: Any,
    input_tokens: int,
    policy: LLMContextCompactionPolicy,
) -> float:
    return estimate_cost_usd(
        str(getattr(request, "model", "") or ""),
        input_tokens,
        max(0, int(policy.expected_output_tokens or 0)),
        0,
        pricing=getattr(request, "model_pricing", None) or {},
    )


def _compact_user_prompt(
    *,
    user_prompt: str,
    system_prompt_tokens: int,
    max_input_tokens: int | None,
    max_anchor_lines: int,
    min_tail_lines: int,
) -> tuple[str, int]:
    lines = [line.rstrip() for line in str(user_prompt or "").splitlines()]
    if not lines:
        return "", 0
    token_budget = max(1, int(max_input_tokens or 0) - int(system_prompt_tokens or 0))
    anchor_lines = _dedupe_lines(
        [line for line in lines if _ANCHOR_RE.search(line) and line.strip()]
    )[:max_anchor_lines]
    anchor_keys = {line for line in anchor_lines}
    non_anchor_lines = [
        line for line in lines if line not in anchor_keys and line.strip()
    ]
    retained = _fit_lines(
        anchor_lines=anchor_lines,
        head_lines=non_anchor_lines[: max(1, min_tail_lines)],
        tail_lines=non_anchor_lines[-max(1, min_tail_lines) :]
        if non_anchor_lines
        else [],
        token_budget=token_budget,
    )
    if not retained:
        retained = [line for line in lines if line.strip()][:1]
    return "\n".join(retained), len(anchor_lines)


def _fit_lines(
    *,
    anchor_lines: list[str],
    head_lines: list[str],
    tail_lines: list[str],
    token_budget: int,
) -> list[str]:
    retained: list[str] = []
    seen: set[str] = set()

    def _try_add(line: str) -> None:
        token = line.strip()
        if not token or token in seen:
            return
        candidate = [*retained, token]
        if estimate_text_tokens("\n".join(candidate)) <= token_budget:
            retained.append(token)
            seen.add(token)

    for line in anchor_lines:
        _try_add(line)
    for line in reversed(tail_lines):
        _try_add(line)
    for line in head_lines:
        _try_add(line)
    return retained


def _dedupe_lines(lines: list[str]) -> list[str]:
    retained: list[str] = []
    seen: set[str] = set()
    for line in lines:
        token = line.strip()
        if token and token not in seen:
            retained.append(token)
            seen.add(token)
    return retained


def _result(
    *,
    policy: LLMContextCompactionPolicy,
    compacted: bool,
    trigger_reason: str,
    original_input_tokens: int,
    compacted_input_tokens: int,
    original_cost: float,
    compacted_cost: float,
    retained_anchor_count: int,
    original_user_prompt: str,
    compacted_user_prompt: str,
) -> LLMContextCompactionResult:
    avoided_tokens = max(0, int(original_input_tokens) - int(compacted_input_tokens))
    avoided_cost = max(0.0, float(original_cost) - float(compacted_cost))
    return LLMContextCompactionResult(
        schema_version="1.0",
        compacted=bool(compacted),
        strategy=str(policy.strategy or "anchor_preserving_head_tail"),
        trigger_reason=trigger_reason,
        original_input_tokens_est=int(original_input_tokens),
        compacted_input_tokens_est=int(compacted_input_tokens),
        avoided_input_tokens_est=avoided_tokens,
        estimated_original_cost_usd=round(float(original_cost), 6),
        estimated_compacted_cost_usd=round(float(compacted_cost), 6),
        estimated_avoided_cost_usd=round(avoided_cost, 6),
        retained_anchor_count=int(retained_anchor_count),
        original_user_chars=len(original_user_prompt),
        compacted_user_chars=len(compacted_user_prompt),
    )
