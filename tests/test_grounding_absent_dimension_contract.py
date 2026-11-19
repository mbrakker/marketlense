from src.contracts.claim_validation import semantic_claim_disposition
from src.contracts.prompts import PromptLoadRequest
from src.contracts.protected_facts import (
    PROTECTED_FACT_DIMENSIONS,
    ProtectedFactComparison,
)
from src.contracts.run_context import RunContext
from src.services.prompt_service import load_prompt_set


def test_grounding_prompt_distinguishes_absent_dimensions_from_claims():
    prompt_set = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0", namespace="report_vs/validate/grounding"
        ),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )
    text = " ".join(prompt_set.system.text.split())
    assert (
        "use null for claim_value when the claim does not assert that dimension" in text
    )
    assert "Do not put explanations of absence in claim_value" in text
    assert "do not treat its authorship as a source attribution claim" in text


def test_recommendation_with_absent_dimensions_remains_editorial():
    dimensions = {
        dimension: {"claim_value": None, "evidence_value": None, "status": "unknown"}
        for dimension in PROTECTED_FACT_DIMENSIONS
    }
    dimensions["timeframe"]["evidence_value"] = "2017"
    dimensions["geography"]["evidence_value"] = "U.S."
    comparison = ProtectedFactComparison.from_payload(
        dimensions, proposition_status="unknown"
    )
    assert (
        semantic_claim_disposition(
            classification="prescriptive_recommendation",
            outcome="not_established",
            violation_type="non_fatal_interpretation",
            protected_facts=comparison,
        )
        == "not_applicable"
    )

    dimensions["timeframe"]["claim_value"] = "2026"
    comparison = ProtectedFactComparison.from_payload(
        dimensions, proposition_status="unknown"
    )
    assert (
        semantic_claim_disposition(
            classification="prescriptive_recommendation",
            outcome="not_established",
            violation_type="non_fatal_interpretation",
            protected_facts=comparison,
        )
        == "unresolved"
    )
