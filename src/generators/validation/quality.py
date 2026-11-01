from __future__ import annotations

from typing import List

from src.contracts.validation import ValidationIssue
from src.generators.validation.models import ValidationRuntime

RULE_ID = "artifact_quality"


def run_artifact_quality_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    """Keep the legacy hook without giving heuristics semantic authority.

    Copy specificity, redundancy, generic phrasing and contextual usefulness
    are interpreted by the independent public-editorial review.  Returning
    heuristic warnings here would still let the legacy registry trigger repair
    or suppress model-adjudicated output.
    """

    del runtime
    return []
