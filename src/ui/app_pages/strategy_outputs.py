from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

import streamlit as st

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportProjectedDataReadRequest,
)
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidateReadRequest,
)
from src.services.analytics_store_service import (
    read_cross_report_projected_data,
    read_signal_candidates,
)
from src.ui import state as ui_state
from src.ui._streamlit_pages.read_models import (
    _invalidate_dashboard_read_models,
    _selected_ui_run,
)
from src.ui.common import (
    UI_SURFACE_EXCEPTIONS,
    _append_terminal,
    _ctx,
    _page_shell,
    _render_empty_state,
    _tip,
)
from src.ui.run_control import launch_background_run, list_recent_runs


PUBLICATION_MODE_LABELS = {
    "generate_only": "Generate only",
    "validate_only": "Validate only",
    "publish_dry_run": "Publish dry run",
    "publish_live": "Publish live",
}


def build_feature_coverage_rows() -> list[dict[str, str]]:
    return [
        {
            "feature": "Ingest pipeline",
            "codebase_surface": "ingest_orchestrator",
            "streamlit_surface": "Ingest Control",
            "status": "Covered",
            "operator_outcome": "Processes a bounded Drive batch and tracks artifacts.",
        },
        {
            "feature": "Candidate extraction",
            "codebase_surface": "candidate_extraction_orchestrator",
            "streamlit_surface": "Candidate Extraction",
            "status": "Covered",
            "operator_outcome": "Extracts chart/table candidates from Drive or a local PDF.",
        },
        {
            "feature": "Cover generation",
            "codebase_surface": "cover_image_orchestrator",
            "streamlit_surface": "Cover Images",
            "status": "Covered",
            "operator_outcome": "Generates cover PNGs from the selected style config.",
        },
        {
            "feature": "Publishing and taxonomy",
            "codebase_surface": "publish_orchestrator, recategorize_orchestrator",
            "streamlit_surface": "Publishing & Taxonomy",
            "status": "Covered",
            "operator_outcome": "Publishes queued HTML and manages category mapping.",
        },
        {
            "feature": "Publisher discovery and acquisition",
            "codebase_surface": "publisher_inventory, report_download, acquisition_audit",
            "streamlit_surface": "Publisher operations",
            "status": "Covered",
            "operator_outcome": "Discovers publisher inventories and acquires reports.",
        },
        {
            "feature": "Report QA and validation",
            "codebase_surface": "report store, validation, state service",
            "streamlit_surface": "Content QA",
            "status": "Covered",
            "operator_outcome": "Inspects metadata, evidence packs, vector status, and validation.",
        },
        {
            "feature": "Observability",
            "codebase_surface": "cost, logs, storage, run registry",
            "streamlit_surface": "Observability and Run Center",
            "status": "Covered",
            "operator_outcome": "Shows costs, events, storage, active jobs, and dead letters.",
        },
        {
            "feature": "Cross-report briefings",
            "codebase_surface": "cross_report_analysis_orchestrator",
            "streamlit_surface": "Strategy Outputs",
            "status": "New in UI",
            "operator_outcome": "Generates, validates, and optionally dry-runs Briefing output.",
        },
        {
            "feature": "Durable Signal candidates",
            "codebase_surface": "signal_candidate_orchestrator",
            "streamlit_surface": "Strategy Outputs",
            "status": "New in UI",
            "operator_outcome": "Extracts and reviews reusable source-backed Signal candidates.",
        },
        {
            "feature": "Signal posts",
            "codebase_surface": "signal_post_orchestrator",
            "streamlit_surface": "Strategy Outputs",
            "status": "New in UI",
            "operator_outcome": "Generates Signal projections and supports dry-run or live publish.",
        },
        {
            "feature": "UI-run replay",
            "codebase_surface": "ui_run_replay_orchestrator",
            "streamlit_surface": "Strategy Outputs",
            "status": "New in UI",
            "operator_outcome": "Replays a recorded UI run and reports manifest/report deltas.",
        },
    ]


def build_status_count_rows(rows: list[dict[str, str]]) -> list[dict[str, int | str]]:
    counts = Counter(row["status"] for row in rows)
    return [
        {"status": status, "feature_count": count}
        for status, count in sorted(counts.items())
    ]


def _selected_date_range(enabled: bool) -> tuple[str | None, str | None]:
    if not enabled:
        return None, None
    values = st.date_input(
        "Report date range",
        value=(date.today(), date.today()),
        help=_tip(
            "Optional inclusive report date range for projected data filters.",
            "Use it to focus strategy output on a specific reporting period.",
        ),
    )
    if isinstance(values, tuple) and len(values) == 2:
        return values[0].isoformat(), values[1].isoformat()
    if isinstance(values, date):
        return values.isoformat(), values.isoformat()
    return None, None


def build_cross_report_run_payload(
    *,
    topic: str,
    auto_theme: bool,
    category_filters: list[str],
    tag_filters: list[str],
    publisher_filters: list[str],
    date_range_start: str | None,
    date_range_end: str | None,
    max_source_reports: int,
    max_evidence_items: int,
    max_prompt_chars: int,
    publication_mode: str,
    output_root: str = "",
    idempotency_db: str = "",
    request_id: str = "",
    diagnostic: bool = False,
    override_publishability: bool = False,
) -> dict[str, Any]:
    return {
        "topic": topic.strip(),
        "auto_theme": bool(auto_theme),
        "category_filters": list(category_filters),
        "tag_filters": list(tag_filters),
        "publisher_filters": list(publisher_filters),
        "date_range_start": date_range_start,
        "date_range_end": date_range_end,
        "max_source_reports": int(max_source_reports),
        "max_evidence_items": int(max_evidence_items),
        "max_prompt_chars": int(max_prompt_chars),
        "publication_mode": publication_mode,
        "output_root": output_root.strip(),
        "idempotency_db": idempotency_db.strip(),
        "request_id": request_id.strip(),
        "diagnostic": bool(diagnostic),
        "override_publishability": bool(override_publishability),
    }


def build_signal_candidate_run_payload(
    *,
    topic: str,
    category_filters: list[str],
    tag_filters: list[str],
    publisher_filters: list[str],
    date_range_start: str | None,
    date_range_end: str | None,
    max_source_reports: int,
    max_evidence_items: int,
    max_signals: int,
    signal_store_db: str,
    extraction_request_id: str = "",
) -> dict[str, Any]:
    return {
        "topic": topic.strip(),
        "category_filters": list(category_filters),
        "tag_filters": list(tag_filters),
        "publisher_filters": list(publisher_filters),
        "date_range_start": date_range_start,
        "date_range_end": date_range_end,
        "max_source_reports": int(max_source_reports),
        "max_evidence_items": int(max_evidence_items),
        "max_signals": int(max_signals),
        "signal_store_db": signal_store_db.strip(),
        "extraction_request_id": extraction_request_id.strip(),
    }


def build_signal_post_run_payload(
    *,
    topic: str,
    category_filters: list[str],
    tag_filters: list[str],
    publisher_filters: list[str],
    date_range_start: str | None,
    date_range_end: str | None,
    max_source_reports: int,
    max_evidence_items: int,
    minimum_source_reports: int,
    minimum_evidence_items: int,
    publication_mode: str,
    output_root: str,
    signal_store_db: str,
    request_id: str = "",
) -> dict[str, Any]:
    return {
        "topic": topic.strip(),
        "category_filters": list(category_filters),
        "tag_filters": list(tag_filters),
        "publisher_filters": list(publisher_filters),
        "date_range_start": date_range_start,
        "date_range_end": date_range_end,
        "max_source_reports": int(max_source_reports),
        "max_evidence_items": int(max_evidence_items),
        "minimum_source_reports": int(minimum_source_reports),
        "minimum_evidence_items": int(minimum_evidence_items),
        "publication_mode": publication_mode,
        "output_root": output_root.strip(),
        "signal_store_db": signal_store_db.strip(),
        "request_id": request_id.strip(),
    }


def _load_projected_data(settings: Any):
    return read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=settings.reports_db,
            content_classes=["claim", "finding", "quote", "metric"],
            minimum_projection_status="projected",
        ),
        _ctx("strategy_projected_data"),
    )


def _load_signal_candidates(settings: Any):
    db_path = settings.signal_store_db or settings.reports_db
    return read_signal_candidates(
        SignalCandidateReadRequest(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=db_path,
            limit=100,
        ),
        _ctx("strategy_signal_candidates"),
    )


def _projection_options(projected: Any | None) -> dict[str, list[str]]:
    if projected is None:
        return {"publishers": [], "categories": [], "tags": []}
    publishers = sorted(
        {
            str(candidate.publisher).strip()
            for candidate in projected.source_candidates
            if str(candidate.publisher).strip()
        },
        key=str.casefold,
    )
    categories = sorted(
        {
            str(category).strip()
            for candidate in projected.source_candidates
            for category in candidate.category_labels
            if str(category).strip()
        },
        key=str.casefold,
    )
    tags = sorted(
        {
            str(tag).strip()
            for candidate in projected.source_candidates
            for tag in candidate.tags
            if str(tag).strip()
        },
        key=str.casefold,
    )
    return {"publishers": publishers, "categories": categories, "tags": tags}


def build_projection_publisher_rows(projected: Any | None) -> list[dict[str, Any]]:
    if projected is None:
        return []
    counts = Counter(
        str(candidate.publisher or "Unknown").strip() or "Unknown"
        for candidate in projected.source_candidates
    )
    return [
        {"publisher": publisher, "projected_reports": count}
        for publisher, count in counts.most_common(12)
    ]


def build_evidence_class_rows(projected: Any | None) -> list[dict[str, Any]]:
    if projected is None:
        return []
    counts = Counter(str(item.content_class) for item in projected.evidence)
    if projected.raw_metrics:
        counts["metric"] += len(projected.raw_metrics)
    return [
        {"content_class": content_class, "item_count": count}
        for content_class, count in sorted(counts.items())
    ]


def build_signal_candidate_rows(response: Any | None) -> list[dict[str, Any]]:
    if response is None:
        return []
    return [
        {
            "title": candidate.title,
            "type": candidate.candidate_type,
            "support": candidate.support_level,
            "confidence": round(float(candidate.confidence), 3),
            "strength": round(float(candidate.strength), 3),
            "status": candidate.validation_status,
            "reports": len(candidate.source_report_ids),
            "evidence": len(candidate.evidence_ids),
        }
        for candidate in response.candidates
    ]


def build_signal_support_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(row["support"]) for row in rows)
    return [
        {"support": support, "candidate_count": count}
        for support, count in sorted(counts.items())
    ]


def _render_filter_controls(
    *,
    options: dict[str, list[str]],
    key_prefix: str,
) -> tuple[list[str], list[str], list[str]]:
    category_filters = st.multiselect(
        "Categories",
        options=options["categories"],
        help=_tip(
            "Optional projected category filter.",
            "Leave empty to allow every projected category.",
        ),
        key=f"{key_prefix}_categories",
    )
    tag_filters = st.multiselect(
        "Tags",
        options=options["tags"],
        help=_tip(
            "Optional projected tag filter.",
            "Choose tags when the strategy output should focus on a known topic.",
        ),
        key=f"{key_prefix}_tags",
    )
    publisher_filters = st.multiselect(
        "Publishers",
        options=options["publishers"],
        help=_tip(
            "Optional publisher filter.",
            "Use this to compare selected publishers or limit a run to trusted sources.",
        ),
        key=f"{key_prefix}_publishers",
    )
    return category_filters, tag_filters, publisher_filters


def _render_feature_map_tab(rows: list[dict[str, str]]) -> None:
    with st.container(horizontal=True):
        st.metric("Mapped features", len(rows), "codebase vs UI", border=True)
        st.metric(
            "New UI surfaces",
            len([row for row in rows if row["status"] == "New in UI"]),
            "added here",
            border=True,
        )
        st.metric(
            "Existing coverage",
            len([row for row in rows if row["status"] == "Covered"]),
            "already present",
            border=True,
        )
    st.bar_chart(build_status_count_rows(rows), x="status", y="feature_count")
    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "feature": st.column_config.TextColumn("Feature", pinned=True),
            "codebase_surface": "Codebase surface",
            "streamlit_surface": "Streamlit surface",
            "status": "Status",
            "operator_outcome": st.column_config.TextColumn(
                "Operator outcome",
                width="large",
            ),
        },
    )


def _render_cross_report_tab(
    *,
    settings: Any,
    options: dict[str, list[str]],
    projected: Any | None,
) -> None:
    with st.container(horizontal=True):
        st.metric(
            "Projected reports",
            len(projected.source_candidates) if projected else 0,
            "eligible source pool",
            border=True,
        )
        st.metric(
            "Evidence items",
            len(projected.evidence) if projected else 0,
            "claims/findings/quotes",
            border=True,
        )
        st.metric(
            "Raw metrics",
            len(projected.raw_metrics) if projected else 0,
            "source-bound",
            border=True,
        )
    chart_rows = build_projection_publisher_rows(projected)
    if chart_rows:
        st.bar_chart(chart_rows, x="publisher", y="projected_reports")

    with st.form("cross_report_analysis_form"):
        auto_theme = st.toggle(
            "Use automatic theme",
            value=bool(settings.cross_report_analysis_auto_theme_enabled),
            help=_tip(
                "Let deterministic source/theme selection choose the strongest theme.",
                "Turn this off when you already know the exact briefing topic.",
            ),
        )
        topic = st.text_input(
            "Topic",
            value="",
            placeholder="Example: AI commerce adoption",
            help=_tip(
                "Optional when automatic theme is on, required when it is off.",
                "Use a plain business topic, not a prompt or instruction.",
            ),
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            max_source_reports = st.number_input(
                "Source reports",
                min_value=1,
                max_value=int(settings.cross_report_analysis_max_source_reports),
                value=min(6, int(settings.cross_report_analysis_max_source_reports)),
                help=_tip(
                    "Maximum projected reports selected for one Briefing.",
                    "Use more reports for broader coverage, fewer for sharper focus.",
                ),
            )
        with c2:
            max_evidence_items = st.number_input(
                "Evidence items",
                min_value=1,
                max_value=int(settings.cross_report_analysis_max_evidence_items),
                value=min(48, int(settings.cross_report_analysis_max_evidence_items)),
                help=_tip(
                    "Maximum evidence records included before synthesis.",
                    "Lower values reduce cost and make outputs easier to audit.",
                ),
            )
        with c3:
            max_prompt_chars = st.number_input(
                "Prompt budget",
                min_value=1000,
                max_value=int(settings.cross_report_analysis_max_prompt_chars),
                value=int(settings.cross_report_analysis_max_prompt_chars),
                step=1000,
                help=_tip(
                    "Maximum rendered input size before the model call.",
                    "The workflow blocks before spend if projected data exceeds this budget.",
                ),
            )
        category_filters, tag_filters, publisher_filters = _render_filter_controls(
            options=options,
            key_prefix="cross_report",
        )
        use_dates = st.checkbox(
            "Filter by report date",
            value=False,
            help=_tip(
                "Limit source reports to an inclusive date window.",
                "Leave unchecked when report dates are incomplete or not comparable.",
            ),
        )
        date_start, date_end = _selected_date_range(use_dates)
        mode_options = ["generate_only", "validate_only", "publish_dry_run"]
        if bool(settings.cross_report_analysis_publish_enabled):
            mode_options.append("publish_live")
        publication_mode_label = st.selectbox(
            "Publication mode",
            options=[PUBLICATION_MODE_LABELS[mode] for mode in mode_options],
            help=_tip(
                "Choose what happens after synthesis and validation.",
                "Use Publish dry run to inspect WordPress routing without creating a post.",
            ),
        )
        publication_mode = {
            label: value for value, label in PUBLICATION_MODE_LABELS.items()
        }[publication_mode_label]
        with st.expander("Advanced controls", icon=":material/tune:"):
            diagnostic = st.checkbox(
                "Diagnostic mode",
                help=_tip(
                    "Allow diagnostic inspection of otherwise weak source sets.",
                    "Use only when investigating why a Briefing cannot be published.",
                ),
            )
            override_publishability = st.checkbox(
                "Override publishability gate",
                help=_tip(
                    "Explicitly continue past deterministic publishability issues.",
                    "The override is logged and the preserved issue list remains visible.",
                ),
            )
            request_id = st.text_input(
                "Request ID override",
                value="",
                help=_tip(
                    "Optional stable request identifier.",
                    "Leave blank to let the app derive one from the selected controls.",
                ),
            )
        submitted = st.form_submit_button(
            "Run cross-report analysis",
            type="primary",
            icon=":material/analytics:",
        )
    if submitted:
        if not auto_theme and not topic.strip():
            st.warning("Enter a topic or turn on automatic theme selection.")
        else:
            payload = build_cross_report_run_payload(
                topic=topic,
                auto_theme=auto_theme,
                category_filters=category_filters,
                tag_filters=tag_filters,
                publisher_filters=publisher_filters,
                date_range_start=date_start,
                date_range_end=date_end,
                max_source_reports=int(max_source_reports),
                max_evidence_items=int(max_evidence_items),
                max_prompt_chars=int(max_prompt_chars),
                publication_mode=publication_mode,
                request_id=request_id,
                diagnostic=diagnostic,
                override_publishability=override_publishability,
            )
            response = launch_background_run(
                settings,
                run_type="cross_report_analysis",
                display_name="Cross-report analysis",
                request_payload=payload,
            )
            _append_terminal(f"Cross-report analysis launched: {response.record.run_id}")
            st.success(f"Cross-report analysis launched: {response.record.run_id}")


def _render_signal_tab(
    *,
    settings: Any,
    options: dict[str, list[str]],
    candidate_response: Any | None,
) -> None:
    signal_store_options: list[str] = []
    for path in [settings.signal_store_db or settings.reports_db, settings.reports_db]:
        if path and path not in signal_store_options:
            signal_store_options.append(path)
    candidate_rows = build_signal_candidate_rows(candidate_response)
    with st.container(horizontal=True):
        st.metric("Signal candidates", len(candidate_rows), "stored", border=True)
        approved = len([row for row in candidate_rows if row["status"] == "approved"])
        st.metric("Approved", approved, "ready for Signal posts", border=True)
        groups = len(candidate_response.groups) if candidate_response else 0
        st.metric("Groups", groups, "agreement clusters", border=True)
    support_rows = build_signal_support_rows(candidate_rows)
    if support_rows:
        st.bar_chart(support_rows, x="support", y="candidate_count")
    if candidate_rows:
        st.dataframe(
            candidate_rows,
            width="stretch",
            hide_index=True,
            column_config={
                "title": st.column_config.TextColumn("Title", pinned=True),
                "confidence": st.column_config.ProgressColumn(
                    "Confidence",
                    min_value=0.0,
                    max_value=1.0,
                ),
                "strength": st.column_config.ProgressColumn(
                    "Strength",
                    min_value=0.0,
                    max_value=1.0,
                ),
            },
        )
    else:
        _render_empty_state(
            "No stored Signal candidates",
            "Run Signal candidate extraction after analytics projection is available.",
        )

    mode = st.segmented_control(
        "Signal action",
        options=["Extract candidates", "Generate Signal post"],
        default="Extract candidates",
        help=_tip(
            "Choose whether to store reusable Signal candidates or create one Signal post projection.",
            "Start with extraction when no approved candidates are available.",
        ),
    )
    with st.form(f"signal_form_{mode}"):
        topic = st.text_input(
            "Signal topic",
            placeholder="Example: AI-assisted customer journeys",
            help=_tip(
                "Business topic used to select projected evidence for Signal generation.",
                "Use a concise topic that a reader would recognize.",
            ),
        )
        category_filters, tag_filters, publisher_filters = _render_filter_controls(
            options=options,
            key_prefix=f"signal_{mode}",
        )
        use_dates = st.checkbox(
            "Filter by report date",
            value=False,
            help=_tip(
                "Limit source reports to an inclusive date window.",
                "Leave unchecked when recency is less important than evidence coverage.",
            ),
        )
        date_start, date_end = _selected_date_range(use_dates)
        c1, c2, c3 = st.columns(3)
        with c1:
            max_source_reports = st.number_input(
                "Source reports",
                min_value=1,
                max_value=20,
                value=3,
                help=_tip(
                    "Maximum projected reports selected for this Signal action.",
                    "Signal posts usually work best with two or three strong reports.",
                ),
            )
        with c2:
            max_evidence_items = st.number_input(
                "Evidence items",
                min_value=1,
                max_value=100,
                value=6,
                help=_tip(
                    "Maximum projected evidence rows retained for Signal generation.",
                    "Use a lower number for a tighter public post.",
                ),
            )
        with c3:
            max_signals = st.number_input(
                "Candidate cap",
                min_value=1,
                max_value=20,
                value=8,
                disabled=mode != "Extract candidates",
                help=_tip(
                    "Maximum Signal candidates to retain from deterministic scoring.",
                    "This applies only to candidate extraction.",
                ),
            )
        signal_store_db = st.selectbox(
            "Signal store",
            options=signal_store_options,
            help=_tip(
                "SQLite database used to read or write reusable Signal candidates.",
                "Use the configured Signal store for normal operations.",
            ),
        )
        publication_mode = "generate_only"
        minimum_source_reports = 2
        minimum_evidence_items = 2
        if mode == "Generate Signal post":
            post_modes = ["generate_only", "validate_only", "publish_dry_run"]
            if ui_state.get_publish_settings() is not None:
                post_modes.append("publish_live")
            publication_mode_label = st.selectbox(
                "Publication mode",
                options=[PUBLICATION_MODE_LABELS[item] for item in post_modes],
                help=_tip(
                    "Choose whether to only generate, validate, dry-run publish, or publish live.",
                    "Use Publish dry run before any live WordPress publication.",
                ),
            )
            publication_mode = {
                label: value for value, label in PUBLICATION_MODE_LABELS.items()
            }[publication_mode_label]
            minimum_source_reports = st.number_input(
                "Minimum source reports",
                min_value=1,
                max_value=10,
                value=2,
                help=_tip(
                    "Minimum distinct source reports required for approval.",
                    "Raise this when the Signal must be backed by stronger coverage.",
                ),
            )
            minimum_evidence_items = st.number_input(
                "Minimum evidence items",
                min_value=1,
                max_value=20,
                value=2,
                help=_tip(
                    "Minimum evidence rows required for approval.",
                    "Raise this when weakly grounded Signals should be blocked.",
                ),
            )
        submitted = st.form_submit_button(
            "Run Signal action",
            type="primary",
            icon=":material/bolt:",
        )
    if submitted:
        if not topic.strip():
            st.warning("Enter a Signal topic before launching the action.")
            return
        if mode == "Extract candidates":
            payload = build_signal_candidate_run_payload(
                topic=topic,
                category_filters=category_filters,
                tag_filters=tag_filters,
                publisher_filters=publisher_filters,
                date_range_start=date_start,
                date_range_end=date_end,
                max_source_reports=int(max_source_reports),
                max_evidence_items=int(max_evidence_items),
                max_signals=int(max_signals),
                signal_store_db=signal_store_db,
            )
            response = launch_background_run(
                settings,
                run_type="signal_candidate_extraction",
                display_name="Signal candidate extraction",
                request_payload=payload,
            )
        else:
            payload = build_signal_post_run_payload(
                topic=topic,
                category_filters=category_filters,
                tag_filters=tag_filters,
                publisher_filters=publisher_filters,
                date_range_start=date_start,
                date_range_end=date_end,
                max_source_reports=int(max_source_reports),
                max_evidence_items=int(max_evidence_items),
                minimum_source_reports=int(minimum_source_reports),
                minimum_evidence_items=int(minimum_evidence_items),
                publication_mode=publication_mode,
                output_root=settings.output_dir,
                signal_store_db=signal_store_db,
            )
            response = launch_background_run(
                settings,
                run_type="signal_post",
                display_name="Signal post workflow",
                request_payload=payload,
            )
        _append_terminal(f"{response.record.display_name} launched: {response.record.run_id}")
        st.success(f"{response.record.display_name} launched: {response.record.run_id}")


def _render_replay_tab(settings: Any) -> None:
    recent_runs = list_recent_runs(settings, limit=50).records
    if not recent_runs:
        _render_empty_state(
            "No recorded UI runs",
            "Launch any background workflow first; replay uses records from the UI-run registry.",
        )
        return
    selected_index = st.selectbox(
        "Recorded run",
        options=list(range(len(recent_runs))),
        format_func=lambda idx: (
            f"{recent_runs[idx].status} | {recent_runs[idx].display_name} | "
            f"{recent_runs[idx].run_id[:8]}"
        ),
        help=_tip(
            "Choose the original UI run to replay.",
            "The replay compares recorded inputs, configuration, prompts, and artifacts.",
        ),
    )
    selected = recent_runs[selected_index]
    st.dataframe(
        [
            {
                "run_id": selected.run_id,
                "workflow": selected.display_name,
                "status": selected.status,
                "created_at_utc": selected.created_at_utc,
                "artifact_count": len(selected.artifact_paths),
            }
        ],
        width="stretch",
        hide_index=True,
    )
    confirmed = st.checkbox(
        "Replay may execute the recorded workflow again",
        help=_tip(
            "Confirm that you understand replay can re-run the recorded workflow.",
            "Use this for incident response when you need a manifest and delta report.",
        ),
    )
    if st.button(
        "Replay selected run",
        type="primary",
        icon=":material/replay:",
        disabled=not confirmed,
        help=_tip(
            "Launch UI-run replay as a tracked background job.",
            "The result writes a replay manifest and delta report for the selected run.",
        ),
    ):
        response = launch_background_run(
            settings,
            run_type="ui_run_replay",
            display_name="UI run replay",
            request_payload={"run_id": selected.run_id},
        )
        _append_terminal(f"UI-run replay launched: {response.record.run_id}")
        st.success(f"UI-run replay launched: {response.record.run_id}")


def render_strategy_outputs() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    clicked, filters, main_col, detail_col = _page_shell(
        "Strategy Outputs",
        status_label="Projected Intelligence",
        status_level="info",
        primary_action="Refresh strategy data",
        primary_help=_tip(
            "Reload projected reports, stored Signal candidates, and run status.",
            "Use after ingest, Signal extraction, or cross-report generation.",
        ),
        primary_key="refresh_strategy_outputs",
    )
    if clicked:
        _invalidate_dashboard_read_models(st.session_state, reason="refresh_all")
        st.rerun()

    projected = None
    projected_error = None
    signal_candidates = None
    signal_error = None
    try:
        projected = _load_projected_data(settings)
    except UI_SURFACE_EXCEPTIONS as exc:
        projected_error = str(exc)
    try:
        signal_candidates = _load_signal_candidates(settings)
    except UI_SURFACE_EXCEPTIONS as exc:
        signal_error = str(exc)
    options = _projection_options(projected)

    with filters:
        st.caption(
            "Compare codebase capabilities with Streamlit coverage, then run Briefing, Signal, and replay workflows from one projected-data surface."
        )
        if projected_error:
            st.warning(f"Projected data unavailable: {projected_error}")
        if signal_error:
            st.warning(f"Signal candidate store unavailable: {signal_error}")

    with main_col:
        feature_rows = build_feature_coverage_rows()
        feature_tab, cross_tab, signal_tab, replay_tab = st.tabs(
            ["Feature map", "Cross-report", "Signals", "Replay"]
        )
        with feature_tab:
            _render_feature_map_tab(feature_rows)
        with cross_tab:
            _render_cross_report_tab(
                settings=settings,
                options=options,
                projected=projected,
            )
        with signal_tab:
            _render_signal_tab(
                settings=settings,
                options=options,
                candidate_response=signal_candidates,
            )
        with replay_tab:
            _render_replay_tab(settings)

    with detail_col:
        st.subheader("Readiness indicators")
        st.metric(
            "Projected reports",
            len(projected.source_candidates) if projected else 0,
            "must be >0",
        )
        st.metric(
            "Projected evidence",
            len(projected.evidence) if projected else 0,
            "claims/findings/quotes",
        )
        st.metric(
            "Stored Signals",
            len(signal_candidates.candidates) if signal_candidates else 0,
            "approved candidates",
        )
        evidence_rows = build_evidence_class_rows(projected)
        if evidence_rows:
            st.bar_chart(evidence_rows, x="content_class", y="item_count")
        st.subheader("Selected strategy run")
        polled = _selected_ui_run(settings)
        if polled is None:
            _render_empty_state(
                "No selected strategy run",
                "Launch a strategy workflow or choose a run in Run Center to inspect its summary here.",
            )
        else:
            st.json(polled.record.result_summary)
