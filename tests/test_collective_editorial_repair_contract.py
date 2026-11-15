from copy import deepcopy

import pytest

from src.orchestrators._report_analysis_orchestrator.validation import (
    _validate_public_editorial_review_payload,
)
from src.services.schema_validator_service import provider_output_schema
from src.utils.errors import AppError
from tests._test_pre_e2e_integrity.cases_01_public_surfaces_and_status import (
    _valid_report_review_payload,
)
from tests._test_validation_generator._shared import _ctx


@pytest.mark.parametrize(
    "invalid",
    [
        "unknown",
        "duplicate",
        "target",
        "evidence",
        "empty_evidence",
        "reason",
        "pass",
        "factual",
        "mixed_targets",
        "missing_evidence_text",
        "factual_surface",
        "quote_surface",
        "unrelated_dimension",
        "factual_verdict",
        "item_factual_failure",
    ],
)
def test_collective_review_rejects_unauthorized_repair_nominations(invalid):
    items, scope, payload = _valid_report_review_payload()
    base = next(i for i in items if i.get("repair_target") and i.get("evidence_ids"))
    item = {
        **base,
        "public_item_id": "insight:fact-1:so_what",
        "field": "insights:fact-1.so_what",
    }
    items.append(item)
    verdict = next(
        v for v in payload["verdicts"] if v["item_id"] == base["public_item_id"]
    )
    selected_verdict = {
        **verdict,
        "item_id": item["public_item_id"],
        "classification": "analyst_interpretation",
    }
    payload["verdicts"].append(selected_verdict)
    nomination = {
        "item_id": item["public_item_id"],
        "repair_target": item["repair_target"],
        "evidence_ids": list(item["evidence_ids"]),
        "reason": "Develop a distinct commercial implication.",
    }
    report = payload["report_verdict"]
    report.update(
        status="fail",
        severity="error",
        rule_id="public_editorial_quality.semantic_analytical_depth",
        hard_fail_class="editorial_quality",
        reason="The report lacks distinct analysis.",
        repair_items=[nomination],
    )
    report["dimensions"]["analytical_depth"] = {
        "status": "fail",
        "reason": "The public insights repeat facts.",
    }
    if invalid == "unknown":
        nomination["item_id"] = "unknown-item"
    elif invalid == "duplicate":
        report["repair_items"].append(deepcopy(nomination))
    elif invalid == "target":
        nomination["repair_target"] = "not-the-allowed-target"
    elif invalid == "evidence":
        nomination["evidence_ids"] = ["unbound-evidence"]
    elif invalid == "empty_evidence":
        nomination["evidence_ids"] = []
    elif invalid == "reason":
        nomination["reason"] = "  "
    elif invalid == "factual":
        report["hard_fail_class"] = "factual_error"
    elif invalid == "mixed_targets":
        report["affected_item_id"] = item["public_item_id"]
        report["repair_target"] = item["repair_target"]
    elif invalid == "missing_evidence_text":
        item["evidence_text"] = ""
    elif invalid == "factual_surface":
        item["field"] = "insights:fact-1"
    elif invalid == "quote_surface":
        item["artifact"] = "quotes_final"
    elif invalid == "unrelated_dimension":
        report["dimensions"]["analytical_depth"]["status"] = "pass"
        report["dimensions"]["material_coverage"]["status"] = "fail"
    elif invalid == "factual_verdict":
        selected_verdict["classification"] = "factual_claim"
    elif invalid == "item_factual_failure":
        selected_verdict.update(
            status="fail",
            severity="error",
            rule_id="public_editorial_quality.semantic_integrity",
            hard_fail_class="factual_error",
            reason="The interpretation contains an unsupported factual premise.",
            repair_target=item["repair_target"],
        )
    else:
        report.update(status="pass", severity="info", rule_id="", hard_fail_class="")
        report["dimensions"]["analytical_depth"]["status"] = "pass"
    with pytest.raises(AppError):
        _validate_public_editorial_review_payload(payload, items, _ctx(), scope)


def test_collective_review_provider_schema_requires_explicit_nomination_array():
    schema = provider_output_schema("public_editorial_quality_review")
    report = schema["properties"]["report_verdict"]
    assert "repair_items" in report["required"]
    assert report["properties"]["repair_items"]["type"] == "array"
