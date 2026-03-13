from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.contracts.config import AppSettings
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationIssue, ValidationRequest


@dataclass(frozen=True)
class SemanticSupport:
    supported: bool
    confidence: float
    reason: str


@dataclass(frozen=True)
class SemanticCheckOutcome:
    metric_support: Dict[str, SemanticSupport]
    quote_support: Dict[str, SemanticSupport]
    issues: List[ValidationIssue]


@dataclass(frozen=True)
class EvidenceWindow:
    idx: int
    text: str
    normalized: str
    tokens: set[str]
    quantities: List[Any]


@dataclass(frozen=True)
class ValidationPreparedInputs:
    insights: List[dict]
    quotes: List[dict]
    pdf_text: str
    evidence_texts: List[str]
    evidence_map: Dict[str, str]
    evidence_windows: List[EvidenceWindow]
    grounding_use_vector_store: bool
    grounding_retrieval_mode: str


@dataclass
class ValidationRuntime:
    request: ValidationRequest
    settings: AppSettings
    ctx: RunContext
    prompt_client: Any
    openai_client: Any
    prepared: ValidationPreparedInputs
    semantic_outcome: SemanticCheckOutcome = field(
        default_factory=lambda: SemanticCheckOutcome(
            metric_support={}, quote_support={}, issues=[]
        )
    )
    issues_by_rule: Dict[str, List[ValidationIssue]] = field(default_factory=dict)
