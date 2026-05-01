from __future__ import annotations

from src.services._config_service.common import *
from src.services._config_service.settings_resolvers import *

def _to_ingest_settings(app_settings: AppSettings) -> IngestSettings:
    payload = asdict(app_settings)
    allowed = {field.name for field in fields(IngestSettings)}
    filtered_payload = {key: value for key, value in payload.items() if key in allowed}
    return IngestSettings(**filtered_payload)


def build_ingest_settings(
    request: IngestSettingsBuildRequest, ctx: RunContext
) -> IngestSettings:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ingest_settings_build_start",
            module=logger.name,
            fields={
                "output_dir": request.app_settings.output_dir,
                "cache_dir": request.app_settings.cache_dir,
                "state_db": request.app_settings.state_db,
                "reports_db": request.app_settings.reports_db,
            },
        )
    )
    settings = _to_ingest_settings(request.app_settings)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ingest_settings_build_complete",
            module=logger.name,
            fields={
                "gdrive_folder_id": settings.gdrive_folder_id,
                "openai_model": settings.openai_model,
                "batch_limit": settings.batch_limit,
                "ingest_worker_limit": settings.ingest_worker_limit,
                "report_worker_limit": settings.report_worker_limit,
            },
        )
    )
    return settings


def _ensure_app_settings_directories(settings: AppSettings) -> None:
    _ensure_app_settings_directories(settings)


def _config_load_complete_fields(
    settings: AppSettings,
    *,
    paths_settings: dict[str, str],
) -> dict[str, Any]:
    return {
        "output_dir": settings.output_dir,
        "cache_dir": settings.cache_dir,
        "state_db": settings.state_db,
        "reports_db": settings.reports_db,
        "publisher_profiles_path": settings.publisher_profiles_path,
        "category_mapping_path": settings.category_mapping_path,
        "html_tag_acronyms_path": paths_settings["html_tag_acronyms_path"],
        "ingest_lock_path": settings.ingest_lock_path,
        "ingest_lock_ttl_seconds": settings.ingest_lock_ttl_seconds,
        "drive_supports_all_drives": settings.drive_supports_all_drives,
        "drive_include_items_from_all_drives": settings.drive_include_items_from_all_drives,
        "drive_id": settings.drive_id or "",
        "drive_list_mode": settings.drive_list_mode,
        "openai_model": settings.openai_model,
        "openai_models": settings.openai_models,
        "temperature": settings.temperature,
        "taxonomy_temperature": settings.taxonomy_temperature,
        "ingest_worker_limit": settings.ingest_worker_limit,
        "report_worker_limit": settings.report_worker_limit,
        "openai_seed": settings.openai_seed,
        "rank_model": settings.rank_model,
        "rank_temperature": settings.rank_temperature,
        "rank_seed": settings.rank_seed,
        "rank_max_candidates": settings.rank_max_candidates,
        "rank_selected_max": settings.rank_selected_max,
        "rank_min_overall_score": settings.rank_min_overall_score,
        "rank_min_quality_score": settings.rank_min_quality_score,
        "rank_min_insight_score": settings.rank_min_insight_score,
        "rank_min_data_score": settings.rank_min_data_score,
        "crop_refine_enabled": settings.crop_refine_enabled,
        "crop_refine_mode": settings.crop_refine_mode,
        "crop_refine_page_dpi": settings.crop_refine_page_dpi,
        "crop_refine_temperature": settings.crop_refine_temperature,
        "crop_refine_timeout_seconds": settings.crop_refine_timeout_seconds,
        "figure_caption_enabled": settings.figure_caption_enabled,
        "figure_caption_temperature": settings.figure_caption_temperature,
        "figure_caption_timeout_seconds": settings.figure_caption_timeout_seconds,
        "figure_caption_prompt_namespace": settings.figure_caption_prompt_namespace,
        "figure_caption_max_chars": settings.figure_caption_max_chars,
        "pdf_text_max_pages": settings.pdf_text_max_pages,
        "pdf_text_max_chars": settings.pdf_text_max_chars,
        "pdf_text_min_density": settings.pdf_text_min_density,
        "pdf_text_sample_pages": settings.pdf_text_sample_pages,
        "pdf_text_native_confidence_threshold": settings.pdf_text_native_confidence_threshold,
        "pdf_text_native_page_confidence_threshold": settings.pdf_text_native_page_confidence_threshold,
        "pdf_text_ocr_enabled": settings.pdf_text_ocr_enabled,
        "pdf_text_ocr_policy": settings.pdf_text_ocr_policy,
        "pdf_text_ocr_model": settings.pdf_text_ocr_model,
        "pdf_text_ocr_timeout_seconds": settings.pdf_text_ocr_timeout_seconds,
        "pdf_text_ocr_prompt_namespace": settings.pdf_text_ocr_prompt_namespace,
        "pdf_text_ocr_cache_enabled": settings.pdf_text_ocr_cache_enabled,
        "pdf_text_ocr_chunk_page_count": settings.pdf_text_ocr_chunk_page_count,
        "openai_timeout_seconds": settings.openai_timeout_seconds,
        "llm_retry_retries": settings.llm_retry_retries,
        "llm_retry_base_delay_seconds": settings.llm_retry_base_delay_seconds,
        "llm_retry_backoff_step_seconds": settings.llm_retry_backoff_step_seconds,
        "llm_retry_jitter_seconds": settings.llm_retry_jitter_seconds,
        "llm_circuit_breaker_failure_threshold": settings.llm_circuit_breaker_failure_threshold,
        "llm_circuit_breaker_recovery_seconds": settings.llm_circuit_breaker_recovery_seconds,
        "rank_timeout_seconds": settings.rank_timeout_seconds,
        "contents_max_pages": settings.contents_max_pages,
        "contents_min_headings": settings.contents_min_headings,
        "contents_keywords": settings.contents_keywords,
        "contents_preview_enabled": settings.contents_preview_enabled,
        "contents_preview_dpi": settings.contents_preview_dpi,
        "evidence_pack_parallel_workers": settings.evidence_pack_parallel_workers,
        "evidence_pack_global_max_in_flight": settings.evidence_pack_global_max_in_flight,
        "evidence_pack_global_min_interval_ms": settings.evidence_pack_global_min_interval_ms,
        "evidence_pack_doc_map_max_attempts": settings.evidence_pack_doc_map_max_attempts,
        "evidence_pack_doc_map_retry_delay_ms": settings.evidence_pack_doc_map_retry_delay_ms,
        "evidence_pack_registry": settings.evidence_pack_registry,
        "evidence_pack_enable_new_variety_packs": settings.evidence_pack_enable_new_variety_packs,
        "artifact_parallel_workers": settings.artifact_parallel_workers,
        "artifact_global_max_in_flight": settings.artifact_global_max_in_flight,
        "artifact_global_min_interval_ms": settings.artifact_global_min_interval_ms,
        "vector_store_keep": settings.vector_store_keep,
        "artifacts_use_vector_store": settings.artifacts_use_vector_store,
        "validation_grounding_use_vector_store": settings.validation_grounding_use_vector_store,
        "strict_schema_validation": settings.strict_schema_validation,
        "cover_cache_enabled": settings.cover_cache_enabled,
        "cost_ledger_path": settings.cost_ledger_path,
        "cost_daily_path": settings.cost_daily_path,
        "html_tag_acronyms": settings.html_tag_acronyms,
        "html_tag_acronyms_count": len(settings.html_tag_acronyms),
        "validation_data_gap_policy": settings.validation_data_gap_policy,
        "validation_regeneration_max_attempts": settings.validation_regeneration_max_attempts,
    }


def load_settings(request: ConfigLoadRequest, ctx: RunContext) -> AppSettings:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))

    logger.info(
        log_event(
            ctx,
            role="service",
            event="config_load_start",
            module=logger.name,
            fields={"path": request.path or str(CONFIG_PATH)},
        )
    )
    sections = _load_config_sections(request)
    resolver = sections.resolver
    need = resolver.need
    need_env = resolver.need_env

    paths_settings = _resolve_paths_settings(sections.paths, resolver)
    openai_model = str(
        sections.ingest.get("openai_model")
        or _env_value("OPENAI_MODEL")
        or _default_config_value("ingest", "openai_model", fallback="")
    ).strip()
    if not openai_model:
        resolver.missing.append("ingest.openai_model|env:OPENAI_MODEL")
    ingest_runtime = _resolve_ingest_runtime_settings(sections.ingest)
    llm_runtime = _resolve_llm_runtime_settings(sections.llm_cfg)
    rank_settings = _resolve_rank_settings(
        sections.rank,
        openai_model=openai_model,
        temperature=ingest_runtime["temperature"],
        openai_timeout_seconds=ingest_runtime["openai_timeout_seconds"],
    )
    figure_caption_settings = _resolve_figure_caption_settings(
        sections.figure_captions_cfg,
        openai_timeout_seconds=ingest_runtime["openai_timeout_seconds"],
    )
    contents_settings = _resolve_contents_settings(sections.contents_page)
    evidence_pack_settings = _resolve_evidence_pack_settings(
        sections.evidence_packs_cfg
    )
    artifact_settings = _resolve_artifact_settings(sections.artifacts_cfg)
    pdf_text_settings = _resolve_pdf_text_settings(
        sections.pdf_text,
        sections.ingest,
    )
    validation_settings = _resolve_validation_settings(sections.validation_cfg)
    analysis_settings = _resolve_analysis_settings(
        sections.analysis_cfg,
        sections.cost_cfg,
        html_tag_acronyms_path=paths_settings["html_tag_acronyms_path"],
    )
    drive_settings = _resolve_drive_settings(sections.drive_cfg)
    drive_auth_settings = _resolve_drive_auth_settings(
        sections.ingest,
        sections.drive_cfg,
        runtime_base_path=sections.runtime_base_path,
        resolver=resolver,
    )

    settings = AppSettings(
        schema_version=str(sections.data.get("schema_version", "1.0")),
        google_sa_path=drive_auth_settings["google_sa_path"],
        gdrive_folder_id=need(
            sections.ingest,
            "gdrive_folder_id",
            "ingest.gdrive_folder_id",
            "GDRIVE_FOLDER_ID",
        ),
        drive_auth_mode=drive_auth_settings["drive_auth_mode"],
        google_oauth_client_path=drive_auth_settings["google_oauth_client_path"],
        google_oauth_token_path=drive_auth_settings["google_oauth_token_path"],
        drive_supports_all_drives=drive_settings["drive_supports_all_drives"],
        drive_include_items_from_all_drives=drive_settings[
            "drive_include_items_from_all_drives"
        ],
        drive_id=drive_settings["drive_id"],
        drive_list_mode=drive_settings["drive_list_mode"],
        openai_api_key=need_env("OPENAI_API_KEY"),
        openai_model=openai_model,
        openai_models=_normalize_openai_models(
            sections.data.get("openai_models")
            or _default_config_value("openai_models", fallback={})
        ),
        batch_limit=ingest_runtime["batch_limit"],
        ingest_worker_limit=ingest_runtime["ingest_worker_limit"],
        report_worker_limit=ingest_runtime["report_worker_limit"],
        output_dir=paths_settings["output_dir"],
        cache_dir=paths_settings["cache_dir"],
        state_db=paths_settings["state_db"],
        reports_db=paths_settings["reports_db"],
        publisher_profiles_path=paths_settings["publisher_profiles_path"],
        category_mapping_path=paths_settings["category_mapping_path"],
        cover_style_path=paths_settings["cover_style_path"],
        ingest_lock_path=paths_settings["ingest_lock_path"],
        ingest_lock_ttl_seconds=ingest_runtime["ingest_lock_ttl_seconds"],
        temperature=ingest_runtime["temperature"],
        taxonomy_temperature=ingest_runtime["taxonomy_temperature"],
        openai_seed=ingest_runtime["openai_seed"],
        pdf_text_max_pages=pdf_text_settings["pdf_text_max_pages"],
        pdf_text_max_chars=pdf_text_settings["pdf_text_max_chars"],
        pdf_text_min_density=pdf_text_settings["pdf_text_min_density"],
        pdf_text_sample_pages=pdf_text_settings["pdf_text_sample_pages"],
        pdf_text_native_confidence_threshold=pdf_text_settings[
            "pdf_text_native_confidence_threshold"
        ],
        pdf_text_native_page_confidence_threshold=pdf_text_settings[
            "pdf_text_native_page_confidence_threshold"
        ],
        pdf_text_ocr_enabled=pdf_text_settings["pdf_text_ocr_enabled"],
        pdf_text_ocr_policy=pdf_text_settings["pdf_text_ocr_policy"],
        pdf_text_ocr_model=pdf_text_settings["pdf_text_ocr_model"],
        pdf_text_ocr_timeout_seconds=pdf_text_settings["pdf_text_ocr_timeout_seconds"],
        pdf_text_ocr_prompt_namespace=pdf_text_settings[
            "pdf_text_ocr_prompt_namespace"
        ],
        pdf_text_ocr_cache_enabled=pdf_text_settings["pdf_text_ocr_cache_enabled"],
        pdf_text_ocr_chunk_page_count=pdf_text_settings[
            "pdf_text_ocr_chunk_page_count"
        ],
        rank_model=rank_settings["rank_model"],
        rank_temperature=rank_settings["rank_temperature"],
        rank_seed=rank_settings["rank_seed"],
        rank_max_candidates=rank_settings["rank_max_candidates"],
        rank_selected_max=rank_settings["rank_selected_max"],
        rank_min_overall_score=rank_settings["rank_min_overall_score"],
        rank_min_quality_score=rank_settings["rank_min_quality_score"],
        rank_min_insight_score=rank_settings["rank_min_insight_score"],
        rank_min_data_score=rank_settings["rank_min_data_score"],
        crop_refine_enabled=rank_settings["crop_refine_enabled"],
        crop_refine_mode=rank_settings["crop_refine_mode"],
        crop_refine_page_dpi=rank_settings["crop_refine_page_dpi"],
        crop_refine_temperature=rank_settings["crop_refine_temperature"],
        crop_refine_timeout_seconds=rank_settings["crop_refine_timeout_seconds"],
        figure_caption_enabled=figure_caption_settings["figure_caption_enabled"],
        figure_caption_temperature=figure_caption_settings[
            "figure_caption_temperature"
        ],
        figure_caption_timeout_seconds=figure_caption_settings[
            "figure_caption_timeout_seconds"
        ],
        figure_caption_prompt_namespace=figure_caption_settings[
            "figure_caption_prompt_namespace"
        ],
        figure_caption_max_chars=figure_caption_settings["figure_caption_max_chars"],
        openai_timeout_seconds=ingest_runtime["openai_timeout_seconds"],
        llm_retry_retries=llm_runtime["llm_retry_retries"],
        llm_retry_base_delay_seconds=llm_runtime["llm_retry_base_delay_seconds"],
        llm_retry_backoff_step_seconds=llm_runtime["llm_retry_backoff_step_seconds"],
        llm_retry_jitter_seconds=llm_runtime["llm_retry_jitter_seconds"],
        llm_circuit_breaker_failure_threshold=llm_runtime[
            "llm_circuit_breaker_failure_threshold"
        ],
        llm_circuit_breaker_recovery_seconds=llm_runtime[
            "llm_circuit_breaker_recovery_seconds"
        ],
        rank_timeout_seconds=rank_settings["rank_timeout_seconds"],
        contents_max_pages=contents_settings["contents_max_pages"],
        contents_min_headings=contents_settings["contents_min_headings"],
        contents_keywords=contents_settings["contents_keywords"],
        contents_preview_enabled=contents_settings["contents_preview_enabled"],
        contents_preview_dpi=contents_settings["contents_preview_dpi"],
        evidence_pack_parallel_workers=evidence_pack_settings[
            "evidence_pack_parallel_workers"
        ],
        evidence_pack_global_max_in_flight=evidence_pack_settings[
            "evidence_pack_global_max_in_flight"
        ],
        evidence_pack_global_min_interval_ms=evidence_pack_settings[
            "evidence_pack_global_min_interval_ms"
        ],
        evidence_pack_doc_map_max_attempts=evidence_pack_settings[
            "evidence_pack_doc_map_max_attempts"
        ],
        evidence_pack_doc_map_retry_delay_ms=evidence_pack_settings[
            "evidence_pack_doc_map_retry_delay_ms"
        ],
        evidence_pack_registry=evidence_pack_settings["evidence_pack_registry"],
        evidence_pack_enable_new_variety_packs=evidence_pack_settings[
            "evidence_pack_enable_new_variety_packs"
        ],
        artifact_parallel_workers=artifact_settings["artifact_parallel_workers"],
        artifact_global_max_in_flight=artifact_settings[
            "artifact_global_max_in_flight"
        ],
        artifact_global_min_interval_ms=artifact_settings[
            "artifact_global_min_interval_ms"
        ],
        vector_store_keep=analysis_settings["vector_store_keep"],
        artifacts_use_vector_store=analysis_settings["artifacts_use_vector_store"],
        validation_grounding_use_vector_store=analysis_settings[
            "validation_grounding_use_vector_store"
        ],
        strict_schema_validation=analysis_settings["strict_schema_validation"],
        cover_cache_enabled=ingest_runtime["cover_cache_enabled"],
        cost_ledger_path=analysis_settings["cost_ledger_path"],
        cost_daily_path=analysis_settings["cost_daily_path"],
        model_pricing=analysis_settings["model_pricing"],
        html_tag_acronyms=analysis_settings["html_tag_acronyms"],
        validation_data_gap_policy=validation_settings["validation_data_gap_policy"],
        validation_regeneration_max_attempts=validation_settings[
            "validation_regeneration_max_attempts"
        ],
    )

    if resolver.missing:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="config_load_failed",
                module=logger.name,
                fields={"missing": resolver.missing},
            )
        )
        raise RuntimeError(
            f"Missing required config/env values: {', '.join(resolver.missing)}"
        )
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.state_db).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.reports_db).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.ingest_lock_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.cost_ledger_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.cost_daily_path).parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="config_load_complete",
            module=logger.name,
            fields=_config_load_complete_fields(
                settings,
                paths_settings=paths_settings,
            ),
        )
    )
    return settings

__all__ = [name for name in globals() if not name.startswith("__")]
