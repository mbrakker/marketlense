from __future__ import annotations

import json
from copy import deepcopy

import pytest

from src.contracts.validation import ValidationRequest
from src.generators.claim_validation_generator import (
    retained_claim_semantic_inputs,
    validate_retained_claims,
)
from src.generators.validation.grounding import (
    _grounding_batch_prompt_variables,
    _grounding_batches,
    grounding_payload,
)
from src.utils.errors import AppError
from src.utils.verified_facts import canonical_evidence_map
from tests.test_verified_facts_validation_authority import (
    SOURCE_IDENTITY,
    _fact,
    _fact_variant,
    _insight,
    _metric,
    _packs_for_facts,
    _report,
    _verified_artifacts,
)


def test_verified_grounding_batches_preserve_referenced_multi_fact_qualifiers():
    first = _fact()
    second = _fact_variant(
        fact_id="fact-2",
        page=7,
        statement="Views reached 18m among all respondents in 2026 H2.",
        metric=_metric(
            observations=[
                {
                    "label": "Views",
                    "value": "18m",
                    "unit": "views",
                    "timeframe": "2026 H2",
                    "population": "all respondents",
                    "methodology": {"weighting": "raw"},
                }
            ]
        ),
    )
    unrelated = _fact_variant(
        fact_id="fact-3",
        page=9,
        statement="Retention reached 61% among returning users in 2026.",
        metric=_metric(),
    )
    multi_fact_insight = _insight(metric=first["metric"])
    multi_fact_insight.update(
        {
            "id": "multi-fact",
            "text": (
                "Adoption reached 42% among buyers and views reached 18m "
                "among all respondents in 2026."
            ),
            "evidence_id": "verified-fact:fact-1",
            "evidence_ids": ["verified-fact:fact-1", "verified-fact:fact-2"],
            "pages": [4, 7],
            "evidence_spans": [
                {
                    "evidence_id": "verified-fact:fact-1",
                    "source_pack": "verified_facts",
                    "page": 4,
                    "text": first["statement"],
                    "source_identity": SOURCE_IDENTITY,
                },
                {
                    "evidence_id": "verified-fact:fact-2",
                    "source_pack": "verified_facts",
                    "page": 7,
                    "text": second["statement"],
                    "source_identity": SOURCE_IDENTITY,
                },
            ],
        }
    )
    artifacts = _verified_artifacts(fact=first)
    artifacts["verified_facts"] = [first, second, unrelated]
    artifacts["insights_final"] = [multi_fact_insight]
    facts = [first, second, unrelated]
    evidence_packs = _packs_for_facts(facts)
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-authority",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts",
    )
    package = validate_retained_claims(
        artifacts,
        evidence_packs,
        source_identity=SOURCE_IDENTITY,
        verified_facts_only=True,
    )
    semantic_inputs = retained_claim_semantic_inputs(
        package,
        evidence_packs,
        source_identity=SOURCE_IDENTITY,
    )
    payload = grounding_payload(
        request,
        artifacts,
        retained_claim_inputs=semantic_inputs,
    )
    batches = _grounding_batches(payload, semantic_inputs)
    assert len(batches) == 1
    batch_payload, batch_inputs = batches[0]
    assert batch_inputs == semantic_inputs
    assert batch_payload["canonical_verified_facts"] == {
        "fact-1": first,
        "fact-2": second,
    }
    assert "fact-3" not in batch_payload["canonical_verified_facts"]
    assert any(
        entry["evidence_ids"] == ["verified-fact:fact-1", "verified-fact:fact-2"]
        for entry in batch_payload["public_factual_items"]
    )

    variables = _grounding_batch_prompt_variables(
        batches,
        evidence_texts=tuple(
            canonical_evidence_map({fact["fact_id"]: fact for fact in facts}).values()
        ),
        authority_policy="verified_facts",
        verified_mode=True,
    )[0]
    rendered_batch = json.loads(variables["report_json"])

    assert variables["evidence_json"] == "[]"
    assert rendered_batch["canonical_verified_facts"] == {
        "fact-1": first,
        "fact-2": second,
    }
    assert (
        rendered_batch["canonical_verified_facts"]["fact-2"]["metric"]
        == second["metric"]
    )
    assert (
        rendered_batch["canonical_verified_facts"]["fact-2"]["provenance"][
            "source_truth_notes_by_page"
        ]["7"]
        in variables["report_json"]
    )
    assert unrelated["statement"] not in variables["report_json"]

    invalid_artifacts = deepcopy(artifacts)
    invalid_artifacts["insights_final"][0]["evidence_ids"] = [
        "verified-fact:fact-1",
        "verified-fact:missing",
    ]
    with pytest.raises(AppError) as exc_info:
        grounding_payload(
            request,
            invalid_artifacts,
            retained_claim_inputs=semantic_inputs,
        )
    assert exc_info.value.code == "verified_fact_snapshot_invalid"
