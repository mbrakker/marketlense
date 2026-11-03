from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from src.contracts.report_assets import RenderRequest
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationIssue
from src.generators._artifact_generator.storage import (
    build_key_figures,
    build_universal_claim_ledger,
    derive_metric_spine_from_insights,
)
from src.generators.artifact_normalization import (
    normalize_artifact_insights,
    select_artifact_insights,
)
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
    public_editorial_semantic_review_items,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from src.services._render_service.normalization import (
    _coerce_public_claim_support,
    _coerce_public_key_figures,
    _coerce_public_metric_spine,
)
from src.services.render_service import render_report
from tests.test_verified_facts_validation_authority import _authority_artifacts


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _artifacts_with_metric_copy(copy: str | None = "42% of surveyed buyers") -> dict:
    artifacts = deepcopy(_authority_artifacts())
    if copy is not None:
        artifacts["insights_final"][0]["metric_public_copy"] = copy
    spine = derive_metric_spine_from_insights(
        artifacts["insights_final"],
        verified_mode=True,
        verified_facts=artifacts["verified_facts"],
    )
    artifacts["metric_spine"] = spine
    artifacts["key_figures"] = build_key_figures(
        metric_spine=spine,
        evidence_packs={},
        insights_final=artifacts["insights_final"],
        verified_mode=True,
        verified_facts=artifacts["verified_facts"],
    )
    artifacts["claim_ledgers"] = build_universal_claim_ledger(
        report_id="report",
        summary={},
        insights_final=artifacts["insights_final"],
        quotes_final=[],
        metric_spine=spine,
        executive_advisory={},
    )
    return artifacts


def test_metric_public_copy_survives_final_normalization_and_derived_artifacts() -> (
    None
):
    raw = {
        "id": "fact-1",
        "text": "The final finding.",
        "metric_public_copy": "42% of surveyed buyers",
        "evidence_id": "verified-fact:fact-1",
        "evidence": "Adoption reached 42% among buyers in 2026.",
        "metric": deepcopy(_authority_artifacts()["insights_final"][0]["metric"]),
    }
    final = normalize_artifact_insights([raw], prefix="insight", verified_mode=True)

    assert final[0]["metric_public_copy"] == "42% of surveyed buyers"

    spine = derive_metric_spine_from_insights(final, verified_mode=True)
    figures = build_key_figures(
        metric_spine=spine,
        evidence_packs={},
        insights_final=final,
        verified_mode=True,
    )
    assert spine[0]["metric_public_copy"] == "42% of surveyed buyers"
    assert figures[0]["metric_public_copy"] == "42% of surveyed buyers"


def test_matching_final_selection_preserves_editorial_metric_copy() -> None:
    candidate = normalize_artifact_insights(
        [
            {
                "id": "fact-1",
                "text": "The retained candidate.",
                "evidence_id": "verified-fact:fact-1",
                "evidence": "Adoption reached 42% among buyers in 2026.",
                "metric": deepcopy(
                    _authority_artifacts()["insights_final"][0]["metric"]
                ),
            }
        ],
        prefix="candidate",
        verified_mode=True,
    )
    final = normalize_artifact_insights(
        [
            {
                **candidate[0],
                "text": "The final editorial finding.",
                "metric_public_copy": "42% of surveyed buyers adopted the product.",
            }
        ],
        prefix="insight",
        verified_mode=True,
    )

    selected = select_artifact_insights(
        final_insights=final,
        candidate_insights=candidate,
        editorial_plan={
            "report_thesis": "Buyer adoption is the report's lead signal.",
            "themes": [
                {
                    "theme": "adoption",
                    "priority": 1,
                    "evidence_ids": ["verified-fact:fact-1"],
                },
                {
                    "theme": "market context",
                    "priority": 2,
                    "evidence_ids": ["verified-fact:fact-2"],
                },
            ],
        },
        verified_mode=True,
        preserve_all=True,
    )

    assert selected[0]["text"] == "The final editorial finding."
    assert selected[0]["metric_public_copy"] == (
        "42% of surveyed buyers adopted the product."
    )


def test_verified_public_surfaces_omit_metric_without_validated_copy() -> None:
    artifacts = _artifacts_with_metric_copy(None)

    assert _coerce_public_metric_spine(artifacts) == []
    assert _coerce_public_key_figures(artifacts) == []
    assert not any(
        item["artifact_section"] == "metric_spine"
        for item in _coerce_public_claim_support(artifacts)
    )
    assert not any(
        item["artifact"] in {"metric_spine", "key_figures"}
        for item in public_editorial_semantic_review_items(artifacts)
    )


def test_verified_metric_public_copy_is_not_repeated_across_public_surfaces() -> None:
    artifacts = _artifacts_with_metric_copy()

    items = [
        item
        for item in public_editorial_semantic_review_items(artifacts)
        if item["text"] == "42% of surveyed buyers"
    ]

    assert len(items) == 1
    assert items[0]["artifact"] == "metric_spine"


def test_verified_metric_without_public_copy_blocks_before_publication() -> None:
    artifacts = _artifacts_with_metric_copy(None)

    quality = evaluate_public_editorial_quality(
        report_id="metric-copy-missing", artifacts=artifacts
    )

    issues = [
        issue
        for issue in quality.issues
        if issue.rule_id == "public_editorial_quality.material_claim_evidence_missing"
    ]
    assert issues
    assert any(
        issue.affected_field == "insights:fact-1.metric_public_copy" for issue in issues
    )


def test_metric_copy_public_surfaces_use_copy_and_not_diagnostic_claim_text() -> None:
    artifacts = _artifacts_with_metric_copy()

    metric = _coerce_public_metric_spine(artifacts, limit=1)[0]
    figure = _coerce_public_key_figures(artifacts, limit=1)[0]
    claim = next(
        item
        for item in _coerce_public_claim_support(artifacts)
        if item["artifact_section"] == "metric_spine"
    )

    for item in (metric, figure):
        assert item["public_copy"] == "42% of surveyed buyers"
    assert claim["claim"] == "42% of surveyed buyers"
    assert "label=" not in claim["claim"]
    assert "value=" not in claim["claim"]


def test_metric_copy_quality_failure_routes_to_exact_final_leaf() -> None:
    artifacts = _artifacts_with_metric_copy()
    item = next(
        item
        for item in public_editorial_semantic_review_items(artifacts)
        if item["artifact"] == "metric_spine"
    )
    assert item["repair_field"] == "insights:fact-1.metric_public_copy"

    issue = ValidationIssue(
        schema_version="1.0",
        message="[public_editorial_quality.semantic_review] weak metric wording",
        severity="error",
        affected_section=item["repair_field"],
        rule_id="public_editorial_quality.semantic_review",
        repair_target=item["repair_target"],
        entity_id=item["public_item_id"],
        evidence_ids=list(item["evidence_ids"]),
    )
    plan = _build_regeneration_plan(
        issues=[issue], artifacts=artifacts, broad_retry_available=True
    )

    assert plan.mode == "targeted"
    assert plan.targets[0].allowed_paths == [
        "insights_final[item=fact-1].metric_public_copy"
    ]


def test_rendered_verified_metric_uses_natural_copy(tmp_path: Path) -> None:
    artifacts = _artifacts_with_metric_copy()
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "Metric copy report",
                "publisher": "MarketLense",
                "artifacts": artifacts,
            },
            doc_name="metric-copy.pdf",
            file_id="metric-copy",
            out_dir=str(tmp_path),
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")
    assert "42% of surveyed buyers" in html
    assert "label=Adoption" not in html
    assert "value=42%" not in html


def test_final_insight_prompt_declares_metric_copy_contract() -> None:
    system = Path(
        "src/prompts/report_vs/artifacts/insights_final/system.yaml"
    ).read_text(encoding="utf-8")
    user = Path("src/prompts/report_vs/artifacts/insights_final/user.yaml").read_text(
        encoding="utf-8"
    )
    assert "metric_public_copy" in system
    assert "metric_public_copy" in user


def test_metric_copy_repair_prompt_declares_exact_leaf_contract() -> None:
    repair_prompt = Path(
        "src/prompts/report_vs/artifacts/regenerate/insights_final/user.yaml"
    ).read_text(encoding="utf-8")

    assert "exact allowed path is `metric_public_copy`" in repair_prompt
    assert "label=` or `value=`" in repair_prompt
