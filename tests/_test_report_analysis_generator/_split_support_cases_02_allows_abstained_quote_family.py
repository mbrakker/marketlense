# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent / "cases_02_allows_abstained_quote_family.py"
)

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from src.contracts.regeneration import RepairDecision, RepairPatchOperation
from src.generators.validation.regeneration_candidate import (
    CandidateIntegrityResult,
    retained_claim_repair_issues,
)
from src.generators.validation_generator import validate_report
from src.orchestrators._report_analysis_orchestrator.validation import (
    _candidate_validation_report,
)
from src.services import report_analysis_store_service
from src.utils.cache_utils import sha256_json
from ._shared import *  # noqa: F401,F403


__all__ = [name for name in globals() if not name.startswith("__")]
