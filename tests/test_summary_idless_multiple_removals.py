from copy import deepcopy

from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
)
from src.generators.report_regeneration_generator import regenerate_artifacts
from tests._test_report_regeneration_generator import (
    _split_support_test_report_regeneration_generator as support,
)


def test_separate_idless_removals_keep_original_target_identity(tmp_path):
    current = support._current_artifacts()
    claims = [
        {
            "claim": "Retained claim.",
            "evidence_id": "f1",
            "evidence": "Evidence text",
            "pages": [1],
        },
        {
            "claim": "First failed claim.",
            "evidence_id": "f2",
            "evidence": "Evidence text 2",
            "pages": [2],
        },
        {
            "claim": "Second failed claim.",
            "evidence_id": "f1",
            "evidence": "Evidence text",
            "pages": [1],
        },
    ]
    current["summary"]["claim_evidence_map"] = deepcopy(claims)
    targets = [
        RegenerationTarget(
            target_section="summary",
            repair_action="REMOVE_CLAIM",
            repair_strategy="safe_removal",
            issues=[
                RegenerationIssue(
                    rule_id="grounding",
                    affected_section=f"summary.claim_evidence_map:{number}.claim",
                    message="The claim is unsupported.",
                    severity="error",
                    entity_id=f"summary_claim:{number}",
                    evidence_ids=[evidence_id],
                )
            ],
            allowed_paths=[f"summary.claim_evidence_map[{number - 1}]"],
        )
        for number, evidence_id in ((2, "f2"), (3, "f1"))
    ]
    evidence = support._evidence_packs()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(mode="targeted", targets=targets),
            current_artifacts=current,
            doc_map=evidence["doc_map"],
            evidence_packs=evidence,
            settings=support._settings(tmp_path),
            ctx=support._ctx(),
            source_status=current["source_status"],
        ),
        openai_client=support._FakeOpenAIClient(),
        prompt_client=support._FakePromptClient(),
    )

    assert response.updated_artifacts["summary"]["claim_evidence_map"] == [claims[0]]
