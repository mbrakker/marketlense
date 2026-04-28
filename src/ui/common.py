from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Optional

import streamlit as st
import yaml

from src.ui import state as ui_state
from src.utils.errors import AppError
from src.utils.logging import new_run_context

UI_SURFACE_EXCEPTIONS = (
    AppError,
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    yaml.YAMLError,
)


def _ctx(task_id: str) -> Any:
    return new_run_context(task_id=f"gui:{task_id}")


def _tip(description: str, example: str = "") -> str:
    text = description.strip()
    if example.strip():
        text = f"{text} Example: {example.strip()}"
    return text[:1000]


def _chip_html(label: str, level: str, *, tooltip: str | None = None) -> str:
    tip = tooltip or _tip(
        "Status indicator for the current view.",
        f"If it shows '{label}', use that state to decide whether to run the page action.",
    )
    return (
        f'<span class="status-chip status-{level}" title="{escape(tip)}">{label}</span>'
    )


def _inject_theme() -> None:
    st.markdown(
        """
<style>
.status-chip {
  display: inline-block;
  border-radius: 999px;
  padding: 0.2rem 0.65rem;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  border: 1px solid transparent;
}

.status-success {
  color: #0f7d45;
  background: rgba(15, 125, 69, 0.12);
  border-color: rgba(15, 125, 69, 0.22);
}

.status-warn {
  color: #9c6200;
  background: rgba(189, 122, 18, 0.14);
  border-color: rgba(189, 122, 18, 0.24);
}

.status-error {
  color: #b42318;
  background: rgba(201, 58, 58, 0.12);
  border-color: rgba(201, 58, 58, 0.24);
}

.status-info {
  color: #116f8f;
  background: rgba(17, 111, 143, 0.12);
  border-color: rgba(17, 111, 143, 0.22);
}

.ml-page-title {
  font-size: 2rem;
  margin-bottom: 0.35rem;
}

.ml-page-subtitle {
  color: #51605a;
  font-size: 0.9rem;
  margin-bottom: 0.2rem;
}

.ml-note {
  font-size: 0.88rem;
}

.ml-stepper {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(126px, 1fr));
  gap: 0.45rem;
  margin: 0.5rem 0 0.8rem;
}

.ml-step {
  border-radius: 0.7rem;
  border: 1px solid rgba(15, 23, 42, 0.10);
  background: rgba(255, 255, 255, 0.88);
  padding: 0.45rem 0.55rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: #475467;
}

.ml-step-done {
  color: #0f7d45;
  border-color: rgba(15, 125, 69, 0.30);
}

.ml-step-active {
  color: #116f8f;
  border-color: rgba(17, 111, 143, 0.28);
}

.ml-step-error {
  color: #b42318;
  border-color: rgba(201, 58, 58, 0.32);
}

.ml-terminal {
  border-radius: 0.8rem;
  border: 1px solid rgba(15, 23, 42, 0.15);
  background: #0f172a;
  color: #d1fae5;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  font-size: 0.84rem;
  padding: 0.75rem;
  min-height: 260px;
  max-height: 420px;
  overflow: auto;
}

.ml-panel {
  border-radius: 1rem;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: linear-gradient(165deg, rgba(255,255,255,0.96) 0%, rgba(247,250,248,0.98) 100%);
  padding: 0.85rem 1rem;
  margin-bottom: 0.75rem;
}

.ml-panel h4 {
  font-size: 0.95rem;
  margin: 0 0 0.35rem;
}

.ml-panel p {
  margin: 0;
  font-size: 0.84rem;
}

.ml-empty-state {
  border-radius: 0.95rem;
  border: 1px dashed rgba(15, 23, 42, 0.16);
  background: rgba(247, 250, 248, 0.95);
  padding: 1rem 1.05rem;
}

.ml-empty-state h4 {
  margin: 0 0 0.3rem;
  font-size: 0.98rem;
}

.ml-empty-state p {
  margin: 0;
  color: #5f6c67;
  font-size: 0.86rem;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _render_page_context() -> None:
    run_id = ui_state.get_selected_run_id()
    report_id = ui_state.get_selected_report_id()
    if not run_id and not report_id:
        return

    with st.container(horizontal=True, gap="small"):
        if run_id:
            st.badge(
                f"Run {run_id[:8]}",
                icon=":material/play_circle:",
                color="blue",
            )
        if report_id:
            st.badge(
                f"Report {report_id[:20]}",
                icon=":material/article:",
                color="gray",
            )


def _page_shell(
    title: str,
    *,
    status_label: str,
    status_level: str,
    primary_action: str | None = None,
    primary_help: str = "",
    primary_key: str = "",
    primary_disabled: bool = False,
) -> tuple[bool, Any, Any, Any]:
    clicked = False
    with st.container(border=True):
        st.markdown(f'<div class="ml-page-title">{title}</div>', unsafe_allow_html=True)
        subtitle_col, action_col = st.columns(
            [4.2, 1.4],
            gap="large",
            vertical_alignment="bottom",
        )
        with subtitle_col:
            st.markdown(
                f'<div class="ml-page-subtitle">{status_label}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(_chip_html(status_label, status_level), unsafe_allow_html=True)
            _render_page_context()
        with action_col:
            if primary_action:
                with st.container(horizontal=True, horizontal_alignment="right"):
                    clicked = st.button(
                        primary_action,
                        key=primary_key,
                        width="stretch",
                        disabled=primary_disabled,
                        help=primary_help[:1000] if primary_help else None,
                    )
    filters_container = st.container(border=True)
    main_col, detail_col = st.columns([2.3, 1.1], gap="large")
    return clicked, filters_container, main_col, detail_col


def _render_empty_state(title: str, detail: str) -> None:
    st.markdown(
        (
            '<div class="ml-empty-state">'
            f"<h4>{escape(title)}</h4>"
            f"<p>{escape(detail)}</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_stepper(
    steps: list[str],
    done_count: int = 0,
    *,
    active_index: Optional[int] = None,
    error_index: Optional[int] = None,
) -> None:
    parts: list[str] = ['<div class="ml-stepper">']
    for idx, step in enumerate(steps):
        cls = "ml-step"
        if error_index is not None and idx == error_index:
            cls += " ml-step-error"
        elif idx < done_count:
            cls += " ml-step-done"
        elif active_index is not None and idx == active_index:
            cls += " ml-step-active"
        tip = _tip(
            "Pipeline step in the current run sequence.", f"Step {idx + 1}: {step}."
        )
        parts.append(f'<div class="{cls}" title="{escape(tip)}">{step}</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def _append_terminal(message: str) -> None:
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    existing = str(st.session_state.get("live_terminal_output") or "")
    next_value = f"{existing}\n[{now}] {message}".strip()
    st.session_state["live_terminal_output"] = next_value


def _render_terminal_panel() -> None:
    st.subheader("Live terminal")
    terminal = str(st.session_state.get("live_terminal_output") or "").strip()
    if not terminal:
        terminal = "[terminal] No UI-triggered output yet."
    st.markdown(
        f'<pre class="ml-terminal">{escape(terminal)}</pre>', unsafe_allow_html=True
    )


def _as_utc(ts: int | float | str | None) -> str:
    if ts in (None, "", 0):
        return ""
    try:
        if isinstance(ts, str):
            if "T" in ts:
                return ts
            ts = float(ts)
        if not isinstance(ts, (int, float)):
            return str(ts)
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%SZ"
        )
    except (TypeError, ValueError, OSError):
        return str(ts)
