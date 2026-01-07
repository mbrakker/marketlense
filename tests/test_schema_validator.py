import pytest

from src.contracts.run_context import RunContext
from src.utils.schema_validator import validate_schema
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
    validate_schema(payload, "doc_map", _ctx())


def test_validate_schema_fails_missing_required():
    payload = {"title": "Missing sections"}
    with pytest.raises(AppError) as exc:
        validate_schema(payload, "doc_map", _ctx())
    assert exc.value.code == "schema_missing_required"
