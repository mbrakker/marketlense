from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Sequence

from src.contracts.config import AppSettings
from src.contracts.validation import ValidationIssue, ValidationRequest

LOGGER_NAME = "market_lense.validation_generator"
logger = logging.getLogger(LOGGER_NAME)

GROUNDING_HARD_FAILURES = {
    "hallucinated_entity_or_event",
    "misattributed_quote",
    "report_directive_misattribution",
    "unsupported_factual_claim",
}
STRICT_SECTION_PREFIXES = {"insights", "quotes", "key_data_insights", "claims_list"}
MIXED_SECTION_PREFIXES = {"summary", "executive_summary"}
SOFT_SECTION_PREFIXES = {"expert_comment", "linkedin_post"}
METRIC_ATTRIBUTION_RE = re.compile(
    r"\b(report\s+(states|shows|documents|finds|found|says|said|recommends|recommended|instructs|instructed))\b",
    re.IGNORECASE,
)
RETRIEVAL_FAILURE_HINTS = {
    "insufficient evidence",
    "retrieval failed",
    "unable to retrieve",
    "no relevant evidence",
    "context window missing",
}
QUOTE_PARAPHRASE_HINTS = {"paraphrase", "paraphrased", "summary", "adapted"}
WINDOW_TOKEN_TARGET = 420
WINDOW_TOKEN_MIN = 260
WINDOW_STRIDE = 150
RETRIEVE_TOP_K = 4
RETRIEVE_NEIGHBOR_RADIUS = 1
QUOTE_MIN_LEXICAL_OVERLAP = 0.86
QUOTE_MIN_PARAPHRASE_OVERLAP = 0.55
QUOTE_MIN_VERBATIM_SEMANTIC_OVERLAP = 0.72
MAGNITUDE_FACTORS: Dict[str, float] = {
    "k": 1_000.0,
    "thousand": 1_000.0,
    "m": 1_000_000.0,
    "mm": 1_000_000.0,
    "mn": 1_000_000.0,
    "million": 1_000_000.0,
    "b": 1_000_000_000.0,
    "bn": 1_000_000_000.0,
    "billion": 1_000_000_000.0,
    "tn": 1_000_000_000_000.0,
    "trillion": 1_000_000_000_000.0,
}


def s(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def ensure_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def ensure_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def prefix_rule_id(rule_id: str, message: str) -> str:
    clean_message = s(message).strip()
    prefix = f"[{rule_id}]"
    if clean_message.startswith(prefix):
        return clean_message
    return f"{prefix} {clean_message}".strip()


def issue(*, rule_id: str, message: str, severity: str, section: str) -> ValidationIssue:
    return ValidationIssue(
        schema_version="1.0",
        message=prefix_rule_id(rule_id, message),
        severity=severity if severity in {"error", "warning", "info"} else "warning",
        affected_section=section,
    )


def aggregate_severity(issues: Sequence[ValidationIssue]) -> str:
    if any(issue.severity == "error" for issue in issues):
        return "error"
    if any(issue.severity == "warning" for issue in issues):
        return "warning"
    return "pass"


def downgrade_issues_for_data_gap(
    issues: Sequence[ValidationIssue],
) -> List[ValidationIssue]:
    return [
        ValidationIssue(
            schema_version=issue.schema_version,
            message=issue.message,
            severity="warning" if issue.severity == "error" else issue.severity,
            affected_section=issue.affected_section,
        )
        for issue in issues
    ]


def format_confidence(value: float) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def has_data_gap(artifacts: dict) -> bool:
    if not isinstance(artifacts, dict):
        return False
    status = artifacts.get("source_status")
    if isinstance(status, dict):
        return bool(status.get("not_available"))
    return False


def validation_parallel_workers(settings: AppSettings) -> int:
    raw = getattr(settings, "report_worker_limit", 1)
    try:
        workers = int(raw)
    except (TypeError, ValueError):
        workers = 1
    if workers < 1:
        return 1
    return workers


def resolve_grounding_vector_store_mode(
    *, request: ValidationRequest, settings: AppSettings
) -> bool:
    return bool(request.vector_store_id) and bool(
        getattr(settings, "validation_grounding_use_vector_store", False)
    )


def grounding_retrieval_mode(use_vector_store: bool) -> str:
    return "vector_store" if use_vector_store else "chat_json"


def section_root(section: str) -> str:
    section_key = section.strip().lower()
    if section_key.startswith("expert_comment"):
        return "expert_comment"
    if section_key.startswith("linkedin_post"):
        return "linkedin_post"
    if section_key.startswith("quotes"):
        return "quotes"
    if section_key.startswith("insights"):
        return "insights"
    if section_key.startswith("summary"):
        return "summary"
    return section_key or "grounding"


def section_policy(section: str) -> str:
    section_key = section_root(section)
    if any(section_key.startswith(prefix) for prefix in STRICT_SECTION_PREFIXES):
        return "strict"
    if any(section_key.startswith(prefix) for prefix in SOFT_SECTION_PREFIXES):
        return "soft"
    if any(section_key.startswith(prefix) for prefix in MIXED_SECTION_PREFIXES):
        return "mixed"
    return "strict"


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        cleaned = str(value).strip()
        if not cleaned:
            return None
        cleaned = cleaned.rstrip(".").replace(",", "")
        return float(cleaned)
    except (TypeError, ValueError):
        return None

