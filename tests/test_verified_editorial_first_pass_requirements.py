from src.generators._artifact_generator.generation import (
    _verified_editorial_obligation_context,
)
from tests.test_verified_editorial_first_pass_and_scoped_repair import (
    _candidate,
    _fact,
    _plan,
)


def test_first_pass_context_preserves_model_declared_fact_requirements() -> None:
    plan = _plan()
    plan["themes"][0]["required_evidence_ids"] = ["verified-fact:f1"]
    plan["themes"][0]["alternative_evidence_groups"] = [
        ["verified-fact:f2", "verified-fact:f3"]
    ]
    plan["themes"][0]["evidence_ids"].append("verified-fact:f3")
    context = _verified_editorial_obligation_context(
        plan,
        [
            _candidate("candidate-1", "f1"),
            _candidate("candidate-2", "f2"),
            _candidate("candidate-3", "f3"),
        ],
        [
            _fact("f1", "First.", qualifier=""),
            _fact("f2", "Second.", qualifier=""),
            _fact("f3", "Third.", qualifier=""),
        ],
    )
    assert context["themes"][0]["required_evidence_ids"] == ["verified-fact:f1"]
    assert context["themes"][0]["alternative_evidence_groups"] == [
        ["verified-fact:f2", "verified-fact:f3"]
    ]
