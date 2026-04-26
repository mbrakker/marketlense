from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from src.contracts.validation import ValidationIssue

from .evidence import contains_token, metric_value_supported, retrieve_evidence_windows
from .models import EvidenceWindow, SemanticSupport, ValidationRuntime
from .shared import RETRIEVE_TOP_K, format_confidence, issue, s

RULE_ID = "metrics"


def run_metric_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    return validate_insight_metrics(
        insights=runtime.prepared.insights,
        evidence_map=runtime.prepared.evidence_map,
        semantic_support=runtime.semantic_outcome.metric_support,
        evidence_windows=runtime.prepared.evidence_windows,
    )


def validate_insight_metrics(
    insights: Sequence[dict],
    evidence_map: Dict[str, str],
    semantic_support: Optional[Dict[str, SemanticSupport]] = None,
    evidence_windows: Optional[Sequence[EvidenceWindow]] = None,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    windows = list(evidence_windows or [])
    for idx, insight in enumerate(insights):
        if not isinstance(insight, dict):
            continue
        raw_metric = insight.get("metric")
        metric: dict[str, Any] = raw_metric if isinstance(raw_metric, dict) else {}
        evidence_id = s(insight.get("evidence_id"))
        evidence_text = s(insight.get("evidence")) or evidence_map.get(evidence_id, "")
        label = s(insight.get("id") or f"insight_{idx + 1}")
        metric_ctx_text = " ".join(
            part
            for part in (
                s(insight.get("text")),
                s(metric.get("value")),
                s(metric.get("unit")),
                s(metric.get("timeframe")),
                s(metric.get("trend")),
            )
            if part
        )
        retrieved = retrieve_evidence_windows(metric_ctx_text, windows, top_k=RETRIEVE_TOP_K)
        retrieved_blob = " ".join(window.text for window in retrieved)
        evidence_blob = " ".join(
            part for part in (evidence_text, retrieved_blob) if part
        )
        if metric and not evidence_blob.strip():
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=f"Missing evidence snippet for metric on {label}",
                    severity="error",
                    section=f"insights:{label}",
                )
            )
            continue
        value = s(metric.get("value")).strip()
        unit = s(metric.get("unit")).strip()
        timeframe = s(metric.get("timeframe")).strip()
        semantic_entry = (semantic_support or {}).get(label)
        semantic_confidence = semantic_entry.confidence if semantic_entry else 0.0
        value_supported_exact = metric_value_supported(
            value, evidence_blob, unit=unit, section=f"insights:{label}"
        )
        value_supported_semantic = semantic_entry.supported if semantic_entry else False
        if value and not (value_supported_exact or value_supported_semantic):
            reason = (
                f" ({semantic_entry.reason})"
                if semantic_entry and semantic_entry.reason
                else ""
            )
            severity = (
                "error"
                if not semantic_entry or semantic_confidence >= 0.6
                else "warning"
            )
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=f"Metric value '{value}' not found in evidence for {label}{reason}",
                    severity=severity,
                    section=f"insights:{label}",
                )
            )
        if value and not value_supported_exact and value_supported_semantic:
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=(
                        "Metric value "
                        f"'{value}' not verbatim but semantically supported "
                        f"(confidence={format_confidence(semantic_confidence)}) for {label}"
                    ),
                    severity="info",
                    section=f"insights:{label}",
                )
            )
        if timeframe and not contains_token(timeframe, evidence_blob):
            if semantic_entry and semantic_entry.supported:
                issues.append(
                    issue(
                        rule_id=RULE_ID,
                        message=(
                            f"Metric timeframe '{timeframe}' not verbatim but "
                            f"semantically supported (confidence={format_confidence(semantic_confidence)}) "
                            f"for {label}"
                        ),
                        severity="info",
                        section=f"insights:{label}",
                    )
                )
            else:
                issues.append(
                    issue(
                        rule_id=RULE_ID,
                        message=f"Metric timeframe '{timeframe}' not present in evidence for {label}",
                        severity="warning",
                        section=f"insights:{label}",
                    )
                )
    return issues
