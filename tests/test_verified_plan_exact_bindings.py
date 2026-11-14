from copy import deepcopy

import pytest

from src.generators.artifact_normalization import validate_verified_editorial_plan
from src.utils.errors import AppError
from tests.test_verified_editorial_fact_requirements import _arguments, _plan


@pytest.mark.parametrize("mismatch", ["canonical", "candidate_fact", "candidate_id"])
def test_new_plan_requires_exact_authoritative_ids(mismatch):
    plan = deepcopy(_plan())
    arguments = _arguments()
    if mismatch == "canonical":
        plan["themes"][0]["evidence_ids"][0] = "F1"
        plan["themes"][0]["required_evidence_ids"] = ["F1"]
    elif mismatch == "candidate_fact":
        arguments["admitted_candidate_evidence_ids"]["c1"] = {"F1"}
    else:
        arguments["admitted_candidate_evidence_ids"]["C1"] = arguments[
            "admitted_candidate_evidence_ids"
        ].pop("c1")

    with pytest.raises(AppError):
        validate_verified_editorial_plan(
            plan, **arguments, require_fact_requirements=True
        )

    assert validate_verified_editorial_plan(plan, **arguments)


def test_new_plan_accepts_exact_authoritative_ids():
    result = validate_verified_editorial_plan(
        _plan(), **_arguments(), require_fact_requirements=True
    )
    assert result["themes"][0]["required_evidence_ids"] == ["f1"]
