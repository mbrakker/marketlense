# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_build_cross_report_publish_package_contains_traceable_html_and_metadata(
    tmp_path,
    run_context,
) -> None:
    generated = _generated_result(tmp_path, run_context)
    generated = replace(
        generated,
        sections=[
            replace(
                generated.sections[0],
                body=(
                    "The board should treat ev-report-a-claim-1 as directional "
                    "evidence, not as a public citation token."
                ),
            ),
            *generated.sections[1:],
        ],
    )
    _, _, agreement_result = _analysis_inputs()
    validation = validate_cross_report_generated_analysis(generated, run_context)

    package = build_cross_report_publish_package(
        generated,
        validation,
        agreement_result,
        run_context,
        artifact_path="out/cross_report_analysis/ai-commerce/analysis.json",
        html_path="out/cross_report_analysis/ai-commerce/publish.html",
        publish_requires_validation_pass=True,
    )

    assert package.package_id == "cross-report:analysis-ai-commerce"
    assert package.title == generated.title
    assert package.slug == generated.slug
    assert package.excerpt == generated.executive_summary
    assert package.canonical_artifact_path.endswith("analysis.json")
    assert package.html_path.endswith("publish.html")
    assert package.selected_report_ids == ["report-a", "report-b"]
    assert package.selected_theme_id == "theme-tag-ai"
    assert package.category_labels == ["Retail"]
    assert package.tag_labels == ["AI"]
    assert package.evidence_reference_ids == [
        "ev-report-a-claim-1",
        "ev-report-b-finding-1",
    ]
    assert package.raw_metric_ids == ["metric-a"]
    assert package.source_metadata[0]["report_id"] == "report-a"
    assert package.source_metadata[0]["source_url"] == "https://sources.example/report-a"
    assert "report-a title, page 1" in package.html_text
    assert "report-b title, page 1" in package.html_text
    assert "report-a title, page 4" in package.html_text
    assert "The board should treat report-a title, page 1 as directional" in package.html_text
    assert "The board should treat ev-report-a-claim-1 as directional" not in package.html_text
    assert "<code>ev-report-a-claim-1</code>" not in package.html_text
    assert "<code>metric-a</code>" not in package.html_text
    assert 'class="ml-ingest-report-content"' in package.html_text
    assert 'class="page-shell"' in package.html_text
    assert 'class="sticky-nav"' in package.html_text
    assert 'href="#section-summary"' in package.html_text
    assert 'href="#section-insights"' in package.html_text
    assert 'href="#section-evidence"' in package.html_text
    assert 'data-tone="summary"' in package.html_text
    assert 'class="insight-card"' in package.html_text
    assert "Executive synthesis" in package.html_text
    assert "Strategic read-through" in package.html_text
    assert "Consulting-style source appendix" in package.html_text
    assert "Source report map" in package.html_text
    assert "Evidence references" in package.html_text
    assert "Raw metric appendix" in package.html_text
    assert "Uncertainty and divergence notes" in package.html_text
    assert "data-market-lense-cross-report-metadata" in package.html_text
    assert 'data-market-lense-publish-entity="true"' in package.html_text
    assert '"entity_type":"briefing"' in package.html_text
    assert '"canonical_route_intent":"wordpress:ml_briefing"' in package.html_text
    assert "Drive fileId: cross-report:analysis-ai-commerce" in package.html_text
    assert "normalized average" not in package.html_text.casefold()
    assert "average across publishers" not in package.html_text.casefold()

def test_build_cross_report_publish_package_blocks_failed_validation(
    tmp_path,
    run_context,
    assert_app_error,
) -> None:
    generated = _generated_result(tmp_path, run_context)
    _, _, agreement_result = _analysis_inputs()
    failed_validation = replace(
        validate_cross_report_generated_analysis(generated, run_context),
        status="fail",
        passed=False,
        issues=["section_missing_evidence:summary"],
    )

    with pytest.raises(Exception) as exc:
        build_cross_report_publish_package(
            generated,
            failed_validation,
            agreement_result,
            run_context,
            artifact_path="out/cross_report_analysis/ai-commerce/analysis.json",
            html_path="out/cross_report_analysis/ai-commerce/publish.html",
            publish_requires_validation_pass=True,
        )

    assert_app_error(
        exc.value,
        code="cross_report_publish_validation_failed",
        retryable=False,
        severity="error",
    )

__all__ = [
    "test_build_cross_report_publish_package_contains_traceable_html_and_metadata",
    "test_build_cross_report_publish_package_blocks_failed_validation",
]
