from __future__ import annotations

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
