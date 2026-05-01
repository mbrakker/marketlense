from __future__ import annotations

from src.services._config_service.common import *

def _resolve_figure_caption_settings(
    figure_captions_cfg: dict[str, Any],
    *,
    openai_timeout_seconds: float,
) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        figure_captions_cfg,
        [
            _SettingSpec(
                field_name="figure_caption_enabled",
                config_key="enabled",
                default=_to_config_bool(
                    _default_config_value(
                        "ingest", "figure_captions", "enabled", fallback=False
                    ),
                    False,
                ),
                coerce=_to_config_bool,
                env_key="FIGURE_CAPTION_ENABLED",
            ),
            _SettingSpec(
                field_name="figure_caption_temperature",
                config_key="temperature",
                default=_to_float(
                    _default_config_value(
                        "ingest", "figure_captions", "temperature", fallback=0.2
                    ),
                    0.2,
                ),
                coerce=_to_float,
                env_key="FIGURE_CAPTION_TEMPERATURE",
            ),
            _SettingSpec(
                field_name="figure_caption_timeout_seconds",
                config_key="timeout_seconds",
                default=openai_timeout_seconds,
                coerce=_to_float,
                env_key="FIGURE_CAPTION_TIMEOUT_SECONDS",
            ),
            _SettingSpec(
                field_name="figure_caption_max_chars",
                config_key="max_chars",
                default=_to_int(
                    _default_config_value(
                        "ingest", "figure_captions", "max_chars", fallback=500
                    ),
                    500,
                ),
                coerce=_to_int,
                env_key="FIGURE_CAPTION_MAX_CHARS",
                minimum=1,
                minimum_mode="default",
            ),
        ],
    )
    resolved["figure_caption_prompt_namespace"] = _to_str(
        _resolve_setting_raw(
            figure_captions_cfg,
            _SettingSpec(
                field_name="figure_caption_prompt_namespace",
                config_key="prompt_namespace",
                default=str(
                    _default_config_value(
                        "ingest",
                        "figure_captions",
                        "prompt_namespace",
                        fallback="report_vs/figure_caption",
                    )
                ),
                coerce=_to_str,
                env_key="FIGURE_CAPTION_PROMPT_NAMESPACE",
            ),
        ),
        str(
            _default_config_value(
                "ingest",
                "figure_captions",
                "prompt_namespace",
                fallback="report_vs/figure_caption",
            )
        ),
    )
    return resolved


def _resolve_contents_settings(contents_page: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        contents_page,
        [
            _SettingSpec(
                field_name="contents_max_pages",
                config_key="max_pages",
                default=_to_int(
                    _default_config_value(
                        "ingest", "contents_page", "max_pages", fallback=8
                    ),
                    8,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="contents_min_headings",
                config_key="min_headings",
                default=_to_int(
                    _default_config_value(
                        "ingest", "contents_page", "min_headings", fallback=3
                    ),
                    3,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="contents_preview_enabled",
                config_key="preview_enabled",
                default=_to_config_bool(
                    _default_config_value(
                        "ingest", "contents_page", "preview_enabled", fallback=True
                    ),
                    True,
                ),
                coerce=_to_config_bool,
            ),
            _SettingSpec(
                field_name="contents_preview_dpi",
                config_key="render_dpi",
                default=_to_int(
                    _default_config_value(
                        "ingest", "contents_page", "render_dpi", fallback=144
                    ),
                    144,
                ),
                coerce=_to_int,
            ),
        ],
    )
    resolved["contents_keywords"] = _normalize_keyword_list(
        contents_page.get("keywords"),
        default_values=_normalize_keyword_list(
            _default_config_value(
                "ingest",
                "contents_page",
                "keywords",
                fallback=["table of contents", "contents", "index"],
            ),
            default_values=["table of contents", "contents", "index"],
        ),
    )
    return resolved


def _resolve_evidence_pack_settings(
    evidence_packs_cfg: dict[str, Any],
) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        evidence_packs_cfg,
        [
            _SettingSpec(
                field_name="evidence_pack_parallel_workers",
                config_key="parallel_workers",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "evidence_packs",
                        "parallel_workers",
                        fallback=3,
                    ),
                    3,
                ),
                coerce=_to_int,
                env_key="EVIDENCE_PACK_PARALLEL_WORKERS",
                minimum=1,
            ),
            _SettingSpec(
                field_name="evidence_pack_global_max_in_flight",
                config_key="global_max_in_flight",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "evidence_packs",
                        "global_max_in_flight",
                        fallback=2,
                    ),
                    2,
                ),
                coerce=_to_int,
                env_key="EVIDENCE_PACK_GLOBAL_MAX_IN_FLIGHT",
                minimum=1,
            ),
            _SettingSpec(
                field_name="evidence_pack_global_min_interval_ms",
                config_key="global_min_interval_ms",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "evidence_packs",
                        "global_min_interval_ms",
                        fallback=250,
                    ),
                    250,
                ),
                coerce=_to_int,
                env_key="EVIDENCE_PACK_GLOBAL_MIN_INTERVAL_MS",
                minimum=0,
            ),
            _SettingSpec(
                field_name="evidence_pack_doc_map_max_attempts",
                config_key="doc_map_max_attempts",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "evidence_packs",
                        "doc_map_max_attempts",
                        fallback=3,
                    ),
                    3,
                ),
                coerce=_to_int,
                env_key="EVIDENCE_PACK_DOC_MAP_MAX_ATTEMPTS",
                minimum=1,
            ),
            _SettingSpec(
                field_name="evidence_pack_doc_map_retry_delay_ms",
                config_key="doc_map_retry_delay_ms",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "evidence_packs",
                        "doc_map_retry_delay_ms",
                        fallback=500,
                    ),
                    500,
                ),
                coerce=_to_int,
                env_key="EVIDENCE_PACK_DOC_MAP_RETRY_DELAY_MS",
                minimum=0,
            ),
            _SettingSpec(
                field_name="evidence_pack_enable_new_variety_packs",
                config_key="enable_new_variety_packs",
                default=_to_config_bool(
                    _default_config_value(
                        "ingest",
                        "evidence_packs",
                        "enable_new_variety_packs",
                        fallback=False,
                    ),
                    False,
                ),
                coerce=_to_config_bool,
                env_key="EVIDENCE_PACK_ENABLE_NEW_VARIETY_PACKS",
            ),
        ],
    )
    evidence_pack_registry_raw = evidence_packs_cfg.get("registry")
    env_evidence_pack_registry = _env_value("EVIDENCE_PACK_REGISTRY")
    if env_evidence_pack_registry:
        evidence_pack_registry_raw = [
            token.strip()
            for token in env_evidence_pack_registry.split(",")
            if token.strip()
        ]
    resolved["evidence_pack_registry"] = _normalize_evidence_pack_registry(
        evidence_pack_registry_raw
    )
    return resolved


def _resolve_artifact_settings(artifacts_cfg: dict[str, Any]) -> dict[str, Any]:
    return _resolve_scalar_settings(
        artifacts_cfg,
        [
            _SettingSpec(
                field_name="artifact_parallel_workers",
                config_key="parallel_workers",
                default=_to_int(
                    _default_config_value(
                        "ingest", "artifacts", "parallel_workers", fallback=4
                    ),
                    4,
                ),
                coerce=_to_int,
                env_key="ARTIFACT_PARALLEL_WORKERS",
                minimum=1,
            ),
            _SettingSpec(
                field_name="artifact_global_max_in_flight",
                config_key="global_max_in_flight",
                default=_to_int(
                    _default_config_value(
                        "ingest", "artifacts", "global_max_in_flight", fallback=2
                    ),
                    2,
                ),
                coerce=_to_int,
                env_key="ARTIFACT_GLOBAL_MAX_IN_FLIGHT",
                minimum=1,
            ),
            _SettingSpec(
                field_name="artifact_global_min_interval_ms",
                config_key="global_min_interval_ms",
                default=_to_int(
                    _default_config_value(
                        "ingest", "artifacts", "global_min_interval_ms", fallback=250
                    ),
                    250,
                ),
                coerce=_to_int,
                env_key="ARTIFACT_GLOBAL_MIN_INTERVAL_MS",
                minimum=0,
            ),
        ],
    )


def _resolve_pdf_text_settings(
    pdf_text: dict[str, Any],
    ingest: dict[str, Any],
) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        pdf_text,
        [
            _SettingSpec(
                field_name="pdf_text_max_pages",
                config_key="max_pages",
                default=_to_int(
                    _default_config_value(
                        "ingest", "pdf_text", "max_pages", fallback=5
                    ),
                    5,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="pdf_text_max_chars",
                config_key="max_chars",
                default=_to_int(
                    _default_config_value(
                        "ingest", "pdf_text", "max_chars", fallback=80_000
                    ),
                    80_000,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="pdf_text_min_density",
                config_key="min_density",
                default=_to_float(
                    _default_config_value(
                        "ingest", "pdf_text", "min_density", fallback=250.0
                    ),
                    250.0,
                ),
                coerce=_to_float,
            ),
            _SettingSpec(
                field_name="pdf_text_sample_pages",
                config_key="sample_pages",
                default=_to_int(
                    _default_config_value(
                        "ingest", "pdf_text", "sample_pages", fallback=3
                    ),
                    3,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="pdf_text_native_confidence_threshold",
                config_key="native_confidence_threshold",
                default=_to_float(
                    _default_config_value(
                        "ingest",
                        "pdf_text",
                        "native_confidence_threshold",
                        fallback=0.55,
                    ),
                    0.55,
                ),
                coerce=_to_float,
            ),
            _SettingSpec(
                field_name="pdf_text_native_page_confidence_threshold",
                config_key="native_page_confidence_threshold",
                default=_to_float(
                    _default_config_value(
                        "ingest",
                        "pdf_text",
                        "native_page_confidence_threshold",
                        fallback=0.35,
                    ),
                    0.35,
                ),
                coerce=_to_float,
            ),
        ],
    )
    ocr_fallback_cfg = pdf_text.get("ocr_fallback") or {}
    resolved.update(
        _resolve_scalar_settings(
            ocr_fallback_cfg,
            [
                _SettingSpec(
                    field_name="pdf_text_ocr_enabled",
                    config_key="enabled",
                    default=_to_bool(
                        _default_config_value(
                            "ingest",
                            "pdf_text",
                            "ocr_fallback",
                            "enabled",
                            fallback=False,
                        ),
                        False,
                    ),
                    coerce=_to_bool,
                ),
                _SettingSpec(
                    field_name="pdf_text_ocr_timeout_seconds",
                    config_key="timeout_seconds",
                    default=_to_float(ingest.get("timeout_seconds"), 600.0),
                    coerce=_to_float,
                ),
                _SettingSpec(
                    field_name="pdf_text_ocr_cache_enabled",
                    config_key="cache_enabled",
                    default=_to_bool(
                        _default_config_value(
                            "ingest",
                            "pdf_text",
                            "ocr_fallback",
                            "cache_enabled",
                            fallback=True,
                        ),
                        True,
                    ),
                    coerce=_to_bool,
                ),
                _SettingSpec(
                    field_name="pdf_text_ocr_chunk_page_count",
                    config_key="chunk_page_count",
                    default=_to_int(
                        _default_config_value(
                            "ingest",
                            "pdf_text",
                            "ocr_fallback",
                            "chunk_page_count",
                            fallback=8,
                        ),
                        8,
                    ),
                    coerce=_to_int,
                    minimum=1,
                ),
            ],
        )
    )
    resolved["pdf_text_ocr_policy"] = _resolve_allowed_string(
        ocr_fallback_cfg.get("policy"),
        default=str(
            _default_config_value(
                "ingest",
                "pdf_text",
                "ocr_fallback",
                "policy",
                fallback="native_first_selective",
            )
        ).strip()
        or "native_first_selective",
        allowed={"native_first_selective", "always"},
    )
    resolved["pdf_text_ocr_model"] = _to_str(
        ocr_fallback_cfg.get("model"),
        str(
            _default_config_value(
                "ingest", "pdf_text", "ocr_fallback", "model", fallback="gpt-5-mini"
            )
        ),
    )
    resolved["pdf_text_ocr_prompt_namespace"] = _to_str(
        ocr_fallback_cfg.get("prompt_namespace"),
        str(
            _default_config_value(
                "ingest",
                "pdf_text",
                "ocr_fallback",
                "prompt_namespace",
                fallback="pdf_text/ocr_fallback",
            )
        ),
    )
    return resolved

__all__ = [name for name in globals() if not name.startswith("__")]
