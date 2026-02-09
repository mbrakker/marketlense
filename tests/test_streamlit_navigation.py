from __future__ import annotations

from src.streamlit_app import NAV_SECTIONS


def test_navigation_sections_match_gui_architecture() -> None:
    assert NAV_SECTIONS == [
        "Cockpit Overview",
        "Ingest Control",
        "Candidate Extraction",
        "Report Command Center",
        "Cover Images",
        "Analysis & Evidence",
        "Validation Center",
        "Publishing Control",
        "Category Manager",
        "Cost & Usage",
        "Logs & Live Terminal",
        "Settings & Prompts",
        "System & Storage",
        "Developer & Test Tools",
    ]
