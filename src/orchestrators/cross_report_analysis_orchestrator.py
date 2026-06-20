from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Callable, cast

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisArtifact,
    CrossReportAnalysisOrchestratorRequest,
    CrossReportAnalysisRequest,
    CrossReportAnalysisSection,
    CrossReportEvidenceReference,
    CrossReportGeneratedAnalysisResult,
    CrossReportOrchestratorOutcome,
    CrossReportOutcomeStatus,
    CrossReportProjectedDataReadRequest,
    CrossReportPublishPackage,
    CrossReportPublishRequestSummary,
    CrossReportPublishResultSummary,
    CrossReportRawMetricReference,
    CrossReportSelectedSourceReport,
    CrossReportSelectedTheme,
    CrossReportSignalScore,
    CrossReportValidationResult,
    validate_cross_report_contract,
)
from src.contracts.files import WriteBytesRequest
from src.contracts.cover_images import CoverImageGenerationRequest, CoverImageReport
from src.contracts.report_cards import CoverFingerprint
from src.contracts.idempotency import (
    OrchestratorIdempotencyGetRequest,
    OrchestratorIdempotencyRecordRequest,
)
from src.contracts.prompts import PromptLoadRequest
from src.contracts.run_context import RunContext
from src.generators.cross_report_analysis_generator import (
    build_cross_report_publish_package,
    generate_cross_report_analysis,
    validate_cross_report_generated_analysis,
)
from src.generators.cover_image_generator import generate_cover_images
from src.orchestrators.publish_orchestrator import publish_cross_report_package
from src.generators.cross_report_analysis_input_generator import (
    assemble_cross_report_analysis_inputs,
    group_cross_report_evidence_agreement,
    score_cross_report_signals,
    select_cross_report_source_reports,
    select_cross_report_theme,
    validate_cross_report_publishability,
)
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.services import (
    analytics_store_service,
    file_service,
    idempotency_service,
    llm_service,
    prompt_service,
)
from src.utils.clock import utc_now_iso as _utc_now
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cross_report_analysis_orchestrator")
_IDEMPOTENCY_SCOPE = "cross_report_analysis_orchestrator.generate"
_IDEMPOTENCY_MATERIAL_VERSION = "2.0"


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _config_fingerprint(settings: Any) -> dict[str, Any]:
    return {
        "enabled": getattr(settings, "cross_report_analysis_enabled", False),
        "prompt_namespace": getattr(
            settings,
            "cross_report_analysis_prompt_namespace",
            "cross_report_analysis/synthesis",
        ),
        "model": getattr(settings, "cross_report_analysis_model", ""),
        "temperature": getattr(settings, "cross_report_analysis_temperature", 1.0),
        "timeout_seconds": getattr(
            settings, "cross_report_analysis_timeout_seconds", 600.0
        ),
        "seed": getattr(settings, "openai_seed", None),
        "cache_enabled": getattr(settings, "cross_report_analysis_cache_enabled", True),
        "auto_theme_enabled": getattr(
            settings, "cross_report_analysis_auto_theme_enabled", True
        ),
        "theme_rotation_window_days": getattr(
            settings, "cross_report_analysis_theme_rotation_window_days", 30
        ),
        "max_prompt_chars": getattr(
            settings, "cross_report_analysis_max_prompt_chars", 60000
        ),
        "signal_score_weights": getattr(
            settings, "cross_report_analysis_signal_score_weights", {}
        ),
    }


def _planned_artifact_path(output_root: str, slug: str) -> str:
    safe_slug = "-".join(
        token
        for token in "".join(
            char.lower() if char.isalnum() else "-" for char in str(slug or "")
        ).split("-")
        if token
    )
    if not safe_slug:
        safe_slug = "cross-report-analysis"
    return str(
        Path(output_root) / "cross_report_analysis" / safe_slug / "analysis.json"
    )


def _planned_publish_html_path(output_root: str, slug: str) -> str:
    safe_slug = "-".join(
        token
        for token in "".join(
            char.lower() if char.isalnum() else "-" for char in str(slug or "")
        ).split("-")
        if token
    )
    if not safe_slug:
        safe_slug = "cross-report-analysis"
    return str(Path(output_root) / "cross_report_analysis" / safe_slug / "publish.html")


def _selected_projection_content_hashes(
    *,
    content_hashes: dict[str, dict[str, str]],
    selected_sources: list[CrossReportSelectedSourceReport],
) -> dict[str, dict[str, str]]:
    selected: dict[str, dict[str, str]] = {}
    for source in selected_sources:
        report_hashes = dict(content_hashes.get(source.report_id) or {})
        if not report_hashes and source.content_hash:
            report_hashes["report"] = source.content_hash
        selected[source.report_id] = report_hashes
    return selected


def _retry_policy(request: CrossReportAnalysisOrchestratorRequest) -> RetryPolicy:
    return RetryPolicy(
        retries=request.retry_retries,
        base_delay_seconds=request.retry_base_delay_seconds,
        backoff_step_seconds=request.retry_backoff_step_seconds,
        jitter_seconds=request.retry_jitter_seconds,
    )


def _run_step(
    *,
    step_name: str,
    operation: Callable[[], Any],
    request: CrossReportAnalysisOrchestratorRequest,
    ctx: RunContext,
    sleep_fn: Callable[[float], None],
) -> Any:
    return run_with_retry(
        step_name=step_name,
        operation=operation,
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        policy=_retry_policy(request),
        retry_event="cross_report_orchestrator_step_retry",
        failure_event="cross_report_orchestrator_step_failed",
        sleep_fn=sleep_fn,
    )


def _enforce_prompt_budget(
    *,
    evidence_inputs_chars: int,
    max_prompt_chars: int,
    request: CrossReportAnalysisOrchestratorRequest,
    ctx: RunContext,
) -> None:
    if evidence_inputs_chars <= max_prompt_chars:
        return
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cross_report_prompt_budget_exceeded",
            module=logger.name,
            fields={
                "request_id": request.analysis_request.request_id,
                "prompt_input_chars": evidence_inputs_chars,
                "max_prompt_chars": max_prompt_chars,
                "selected_max_evidence_items": request.max_evidence_items,
            },
        )
    )
    raise AppError(
        code="cross_report_prompt_budget_exceeded",
        message="Cross-report prompt input exceeds the configured character budget",
        retryable=False,
        severity="error",
        context={
            "request_id": request.analysis_request.request_id,
            "prompt_input_chars": evidence_inputs_chars,
            "max_prompt_chars": max_prompt_chars,
            "max_evidence_items": request.max_evidence_items,
            "operator_action": (
                "Reduce source/evidence limits or increase the cross-report prompt "
                "budget before retrying."
            ),
        },
    )


def _idempotency_material(
    *,
    request: CrossReportAnalysisOrchestratorRequest,
    selected_report_ids: list[str],
    content_hashes: dict[str, dict[str, str]],
    prompt_hashes: dict[str, str],
    settings: Any,
) -> dict[str, Any]:
    return {
        "schema_version": CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        "material_version": _IDEMPOTENCY_MATERIAL_VERSION,
        "analysis_request": asdict(request.analysis_request),
        "projected_data_request": asdict(request.projected_data_request),
        "output_root": request.output_root,
        "max_evidence_items": request.max_evidence_items,
        "max_signals": request.max_signals,
        "max_prompt_chars": request.max_prompt_chars,
        "publish_target_route": request.publish_target_route,
        "selected_report_ids": selected_report_ids,
        "projection_content_hashes": content_hashes,
        "prompt_hashes": prompt_hashes,
        "config_fingerprint": _config_fingerprint(settings),
    }


def _log_transition(
    ctx: RunContext,
    transitions: list[str],
    transition: str,
    fields: dict[str, Any] | None = None,
) -> None:
    transitions.append(transition)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cross_report_orchestrator_transition",
            module=logger.name,
            fields={"transition": transition, **(fields or {})},
        )
    )


def _request_from_dict(payload: dict[str, Any]) -> CrossReportAnalysisRequest:
    return CrossReportAnalysisRequest(**payload)


def _selected_source_from_dict(
    payload: dict[str, Any],
) -> CrossReportSelectedSourceReport:
    return CrossReportSelectedSourceReport(**payload)


def _selected_theme_from_dict(payload: dict[str, Any]) -> CrossReportSelectedTheme:
    return CrossReportSelectedTheme(**payload)


def _evidence_from_dict(payload: dict[str, Any]) -> CrossReportEvidenceReference:
    return CrossReportEvidenceReference(**payload)


def _metric_from_dict(payload: dict[str, Any]) -> CrossReportRawMetricReference:
    return CrossReportRawMetricReference(**payload)


def _signal_from_dict(payload: dict[str, Any]) -> CrossReportSignalScore:
    return CrossReportSignalScore(**payload)


def _section_from_dict(payload: dict[str, Any]) -> CrossReportAnalysisSection:
    return CrossReportAnalysisSection(**payload)


def _generated_from_dict(payload: dict[str, Any]) -> CrossReportGeneratedAnalysisResult:
    return CrossReportGeneratedAnalysisResult(
        schema_version=str(payload["schema_version"]),
        analysis_id=str(payload["analysis_id"]),
        title=str(payload["title"]),
        slug=str(payload["slug"]),
        executive_summary=str(payload["executive_summary"]),
        selected_theme=_selected_theme_from_dict(payload["selected_theme"]),
        selected_sources=[
            _selected_source_from_dict(item) for item in payload["selected_sources"]
        ],
        evidence=[_evidence_from_dict(item) for item in payload["evidence"]],
        signal_scores=[_signal_from_dict(item) for item in payload["signal_scores"]],
        raw_metrics=[_metric_from_dict(item) for item in payload["raw_metrics"]],
        sections=[_section_from_dict(item) for item in payload["sections"]],
        evidence_map=dict(payload["evidence_map"]),
        prompt_hashes=dict(payload["prompt_hashes"]),
        model=str(payload["model"]),
        cost_summary=dict(payload["cost_summary"]),
        decision_focus=str(payload["decision_focus"]),
        executive_takeaways=[
            str(value) for value in payload["executive_takeaways"]
        ],
    )


def _validation_from_dict(payload: dict[str, Any]) -> CrossReportValidationResult:
    return CrossReportValidationResult(**payload)


def _publish_request_from_dict(
    payload: dict[str, Any],
) -> CrossReportPublishRequestSummary:
    return CrossReportPublishRequestSummary(**payload)


def _publish_result_from_dict(
    payload: dict[str, Any],
) -> CrossReportPublishResultSummary:
    return CrossReportPublishResultSummary(**payload)


def _outcome_from_payload(
    payload: dict[str, Any],
    *,
    idempotency_reused: bool,
    current_transitions: list[str],
    ctx: RunContext,
) -> CrossReportOrchestratorOutcome:
    outcome = CrossReportOrchestratorOutcome(
        schema_version=str(payload["schema_version"]),
        run_id=str(payload["run_id"]),
        task_id=str(payload["task_id"]),
        status=payload["status"],
        artifact_path=str(payload["artifact_path"]),
        request=_request_from_dict(payload["request"]),
        generated_result=_generated_from_dict(payload["generated_result"]),
        validation_result=_validation_from_dict(payload["validation_result"]),
        publish_request=_publish_request_from_dict(payload["publish_request"]),
        publish_result=_publish_result_from_dict(payload["publish_result"]),
        idempotency_key=str(payload["idempotency_key"]),
        idempotency_reused=bool(payload["idempotency_reused"]),
        state_transitions=list(payload["state_transitions"]),
    )
    return replace(
        outcome,
        run_id=ctx.run_id,
        task_id=ctx.task_id,
        idempotency_reused=idempotency_reused,
        state_transitions=[*current_transitions, "idempotency_reused"],
    )


def _artifact_bytes(artifact: CrossReportAnalysisArtifact) -> bytes:
    return (
        json.dumps(
            asdict(artifact),
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
            default=str,
        )
        + "\n"
    ).encode("utf-8")


def _publish_html_bytes(package: CrossReportPublishPackage) -> bytes:
    return (package.html_text + "\n").encode("utf-8")


def _skipped_publish_result(
    request: CrossReportAnalysisOrchestratorRequest,
) -> CrossReportPublishResultSummary:
    return CrossReportPublishResultSummary(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        publication_mode=request.analysis_request.publication_mode,
        status="skipped",
        target_route=request.publish_target_route,
        idempotency_reused=False,
        error_code="publication_not_requested",
        error_message="Publication was not requested for this mode.",
    )


def _not_requested_publish_result(
    request: CrossReportAnalysisOrchestratorRequest,
) -> CrossReportPublishResultSummary:
    return CrossReportPublishResultSummary(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        publication_mode=request.analysis_request.publication_mode,
        status="not_requested",
        target_route=request.publish_target_route,
        idempotency_reused=False,
    )


def _outcome_status(
    publication_mode: str,
    publish_result: CrossReportPublishResultSummary,
) -> CrossReportOutcomeStatus:
    if publication_mode == "publish_live":
        if publish_result.status == "published":
            return "published"
        if publish_result.status == "error":
            return "failed"
        if publish_result.status == "skipped":
            return "skipped"
    return cast(CrossReportOutcomeStatus, "validated")


def _enforce_cross_report_feature_policy(
    request: CrossReportAnalysisOrchestratorRequest,
    settings: Any,
    ctx: RunContext,
) -> None:
    enabled = bool(getattr(settings, "cross_report_analysis_enabled", False))
    auto_theme_enabled = bool(
        getattr(settings, "cross_report_analysis_auto_theme_enabled", True)
    )
    request_uses_auto_theme = bool(
        request.analysis_request.auto_theme
        or not request.analysis_request.topic.strip()
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cross_report_feature_policy_evaluated",
            module=logger.name,
            fields={
                "request_id": request.analysis_request.request_id,
                "enabled": enabled,
                "auto_theme_enabled": auto_theme_enabled,
                "auto_theme": request.analysis_request.auto_theme,
                "topic_present": bool(request.analysis_request.topic.strip()),
            },
        )
    )
    if not enabled:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="cross_report_feature_policy_blocked",
                module=logger.name,
                fields={
                    "request_id": request.analysis_request.request_id,
                    "reason": "feature_disabled",
                },
            )
        )
        raise AppError(
            code="cross_report_analysis_disabled",
            message="Cross-report analysis is disabled by configuration",
            retryable=False,
            severity="error",
            context={"request_id": request.analysis_request.request_id},
        )
    if request_uses_auto_theme and not auto_theme_enabled:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="cross_report_feature_policy_blocked",
                module=logger.name,
                fields={
                    "request_id": request.analysis_request.request_id,
                    "reason": "auto_theme_disabled",
                    "auto_theme": request.analysis_request.auto_theme,
                    "topic_present": bool(request.analysis_request.topic.strip()),
                },
            )
        )
        raise AppError(
            code="cross_report_auto_theme_disabled",
            message="Automatic cross-report theme selection is disabled by configuration",
            retryable=False,
            severity="error",
            context={
                "request_id": request.analysis_request.request_id,
                "auto_theme": request.analysis_request.auto_theme,
                "topic": request.analysis_request.topic,
            },
        )


def _recent_artifacts_root(output_root: str) -> str:
    return str(Path(output_root) / "cross_report_analysis")


def _theme_rotation_reference_date(request: CrossReportAnalysisRequest) -> str | None:
    return str(request.date_range_end or "").strip() or None


def run_cross_report_analysis(
    request: CrossReportAnalysisOrchestratorRequest,
    settings: Any,
    ctx: RunContext,
    *,
    read_projected_data_fn: Callable[
        [CrossReportProjectedDataReadRequest, RunContext], Any
    ] = analytics_store_service.read_cross_report_projected_data,
    write_bytes_fn: Callable[
        [WriteBytesRequest, RunContext], Any
    ] = file_service.write_bytes,
    prompt_client: Any = prompt_service,
    openai_client: Any | None = None,
    publish_settings: Any | None = None,
    publish_cross_report_package_fn: Callable[
        ..., CrossReportPublishResultSummary
    ] = publish_cross_report_package,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> CrossReportOrchestratorOutcome:
    validate_cross_report_contract(request)
    transitions: list[str] = []
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cross_report_orchestrator_start",
            module=logger.name,
            fields={
                "request_id": request.analysis_request.request_id,
                "publication_mode": request.analysis_request.publication_mode,
                "output_root": request.output_root,
            },
        )
    )
    _log_transition(ctx, transitions, "started")
    _enforce_cross_report_feature_policy(request, settings, ctx)
    if openai_client is None:
        openai_client = llm_service.build_client_for_settings(
            settings,
            scope="cross_report_analysis",
        )

    projected_data = _run_step(
        step_name="read_projected_data",
        operation=lambda: read_projected_data_fn(request.projected_data_request, ctx),
        request=request,
        ctx=ctx,
        sleep_fn=sleep_fn,
    )
    _log_transition(ctx, transitions, "projected_data_read")
    source_selection = select_cross_report_source_reports(
        request.analysis_request, projected_data, ctx
    )
    _log_transition(
        ctx,
        transitions,
        "source_selected",
        {
            "selected_report_ids": [
                s.report_id for s in source_selection.selected_sources
            ]
        },
    )
    theme_selection = select_cross_report_theme(
        request.analysis_request,
        source_selection,
        ctx,
        recent_artifacts_root=_recent_artifacts_root(request.output_root),
        theme_rotation_window_days=int(
            getattr(settings, "cross_report_analysis_theme_rotation_window_days", 30)
        ),
        theme_rotation_reference_date=_theme_rotation_reference_date(
            request.analysis_request
        ),
    )
    _log_transition(
        ctx,
        transitions,
        "theme_selected",
        {"selected_theme_id": theme_selection.selected_theme.theme_id},
    )
    validate_cross_report_publishability(
        request.analysis_request,
        theme_selection,
        source_selection,
        ctx,
        min_source_publishers=int(
            getattr(settings, "cross_report_analysis_min_theme_source_publishers", 2)
        ),
        publish_requires_validation_pass=False,
    )
    _log_transition(ctx, transitions, "publishability_checked")
    evidence_inputs = assemble_cross_report_analysis_inputs(
        request.analysis_request,
        source_selection,
        projected_data,
        ctx,
        max_evidence_items=request.max_evidence_items,
    )
    _enforce_prompt_budget(
        evidence_inputs_chars=evidence_inputs.prompt_input_chars,
        max_prompt_chars=request.max_prompt_chars,
        request=request,
        ctx=ctx,
    )
    _log_transition(ctx, transitions, "evidence_assembled")
    signal_result = score_cross_report_signals(
        request.analysis_request,
        evidence_inputs,
        theme_selection,
        ctx,
        score_weights=getattr(
            settings, "cross_report_analysis_signal_score_weights", {}
        ),
        max_signals=request.max_signals,
    )
    _log_transition(ctx, transitions, "signals_scored")
    agreement_result = group_cross_report_evidence_agreement(
        request.analysis_request,
        evidence_inputs,
        signal_result,
        ctx,
    )
    _log_transition(ctx, transitions, "agreement_grouped")
    prompt_set = prompt_client.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace=str(
                getattr(
                    settings,
                    "cross_report_analysis_prompt_namespace",
                    "cross_report_analysis/synthesis",
                )
            ),
            reload_if_changed=True,
        ),
        ctx,
    )
    prompt_hashes = {
        "system": prompt_set.system.sha256,
        "user": prompt_set.user.sha256,
    }
    selected_report_ids = [
        source.report_id for source in source_selection.selected_sources
    ]
    selected_content_hashes = _selected_projection_content_hashes(
        content_hashes=projected_data.content_hashes,
        selected_sources=source_selection.selected_sources,
    )
    idempotency_material = _idempotency_material(
        request=request,
        selected_report_ids=selected_report_ids,
        content_hashes=selected_content_hashes,
        prompt_hashes=prompt_hashes,
        settings=settings,
    )
    input_checksum = _hash_payload(idempotency_material)
    idempotency_key = f"cross-report-analysis:{input_checksum}"
    lookup = idempotency_service.get_outcome(
        OrchestratorIdempotencyGetRequest(
            schema_version="1.0",
            db_path=request.idempotency_db_path,
            scope=_IDEMPOTENCY_SCOPE,
            idempotency_key=idempotency_key,
            input_checksum=input_checksum,
        ),
        ctx,
    )
    _log_transition(
        ctx,
        transitions,
        "idempotency_checked",
        {
            "idempotency_key": idempotency_key,
            "found": lookup.found,
            "material_version": _IDEMPOTENCY_MATERIAL_VERSION,
            "material_fields": sorted(idempotency_material.keys()),
            "miss_diagnostics": (
                {
                    "output_root": request.output_root,
                    "max_evidence_items": request.max_evidence_items,
                    "max_signals": request.max_signals,
                    "max_prompt_chars": request.max_prompt_chars,
                    "publish_target_route": request.publish_target_route,
                }
                if not lookup.found
                else {}
            ),
        },
    )
    if lookup.found and lookup.record is not None:
        reused = _outcome_from_payload(
            lookup.record.outcome_payload,
            idempotency_reused=True,
            current_transitions=transitions,
            ctx=ctx,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="cross_report_orchestrator_idempotency_reused",
                module=logger.name,
                fields={
                    "request_id": request.analysis_request.request_id,
                    "idempotency_key": idempotency_key,
                    "artifact_path": reused.artifact_path,
                },
            )
        )
        return reused

    generated = _run_step(
        step_name="generate_analysis",
        operation=lambda: generate_cross_report_analysis(
            request.analysis_request,
            evidence_inputs,
            signal_result,
            agreement_result,
            settings,
            ctx,
            prompt_client=prompt_client,
            openai_client=openai_client,
            max_prompt_chars=request.max_prompt_chars,
        ),
        request=request,
        ctx=ctx,
        sleep_fn=sleep_fn,
    )
    _log_transition(ctx, transitions, "generated")
    validation = validate_cross_report_generated_analysis(
        generated,
        ctx,
        prompt_budget_chars=evidence_inputs.prompt_input_chars,
        max_prompt_chars=request.max_prompt_chars,
    )
    _log_transition(ctx, transitions, "validated", {"status": validation.status})
    artifact_path = _planned_artifact_path(request.output_root, generated.slug)
    publish_html_path = _planned_publish_html_path(request.output_root, generated.slug)
    fingerprint = CoverFingerprint(
        schema_version="1.0",
        geometry_family="system_matrix",
        evidence_shape="system",
        direction="neutral",
        geography_scope="unknown",
        evidence_density="balanced",
        domain_layer="forecast",
        seed=int(hashlib.sha256(generated.analysis_id.encode("utf-8")).hexdigest()[:8], 16),
        selection_reason="Cross-report briefing synthesizes multiple linked report systems.",
    )
    cover_outcomes = generate_cover_images(
        CoverImageGenerationRequest(
            schema_version="2.0",
            output_dir=request.output_root,
            style_config_path=str(getattr(settings, "cover_style_path", "")),
            reports=[CoverImageReport(
                schema_version="2.0", file_id=f"cross-report:{generated.analysis_id}",
                title=generated.title, publisher="Market Bearing", report_slug=generated.slug,
                time_period="", region=None, fingerprint=fingerprint, cover_profile="briefing",
            )],
        ),
        ctx,
    )
    cover_assets = cover_outcomes[0].assets if cover_outcomes and cover_outcomes[0].status == "generated" else None
    if cover_assets is None:
        raise AppError(code="cover_asset_set_incomplete", message="Briefing cover generation did not produce all assets", retryable=False)
    briefing_card = {
        "schema_version": "1.0", "summary_compact": generated.executive_summary,
        "summary_standard": generated.executive_summary, "decision_focus": generated.decision_focus,
        "takeaways": list(generated.executive_takeaways), "source_count": len(generated.selected_sources),
        "evidence_count": len(generated.evidence),
        "covers": {size: getattr(cover_assets, size).output_path for size in ("small", "medium", "large")},
    }
    publish_package = build_cross_report_publish_package(
        generated,
        validation,
        agreement_result,
        ctx,
        artifact_path=artifact_path,
        html_path=publish_html_path,
        publish_requires_validation_pass=bool(
            getattr(
                settings, "cross_report_analysis_publish_requires_validation_pass", True
            )
        ),
        target_route=request.publish_target_route,
        briefing_card=briefing_card,
    )
    _log_transition(
        ctx,
        transitions,
        "publish_package_built",
        {
            "package_id": publish_package.package_id,
            "html_path": publish_package.html_path,
        },
    )
    html_write_response = write_bytes_fn(
        WriteBytesRequest(
            schema_version="1.0",
            path=publish_package.html_path,
            content=_publish_html_bytes(publish_package),
            make_parents=True,
        ),
        ctx,
    )
    _log_transition(
        ctx,
        transitions,
        "publish_html_persisted",
        {
            "html_path": publish_package.html_path,
            "bytes_written": getattr(html_write_response, "bytes_written", 0),
            "md5": getattr(html_write_response, "md5", ""),
        },
    )
    publish_request = CrossReportPublishRequestSummary(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        publication_mode=request.analysis_request.publication_mode,
        target_route=request.publish_target_route,
        title=generated.title,
        slug=generated.slug,
        artifact_path=artifact_path,
        validation_status=validation.status,
        selected_report_ids=selected_report_ids,
        selected_theme_id=signal_result.selected_theme.theme_id,
    )
    publication_mode = request.analysis_request.publication_mode
    if publication_mode == "generate_only":
        publish_result = _not_requested_publish_result(request)
    elif publication_mode == "validate_only":
        publish_result = _skipped_publish_result(request)
    elif publication_mode == "publish_dry_run":
        publish_result = _run_step(
            step_name="publish_cross_report_package",
            operation=lambda: publish_cross_report_package_fn(
                publish_package,
                publish_settings,
                ctx,
                dry_run=True,
                sleep_fn=sleep_fn,
            ),
            request=request,
            ctx=ctx,
            sleep_fn=sleep_fn,
        )
    elif publication_mode == "publish_live":
        if not bool(getattr(settings, "cross_report_analysis_publish_enabled", False)):
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="cross_report_publish_decision",
                    module=logger.name,
                    fields={
                        "publication_mode": publication_mode,
                        "decision": "blocked",
                        "reason": "publish_disabled",
                        "target_route": request.publish_target_route,
                        "validation_status": validation.status,
                    },
                )
            )
            raise AppError(
                code="cross_report_publish_live_disabled",
                message="Cross-report live publication is disabled by configuration",
                retryable=False,
                severity="error",
                context={
                    "publication_mode": publication_mode,
                    "target_route": request.publish_target_route,
                },
            )
        if publish_settings is None:
            raise AppError(
                code="cross_report_publish_settings_missing",
                message="Cross-report live publication requires publish settings",
                retryable=False,
                severity="error",
                context={"publication_mode": publication_mode},
            )
        publish_result = _run_step(
            step_name="publish_cross_report_package",
            operation=lambda: publish_cross_report_package_fn(
                publish_package,
                publish_settings,
                ctx,
                dry_run=False,
                sleep_fn=sleep_fn,
            ),
            request=request,
            ctx=ctx,
            sleep_fn=sleep_fn,
        )
    else:
        raise AppError(
            code="cross_report_publication_mode_invalid",
            message="Unsupported cross-report publication mode",
            retryable=False,
            severity="error",
            context={"publication_mode": publication_mode},
        )
    _log_transition(
        ctx,
        transitions,
        "publish_decision_evaluated",
        {
            "publication_mode": publication_mode,
            "publish_status": publish_result.status,
            "target_route": request.publish_target_route,
            "validation_status": validation.status,
        },
    )
    artifact = CrossReportAnalysisArtifact(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        artifact_type="cross_report_analysis",
        generated_at_utc=_utc_now(),
        request_fingerprint=input_checksum,
        idempotency_key=idempotency_key,
        selected_report_ids=selected_report_ids,
        projection_content_hashes=selected_content_hashes,
        prompt_hashes=prompt_hashes,
        config_fingerprint=_config_fingerprint(settings),
        validation_status=validation.status,
        request=request.analysis_request,
        generated_result=generated,
        validation_result=validation,
        publish_request=publish_request,
        publish_result=publish_result,
        publish_package=publish_package,
    )
    validate_cross_report_contract(artifact)
    write_response = write_bytes_fn(
        WriteBytesRequest(
            schema_version="1.0",
            path=artifact_path,
            content=_artifact_bytes(artifact),
            make_parents=True,
        ),
        ctx,
    )
    _log_transition(
        ctx,
        transitions,
        "artifact_persisted",
        {
            "artifact_path": artifact_path,
            "bytes_written": getattr(write_response, "bytes_written", 0),
            "md5": getattr(write_response, "md5", ""),
        },
    )
    outcome = CrossReportOrchestratorOutcome(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        run_id=ctx.run_id,
        task_id=ctx.task_id,
        status=_outcome_status(publication_mode, publish_result),
        artifact_path=artifact_path,
        request=request.analysis_request,
        generated_result=generated,
        validation_result=validation,
        publish_request=publish_request,
        publish_result=publish_result,
        idempotency_key=idempotency_key,
        idempotency_reused=False,
        state_transitions=[*transitions, "idempotency_recorded", "completed"],
    )
    validate_cross_report_contract(outcome)
    idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=request.idempotency_db_path,
            scope=_IDEMPOTENCY_SCOPE,
            idempotency_key=idempotency_key,
            input_checksum=input_checksum,
            outcome_payload=asdict(outcome),
            artifact_references={"artifact_path": artifact_path},
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cross_report_orchestrator_transition",
            module=logger.name,
            fields={"transition": "idempotency_recorded"},
        )
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cross_report_orchestrator_complete",
            module=logger.name,
            fields={
                "request_id": request.analysis_request.request_id,
                "status": outcome.status,
                "artifact_path": outcome.artifact_path,
                "idempotency_key": outcome.idempotency_key,
                "idempotency_reused": outcome.idempotency_reused,
            },
        )
    )
    return outcome
