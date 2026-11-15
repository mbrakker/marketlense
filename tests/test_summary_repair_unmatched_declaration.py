import pytest

from src.utils.errors import AppError
from tests._test_soft_copy_claim_provenance._split_support_test_soft_copy_claim_provenance import (  # noqa: E501
    _assemble_soft_copy,
)


def test_summary_repair_rejects_unmatched_evidence_declaration():
    summary = {
        "tldr": "Sales rose.",
        "card_tldr_compact": "Sales rose.",
        "executive_summary": "Sales rose.",
    }
    bindings = [
        {"claim": "Sales rose.", "classification": "factual", "evidence_ids": ["f1"]},
        {"claim": "Profits fell.", "classification": "factual", "evidence_ids": ["f2"]},
    ]

    with pytest.raises(AppError) as error:
        _assemble_soft_copy(
            summary=summary,
            soft_copy_claim_bindings={"summary": bindings},
            soft_copy_repair_texts={"summary": ["Sales rose."]},
            regeneration_attempt=1,
        )

    assert error.value.code == "soft_copy_claim_provenance_coverage_invalid"
