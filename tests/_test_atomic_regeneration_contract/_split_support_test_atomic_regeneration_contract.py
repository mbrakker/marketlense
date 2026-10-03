# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_atomic_regeneration_contract.py"
)

import hashlib
from copy import deepcopy
from types import SimpleNamespace
import pytest
from src.contracts.regeneration import RegenerationIssue, RegenerationTarget
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.contracts.validation import ValidationIssue
from src.generators.report_regeneration_generator import (
    _apply_repair_decision_patch,
    _read_repair_path,
    _render_regeneration_model,
    _required_repair_protected_fields,
    _validate_model_writable_paths,
    _validated_repair_decision,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _allowed_paths,
    _build_regeneration_plan,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _scope_validation_report,
)
from src.services.schema_validator_service import validate_schema
from src.utils.artifact_diff import artifact_diff_paths
from src.utils.errors import AppError


def _insight_artifacts() -> dict[str, object]:
    return {
        "insights_final": [
            {
                "id": "insight-1",
                "text": "Original insight.",
                "so_what": "Original implication.",
                "now_what": "Original action.",
                "evidence_id": "evidence-1",
                "evidence": "Retained source excerpt.",
                "evidence_spans": [{"start": 1, "end": 2}],
                "pages": [1],
                "metric": {
                    "value": "25%",
                    "unit": "",
                    "label": "Existing metric",
                    "subject": "protected subject",
                    "cohort": "protected cohort",
                    "denominator": "protected denominator",
                    "observation_status": "observed",
                },
            },
            {
                "id": "insight-2",
                "text": "Unrelated sibling insight.",
                "so_what": "Unrelated sibling implication.",
                "now_what": "Unrelated sibling action.",
                "evidence_id": "evidence-2",
                "metric": {
                    "value": "40%",
                    "unit": "sibling unit",
                    "subject": "sibling fact",
                },
            },
        ]
    }


def _insight_issue(field: str, *, insight_id: str = "insight-1") -> RegenerationIssue:
    return RegenerationIssue(
        rule_id="grounding",
        affected_section=f"insights:{insight_id}.{field}",
        entity_id=f"insight:{insight_id}:{field}",
        message="The retained field needs a grounded repair.",
        severity="error",
        evidence_ids=["retained-evidence"],
    )


def _execution(target: RegenerationTarget) -> SimpleNamespace:
    return SimpleNamespace(
        target=target,
        runtime=SimpleNamespace(request=SimpleNamespace(report_id="report-1")),
    )


def _decision_payload(
    *,
    target: RegenerationTarget,
    artifacts: dict[str, object],
    patches: list[tuple[str, object]],
    evidence_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "repair_action": target.repair_action,
        "repair_strategy": target.repair_strategy,
        "evidence_ids_used": evidence_ids or [],
        "changed_paths": [path for path, _ in patches],
        "minimal_patch": [
            {
                "op": "replace",
                "path": path,
                "value": value,
            }
            for path, value in patches
        ],
    }


def _target(paths: list[str], issues: list[RegenerationIssue]) -> RegenerationTarget:
    return RegenerationTarget(
        target_section="insights_bundle",
        regenerate_steps=["insights_final"],
        prompt_namespaces=[],
        issues=issues,
        repair_action="CORRECT_PROTECTED_FACT",
        repair_strategy="retained_evidence",
        allowed_paths=paths,
    )


def _soft_copy_claim(family: str, claim_id: str, text: str) -> SoftCopyClaimProvenance:
    return SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family=family,
        claim_id=claim_id,
        text_hash=hashlib.sha256(" ".join(text.split()).encode()).hexdigest(),
        classification="interpretive",
        evidence_ids=("retained-evidence",),
        source_spans=(),
        producing_prompt_identity={"namespace": f"report_vs/artifacts/{family}"},
        generation_attempt=1,
        regeneration_attempt=0,
    )


def _model_repair_path_case(case_id: str) -> dict[str, object]:
    artifacts: dict[str, object] = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "summary-claim-1",
                    "claim": "Original summary map claim.",
                    "evidence_id": "retained-evidence",
                    "evidence": "Retained source excerpt.",
                },
                {
                    "id": "summary-claim-2",
                    "claim": "Unchanged summary map sibling.",
                    "evidence_id": "sibling-evidence",
                    "evidence": "Other retained source excerpt.",
                },
            ],
            "executive_summary": "Original summary claim. Unchanged summary sibling.",
            "tldr": "Original TLDR claim. Unchanged TLDR sibling.",
            "card_tldr_compact": "Compact summary.",
        },
        **_insight_artifacts(),
        "insights_candidates": [
            {
                "id": "candidate-1",
                "text": "Original candidate insight.",
                "evidence_id": "retained-evidence",
                "metric": {"value": "15%", "unit": "percent"},
            },
            {
                "id": "candidate-2",
                "text": "Unchanged candidate sibling.",
                "evidence_id": "sibling-evidence",
                "metric": {"value": "20%", "unit": "points"},
            },
        ],
        "quotes_final": [
            {
                "id": "quote-1",
                "text": "Original quote text.",
                "evidence_id": "retained-evidence",
            },
            {
                "id": "quote-2",
                "text": "Unchanged quote sibling.",
                "evidence_id": "sibling-evidence",
            },
        ],
        "expert_comment": "Original expert claim. Unchanged expert sibling.",
        "linkedin_post": "Original LinkedIn claim. Unchanged LinkedIn sibling.",
    }
    provenance = [
        _soft_copy_claim(
            "summary", "soft_copy:summary:executive-claim", "Original summary claim."
        ),
        _soft_copy_claim(
            "summary", "soft_copy:summary:tldr-claim", "Original TLDR claim."
        ),
        _soft_copy_claim(
            "expert_comment",
            "soft_copy:expert_comment:claim-1",
            "Original expert claim.",
        ),
        _soft_copy_claim(
            "expert_comment",
            "soft_copy:expert_comment:claim-2",
            "Unchanged expert sibling.",
        ),
        _soft_copy_claim(
            "linkedin_post",
            "soft_copy:linkedin_post:claim-1",
            "Original LinkedIn claim.",
        ),
        _soft_copy_claim(
            "linkedin_post",
            "soft_copy:linkedin_post:claim-2",
            "Unchanged LinkedIn sibling.",
        ),
    ]
    artifacts["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        provenance
    )

    if case_id == "summary_claim":
        family = "summary"
        issue = RegenerationIssue(
            rule_id="retained_claim.number_value_unit_match",
            affected_section="summary.claim_evidence_map:summary-claim-1.claim",
            entity_id="summary_claim:summary-claim-1",
            message="The summary map claim needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = "summary.claim_evidence_map[item=summary-claim-1].claim"
        sibling = "summary.claim_evidence_map[item=summary-claim-2].claim"
        parent = "summary.claim_evidence_map[item=summary-claim-1]"
    elif case_id == "summary_tldr":
        family = "summary"
        issue = RegenerationIssue(
            rule_id="grounding",
            affected_section="summary.tldr",
            entity_id="soft_copy:summary:tldr-claim",
            message="The TLDR claim needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = "summary.tldr[claim_index=0]"
        sibling = "summary.tldr[claim_index=1]"
        parent = "summary.tldr"
    elif case_id == "summary_executive":
        family = "summary"
        issue = RegenerationIssue(
            rule_id="grounding",
            affected_section="summary.executive_summary",
            entity_id="soft_copy:summary:executive-claim",
            message="The executive summary claim needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = "summary.executive_summary[claim_index=0]"
        sibling = "summary.executive_summary[claim_index=1]"
        parent = "summary.executive_summary"
    elif case_id in {
        "insight_text",
        "insight_so_what",
        "insight_metric_value",
        "insight_metric_unit",
        "candidate_text",
        "candidate_metric_value",
        "candidate_metric_unit",
    }:
        family = "insights_bundle"
        field, rule_id = {
            "insight_text": ("text", "grounding"),
            "insight_so_what": ("so_what", "grounding"),
            "insight_metric_value": (
                "metric.value",
                "retained_claim.protected_fact_value_consistency",
            ),
            "insight_metric_unit": (
                "metric.unit",
                "retained_claim.protected_fact_unit_currency_consistency",
            ),
            "candidate_text": ("text", "grounding"),
            "candidate_metric_value": (
                "metric.value",
                "retained_claim.protected_fact_value_consistency",
            ),
            "candidate_metric_unit": (
                "metric.unit",
                "retained_claim.protected_fact_unit_currency_consistency",
            ),
        }[case_id]
        root, identity = (
            ("insights_candidates", "candidate-1")
            if case_id.startswith("candidate_")
            else ("insights_final", "insight-1")
        )
        issue = RegenerationIssue(
            rule_id=rule_id,
            affected_section=f"insights:{identity}.{field}",
            entity_id=f"insight:{identity}:{field}",
            message="The insight leaf needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = f"{root}[item={identity}].{field}"
        sibling_identity = (
            "candidate-2" if root == "insights_candidates" else "insight-2"
        )
        sibling = f"{root}[item={sibling_identity}].{field}"
        parent = f"{root}[item={identity}]"
    elif case_id == "quote_text":
        family = "quotes"
        issue = RegenerationIssue(
            rule_id="grounding",
            affected_section="quotes_final[0].text",
            entity_id="quote:quote-1:text",
            message="The quote text needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = "quotes_final[item=quote-1].text"
        sibling = "quotes_final[item=quote-2].text"
        parent = "quotes_final[item=quote-1]"
    elif case_id == "expert_claim":
        family = "expert_comment"
        issue = RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            entity_id="soft_copy:expert_comment:claim-1",
            message="The Expert View claim needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = "expert_comment[claim_index=0]"
        sibling = "expert_comment[claim_index=1]"
        parent = "expert_comment"
    else:
        family = "linkedin_post"
        issue = RegenerationIssue(
            rule_id="grounding",
            affected_section="linkedin_post",
            entity_id="soft_copy:linkedin_post:claim-1",
            message="The LinkedIn claim needs repair.",
            severity="error",
            evidence_ids=["retained-evidence"],
        )
        expected = "linkedin_post[claim_index=0]"
        sibling = "linkedin_post[claim_index=1]"
        parent = "linkedin_post"
    return {
        "artifacts": artifacts,
        "family": family,
        "issue": issue,
        "expected": expected,
        "sibling": sibling,
        "parent": parent,
    }


def _validate_repair_schema(decision: dict[str, object]) -> None:
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0",
            payload={"repair_decision": decision},
            schema_name="regeneration_repair_decision",
        ),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )


__all__ = [name for name in globals() if not name.startswith("__")]
