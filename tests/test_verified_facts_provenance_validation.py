from copy import deepcopy

import pytest

from src.generators.validation.verified_facts import validated_verified_facts
from src.services.schema_validator_service import validate_evidence_references
from src.utils.errors import AppError
from tests._test_validation_generator._shared import _ctx
from tests.test_verified_facts_validation_authority import (
    SOURCE_SHA,
    _fact,
    _packs,
    _verified_artifacts,
)


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
