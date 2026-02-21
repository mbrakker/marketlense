from __future__ import annotations

try:
    from scripts.duration_tools import main_calculate
except ModuleNotFoundError:
    from duration_tools import main_calculate


if __name__ == "__main__":
    main_calculate()
