import json
from pathlib import Path

import jsonschema
import pytest

from src.contracts.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationRequest,
)
from src.generators.validation.cache import (
    validation_cache_key,
    validation_cache_meta,
    validation_report_from_payload,
)
from src.generators.validation.shared import downgrade_issues_for_data_gap
from src.orchestrators._report_generation_orchestrator.checkpoints import (
    _validation_report_from_dict,
)
from src.utils.validation import parse_validation_report_payload
from tests._test_validation_generator._shared import (
    FakePromptClient,
    _ctx,
    _report,
    _settings,
)


@pytest.mark.parametrize("old_version", ["8", "9"])
def test_legacy_cached_verdicts_cannot_bypass_explicit_outcome_handover(
    tmp_path, old_version
):
    current = validation_cache_meta(
        request=ValidationRequest(
            schema_version="1.0",
            report_id="cache-test",
            report=_report(),
            artifacts={"insights_final": []},
            evidence_packs={},
        ),
        settings=_settings(tmp_path),
        prompt_client=FakePromptClient(),
        ctx=_ctx(),
        md5="source-md5",
        grounding_retrieval_mode="chat",
    )
    old = {**current, "validation_ruleset_version": old_version}
    assert validation_cache_key(current) != validation_cache_key(old)


@pytest.mark.parametrize("outcome", ["entailed", "contradicted", "not_established"])
def test_outcome_survives_validation_report_readers_and_issue_copy(outcome):
    issue = ValidationIssue(
        message="A grounding finding.",
        severity="error",
        affected_section="summary",
        rule_id="grounding",
        entailment_outcome=outcome,
    )
    report = ValidationReport(schema_version="1.1", status="fail", issues=[issue])
    payload = report.to_dict()
    assert payload["issues"][0]["entailment_outcome"] == outcome
    schema = json.loads(Path("src/schemas/validation_report.schema.json").read_text())
    jsonschema.validate(payload, schema)
    for restored in (
        validation_report_from_payload(payload, ""),
        parse_validation_report_payload(payload),
        _validation_report_from_dict(payload),
    ):
        assert restored.issues[0].entailment_outcome == outcome
    assert downgrade_issues_for_data_gap([issue])[0].entailment_outcome == outcome


def test_legacy_issues_remain_compatible_and_invalid_outcome_is_rejected():
    payload = {
        "schema_version": "1.1",
        "status": "fail",
        "severity": "error",
        "issues": [
            {"message": "legacy", "severity": "error", "affected_section": "summary"}
        ],
    }
    schema = json.loads(Path("src/schemas/validation_report.schema.json").read_text())
    jsonschema.validate(payload, schema)
    for restored in (
        validation_report_from_payload(payload, ""),
        parse_validation_report_payload(payload),
        _validation_report_from_dict(payload),
    ):
        assert restored.issues[0].entailment_outcome == ""
        assert "entailment_outcome" not in restored.to_dict()["issues"][0]
    payload["issues"][0]["entailment_outcome"] = "untrusted"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)
