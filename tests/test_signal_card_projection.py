import pytest

from src.contracts.report_cards import GEOMETRY_FAMILIES
from src.generators.signal_card_projection import (
    SIGNAL_COVER_FAMILIES,
    build_signal_card_content,
)
from src.utils.errors import AppError


def test_signal_card_projection_is_complete_deterministic_and_uses_all_twenty_families() -> (
    None
):
    card = build_signal_card_content(
        title="Checkout trust is becoming a conversion condition",
        summary="Checkout trust is becoming a conversion condition.",
        confidence=0.84,
        source_report_ids=["report-a", "report-b", "report-a"],
        evidence_ids=["evidence-a", "evidence-b", "evidence-c"],
        uncertainty="Coverage is strongest in retail and technology publishers.",
    )

    assert card == build_signal_card_content(
        title="Checkout trust is becoming a conversion condition",
        summary="Checkout trust is becoming a conversion condition.",
        confidence=0.84,
        source_report_ids=["report-a", "report-b", "report-a"],
        evidence_ids=["evidence-a", "evidence-b", "evidence-c"],
        uncertainty="Coverage is strongest in retail and technology publishers.",
    )
    assert card.source_count == 2
    assert card.evidence_count == 3
    assert card.fingerprint.geometry_family in SIGNAL_COVER_FAMILIES
    assert SIGNAL_COVER_FAMILIES == GEOMETRY_FAMILIES
    assert len(SIGNAL_COVER_FAMILIES) == 20


def test_signal_card_projection_rejects_ungrounded_content() -> None:
    with pytest.raises(AppError) as exc_info:
        build_signal_card_content(
            title="",
            summary="",
            confidence=1.1,
            source_report_ids=[],
            evidence_ids=[],
            uncertainty="",
        )

    assert exc_info.value.code == "signal_card_contract_invalid"
    assert exc_info.value.retryable is False
