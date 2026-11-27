# ruff: noqa: F401,F403,F405
from __future__ import annotations

from tests._test_report_regeneration_generator._split_support_test_report_regeneration_generator import *  # noqa: E501,F401,F403


def test_atomic_insight_provider_receives_scoped_grounding_with_large_roster(tmp_path):
    import logging

    from src.contracts.llm import LLMContextCompactionPolicy
    from src.services import prompt_service
    from src.services._llm_service.context_compaction import (
        compact_prompt_request_if_needed,
    )

    current = _current_artifacts()
    current["insights_final"][1]["text"] = "UNRELATED_ROSTER_MARKER " + "x" * 150000
    before = deepcopy(current["insights_final"])
    evidence = _evidence_packs()
    fact = {
        "id": "f1",
        "text": "Among US adults in 2025, 42 percent used podcasts weekly.",
        "evidence": "Among US adults in 2025, 42 percent used podcasts weekly.",
        "pages": [1],
        "qualifier": "weekly; US adults; 2025",
    }
    evidence["findings"]["findings"][0] = fact
    issue = RegenerationIssue(
        rule_id="public_editorial_quality.so_what",
        affected_section="insights:insight-1.text",
        message="Repair the wording.",
        severity="error",
        entity_id="insight:insight-1:text",
        evidence_ids=["f1"],
    )
    path = "insights_final[item=insight-1].text"
    target = RegenerationTarget(
        target_section="insights_bundle",
        regenerate_steps=["insights_final"],
        prompt_namespaces=["report_vs/artifacts/regenerate/insights_final"],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        allowed_paths=[path],
        issues=[issue],
    )

    class Provider:
        def __init__(self):
            self.requests = []

        def openai_chat_json(self, req, ctx):
            policy = LLMContextCompactionPolicy(
                schema_version="1.0", enabled=True, max_input_tokens=12000
            )
            sent, _ = compact_prompt_request_if_needed(
                request=replace(req, context_compaction_policy=policy),
                ctx=ctx,
                operation="regression",
                logger=logging.getLogger(__name__),
            )
            self.requests.append(sent)
            payload = {
                "repair_decision": {
                    "schema_version": "1.0",
                    "repair_action": "REGENERATE_ITEM",
                    "repair_strategy": "current_evidence",
                    "evidence_ids_used": ["f1"],
                    "changed_paths": [path],
                    "minimal_patch": [
                        {
                            "op": "replace",
                            "path": path,
                            "value": "A corrected grounded insight.",
                        }
                    ],
                }
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                request_id="fixture",
            )

    provider = Provider()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[target],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current,
            doc_map=evidence["doc_map"],
            evidence_packs=evidence,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
        ),
        openai_client=provider,
        prompt_client=prompt_service,
    )
    assert len(provider.requests) == 1
    prompt = provider.requests[0].user_prompt
    assert "UNRELATED_ROSTER_MARKER" not in prompt
    context_line = next(
        line for line in prompt.splitlines() if "Repair context JSON:" in line
    )
    context = json.loads(context_line.split("Repair context JSON:", 1)[1])
    assert context["allowed_paths"] == [path]
    assert "Task:" in prompt and "Repair only the declared final insight" in prompt
    grounding_line = next(
        line for line in prompt.splitlines() if "Grounding package JSON:" in line
    )
    grounding = json.loads(grounding_line.split("Grounding package JSON:", 1)[1])
    assert "current_section" not in grounding
    assert grounding["evidence_ids"] == ["f1"]
    assert fact in [
        entry.get("entry", entry) for entry in grounding["relevant_evidence"]
    ]
    assert (
        response.updated_artifacts["insights_final"][0]["text"]
        == "A corrected grounded insight."
    )
    assert (
        response.updated_artifacts["insights_final"][0]["evidence_id"]
        == before[0]["evidence_id"]
    )
    assert response.updated_artifacts["insights_final"][1:] == before[1:]
