from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import logging
import re
import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.contracts.config import AppSettings
from src.contracts.files import ReadTextRequest
from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.report_analysis import AnalysisPackPathRequest, AnalysisStorePackRequest
from src.contracts.report_models import ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.validation import ValidationIssue, ValidationReport, ValidationRequest
from src.services import file_service, openai_service, prompt_service, report_analysis_store_service
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event, new_run_context
from src.services.schema_validator_service import validate_schema
from src.utils.model_resolver import resolve_model
from src.utils.cache_utils import sha256_json
from src.utils.quantity import (
    Quantity,
    extract_quantities,
    quantities_match,
    quantity_has_metric_cues,
    should_ground_quantity,
)
from src.utils.text_normalization import normalize_for_lookup, normalize_text

logger = logging.getLogger("market_lense.validation_generator")

_SEVERITY_ORDER = ("error", "warning", "info", "pass")
_GROUNDING_HARD_FAILURES = {
    "hallucinated_entity_or_event",
    "misattributed_quote",
    "report_directive_misattribution",
    "unsupported_factual_claim",
}
_ALLOWED_INTERPRETIVE_SECTIONS = {"expert_comment", "linkedin_post"}
_STRICT_SECTION_PREFIXES = {"insights", "quotes", "key_data_insights", "claims_list"}
_MIXED_SECTION_PREFIXES = {"summary", "executive_summary"}
_SOFT_SECTION_PREFIXES = {"expert_comment", "linkedin_post"}
_METRIC_ATTRIBUTION_RE = re.compile(
    r"\b(report\s+(states|shows|documents|finds|found|says|said|recommends|recommended|instructs|instructed))\b",
    re.IGNORECASE,
)
_RETRIEVAL_FAILURE_HINTS = {
    "insufficient evidence",
    "retrieval failed",
    "unable to retrieve",
    "no relevant evidence",
    "context window missing",
}
_QUOTE_PARAPHRASE_HINTS = {"paraphrase", "paraphrased", "summary", "adapted"}
_WINDOW_TOKEN_TARGET = 420
_WINDOW_TOKEN_MIN = 260
_WINDOW_STRIDE = 150
_RETRIEVE_TOP_K = 4
_RETRIEVE_NEIGHBOR_RADIUS = 1
_QUOTE_MIN_LEXICAL_OVERLAP = 0.86
_QUOTE_MIN_PARAPHRASE_OVERLAP = 0.55
_QUOTE_MIN_VERBATIM_SEMANTIC_OVERLAP = 0.72
_MAGNITUDE_FACTORS: Dict[str, float] = {
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


@dataclass(frozen=True)
class _SemanticSupport:
    supported: bool
    confidence: float
    reason: str


@dataclass(frozen=True)
class _SemanticCheckOutcome:
    metric_support: Dict[str, _SemanticSupport]
    quote_support: Dict[str, _SemanticSupport]
    issues: List[ValidationIssue]


@dataclass(frozen=True)
class _EvidenceWindow:
    idx: int
    text: str
    normalized: str
    tokens: set[str]
    quantities: List[Quantity]


def validate_report(
    request: ValidationRequest,
    settings: AppSettings,
    ctx: Optional[RunContext] = None,
    *,
    prompt_client=prompt_service,
    openai_client=openai_service,
    analysis_store=report_analysis_store_service,
    pack_name: str = "validation",
    report_name: Optional[str] = None,
    md5: Optional[str] = None,
) -> ValidationReport:
    ctx = ctx or new_run_context(task_id=f"validation:{request.report_id}")
    logger.info(log_event(
        ctx,
        role="generator",
        event="validation_start",
        module=logger.name,
        fields={
            "report_id": request.report_id,
            "has_artifacts": bool(request.artifacts),
            "has_evidence_packs": bool(request.evidence_packs),
            "vector_store_id": request.vector_store_id or "",
        },
    ))
    grounding_use_vector_store = _resolve_grounding_vector_store_mode(request=request, settings=settings)
    grounding_retrieval_mode = _grounding_retrieval_mode(grounding_use_vector_store)
    cache_key = ""
    cache_meta = None
    if md5:
        cache_meta = _validation_cache_meta(
            request=request,
            settings=settings,
            prompt_client=prompt_client,
            ctx=ctx,
            md5=md5,
            grounding_retrieval_mode=grounding_retrieval_mode,
        )
        cache_key = sha256_json(cache_meta)
        cached = _load_cached_validation(
            output_dir=settings.output_dir,
            report_id=request.report_id,
            pack_name=pack_name,
            report_name=report_name,
            cache_key=cache_key,
            ctx=ctx,
            analysis_store=analysis_store,
        )
        if cached is not None:
            logger.info(log_event(
                ctx,
                role="generator",
                event="validation_cache_hit",
                module=logger.name,
                fields={"report_id": request.report_id, "pack_name": pack_name},
            ))
            return cached
        logger.info(log_event(
            ctx,
            role="generator",
            event="validation_cache_miss",
            module=logger.name,
            fields={"report_id": request.report_id, "pack_name": pack_name},
        ))

    issues: List[ValidationIssue] = []
    insights = _ensure_list(request.artifacts.get("insights_final") if isinstance(request.artifacts, dict) else [])
    quotes = _extract_quotes(request, insights)
    pdf_text = _load_pdf_text_from_cache(settings.cache_dir, md5, ctx)
    evidence_texts, evidence_map = _collect_evidence_texts(
        request.artifacts,
        request.evidence_packs,
        pdf_text=pdf_text,
    )
    window_sources = list(evidence_texts)
    if pdf_text:
        window_sources.append(pdf_text)
    evidence_windows = _build_evidence_windows(window_sources)
    logger.info(log_event(
        ctx,
        role="generator",
        event="validation_evidence_index_ready",
        module=logger.name,
        fields={
            "report_id": request.report_id,
            "evidence_snippets": len(evidence_texts),
            "windows": len(evidence_windows),
            "pdf_text_loaded": bool(pdf_text),
        },
    ))
    parallel_workers = _validation_parallel_workers(settings)
    semantic_outcome: _SemanticCheckOutcome
    metric_issues: List[ValidationIssue] = []
    quote_issues: List[ValidationIssue] = []
    number_issues: List[ValidationIssue] = []
    grounding_issues: List[ValidationIssue] = []
    if parallel_workers > 1:
        logger.info(log_event(
            ctx,
            role="generator",
            event="validation_parallel_start",
            module=logger.name,
            fields={
                "report_id": request.report_id,
                "workers": parallel_workers,
                "tasks": ["semantic", "grounding", "metrics", "quotes", "numbers"],
            },
        ))
        with ThreadPoolExecutor(max_workers=min(parallel_workers, 3)) as executor:
            semantic_future = executor.submit(
                _run_semantic_validation,
                insights,
                quotes,
                evidence_texts,
                settings,
                prompt_client,
                openai_client,
                ctx,
            )
            grounding_future = executor.submit(
                _run_grounding_check,
                request,
                settings,
                grounding_use_vector_store,
                evidence_texts,
                evidence_windows,
                prompt_client,
                openai_client,
                ctx,
            )
            number_future = executor.submit(
                _validate_new_numbers,
                request.artifacts,
                insights,
                request.report,
                evidence_texts,
                evidence_windows,
            )
            try:
                semantic_outcome = semantic_future.result()
            except Exception:
                grounding_future.cancel()
                number_future.cancel()
                raise
            metric_future = executor.submit(
                _validate_insight_metrics,
                insights,
                evidence_map,
                semantic_outcome.metric_support,
                evidence_windows,
            )
            quote_future = executor.submit(
                _validate_quotes,
                quotes,
                evidence_texts,
                semantic_outcome.quote_support,
                evidence_windows,
            )
            metric_issues = metric_future.result()
            quote_issues = quote_future.result()
            number_issues = number_future.result()
            grounding_issues = grounding_future.result()
        logger.info(log_event(
            ctx,
            role="generator",
            event="validation_parallel_complete",
            module=logger.name,
            fields={
                "report_id": request.report_id,
                "workers": parallel_workers,
                "semantic_issues": len(semantic_outcome.issues),
                "metric_issues": len(metric_issues),
                "quote_issues": len(quote_issues),
                "number_issues": len(number_issues),
                "grounding_issues": len(grounding_issues),
            },
        ))
    else:
        semantic_outcome = _run_semantic_validation(
            insights,
            quotes,
            evidence_texts,
            settings,
            prompt_client,
            openai_client,
            ctx,
        )
        metric_issues = _validate_insight_metrics(insights, evidence_map, semantic_outcome.metric_support, evidence_windows)
        quote_issues = _validate_quotes(quotes, evidence_texts, semantic_outcome.quote_support, evidence_windows)
        number_issues = _validate_new_numbers(request.artifacts, insights, request.report, evidence_texts, evidence_windows)
        grounding_issues = _run_grounding_check(
            request,
            settings,
            grounding_use_vector_store,
            evidence_texts,
            evidence_windows,
            prompt_client,
            openai_client,
            ctx,
        )

    # Preserve deterministic issue ordering even when checks execute in parallel.
    issues.extend(semantic_outcome.issues)
    issues.extend(metric_issues)
    issues.extend(quote_issues)
    issues.extend(number_issues)
    issues.extend(grounding_issues)

    data_gap = _has_data_gap(request.artifacts)
    if data_gap and getattr(settings, "validation_data_gap_policy", "warn") == "warn":
        issues = [
            ValidationIssue(
                schema_version=issue.schema_version,
                message=issue.message,
                severity="warning" if issue.severity == "error" else issue.severity,
                affected_section=issue.affected_section,
            )
            for issue in issues
        ]
    severity = _aggregate_severity(issues)
    status = "pass" if severity != "error" else "fail"
    report = ValidationReport(schema_version="1.1", status=status, issues=issues, severity=severity)

    try:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0",
                payload=report.to_dict(),
                schema_name="validation_report",
            ),
            ctx,
        )
    except AppError as exc:
        logger.info(log_event(
            ctx,
            role="generator",
            event="validation_schema_failed",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))
        raise

    payload = report.to_dict()
    if cache_meta:
        payload["_cache"] = {**cache_meta, "key": cache_key}
    stored_path = _store_pack(
        analysis_store=analysis_store,
        output_dir=settings.output_dir,
        report_id=request.report_id,
        pack_name=pack_name,
        payload=payload,
        ctx=ctx,
        report_name=report_name,
    )
    if cache_meta:
        logger.info(log_event(
            ctx,
            role="generator",
            event="validation_cache_written",
            module=logger.name,
            fields={"report_id": request.report_id, "pack_name": pack_name},
        ))
    report = ValidationReport(
        schema_version=report.schema_version,
        status=report.status,
        issues=report.issues,
        severity=report.severity,
        source_path=stored_path,
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="validation_complete",
        module=logger.name,
        fields={"report_id": request.report_id, "status": status, "severity": severity, "issue_count": len(issues), "path": stored_path},
    ))
    return report


def _validate_insight_metrics(
    insights: Sequence[dict],
    evidence_map: Dict[str, str],
    semantic_support: Optional[Dict[str, _SemanticSupport]] = None,
    evidence_windows: Optional[Sequence[_EvidenceWindow]] = None,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    windows = list(evidence_windows or [])
    for idx, insight in enumerate(insights):
        if not isinstance(insight, dict):
            continue
        metric = insight.get("metric") if isinstance(insight.get("metric"), dict) else {}
        evidence_id = _s(insight.get("evidence_id"))
        evidence_text = _s(insight.get("evidence")) or evidence_map.get(evidence_id, "")
        label = _s(insight.get("id") or f"insight_{idx + 1}")
        metric_ctx_text = " ".join(
            part for part in (
                _s(insight.get("text")),
                _s(metric.get("value")),
                _s(metric.get("unit")),
                _s(metric.get("timeframe")),
                _s(metric.get("trend")),
            )
            if part
        )
        retrieved = _retrieve_evidence_windows(metric_ctx_text, windows, top_k=_RETRIEVE_TOP_K)
        retrieved_blob = " ".join(window.text for window in retrieved)
        evidence_blob = " ".join(part for part in (evidence_text, retrieved_blob) if part)
        if metric and not evidence_blob.strip():
            issues.append(_issue(
                message=f"Missing evidence snippet for metric on {label}",
                severity="error",
                section=f"insights:{label}",
            ))
            continue
        value = _s(metric.get("value")).strip()
        unit = _s(metric.get("unit")).strip()
        timeframe = _s(metric.get("timeframe")).strip()
        semantic_entry = (semantic_support or {}).get(label)
        value_supported_exact = _metric_value_supported(value, evidence_blob, unit=unit, section=f"insights:{label}")
        value_supported_semantic = semantic_entry.supported if semantic_entry else False
        if value and not (value_supported_exact or value_supported_semantic):
            reason = f" ({semantic_entry.reason})" if semantic_entry and semantic_entry.reason else ""
            severity = "error" if not semantic_entry or semantic_entry.confidence >= 0.6 else "warning"
            issues.append(_issue(
                message=f"Metric value '{value}' not found in evidence for {label}{reason}",
                severity=severity,
                section=f"insights:{label}",
            ))
        if value and not value_supported_exact and value_supported_semantic:
            issues.append(_issue(
                message=f"Metric value '{value}' not verbatim but semantically supported (confidence={_format_confidence(semantic_entry.confidence)}) for {label}",
                severity="info",
                section=f"insights:{label}",
            ))
        if timeframe and not _contains_token(timeframe, evidence_blob):
            if semantic_entry and semantic_entry.supported:
                issues.append(_issue(
                    message=f"Metric timeframe '{timeframe}' not verbatim but semantically supported (confidence={_format_confidence(semantic_entry.confidence)}) for {label}",
                    severity="info",
                    section=f"insights:{label}",
                ))
            else:
                issues.append(_issue(
                    message=f"Metric timeframe '{timeframe}' not present in evidence for {label}",
                    severity="warning",
                    section=f"insights:{label}",
                ))
    return issues


def _validate_quotes(
    quotes: Sequence[dict],
    evidence_texts: Sequence[str],
    semantic_support: Optional[Dict[str, _SemanticSupport]] = None,
    evidence_windows: Optional[Sequence[_EvidenceWindow]] = None,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not quotes:
        return issues
    windows = list(evidence_windows or [])
    for idx, quote in enumerate(quotes):
        if not isinstance(quote, dict):
            continue
        text = _s(quote.get("text"))
        if not text:
            continue
        label = _quote_label(quote, idx)
        quote_paraphrase = _quote_is_paraphrase(quote)
        semantic_entry = (semantic_support or {}).get(label)
        retrieved = _retrieve_evidence_windows(text, windows, top_k=_RETRIEVE_TOP_K)
        candidate_evidence = list(evidence_texts) + [window.text for window in retrieved]
        verbatim_match = any(_quote_near_verbatim(text, evidence) for evidence in candidate_evidence)
        best_overlap = 0.0
        if candidate_evidence:
            best_overlap = max(_lexical_overlap(text, evidence) for evidence in candidate_evidence)
        if verbatim_match:
            continue
        semantic_supported = bool(semantic_entry and semantic_entry.supported)
        if quote_paraphrase:
            if semantic_supported or best_overlap >= _QUOTE_MIN_PARAPHRASE_OVERLAP:
                issues.append(_issue(
                    message=f"Quote paraphrased but semantically supported (confidence={_format_confidence((semantic_entry.confidence if semantic_entry else 0.0))}): {text[:120]}",
                    severity="info",
                    section=f"quotes:{label}",
                ))
                continue
            issues.append(_issue(
                message=f"Quote paraphrase not supported by evidence: {text[:120]}",
                severity="warning",
                section=f"quotes:{label}",
            ))
            continue
        if semantic_supported and best_overlap >= _QUOTE_MIN_VERBATIM_SEMANTIC_OVERLAP:
            issues.append(_issue(
                message=f"Quote semantically supported with lexical overlap (confidence={_format_confidence(semantic_entry.confidence)}): {text[:120]}",
                severity="info",
                section=f"quotes:{label}",
            ))
        else:
            reason = f" ({semantic_entry.reason})" if semantic_entry and semantic_entry.reason else ""
            severity = "error" if not semantic_entry or semantic_entry.confidence >= 0.6 else "warning"
            issues.append(_issue(
                message=f"Quote not verbatim in evidence{reason}: {text[:120]}",
                severity=severity,
                section=f"quotes:{label}",
            ))
    return issues


def _validate_new_numbers(
    artifacts: dict,
    insights: Sequence[dict],
    report: ReportPayload,
    evidence_texts: Sequence[str],
    evidence_windows: Optional[Sequence[_EvidenceWindow]] = None,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    allowed_quantities = _collect_allowed_quantities(insights, report, artifacts, evidence_texts)
    windows = list(evidence_windows or [])
    summary = artifacts.get("summary") if isinstance(artifacts, dict) and isinstance(artifacts.get("summary"), dict) else {}
    section_texts: List[Tuple[str, str]] = [
        (_s(artifacts.get("expert_comment") if isinstance(artifacts, dict) else ""), "expert_comment"),
        (_s(artifacts.get("linkedin_post") if isinstance(artifacts, dict) else ""), "linkedin_post"),
        (_s(summary.get("executive_summary")), "summary.executive_summary"),
    ]
    seen: set[Tuple[str, str, str]] = set()
    for text, section in section_texts:
        if not text:
            continue
        policy = _section_policy(section)
        for sentence in _split_sentences(text):
            sentence_quantities = extract_quantities(sentence)
            if not sentence_quantities:
                continue
            retrieved = _retrieve_evidence_windows(sentence, windows, top_k=_RETRIEVE_TOP_K)
            local_evidence_quantities = list(allowed_quantities)
            for window in retrieved:
                local_evidence_quantities.extend(window.quantities)
            for quantity in sentence_quantities:
                if not should_ground_quantity(quantity, sentence, section_policy=policy, strict_section=policy == "strict"):
                    continue
                if _quantity_supported(quantity, local_evidence_quantities, numeric_only=True):
                    continue
                severity = _unsupported_quantity_severity(policy=policy, quantity=quantity, sentence=sentence)
                key = (section, quantity.raw or str(quantity.value), severity)
                if key in seen:
                    continue
                seen.add(key)
                issues.append(_issue(
                    message=f"Number {quantity.value} not present in report or evidence",
                    severity=severity,
                    section=section,
                ))
    return issues


def _run_semantic_validation(
    insights: Sequence[dict],
    quotes: Sequence[dict],
    evidence_texts: Sequence[str],
    settings: AppSettings,
    prompt_client,
    openai_client,
    ctx: RunContext,
) -> _SemanticCheckOutcome:
    if not evidence_texts or (not insights and not quotes):
        return _SemanticCheckOutcome(metric_support={}, quote_support={}, issues=[])
    semantic_ctx = child_context(ctx, task_id=f"{ctx.task_id}:semantic")
    logger.info(log_event(
        semantic_ctx,
        role="generator",
        event="semantic_validation_start",
        module=logger.name,
        fields={
            "insight_count": len(insights),
            "quote_count": len(quotes),
            "evidence_count": len(evidence_texts),
        },
    ))
    prompt_namespace = "report_vs/validate/semantic"
    prompt_set = prompt_client.load_prompt_set(PromptLoadRequest(schema_version="1.0", namespace=prompt_namespace), semantic_ctx)
    logger.info(log_event(
        semantic_ctx,
        role="generator",
        event="prompt_selected",
        module=logger.name,
        fields={
            "namespace": prompt_namespace,
            "system_path": prompt_set.system.path,
            "system_sha256": prompt_set.system.sha256,
            "user_path": prompt_set.user.path,
            "user_sha256": prompt_set.user.sha256,
        },
    ))
    payload = _semantic_payload(insights, quotes)
    prompt_vars = {
        "metrics_json": json.dumps(payload["metrics"], ensure_ascii=False),
        "quotes_json": json.dumps(payload["quotes"], ensure_ascii=False),
        "evidence_json": json.dumps(list(evidence_texts), ensure_ascii=False),
    }
    system_render = prompt_client.render_prompt(PromptRenderRequest(schema_version="1.0", template=prompt_set.system, variables=prompt_vars), semantic_ctx)
    user_render = prompt_client.render_prompt(PromptRenderRequest(schema_version="1.0", template=prompt_set.user, variables=prompt_vars), semantic_ctx)
    logger.info(log_event(
        semantic_ctx,
        role="generator",
        event="prompt_rendered",
        module=logger.name,
        fields={
            "system_prompt": system_render.text,
            "user_prompt": user_render.text,
        },
    ))
    resolved_model = resolve_model(prompt_namespace, getattr(settings, "openai_models", {}), settings.openai_model)
    evidence_hash = hashlib.sha256("||".join(evidence_texts).encode("utf-8")).hexdigest()
    metrics_hash = hashlib.sha256(json.dumps(payload["metrics"], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    quotes_hash = hashlib.sha256(json.dumps(payload["quotes"], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    logger.info(log_event(
        semantic_ctx,
        role="generator",
        event="model_resolved",
        module=logger.name,
        fields={
            "namespace": prompt_namespace,
            "resolved_model": resolved_model,
            "default_model": settings.openai_model,
            "evidence_sha256": evidence_hash,
            "metrics_sha256": metrics_hash,
            "quotes_sha256": quotes_hash,
        },
    ))
    logger.info(log_event(
        semantic_ctx,
        role="generator",
        event="semantic_request_config",
        module=logger.name,
        fields={
            "model": resolved_model,
            "temperature": settings.temperature,
            "seed": settings.openai_seed,
        },
    ))
    try:
        resp = openai_client.openai_chat_json(
            OpenAIJSONPromptRequest(
                schema_version="1.0",
                system_prompt=system_render.text,
                user_prompt=user_render.text,
                model=resolved_model,
                temperature=settings.temperature,
                api_key=settings.openai_api_key,
                seed=settings.openai_seed,
                timeout_seconds=settings.openai_timeout_seconds,
                cost_ledger_path=settings.cost_ledger_path,
                cost_daily_path=settings.cost_daily_path,
                model_pricing=settings.model_pricing,
            ),
            semantic_ctx,
        )
        parsed = resp.parsed_json if isinstance(resp.parsed_json, dict) else None
        logger.info(log_event(
            semantic_ctx,
            role="generator",
            event="semantic_response",
            module=logger.name,
            fields={
                "has_json": isinstance(parsed, dict),
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
            },
        ))
        if parsed is None:
            raise AppError(
                code="semantic_response_invalid",
                message="Semantic validation did not return JSON payload",
                retryable=False,
                context={"model": resolved_model},
            )
        outcome = _parse_semantic_response(parsed)
        logger.info(log_event(
            semantic_ctx,
            role="generator",
            event="semantic_validation_complete",
            module=logger.name,
            fields={
                "metric_entries": len(outcome.metric_support),
                "quote_entries": len(outcome.quote_support),
                "issue_count": len(outcome.issues),
            },
        ))
        return outcome
    except AppError as exc:
        logger.info(log_event(
            semantic_ctx,
            role="generator",
            event="semantic_validation_failed",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))
        return _SemanticCheckOutcome(
            metric_support={},
            quote_support={},
            issues=[_issue(
                message=f"Semantic validation failed: {exc.message}",
                severity="warning",
                section="semantic",
            )],
        )


def _run_grounding_check(
    request: ValidationRequest,
    settings: AppSettings,
    grounding_use_vector_store: bool,
    evidence_texts: Sequence[str],
    evidence_windows: Sequence[_EvidenceWindow],
    prompt_client,
    openai_client,
    ctx: RunContext,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    prompt_ctx = child_context(ctx, task_id=f"{ctx.task_id}:grounding")
    prompt_namespace = "report_vs/validate/grounding"
    prompt_set = prompt_client.load_prompt_set(PromptLoadRequest(schema_version="1.0", namespace=prompt_namespace), prompt_ctx)
    logger.info(log_event(
        prompt_ctx,
        role="generator",
        event="prompt_selected",
        module=logger.name,
        fields={
            "namespace": prompt_namespace,
            "system_path": prompt_set.system.path,
            "system_sha256": prompt_set.system.sha256,
            "user_path": prompt_set.user.path,
            "user_sha256": prompt_set.user.sha256,
        },
    ))
    artifacts = request.artifacts if isinstance(request.artifacts, dict) else {}
    grounding_payload = _grounding_payload(request, artifacts)
    prompt_vars = {
        "report_json": json.dumps(grounding_payload, ensure_ascii=False),
        "evidence_json": json.dumps(list(evidence_texts), ensure_ascii=False),
    }
    system_render = prompt_client.render_prompt(PromptRenderRequest(schema_version="1.0", template=prompt_set.system, variables=prompt_vars), prompt_ctx)
    user_render = prompt_client.render_prompt(PromptRenderRequest(schema_version="1.0", template=prompt_set.user, variables=prompt_vars), prompt_ctx)
    logger.info(log_event(
        prompt_ctx,
        role="generator",
        event="prompt_rendered",
        module=logger.name,
        fields={
            "system_prompt": system_render.text,
            "user_prompt": user_render.text,
        },
    ))

    resolved_model = resolve_model(prompt_namespace, getattr(settings, "openai_models", {}), settings.openai_model)
    logger.info(log_event(
        prompt_ctx,
        role="generator",
        event="model_resolved",
        module=logger.name,
        fields={
            "namespace": prompt_namespace,
            "resolved_model": resolved_model,
            "default_model": settings.openai_model,
        },
    ))
    logger.info(log_event(
        prompt_ctx,
        role="generator",
        event="grounding_request_config",
        module=logger.name,
        fields={
            "model": resolved_model,
            "temperature": settings.temperature,
            "vector_store_id_present": bool(request.vector_store_id),
            "setting_enabled": bool(getattr(settings, "validation_grounding_use_vector_store", False)),
            "grounding_use_vector_store": grounding_use_vector_store,
            "retrieval_mode": _grounding_retrieval_mode(grounding_use_vector_store),
            "seed": settings.openai_seed,
        },
    ))
    try:
        if grounding_use_vector_store:
            resp = openai_client.openai_respond_with_vector_store(
            OpenAIResponseRequest(
                schema_version="1.0",
                system_prompt=system_render.text,
                user_prompt=user_render.text,
                vector_store_id=request.vector_store_id or "",
                model=resolved_model,
                temperature=settings.temperature,
                api_key=settings.openai_api_key,
                seed=settings.openai_seed,
                timeout_seconds=settings.openai_timeout_seconds,
                cost_ledger_path=settings.cost_ledger_path,
                    cost_daily_path=settings.cost_daily_path,
                    model_pricing=settings.model_pricing,
                ),
                prompt_ctx,
            )
        else:
            resp = openai_client.openai_chat_json(
            OpenAIJSONPromptRequest(
                schema_version="1.0",
                system_prompt=system_render.text,
                user_prompt=user_render.text,
                model=resolved_model,
                temperature=settings.temperature,
                api_key=settings.openai_api_key,
                seed=settings.openai_seed,
                timeout_seconds=settings.openai_timeout_seconds,
                    cost_ledger_path=settings.cost_ledger_path,
                    cost_daily_path=settings.cost_daily_path,
                    model_pricing=settings.model_pricing,
                ),
                prompt_ctx,
            )
        unsupported = []
        if isinstance(resp.parsed_json, dict):
            unsupported = resp.parsed_json.get("unsupported") or []
        logger.info(log_event(
            prompt_ctx,
            role="generator",
            event="grounding_response",
            module=logger.name,
            fields={
                "has_json": isinstance(resp.parsed_json, dict),
                "unsupported_count": len(unsupported) if isinstance(unsupported, list) else 0,
            },
        ))
        if isinstance(unsupported, list):
            evidence_quantities = _collect_quantities_from_texts(evidence_texts)
            for window in evidence_windows:
                evidence_quantities.extend(window.quantities)
            for entry in unsupported:
                if not isinstance(entry, dict):
                    continue
                text = _s(entry.get("text"))
                section = _s(entry.get("section") or "grounding")
                reason = _s(entry.get("reason") or "Unsupported sentence")
                section_key = _section_root(section)
                section_policy = _section_policy(section_key)
                classification = _normalize_claim_classification(_s(entry.get("classification")))
                if not classification:
                    classification = _infer_claim_classification(section_key, text)
                violation_type = _normalize_violation_type(_s(entry.get("violation_type") or entry.get("failure_type")))
                if not violation_type:
                    violation_type = _infer_violation_type(
                        section_key=section_key,
                        classification=classification,
                        text=text,
                        reason=reason,
                    )
                retrieval_failure = _is_retrieval_failure(reason)
                if retrieval_failure:
                    violation_type = "evidence_retrieval_failure"

                # Guard against false positives from format variants and conversions.
                if violation_type == "unsupported_number":
                    candidate_quantities = extract_quantities(text)
                    if candidate_quantities and _all_quantities_supported(candidate_quantities, evidence_quantities, numeric_only=True):
                        issues.append(_issue(
                            message=f"[{classification}|normalized_quantity_supported] {reason}: {text[:200]}",
                            severity="info",
                            section=section,
                        ))
                        continue
                severity = _grounding_issue_severity(
                    section_policy=section_policy,
                    section_key=section_key,
                    classification=classification,
                    violation_type=violation_type,
                    text=text,
                    reason=reason,
                )
                if severity == "pass":
                    continue
                if text:
                    issues.append(_issue(
                        message=f"[{classification}|{violation_type}] {reason}: {text[:200]}",
                        severity=severity,
                        section=section,
                    ))
    except AppError as exc:
        logger.info(log_event(
            prompt_ctx,
            role="generator",
            event="grounding_failed",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))
        issues.append(_issue(
            message=f"Grounding check failed: {exc.message}",
            severity="warning",
            section="grounding",
        ))
    return issues


def _grounding_payload(request: ValidationRequest, artifacts: dict) -> dict:
    summary = artifacts.get("summary") if isinstance(artifacts, dict) else {}
    insights_raw = artifacts.get("insights_final") if isinstance(artifacts, dict) else []
    insights: List[dict] = []
    for insight in insights_raw or []:
        if not isinstance(insight, dict):
            continue
        metric = insight.get("metric") if isinstance(insight.get("metric"), dict) else {}
        # confidence is a model-side score, not a report fact; exclude from grounding checks.
        metric_clean = {
            "value": _s(metric.get("value")),
            "unit": _s(metric.get("unit")),
            "timeframe": _s(metric.get("timeframe")),
            "trend": _s(metric.get("trend")),
            "sample_size": _s(metric.get("sample_size")),
            "geography": _s(metric.get("geography")),
            "segment": _s(metric.get("segment")),
        }
        insights.append({
            "id": _s(insight.get("id")),
            "text": _s(insight.get("text")),
            "evidence_id": _s(insight.get("evidence_id")),
            "evidence": _s(insight.get("evidence")),
            "metric": metric_clean,
        })
    summary_clean = {
        "tldr": _s(summary.get("tldr")) if isinstance(summary, dict) else "",
        "executive_summary": _sanitize_citation_tokens(_s(summary.get("executive_summary"))) if isinstance(summary, dict) else "",
        "claim_evidence_map": summary.get("claim_evidence_map") if isinstance(summary, dict) else [],
    }
    return {
        "tldr": request.report.tldr,
        "title": request.report.title,
        "insights_final": insights,
        "quotes_final": artifacts.get("quotes_final") if isinstance(artifacts, dict) else [],
        "summary": summary_clean,
        "expert_comment": _sanitize_citation_tokens(_s(artifacts.get("expert_comment") if isinstance(artifacts, dict) else "")),
        "linkedin_post": _sanitize_citation_tokens(_s(artifacts.get("linkedin_post") if isinstance(artifacts, dict) else "")),
    }


def _semantic_payload(insights: Sequence[dict], quotes: Sequence[dict]) -> dict:
    metrics: List[dict] = []
    for idx, insight in enumerate(insights):
        if not isinstance(insight, dict):
            continue
        metric = insight.get("metric") if isinstance(insight.get("metric"), dict) else {}
        metrics.append({
            "id": _s(insight.get("id") or f"insight_{idx + 1}"),
            "value": _s(metric.get("value")),
            "unit": _s(metric.get("unit")),
            "timeframe": _s(metric.get("timeframe")),
            "insight_text": _s(insight.get("text")),
            "evidence_id": _s(insight.get("evidence_id")),
        })
    quote_entries: List[dict] = []
    for idx, quote in enumerate(quotes):
        if not isinstance(quote, dict):
            continue
        quote_entries.append({
            "id": _quote_label(quote, idx),
            "text": _s(quote.get("text")),
            "speaker": _s(quote.get("speaker")),
            "evidence_id": _s(quote.get("evidence_id")),
        })
    return {"metrics": metrics, "quotes": quote_entries}


def _parse_semantic_response(payload: dict) -> _SemanticCheckOutcome:
    metric_support: Dict[str, _SemanticSupport] = {}
    quote_support: Dict[str, _SemanticSupport] = {}
    issues: List[ValidationIssue] = []
    metrics = payload.get("metrics") if isinstance(payload, dict) else []
    if isinstance(metrics, list):
        for entry in metrics:
            if not isinstance(entry, dict):
                continue
            label = _s(entry.get("id") or entry.get("label") or entry.get("insight_id"))
            if not label:
                continue
            state = entry.get("supported")
            if isinstance(state, str):
                normalized = state.strip().lower()
                supported = normalized in {"true", "yes", "supported", "pass"}
            else:
                supported = bool(state) if state is not None else False
            confidence = _to_float(entry.get("confidence"))
            confidence = confidence if confidence is not None else 0.0
            reason = _s(entry.get("reason"))
            metric_support[label] = _SemanticSupport(supported=supported, confidence=confidence, reason=reason)
            if not supported:
                severity = "error" if confidence >= 0.6 else "warning"
                reason_suffix = f" ({reason})" if reason else ""
                issues.append(_issue(
                    message=f"Semantic check: metric for {label} not supported{reason_suffix}",
                    severity=severity,
                    section=f"insights:{label}",
                ))
    quotes = payload.get("quotes") if isinstance(payload, dict) else []
    if isinstance(quotes, list):
        for entry in quotes:
            if not isinstance(entry, dict):
                continue
            label = _s(entry.get("id") or entry.get("label") or entry.get("quote_id"))
            if not label:
                continue
            state = entry.get("supported")
            if isinstance(state, str):
                normalized = state.strip().lower()
                supported = normalized in {"true", "yes", "supported", "pass"}
            else:
                supported = bool(state) if state is not None else False
            confidence = _to_float(entry.get("confidence"))
            confidence = confidence if confidence is not None else 0.0
            reason = _s(entry.get("reason"))
            quote_support[label] = _SemanticSupport(supported=supported, confidence=confidence, reason=reason)
            if not supported:
                severity = "error" if confidence >= 0.6 else "warning"
                reason_suffix = f" ({reason})" if reason else ""
                issues.append(_issue(
                    message=f"Semantic check: quote {label} not supported{reason_suffix}",
                    severity=severity,
                    section=f"quotes:{label}",
                ))
    return _SemanticCheckOutcome(metric_support=metric_support, quote_support=quote_support, issues=issues)


def _aggregate_severity(issues: Sequence[ValidationIssue]) -> str:
    if any(issue.severity == "error" for issue in issues):
        return "error"
    if any(issue.severity == "warning" for issue in issues):
        return "warning"
    return "pass"


def _collect_allowed_quantities(
    insights: Sequence[dict],
    report: ReportPayload,
    artifacts: dict,
    evidence_texts: Sequence[str],
) -> List[Quantity]:
    quantities: List[Quantity] = []
    quantities.extend(_collect_quantities_from_insights(insights))
    quantities.extend(_collect_quantities_from_report(report))
    quantities.extend(_collect_quantities_from_artifacts(artifacts))
    quantities.extend(_collect_quantities_from_texts(evidence_texts))
    return quantities


def _collect_quantities_from_insights(insights: Sequence[dict]) -> List[Quantity]:
    quantities: List[Quantity] = []
    for insight in insights:
        if not isinstance(insight, dict):
            continue
        metric = insight.get("metric") if isinstance(insight.get("metric"), dict) else {}
        for field in ("value", "unit", "timeframe", "sample_size"):
            value = _s(metric.get(field))
            if value:
                quantities.extend(extract_quantities(value))
        quantities.extend(extract_quantities(_s(insight.get("text"))))
        quantities.extend(extract_quantities(_s(insight.get("evidence"))))
    return quantities


def _collect_quantities_from_report(report: ReportPayload) -> List[Quantity]:
    if not isinstance(report, ReportPayload):
        return []
    texts: List[str] = [
        report.tldr,
        report.title,
        report.commentary,
        report.quote.text if getattr(report, "quote", None) else "",
        report.figure.evidence if getattr(report, "figure", None) else "",
        report.time_period,
        report.region,
        report.source,
    ]
    texts.extend(report.insights or [])
    texts.extend(report.taxonomy or [])
    texts.extend(report.categories or [])
    return _collect_quantities_from_texts(texts)


def _collect_quantities_from_artifacts(artifacts: dict) -> List[Quantity]:
    if not isinstance(artifacts, dict):
        return []
    quantities: List[Quantity] = []
    summary = artifacts.get("summary") if isinstance(artifacts.get("summary"), dict) else {}
    if summary:
        quantities.extend(extract_quantities(_s(summary.get("tldr"))))
        quantities.extend(extract_quantities(_s(summary.get("executive_summary"))))
        for claim in summary.get("claim_evidence_map") or []:
            if not isinstance(claim, dict):
                continue
            quantities.extend(extract_quantities(_s(claim.get("claim"))))
            quantities.extend(extract_quantities(_s(claim.get("evidence"))))
    quantities.extend(_collect_quantities_from_insights(artifacts.get("insights_final") or []))
    quantities.extend(_collect_quantities_from_insights(artifacts.get("insights_candidates") or []))
    for quote in artifacts.get("quotes_final") or []:
        if isinstance(quote, dict):
            quantities.extend(extract_quantities(_s(quote.get("text"))))
            quantities.extend(extract_quantities(_s(quote.get("citation"))))
    return quantities


def _collect_quantities_from_texts(texts: Iterable[Any]) -> List[Quantity]:
    quantities: List[Quantity] = []
    for text in texts:
        quantities.extend(extract_quantities(_s(text)))
    return quantities


def _quantity_supported(
    candidate: Quantity,
    allowed: Iterable[Quantity],
    *,
    numeric_only: bool = False,
) -> bool:
    if numeric_only:
        return any(_quantities_match_numeric_only(candidate, evidence) for evidence in allowed)
    return any(quantities_match(candidate, evidence) for evidence in allowed)


def _all_quantities_supported(
    candidates: Sequence[Quantity],
    allowed: Sequence[Quantity],
    *,
    numeric_only: bool = False,
) -> bool:
    if not candidates:
        return False
    for candidate in candidates:
        if not _quantity_supported(candidate, allowed, numeric_only=numeric_only):
            return False
    return True


def _quantities_match_numeric_only(candidate: Quantity, evidence: Quantity) -> bool:
    candidate_variants = _quantity_numeric_only_variants(candidate)
    evidence_variants = _quantity_numeric_only_variants(evidence)
    for candidate_variant in candidate_variants:
        for evidence_variant in evidence_variants:
            approx = candidate_variant.comparator == "approx" or evidence_variant.comparator == "approx"
            reference = max(abs(candidate_variant.value), abs(evidence_variant.value), 1.0)
            tol = _numeric_only_tolerance(reference=reference, approx=approx)
            if candidate_variant.comparator == "range" or evidence_variant.comparator == "range":
                if _numeric_ranges_overlap(candidate_variant, evidence_variant, tol):
                    return True
                continue
            if candidate_variant.comparator in {"eq", "approx"}:
                if _numeric_value_supported_by_comparator(candidate_variant.value, evidence_variant, tol):
                    return True
                continue
            if evidence_variant.comparator in {"eq", "approx"}:
                if _numeric_value_supported_by_comparator(evidence_variant.value, candidate_variant, tol):
                    return True
                continue
            if _numeric_inequality_compatible(candidate_variant, evidence_variant, tol):
                return True
    return False


def _quantity_numeric_only_variants(quantity: Quantity) -> List[Quantity]:
    variants: List[Quantity] = []
    factor = _MAGNITUDE_FACTORS.get(_s(quantity.magnitude).lower(), 1.0)
    if quantity.comparator == "range" and quantity.low is not None and quantity.high is not None:
        range_pairs = {(quantity.low, quantity.high)}
        if factor > 1.0:
            range_pairs.add((quantity.low / factor, quantity.high / factor))
        for low, high in range_pairs:
            variants.append(
                replace(
                    quantity,
                    value=(low + high) / 2.0,
                    low=low,
                    high=high,
                    unit_family="unknown",
                    unit="",
                    magnitude="",
                )
            )
        return variants

    numeric_values = {quantity.value}
    if quantity.unit_family in {"percent", "ratio"} or _looks_percent_like(quantity):
        numeric_values.add(quantity.value / 100.0)
        numeric_values.add(quantity.value * 100.0)
    if factor > 1.0:
        numeric_values.add(quantity.value / factor)
    for value in sorted(numeric_values):
        variants.append(
            replace(
                quantity,
                value=value,
                low=None,
                high=None,
                unit_family="unknown",
                unit="",
                magnitude="",
            )
        )
    return variants


def _looks_percent_like(quantity: Quantity) -> bool:
    raw_norm = normalize_text(quantity.raw)
    return "%" in raw_norm or "percent" in raw_norm or "pct" in raw_norm


def _numeric_only_tolerance(*, reference: float, approx: bool) -> float:
    base = max(reference * 0.002, 0.01)
    return base * (2.0 if approx else 1.0)


def _numeric_value_supported_by_comparator(value: float, claim: Quantity, tol: float) -> bool:
    if claim.comparator in {"eq", "approx"}:
        return abs(value - claim.value) <= tol
    if claim.comparator == "gt":
        return value > claim.value - tol
    if claim.comparator == "gte":
        return value >= claim.value - tol
    if claim.comparator == "lt":
        return value < claim.value + tol
    if claim.comparator == "lte":
        return value <= claim.value + tol
    if claim.comparator == "range":
        if claim.low is None or claim.high is None:
            return False
        return (claim.low - tol) <= value <= (claim.high + tol)
    return False


def _numeric_bounds(quantity: Quantity) -> Tuple[float, float]:
    if quantity.comparator == "range" and quantity.low is not None and quantity.high is not None:
        return quantity.low, quantity.high
    if quantity.comparator in {"eq", "approx"}:
        return quantity.value, quantity.value
    if quantity.comparator in {"gt", "gte"}:
        return quantity.value, float("inf")
    if quantity.comparator in {"lt", "lte"}:
        return -float("inf"), quantity.value
    return quantity.value, quantity.value


def _numeric_ranges_overlap(left: Quantity, right: Quantity, tol: float) -> bool:
    left_low, left_high = _numeric_bounds(left)
    right_low, right_high = _numeric_bounds(right)
    return max(left_low, right_low) <= min(left_high, right_high) + tol


def _numeric_inequality_compatible(candidate: Quantity, evidence: Quantity, tol: float) -> bool:
    candidate_low, candidate_high = _numeric_bounds(candidate)
    evidence_low, evidence_high = _numeric_bounds(evidence)
    within = (
        (candidate_low >= evidence_low - tol and candidate_high <= evidence_high + tol)
        or (evidence_low >= candidate_low - tol and evidence_high <= candidate_high + tol)
    )
    overlap = max(candidate_low, evidence_low) <= min(candidate_high, evidence_high) + tol
    return within or overlap


def _collect_evidence_texts(
    artifacts: dict,
    evidence_packs: dict,
    *,
    pdf_text: str = "",
) -> Tuple[List[str], Dict[str, str]]:
    texts: List[str] = []
    text_keys: set[str] = set()
    evidence_by_id: Dict[str, str] = {}

    def _add(text: str) -> None:
        cleaned = _s(text).strip()
        if not cleaned:
            return
        key = normalize_text(cleaned)
        if not key or key in text_keys:
            return
        text_keys.add(key)
        texts.append(cleaned)

    if isinstance(artifacts, dict):
        summary = artifacts.get("summary") if isinstance(artifacts.get("summary"), dict) else {}
        for claim in summary.get("claim_evidence_map") or []:
            if isinstance(claim, dict):
                ev = _s(claim.get("evidence"))
                _add(ev)
        for insight in artifacts.get("insights_final") or []:
            if isinstance(insight, dict):
                evidence_text = _s(insight.get("evidence"))
                evidence_id = _s(insight.get("evidence_id"))
                if evidence_text:
                    _add(evidence_text)
                    if evidence_id:
                        evidence_by_id[evidence_id] = evidence_text
        for quote in artifacts.get("quotes_final") or []:
            if isinstance(quote, dict):
                _add(_s(quote.get("citation")))

    if isinstance(evidence_packs, dict):
        for pack in evidence_packs.values():
            if not isinstance(pack, dict):
                continue
            for findings_key in ("findings", "scope", "methods", "limitations"):
                for entry in pack.get(findings_key) or []:
                    if isinstance(entry, dict):
                        ev = _s(entry.get("evidence"))
                        ev_id = _s(entry.get("id"))
                        if ev:
                            _add(ev)
                            if ev_id:
                                evidence_by_id[ev_id] = ev
                        _add(_s(entry.get("description")))
                        _add(_s(entry.get("title")))
            for quote in pack.get("quote_candidates") or []:
                if isinstance(quote, dict):
                    _add(_s(quote.get("text")))
                    _add(_s(quote.get("source_citation")))
    return texts, evidence_by_id


def _build_evidence_windows(texts: Sequence[str]) -> List[_EvidenceWindow]:
    windows: List[_EvidenceWindow] = []
    idx = 0
    for text in texts:
        raw = _s(text).strip()
        if not raw:
            continue
        tokens = _tokenize(raw)
        if len(tokens) <= _WINDOW_TOKEN_TARGET:
            norm = normalize_for_lookup(raw)
            windows.append(_EvidenceWindow(
                idx=idx,
                text=raw,
                normalized=norm,
                tokens=set(tokens),
                quantities=extract_quantities(raw),
            ))
            idx += 1
            continue
        for chunk in _window_tokens(tokens):
            chunk_text = " ".join(chunk).strip()
            if len(chunk_text) < 20:
                continue
            norm = normalize_for_lookup(chunk_text)
            windows.append(_EvidenceWindow(
                idx=idx,
                text=chunk_text,
                normalized=norm,
                tokens=set(chunk),
                quantities=extract_quantities(chunk_text),
            ))
            idx += 1
    return windows


def _window_tokens(tokens: Sequence[str]) -> Iterable[List[str]]:
    if len(tokens) <= _WINDOW_TOKEN_TARGET:
        yield list(tokens)
        return
    start = 0
    n = len(tokens)
    while start < n:
        end = min(n, start + _WINDOW_TOKEN_TARGET)
        chunk = list(tokens[start:end])
        if len(chunk) < _WINDOW_TOKEN_MIN and start != 0:
            break
        yield chunk
        if end >= n:
            break
        start += _WINDOW_STRIDE


def _retrieve_evidence_windows(
    claim_text: str,
    windows: Sequence[_EvidenceWindow],
    *,
    top_k: int = _RETRIEVE_TOP_K,
) -> List[_EvidenceWindow]:
    if not claim_text or not windows:
        return []
    claim_norm = normalize_for_lookup(claim_text)
    claim_tokens = set(_tokenize(claim_norm))
    claim_quantities = extract_quantities(claim_text)
    if not claim_tokens and not claim_quantities:
        return []
    ranked: List[Tuple[float, int]] = []
    for window in windows:
        embedding_sim = _pseudo_embedding_similarity(claim_norm, window.normalized)
        overlap = _token_overlap_score(claim_tokens, window.tokens)
        bm25ish = _bm25ish(claim_tokens, window.tokens)
        quantity_boost = _quantity_boost(claim_quantities, window.quantities)
        score = (0.35 * embedding_sim) + (0.30 * overlap) + (0.20 * bm25ish) + (0.15 * quantity_boost)
        if score > 0:
            ranked.append((score, window.idx))
    if not ranked:
        return []
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected_idx = {idx for _, idx in ranked[:top_k]}
    max_idx = max(window.idx for window in windows)
    expanded_idx = set(selected_idx)
    for idx in list(selected_idx):
        for delta in range(1, _RETRIEVE_NEIGHBOR_RADIUS + 1):
            if idx - delta >= 0:
                expanded_idx.add(idx - delta)
            if idx + delta <= max_idx:
                expanded_idx.add(idx + delta)
    by_idx = {window.idx: window for window in windows}
    return [by_idx[idx] for idx in sorted(expanded_idx) if idx in by_idx]


def _token_overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    inter = len(left & right)
    if inter == 0:
        return 0.0
    return inter / max(1, len(left | right))


def _bm25ish(query_tokens: set[str], doc_tokens: set[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    hits = sum(1 for token in query_tokens if token in doc_tokens)
    return hits / max(1, len(query_tokens))


def _pseudo_embedding_similarity(left: str, right: str) -> float:
    left_vec = _char_ngram_counts(left, n=3)
    right_vec = _char_ngram_counts(right, n=3)
    if not left_vec or not right_vec:
        return 0.0
    dot = 0.0
    for key, left_value in left_vec.items():
        right_value = right_vec.get(key, 0.0)
        dot += left_value * right_value
    left_norm = sum(value * value for value in left_vec.values()) ** 0.5
    right_norm = sum(value * value for value in right_vec.values()) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _char_ngram_counts(text: str, *, n: int) -> Dict[str, float]:
    normalized = normalize_for_lookup(text)
    compact = normalized.replace(" ", "")
    if len(compact) < n:
        return {}
    counts: Dict[str, float] = {}
    for idx in range(len(compact) - n + 1):
        gram = compact[idx:idx + n]
        counts[gram] = counts.get(gram, 0.0) + 1.0
    return counts


def _quantity_boost(claim: Sequence[Quantity], evidence: Sequence[Quantity]) -> float:
    if not claim or not evidence:
        return 0.0
    matched = 0
    for quantity in claim:
        if _quantity_supported(quantity, evidence):
            matched += 1
    return matched / max(1, len(claim))


def _load_pdf_text_from_cache(cache_dir: str, md5: Optional[str], ctx: RunContext) -> str:
    if not md5:
        return ""
    root = Path(cache_dir) / "pdf_cache" / md5
    if not root.exists() or not root.is_dir():
        return ""
    candidates = sorted(root.glob("text_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return ""
    path = candidates[0]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - best effort
        logger.info(log_event(
            ctx,
            role="generator",
            event="validation_pdf_text_cache_read_failed",
            module=logger.name,
            fields={"path": str(path), "error": str(exc)},
        ))
        return ""
    if not isinstance(payload, dict):
        return ""
    return _s(payload.get("text"))


def _extract_quotes(request: ValidationRequest, insights: Sequence[dict]) -> List[dict]:
    artifacts = request.artifacts if isinstance(request.artifacts, dict) else {}
    quotes = artifacts.get("quotes_final") or []
    if quotes:
        return quotes
    quote = request.report.quote
    return [{"text": quote.text, "speaker": quote.author, "evidence_id": _s(insights[0].get("evidence_id")) if insights else ""}]


def _quote_label(quote: dict, idx: int) -> str:
    explicit = _s(quote.get("id") or quote.get("evidence_id"))
    if explicit:
        return explicit
    return str(idx + 1)


def _metric_value_supported(value: str, evidence_text: str, *, unit: str = "", section: str = "") -> bool:
    if not value:
        return True
    value_norm = normalize_text(value)
    evidence_normalized = normalize_text(evidence_text)
    if value_norm and value_norm in evidence_normalized:
        return True
    value_quantities = extract_quantities(f"{value} {unit}".strip())
    evidence_quantities = extract_quantities(evidence_text)
    if value_quantities and evidence_quantities:
        for candidate in value_quantities:
            if not should_ground_quantity(candidate, candidate.sentence, section_policy=_section_policy(section), strict_section=True):
                continue
            if not _quantity_supported(candidate, evidence_quantities, numeric_only=True):
                return False
        return True
    return False


def _contains_token(token: str, text: str) -> bool:
    token_norm = normalize_text(token)
    if not token_norm:
        return True
    return token_norm in normalize_text(text)


def _extract_numbers(text: str) -> List[float]:
    deduped: List[float] = []
    seen: set[int] = set()
    for quantity in extract_quantities(text):
        key = int(round(quantity.value * 10_000))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(quantity.value)
    return deduped


def _to_float(value: Any) -> Optional[float]:
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


def _split_sentences(text: str) -> List[str]:
    cleaned = _sanitize_citation_tokens(_s(text))
    if not cleaned.strip():
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    return [part.strip() for part in parts if part and part.strip()]


def _tokenize(text: str) -> List[str]:
    normalized = normalize_for_lookup(text)
    if not normalized:
        return []
    return re.findall(r"[a-z0-9%$€£¥]+", normalized)


def _lexical_overlap(left: str, right: str) -> float:
    left_tokens = set(_tokenize(left))
    right_tokens = set(_tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    inter = len(left_tokens & right_tokens)
    return inter / max(1, len(left_tokens))


def _quote_near_verbatim(quote: str, evidence: str) -> bool:
    quote_norm = normalize_for_lookup(quote)
    evidence_norm = normalize_for_lookup(evidence)
    if not quote_norm or not evidence_norm:
        return False
    if quote_norm in evidence_norm:
        return True
    overlap = _lexical_overlap(quote_norm, evidence_norm)
    return overlap >= _QUOTE_MIN_LEXICAL_OVERLAP


def _quote_is_paraphrase(quote: dict) -> bool:
    if not isinstance(quote, dict):
        return False
    flags = [_s(quote.get("style")), _s(quote.get("mode")), _s(quote.get("label"))]
    if any(any(hint in normalize_text(flag) for hint in _QUOTE_PARAPHRASE_HINTS) for flag in flags):
        return True
    if quote.get("paraphrase") is True or quote.get("is_paraphrase") is True:
        return True
    text = normalize_text(_s(quote.get("text")))
    return text.startswith("paraphrase:")


def _unsupported_quantity_severity(*, policy: str, quantity: Quantity, sentence: str) -> str:
    if policy == "strict":
        return "error"
    if policy == "mixed":
        if _METRIC_ATTRIBUTION_RE.search(normalize_text(sentence)) or quantity_has_metric_cues(quantity, sentence):
            return "error"
        return "warning"
    if quantity_has_metric_cues(quantity, sentence):
        return "error"
    return "warning"


def quantity_has_metric_cues_from_text(text: str) -> bool:
    quantities = extract_quantities(text)
    if not quantities:
        return False
    return any(quantity_has_metric_cues(quantity, text) for quantity in quantities)


def _sanitize_citation_tokens(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[\ue000-\uf8ff]", " ", text)
    cleaned = re.sub(r"filecite|turn\d+file\d+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _is_retrieval_failure(reason: str) -> bool:
    reason_norm = normalize_text(reason)
    if not reason_norm:
        return False
    return any(hint in reason_norm for hint in _RETRIEVAL_FAILURE_HINTS)


def _section_root(section: str) -> str:
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


def _section_policy(section: str) -> str:
    section_key = _section_root(section)
    if any(section_key.startswith(prefix) for prefix in _STRICT_SECTION_PREFIXES):
        return "strict"
    if any(section_key.startswith(prefix) for prefix in _SOFT_SECTION_PREFIXES):
        return "soft"
    if any(section_key.startswith(prefix) for prefix in _MIXED_SECTION_PREFIXES):
        return "mixed"
    return "strict"


def _normalize_claim_classification(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"factual", "fact", "factual_claim", "claim"}:
        return "factual_claim"
    if normalized in {"analyst_interpretation", "interpretation", "analysis"}:
        return "analyst_interpretation"
    if normalized in {"prescriptive_recommendation", "recommendation", "prescriptive"}:
        return "prescriptive_recommendation"
    return ""


def _infer_claim_classification(section_key: str, text: str) -> str:
    lowered = normalize_text(text)
    policy = _section_policy(section_key)
    if policy == "soft":
        if re.search(r"\b(should|must|need to|recommend|recommended|prioriti[sz]e|consider|action|next step|implement)\b", lowered):
            return "prescriptive_recommendation"
        return "analyst_interpretation"
    if policy == "mixed" and not _METRIC_ATTRIBUTION_RE.search(lowered):
        if re.search(r"\b(should|could|may|might|consider|recommend|priority)\b", lowered):
            return "analyst_interpretation"
    return "factual_claim"


def _normalize_violation_type(value: str) -> str:
    normalized = value.strip().lower()
    mapping = {
        "hallucinated_entity_or_event": "hallucinated_entity_or_event",
        "hallucination": "hallucinated_entity_or_event",
        "unsupported_number": "unsupported_number",
        "new_number": "unsupported_number",
        "misattributed_quote": "misattributed_quote",
        "quote_misattribution": "misattributed_quote",
        "report_directive_misattribution": "report_directive_misattribution",
        "report_said_x": "report_directive_misattribution",
        "unsupported_factual_claim": "unsupported_factual_claim",
        "factual_claim": "unsupported_factual_claim",
        "evidence_retrieval_failure": "evidence_retrieval_failure",
        "non_fatal_interpretation": "non_fatal_interpretation",
    }
    return mapping.get(normalized, "")


def _infer_violation_type(*, section_key: str, classification: str, text: str, reason: str) -> str:
    text_l = normalize_text(text)
    reason_l = normalize_text(reason)
    combined = f"{text_l} {reason_l}"
    if _is_report_directive_misattribution(text_l) or "report instruct" in combined or "report recommends" in combined:
        return "report_directive_misattribution"
    if section_key.startswith("quotes") or "quote" in combined:
        return "misattributed_quote"
    if extract_quantities(text) and any(
        keyword in combined for keyword in ("number", "metric", "value", "figure", "percent", "unsupported")
    ):
        return "unsupported_number"
    if any(
        keyword in combined
        for keyword in ("hallucin", "invented", "made up", "contradict", "not in evidence", "unsupported fact", "entity", "event")
    ):
        return "hallucinated_entity_or_event"
    if classification == "factual_claim":
        return "unsupported_factual_claim"
    return "non_fatal_interpretation"


def _is_report_directive_misattribution(text: str) -> bool:
    return bool(re.search(r"\breport\s+(says|said|states|stated|instructs|instructed|requires|required|recommends|recommended)\b", normalize_text(text)))


def _grounding_issue_severity(
    *,
    section_policy: str,
    section_key: str,
    classification: str,
    violation_type: str,
    text: str,
    reason: str,
) -> str:
    if violation_type in _GROUNDING_HARD_FAILURES:
        return "error"
    if violation_type == "evidence_retrieval_failure":
        return "warning"
    if violation_type == "unsupported_number":
        if section_policy == "strict":
            return "error"
        if section_policy == "mixed":
            if _METRIC_ATTRIBUTION_RE.search(text) or quantity_has_metric_cues_from_text(text):
                return "error"
            return "warning"
        if quantity_has_metric_cues_from_text(text):
            return "error"
        return "warning"
    if section_policy == "soft" and classification in {
        "analyst_interpretation",
        "prescriptive_recommendation",
    }:
        return "info"
    if section_policy == "mixed" and classification in {"analyst_interpretation", "prescriptive_recommendation"}:
        return "info"
    if violation_type == "non_fatal_interpretation":
        return "info"
    return "warning"


def _s(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _ensure_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _issue(message: str, severity: str, section: str) -> ValidationIssue:
    return ValidationIssue(
        schema_version="1.0",
        message=message,
        severity=severity if severity in {"error", "warning", "info"} else "warning",
        affected_section=section,
    )


def _format_confidence(value: float) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _has_data_gap(artifacts: dict) -> bool:
    if not isinstance(artifacts, dict):
        return False
    status = artifacts.get("source_status")
    if isinstance(status, dict):
        return bool(status.get("not_available"))
    return False


def _validation_parallel_workers(settings: AppSettings) -> int:
    raw = getattr(settings, "report_worker_limit", 1)
    try:
        workers = int(raw)
    except (TypeError, ValueError):
        workers = 1
    if workers < 1:
        return 1
    return workers


def _resolve_grounding_vector_store_mode(*, request: ValidationRequest, settings: AppSettings) -> bool:
    return bool(request.vector_store_id) and bool(getattr(settings, "validation_grounding_use_vector_store", False))


def _grounding_retrieval_mode(use_vector_store: bool) -> str:
    return "vector_store" if use_vector_store else "chat_json"


def _validation_cache_meta(
    *,
    request: ValidationRequest,
    settings: AppSettings,
    prompt_client,
    ctx: RunContext,
    md5: str,
    grounding_retrieval_mode: str,
) -> Dict[str, Any]:
    prompt_meta: Dict[str, Any] = {}
    namespaces = [
        "report_vs/validate/semantic",
        "report_vs/validate/grounding",
    ]
    for namespace in namespaces:
        prompt_set = prompt_client.load_prompt_set(PromptLoadRequest(schema_version="1.0", namespace=namespace), ctx)
        prompt_meta[namespace] = {
            "prompt_system_sha256": prompt_set.system.sha256,
            "prompt_user_sha256": prompt_set.user.sha256,
            "model": resolve_model(namespace, getattr(settings, "openai_models", {}), settings.openai_model),
        }
    inputs_hash = sha256_json({
        "report": request.report.to_dict(),
        "artifacts": request.artifacts,
        "evidence_packs": request.evidence_packs,
        "vector_store_id": request.vector_store_id or "",
        "data_gap_policy": getattr(settings, "validation_data_gap_policy", "warn"),
    })
    return {
        "schema_version": "1.0",
        "md5": md5,
        "inputs_sha256": inputs_hash,
        "prompts": prompt_meta,
        "temperature": settings.temperature,
        "seed": settings.openai_seed,
        "use_vector_store": bool(request.vector_store_id),
        "grounding_retrieval_mode": grounding_retrieval_mode,
    }


def _resolve_pack_path(
    output_dir: str,
    report_id: str,
    pack_name: str,
    report_name: Optional[str],
    analysis_store,
    ctx: RunContext,
) -> str:
    if hasattr(analysis_store, "pack_path"):
        try:
            response = analysis_store.pack_path(
                AnalysisPackPathRequest(
                    schema_version="1.0",
                    output_dir=output_dir,
                    report_id=report_id,
                    pack_name=pack_name,
                    report_slug=report_name,
                ),
                ctx,
            )
            if isinstance(response, str):
                return response
            output_path = getattr(response, "output_path", None)
            if isinstance(output_path, str):
                return output_path
        except TypeError:
            return str(analysis_store.pack_path(output_dir, report_id, pack_name, report_slug=report_name))
    return report_analysis_store_service.pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name=pack_name,
            report_slug=report_name,
        ),
        ctx,
    ).output_path


def _store_pack(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    pack_name: str,
    payload: dict,
    ctx: RunContext,
    report_name: Optional[str],
) -> str:
    if hasattr(analysis_store, "store_pack"):
        try:
            response = analysis_store.store_pack(
                AnalysisStorePackRequest(
                    schema_version="1.0",
                    output_dir=output_dir,
                    report_id=report_id,
                    pack_name=pack_name,
                    payload=payload,
                    report_slug=report_name,
                ),
                ctx,
            )
            if isinstance(response, str):
                return response
            output_path = getattr(response, "output_path", None)
            if isinstance(output_path, str):
                return output_path
        except TypeError:
            return str(analysis_store.store_pack(
                output_dir,
                report_id,
                pack_name,
                payload,
                ctx,
                report_slug=report_name,
            ))
    return report_analysis_store_service.store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name=pack_name,
            payload=payload,
            report_slug=report_name,
        ),
        ctx,
    ).output_path


def _load_cached_validation(
    *,
    output_dir: str,
    report_id: str,
    pack_name: str,
    report_name: Optional[str],
    cache_key: str,
    ctx: RunContext,
    analysis_store,
) -> Optional[ValidationReport]:
    if not cache_key:
        return None
    path = _resolve_pack_path(output_dir, report_id, pack_name, report_name, analysis_store, ctx)
    try:
        resp = file_service.read_text(ReadTextRequest(schema_version="1.0", path=path), ctx)
    except AppError as exc:
        if exc.code == "file_not_found":
            return None
        logger.info(log_event(
            ctx,
            role="generator",
            event="validation_cache_read_failed",
            module=logger.name,
            fields={"report_id": report_id, "pack_name": pack_name, "error": exc.message},
        ))
        return None
    try:
        payload = json.loads(resp.content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    cached = payload.get("_cache") if isinstance(payload.get("_cache"), dict) else {}
    if cached.get("key") != cache_key:
        return None
    return _validation_report_from_payload(payload, path)


def _validation_report_from_payload(payload: dict, path: str) -> ValidationReport:
    issues_raw = payload.get("issues") if isinstance(payload.get("issues"), list) else []
    issues: List[ValidationIssue] = []
    for entry in issues_raw:
        if not isinstance(entry, dict):
            continue
        issues.append(ValidationIssue(
            schema_version=str(entry.get("schema_version") or "1.0"),
            message=str(entry.get("message") or ""),
            severity=str(entry.get("severity") or "warning"),
            affected_section=str(entry.get("affected_section") or ""),
        ))
    return ValidationReport(
        schema_version=str(payload.get("schema_version") or "1.0"),
        status=str(payload.get("status") or "fail"),
        severity=str(payload.get("severity") or "pass"),
        issues=issues,
        source_path=path,
    )
