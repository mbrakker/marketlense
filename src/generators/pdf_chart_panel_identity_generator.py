from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

from src.contracts.files import ReadBytesRequest
from src.contracts.openai import OpenAIJSONImagePromptRequest
from src.contracts.pdf_context import PdfContextBuildRequest
from src.contracts.pdf_text import PdfTextChartIdentityEvidence, PdfTextPage
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.report_assets import CropRequest
from src.contracts.report_generation import ReportRuntimeState
from src.contracts.report_models import CropItem
from src.generators.report_generation_dependencies import ReportSourceDependencies
from src.services import file_service, pdf_service
from src.utils.logging import child_context, log_event
from src.utils.model_client_contract import require_injected_model_client
from src.utils.model_resolver import (
    effective_sampling_controls,
    resolve_settings_execution_policy,
)
from src.utils.pdf_text_layout import (
    two_panel_chart_image_bbox,
    two_panel_chart_platform_names,
)

logger = logging.getLogger("market_lense.pdf_chart_panel_identity_generator")

_PROMPT_NAMESPACE = "pdf_text/chart_panel_identity"
_MIN_LABEL_CONFIDENCE = 0.9


def transcribe_chart_panel_identity(
    runtime: ReportRuntimeState,
    page: PdfTextPage,
    *,
    pdf_path: str,
    pdf_context: Any,
    dependencies: ReportSourceDependencies,
    llm_client=None,
) -> PdfTextPage:
    """Read only the visible labels on a chart crop and retain their provenance."""

    if page.chart_identity_status != "pending":
        return page
    if not page.layout_analysis_complete or not page.layout_evidence:
        return replace(page, chart_identity_status="geometry_unresolved")
    if llm_client is None or not runtime.md5:
        return replace(page, chart_identity_status="unavailable")
    active_context = pdf_context
    owned_context = False
    if (
        getattr(active_context, "path", None) != pdf_path
        or getattr(active_context, "fitz_doc", None) is None
    ):
        context_response = pdf_service.build_pdf_context(
            PdfContextBuildRequest(schema_version="1.0", path=pdf_path), runtime.ctx
        )
        active_context = context_response.context
        owned_context = True
    try:
        return _transcribe_chart_panel_identity_with_context(
            runtime,
            page,
            pdf_path=pdf_path,
            pdf_context=active_context,
            dependencies=dependencies,
            llm_client=llm_client,
        )
    finally:
        if owned_context:
            active_context.close()


def _transcribe_chart_panel_identity_with_context(
    runtime: ReportRuntimeState,
    page: PdfTextPage,
    *,
    pdf_path: str,
    pdf_context: Any,
    dependencies: ReportSourceDependencies,
    llm_client,
) -> PdfTextPage:
    active_client = require_injected_model_client(
        llm_client, scope="pdf_chart_panel_identity"
    )
    fitz_doc = getattr(pdf_context, "fitz_doc", None)
    if fitz_doc is None or getattr(pdf_context, "path", None) != pdf_path:
        return replace(page, chart_identity_status="unavailable")

    page_index = page.page_number - 1
    if not 0 <= page_index < len(fitz_doc):
        return replace(page, chart_identity_status="unavailable")
    fitz_page = fitz_doc[page_index]
    words = fitz_page.get_text("words", sort=True)
    bbox = two_panel_chart_image_bbox(
        page.text,
        words,
        (fitz_page.rect.x0, fitz_page.rect.y0, fitz_page.rect.x1, fitz_page.rect.y1),
    )
    expected_labels = two_panel_chart_platform_names(page.text)
    if bbox is None or expected_labels is None:
        return replace(page, chart_identity_status="unavailable")

    crop_root = Path(runtime.settings.cache_dir) / "pdf_chart_panel_identity"
    crop_response = pdf_service.crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path,
            out_dir=str(crop_root),
            report_name=runtime.report_name,
            subdir="source",
            items=[
                CropItem(
                    id=f"chart-panel-labels-p{page.page_number}",
                    type="figure",
                    score=0.0,
                    page=page_index,
                    bbox=bbox,
                )
            ],
            pad=4,
            mode="legacy",
            dpi=180,
            pdf_context=pdf_context,
        ),
        runtime.ctx,
    )
    if not crop_response.paths:
        return replace(page, chart_identity_status="unavailable")
    image_path = str((crop_root / crop_response.paths[0]).resolve())
    image_bytes = file_service.read_bytes(
        ReadBytesRequest(schema_version="1.0", path=image_path), runtime.ctx
    ).content
    image_sha256 = hashlib.sha256(image_bytes).hexdigest()

    prompt_set = dependencies.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace=_PROMPT_NAMESPACE,
            reload_if_changed=True,
        ),
        runtime.ctx,
    )
    system_render = dependencies.render_prompt(
        PromptRenderRequest(
            schema_version="1.0", template=prompt_set.system, variables={}
        ),
        runtime.ctx,
    )
    user_render = dependencies.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.user,
            variables={"page_number": page.page_number},
        ),
        runtime.ctx,
    )
    decision = resolve_settings_execution_policy(_PROMPT_NAMESPACE, runtime.settings)
    policy = decision.policy
    temperature, seed = effective_sampling_controls(
        policy.model,
        policy.reasoning_effort,
        policy.temperature,
        policy.seed,
    )
    image_ctx = child_context(
        runtime.ctx,
        task_id=f"{runtime.ctx.task_id}:chart_identity:p{page.page_number}",
    )
    logger.info(
        log_event(
            image_ctx,
            role="generator",
            event="chart_panel_identity_transcription_start",
            module=logger.name,
            fields={
                "source_md5": runtime.md5,
                "physical_page": page.page_number,
                "crop_image_sha256": image_sha256,
                "model": policy.model,
                "prompt_namespace": _PROMPT_NAMESPACE,
                "prompt_hash": prompt_set.prompt_content_hash,
            },
        )
    )
    response = active_client.openai_chat_json_with_images(
        OpenAIJSONImagePromptRequest(
            schema_version="1.0",
            system_prompt=system_render.text,
            user_prompt=user_render.text,
            model=policy.model,
            temperature=temperature,
            reasoning_effort=policy.reasoning_effort,
            api_key=runtime.settings.openai_api_key,
            image_paths=[image_path],
            seed=seed,
            timeout_seconds=policy.timeout_seconds,
            max_output_tokens=policy.max_output_tokens,
            cost_ledger_path=runtime.settings.cost_ledger_path,
            cost_daily_path=runtime.settings.cost_daily_path,
            model_pricing=runtime.settings.model_pricing,
            response_cache_enabled=True,
            response_cache_dir=runtime.settings.cache_dir,
            publisher_name=runtime.publisher_name,
            report_name=runtime.source_report_name or runtime.report_title,
            source_url=runtime.source_url,
            prompt_namespace=_PROMPT_NAMESPACE,
            prompt_hash=prompt_set.user.sha256,
            usage_db_path=str(
                getattr(runtime.settings, "usage_db_path", "./state/llm_usage.sqlite")
            ),
        ),
        image_ctx,
    )
    parsed = response.parsed_json if isinstance(response.parsed_json, dict) else {}
    left_label = _text(parsed.get("left_label"))
    right_label = _text(parsed.get("right_label"))
    left_confidence = _confidence(parsed.get("left_confidence"))
    right_confidence = _confidence(parsed.get("right_confidence"))
    expected_by_fold = {label.casefold(): label for label in expected_labels}
    labels_match = (
        left_label.casefold() in expected_by_fold
        and right_label.casefold() in expected_by_fold
        and left_label.casefold() != right_label.casefold()
        and {left_label.casefold(), right_label.casefold()} == set(expected_by_fold)
    )
    transcribed = bool(
        labels_match
        and left_confidence >= _MIN_LABEL_CONFIDENCE
        and right_confidence >= _MIN_LABEL_CONFIDENCE
    )
    evidence = PdfTextChartIdentityEvidence(
        schema_version="1.0",
        status="transcribed" if transcribed else "abstained",
        source_pdf_md5=str(runtime.md5 or ""),
        physical_page_number=page.page_number,
        crop_image_path=image_path,
        crop_image_sha256=image_sha256,
        label_left=expected_by_fold.get(left_label.casefold(), "")
        if transcribed
        else "",
        label_right=expected_by_fold.get(right_label.casefold(), "")
        if transcribed
        else "",
        confidence_left=left_confidence,
        confidence_right=right_confidence,
        model=str(getattr(response, "model", "") or policy.model),
        request_id=str(getattr(response, "request_id", "") or ""),
        prompt_sha256=str(prompt_set.prompt_content_hash),
    )
    logger.info(
        log_event(
            image_ctx,
            role="generator",
            event="chart_panel_identity_transcription_complete",
            module=logger.name,
            fields={
                "physical_page": page.page_number,
                "status": evidence.status,
                "model": evidence.model,
                "request_id": evidence.request_id,
                "crop_image_sha256": evidence.crop_image_sha256,
                "confidence_left": evidence.confidence_left,
                "confidence_right": evidence.confidence_right,
                "input_tokens": getattr(response, "input_tokens", None),
                "output_tokens": getattr(response, "output_tokens", None),
                "total_tokens": getattr(response, "total_tokens", None),
            },
        )
    )
    return replace(
        page,
        chart_identity_status=evidence.status,
        chart_identity_evidence=evidence,
    )


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    confidence = float(value)
    return confidence if math.isfinite(confidence) and 0.0 <= confidence <= 1.0 else 0.0


__all__ = ["transcribe_chart_panel_identity"]
