from __future__ import annotations

from src.ui import streamlit_pages as pages
from src import streamlit_app


def test_tip_truncates_to_max_length() -> None:
    text = streamlit_app._tip("x" * 1200, "example")
    assert len(text) == 1000


def test_chip_html_includes_escaped_tooltip_title() -> None:
    tooltip = 'Use "Refresh" after ingest.'
    rendered = streamlit_app._chip_html("System Ready", "success", tooltip=tooltip)
    assert 'class="status-chip status-success"' in rendered
    assert 'title="Use &quot;Refresh&quot; after ingest."' in rendered


def test_inject_theme_has_black_captions_and_light_blue_buttons(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _capture_markdown(body: str, unsafe_allow_html: bool = False) -> None:
        captured["body"] = body
        captured["unsafe"] = unsafe_allow_html

    monkeypatch.setattr(streamlit_app.st, "markdown", _capture_markdown)
    streamlit_app._inject_theme()

    body = str(captured.get("body") or "")
    assert "[data-testid=\"stAppViewContainer\"] [data-testid=\"stMain\"] {" in body
    assert "--text-color: #000000 !important;" in body
    assert "[data-testid=\"stAppViewContainer\"] [data-testid=\"stMain\"] [data-testid=\"stCaptionContainer\"]" in body
    assert "[data-testid=\"stAppViewContainer\"] [data-testid=\"stMain\"] [data-testid=\"stMetricLabel\"]" in body
    assert "[data-testid=\"stAppViewContainer\"] [data-testid=\"stMain\"] [data-testid=\"stWidgetLabel\"]" in body
    assert "[data-testid=\"stAppViewContainer\"] [data-testid=\"stMain\"] [data-testid=\"stHeadingWithActionElements\"]" in body
    assert "-webkit-text-fill-color: #000000 !important;" in body
    assert "color: #000000 !important;" in body
    assert "background: #d7ecff !important;" in body
    assert captured.get("unsafe") is True


def test_dashboard_read_model_cache_reuses_loaded_value() -> None:
    session_state: dict[str, object] = {}
    calls = {"count": 0}

    def _load() -> list[dict[str, str]]:
        calls["count"] += 1
        return [{"file_id": f"report-{calls['count']}"}]

    first = pages._load_dashboard_read_model(
        session_state,
        view_name="report_rows",
        identity=("reports.sqlite",),
        loader=_load,
    )
    second = pages._load_dashboard_read_model(
        session_state,
        view_name="report_rows",
        identity=("reports.sqlite",),
        loader=_load,
    )

    assert first == [{"file_id": "report-1"}]
    assert second == first
    assert calls["count"] == 1


def test_dashboard_read_model_cache_invalidation_is_reason_scoped() -> None:
    session_state: dict[str, object] = {}
    pages._load_dashboard_read_model(
        session_state,
        view_name="report_rows",
        identity=("reports.sqlite",),
        loader=lambda: [{"file_id": "report-1"}],
    )
    pages._load_dashboard_read_model(
        session_state,
        view_name="processed_rows",
        identity=("state.sqlite", 1000),
        loader=lambda: [{"file_id": "processed-1"}],
    )
    pages._load_dashboard_read_model(
        session_state,
        view_name="directory_counts",
        identity=("out", 5000),
        loader=lambda: [{"name": "HTML", "count": 1}],
    )

    removed = pages._invalidate_dashboard_read_models(
        session_state, reason="ingest"
    )
    cache = session_state[pages._DASHBOARD_READ_MODEL_CACHE_KEY]

    assert set(removed) == {"report_rows", "processed_rows", "directory_counts"}
    assert cache == {}
    assert (
        session_state[pages._DASHBOARD_CACHE_INVALIDATION_REASON_KEY] == "ingest"
    )


def test_dashboard_read_model_cache_settings_invalidation_clears_all_views() -> None:
    session_state: dict[str, object] = {}
    pages._load_dashboard_read_model(
        session_state,
        view_name="report_rows",
        identity=("reports.sqlite",),
        loader=lambda: [{"file_id": "report-1"}],
    )
    pages._load_dashboard_read_model(
        session_state,
        view_name="log_files",
        identity=("logs", "market_lense", 100),
        loader=lambda: [{"path": "logs/app.log"}],
    )

    removed = pages._invalidate_dashboard_read_models(
        session_state, reason="settings"
    )

    assert set(removed) == {"report_rows", "log_files"}
    assert session_state[pages._DASHBOARD_READ_MODEL_CACHE_KEY] == {}
    assert (
        session_state[pages._DASHBOARD_CACHE_INVALIDATION_REASON_KEY] == "settings"
    )
