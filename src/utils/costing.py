from __future__ import annotations

import math
import re
from typing import Dict


_VERSION_SUFFIX_RE = re.compile(r"-(?:19|20)\d{2}-\d{2}-\d{2}$")


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
) -> float:
    model_pricing = _resolve_model_pricing(model, pricing)
    input_rate = float(model_pricing.get("input_tokens_per_1k_usd", 0.0))
    output_rate = float(model_pricing.get("output_tokens_per_1k_usd", 0.0))
    tool_rate = float(model_pricing.get("tool_call_usd", 0.0))
    cost = (max(0, int(input_tokens or 0)) / 1000.0) * input_rate
    cost += (max(0, int(output_tokens or 0)) / 1000.0) * output_rate
    cost += max(0, int(tool_calls or 0)) * tool_rate
    return round(cost, 6)


def _resolve_model_pricing(model: str, pricing: Dict[str, dict]) -> dict:
    if not pricing:
        return {}
    normalized = str(model or "").strip()
    if not normalized:
        return {}
    if normalized in pricing:
        return pricing[normalized]

    normalized_lower = normalized.lower()
    lower_index = {str(key).strip().lower(): value for key, value in pricing.items()}
    if normalized_lower in lower_index:
        return lower_index[normalized_lower]

    for candidate in _model_alias_candidates(normalized):
        if candidate in pricing:
            return pricing[candidate]
        lower_candidate = candidate.lower()
        if lower_candidate in lower_index:
            return lower_index[lower_candidate]
    return {}


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
