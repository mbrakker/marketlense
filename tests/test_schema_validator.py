import pytest

from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.services.schema_validator_service import (
    provider_output_schema,
    validate_evidence_references,
    validate_schema,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_validate_schema_passes_for_doc_map():
    payload = {
        "doc_id": "doc-1",
        "title": "Doc Title",
        "sections": [
            {
                "id": "s1",
                "title": "Intro",
                "summary": "text",
                "key_points": ["Point 1"],
                "pages": [1, 2],
                "references": ["r1"],
            }
        ],
    }
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0", payload=payload, schema_name="doc_map"
        ),
        _ctx(),
    )


def test_validate_schema_fails_missing_required():
    payload = {"title": "Missing sections"}
    with pytest.raises(AppError) as exc:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0", payload=payload, schema_name="doc_map"
            ),
            _ctx(),
        )
    assert exc.value.code == "schema_missing_required"


def test_validate_schema_fails_when_doc_map_section_missing_summary_or_key_points():
    payload = {
        "doc_id": "doc-1",
        "title": "Doc Title",
        "sections": [{"id": "s1", "title": "Intro"}],
    }
    with pytest.raises(AppError) as exc:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0", payload=payload, schema_name="doc_map"
            ),
            _ctx(),
        )
    assert exc.value.code == "schema_missing_required"


def test_validate_schema_passes_for_findings_linked_to_doc_map_section():
    payload = {
        "findings": [
            {
                "id": "f1",
                "text": "Investment follows attributable outcomes.",
                "evidence": "The report links buyer budgets to attribution.",
                "pages": [8],
                "section_id": "investment-outlook",
                "section_title": "Investment outlook",
            }
        ]
    }
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0", payload=payload, schema_name="findings_pack"
        ),
        _ctx(),
    )


def test_validate_schema_allows_nullable_union_fields():
    payload = {
        "taxonomy": ["Retail", "FMCG"],
        "region": None,
        "time_period": None,
        "not_found_reason": None,
    }
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0", payload=payload, schema_name="taxonomy"
        ),
        _ctx(),
    )


def test_validate_schema_rejects_invalid_union_type():
    payload = {
        "taxonomy": ["Retail"],
        "region": 123,
        "time_period": "2025",
    }
    with pytest.raises(AppError) as exc:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0", payload=payload, schema_name="taxonomy"
            ),
            _ctx(),
        )
    assert exc.value.code == "schema_type_mismatch"


def test_validate_schema_allows_string_variant_in_object_union():
    payload = {
        "scope": "Report scope text",
        "methods": [],
        "findings": [],
        "limitations": [],
        "quote_candidates": [],
    }
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0", payload=payload, schema_name="evidence_pack"
        ),
        _ctx(),
    )


def test_validate_schema_enforces_one_of_for_methods_items():
    payload = {
        "scope": "",
        "methods": [42],
        "findings": [],
        "limitations": [],
        "quote_candidates": [],
    }
    with pytest.raises(AppError) as exc:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0", payload=payload, schema_name="evidence_pack"
            ),
            _ctx(),
        )
    assert exc.value.code == "schema_type_mismatch"


def test_provider_schema_types_const_values_for_strict_openai_responses():
    schema = provider_output_schema("grounding_validation_output")

    classification = schema["properties"]["checks"]["items"]["properties"][
        "classification"
    ]

    assert classification == {"const": "factual_claim", "type": "string"}


def test_validate_evidence_references_passes_for_known_ids():
    artifacts_payload = {
        "summary": {
            "claim_evidence_map": [
                {
                    "claim": "c",
                    "evidence_id": "f1",
                    "evidence_spans": [
                        {"evidence_id": "f1", "source_pack": "findings", "page": 2}
                    ],
                }
            ]
        },
        "insights_candidates": [
            {
                "id": "i1",
                "evidence_id": "f1",
                "evidence_spans": [
                    {"evidence_id": "f1", "source_pack": "findings", "page": 2}
                ],
            }
        ],
        "insights_final": [{"id": "i2", "evidence_id": "f1"}],
        "quotes_final": [
            {
                "text": "q",
                "evidence_id": "q1",
                "evidence_spans": [
                    {
                        "evidence_id": "q1",
                        "source_pack": "quote_candidates",
                        "page": 1,
                    }
                ],
            }
        ],
    }
    evidence_packs = {
        "findings": {
            "findings": [{"id": "f1", "text": "Finding", "evidence": "Support"}]
        },
        "quote_candidates": {"quote_candidates": [{"id": "q1", "text": "Quote"}]},
    }
    validate_evidence_references(artifacts_payload, evidence_packs, _ctx())


def test_validate_evidence_references_accepts_retained_key_metric_ids():
    artifacts_payload = {
        "summary": {"claim_evidence_map": [{"claim": "c", "evidence_id": "m2"}]},
        "insights_candidates": [{"id": "i1", "evidence_id": "m3"}],
        "insights_final": [{"id": "i2", "evidence_id": "m4"}],
        "quotes_final": [{"text": "q", "evidence_id": "m5"}],
    }
    evidence_packs = {
        "key_metrics": {
            "schema_version": "1.0",
            "key_metrics": [
                {
                    "id": "m2",
                    "metric": "Priority share",
                    "value": "8.8%",
                    "unit": "percent",
                    "evidence_id": "",
                    "pages": [25],
                },
                {
                    "id": "m3",
                    "metric": "Personalization share",
                    "value": "10.8%",
                    "unit": "percent",
                    "evidence_id": "",
                    "pages": [20],
                },
                {
                    "id": "m4",
                    "metric": "AI priority share",
                    "value": "40.6%",
                    "unit": "percent",
                    "evidence_id": "",
                    "pages": [6],
                },
                {
                    "id": "m5",
                    "metric": "Conversion increase",
                    "value": "+258%",
                    "unit": "percent",
                    "evidence_id": "",
                    "pages": [24],
                },
            ],
        }
    }
    validate_evidence_references(artifacts_payload, evidence_packs, _ctx())


def test_validate_evidence_references_fails_for_unknown_ids():
    artifacts_payload = {
        "summary": {"claim_evidence_map": [{"claim": "c", "evidence_id": "missing"}]},
        "insights_candidates": [],
        "insights_final": [],
        "quotes_final": [],
    }
    evidence_packs = {
        "findings": {
            "findings": [{"id": "f1", "text": "Finding", "evidence": "Support"}]
        },
    }
    with pytest.raises(AppError) as exc:
        validate_evidence_references(artifacts_payload, evidence_packs, _ctx())
    assert exc.value.code == "schema_reference_missing"
