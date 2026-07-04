from __future__ import annotations

"""Content-QA Streamlit pages owned by the report review workflow family."""

from dataclasses import asdict
from pathlib import Path
from typing import Any

import streamlit as st

from src.contracts.files import FileExistsRequest
from src.contracts.state import StateGetRequest
from src.services.file_service import file_exists
from src.services.state_service import get as get_state
from src.ui import state as ui_state
from src.ui._streamlit_pages.read_models import (
    _invalidate_dashboard_read_models,
    _load_report_rows,
    _read_json,
    _recent_validation_files,
    _selected_report_index,
)
from src.ui.common import _as_utc, _chip_html, _ctx, _page_shell, _tip
from src.utils.cover_path_utils import build_cover_asset_path
from src.utils.gui_utils import status_chip_level
from src.utils.slugify import slugify


def _file_exists(path: Path) -> bool:
    return file_exists(
        FileExistsRequest(schema_version="1.0", path=str(path)),
        _ctx("report_center_file_exists"),
    ).exists


def render_report_command_center() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    clicked, filters, main_col, detail_col = _page_shell(
        "Report Command Center",
        status_label="Report Hub",
        status_level="info",
        primary_action="Refresh Catalog",
        primary_help=_tip(
            "Reload report metadata and refresh the report selector.",
            "Use after ingest, recategorize, or cover generation to pick up new records.",
        ),
        primary_key="refresh_reports_center",
    )
    if clicked:
        _invalidate_dashboard_read_models(st.session_state, reason="refresh_all")
        st.rerun()
    reports = _load_report_rows(settings)
    with filters:
        st.caption(
            "Select one report from the metadata DB and inspect provenance, evidence packs, and cover assets."
        )
    with main_col:
        if not reports:
            st.warning("No reports found in the reports DB.")
            return
        labels = [f"{row['title']} ({row['file_id']})" for row in reports]
        selected_idx = st.selectbox(
            "Report",
            options=list(range(len(labels))),
            index=_selected_report_index(reports),
            format_func=lambda idx: labels[idx],
            help=_tip(
                "Select a report metadata row for detailed provenance and artifact review.",
                "Pick the most recent title to inspect its latest evidence packs.",
            ),
        )
        report = reports[selected_idx]
        ui_state.set_selected_report_id(str(report.get("file_id") or ""))
        st.dataframe(
            [
                {
                    "file_id": report.get("file_id"),
                    "file_name": report.get("file_name"),
                    "title": report.get("title"),
                    "publisher": report.get("publisher"),
                    "analysis_mode": report.get("analysis_mode"),
                    "vector_store_id": report.get("vector_store_id"),
                    "html_path": report.get("html_path"),
                    "updated_at_utc": _as_utc(report.get("updated_at")),
                }
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.subheader("Evidence Pack Paths")
        evidence_paths = report.get("evidence_pack_paths") or {}
        if evidence_paths:
            st.dataframe(
                [{"pack": name, "path": path} for name, path in evidence_paths.items()],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No evidence packs recorded for this report.")

    with detail_col:
        if not reports:
            return
        report = reports[selected_idx]
        st.subheader("Metadata")
        st.json(
            {
                "file_id": report.get("file_id"),
                "file_name": report.get("file_name"),
                "title": report.get("title"),
                "publisher": report.get("publisher"),
                "region": report.get("region"),
                "time_period": report.get("time_period"),
                "taxonomy": report.get("taxonomy"),
                "categories": report.get("categories"),
                "html_path": report.get("html_path"),
                "md5": report.get("md5"),
                "analysis_mode": report.get("analysis_mode"),
            }
        )
        st.subheader("Provenance")
        file_id = str(report.get("file_id") or "").strip()
        state_row = get_state(
            StateGetRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                file_id=file_id,
            ),
            _ctx("report_center_state"),
        )
        if state_row:
            st.json(asdict(state_row))
        else:
            st.caption("No matching state record.")
        st.subheader("Artifacts")
        html_path = str(report.get("html_path") or "").strip()
        if html_path:
            st.code(html_path)
        publisher = str(report.get("publisher") or "").strip()
        title = str(report.get("title") or "").strip()
        if title and file_id:
            report_slug = Path(html_path).stem if html_path else None
            cover_path = build_cover_asset_path(
                settings.output_dir,
                file_id=file_id,
                title=title,
                publisher=publisher,
                report_slug=report_slug,
            )
            legacy_cover_path = build_cover_asset_path(
                settings.output_dir,
                file_id=file_id,
                title=title,
                publisher=publisher,
            )
            legacy_cover_path_older = (
                Path(settings.output_dir)
                / slugify(f"{title}.pdf")
                / "assets"
                / f"{slugify(f'{publisher} {title}')}.png"
            )
            if _file_exists(cover_path):
                st.image(
                    str(cover_path), caption="Cover preview", use_container_width=True
                )
            elif _file_exists(legacy_cover_path):
                st.image(
                    str(legacy_cover_path),
                    caption="Cover preview",
                    use_container_width=True,
                )
            elif _file_exists(legacy_cover_path_older):
                st.image(
                    str(legacy_cover_path_older),
                    caption="Cover preview",
                    use_container_width=True,
                )


def render_analysis_evidence() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    clicked, filters, main_col, detail_col = _page_shell(
        "Analysis & Evidence",
        status_label="Vector Store",
        status_level="info",
        primary_action="Refresh Status",
        primary_help=_tip(
            "Refresh vector-store and evidence-pack status for the selected report.",
            "Run after indexing to confirm vector_store_status and artifact paths.",
        ),
        primary_key="analysis_refresh",
    )
    if clicked:
        _invalidate_dashboard_read_models(st.session_state, reason="refresh_all")
        st.rerun()
    reports = _load_report_rows(settings)
    with filters:
        st.caption(
            "Inspect vector store indexing status and evidence packs backing a report."
        )
    if not reports:
        st.warning("No report metadata available.")
        return
    labels = [f"{row['title']} ({row['file_id']})" for row in reports]
    selected_idx = st.selectbox(
        "Report",
        options=list(range(len(labels))),
        index=_selected_report_index(reports),
        format_func=lambda idx: labels[idx],
        help=_tip(
            "Choose which report to inspect for vector indexing and evidence packs.",
            "Select a report that recently completed ingest to confirm indexing status.",
        ),
    )
    report = reports[selected_idx]
    ui_state.set_selected_report_id(str(report.get("file_id") or ""))
    state_row = get_state(
        StateGetRequest(
            schema_version="1.0", state_db=settings.state_db, file_id=report["file_id"]
        ),
        _ctx("analysis_state"),
    )
    evidence_paths = report.get("evidence_pack_paths") or {}

    with main_col:
        st.subheader("Vector Store Status")
        st.dataframe(
            [
                {
                    "file_id": report.get("file_id"),
                    "vector_store_id": report.get("vector_store_id")
                    or (
                        getattr(state_row, "vector_store_id", None)
                        if state_row
                        else None
                    ),
                    "vector_store_status": getattr(
                        state_row, "vector_store_status", None
                    )
                    if state_row
                    else None,
                    "indexed_at_utc": getattr(state_row, "indexed_at_utc", None)
                    if state_row
                    else None,
                    "last_error": getattr(state_row, "last_error", None)
                    if state_row
                    else None,
                }
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.subheader("Evidence Pack Explorer")
        if evidence_paths:
            selected_pack = st.selectbox(
                "Pack",
                options=list(evidence_paths.keys()),
                help=_tip(
                    "Pick an evidence pack to inspect its JSON payload.",
                    "Open the 'summary' or 'claims' pack to verify extracted evidence.",
                ),
            )
            selected_path = evidence_paths[selected_pack]
            st.code(selected_path)
            payload = _read_json(selected_path)
            if payload is not None:
                st.json(payload)
            else:
                st.warning("Unable to parse selected pack JSON.")
        else:
            st.info("No evidence packs recorded for this report.")

    with detail_col:
        st.subheader("Analysis Mode")
        st.info("`vector_store`")
        if state_row:
            st.subheader("State Snapshot")
            st.json(asdict(state_row))


def render_validation_center() -> None:
    settings = ui_state.get_app_settings()
    publish_settings = ui_state.get_publish_settings()
    publish_error = ui_state.get_publish_error()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    clicked, filters, main_col, detail_col = _page_shell(
        "Validation Center",
        status_label="Policy View",
        status_level="info",
        primary_action="Refresh Reports",
        primary_help=_tip(
            "Reload validation artifacts and compliance callouts from output storage.",
            "Use after running validation or publishing policy checks.",
        ),
        primary_key="validation_refresh",
    )
    if clicked:
        _invalidate_dashboard_read_models(st.session_state, reason="refresh_all")
        st.rerun()
    with filters:
        st.caption("Validation policy and artifact compliance status across reports.")
    rows = _recent_validation_files(settings.output_dir)
    with main_col:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                _chip_html(
                    f"data_gap_policy={settings.validation_data_gap_policy}",
                    status_chip_level(settings.validation_data_gap_policy),
                ),
                unsafe_allow_html=True,
            )
        with c2:
            if publish_settings:
                st.markdown(
                    _chip_html(
                        f"publish_policy={publish_settings.validation_policy}",
                        status_chip_level(publish_settings.validation_policy),
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    _chip_html("publish_policy=unavailable", "warn"),
                    unsafe_allow_html=True,
                )
        st.subheader("Validation Artifacts")
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("No validation artifacts found.")

    with detail_col:
        st.subheader("Compliance Callouts")
        total = len(rows)
        red = len([r for r in rows if r["chip_level"] == "error"])
        yellow = len([r for r in rows if r["chip_level"] == "warn"])
        green = len([r for r in rows if r["chip_level"] == "success"])
        st.metric("Green", green)
        st.metric("Yellow", yellow)
        st.metric("Red", red)
        st.metric("Total", total)
        if publish_error:
            st.caption(f"Publish settings unavailable: {publish_error}")
