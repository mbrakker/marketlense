from __future__ import annotations

from src.generators.validation.numbers import validate_new_numbers


def test_number_rule_keeps_temporal_context_local_to_each_sentence() -> None:
    artifacts = {
        "summary": {
            "executive_summary": (
                "Year-over-year growth was 16.0% in 2024. "
                "Year-over-year growth was 10.5% in 2025."
            )
        }
    }

    issues = validate_new_numbers(
        artifacts=artifacts,
        insights=[],
        report=None,  # type: ignore[arg-type]
        evidence_texts=[],
    )

    assert issues == []
