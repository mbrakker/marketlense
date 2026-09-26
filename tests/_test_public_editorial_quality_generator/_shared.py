# ruff: noqa: F401,F403,F405
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
import pytest
from src.contracts.public_editorial_quality import PUBLIC_EDITORIAL_VALIDATOR_VERSION
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.generators.public_editorial_quality_generator import (
    _metric_label_relationship_explanation,
    _ordered_category_row_value_pairs,
    _period_value_pairs,
    _public_text_items,
    _structured_category_value_pairs,
    _subject_value_relationships,
    evaluate_public_editorial_quality,
    validation_issues_from_public_editorial_quality,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from src.services._config_service.validation import _resolve_validation_settings

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_public_editorial_quality_generator.py"
)


_GOLDEN_ARTIFACT = Path(__file__).parent / (
    "fixtures/docpacks/golden/"
    "allegro-2026-trends-macrotrends-es-acig-pdf/"
    "report_analysis/artifacts.json"
)

_TEMPORAL_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "editorial_temporal"

_RELATIONSHIP_FIXTURE_DIR = (
    Path(__file__).parent / "fixtures" / "editorial_relationships"
)


def _retained_artifacts() -> dict:
    return json.loads(_GOLDEN_ARTIFACT.read_text(encoding="utf-8"))


def _temporal_fixture(name: str) -> dict:
    return json.loads((_TEMPORAL_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _relationship_fixture(name: str) -> dict:
    return json.loads((_RELATIONSHIP_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _rule_ids(report) -> set[str]:
    return {issue.rule_id for issue in report.issues}


def _temporal_artifacts(*, text: str, evidence: str) -> dict:
    return {
        "insights_final": [
            {
                "id": "insight-temporal",
                "text": text,
                "evidence_id": "temporal-evidence",
                "evidence": evidence,
                "metric": {},
                "pages": [1],
                "so_what": "The comparison should inform the next reporting review.",
                "now_what": "Review the distinct source periods before acting.",
            }
        ]
    }


def _compact_tldr_artifacts(*, text: str, evidence: str) -> dict:
    return {
        "summary": {
            "tldr": "The retained Summary remains available.",
            "card_tldr_compact": text,
            "executive_summary": "The retained Summary remains available.",
            "claim_evidence_map": [
                {
                    "claim": text,
                    "evidence_id": "summary-evidence",
                    "evidence": evidence,
                    "pages": [1],
                }
            ],
        }
    }


def _set_near_duplicate(payload: dict) -> None:
    payload["insights_final"][0].update(
        {
            "text": "A 70% rate is reported for retail buyers in 2026.",
            "evidence": "A 70% rate is reported for retail buyers in 2026.",
            "evidence_id": "retained-70",
        }
    )
    payload["insights_final"][1].update(
        {
            "text": "In 2026, retail buyers are reported at a 70% rate.",
            "evidence": "A 70% rate is reported for retail buyers in 2026.",
            "evidence_id": "retained-70",
        }
    )


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
