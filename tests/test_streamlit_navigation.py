from __future__ import annotations

from src import streamlit_app


def test_navigation_groups_cover_required_pages() -> None:
    required_groups = {
        "Overview",
        "Core operations",
        "Publisher operations",
        "Content QA",
        "Strategy outputs",
        "Observability",
        "Configuration",
    }
    assert required_groups == set(streamlit_app.NAVIGATION_GROUPS)
    assert len(streamlit_app.NAV_SECTIONS) == len(set(streamlit_app.NAV_SECTIONS))
    assert streamlit_app.NAV_SECTIONS[0] == "Cockpit Overview"
    assert streamlit_app.NAV_SECTIONS[-1] == "Settings & Prompts"
    assert "Run Center" in streamlit_app.NAVIGATION_GROUPS["Overview"]
    assert "Publishing & Taxonomy" in streamlit_app.NAVIGATION_GROUPS["Core operations"]
    assert (
        "Report Download Lab" in streamlit_app.NAVIGATION_GROUPS["Publisher operations"]
    )
    assert "Strategy Outputs" in streamlit_app.NAVIGATION_GROUPS["Strategy outputs"]
    assert "Logs & Live Events" in streamlit_app.NAVIGATION_GROUPS["Observability"]
    assert all(section.strip() for section in streamlit_app.NAV_SECTIONS)


def test_build_navigation_registers_grouped_pages(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _page(page_callable, *, title: str, icon: str):
        return {"title": title, "icon": icon, "callable": page_callable}

    def _navigation(pages: dict[str, list[dict[str, object]]], *, position: str):
        captured["pages"] = pages
        captured["position"] = position
        return {"pages": pages}

    monkeypatch.setattr(streamlit_app.st, "Page", _page)
    monkeypatch.setattr(streamlit_app.st, "navigation", _navigation)

    result = streamlit_app._build_navigation(True)

    assert captured["position"] == "sidebar"
    pages = captured["pages"]
    assert isinstance(pages, dict)
    assert [item["title"] for item in pages["Overview"]] == [
        "Cockpit Overview",
        "Run Center",
    ]
    assert [item["title"] for item in pages["Publisher operations"]] == [
        "Publisher Discovery",
        "Report Download Lab",
        "Acquisition Audit",
        "Publisher Sync",
        "Auth & External Access",
    ]
    assert [item["title"] for item in pages["Strategy outputs"]] == [
        "Strategy Outputs"
    ]
    assert result == {"pages": pages}
