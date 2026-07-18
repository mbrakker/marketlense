from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Dict


_VERSION_SUFFIX_RE = re.compile(r"-(?:19|20)\d{2}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class PricingResolution:
    """Deterministic pricing lookup result used by the accounting service."""

    status: str
    key: str
    rates: dict


def estimate_text_tokens(text: str) -> int:
    normalized = str(text or "")
    if not normalized:
        return 0
    # Deterministic heuristic for CI budgeting when a provider tokenizer is unavailable.
    return max(1, int(math.ceil(len(normalized) / 4.0)))


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    tool_calls: int,
    pricing: Dict[str, dict],
    cached_input_tokens: int | None = None,
) -> float:
    model_pricing = resolve_model_pricing(model, pricing).rates
    input_rate = float(model_pricing.get("input_tokens_per_1k_usd", 0.0))
    cached_input_rate = float(
        model_pricing.get("cached_input_tokens_per_1k_usd", input_rate)
    )
    output_rate = float(model_pricing.get("output_tokens_per_1k_usd", 0.0))
    tool_rate = float(model_pricing.get("tool_call_usd", 0.0))
    billed_input_tokens = max(0, int(input_tokens or 0))
    cached_tokens = min(billed_input_tokens, max(0, int(cached_input_tokens or 0)))
    cost = ((billed_input_tokens - cached_tokens) / 1000.0) * input_rate
    cost += (cached_tokens / 1000.0) * cached_input_rate
    cost += (max(0, int(output_tokens or 0)) / 1000.0) * output_rate
    cost += max(0, int(tool_calls or 0)) * tool_rate
    return round(cost, 6)


def resolve_model_pricing(model: str, pricing: Dict[str, dict]) -> PricingResolution:
    if not pricing:
        return PricingResolution(status="missing", key="", rates={})
    normalized = str(model or "").strip()
    if not normalized:
        return PricingResolution(status="missing", key="", rates={})
    if normalized in pricing:
        return _pricing_resolution("matched", normalized, pricing[normalized])

    normalized_lower = normalized.lower()
    lower_index = {
        str(key).strip().lower(): (str(key), value) for key, value in pricing.items()
    }
    if normalized_lower in lower_index:
        key, rates = lower_index[normalized_lower]
        return _pricing_resolution("alias_matched", key, rates)

    for candidate in _model_alias_candidates(normalized):
        if candidate in pricing:
            return _pricing_resolution("alias_matched", candidate, pricing[candidate])
        lower_candidate = candidate.lower()
        if lower_candidate in lower_index:
            key, rates = lower_index[lower_candidate]
            return _pricing_resolution("alias_matched", key, rates)
    return PricingResolution(status="missing", key="", rates={})


def _pricing_resolution(status: str, key: str, rates: object) -> PricingResolution:
    if not isinstance(rates, dict):
        return PricingResolution(status="invalid", key=key, rates={})
    disposition = str(rates.get("disposition") or "priced").strip().lower()
    if disposition in {"block", "hold"}:
        return PricingResolution(status="held", key=key, rates={})
    valid_until = str(rates.get("valid_until") or "").strip()
    if valid_until:
        try:
            if date.fromisoformat(valid_until) < date.today():
                return PricingResolution(status="stale", key=key, rates={})
        except ValueError:
            return PricingResolution(status="invalid", key=key, rates={})
    required = (
        "input_tokens_per_1k_usd",
        "output_tokens_per_1k_usd",
        "tool_call_usd",
    )
    try:
        normalized = {name: float(rates.get(name, 0.0)) for name in required}
        if "cached_input_tokens_per_1k_usd" in rates:
            normalized["cached_input_tokens_per_1k_usd"] = float(
                rates["cached_input_tokens_per_1k_usd"]
            )
    except (TypeError, ValueError):
        return PricingResolution(status="invalid", key=key, rates={})
    if any(value < 0.0 for value in normalized.values()):
        return PricingResolution(status="invalid", key=key, rates={})
    return PricingResolution(status=status, key=key, rates=normalized)


def _model_alias_candidates(model: str) -> tuple[str, ...]:
    raw = str(model or "").strip()
    if not raw:
        return ()
    candidates: list[str] = []

    def _add(value: str) -> None:
        token = value.strip()
        if token and token not in candidates:
            candidates.append(token)

    _add(raw)
    compact = raw.replace("openai/", "").replace("openai:", "")
    _add(compact)
    if "/" in raw:
        _add(raw.split("/")[-1])
    if ":" in raw:
        _add(raw.split(":")[-1])
    versionless = _VERSION_SUFFIX_RE.sub("", compact)
    _add(versionless)
    if "/" in compact:
        _add(compact.split("/")[-1])
    if ":" in compact:
        _add(compact.split(":")[-1])
    versionless_tail = _VERSION_SUFFIX_RE.sub("", raw.split("/")[-1].split(":")[-1])
    _add(versionless_tail)
    return tuple(candidates)
