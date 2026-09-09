"""Bounded LLM resolution for genuinely ambiguous report identities."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.contracts.openai import OpenAIJSONImagePromptRequest
from src.contracts.report_assets import PreviewRequest
from src.contracts.report_generation import ReportRuntimeState
from src.contracts.report_identity import ReportTitleResolution
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.report_generation_dependencies import ReportSourceDependencies
from src.generators.report_title_resolution_generator import resolve_report_title
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event
from src.utils.model_client_contract import require_injected_model_client

_IDENTITY_PROMPT_NAMESPACE = "report_vs/identity_resolution"


def resolve_ambiguous_report_title(
    *,
    runtime: ReportRuntimeState,
    dependencies: ReportSourceDependencies,
    pdf_metadata: Mapping[str, object],
    pages: list[tuple[int, str]],
    deterministic_resolution: ReportTitleResolution,
    llm_client: Any | None,
) -> ReportTitleResolution:
    """Resolve only a deterministic title tie from bounded identity evidence."""

    if "title_candidates_ambiguous" not in deterministic_resolution.issues:
        return deterministic_resolution
    identity_ctx = child_context(
        runtime.ctx, task_id=f"{runtime.ctx.task_id}:title_identity"
    )
    preview = dependencies.render_preview(
        PreviewRequest(
            schema_version="1.0",
            pdf_path=runtime.local_pdf_path,
            out_dir=runtime.settings.output_dir,
            report_name=runtime.report_name,
            page_number=0,
            variant="title-identity",
            dpi=144,
        ),
        identity_ctx,
    )
    image_path = _absolute_preview_path(runtime, getattr(preview, "image_path", ""))
    if image_path is None:
        raise AppError(
            code="report_title_identity_preview_missing",
            message="Ambiguous report title cannot be resolved without its cover image",
            retryable=False,
            context={"file_id": runtime.file.file_id},
        )
    evidence = _identity_evidence(runtime.file_name, pdf_metadata, pages)
    prompt = prepare_prompt_bundle(
        namespace=_IDENTITY_PROMPT_NAMESPACE,
        settings=runtime.settings,
        ctx=identity_ctx,
        prompt_client=dependencies,
        user_variables={
            "identity_evidence_json": json.dumps(
                evidence, ensure_ascii=False, sort_keys=True
            )
        },
        output_contract_schema_version="report_title_identity.v1",
        validator_version="report_title_identity.v1",
    )

    def resolve_with_model(_: dict[str, Any]) -> dict[str, Any]:
        response = require_injected_model_client(
            llm_client, scope="report_title_identity"
        ).openai_chat_json_with_images(
            OpenAIJSONImagePromptRequest(
                schema_version="1.0",
                system_prompt=prompt.system_prompt,
                user_prompt=prompt.user_prompt,
                model=prompt.resolved_model,
                temperature=prompt.effective_temperature,
                api_key=runtime.settings.openai_api_key,
                image_paths=[str(image_path)],
                seed=prompt.effective_seed,
                timeout_seconds=prompt.effective_timeout_seconds,
                max_output_tokens=prompt.effective_max_output_tokens,
                cost_ledger_path=runtime.settings.cost_ledger_path,
                cost_daily_path=runtime.settings.cost_daily_path,
                model_pricing=runtime.settings.model_pricing,
                publisher_name=runtime.publisher_name,
                report_name=runtime.source_report_name or runtime.report_title,
                source_url=runtime.source_url,
                prompt_namespace=_IDENTITY_PROMPT_NAMESPACE,
                prompt_hash=prompt.prompt_content_hash,
                usage_db_path=str(getattr(runtime.settings, "usage_db_path", "")),
            ),
            identity_ctx,
        )
        return response.parsed_json if isinstance(response.parsed_json, dict) else {}

    result = resolve_report_title(
        file_name=runtime.file_name,
        pdf_metadata=pdf_metadata,
        pages=pages,
        publisher_name=runtime.publisher_name,
        identity_resolver=resolve_with_model,
    )
    if result.candidate_source != "llm_identity_resolution":
        raise AppError(
            code="report_title_identity_unresolved",
            message="Identity resolver did not return a credible report title",
            retryable=False,
            context={"file_id": runtime.file.file_id},
        )
    log_event_payload = {
        "file_id": runtime.file.file_id,
        "candidate_source": result.candidate_source,
        "confidence": result.confidence,
        "evidence_count": len(result.evidence),
    }
    logging.getLogger("market_lense.report_title_identity_generator").info(
        log_event(
            identity_ctx,
            role="generator",
            event="report_title_identity_resolved",
            module="market_lense.report_title_identity_generator",
            fields=log_event_payload,
        )
    )
    return result


def _absolute_preview_path(runtime: ReportRuntimeState, value: object) -> Path | None:
    path = Path(str(value or "").strip())
    if not str(path):
        return None
    if not path.is_absolute():
        path = Path(runtime.settings.output_dir) / path
    return path if path.is_file() else None


def _identity_evidence(
    file_name: str, pdf_metadata: Mapping[str, object], pages: list[tuple[int, str]]
) -> dict[str, object]:
    return {
        "filename": str(file_name or "").strip(),
        "document_metadata": {
            str(key): str(value).strip()
            for key, value in pdf_metadata.items()
            if str(value or "").strip()
        },
        "first_pages": [
            {"page_number": page_number, "text": str(text or "")[:4000]}
            for page_number, text in pages[:3]
        ],
    }


__all__ = ["resolve_ambiguous_report_title"]
