from types import SimpleNamespace

from src.contracts.validation import ValidationRequest
from src.generators.validation.grounding import grounding_payload, run_grounding_check
from src.services import prompt_service
from tests._test_validation_generator._shared import FakeOpenAI, _ctx, _settings
from tests.test_grounding_recovery_diagnostics import _raw_grounding_check
from tests.test_verified_facts_validation_authority import (
    SOURCE_IDENTITY,
    _fact,
    _packs,
    _report,
    _verified_artifacts,
)


def test_grounding_recovery_supplies_vocabulary_and_preserves_aliases(tmp_path):
    fact = _fact()
    artifacts = _verified_artifacts(fact=fact)
    request = ValidationRequest(
        schema_version="1.0",
        report_id="grounding-vocabulary-recovery",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=_packs(fact),
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts",
    )
    payload = grounding_payload(request, artifacts)
    entries = payload["retained_claims_to_ground"] + payload["public_factual_items"]
    checks = [
        _raw_grounding_check(
            entry["item_id"],
            entry["text"],
            "entailed",
            classification=entry.get("declared_classification", "factual_claim"),
        )
        for entry in entries
    ]
    invalid = [dict(check) for check in checks]
    invalid[0]["violation_type"] = "unsupported_unknown_type"
    repaired = [dict(check) for check in checks]
    repaired[0]["violation_type"] = "no_violation"

    class RecordingProvider(FakeOpenAI):
        def __init__(self):
            super().__init__(
                {"checks": invalid},
                {"checks": repaired},
                complete_grounding_contract=False,
            )
            self.schemas = []

        def openai_chat_json(self, req, ctx):
            self.schemas.append(req.structured_output_schema)
            return super().openai_chat_json(req, ctx)

    provider = RecordingProvider()
    issues = run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=prompt_service,
        openai_client=provider,
        ctx=_ctx(),
        source_id=SOURCE_IDENTITY,
        prompt_family_reuse_reader=lambda *_args: SimpleNamespace(
            reusable=False, output_payload=None, reason="test_vocabulary"
        ),
    )

    assert issues == []
    assert len(provider.schemas) == 2
    for schema in provider.schemas:
        field = schema["properties"]["checks"]["items"]["properties"]["violation_type"]
        description = field["description"]
        assert "entailed" in description and "none" in description
        assert (
            "not_established" in description
            and "unsupported_factual_claim" in description
        )
        assert "non_fatal_interpretation" in description
