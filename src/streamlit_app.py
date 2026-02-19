from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Ensure `src.*` imports resolve when launched via `streamlit run src/streamlit_app.py`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ui.streamlit_pages import (
    NAV_SECTIONS,
    _chip_html,
    _inject_theme,
    _tip,
    main as _pages_main,
)

__all__ = ["NAV_SECTIONS", "_tip", "_chip_html", "_inject_theme", "main", "st"]


def main() -> None:
    _pages_main()


if __name__ == "__main__":
    main()
