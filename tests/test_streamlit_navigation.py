from __future__ import annotations

from src.streamlit_app import NAV_SECTIONS


def test_navigation_sections_cover_required_pages() -> None:
    required_sections = {
        "Cockpit Overview",
        "Ingest Control",
        "Candidate Extraction",
        "Report Command Center",
        "Validation Center",
        "Publishing Control",
        "Logs & Live Terminal",
        "Settings & Prompts",
        "System & Storage",
        "Developer & Test Tools",
    }
    assert required_sections.issubset(set(NAV_SECTIONS))
    assert len(NAV_SECTIONS) == len(set(NAV_SECTIONS))
    assert NAV_SECTIONS[0] == "Cockpit Overview"
    assert NAV_SECTIONS[-1] == "Developer & Test Tools"
    assert all(section.strip() for section in NAV_SECTIONS)
