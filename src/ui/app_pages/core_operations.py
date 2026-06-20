from __future__ import annotations

"""Core-operation Streamlit pages.

These pages own the ingest, extraction, cover-generation, publish, and
taxonomy workflows directly so the navigation surface is not just a thin
delegator back into the legacy monolith.
"""

from dataclasses import asdict
from pathlib import Path
from typing import Any

import streamlit as st

from src.contracts.categories import CategoryMappingLoadRequest, RecategorizeRequest
from src.contracts.cover_images import CoverStyleLoadRequest
from src.contracts.publish import PublishQueueRequest
from src.orchestrators.publish_queue_orchestrator import build_publish_queue_snapshot
from src.orchestrators.recategorize_orchestrator import run_recategorize
from src.orchestrators.wp_category_update_orchestrator import run_update_wp_categories
from src.services.category_mapping_service import load_mappings
from src.services.cover_style_service import load_cover_styles
from src.ui import state as ui_state
from src.ui._streamlit_pages.read_models import (
    CANDIDATE_STEPS,
    INGEST_STEPS,
    _invalidate_dashboard_read_models,
    _lock_snapshot,
    _read_json,
    _selected_ui_run,
)
from src.ui.common import (
    UI_SURFACE_EXCEPTIONS,
    _append_terminal,
    _ctx,
    _page_shell,
    _render_stepper,
    _tip,
)
from src.ui.run_control import launch_background_run
from src.utils.errors import AppError
from src.utils.gui_utils import row_dicts


def render_ingest_control() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    lock = _lock_snapshot(settings.ingest_lock_path)
    status_level = "warn" if lock.get("found") else "info"
    clicked, filters, main_col, detail_col = _page_shell(
        "Ingest Control",
        status_label="Lock Conflict" if lock.get("found") else "Ready to Run",
        status_level=status_level,
        primary_action="Run Ingest",
        primary_help=_tip(
            "Run the ingest orchestrator with the current controls.",
            "Set folder override and limit, then click to process a bounded batch.",
        ),
        primary_key="run_ingest",
        primary_disabled=False,
    )

    with filters:
        c1, c2 = st.columns(2)
        with c1:
            folder_override = st.text_input(
                "Folder Override",
                value="",
                placeholder="Optional Drive folder ID",
                help=_tip(
                    "Optional Google Drive folder ID that overrides the default ingest folder.",
                    "Paste a folder ID to run ingest on a specific collection.",
                ),
            )
        with c2:
            limit = st.number_input(
                "Limit",
                min_value=1,
                max_value=1000,
                value=int(settings.batch_limit),
                step=1,
                help=_tip(
                    "Maximum number of PDFs to ingest in this run.",
                    "Use 10 for a quick smoke test before full ingest.",
                ),
            )
        st.caption(
            f"Model `{settings.openai_model}` | temperature `{settings.temperature}` | timeout `{settings.openai_timeout_seconds}`s"
        )

    if clicked:
        response = launch_background_run(
            settings,
            run_type="ingest",
            display_name="Ingest",
            request_payload={
                "folder_id": folder_override.strip(),
                "limit": int(limit),
            },
        )
        _append_terminal(f"Ingest launched: {response.record.run_id}")
        st.success(f"Ingest launched: {response.record.run_id}")

    polled = _selected_ui_run(settings, run_type="ingest")
    run_status = polled.record.status if polled is not None else ""
    done_count = len(INGEST_STEPS) if run_status == "succeeded" else 0
    active_index = 0 if run_status in {"queued", "running"} else None
    error_index = len(INGEST_STEPS) - 1 if run_status == "failed" else None

    with main_col:
        st.subheader("Pipeline Stepper")
        _render_stepper(
            INGEST_STEPS,
            done_count=done_count,
            active_index=active_index,
            error_index=error_index,
        )
        if polled is None:
            st.info("Launch ingest to create a tracked background run.")
        else:
            st.subheader("Selected run summary")
            st.json(polled.record.result_summary)
            if polled.output_chunk is not None:
                st.subheader("Worker output")
                st.code(polled.output_chunk.text or "[worker] no output yet")

    with detail_col:
        st.subheader("Lock & Config")
        if lock.get("found"):
            st.error(
                f"Conflict on `{settings.ingest_lock_path}` owner=`{lock.get('owner_id')}` pid=`{lock.get('pid')}`"
            )
        else:
            st.success("No lock conflict detected.")
        st.json(
            {
                "openai_model": settings.openai_model,
                "temperature": settings.temperature,
                "timeout_seconds": settings.openai_timeout_seconds,
                "batch_limit": settings.batch_limit,
                "analysis_mode": "vector_store",
            }
        )
        if polled is not None:
            st.subheader("Run record")
            st.json(polled.record.__dict__)


def render_candidate_extraction() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    clicked, filters, main_col, detail_col = _page_shell(
        "Candidate Extraction",
        status_label="Ready",
        status_level="info",
        primary_action="Run Extraction",
        primary_help=_tip(
            "Run candidate extraction for selected reports or a local PDF.",
            "Provide file_id for a single file or keep it empty to process by limit.",
        ),
        primary_key="run_candidates",
    )

    with filters:
        c1, c2, c3 = st.columns(3)
        with c1:
            folder_override = st.text_input(
                "Folder Override",
                value="",
                key="cand_folder",
                help=_tip(
                    "Optional Drive folder ID for candidate extraction scope.",
                    "Set this to extract from a folder different from default ingest settings.",
                ),
            )
        with c2:
            limit = st.number_input(
                "Limit",
                min_value=1,
                max_value=1000,
                value=5,
                key="cand_limit",
                help=_tip(
                    "Maximum number of items to process in candidate extraction.",
                    "Use 1 when validating extraction output for a single report.",
                ),
            )
        with c3:
            file_id = st.text_input(
                "file_id (optional)",
                value="",
                key="cand_file_id",
                help=_tip(
                    "Optional file_id filter for extracting one known document.",
                    "Paste a Drive file_id to bypass folder scanning.",
                ),
            )
        c4, c5 = st.columns(2)
        with c4:
            local_pdf = st.text_input(
                "Local PDF Path (optional)",
                value="",
                key="cand_local_pdf",
                help=_tip(
                    "Local PDF path for direct extraction without Drive lookup.",
                    r"Example path: C:\reports\sample.pdf",
                ),
            )
        with c5:
            report_id = st.text_input(
                "report_id override (optional)",
                value="",
                key="cand_report_id",
                help=_tip(
                    "Optional report_id override used when processing a local PDF.",
                    "Set report_id='my-test-report' for deterministic artifact paths.",
                ),
            )

    if clicked:
        response = launch_background_run(
            settings,
            run_type="candidate_extraction",
            display_name="Candidate extraction",
            request_payload={
                "folder_id": folder_override.strip(),
                "limit": int(limit),
                "file_id": file_id.strip(),
                "pdf_path": local_pdf.strip(),
                "report_id": report_id.strip(),
            },
        )
        _append_terminal(f"Candidate extraction launched: {response.record.run_id}")
        st.success(f"Candidate extraction launched: {response.record.run_id}")

    polled = _selected_ui_run(settings, run_type="candidate_extraction")
    with main_col:
        st.subheader("Pipeline Stepper")
        _render_stepper(
            CANDIDATE_STEPS,
            done_count=(
                len(CANDIDATE_STEPS)
                if polled and polled.record.status == "succeeded"
                else 0
            ),
            active_index=(
                0 if polled and polled.record.status in {"queued", "running"} else None
            ),
            error_index=(
                len(CANDIDATE_STEPS) - 1
                if polled and polled.record.status == "failed"
                else None
            ),
        )
        if polled is None:
            st.info("Launch extraction to create a tracked background run.")
        else:
            st.subheader("Selected run summary")
            st.json(polled.record.result_summary)
            if polled.output_chunk is not None:
                st.subheader("Worker output")
                st.code(polled.output_chunk.text or "[worker] no output yet")

    with detail_col:
        st.subheader("Asset Viewer")
        if polled is None:
            st.caption("Run extraction to inspect generated candidate artifacts.")
            return
        if polled.record.artifact_paths:
            st.dataframe(
                [{"path": path} for path in polled.record.artifact_paths],
                use_container_width=True,
                hide_index=True,
            )
            first_json = next(
                (
                    path
                    for path in polled.record.artifact_paths
                    if str(path).strip().lower().endswith(".json")
                ),
                "",
            )
            if first_json:
                payload = _read_json(first_json)
                if payload is not None:
                    st.subheader("Artifact preview")
                    st.json(payload)
        else:
            st.caption("No artifact paths recorded yet.")


def render_cover_images() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    clicked, filters, main_col, detail_col = _page_shell(
        "Cover Images",
        status_label="Ready",
        status_level="info",
        primary_action="Generate Covers",
        primary_help=_tip(
            "Generate cover PNG assets from report metadata using the selected style config.",
            "Set limit=10 for a small batch, or specify file_id to regenerate one cover.",
        ),
        primary_key="generate_covers",
    )
    with filters:
        c1, c2, c3 = st.columns(3)
        with c1:
            style_path = st.text_input(
                "Style Config Path",
                value=settings.cover_style_path,
                help=_tip(
                    "Path to cover style YAML used for rendering cover images.",
                    "Point to a custom style file to test alternate branding.",
                ),
            )
        with c2:
            limit = st.number_input(
                "Limit",
                min_value=1,
                max_value=2000,
                value=10,
                help=_tip(
                    "Maximum number of report covers to generate in this run.",
                    "Use 5 for quick verification during style tuning.",
                ),
            )
        with c3:
            file_id = st.text_input(
                "file_id (optional)",
                value="",
                help=_tip(
                    "Optional single report file_id to generate one cover only.",
                    "Paste file_id to regenerate a failed cover asset.",
                ),
            )
        st.caption(f"Source of truth style config: `{settings.cover_style_path}`")

    if clicked:
        response = launch_background_run(
            settings,
            run_type="cover_images",
            display_name="Cover image generation",
            request_payload={
                "style_config_path": style_path.strip(),
                "limit": int(limit),
                "file_id": file_id.strip(),
            },
        )
        _append_terminal(f"Cover generation launched: {response.record.run_id}")
        st.success(f"Cover generation launched: {response.record.run_id}")

    polled = _selected_ui_run(settings, run_type="cover_images")
    with main_col:
        try:
            style_config = load_cover_styles(
                request=CoverStyleLoadRequest(
                    schema_version="1.0", path=style_path.strip()
                ),
                ctx=_ctx("load_cover_style"),
            )
            st.subheader("Style Summary")
            st.json(
                {
                    "profiles": {
                        name: {
                            "palette_and_fonts": asdict(profile.style),
                            "layouts": {
                                size: asdict(layout)
                                for size, layout in profile.layouts.items()
                            },
                        }
                        for name, profile in style_config.config.profiles.items()
                    },
                }
            )
        except UI_SURFACE_EXCEPTIONS as exc:
            st.warning(f"Unable to load style config: {exc}")
        if polled is None:
            st.info("Launch cover generation to create a tracked background run.")
        else:
            st.subheader("Selected run summary")
            st.json(polled.record.result_summary)
            if polled.output_chunk is not None:
                st.subheader("Worker output")
                st.code(polled.output_chunk.text or "[worker] no output yet")

    with detail_col:
        st.subheader("Asset Viewer")
        generated_paths = [
            path
            for path in (polled.record.artifact_paths if polled is not None else [])
            if str(path).strip()
        ]
        if not generated_paths:
            st.caption("No generated assets recorded yet.")
            return
        labels = [Path(path).name for path in generated_paths]
        selected = st.selectbox(
            "Select output",
            options=list(range(len(labels))),
            format_func=lambda idx: labels[idx],
            help=_tip(
                "Select a generated cover output to preview the PNG artifact.",
                "Pick a report with recent style updates to validate rendering.",
            ),
        )
        selected_path = generated_paths[selected]
        st.code(selected_path)
        if Path(selected_path).exists():
            st.image(selected_path, use_container_width=True)


def _render_publishing_control(
    settings: Any, publish_settings: Any | None, publish_error: str | None
) -> None:
    can_publish = publish_settings is not None
    clicked, filters, main_col, detail_col = _page_shell(
        "Publishing Control",
        status_label="Ready" if can_publish else "Config Missing",
        status_level="success" if can_publish else "error",
        primary_action="Publish Queue",
        primary_help=_tip(
            "Publish queued HTML reports to WordPress with the configured validation policy.",
            "Set publish limit to 20 for a controlled batch publish.",
        ),
        primary_key="run_publish",
        primary_disabled=not can_publish,
    )
    with filters:
        limit = st.number_input(
            "Publish Limit",
            min_value=1,
            max_value=1000,
            value=20,
            step=1,
            help=_tip(
                "Maximum number of queued HTML reports to publish in one run.",
                "Start with 5 to validate WordPress connectivity and permissions.",
            ),
        )
    if clicked and publish_settings:
        response = launch_background_run(
            settings,
            run_type="publish",
            display_name="Publish queue",
            request_payload={"limit": int(limit)},
        )
        _append_terminal(f"Publish launched: {response.record.run_id}")
        st.success(f"Publish launched: {response.record.run_id}")

    queue_rows: list[dict[str, Any]] = []
    try:
        queue_snapshot = build_publish_queue_snapshot(
            PublishQueueRequest(
                schema_version="1.0",
                output_dir=settings.output_dir,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                post_type=(
                    publish_settings.wp.post_type
                    if publish_settings is not None
                    else "ml_report"
                ),
            ),
            _ctx("publish_queue"),
        )
        queue_rows = row_dicts(queue_snapshot.items)
    except AppError:
        queue_rows = []

    with main_col:
        st.subheader("Publish Queue")
        if queue_rows:
            st.dataframe(queue_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No HTML files found in output directory.")
        polled = _selected_ui_run(settings, run_type="publish")
        if polled is not None:
            st.subheader("Selected run summary")
            st.json(polled.record.result_summary)
            if polled.output_chunk is not None:
                st.subheader("Worker output")
                st.code(polled.output_chunk.text or "[worker] no output yet")

    with detail_col:
        st.subheader("Settings Summary")
        if publish_settings:
            st.json(
                {
                    "site_url": publish_settings.wp.site_url,
                    "username": publish_settings.wp.username,
                    "post_status": publish_settings.wp.post_status,
                    "post_type": publish_settings.wp.post_type,
                    "validation_policy": publish_settings.validation_policy,
                }
            )
        else:
            st.error(f"Publish settings unavailable: {publish_error}")
        if can_publish and polled is not None:
            st.subheader("Artifacts")
            st.dataframe(
                [{"path": path} for path in polled.record.artifact_paths],
                use_container_width=True,
                hide_index=True,
            )


def _render_category_manager(settings: Any, publish_settings: Any | None) -> None:
    clicked, filters, main_col, detail_col = _page_shell(
        "Category Manager",
        status_label="Mapping Loaded",
        status_level="info",
        primary_action="Recategorize",
        primary_help=_tip(
            "Apply category mappings to reports and persist recategorization outcomes.",
            "Run after updating category-mappings YAML to refresh assignments.",
        ),
        primary_key="run_recategorize",
    )
    with filters:
        st.caption(
            "View category mapping source and trigger recategorize / WordPress category sync."
        )
    sync_clicked = detail_col.button(
        "Sync WP Categories",
        key="run_wp_sync",
        use_container_width=True,
        disabled=publish_settings is None,
        help=_tip(
            "Synchronize mapped categories from reports DB to WordPress categories.",
            "Run after mapping changes so WordPress taxonomy stays aligned.",
        ),
    )

    if clicked:
        _append_terminal("Recategorize requested from UI.")
        try:
            outcomes = run_recategorize(
                RecategorizeRequest(
                    schema_version="1.0",
                    db_path=settings.reports_db,
                    category_mapping_path=settings.category_mapping_path,
                    settings=settings,
                )
            )
            st.session_state["last_recategorize_outcomes"] = outcomes
            _invalidate_dashboard_read_models(st.session_state, reason="recategorize")
            _append_terminal(f"Recategorize complete. outcomes={len(outcomes)}")
            st.success(f"Recategorization completed for {len(outcomes)} reports.")
        except UI_SURFACE_EXCEPTIONS as exc:
            _append_terminal(f"Recategorize failed: {exc}")
            st.error(str(exc))

    if sync_clicked and publish_settings:
        _append_terminal("WP category sync requested from UI.")
        try:
            wp_sync_outcomes = run_update_wp_categories(publish_settings)
            st.session_state["last_wp_sync_outcomes"] = wp_sync_outcomes
            _invalidate_dashboard_read_models(st.session_state, reason="publish")
            _append_terminal(
                f"WP category sync complete. outcomes={len(wp_sync_outcomes)}"
            )
            st.success(
                f"WordPress category sync completed for {len(wp_sync_outcomes)} reports."
            )
        except UI_SURFACE_EXCEPTIONS as exc:
            _append_terminal(f"WP category sync failed: {exc}")
            st.error(str(exc))

    mapping_response = load_mappings(
        request=CategoryMappingLoadRequest(
            schema_version="1.0",
            path=settings.category_mapping_path,
            reload_if_changed=True,
            force_reload=False,
        ),
        ctx=_ctx("load_mapping"),
    )
    categories = row_dicts(mapping_response.mappings.categories)

    with main_col:
        st.subheader("Category Mapping")
        st.dataframe(categories, use_container_width=True, hide_index=True)
        recat = st.session_state.get("last_recategorize_outcomes", [])
        if recat:
            st.subheader("Recategorize Outcomes")
            st.dataframe(row_dicts(recat), use_container_width=True, hide_index=True)
    with detail_col:
        st.subheader("WP Sync")
        if publish_settings is None:
            st.caption("Publish settings missing; WP sync disabled.")
        sync = st.session_state.get("last_wp_sync_outcomes", [])
        if sync:
            st.dataframe(row_dicts(sync), use_container_width=True, hide_index=True)


def render_publishing_and_taxonomy() -> None:
    settings = ui_state.get_app_settings()
    publish_settings = ui_state.get_publish_settings()
    publish_error = ui_state.get_publish_error()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    mode = st.segmented_control(
        "Mode",
        options=["Publishing", "Taxonomy"],
        default="Publishing",
        help=_tip(
            "Switch between WordPress publishing controls and taxonomy management.",
            "Use 'Taxonomy' after category mapping changes, then switch back to 'Publishing'.",
        ),
    )
    if mode == "Publishing":
        _render_publishing_control(settings, publish_settings, publish_error)
    else:
        _render_category_manager(settings, publish_settings)
