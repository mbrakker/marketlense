from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from typing import get_args

from src.contracts import cross_report_analysis


def test_cross_report_shared_vocabulary_has_single_context_owner() -> None:
    package_root = Path("src/contracts/_cross_report_analysis")
    context_contracts = importlib.import_module("src.contracts._cross_report_analysis")

    assert not (package_root / "common.py").exists()
    assert importlib.util.find_spec("src.contracts._cross_report_analysis.common") is None
    assert context_contracts.CROSS_REPORT_ANALYSIS_SCHEMA_VERSION == "1.0"
    assert get_args(context_contracts.PublicationMode) == (
        "generate_only",
        "validate_only",
        "publish_dry_run",
        "publish_live",
    )


def test_cross_report_public_facade_preserves_shared_vocabulary_imports() -> None:
    context_contracts = importlib.import_module("src.contracts._cross_report_analysis")

    assert (
        cross_report_analysis.CROSS_REPORT_ANALYSIS_SCHEMA_VERSION
        == context_contracts.CROSS_REPORT_ANALYSIS_SCHEMA_VERSION
    )
    assert cross_report_analysis.PublicationMode is context_contracts.PublicationMode
