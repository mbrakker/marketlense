# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent
    / "cases_01_validation_flags_metric_and_quote.py"
)

from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.generators.validation.claim_support import _has_unscoped_strong_language
from src.generators.validation.semantic import run_semantic_validation
from ._shared import *  # noqa: F401,F403


__all__ = [name for name in globals() if not name.startswith("__")]
