import hashlib
import json

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
from tests._test_report_regeneration_generator import (
    _split_support_test_report_regeneration_generator as support,
)


def test_short_scoped_summary_repair_preserves_copy_and_provenance(tmp_path):
    current = support._current_artifacts()
    tldr = "The market is growing steadily."
    original = "The original claim needs repair."
    current["summary"].update(
        tldr=tldr, card_tldr_compact=tldr, executive_summary=original
    )
    old_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="summary",
            claim_id=f"soft_copy:summary:replay:{i}",
            text_hash=hashlib.sha256(text.encode()).hexdigest(),
            classification="factual",
            evidence_ids=("f1",),
            source_spans=(),
            producing_prompt_identity={"namespace": "report_vs/artifacts/summary"},
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for i, text in enumerate((tldr, original))
    ]
    current["soft_copy_claim_provenance"]["claims"] = [
        c
        for c in current["soft_copy_claim_provenance"]["claims"]
        if c["artifact_family"] != "summary"
    ] + soft_copy_claim_provenance_to_payload(old_claims)["claims"]
    evidence = support._evidence_packs()
    evidence["findings"]["findings"].append(
        {"id": "f3", "evidence": "Sales grew.", "text": "Sales grew."}
    )
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                rule_id="grounding",
                affected_section="summary.executive_summary",
                message="Claim requires repair.",
                severity="error",
                entity_id=old_claims[1].claim_id,
                evidence_ids=["f1"],
            )
        ],
        artifacts=current,
        broad_retry_available=False,
    )

    class Provider:
        def openai_chat_json(self, req, ctx):
            payload = {
                "claim_repair_proposal": {
                    "schema_version": "1.0",
                    "action": "replace",
                    "replacement_text": "Sales grew.",
                    "evidence_ids_used": ["f3"],
                }
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                request_id="short-repair",
            )

    result = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=plan,
            current_artifacts=current,
            doc_map=evidence["doc_map"],
            evidence_packs=evidence,
            settings=support._settings(tmp_path),
            ctx=support._ctx(),
            source_status=current["source_status"],
            categories=["Category"],
        ),
        openai_client=Provider(),
        prompt_client=support._FakePromptClient(),
    )
    updated = result.updated_artifacts
    assert updated["summary"]["executive_summary"] == "Sales grew.", repr(
        result.repair_decisions
    )
    claims = updated["soft_copy_claim_provenance"]["claims"]
    repaired = [
        c for c in claims if c.get("repaired_from_claim_id") == old_claims[1].claim_id
    ]
    assert len(repaired) == 1
    assert repaired[0]["text_hash"] == hashlib.sha256(b"Sales grew.").hexdigest()
    assert repaired[0]["evidence_ids"] == ["f3"]
