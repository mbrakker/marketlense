from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.contracts.openai import OpenAIJSONImagePromptRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.report_generation import ReportRuntimeState
from src.contracts.report_models import ReportFigureAsset, ReportPayload
from src.contracts.semantic_ids import ReportId
from src.generators.report_generation_dependencies import FigureCaptionDependencies
from src.services import llm_service
from src.utils.logging import child_context, log_event
from src.utils.model_resolver import resolve_model

if TYPE_CHECKING:
    from src.contracts.report_generation import ReportSelectionState

logger = logging.getLogger("market_lense.figure_caption_generator")

_SPACE_RX = re.compile(r"\s+")
_TOKEN_RX = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class FigureCaptionGenerationResult:
    schema_version: str
    payload: ReportPayload
    pack_path: str
    pack_payload: dict[str, Any]


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return _SPACE_RX.sub(" ", text)


def _truncate(text: Any, limit: int) -> str:
    normalized = _normalize_text(text)
    if limit <= 0 or len(normalized) <= limit:
        return normalized
    if limit <= 3:
        return normalized[:limit]
    return normalized[: limit - 3].rstrip() + "..."


def _tokenize(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for token in _TOKEN_RX.findall(_normalize_text(value).lower()):
            if len(token) >= 3:
                tokens.add(token)
    return tokens


def _pages(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    pages: list[int] = []
    for item in value:
        try:
            pages.append(int(item))
        except (TypeError, ValueError):
            continue
    return pages


def _overlap_score(tokens: set[str], *values: Any) -> int:
    if not tokens:
        return 0
    target = _tokenize(*values)
    return len(tokens & target)


def _select_section_context(
    doc_map: dict[str, Any], asset: ReportFigureAsset
) -> dict[str, Any]:
    sections = (
        doc_map.get("sections") if isinstance(doc_map.get("sections"), list) else []
    )
    if not sections:
        return {"section_title": "", "section_summary": "", "page_hint": asset.page}
    asset_page = asset.page + 1 if asset.page >= 0 else -1
    asset_tokens = _tokenize(asset.detected_caption, asset.preview_text)
    best_section: dict[str, Any] | None = None
    best_score: tuple[int, int, int] | None = None
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_pages = _pages(section.get("pages"))
        page_score = 0
        page_distance = 9999
        if asset_page > 0 and section_pages:
            page_distance = min(abs(page - asset_page) for page in section_pages)
            if asset_page in section_pages:
                page_score = 3
            elif page_distance <= 1:
                page_score = 2
            elif page_distance <= 3:
                page_score = 1
        lexical_score = _overlap_score(
            asset_tokens,
            section.get("title"),
            section.get("summary"),
            " ".join(str(item) for item in section.get("key_points") or []),
        )
        score = (page_score, lexical_score, -page_distance)
        if best_score is None or score > best_score:
            best_score = score
            best_section = section
    if not isinstance(best_section, dict):
        return {"section_title": "", "section_summary": "", "page_hint": asset.page}
    page_hint = asset.page
    section_pages = _pages(best_section.get("pages"))
    if section_pages:
        page_hint = section_pages[0] - 1
    return {
        "section_title": _truncate(best_section.get("title"), 180),
        "section_summary": _truncate(best_section.get("summary"), 350),
        "page_hint": int(page_hint if page_hint >= 0 else asset.page),
    }


def _collect_evidence_candidates(
    findings_pack: dict[str, Any], artifacts_payload: dict[str, Any]
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    findings_value = findings_pack.get("findings")
    findings = findings_value if isinstance(findings_value, list) else []
    for item in findings:
        if not isinstance(item, dict):
            continue
        text = _normalize_text(item.get("text"))
        if not text:
            continue
        candidates.append(
            {
                "text": text,
                "pages": _pages(item.get("pages")),
            }
        )
    summary_value = artifacts_payload.get("summary")
    summary = summary_value if isinstance(summary_value, dict) else {}
    claim_map_value = summary.get("claim_evidence_map")
    claim_map = claim_map_value if isinstance(claim_map_value, list) else []
    for item in claim_map:
        if not isinstance(item, dict):
            continue
        claim = _normalize_text(item.get("claim"))
        evidence = _normalize_text(item.get("evidence"))
        text = ": ".join(part for part in (claim, evidence) if part)
        if not text:
            continue
        candidates.append(
            {
                "text": text,
                "pages": _pages(item.get("pages")),
            }
        )
    return candidates


def _select_evidence_highlights(
    *,
    findings_pack: dict[str, Any],
    artifacts_payload: dict[str, Any],
    asset: ReportFigureAsset,
    section_context: dict[str, Any],
) -> list[str]:
    asset_page = asset.page + 1 if asset.page >= 0 else -1
    asset_tokens = _tokenize(
        asset.detected_caption,
        asset.preview_text,
        section_context.get("section_title"),
        section_context.get("section_summary"),
    )
    scored: list[tuple[tuple[int, int, int], str]] = []
    for candidate in _collect_evidence_candidates(findings_pack, artifacts_payload):
        pages = candidate["pages"]
        page_score = 0
        page_distance = 9999
        if asset_page > 0 and pages:
            page_distance = min(abs(page - asset_page) for page in pages)
            if asset_page in pages:
                page_score = 3
            elif page_distance <= 1:
                page_score = 2
            elif page_distance <= 3:
                page_score = 1
        lexical_score = _overlap_score(asset_tokens, candidate["text"])
        scored.append(((page_score, lexical_score, -page_distance), candidate["text"]))
    highlights: list[str] = []
    seen: set[str] = set()
    for _score, text in sorted(scored, key=lambda item: item[0], reverse=True):
        normalized = _truncate(text, 220)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        highlights.append(normalized)
        if len(highlights) >= 3:
            break
    return highlights


def _build_context_bundle(
    *,
    payload: ReportPayload,
    asset: ReportFigureAsset,
    doc_map: dict[str, Any],
    findings_pack: dict[str, Any],
    artifacts_payload: dict[str, Any],
) -> dict[str, Any]:
    section_context = _select_section_context(doc_map, asset)
    summary_value = artifacts_payload.get("summary")
    summary = summary_value if isinstance(summary_value, dict) else {}
    report_identity = {
        "title": _truncate(payload.title, 180),
        "publisher": _truncate(payload.publisher, 120),
        "region": _truncate(payload.region, 80),
        "time_period": _truncate(payload.time_period, 80),
    }
    report_thesis = {
        "tldr": _truncate(summary.get("tldr") or payload.tldr, 320),
        "executive_summary": _truncate(
            summary.get("executive_summary") or payload.commentary, 700
        ),
    }
    evidence_highlights = _select_evidence_highlights(
        findings_pack=findings_pack,
        artifacts_payload=artifacts_payload,
        asset=asset,
        section_context=section_context,
    )
    return {
        "report_identity": report_identity,
        "report_thesis": report_thesis,
        "section_context": section_context,
        "evidence_highlights": evidence_highlights,
        "figure_signals": {
            "candidate_type": _truncate(asset.kind, 32),
            "page": asset.page,
            "detected_caption": _truncate(asset.detected_caption, 180),
            "preview_text": _truncate(asset.preview_text, 260),
        },
    }


def _fallback_display_caption(
    *,
    asset: ReportFigureAsset,
    index: int,
    legacy_primary_caption: str,
) -> tuple[str, str]:
    if asset.is_primary:
        return legacy_primary_caption, "legacy"
    detected_caption = _normalize_text(asset.detected_caption)
    if detected_caption:
        return detected_caption, "detected"
    return f"Additional figure {index}", "placeholder"


def _apply_asset_captions(
    payload: ReportPayload,
    assets: list[ReportFigureAsset],
    primary_caption: str,
) -> ReportPayload:
    updated = list(assets)
    if updated:
        primary = updated[0]
        final_primary_caption = (
            _normalize_text(primary.display_caption) or primary_caption
        )
        payload.figure.title = final_primary_caption
        payload.figure.evidence = final_primary_caption
    payload._figure_assets = updated
    return payload


def generate_figure_captions(
    *,
    runtime: ReportRuntimeState,
    selection: "ReportSelectionState",
    payload: ReportPayload,
    doc_map: dict[str, Any],
    findings_pack: dict[str, Any],
    artifacts_payload: dict[str, Any],
    dependencies: FigureCaptionDependencies,
) -> FigureCaptionGenerationResult:
    assets = list(payload._figure_assets or [])
    if not runtime.settings.figure_caption_enabled or not assets:
        return FigureCaptionGenerationResult(
            schema_version="1.0",
            payload=payload,
            pack_path="",
            pack_payload={},
        )

    caption_ctx = child_context(
        runtime.ctx, task_id=f"{runtime.ctx.task_id}:figure_captions"
    )
    prompt_namespace = runtime.settings.figure_caption_prompt_namespace
    prompt_set = dependencies.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace=prompt_namespace,
            reload_if_changed=True,
        ),
        caption_ctx,
    )
    resolved_model = resolve_model(
        prompt_namespace,
        getattr(runtime.settings, "openai_models", {}),
        runtime.settings.openai_model,
    )
    logger.info(
        log_event(
            caption_ctx,
            role="generator",
            event="figure_caption_prompt_selected",
            module=logger.name,
            fields={
                "namespace": prompt_namespace,
                "system_path": prompt_set.system.path,
                "system_sha256": prompt_set.system.sha256,
                "user_path": prompt_set.user.path,
                "user_sha256": prompt_set.user.sha256,
            },
        )
    )
    system_render = dependencies.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.system,
            variables={"max_chars": runtime.settings.figure_caption_max_chars},
        ),
        caption_ctx,
    )
    logger.info(
        log_event(
            caption_ctx,
            role="generator",
            event="figure_caption_system_prompt_rendered",
            module=logger.name,
            fields={"system_prompt": system_render.text},
        )
    )

    legacy_primary_caption = _normalize_text(
        payload.figure.title or payload.figure.evidence
    )
    if not legacy_primary_caption:
        legacy_primary_caption = "Representative figure from the source report."
    results: list[dict[str, Any]] = []
    updated_assets: list[ReportFigureAsset] = []
    llm_client = llm_service.build_client_from_callables(
        policy=llm_service.client_policy_from_settings(
            runtime.settings,
            scope="figure_caption",
        ),
        openai_chat_json_with_images=dependencies.openai_chat_json_with_images,
    )
    for index, asset in enumerate(assets, start=1):
        asset_ctx = child_context(caption_ctx, task_id=f"{caption_ctx.task_id}:{index}")
        context_bundle = _build_context_bundle(
            payload=payload,
            asset=asset,
            doc_map=doc_map,
            findings_pack=findings_pack,
            artifacts_payload=artifacts_payload,
        )
        user_render = dependencies.render_prompt(
            PromptRenderRequest(
                schema_version="1.0",
                template=prompt_set.user,
                variables={
                    "max_chars": runtime.settings.figure_caption_max_chars,
                    "context_json": json.dumps(
                        context_bundle, ensure_ascii=False, indent=2
                    ),
                },
            ),
            asset_ctx,
        )
        logger.info(
            log_event(
                asset_ctx,
                role="generator",
                event="figure_caption_prompt_rendered",
                module=logger.name,
                fields={
                    "image_path": asset.image_path,
                    "user_prompt": user_render.text,
                    "context_bundle": context_bundle,
                    "model": resolved_model,
                    "temperature": runtime.settings.figure_caption_temperature,
                },
            )
        )
        image_path = Path(runtime.settings.output_dir) / asset.image_path
        generated_caption = ""
        raw_content = ""
        request_id = None
        prompt_tokens = None
        completion_tokens = None
        total_tokens = None
        error_message = ""
        try:
            response = llm_client.openai_chat_json_with_images(
                OpenAIJSONImagePromptRequest(
                    schema_version="1.0",
                    system_prompt=system_render.text,
                    user_prompt=user_render.text,
                    model=resolved_model,
                    temperature=runtime.settings.figure_caption_temperature,
                    api_key=runtime.settings.openai_api_key,
                    image_paths=[str(image_path)],
                    seed=runtime.settings.openai_seed,
                    timeout_seconds=runtime.settings.figure_caption_timeout_seconds,
                    cost_ledger_path=runtime.settings.cost_ledger_path,
                    cost_daily_path=runtime.settings.cost_daily_path,
                    model_pricing=runtime.settings.model_pricing,
                ),
                asset_ctx,
            )
            raw_content = _normalize_text(response.text)
            parsed = (
                response.parsed_json if isinstance(response.parsed_json, dict) else {}
            )
            generated_caption = _normalize_text(parsed.get("caption"))
            request_id = response.request_id
            prompt_tokens = response.input_tokens
            completion_tokens = response.output_tokens
            total_tokens = response.total_tokens
            if not generated_caption:
                error_message = "empty_caption"
            elif len(generated_caption) > int(
                runtime.settings.figure_caption_max_chars
            ):
                error_message = "caption_too_long"
        except Exception as exc:  # fail-open by design
            error_message = str(exc)

        if error_message:
            display_caption, caption_source = _fallback_display_caption(
                asset=asset,
                index=index,
                legacy_primary_caption=legacy_primary_caption,
            )
            updated_asset = replace(
                asset,
                generated_caption="",
                display_caption=display_caption,
                caption_source=caption_source,
            )
            logger.info(
                log_event(
                    asset_ctx,
                    role="generator",
                    event="figure_caption_failed_open",
                    module=logger.name,
                    fields={
                        "image_path": asset.image_path,
                        "error": error_message,
                        "raw_response": raw_content,
                        "request_id": request_id or "",
                        "caption_source": caption_source,
                        "display_caption": display_caption,
                    },
                )
            )
        else:
            updated_asset = replace(
                asset,
                generated_caption=generated_caption,
                display_caption=generated_caption,
                caption_source="generated",
            )
            logger.info(
                log_event(
                    asset_ctx,
                    role="generator",
                    event="figure_caption_generated",
                    module=logger.name,
                    fields={
                        "image_path": asset.image_path,
                        "caption": generated_caption,
                        "raw_response": raw_content,
                        "request_id": request_id or "",
                        "caption_source": "generated",
                    },
                )
            )
        updated_assets.append(updated_asset)
        results.append(
            {
                "schema_version": "1.0",
                "image_path": asset.image_path,
                "page": asset.page,
                "candidate_id": asset.candidate_id,
                "kind": asset.kind,
                "is_primary": asset.is_primary,
                "context_bundle": context_bundle,
                "model": resolved_model,
                "prompt_namespace": prompt_namespace,
                "prompt_system_sha256": prompt_set.system.sha256,
                "prompt_user_sha256": prompt_set.user.sha256,
                "raw_response": raw_content,
                "request_id": request_id,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "generated_caption": updated_asset.generated_caption,
                "display_caption": updated_asset.display_caption,
                "caption_source": updated_asset.caption_source,
                "error": error_message,
            }
        )

    updated_payload = _apply_asset_captions(
        payload, updated_assets, legacy_primary_caption
    )
    pack_payload = {
        "schema_version": "1.0",
        "prompt_namespace": prompt_namespace,
        "model": resolved_model,
        "temperature": runtime.settings.figure_caption_temperature,
        "max_chars": runtime.settings.figure_caption_max_chars,
        "results": results,
    }
    pack_response = dependencies.analysis_store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name="figure_captions",
            payload=pack_payload,
            report_slug=runtime.report_name,
        ),
        caption_ctx,
    )
    logger.info(
        log_event(
            caption_ctx,
            role="generator",
            event="figure_caption_pack_stored",
            module=logger.name,
            fields={
                "report_id": runtime.file.file_id,
                "path": pack_response.output_path,
                "count": len(results),
            },
        )
    )
    return FigureCaptionGenerationResult(
        schema_version="1.0",
        payload=updated_payload,
        pack_path=pack_response.output_path,
        pack_payload=pack_payload,
    )
