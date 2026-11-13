# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json

import pytest

from ._split_support_test_report_regeneration_generator import *  # noqa: F401,F403


def test_summary_claim_map_repair_rejects_abstained_status_with_restored_copy(
    tmp_path,
) -> None:
    class _ClaimMapRepairClient(_FakeOpenAIClient):
        def _legacy_chat_json(self, req, ctx):
            if "system::report_vs/artifacts/regenerate/summary" in req.system_prompt:
                self.calls.append(req)
                payload = {
                    "summary": {
                        "claim_evidence_map": [
                            {
                                "id": "claim-one",
                                "claim": "Corrected retained claim.",
                                "evidence_id": "f1",
                            }
                        ]
                    }
                }
                return OpenAIResponseResult(
                    schema_version="1.0",
                    text=json.dumps(payload),
                    parsed_json=payload,
                    request_id="req-claim-map-abstained",
                )
            return super()._legacy_chat_json(req, ctx)

    artifacts = _current_artifacts()
    # The assembled family must abstain on regeneration when a required public
    # summary field is incomplete. Atomic claim-map reconciliation must not
    # restore the promoted copy while retaining that abstained status.
    artifacts["summary"]["card_tldr_compact"] = ""
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                rule_id="retained_claim.number_value_unit_match",
                affected_section="summary.claim_evidence_map:claim-one.claim",
                message="[retained_claim.number_value_unit_match] repair claim",
                severity="error",
                entity_id="summary_claim:claim-one",
                evidence_ids=["f1"],
            )
        ],
        artifacts=artifacts,
        broad_retry_available=False,
    )

    with pytest.raises(AppError) as error:
        regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=plan,
                current_artifacts=artifacts,
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=artifacts["source_status"],
                categories=["Category"],
                vector_store_id=None,
                md5="md5",
            ),
            openai_client=_ClaimMapRepairClient(),
            prompt_client=_FakePromptClient(),
        )

    assert error.value.code == "regeneration_deterministic_projection_failed"
    assert error.value.context["projection"] == "summary_status_content"
