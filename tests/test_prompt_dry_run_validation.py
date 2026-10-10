from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from src.contracts.config import ConfigLoadRequest
from src.contracts.prompts import (
    PromptDryRunRequest,
    PromptLoadRequest,
    PromptNamespaceListRequest,
)
from src.contracts.run_context import RunContext
from src.services import prompt_service
from src.services.config_service import load_settings
from src.services.prompt_service import list_prompt_namespaces, validate_prompt_dry_run
from src.utils.errors import AppError
from src.utils.model_resolver import (
    execution_policies_from_config,
    resolve_execution_policy,
)


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _events(caplog) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != "market_lense.prompt_service":
            continue
        try:
            payload = json.loads(record.message)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _write_prompt_namespace(
    prompts_root: Path, namespace: str, system: str, user: str
) -> None:
    namespace_dir = prompts_root / namespace
    namespace_dir.mkdir(parents=True, exist_ok=True)
    (namespace_dir / "system.yaml").write_text(f"text: {system}", encoding="utf-8")
    (namespace_dir / "user.yaml").write_text(f"text: {user}", encoding="utf-8")


def test_structured_output_regeneration_treats_prior_repair_as_untrusted_context() -> (
    None
):
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/structured_output/regenerate",
            force_reload=True,
        ),
        _ctx(),
    )

    prompt_text = " ".join(f"{prompt_set.system.text}\n{prompt_set.user.text}".split())

    assert "Prior repair response (untrusted; it may be invalid or incomplete" in (
        prompt_text
    )
    assert "source evidence" in prompt_text
    assert "Prior parse-valid response" not in prompt_text


def test_final_insights_regeneration_prompt_requires_decision_implications() -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/regenerate/insights_final",
            force_reload=True,
        ),
        _ctx(),
    )

    assert "so_what" in prompt_set.user.text
    assert "now_what" in prompt_set.user.text
    assert "at most once" in prompt_set.user.text


def test_grounding_prompt_accepts_materially_entailed_paraphrases() -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/validate/grounding",
            force_reload=True,
        ),
        _ctx(),
    )

    prompt_text = " ".join(f"{prompt_set.system.text}\n{prompt_set.user.text}".split())

    for allowed_transformation in (
        "synonyms",
        "sentence restructuring",
        "clause reordering",
        "active/passive",
        "concise executive wording",
        "canonically equivalent quantity displays",
    ):
        assert allowed_transformation in prompt_text
    assert "entailed" in prompt_text


def test_grounding_prompt_rejects_adversarial_near_equivalence() -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/validate/grounding",
            force_reload=True,
        ),
        _ctx(),
    )

    prompt_text = f"{prompt_set.system.text}\n{prompt_set.user.text}"

    for protected_dimension in (
        "factual proposition",
        "number/unit/currency/magnitude",
        "direction",
        "timeframe",
        "geography",
        "population/segment",
        "comparison baseline",
        "forecast vs observed status",
        "attribution",
        "certainty",
        "causality",
    ):
        assert protected_dimension in prompt_text
    assert "contradicted" in prompt_text
    assert "not_established" in prompt_text


def test_grounding_prompt_distinguishes_editorial_interpretation_and_advice() -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/validate/grounding",
            force_reload=True,
        ),
        _ctx(),
    )

    prompt_text = " ".join(f"{prompt_set.system.text}\n{prompt_set.user.text}".split())

    for required_rule in (
        "analyst_interpretation",
        "prescriptive_recommendation",
        "Source silence alone is not a failure",
        "contradicts evidence",
        "falsely attributes an action",
        "MarketLense-authored",
    ):
        assert required_rule in prompt_text


def test_numeric_artifact_claims_require_direct_finding_or_quote_evidence() -> None:
    def load(namespace: str):
        return prompt_service.load_prompt_set(
            PromptLoadRequest(
                schema_version="1.0", namespace=namespace, force_reload=True
            ),
            _ctx(),
        )

    candidates = load("report_vs/artifacts/insights_candidates")
    final = load("report_vs/artifacts/insights_final")
    summary = load("report_vs/artifacts/summary")
    findings = load("report_vs/evidence_packs/findings")
    candidates_text = " ".join(candidates.user.text.split())
    final_text = " ".join(final.user.text.split())
    summary_text = " ".join(summary.user.text.split())
    findings_text = " ".join(findings.system.text.split())

    assert "A paraphrased finding alone is not numeric evidence" in candidates_text
    assert "Use a quote ID only if its exact text states" in candidates_text
    assert "value, subject, and period/status" in candidates_text
    assert "finding/quote ID and page" in final_text
    assert "do not expand scope" in final_text
    assert "direct quote candidate" in summary_text
    assert "Paraphrased finding text alone is insufficient" in summary_text
    assert "Each number in `text` must appear" in findings_text
    assert "paraphrase or a nearby unrelated value is insufficient" in findings_text


def test_summary_prompt_requires_both_tldrs_to_use_the_report_level_lead() -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/summary",
            force_reload=True,
        ),
        _ctx(),
    )
    prompt_text = " ".join(prompt_set.user.text.split()).lower()

    assert (
        "both tldrs must share the report's most material supported finding"
        in prompt_text
    )
    assert "prefer decision-useful body outcomes over broad context" in prompt_text
    assert "directly supported docmap point" in prompt_text
    assert "plan guides selection, not evidence" in prompt_text
    assert "abstain if unsupported" in prompt_text
    assert "strongest decision-useful supported finding" in prompt_text
    assert "even outside the priority-one theme" in prompt_text
    assert "priority order cannot exclude stronger evidence" in prompt_text
    assert "preserve exact comparisons" in prompt_text
    assert "findings omit a stronger body result" in prompt_text


def test_summary_fallback_keeps_docmap_only_claims_section_scoped() -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/summary",
            force_reload=True,
        ),
        _ctx(),
    )
    prompt_text = " ".join(prompt_set.user.text.split()).lower()

    assert "plan guides selection, not evidence" in prompt_text
    assert "directly supported docmap point" in prompt_text
    assert "abstain if unsupported" in prompt_text


@pytest.mark.parametrize(
    "namespace",
    [
        "report_vs/artifacts/summary",
        "report_vs/artifacts/expert_comment",
        "report_vs/artifacts/regenerate/summary",
        "report_vs/artifacts/regenerate/expert_comment",
    ],
)
def test_editorial_plan_is_selection_guidance_not_cross_section_evidence(
    namespace: str,
) -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=namespace, force_reload=True),
        _ctx(),
    )
    prompt_text = " ".join(
        f"{prompt_set.system.text} {prompt_set.user.text}".split()
    ).lower()

    if namespace == "report_vs/artifacts/summary":
        assert "plan guides selection, not evidence" in prompt_text
    elif namespace == "report_vs/artifacts/regenerate/summary":
        assert "selection guidance, not evidence" in prompt_text
        assert "section-scoped" in prompt_text
    elif namespace == "report_vs/artifacts/expert_comment":
        assert "cross-section links or report-wide centrality" in prompt_text
    else:
        assert "use the plan to select, not prove" in prompt_text
        assert "unsupported cross-section links or centrality" in prompt_text


def test_docmap_retains_specific_mechanisms_and_contrasts() -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/doc_map",
            force_reload=True,
        ),
        _ctx(),
    )
    prompt_text = " ".join(prompt_set.user.text.split()).lower()

    assert (
        "preserve exact metrics, periods, causes, mechanisms, and contrasts"
        in prompt_text
    )
    assert "in `key_points`" in prompt_text
    assert (
        "state its strongest source result in `key_points`, not just its theme"
        in prompt_text
    )
    assert "final body page before the next heading" in prompt_text
    assert "full page span, not only the opener" in prompt_text
    assert "all explicit printed pages" in prompt_text


def test_insight_candidate_prompt_balances_plan_and_specificity() -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/insights_candidates",
            force_reload=True,
        ),
        _ctx(),
    )
    prompt_text = " ".join(prompt_set.user.text.split()).lower()

    assert "use the plan for coherence" in prompt_text
    assert "rank specific, decision-useful commercial results" in prompt_text
    assert "above sample details or section descriptions" in prompt_text
    assert "preserve exact values and comparisons" in prompt_text


def test_editorial_prompts_preserve_specific_measured_findings() -> None:
    def load(namespace: str):
        return prompt_service.load_prompt_set(
            PromptLoadRequest(
                schema_version="1.0", namespace=namespace, force_reload=True
            ),
            _ctx(),
        )

    doc_map_text = " ".join(load("report_vs/doc_map").user.text.split()).lower()
    findings_text = " ".join(
        load("report_vs/evidence_packs/findings").user.text.split()
    ).lower()
    candidates_text = " ".join(
        load("report_vs/artifacts/insights_candidates").user.text.split()
    ).lower()
    final_text = " ".join(
        load("report_vs/artifacts/insights_final").user.text.split()
    ).lower()
    summary_text = " ".join(
        load("report_vs/artifacts/summary").user.text.split()
    ).lower()

    assert (
        "state its strongest source result in `key_points`, not just its theme"
        in doc_map_text
    )
    assert (
        "search file_search by section/title/page and exact key-point metric"
        in findings_text
    )
    assert "exhaust body searches before summary-only findings" in findings_text
    assert "docmap/temporal pairs are clues, not evidence" in findings_text
    assert "keep chart values exact" in findings_text
    assert "state a share only when the source names its base" in findings_text
    assert "keep each value's role" in candidates_text
    assert (
        "from key points and comparisons, including nonnumeric relationships"
        in candidates_text
    )
    assert "keep its wording and date range exact" in summary_text
    assert "preserve exact values and comparisons" in candidates_text
    assert "preserve candidates' exact values, comparisons" in final_text
    assert "rank by candidate score and decision relevance first" in final_text
    assert "use plan priority for coherence or ties" in final_text
    assert "most specific, commercially useful insight first" in final_text


@pytest.mark.parametrize(
    "namespace",
    [
        "report_vs/artifacts/regenerate/insights_final",
        "report_vs/artifacts/regenerate/summary",
    ],
)
def test_regeneration_prompts_require_exact_retained_evidence_bindings(
    namespace: str,
) -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=namespace, force_reload=True),
        _ctx(),
    )

    if namespace == "report_vs/artifacts/regenerate/insights_final":
        assert "exact canonical source page(s)" in prompt_set.user.text
    else:
        assert "exact page" in prompt_set.user.text
    assert "empty" in prompt_set.user.text
    assert "numeric value" in prompt_set.user.text


def test_insight_rebinding_prompt_requires_direct_source_evidence() -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/regenerate/insights_final",
            force_reload=True,
        ),
        _ctx(),
    )

    assert "grounding_package.relevant_evidence" in prompt_set.user.text
    assert "direct finding or quote ID" in prompt_set.user.text
    assert "Never use a DocMap section ID" in prompt_set.user.text


@pytest.mark.parametrize(
    "namespace",
    [
        "report_vs/evidence_packs/findings",
        "report_vs/artifacts/insights_candidates",
        "report_vs/artifacts/insights_final",
        "report_vs/artifacts/summary",
        "report_vs/artifacts/expert_comment",
        "report_vs/artifacts/linkedin_post",
        "report_vs/artifacts/regenerate/insights_candidates",
        "report_vs/artifacts/regenerate/insights_final",
        "report_vs/artifacts/regenerate/summary",
        "report_vs/artifacts/regenerate/expert_comment",
        "report_vs/artifacts/regenerate/linkedin_post",
    ],
)
def test_editorial_prompts_require_distinct_temporal_qualifiers(namespace: str) -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=namespace, force_reload=True),
        _ctx(),
    )

    assert "distinct temporal qualifiers" in (
        f"{prompt_set.system.text}\n{prompt_set.user.text}"
    )


@pytest.mark.parametrize(
    ("namespace", "scope"),
    [
        ("report_vs/artifacts/linkedin_post", "Broad report scope"),
        ("report_vs/artifacts/regenerate/linkedin_post", "Narrow report scope"),
    ],
)
def test_linkedin_prompt_materializes_editorial_plan_and_report_scope(
    namespace: str, scope: str
) -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=namespace, force_reload=True),
        _ctx(),
    )
    variables = {
        "editorial_plan_json": '{"report_thesis":"Retention is the angle."}',
        "doc_map_json": json.dumps({"scope": scope, "publisher": "Source Co."}),
        "report_identity_json": json.dumps({"scope": scope, "publisher": "Source Co."}),
        "summary_json": '{"executive_summary":"Secondary context."}',
        "insights_final_json": '[{"text":"Supporting insight."}]',
        "metric_spine_json": "[]",
        "attempt_index": 1,
        "target_section": "linkedin_post",
        "current_section_text": "Current post.",
        "claim_repair_scope_json": '{"mode":"family"}',
        "repair_context_json": "{}",
        "prior_repair_memory_json": "[]",
        "failure_reasons_json": "[]",
        "fix_checklist_json": "[]",
        "grounding_package_json": "{}",
    }

    rendered = prompt_service.render_prompt(
        prompt_service.PromptRenderRequest(
            schema_version="1.0", template=prompt_set.user, variables=variables
        ),
        _ctx(),
    )

    assert "Retention is the angle." in rendered.text
    assert scope in rendered.text
    assert "Secondary context." not in rendered.text
    assert "180–280 words" in rendered.text
    assert "no more than four quantitative proof points" in rendered.text
    assert (
        "Select the four or fewer quantitative proof points before drafting"
        in rendered.text
    )
    assert "no more than four distinct numerical values" in rendered.text
    assert "Do not use bullets" in rendered.text
    assert "The evidence points to" in rendered.text
    assert "interpretive bridge sentences" in rendered.text


def test_linkedin_regeneration_prompt_separates_claim_scope_from_full_post_rules() -> (
    None
):
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/regenerate/linkedin_post",
            force_reload=True,
        ),
        _ctx(),
    )

    assert "Do not apply the full-post word" in prompt_set.user.text
    assert "hashtag rules in claim mode" in prompt_set.user.text


@pytest.mark.parametrize(
    "namespace",
    [
        "report_vs/artifacts/linkedin_post",
        "report_vs/artifacts/regenerate/linkedin_post",
    ],
)
def test_linkedin_prompts_require_plain_text_paragraphs_without_markdown_or_bullets(
    namespace: str,
) -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=namespace, force_reload=True),
        _ctx(),
    )

    prompt_text = f"{prompt_set.system.text}\n{prompt_set.user.text}"

    assert "Do not use bullets" in prompt_text
    assert "Markdown formatting" in prompt_text
    assert "plain-text short paragraphs separated by blank lines" in prompt_text
    assert "two newline characters" in prompt_text
    assert "shorter is fine" in prompt_text
    assert "Do not return fewer than 180 words" not in prompt_text
    assert "optional bullets" not in prompt_text


def test_validate_prompt_dry_run_repository_covers_all_discovered_namespaces(
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.prompt_service")
    response = validate_prompt_dry_run(
        PromptDryRunRequest(schema_version="1.0", reload_if_changed=True),
        _ctx(),
    )
    namespace_response = list_prompt_namespaces(
        PromptNamespaceListRequest(schema_version="1.0", reload_if_changed=True),
        _ctx(),
    )

    assert {item.namespace for item in response.results} == {
        item.namespace for item in namespace_response.namespaces
    }
    assert {"report", "validation", "ranking", "browser_download", "publishing"} <= {
        item.family for item in response.results
    }
    events = _events(caplog)
    namespace_events = [
        item
        for item in events
        if item.get("event") == "prompt_dry_run_namespace_validated"
    ]
    assert len(namespace_events) == len(response.results)
    assert_logs_have_required_fields(events)


def test_prompt_dry_run_uses_the_runtime_execution_policy() -> None:
    response = validate_prompt_dry_run(
        PromptDryRunRequest(
            schema_version="1.0", namespaces=["report_vs/artifacts/summary"]
        ),
        _ctx(),
    )
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), _ctx())
    expected = resolve_execution_policy(
        "report_vs/artifacts/summary",
        execution_policies_from_config(
            settings.llm_execution_policies,
            model_overrides=settings.openai_models,
            legacy_routing=settings.llm_routing,
            default_model=settings.openai_model,
            default_temperature=settings.temperature,
            default_seed=settings.openai_seed,
            default_timeout_seconds=settings.openai_timeout_seconds,
        ),
        default_model=settings.openai_model,
        default_temperature=settings.temperature,
        default_seed=settings.openai_seed,
        default_timeout_seconds=settings.openai_timeout_seconds,
    )

    result = response.results[0]
    assert result.model == expected.policy.model
    assert result.temperature == expected.policy.temperature
    assert result.reasoning_effort == expected.policy.reasoning_effort
    assert result.execution_policy_hash == expected.policy_hash


def test_linkedin_publication_copy_uses_the_configured_execution_policy() -> None:
    response = validate_prompt_dry_run(
        PromptDryRunRequest(
            schema_version="1.0", namespaces=["report_vs/artifacts/linkedin_post"]
        ),
        _ctx(),
    )

    result = response.results[0]
    assert result.temperature is None
    assert result.reasoning_effort == "medium"


def test_validate_prompt_dry_run_rejects_missing_fixture(
    tmp_path: Path,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    prompts_root = tmp_path / "prompts"
    _write_prompt_namespace(prompts_root, "alpha", "system-a", "user-a")
    fixture_path = prompts_root / "_dry_run_fixtures.yaml"
    fixture_path.write_text(
        'schema_version: "1.0"\nfixtures: []\n',
        encoding="utf-8",
    )

    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)
    external_boundary_mocks_only.setattr(
        prompt_service,
        "PROMPT_DRY_RUN_FIXTURE_PATH",
        fixture_path,
    )

    with pytest.raises(AppError) as err:
        validate_prompt_dry_run(
            PromptDryRunRequest(schema_version="1.0", reload_if_changed=True),
            _ctx(),
        )

    assert_app_error(
        err.value,
        code="prompt_dry_run_fixture_registry_invalid",
        retryable=False,
    )


def test_validate_prompt_dry_run_surfaces_missing_variable(
    tmp_path: Path,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    prompts_root = tmp_path / "prompts"
    _write_prompt_namespace(
        prompts_root,
        "alpha",
        "system-a",
        "hello {{ required_name }}",
    )
    fixture_path = prompts_root / "_dry_run_fixtures.yaml"
    fixture_path.write_text(
        "\n".join(
            [
                'schema_version: "1.0"',
                "fixtures:",
                '  - namespace: "alpha"',
                '    family: "report"',
                "    test_only_execution_override: true",
                "    system_variables: {}",
                "    user_variables: {}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)
    external_boundary_mocks_only.setattr(
        prompt_service,
        "PROMPT_DRY_RUN_FIXTURE_PATH",
        fixture_path,
    )

    with pytest.raises(AppError) as err:
        validate_prompt_dry_run(
            PromptDryRunRequest(schema_version="1.0", reload_if_changed=True),
            _ctx(),
        )

    assert_app_error(
        err.value,
        code="prompt_render_missing_variable",
        retryable=False,
    )


def test_prompt_service_composes_shared_include_and_schema_snippet(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    prompts_root = tmp_path / "prompts"
    schemas_root = tmp_path / "schemas"
    (prompts_root / "_partials").mkdir(parents=True)
    schemas_root.mkdir(parents=True)
    (prompts_root / "_partials" / "evidence.yaml").write_text(
        "text: |\n  Shared evidence rule.\n",
        encoding="utf-8",
    )
    namespace_dir = prompts_root / "alpha"
    namespace_dir.mkdir(parents=True)
    (namespace_dir / "system.yaml").write_text(
        "\n".join(
            [
                "includes:",
                '  - "_partials/evidence.yaml"',
                "schema_snippets:",
                "  artifact_schema:",
                '    schema: "artifact.schema.json"',
                '    pointer: "/properties/summary"',
                "text: |",
                "  Local instruction.",
                "  {{ artifact_schema }}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (namespace_dir / "user.yaml").write_text("text: User prompt.\n", encoding="utf-8")
    (schemas_root / "artifact.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "object",
                        "required": ["tldr", "claim_evidence_map"],
                        "properties": {
                            "tldr": {"type": "string", "minLength": 1},
                            "claim_evidence_map": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "required": ["claim", "evidence_id"],
                                    "properties": {
                                        "claim": {"type": "string"},
                                        "evidence_id": {"type": "string"},
                                    },
                                },
                            },
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)
    external_boundary_mocks_only.setattr(prompt_service, "SCHEMAS_ROOT", schemas_root)

    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace="alpha", force_reload=True),
        _ctx(),
    )
    rendered = prompt_service.render_prompt(
        prompt_service.PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.system,
            variables={},
        ),
        _ctx(),
    )

    assert prompt_set.system.include_paths == [
        str((prompts_root / "_partials" / "evidence.yaml").resolve())
    ]
    assert "Shared evidence rule." in rendered.text
    assert "Local instruction." in rendered.text
    assert "Schema source: artifact.schema.json#/properties/summary" in rendered.text
    assert "- tldr: string, required, minLength=1" in rendered.text
    assert "- claim_evidence_map: array, required, minItems=1" in rendered.text
    assert "claim: string, required" in rendered.text
