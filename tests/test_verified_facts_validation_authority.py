from __future__ import annotations

import json
from copy import deepcopy

import pytest

from src.contracts.validation import ValidationRequest
from src.generators._artifact_generator.storage import derive_metric_spine_from_insights
from src.generators.artifact_normalization import normalize_artifact_insights
from src.generators.claim_validation_generator import (
    materialize_retained_claim_package,
    metric_claim_text,
)
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
)
from src.generators.validation.grounding import (
    _grounding_batch_prompt_variables,
    _grounding_batches,
    grounding_payload,
)
from src.generators.validation.preparation import prepare_validation_inputs
from src.generators.validation.verified_facts import validated_verified_facts
from src.services.schema_validator_service import validate_evidence_references
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.verified_facts import (
    build_verified_authority_context,
    canonical_evidence_map,
    canonical_fact_text,
    validate_verified_artifact_bindings,
)
from tests._test_validation_generator._shared import _ctx, _report, _settings

SOURCE_IDENTITY = f"frozen-report|pdf-sha256:{'a' * 64}"
SOURCE_SHA = "a" * 64


def _metric(*, observations: list[dict] | None = None) -> dict:
    value = "42%" if not observations else "42%; 18%"
    payload = {
        "label": "Adoption",
        "value": value,
        "unit": "%",
        "trend": "up",
        "timeframe": "2026",
        "geography": "global",
        "segment": "buyers",
        "sample_size": "1000",
        "confidence": "high",
        "subject": "buyers",
        "cohort": "survey respondents",
        "denominator": "respondents",
        "observation_status": "observed",
    }
    if observations is not None:
        payload["observations"] = deepcopy(observations)
    return payload


def _fact(*, metric: dict | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "fact_id": "fact-1",
        "statement": "Adoption reached 42% among buyers in 2026.",
        "metric": deepcopy(metric or _metric()),
        "qualifiers": ["among buyers"],
        "source_identity": SOURCE_IDENTITY,
        "source_pdf_sha256": SOURCE_SHA,
        "supporting_physical_pages": [4],
        "verification_outcome": "verified",
        "provenance": {
            "inspected_physical_pages": [4],
            "source_truth_notes_by_page": {
                "4": "Page 4 reports 42% adoption among buyers in the 2026 survey."
            },
        },
    }


def _fact_variant(*, fact_id: str, page: int, statement: str, metric: dict) -> dict:
    fact = _fact(metric=metric)
    fact["fact_id"] = fact_id
    fact["statement"] = statement
    fact["supporting_physical_pages"] = [page]
    fact["provenance"]["inspected_physical_pages"] = [page]
    fact["provenance"]["source_truth_notes_by_page"] = {
        str(page): f"Page {page} reports the verified observation."
    }
    return fact


def _packs(fact: dict | None = None) -> dict:
    fact = deepcopy(fact or _fact())
    evidence_id = f"verified-fact:{fact['fact_id']}"
    return {
        "findings": {
            "family_status": {
                "family": "findings",
                "source": "verified_facts",
                "status": "generated",
                "policy_action": "keep",
            },
            "findings": [
                {
                    "id": evidence_id,
                    "verified_fact_id": fact["fact_id"],
                    "text": fact["statement"],
                    "statement": fact["statement"],
                    "evidence": fact["statement"],
                    "metric": deepcopy(fact["metric"]),
                    "pages": [4],
                    "source_identity": SOURCE_IDENTITY,
                    "evidence_spans": [
                        {
                            "evidence_id": evidence_id,
                            "source_pack": "verified_facts",
                            "page": 4,
                            "text": fact["statement"],
                            "source_identity": SOURCE_IDENTITY,
                        }
                    ],
                }
            ],
        },
        "verified_facts": {
            "family_status": {
                "family": "verified_facts",
                "source": "visual_verification",
                "status": "generated",
                "policy_action": "keep",
            },
            "verified_facts": [fact],
        },
    }


def _packs_for_facts(facts: list[dict]) -> dict:
    assert facts
    packs = _packs(facts[0])
    for fact in facts[1:]:
        additional = _packs(fact)
        packs["findings"]["findings"].extend(additional["findings"]["findings"])
        packs["verified_facts"]["verified_facts"].extend(
            additional["verified_facts"]["verified_facts"]
        )
    return packs


def _insight(
    *, text: str = "Adoption reached 42% among buyers in 2026.", metric=None
) -> dict:
    evidence_id = "verified-fact:fact-1"
    return {
        "id": "fact-1",
        "text": text,
        "evidence_id": evidence_id,
        "evidence": (
            "Discovery evidence intentionally differs from the verified statement."
        ),
        "evidence_spans": [
            {
                "evidence_id": evidence_id,
                "source_pack": "verified_facts",
                "page": 4,
                "text": (
                    "Discovery evidence intentionally differs from the verified "
                    "statement."
                ),
                "source_identity": SOURCE_IDENTITY,
            }
        ],
        "pages": [4],
        "metric": deepcopy(metric or _metric()),
    }


def _verified_artifacts(
    *, insight: dict | None = None, fact: dict | None = None
) -> dict:
    fact = deepcopy(fact or _fact())
    insight = deepcopy(insight or _insight(metric=fact["metric"]))
    return {
        "verified_facts": [fact],
        "insights_final": [insight],
        "summary": {},
        "key_figures": [],
        "quotes_final": [],
    }


def _authority_artifacts(*, fact: dict | None = None) -> dict:
    fact = deepcopy(fact or _fact())
    digest = sha256_json(
        {
            "source_identity": SOURCE_IDENTITY,
            "verified_facts": [fact],
        }
    )
    artifacts = _verified_artifacts(fact=fact)
    artifacts["_cache"] = {
        "visual_authority_canary": {
            "enabled": True,
            "digest": digest,
            "verified_fact_digest": digest,
            "verified_facts": [fact],
            "verified_evidence_packs": _packs(fact),
        }
    }
    return artifacts


def test_verified_authority_context_is_hash_bound_and_canonical():
    context = build_verified_authority_context(
        _authority_artifacts(), expected_source_identity=SOURCE_IDENTITY
    )

    assert context.source_identity == SOURCE_IDENTITY
    assert context.source_pdf_sha256 == SOURCE_SHA
    assert context.verified_fact_digest
    assert context.verified_facts["fact-1"]["metric"] == _metric()
    assert (
        context.evidence_packs["findings"]["findings"][0]["id"]
        == "verified-fact:fact-1"
    )


def test_stale_verified_authority_digest_fails_closed():
    artifacts = _authority_artifacts()
    artifacts["_cache"]["visual_authority_canary"]["digest"] = "b" * 64

    with pytest.raises(AppError) as raised:
        build_verified_authority_context(
            artifacts, expected_source_identity=SOURCE_IDENTITY
        )

    assert raised.value.code == "verified_fact_snapshot_invalid"


def test_verified_materialization_retains_authoritative_composite_observations():
    fact = _fact(
        metric={
            **_metric(
                observations=[
                    {
                        "label": "Creators",
                        "value": "42%",
                        "unit": "%",
                        "timeframe": "2026",
                    },
                    {
                        "label": "Views",
                        "value": "18m",
                        "unit": "views",
                        "timeframe": "2026 H2",
                    },
                ]
            ),
            "forecast_status": "conditional_forecast",
        }
    )
    retained, failure_code = materialize_retained_claim_package(
        None,
        report_id="verified-authority",
        artifacts=_verified_artifacts(fact=fact),
        evidence_packs=_packs(fact),
        final_html="<html><body>Verified report.</body></html>",
        source_id=SOURCE_IDENTITY,
        source_md5=SOURCE_SHA,
        configuration_hash="config-sha256",
        policy_hash="policy-sha256",
        verified_facts_only=True,
    )

    assert failure_code == ""
    assert retained is not None
    metric_rows = [
        result
        for result in retained["results"]
        if str(result.get("candidate", {}).get("claim_id", "")).endswith(":metric")
    ]
    assert metric_rows
    assert "18m" in metric_rows[0]["candidate"]["text"]
    assert metric_rows[0]["candidate"]["text"].find("2026 H2") >= 0


def test_verified_preparation_excludes_original_pdf_and_non_authoritative_packs(
    tmp_path,
):
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-authority",
        report=_report(),
        artifacts=_verified_artifacts(),
        evidence_packs={
            **_packs(),
            "doc_map": {
                "summary": "Original extraction says 99% and must not be authority.",
                "sections": [],
            },
            "findings_legacy": {
                "findings": [
                    {
                        "id": "legacy-1",
                        "evidence": "Legacy extraction says 99%.",
                    }
                ]
            },
        },
        source_id=SOURCE_IDENTITY,
        source_text="Original PDF extraction says 99%.",
        validation_mode="verified_facts",
    )

    prepared = prepare_validation_inputs(
        request, _settings(tmp_path), _ctx(), md5=SOURCE_SHA
    )

    assert prepared.pdf_text == ""
    assert any("42%" in text for text in prepared.evidence_texts)
    assert all("99%" not in text for text in prepared.evidence_texts)
    assert prepared.verified_facts_mode is True


def test_verified_preparation_disables_vector_store_source_retrieval(tmp_path):
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-authority",
        report=_report(),
        artifacts=_verified_artifacts(),
        evidence_packs=_packs(),
        source_id=SOURCE_IDENTITY,
        vector_store_id="vs-legacy-source",
        validation_mode="verified_facts",
    )

    prepared = prepare_validation_inputs(
        request,
        _settings(tmp_path, validation_grounding_use_vector_store=True),
        _ctx(),
        md5=SOURCE_SHA,
    )

    assert prepared.grounding_use_vector_store is False
    assert prepared.grounding_retrieval_mode == "chat_json"


def test_verified_grounding_payload_uses_fact_snapshot_over_discovery_copy(tmp_path):
    artifacts = _verified_artifacts()
    artifacts["insights_final"][0]["evidence"] = "Discovery extraction says 99%."
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-authority",
        report=_report(),
        artifacts=artifacts,
        evidence_packs={
            **_packs(),
            "doc_map": {"summary": "Discovery extraction says 99%.", "sections": []},
        },
        source_id=SOURCE_IDENTITY,
        source_text="Discovery extraction says 99%.",
        validation_mode="verified_facts",
    )

    payload = grounding_payload(request, artifacts)

    insight_payload = payload["insights_final"][0]
    assert "42%" in insight_payload["evidence"]
    assert "99%" not in insight_payload["evidence"]
    assert insight_payload["metric"]["value"] == "42%"
    assert all(
        "99%" not in str(item.get("retained_evidence") or "")
        for item in payload["public_factual_items"]
        if isinstance(item, dict)
    )


def test_verified_grounding_retains_page_bound_source_truth_notes():
    fact = _fact()
    fact["statement"] = "The methodology describes the tracked-app dataset."
    note = (
        "The page states that the data are aggregated and anonymized and may not "
        "reflect the entire global app market."
    )
    fact["provenance"]["source_truth_notes_by_page"]["4"] = note

    canonical_text = canonical_fact_text(fact)
    assert note in canonical_text
    assert note in canonical_evidence_map({"fact-1": fact})["verified-fact:fact-1"]

    payload = grounding_payload(
        ValidationRequest(
            schema_version="1.0",
            report_id="verified-authority",
            report=_report(),
            artifacts=_verified_artifacts(fact=fact),
            evidence_packs=_packs(fact),
            source_id=SOURCE_IDENTITY,
            validation_mode="verified_facts",
        ),
        _verified_artifacts(fact=fact),
    )
    assert any(
        note in str(item.get("retained_evidence") or "")
        for item in payload["public_factual_items"]
        if isinstance(item, dict)
    )


def test_verified_grounding_passes_complete_canonical_fact_to_batches():
    metric = _metric(
        observations=[
            {
                "label": "Creators",
                "value": "42%",
                "unit": "%",
                "timeframe": "2026 H1",
                "population": "verified buyers",
                "methodology": {"weighting": "post-stratified"},
            },
            {
                "label": "Views",
                "value": "18m",
                "unit": "views",
                "timeframe": "2026 H2",
                "population": "all respondents",
                "methodology": {"weighting": "raw"},
            },
        ]
    )
    metric.update(
        {
            "forecast_status": "conditional_forecast",
            "assumptions": {
                "adoption_rate": {"value": "42%", "condition": "if spend holds"},
                "confidence_interval": {"lower": "35%", "upper": "49%"},
            },
            "composite_methodology": {
                "units": ["%", "views"],
                "populations": ["verified buyers", "all respondents"],
            },
        }
    )
    fact = _fact(metric=metric)
    artifacts = _verified_artifacts(fact=fact)
    artifacts["insights_final"][0]["text"] = (
        "Adoption stayed flat at 42% for a different population."
    )
    artifacts["insights_final"][0]["metric"] = {
        "value": "99%",
        "unit": "%",
        "final_only_population": "unverified segment",
    }
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-authority",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=_packs(fact),
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts",
    )

    payload = grounding_payload(request, artifacts)
    insight_payload = payload["insights_final"][0]
    assert insight_payload["metric"] == metric
    assert "final_only_population" not in insight_payload["metric"]
    assert payload["canonical_verified_facts"]["fact-1"] == fact
    assert (
        payload["canonical_verified_facts"]["fact-1"]["statement"] == fact["statement"]
    )

    batch_payload, _semantic_inputs = _grounding_batches(
        {**payload, "retained_claims_to_ground": []}, []
    )[0]
    assert batch_payload["canonical_verified_facts"] == {"fact-1": fact}
    assert (
        batch_payload["canonical_verified_facts"]["fact-1"]["provenance"]
        == fact["provenance"]
    )


def test_verified_grounding_batch_variables_scope_report_wide_evidence():
    fact = _fact()
    batch_payload = {
        "public_factual_items": [
            {
                "item_id": "insights:fact-1.text",
                "text": fact["statement"],
                "evidence_ids": ["verified-fact:fact-1"],
                "retained_evidence": [fact["statement"]],
            }
        ],
        "retained_claims_to_ground": [],
        "canonical_verified_facts": {"fact-1": fact},
    }

    variables = _grounding_batch_prompt_variables(
        [(batch_payload, [])],
        evidence_texts=(fact["statement"], "Unrelated report-wide evidence."),
        authority_policy="verified_facts",
        verified_mode=True,
    )[0]

    assert variables["evidence_json"] == "[]"
    rendered_batch = json.loads(variables["report_json"])
    assert rendered_batch["canonical_verified_facts"] == {"fact-1": fact}
    assert rendered_batch["public_factual_items"][0]["retained_evidence"] == [
        fact["statement"]
    ]
    assert (
        rendered_batch["canonical_verified_facts"]["fact-1"]["provenance"]
        == fact["provenance"]
    )


def test_grounding_batch_variables_keep_legacy_evidence_serialization_unchanged():
    batch_payload = {
        "public_factual_items": [],
        "retained_claims_to_ground": [],
    }
    evidence_texts = ("Legacy evidence one.", "Legacy evidence two.")

    variables = _grounding_batch_prompt_variables(
        [(batch_payload, [])],
        evidence_texts=evidence_texts,
        authority_policy="legacy",
        verified_mode=False,
    )[0]

    assert variables["evidence_json"] == json.dumps(
        list(evidence_texts), ensure_ascii=False
    )


def test_grounding_batch_variables_are_reused_for_initial_and_recovery_context():
    batch_payload = {
        "public_factual_items": [],
        "retained_claims_to_ground": [],
    }
    kwargs = {
        "evidence_texts": ("Canonical fact evidence.", "Unrelated evidence."),
        "authority_policy": "verified_facts",
        "verified_mode": True,
    }

    initial = _grounding_batch_prompt_variables([(batch_payload, [])], **kwargs)[0]
    post_reuse = _grounding_batch_prompt_variables([(batch_payload, [])], **kwargs)[0]
    recovery_source_evidence = {
        "report_json": initial["report_json"],
        "evidence_json": initial["evidence_json"],
        "authority_policy": initial["authority_policy"],
    }

    assert post_reuse == initial
    assert recovery_source_evidence["evidence_json"] == "[]"
    assert recovery_source_evidence == {
        "report_json": post_reuse["report_json"],
        "evidence_json": post_reuse["evidence_json"],
        "authority_policy": post_reuse["authority_policy"],
    }


def test_verified_grounding_keeps_authoritative_fact_when_editorial_value_matches():
    fact = _fact(
        metric={
            **_metric(),
            "forecast_status": "observed",
            "population_definition": {
                "included": "buyers who completed the survey",
                "excluded": "non-respondents",
            },
        }
    )
    artifacts = _verified_artifacts(fact=fact)
    artifacts["insights_final"][0]["text"] = (
        "Adoption fell to 42% among non-respondents in a forecast."
    )
    artifacts["insights_final"][0]["metric"] = {
        "value": "42%",
        "unit": "%",
        "population_definition": "non-respondents",
        "forecast_status": "forecast",
    }
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-authority",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=_packs(fact),
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts",
    )

    payload = grounding_payload(request, artifacts)

    assert payload["insights_final"][0]["text"].endswith("forecast.")
    assert payload["insights_final"][0]["metric"] == fact["metric"]
    assert (
        payload["canonical_verified_facts"]["fact-1"]["metric"]["population_definition"]
        == fact["metric"]["population_definition"]
    )
    assert (
        payload["canonical_verified_facts"]["fact-1"]["metric"]["forecast_status"]
        == "observed"
    )


def test_verified_composite_metric_survives_normalization_and_metric_spine():
    observations = [
        {"label": "Creators", "value": "42%", "unit": "%", "timeframe": "2026"},
        {"label": "Views", "value": "18%", "unit": "%", "timeframe": "2026"},
    ]
    metric = _metric(observations=observations)
    normalized = normalize_artifact_insights(
        [_insight(metric=metric)], prefix="insight", verified_mode=True
    )

    assert normalized[0]["metric"]["observations"] == observations
    spine = derive_metric_spine_from_insights(normalized, verified_mode=True)
    assert spine[0]["observations"] == observations


def test_verified_metric_spine_preserves_multi_fact_binding():
    insight = _insight()
    insight["evidence_ids"] = ["verified-fact:fact-1", "verified-fact:fact-2"]

    spine = derive_metric_spine_from_insights([insight], verified_mode=True)

    assert spine[0]["evidence_ids"] == [
        "verified-fact:fact-1",
        "verified-fact:fact-2",
    ]


def test_verified_metric_spine_preserves_authoritative_statement_qualifier():
    fact = _fact(
        metric={
            **_metric(),
            "label": "Businesses reporting use of AI in their daily work",
            "value": "88",
            "unit": "%",
        }
    )
    fact["statement"] = (
        "The report says as many as 88% of businesses now report using AI "
        "in their daily work."
    )
    insight = {
        "id": fact["fact_id"],
        "text": fact["statement"],
        "evidence_id": "verified-fact:fact-1",
        "evidence": fact["statement"],
        "metric": deepcopy(fact["metric"]),
    }

    spine = derive_metric_spine_from_insights(
        [insight], verified_mode=True, verified_facts=[fact]
    )

    assert spine[0]["source_statement"] == fact["statement"]
    assert fact["statement"] in metric_claim_text(spine[0], include_observations=True)


def test_verified_multi_fact_artifact_uses_union_of_authoritative_pages():
    first = _fact()
    second = deepcopy(first)
    second["fact_id"] = "fact-2"
    second["supporting_physical_pages"] = [5]
    second["provenance"] = {
        "inspected_physical_pages": [5],
        "source_truth_notes_by_page": {
            "5": "The second verified fact is supported on page 5."
        },
    }
    artifacts = _verified_artifacts(fact=first)
    artifacts["verified_facts"] = [first, second]
    artifacts["insights_final"][0].update(
        {
            "evidence_ids": ["verified-fact:fact-1", "verified-fact:fact-2"],
            "pages": [4, 5],
            "evidence_spans": [
                {
                    "evidence_id": "verified-fact:fact-1",
                    "source_pack": "verified_facts",
                    "page": 4,
                    "text": "The first verified fact is supported on page 4.",
                    "source_identity": SOURCE_IDENTITY,
                },
                {
                    "evidence_id": "verified-fact:fact-2",
                    "source_pack": "verified_facts",
                    "page": 5,
                    "text": "The second verified fact is supported on page 5.",
                    "source_identity": SOURCE_IDENTITY,
                },
            ],
        }
    )

    validate_verified_artifact_bindings(
        artifacts,
        {"fact-1": first, "fact-2": second},
    )


def test_verified_multi_fact_artifact_requires_a_span_for_each_fact():
    first = _fact()
    second = deepcopy(first)
    second["fact_id"] = "fact-2"
    second["supporting_physical_pages"] = [5]
    second["provenance"] = {
        "inspected_physical_pages": [5],
        "source_truth_notes_by_page": {
            "5": "The second verified fact is supported on page 5."
        },
    }
    artifacts = _verified_artifacts(fact=first)
    artifacts["verified_facts"] = [first, second]
    artifacts["insights_final"][0].update(
        {
            "evidence_ids": ["verified-fact:fact-1", "verified-fact:fact-2"],
            "pages": [4, 5],
            "evidence_spans": [
                {
                    "evidence_id": "verified-fact:fact-1",
                    "source_pack": "verified_facts",
                    "page": 4,
                    "text": "The first verified fact is supported on page 4.",
                    "source_identity": SOURCE_IDENTITY,
                }
            ],
        }
    )

    with pytest.raises(AppError, match="every fact"):
        validate_verified_artifact_bindings(
            artifacts,
            {"fact-1": first, "fact-2": second},
        )


def test_verified_multi_fact_artifact_rejects_swapped_per_fact_pages():
    first = _fact()
    second = deepcopy(first)
    second["fact_id"] = "fact-2"
    second["supporting_physical_pages"] = [5]
    second["provenance"] = {
        "inspected_physical_pages": [5],
        "source_truth_notes_by_page": {
            "5": "The second verified fact is supported on page 5."
        },
    }
    artifacts = _verified_artifacts(fact=first)
    artifacts["verified_facts"] = [first, second]
    artifacts["insights_final"][0].update(
        {
            "evidence_ids": ["verified-fact:fact-1", "verified-fact:fact-2"],
            "pages": [4, 5],
            "evidence_spans": [
                {
                    "evidence_id": "verified-fact:fact-1",
                    "source_pack": "verified_facts",
                    "page": 5,
                    "text": (
                        "The first verified fact is incorrectly attached to page 5."
                    ),
                    "source_identity": SOURCE_IDENTITY,
                },
                {
                    "evidence_id": "verified-fact:fact-2",
                    "source_pack": "verified_facts",
                    "page": 4,
                    "text": (
                        "The second verified fact is incorrectly attached to page 4."
                    ),
                    "source_identity": SOURCE_IDENTITY,
                },
            ],
        }
    )

    with pytest.raises(AppError, match="span page conflicts"):
        validate_verified_artifact_bindings(
            artifacts,
            {"fact-1": first, "fact-2": second},
        )


def test_verified_unknown_additional_binding_fails_closed():
    artifacts = _verified_artifacts()
    artifacts["insights_final"][0]["evidence_ids"] = [
        "verified-fact:fact-1",
        "verified-fact:missing",
    ]

    with pytest.raises(AppError) as exc_info:
        validate_evidence_references(artifacts, _packs(), _ctx())

    assert exc_info.value.code == "verified_fact_snapshot_invalid"


@pytest.mark.parametrize(
    "text",
    [
        "Adoption reached 99% among buyers in 2026.",
        "Revenue reached 42% among buyers in 2026.",
        "Adoption reached 42% among buyers in 2024.",
    ],
)
def test_verified_editorial_copy_is_deferred_to_semantic_grounding(text):
    report = evaluate_public_editorial_quality(
        report_id="verified-authority",
        artifacts=_verified_artifacts(insight=_insight(text=text)),
    )

    assert {
        "public_editorial_quality.unsupported_numeric_claim",
        "public_editorial_quality.metric_label_relationship",
        "public_editorial_quality.temporal_integrity",
    }.isdisjoint({issue.rule_id for issue in report.issues})


def test_verified_quality_propagates_invalid_authority_snapshot():
    fact = _fact()
    fact["source_pdf_sha256"] = "b" * 64

    with pytest.raises(AppError, match="PDF hash"):
        evaluate_public_editorial_quality(
            report_id="verified-authority",
            artifacts=_verified_artifacts(fact=fact),
        )


def test_verified_expert_number_is_deferred_to_semantic_grounding():
    artifacts = _verified_artifacts()
    artifacts["expert_comment"] = "Revenue reached 99% and should drive expansion."

    report = evaluate_public_editorial_quality(
        report_id="verified-authority", artifacts=artifacts
    )

    assert "public_editorial_quality.unsupported_numeric_claim" not in {
        issue.rule_id for issue in report.issues
    }


def test_verified_composite_observation_label_swap_is_deferred_to_semantic_grounding():
    observations = [
        {"label": "Creators", "value": "42%", "unit": "%", "timeframe": "2026"},
        {"label": "Views", "value": "18%", "unit": "%", "timeframe": "2026"},
    ]
    metric = _metric(observations=observations)
    insight = _insight(
        text="Views reached 42% among buyers in 2026.",
        metric=metric,
    )

    report = evaluate_public_editorial_quality(
        report_id="verified-authority",
        artifacts=_verified_artifacts(insight=insight, fact=_fact(metric=metric)),
    )

    assert "public_editorial_quality.metric_label_relationship" not in {
        issue.rule_id for issue in report.issues
    }


def test_verified_observations_must_remain_structured():
    fact = _fact(metric=_metric(observations=["not-an-observation"]))

    with pytest.raises(AppError):
        validated_verified_facts(_verified_artifacts(fact=fact), _packs(fact))


def test_verified_snapshot_hash_and_reference_fail_closed(tmp_path):
    fact = _fact()
    bad_fact = deepcopy(fact)
    bad_fact["source_pdf_sha256"] = "b" * 64
    artifacts = _verified_artifacts(fact=bad_fact)
    artifacts["insights_final"][0]["evidence_id"] = "verified-fact:missing"
    with pytest.raises(AppError):
        validate_evidence_references(artifacts, _packs(bad_fact), _ctx())


def test_verified_snapshot_missing_provenance_fails_closed():
    fact = _fact()
    fact["provenance"] = {}

    with pytest.raises(AppError):
        validated_verified_facts(_verified_artifacts(fact=fact), _packs(fact))


def test_verified_artifact_page_binding_fails_closed():
    artifacts = _verified_artifacts()
    artifacts["insights_final"][0]["pages"] = [9]

    with pytest.raises(AppError) as exc_info:
        validate_evidence_references(artifacts, _packs(), _ctx())

    assert exc_info.value.code == "verified_fact_snapshot_invalid"


def test_verified_artifact_span_source_identity_fails_closed():
    artifacts = _verified_artifacts()
    artifacts["insights_final"][0]["evidence_spans"][0]["source_identity"] = (
        "other|pdf-sha256:" + SOURCE_SHA
    )

    with pytest.raises(AppError) as exc_info:
        validate_evidence_references(artifacts, _packs(), _ctx())

    assert exc_info.value.code == "verified_fact_snapshot_invalid"


def test_verified_references_cannot_fall_back_to_legacy_source_ids():
    artifacts = _verified_artifacts()
    artifacts["insights_final"][0]["evidence_id"] = "finding-legacy"
    packs = _packs()
    packs["findings"]["findings"].append(
        {
            "id": "finding-legacy",
            "text": "Legacy extraction says 99%.",
            "evidence": "Legacy extraction says 99%.",
            "pages": [9],
        }
    )

    with pytest.raises(AppError) as exc_info:
        validate_evidence_references(artifacts, packs, _ctx())

    assert exc_info.value.context["missing_references"] == ["finding-legacy"]


def test_normal_mode_numeric_quality_rule_remains_active():
    report = evaluate_public_editorial_quality(
        report_id="normal-mode",
        artifacts={
            "insights_final": [
                {
                    "id": "normal-1",
                    "text": "Adoption reached 99%.",
                    "evidence_id": "finding-1",
                    "evidence": "Adoption reached 42%.",
                    "metric": {},
                }
            ]
        },
    )

    assert "public_editorial_quality.unsupported_numeric_claim" in {
        issue.rule_id for issue in report.issues
    }
