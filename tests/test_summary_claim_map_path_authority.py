from __future__ import annotations

from copy import deepcopy

import pytest

from src.generators.report_regeneration_generator import (
    _remove_summary_claim_map_item,
    _summary_claim_map_item_index,
)
from src.utils.errors import AppError


@pytest.mark.parametrize(
    "path",
    [
        "summary.claim_evidence_map",
        "summary.claim_evidence_map[-1]",
        "summary.claim_evidence_map[1.0]",
        "summary.claim_evidence_map[2]",
        "summary.claim_evidence_map[item=]",
        "summary.claim_evidence_map[item=missing]",
        "summary.claim_evidence_map[0].evidence_id",
        "summary.claim_evidence_map[0].claim.extra",
        "summary.claim_evidence_map[0]trailing",
    ],
)
def test_summary_removal_rejects_invalid_path_without_mutation(path):
    summary = {
        "claim_evidence_map": [
            {"id": "first", "claim": "First claim."},
            {"claim": "ID-less sibling."},
        ]
    }
    before = deepcopy(summary)

    with pytest.raises(AppError) as error:
        _remove_summary_claim_map_item(summary=summary, full_path=path)

    assert error.value.code == "regeneration_target_item_unresolved"
    assert error.value.retryable is False
    assert error.value.context == {
        "path": path,
        "reason": "summary_removal_item_unresolved",
    }
    assert summary == before


@pytest.mark.parametrize("identity_field", ["id", "claim_id"])
def test_summary_removal_rejects_duplicate_identity_without_mutation(identity_field):
    summary = {
        "claim_evidence_map": [
            {"id": "shared", "claim": "First claim."},
            {identity_field: "shared", "claim": "Second claim."},
        ]
    }
    before = deepcopy(summary)

    with pytest.raises(AppError) as error:
        _remove_summary_claim_map_item(
            summary=summary, full_path="summary.claim_evidence_map[item=shared]"
        )

    assert error.value.code == "regeneration_target_item_unresolved"
    assert summary == before


def test_summary_missing_identity_does_not_fall_back_to_row_position():
    summary = {"claim_evidence_map": [{"claim": "ID-less claim."}]}

    with pytest.raises(AppError) as error:
        _summary_claim_map_item_index(
            original_family=summary, full_path="summary.claim_evidence_map[item=1]"
        )

    assert error.value.code == "regeneration_target_item_unresolved"


def test_summary_explicit_index_is_authoritative_over_numeric_identity():
    summary = {
        "claim_evidence_map": [
            {"id": "1", "claim": "Numeric identity sibling."},
            {"claim": "ID-less target."},
        ]
    }
    sibling = deepcopy(summary["claim_evidence_map"][0])

    result = _remove_summary_claim_map_item(
        summary=summary, full_path="summary.claim_evidence_map[1].claim"
    )

    assert result == {"claim_evidence_map": [sibling]}
