import pytest

from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.services.schema_validator_service import validate_schema
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_validate_schema_passes_for_doc_map():
    payload = {
        "doc_id": "doc-1",
        "title": "Doc Title",
        "sections": [
            {"id": "s1", "title": "Intro", "summary": "text", "pages": [1, 2], "references": ["r1"]}
        ],
    }
    validate_schema(
        SchemaValidateRequest(schema_version="1.0", payload=payload, schema_name="doc_map"),
        _ctx(),
    )


def test_validate_schema_fails_missing_required():
    payload = {"title": "Missing sections"}
    with pytest.raises(AppError) as exc:
        validate_schema(
            SchemaValidateRequest(schema_version="1.0", payload=payload, schema_name="doc_map"),
            _ctx(),
        )
    assert exc.value.code == "schema_missing_required"


def test_validate_schema_allows_nullable_union_fields():
    payload = {
        "taxonomy": ["Retail", "FMCG"],
        "region": None,
        "time_period": None,
        "not_found_reason": None,
    }
    validate_schema(
        SchemaValidateRequest(schema_version="1.0", payload=payload, schema_name="taxonomy"),
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
            SchemaValidateRequest(schema_version="1.0", payload=payload, schema_name="taxonomy"),
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
        SchemaValidateRequest(schema_version="1.0", payload=payload, schema_name="evidence_pack"),
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
            SchemaValidateRequest(schema_version="1.0", payload=payload, schema_name="evidence_pack"),
            _ctx(),
        )
    assert exc.value.code == "schema_type_mismatch"
