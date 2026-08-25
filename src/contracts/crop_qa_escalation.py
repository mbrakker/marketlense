from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CropQaEscalationPolicy:
    schema_version: str = field(
        default="1.0",
        metadata={"doc": "Crop QA escalation policy schema version."},
    )
    enabled: bool = field(
        default=False,
        metadata={"doc": "Whether model-backed crop QA escalation may run."},
    )
    quality_profile: str = field(
        default="publication_strict",
        metadata={"doc": "Deterministic crop QA profile eligible for escalation."},
    )
    low_confidence_min_score: float = field(
        default=0.0,
        metadata={"doc": "Inclusive lower deterministic crop QA score for escalation."},
    )
    low_confidence_max_score: float = field(
        default=82.0,
        metadata={"doc": "Inclusive upper deterministic crop QA score for escalation."},
    )
    high_risk_defects: list[str] = field(
        default_factory=lambda: [
            "chart_axis_clipped",
            "table_boundary_clipped",
            "visual_card_boundary_clipped",
            "neighbor_contamination",
        ],
        metadata={"doc": "Deterministic defect labels that make a crop escalation eligible."},
    )
    max_escalations: int = field(
        default=2,
        metadata={"doc": "Maximum model-backed crop QA calls allowed for this batch."},
    )
    max_repairs: int = field(
        default=1,
        metadata={"doc": "Maximum repair recommendations allowed for this batch."},
    )
    model: str = field(
        default="gpt-5.6-luna",
        metadata={"doc": "Model used for image-backed crop QA escalation."},
    )
    temperature: float = field(
        default=0.0,
        metadata={"doc": "Sampling temperature for crop QA escalation."},
    )
    seed: int | None = field(
        default=None,
        metadata={"doc": "Optional seed for provider calls when supported."},
    )
    timeout_seconds: float | None = field(
        default=None,
        metadata={"doc": "Optional provider request timeout in seconds."},
    )
    api_key: str = field(
        default="",
        metadata={"doc": "Resolved OpenAI API key; empty only when no model call is made."},
    )
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={"doc": "Cost ledger JSONL path for model-backed QA accounting."},
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={"doc": "Daily cost rollup path for model-backed QA accounting."},
    )
    model_pricing: dict = field(
        default_factory=dict,
        metadata={"doc": "Per-model pricing table for cost estimation."},
    )
    prompt_namespace: str = field(
        default="crop_qa_escalation/publication_strict",
        metadata={"doc": "Prompt namespace used for model-backed crop QA escalation."},
    )


@dataclass(frozen=True)
class CropQaEscalationRequest:
    schema_version: str = field(
        metadata={"doc": "Crop QA escalation request schema version."}
    )
    output_dir: str = field(
        metadata={"doc": "Output directory for the crop batch being reviewed."}
    )
    crops: list[dict] = field(
        metadata={"doc": "Crop dictionaries containing image and QA sidecar paths."}
    )
    policy: CropQaEscalationPolicy = field(
        metadata={"doc": "Model escalation policy for the crop batch."}
    )


@dataclass(frozen=True)
class CropQaEscalationDecision:
    schema_version: str = field(metadata={"doc": "Crop QA escalation decision schema version."})
    candidate_id: str = field(metadata={"doc": "Stable crop candidate identifier."})
    image_path: str = field(metadata={"doc": "Image crop path evaluated by deterministic QA."})
    qa_sidecar_path: str = field(metadata={"doc": "Existing deterministic QA sidecar path."})
    deterministic_score: float | None = field(metadata={"doc": "Deterministic QA score from the sidecar."})
    deterministic_defects: list[str] = field(metadata={"doc": "Deterministic defect labels from the sidecar."})
    decision: str = field(metadata={"doc": "Decision: not_escalated, accept, repair, or reject."})
    reason: str = field(metadata={"doc": "Stable machine-readable decision reason."})
    model_confidence: float | None = field(metadata={"doc": "Model confidence, when provided."})
    defects: list[str] = field(metadata={"doc": "Model-backed defect labels, when escalated."})
    repair_instruction: str = field(metadata={"doc": "Bounded repair instruction, when decision is repair."})
    provider_request_id: str = field(metadata={"doc": "Provider request ID for model-backed decisions."})
    input_tokens: int | None = field(metadata={"doc": "Provider input tokens, if reported."})
    output_tokens: int | None = field(metadata={"doc": "Provider output tokens, if reported."})
    total_tokens: int | None = field(metadata={"doc": "Provider total tokens, if reported."})
    estimated_cost_usd: float = field(metadata={"doc": "Estimated provider cost for the decision."})


@dataclass(frozen=True)
class CropQaEscalationResponse:
    schema_version: str = field(metadata={"doc": "Crop QA escalation response schema version."})
    decisions: list[CropQaEscalationDecision] = field(
        metadata={"doc": "Per-crop escalation decisions in input order."}
    )
    eligible_count: int = field(metadata={"doc": "Crops eligible for model-backed QA."})
    model_call_count: int = field(metadata={"doc": "Model-backed QA calls performed."})
    repair_count: int = field(metadata={"doc": "Repair decisions returned by the model."})
    reject_count: int = field(metadata={"doc": "Reject decisions returned by the model."})
    escalation_rate: float = field(metadata={"doc": "Model calls divided by candidate count."})


__all__ = [
    "CropQaEscalationDecision",
    "CropQaEscalationPolicy",
    "CropQaEscalationRequest",
    "CropQaEscalationResponse",
]
