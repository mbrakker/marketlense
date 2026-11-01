from __future__ import annotations

from typing import List

from src.contracts.validation import ValidationIssue

from .models import ValidationRuntime

RULE_ID = "quotes"


def run_quote_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    return []
