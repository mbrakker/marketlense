from __future__ import annotations

from copy import deepcopy
from typing import Any

import streamlit as st
import yaml

from src.utils.coercion import (
    coerce_extended_bool as _as_bool,
)
from src.utils.coercion import (
    coerce_float as _as_float,
)
from src.utils.coercion import (
    coerce_int as _as_int,
)
from src.utils.gui_utils import (
    mapping_from_editor_records,
    normalize_text_lines,
    pricing_from_editor_records,
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _optional_int_from_text(value: str, *, field: str, errors: list[str]) -> int | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        errors.append(f"{field} must be an integer or blank.")
        return None


def render_structured_config_form(
    config_payload: dict[str, Any], *, editor_key: str
) -> None:
    working = deepcopy(config_payload)
    if not isinstance(working.get("paths"), dict):
        working["paths"] = {}
    if not isinstance(working.get("ingest"), dict):
        working["ingest"] = {}
    if not isinstance(working.get("openai_models"), dict):
        working["openai_models"] = {}
    if not isinstance(working.get("rank"), dict):
        working["rank"] = {}
    if not isinstance(working.get("publish"), dict):
        working["publish"] = {}
    if not isinstance(working.get("analysis"), dict):
        working["analysis"] = {}
    if not isinstance(working.get("cost"), dict):
        working["cost"] = {}

    paths = _as_mapping(working.get("paths"))
    ingest = _as_mapping(working.get("ingest"))
    if not isinstance(ingest.get("drive"), dict):
        ingest["drive"] = {}
    if not isinstance(ingest.get("pdf_text"), dict):
        ingest["pdf_text"] = {}
    if not isinstance(ingest.get("validation"), dict):
        ingest["validation"] = {}
    if not isinstance(ingest.get("contents_page"), dict):
        ingest["contents_page"] = {}
    if not isinstance(ingest.get("evidence_packs"), dict):
        ingest["evidence_packs"] = {}
    if not isinstance(ingest.get("artifacts"), dict):
        ingest["artifacts"] = {}
    drive = _as_mapping(ingest.get("drive"))
    pdf_text = _as_mapping(ingest.get("pdf_text"))
    ingest_validation = _as_mapping(ingest.get("validation"))
    contents_page = _as_mapping(ingest.get("contents_page"))
    evidence_packs = _as_mapping(ingest.get("evidence_packs"))
    artifacts = _as_mapping(ingest.get("artifacts"))
    openai_models = _as_mapping(working.get("openai_models"))
    rank = _as_mapping(working.get("rank"))
    publish = _as_mapping(working.get("publish"))
    if not isinstance(publish.get("wp"), dict):
        publish["wp"] = {}
    if not isinstance(publish.get("validation"), dict):
        publish["validation"] = {}
    wp = _as_mapping(publish.get("wp"))
    publish_validation = _as_mapping(publish.get("validation"))
    analysis = _as_mapping(working.get("analysis"))
    cost = _as_mapping(working.get("cost"))
    pricing = _as_mapping(cost.get("pricing"))

    st.markdown(
        '<div class="ml-panel"><h4>Structured Editor</h4><p>Edit config by fields, apply changes, then use YAML tab to save.</p></div>',
        unsafe_allow_html=True,
    )

    with st.form("app_yaml_structured_form", border=False):
        st.subheader("Core")
        core_col1, core_col2, core_col3 = st.columns(3, gap="large")
        with core_col1:
            schema_version = st.text_input(
                "Schema Version", value=_as_str(working.get("schema_version"), "1.0")
            )
        with core_col2:
            ingest_openai_model = st.text_input(
                "Ingest OpenAI Model",
                value=_as_str(ingest.get("openai_model"), "gpt-5.6-luna"),
            )
        with core_col3:
            rank_model = st.text_input(
                "Rank Model", value=_as_str(rank.get("model"), ingest_openai_model)
            )

        with st.expander("Paths", expanded=True):
            p1, p2 = st.columns(2, gap="large")
            with p1:
                path_output_dir = st.text_input(
                    "Output Dir", value=_as_str(paths.get("output_dir"), "./out")
                )
                path_state_db = st.text_input(
                    "State DB",
                    value=_as_str(paths.get("state_db"), "./state/index.sqlite"),
                )
                path_category_mappings = st.text_input(
                    "Category Mappings YAML",
                    value=_as_str(
                        paths.get("category_mappings"),
                        "./src/config/category-mappings.yaml",
                    ),
                )
                path_cover_styles = st.text_input(
                    "Cover Styles YAML",
                    value=_as_str(
                        paths.get("cover_styles"), "./src/config/cover-styles.yaml"
                    ),
                )
            with p2:
                path_cache_dir = st.text_input(
                    "Cache Dir", value=_as_str(paths.get("cache_dir"), "./cache")
                )
                path_reports_db = st.text_input(
                    "Reports DB",
                    value=_as_str(paths.get("reports_db"), "./state/reports.sqlite"),
                )
                path_html_tag_acronyms = st.text_input(
                    "HTML Tag Acronyms YAML",
                    value=_as_str(
                        paths.get("html_tag_acronyms"),
                        "./src/config/html-tag-acronyms.yaml",
                    ),
                )
                path_ingest_lock = st.text_input(
                    "Ingest Lock Path",
                    value=_as_str(paths.get("ingest_lock"), "./state/ingest.lock"),
                )

        with st.expander("Ingest Core", expanded=True):
            i1, i2, i3 = st.columns(3, gap="large")
            with i1:
                ingest_google_sa_path = st.text_input(
                    "Google SA Path",
                    value=_as_str(ingest.get("google_sa_path"), "./sa.json"),
                )
                ingest_temperature = st.number_input(
                    "Ingest Temperature",
                    value=_as_float(ingest.get("temperature"), 1.0),
                    step=0.1,
                    format="%.3f",
                )
                ingest_batch_limit = st.number_input(
                    "Batch Limit",
                    value=_as_int(ingest.get("batch_limit"), 20),
                    min_value=1,
                    step=1,
                )
                ingest_worker_limit = st.number_input(
                    "Worker Limit",
                    value=_as_int(ingest.get("worker_limit"), 2),
                    min_value=1,
                    step=1,
                )
            with i2:
                ingest_gdrive_folder_id = st.text_input(
                    "GDrive Folder ID",
                    value=_as_str(ingest.get("gdrive_folder_id"), ""),
                )
                ingest_timeout_seconds = st.number_input(
                    "OpenAI Timeout Seconds",
                    value=_as_float(ingest.get("timeout_seconds"), 600.0),
                    min_value=1.0,
                    step=1.0,
                    format="%.1f",
                )
                ingest_report_worker_limit = st.number_input(
                    "Report Worker Limit",
                    value=_as_int(ingest.get("report_worker_limit"), 2),
                    min_value=1,
                    step=1,
                )
                ingest_lock_ttl_seconds = st.number_input(
                    "Lock TTL Seconds",
                    value=_as_float(ingest.get("lock_ttl_seconds"), 7200.0),
                    min_value=0.0,
                    step=60.0,
                    format="%.1f",
                )
            with i3:
                ingest_seed_text = st.text_input(
                    "Ingest Seed (blank for null)",
                    value=""
                    if ingest.get("seed") in {None, ""}
                    else _as_str(ingest.get("seed")),
                )

        with st.expander("Drive", expanded=False):
            d1, d2 = st.columns(2, gap="large")
            with d1:
                drive_supports_all_drives = st.checkbox(
                    "Supports All Drives",
                    value=_as_bool(drive.get("supports_all_drives"), True),
                )
                drive_include_items_from_all_drives = st.checkbox(
                    "Include Items From All Drives",
                    value=_as_bool(drive.get("include_items_from_all_drives"), True),
                )
            with d2:
                drive_id = st.text_input(
                    "Drive ID (optional)", value=_as_str(drive.get("drive_id"), "")
                )
                drive_list_mode = st.selectbox(
                    "Drive List Mode",
                    options=["metadata", "full"],
                    index=0
                    if _as_str(drive.get("list_mode"), "metadata").strip().lower()
                    != "full"
                    else 1,
                )

        with st.expander("PDF Text & Contents", expanded=False):
            pt1, pt2 = st.columns(2, gap="large")
            with pt1:
                pdf_text_max_pages = st.number_input(
                    "PDF Text Max Pages",
                    value=_as_int(pdf_text.get("max_pages"), 5),
                    min_value=1,
                    step=1,
                )
                pdf_text_max_chars = st.number_input(
                    "PDF Text Max Chars",
                    value=_as_int(pdf_text.get("max_chars"), 80000),
                    min_value=1000,
                    step=1000,
                )
                pdf_text_min_density = st.number_input(
                    "PDF Text Min Density",
                    value=_as_float(pdf_text.get("min_density"), 250.0),
                    min_value=0.0,
                    step=10.0,
                )
                pdf_text_sample_pages = st.number_input(
                    "PDF Text Sample Pages",
                    value=_as_int(pdf_text.get("sample_pages"), 3),
                    min_value=1,
                    step=1,
                )
            with pt2:
                contents_max_pages = st.number_input(
                    "Contents Max Pages",
                    value=_as_int(contents_page.get("max_pages"), 8),
                    min_value=1,
                    step=1,
                )
                contents_min_headings = st.number_input(
                    "Contents Min Headings",
                    value=_as_int(contents_page.get("min_headings"), 3),
                    min_value=1,
                    step=1,
                )
                contents_preview_enabled = st.checkbox(
                    "Contents Preview Enabled",
                    value=_as_bool(contents_page.get("preview_enabled"), True),
                )
                contents_render_dpi = st.number_input(
                    "Contents Render DPI",
                    value=_as_int(contents_page.get("render_dpi"), 144),
                    min_value=72,
                    step=1,
                )
            raw_keywords = contents_page.get("keywords")
            keywords_default: list[Any] = (
                raw_keywords if isinstance(raw_keywords, list) else []
            )
            contents_keywords_text = st.text_area(
                "Contents Keywords (one per line)",
                value="\n".join(
                    str(item).strip() for item in keywords_default if str(item).strip()
                ),
                height=100,
            )

        with st.expander("Validation + Parallelism", expanded=False):
            vp1, vp2, vp3 = st.columns(3, gap="large")
            with vp1:
                validation_data_gap_policy = st.selectbox(
                    "Validation Data Gap Policy",
                    options=["warn", "fail"],
                    index=0
                    if _as_str(ingest_validation.get("data_gap_policy"), "warn")
                    .strip()
                    .lower()
                    != "fail"
                    else 1,
                )
            with vp2:
                evidence_parallel_workers = st.number_input(
                    "Evidence Packs Parallel Workers",
                    value=_as_int(evidence_packs.get("parallel_workers"), 3),
                    min_value=1,
                    step=1,
                )
                evidence_global_max_in_flight = st.number_input(
                    "Evidence Packs Global Max In Flight",
                    value=_as_int(evidence_packs.get("global_max_in_flight"), 2),
                    min_value=1,
                    step=1,
                )
                evidence_global_min_interval_ms = st.number_input(
                    "Evidence Packs Global Min Interval (ms)",
                    value=_as_int(evidence_packs.get("global_min_interval_ms"), 250),
                    min_value=0,
                    step=1,
                )
            with vp3:
                artifact_parallel_workers = st.number_input(
                    "Artifacts Parallel Workers",
                    value=_as_int(artifacts.get("parallel_workers"), 4),
                    min_value=1,
                    step=1,
                )
                artifact_global_max_in_flight = st.number_input(
                    "Artifacts Global Max In Flight",
                    value=_as_int(artifacts.get("global_max_in_flight"), 2),
                    min_value=1,
                    step=1,
                )
                artifact_global_min_interval_ms = st.number_input(
                    "Artifacts Global Min Interval (ms)",
                    value=_as_int(artifacts.get("global_min_interval_ms"), 250),
                    min_value=0,
                    step=1,
                )

        with st.expander("OpenAI Namespace Model Overrides", expanded=False):
            openai_rows = [
                {"namespace": key, "model": value}
                for key, value in sorted(openai_models.items())
            ]
            openai_models_editor = st.data_editor(
                openai_rows,
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
            )

        with st.expander("Rank", expanded=False):
            r1, r2, r3 = st.columns(3, gap="large")
            with r1:
                rank_temperature = st.number_input(
                    "Rank Temperature",
                    value=_as_float(rank.get("temperature"), 1.0),
                    step=0.1,
                    format="%.3f",
                )
                rank_timeout_seconds = st.number_input(
                    "Rank Timeout Seconds",
                    value=_as_float(rank.get("timeout_seconds"), 600.0),
                    min_value=1.0,
                    step=1.0,
                    format="%.1f",
                )
                rank_seed_text = st.text_input(
                    "Rank Seed (blank for null)",
                    value=""
                    if rank.get("seed") in {None, ""}
                    else _as_str(rank.get("seed")),
                )
                rank_max_candidates = st.number_input(
                    "Rank Max Candidates",
                    value=_as_int(rank.get("max_candidates"), 40),
                    min_value=1,
                    step=1,
                )
                rank_selected_max = st.number_input(
                    "Rank Selected Max",
                    value=_as_int(rank.get("selected_max"), 5),
                    min_value=1,
                    step=1,
                )
            with r2:
                rank_min_overall_score = st.number_input(
                    "Rank Min Overall Score",
                    value=_as_int(rank.get("min_overall_score"), 78),
                    min_value=0,
                    max_value=100,
                    step=1,
                )
                rank_min_quality_score = st.number_input(
                    "Rank Min Quality Score",
                    value=_as_int(rank.get("min_quality_score"), 75),
                    min_value=0,
                    max_value=100,
                    step=1,
                )
                rank_min_insight_score = st.number_input(
                    "Rank Min Insight Score",
                    value=_as_int(rank.get("min_insight_score"), 75),
                    min_value=0,
                    max_value=100,
                    step=1,
                )
                rank_min_data_score = st.number_input(
                    "Rank Min Data Score",
                    value=_as_int(rank.get("min_data_score"), 70),
                    min_value=0,
                    max_value=100,
                    step=1,
                )
            with r3:
                rank_crop_refine_enabled = st.checkbox(
                    "Crop Refine Enabled",
                    value=_as_bool(rank.get("crop_refine_enabled"), True),
                )
                rank_crop_refine_mode = st.selectbox(
                    "Crop Refine Mode",
                    options=["adaptive", "always", "off"],
                    index=["adaptive", "always", "off"].index(
                        _as_str(rank.get("crop_refine_mode"), "adaptive")
                        .strip()
                        .lower()
                    )
                    if _as_str(rank.get("crop_refine_mode"), "adaptive").strip().lower()
                    in {"adaptive", "always", "off"}
                    else 0,
                )
                rank_crop_refine_page_dpi = st.number_input(
                    "Crop Refine Page DPI",
                    value=_as_int(rank.get("crop_refine_page_dpi"), 110),
                    min_value=72,
                    step=1,
                )
                rank_final_crop_dpi = st.number_input(
                    "Final Crop DPI",
                    value=_as_int(rank.get("final_crop_dpi"), 216),
                    min_value=72,
                    step=1,
                )
                rank_crop_refine_temperature = st.number_input(
                    "Crop Refine Temperature",
                    value=_as_float(rank.get("crop_refine_temperature"), 0.0),
                    step=0.1,
                    format="%.3f",
                )
                rank_crop_refine_timeout_seconds = st.number_input(
                    "Crop Refine Timeout Seconds",
                    value=_as_float(
                        rank.get("crop_refine_timeout_seconds"),
                        _as_float(rank.get("timeout_seconds"), 600.0),
                    ),
                    min_value=1.0,
                    step=1.0,
                    format="%.1f",
                )

        with st.expander("Publish", expanded=False):
            pub1, pub2 = st.columns(2, gap="large")
            with pub1:
                wp_site_url = st.text_input(
                    "WordPress Site URL", value=_as_str(wp.get("site_url"), "")
                )
                wp_username = st.text_input(
                    "WordPress Username", value=_as_str(wp.get("username"), "")
                )
                wp_post_status = st.selectbox(
                    "WordPress Post Status",
                    options=["publish", "draft", "pending", "private"],
                    index=0
                    if _as_str(wp.get("post_status"), "publish")
                    not in {"publish", "draft", "pending", "private"}
                    else ["publish", "draft", "pending", "private"].index(
                        _as_str(wp.get("post_status"), "publish")
                    ),
                )
                wp_post_type = st.text_input(
                    "WordPress Post Type Endpoint",
                    value=_as_str(wp.get("post_type"), "ml_report"),
                    help="REST endpoint slug used for publishing (for example: ml_report or posts).",
                )
            with pub2:
                publish_validation_policy = st.selectbox(
                    "Publish Validation Policy",
                    options=["block", "warn"],
                    index=0
                    if _as_str(publish_validation.get("policy"), "block")
                    .strip()
                    .lower()
                    != "warn"
                    else 1,
                )

        with st.expander("Analysis & Cost", expanded=False):
            ac1, ac2 = st.columns(2, gap="large")
            with ac1:
                analysis_vector_store_keep = st.checkbox(
                    "Vector Store Keep",
                    value=_as_bool(analysis.get("vector_store_keep"), True),
                )
                analysis_cost_ledger_path = st.text_input(
                    "Cost Ledger Path",
                    value=_as_str(
                        analysis.get("cost_ledger_path"), "./out/cost-ledger.jsonl"
                    ),
                )
            with ac2:
                cost_daily_path = st.text_input(
                    "Cost Daily Path",
                    value=_as_str(cost.get("daily_path"), "./out/cost-daily.json"),
                )
            pricing_rows = []
            for model, model_prices in sorted(pricing.items()):
                if not isinstance(model_prices, dict):
                    continue
                pricing_rows.append(
                    {
                        "model": str(model),
                        "input_tokens_per_1k_usd": _as_float(
                            model_prices.get("input_tokens_per_1k_usd"), 0.0
                        ),
                        "output_tokens_per_1k_usd": _as_float(
                            model_prices.get("output_tokens_per_1k_usd"), 0.0
                        ),
                        "tool_call_usd": _as_float(
                            model_prices.get("tool_call_usd"), 0.0
                        ),
                    }
                )
            pricing_editor = st.data_editor(
                pricing_rows,
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
            )

        apply_clicked = st.form_submit_button(
            "Apply Structured Changes To YAML",
            type="secondary",
            use_container_width=True,
        )

    if not apply_clicked:
        return

    errors: list[str] = []
    ingest_seed = _optional_int_from_text(
        ingest_seed_text, field="Ingest seed", errors=errors
    )
    rank_seed = _optional_int_from_text(
        rank_seed_text, field="Rank seed", errors=errors
    )
    keywords = normalize_text_lines(contents_keywords_text)
    if not keywords:
        errors.append("Contents keywords must contain at least one keyword.")
    openai_models_map = mapping_from_editor_records(
        openai_models_editor,
        key_field="namespace",
        value_field="model",
    )
    pricing_map, pricing_errors = pricing_from_editor_records(pricing_editor)
    errors.extend(pricing_errors)

    if errors:
        for message in errors:
            st.error(message)
        return

    working["schema_version"] = schema_version.strip() or "1.0"
    paths["output_dir"] = path_output_dir.strip()
    paths["cache_dir"] = path_cache_dir.strip()
    paths["state_db"] = path_state_db.strip()
    paths["reports_db"] = path_reports_db.strip()
    paths["category_mappings"] = path_category_mappings.strip()
    paths["html_tag_acronyms"] = path_html_tag_acronyms.strip()
    paths["cover_styles"] = path_cover_styles.strip()
    paths["ingest_lock"] = path_ingest_lock.strip()
    working["paths"] = paths

    ingest["google_sa_path"] = ingest_google_sa_path.strip()
    ingest["gdrive_folder_id"] = ingest_gdrive_folder_id.strip()
    ingest["openai_model"] = ingest_openai_model.strip()
    ingest["temperature"] = float(ingest_temperature)
    ingest["timeout_seconds"] = float(ingest_timeout_seconds)
    ingest["lock_ttl_seconds"] = float(ingest_lock_ttl_seconds)
    ingest["seed"] = ingest_seed
    ingest["batch_limit"] = int(ingest_batch_limit)
    ingest["worker_limit"] = int(ingest_worker_limit)
    ingest["report_worker_limit"] = int(ingest_report_worker_limit)

    drive["supports_all_drives"] = bool(drive_supports_all_drives)
    drive["include_items_from_all_drives"] = bool(drive_include_items_from_all_drives)
    drive["drive_id"] = drive_id.strip()
    drive["list_mode"] = drive_list_mode
    ingest["drive"] = drive

    pdf_text["max_pages"] = int(pdf_text_max_pages)
    pdf_text["max_chars"] = int(pdf_text_max_chars)
    pdf_text["min_density"] = float(pdf_text_min_density)
    pdf_text["sample_pages"] = int(pdf_text_sample_pages)
    ingest["pdf_text"] = pdf_text

    ingest_validation["data_gap_policy"] = validation_data_gap_policy
    ingest["validation"] = ingest_validation

    contents_page["max_pages"] = int(contents_max_pages)
    contents_page["min_headings"] = int(contents_min_headings)
    contents_page["keywords"] = keywords
    contents_page["preview_enabled"] = bool(contents_preview_enabled)
    contents_page["render_dpi"] = int(contents_render_dpi)
    ingest["contents_page"] = contents_page

    evidence_packs["parallel_workers"] = int(evidence_parallel_workers)
    evidence_packs["global_max_in_flight"] = int(evidence_global_max_in_flight)
    evidence_packs["global_min_interval_ms"] = int(evidence_global_min_interval_ms)
    ingest["evidence_packs"] = evidence_packs

    artifacts["parallel_workers"] = int(artifact_parallel_workers)
    artifacts["global_max_in_flight"] = int(artifact_global_max_in_flight)
    artifacts["global_min_interval_ms"] = int(artifact_global_min_interval_ms)
    ingest["artifacts"] = artifacts
    working["ingest"] = ingest

    working["openai_models"] = openai_models_map

    rank["model"] = rank_model.strip() or ingest_openai_model.strip()
    rank["temperature"] = float(rank_temperature)
    rank["timeout_seconds"] = float(rank_timeout_seconds)
    rank["seed"] = rank_seed
    rank["max_candidates"] = int(rank_max_candidates)
    rank["selected_max"] = int(rank_selected_max)
    rank["min_overall_score"] = int(rank_min_overall_score)
    rank["min_quality_score"] = int(rank_min_quality_score)
    rank["min_insight_score"] = int(rank_min_insight_score)
    rank["min_data_score"] = int(rank_min_data_score)
    rank["crop_refine_enabled"] = bool(rank_crop_refine_enabled)
    rank["crop_refine_mode"] = rank_crop_refine_mode
    rank["crop_refine_page_dpi"] = int(rank_crop_refine_page_dpi)
    rank["final_crop_dpi"] = int(rank_final_crop_dpi)
    rank["crop_refine_temperature"] = float(rank_crop_refine_temperature)
    rank["crop_refine_timeout_seconds"] = float(rank_crop_refine_timeout_seconds)
    working["rank"] = rank

    wp["site_url"] = wp_site_url.strip()
    wp["username"] = wp_username.strip()
    wp["post_status"] = wp_post_status
    wp["post_type"] = wp_post_type.strip().strip("/") or "ml_report"
    publish["wp"] = wp
    publish_validation["policy"] = publish_validation_policy
    publish["validation"] = publish_validation
    working["publish"] = publish

    analysis["vector_store_keep"] = bool(analysis_vector_store_keep)
    analysis["cost_ledger_path"] = analysis_cost_ledger_path.strip()
    working["analysis"] = analysis

    cost["daily_path"] = cost_daily_path.strip()
    cost["pricing"] = pricing_map
    working["cost"] = cost

    rendered_yaml = yaml.safe_dump(working, sort_keys=False, allow_unicode=False)
    st.session_state[editor_key] = rendered_yaml
    st.session_state["app_yaml_notice"] = (
        "Structured changes applied to YAML editor. Open 'YAML Editor' tab and click Save."
    )
    st.rerun()


def _render_structured_config_form_legacy(
    config_payload: dict[str, Any], *, editor_key: str
) -> None:
    render_structured_config_form(config_payload=config_payload, editor_key=editor_key)
