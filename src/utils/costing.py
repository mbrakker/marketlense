from __future__ import annotations

from typing import Dict


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int, tool_calls: int, pricing: Dict[str, dict]) -> float:
    model_pricing = pricing.get(model, {})
    input_rate = float(model_pricing.get("input_tokens_per_1k_usd", 0.0))
    output_rate = float(model_pricing.get("output_tokens_per_1k_usd", 0.0))
    tool_rate = float(model_pricing.get("tool_call_usd", 0.0))
    cost = (input_tokens / 1000.0) * input_rate
    cost += (output_tokens / 1000.0) * output_rate
    cost += tool_calls * tool_rate
    return round(cost, 6)
