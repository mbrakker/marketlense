import hashlib
import json
from copy import deepcopy

from src.contracts.openai import OpenAIResponseResult
from src.contracts.regeneration import ArtifactRegenerationRequest
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.contracts.validation import ValidationIssue
from src.generators.report_regeneration_generator import regenerate_artifacts
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from tests._test_report_regeneration_generator._split_support_test_report_regeneration_generator import (  # noqa: E501
    _ctx,
    _current_artifacts,
    _evidence_packs,
    _FakePromptClient,
    _settings,
)


def test_two_summary_claim_repairs_keep_each_replacement_and_its_provenance(tmp_path):
    current = _current_artifacts()
    sentences = [
        "Opening context remains unchanged.",
        "The first original factual claim.",
        "The second original factual claim.",
        "Closing context remains unchanged.",
    ]
    current["summary"]["executive_summary"] = " ".join(sentences)
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="summary",
            claim_id=f"soft_copy:summary:replay:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="factual" if index in (1, 2) else "interpretive",
            evidence_ids=("f1" if index != 2 else "f2",),
            source_spans=(),
            producing_prompt_identity={"namespace": "report_vs/artifacts/summary"},
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences)
    ]
    current["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "summary"
        or claim["text_hash"] == hashlib.sha256(b"Old TLDR.").hexdigest()
    ] + soft_copy_claim_provenance_to_payload(claims)["claims"]
    original_summary = deepcopy(current["summary"])
    original_claims = deepcopy(current["soft_copy_claim_provenance"]["claims"])
    evidence = _evidence_packs()
    evidence["findings"]["findings"].extend(
        [
            {
                "id": "f3",
                "evidence": "The first replacement is supported.",
                "text": "The first replacement is supported.",
            },
            {
                "id": "f4",
                "evidence": "The second replacement is supported.",
                "text": "The second replacement is supported.",
            },
        ]
    )
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                rule_id="grounding",
                affected_section="summary.executive_summary",
                message="The retained factual claim requires repair.",
                severity="error",
                entity_id=claims[index].claim_id,
                evidence_ids=[evidence_id],
            )
            for index, evidence_id in ((1, "f1"), (2, "f2"))
        ],
        artifacts=current,
        broad_retry_available=False,
    )

    class ControlledProvider:
        def __init__(self):
            self.calls = 0

        def openai_chat_json(self, req, ctx):
            del req, ctx
            proposals = [
                ("The first replacement is supported.", "f3"),
                ("The second replacement is supported.", "f4"),
            ]
            replacement, evidence_id = proposals[self.calls]
            self.calls += 1
            payload = {
                "claim_repair_proposal": {
                    "schema_version": "1.0",
                    "action": "replace",
                    "replacement_text": replacement,
                    "evidence_ids_used": [evidence_id],
                }
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                request_id=f"replay-{self.calls}",
            )

    provider = ControlledProvider()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=plan,
            current_artifacts=current,
            doc_map=evidence["doc_map"],
            evidence_packs=evidence,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
        ),
        openai_client=provider,
        prompt_client=_FakePromptClient(),
    )

    updated = response.updated_artifacts
    assert updated["summary"]["executive_summary"] == (
        "Opening context remains unchanged. The first replacement is supported. "
        "The second replacement is supported. Closing context remains unchanged."
    ), f"calls={provider.calls}; decisions={response.repair_decisions!r}"
    assert provider.calls == 2
    assert {
        k: v for k, v in updated["summary"].items() if k != "executive_summary"
    } == {k: v for k, v in original_summary.items() if k != "executive_summary"}
    result_claims = updated["soft_copy_claim_provenance"]["claims"]
    by_id = {claim["claim_id"]: claim for claim in result_claims}
    for original in original_claims:
        if original["claim_id"] not in {claims[1].claim_id, claims[2].claim_id}:
            assert by_id[original["claim_id"]] == original
    for index, replacement, evidence_id in (
        (1, "The first replacement is supported.", "f3"),
        (2, "The second replacement is supported.", "f4"),
    ):
        repaired = [
            c
            for c in result_claims
            if c.get("repaired_from_claim_id") == claims[index].claim_id
        ]
        assert len(repaired) == 1
        assert (
            repaired[0]["text_hash"] == hashlib.sha256(replacement.encode()).hexdigest()
        )
        assert repaired[0]["evidence_ids"] == [evidence_id]
        assert claims[index].claim_id not in by_id
