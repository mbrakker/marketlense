from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.contracts.categories import (
    CategoryClassificationConfig,
    CategoryDefinition,
    CategoryMappingLoadRequest,
    CategoryMappingLoadResponse,
    CategoryMappings,
)
from src.contracts.run_context import RunContext
from src.contracts.taxonomy import TaxonomyExtractResponse, TaxonomyTagEvidence
from src.generators.categorize_generator import categorize_taxonomy
from src.services.category_mapping_service import load_mappings
from src.utils.errors import AppError
from src.utils.tag_utils import normalize_slug_tag


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="run", task_id="task", span_id="span")


def _slug(value: str) -> str:
    return normalize_slug_tag(value)


def _mappings(categories: list[CategoryDefinition]) -> CategoryMappingLoadResponse:
    return CategoryMappingLoadResponse(
        schema_version="1.1",
        mappings=CategoryMappings(
            schema_version="1.1",
            categories=categories,
            classification=CategoryClassificationConfig(
                schema_version="1.1",
                max_categories=2,
                min_primary_score=2.2,
                min_secondary_score=1.6,
                secondary_score_ratio=0.72,
                secondary_rescue_score_ratio=0.55,
                secondary_rescue_min_strong_matches=2,
                secondary_rescue_min_evidence_tags=2,
                secondary_rescue_min_evidence_sections=2,
                core_tag_weight=2.2,
                supporting_tag_weight=1.2,
                legacy_tag_weight=1.0,
                generic_tag_weight=0.3,
                negative_tag_weight=-2.0,
                repeated_match_bonus=0.25,
                global_generic_tags=[
                    "digital_economy",
                    "innovation",
                    "social_media",
                    "forecasts",
                ],
            ),
            uncategorized=[],
        ),
    )


def test_categorize_taxonomy_prefers_specific_domain_over_generic_overlap() -> None:
    mappings = _mappings(
        [
            CategoryDefinition(
                id="macroeconomics",
                label="Macroeconomics",
                description="Macro",
                core_tags=[
                    "macroeconomic_outlook",
                    "gdp_growth",
                    "interest_rates",
                ],
                supporting_tags=["country_analysis"],
                generic_tags=["digital_economy", "risk_assessment"],
            ),
            CategoryDefinition(
                id="technology",
                label="Technology",
                description="Tech",
                core_tags=["ai_infrastructure", "cloud_infrastructure"],
                generic_tags=["innovation", "emerging_tech", "digital_economy"],
            ),
            CategoryDefinition(
                id="measurement",
                label="Measurement",
                description="Measurement",
                core_tags=["attribution", "roas"],
                generic_tags=["forecasts"],
            ),
        ]
    )

    assignment = categorize_taxonomy(
        [
            "macroeconomic_outlook",
            "gdp_growth",
            "interest_rates",
            "innovation",
            "digital_economy",
            "forecasts",
        ],
        mappings,
        _ctx(),
    )

    assert assignment.categories == ["macroeconomics"]
    assert assignment.category_labels == ["Macroeconomics"]
    assert assignment.unmapped_tags == []
    assert assignment.score_details[0].category_id == "macroeconomics"
    assert assignment.score_details[0].eligible is True
    tech_detail = next(
        detail for detail in assignment.score_details if detail.category_id == "technology"
    )
    assert tech_detail.eligible is False
    assert tech_detail.skip_reason == "generic_only_matches"


def test_categorize_taxonomy_returns_secondary_category_only_when_it_is_strong() -> None:
    mappings = _mappings(
        [
            CategoryDefinition(
                id="social_commerce",
                label="Social Commerce",
                description="Social commerce",
                core_tags=[
                    "social_commerce",
                    "creator_commerce",
                    "live_shopping",
                    "in_app_checkout",
                ],
                generic_tags=["creator_economy"],
            ),
            CategoryDefinition(
                id="social_video_creator",
                label="Social Video",
                description="Social video",
                core_tags=[
                    "short_form_video",
                    "creator_marketing",
                    "user_generated_content",
                ],
                supporting_tags=["tiktok", "vertical_video"],
            ),
        ]
    )

    assignment = categorize_taxonomy(
        [
            "social_commerce",
            "creator_commerce",
            "live_shopping",
            "in_app_checkout",
            "short_form_video",
            "creator_marketing",
            "user_generated_content",
        ],
        mappings,
        _ctx(),
    )

    assert assignment.categories == ["social_commerce", "social_video_creator"]
    assert assignment.category_labels == ["Social Commerce", "Social Video"]


def test_categorize_taxonomy_skips_generic_only_matches() -> None:
    mappings = _mappings(
        [
            CategoryDefinition(
                id="consumer_behavior",
                label="Consumer Behavior",
                description="Consumer behavior",
                core_tags=["consumer_behavior"],
                generic_tags=["consumer_trends", "social_media"],
            )
        ]
    )

    assignment = categorize_taxonomy(
        ["consumer_trends", "social_media"],
        mappings,
        _ctx(),
    )

    assert assignment.categories == []
    assert assignment.unmapped_tags == []
    assert assignment.score_details[0].category_id == "consumer_behavior"
    assert assignment.score_details[0].eligible is False
    assert assignment.score_details[0].skip_reason == "generic_only_matches"


def test_categorize_taxonomy_ignores_descriptor_tags_without_marking_unmapped() -> None:
    mappings = _mappings(
        [
            CategoryDefinition(
                id="consumer_behavior",
                label="Consumer Behavior",
                description="Consumer behavior",
                core_tags=["consumer_behavior"],
                descriptor_tags=["consumer_trends", "social_media"],
            )
        ]
    )

    assignment = categorize_taxonomy(
        ["consumer_trends", "social_media"],
        mappings,
        _ctx(),
    )

    assert assignment.categories == []
    assert assignment.unmapped_tags == []
    assert assignment.score_details[0].category_id == "consumer_behavior"
    assert assignment.score_details[0].score == 0.0
    assert assignment.score_details[0].eligible is False
    assert assignment.score_details[0].skip_reason == "non_positive_score"


def test_categorize_taxonomy_rescues_evidence_backed_secondary_category() -> None:
    mappings = _mappings(
        [
            CategoryDefinition(
                id="business_performance",
                label="Business Performance",
                description="Business performance",
                core_tags=["brand_growth", "market_share", "pricing_power"],
            ),
            CategoryDefinition(
                id="consumer_behavior",
                label="Consumer Behavior",
                description="Consumer behavior",
                supporting_tags=[
                    "consumer_behavior",
                    "shopper_behavior",
                    "consumer_sentiment",
                ],
                secondary_supporting_tags=[
                    "consumer_behavior",
                    "shopper_behavior",
                    "consumer_sentiment",
                ],
                must_have_one_of=["consumer_behavior", "shopper_behavior"],
            ),
        ]
    )

    assignment = categorize_taxonomy(
        TaxonomyExtractResponse(
            schema_version="1.0",
            taxonomy=[
                "brand_growth",
                "market_share",
                "pricing_power",
                "consumer_behavior",
                "shopper_behavior",
                "consumer_sentiment",
            ],
            primary_tags=["brand_growth", "market_share", "pricing_power"],
            secondary_tags=[
                "consumer_behavior",
                "shopper_behavior",
                "consumer_sentiment",
            ],
            tag_evidence=[
                TaxonomyTagEvidence(
                    tag="consumer_behavior",
                    tier="secondary",
                    section_label="Executive Summary",
                    evidence="Consumers are trading attention across channels.",
                ),
                TaxonomyTagEvidence(
                    tag="shopper_behavior",
                    tier="secondary",
                    section_label="Consumer Trends",
                    evidence="Shoppers are splitting spend across formats.",
                ),
                TaxonomyTagEvidence(
                    tag="consumer_sentiment",
                    tier="secondary",
                    section_label="Consumer Trends",
                    evidence="Sentiment remains cautious despite higher intent.",
                ),
            ],
            region="Global",
            time_period="2026",
            not_found_reason=None,
        ),
        mappings,
        _ctx(),
    )

    assert assignment.categories == ["business_performance", "consumer_behavior"]
    consumer_detail = next(
        detail
        for detail in assignment.score_details
        if detail.category_id == "consumer_behavior"
    )
    assert consumer_detail.secondary_rescue_eligible is True
    assert consumer_detail.evidence_tag_count == 3
    assert consumer_detail.evidence_section_count == 2
    assert consumer_detail.secondary_tier_match_count == 3
    assert consumer_detail.must_have_match_count == 2


def test_categorize_taxonomy_rejects_secondary_without_enough_evidence_sections() -> None:
    mappings = _mappings(
        [
            CategoryDefinition(
                id="business_performance",
                label="Business Performance",
                description="Business performance",
                core_tags=["brand_growth", "market_share", "pricing_power"],
            ),
            CategoryDefinition(
                id="consumer_behavior",
                label="Consumer Behavior",
                description="Consumer behavior",
                supporting_tags=[
                    "consumer_behavior",
                    "shopper_behavior",
                    "consumer_sentiment",
                ],
                secondary_supporting_tags=[
                    "consumer_behavior",
                    "shopper_behavior",
                    "consumer_sentiment",
                ],
                must_have_one_of=["consumer_behavior", "shopper_behavior"],
            ),
        ]
    )

    assignment = categorize_taxonomy(
        TaxonomyExtractResponse(
            schema_version="1.0",
            taxonomy=[
                "brand_growth",
                "market_share",
                "pricing_power",
                "consumer_behavior",
                "shopper_behavior",
                "consumer_sentiment",
            ],
            primary_tags=["brand_growth", "market_share", "pricing_power"],
            secondary_tags=[
                "consumer_behavior",
                "shopper_behavior",
                "consumer_sentiment",
            ],
            tag_evidence=[
                TaxonomyTagEvidence(
                    tag="consumer_behavior",
                    tier="secondary",
                    section_label="Executive Summary",
                    evidence="Consumers are trading attention across channels.",
                ),
                TaxonomyTagEvidence(
                    tag="shopper_behavior",
                    tier="secondary",
                    section_label="Executive Summary",
                    evidence="Shoppers are splitting spend across formats.",
                ),
            ],
            region="Global",
            time_period="2026",
            not_found_reason=None,
        ),
        mappings,
        _ctx(),
    )

    assert assignment.categories == ["business_performance"]
    consumer_detail = next(
        detail
        for detail in assignment.score_details
        if detail.category_id == "consumer_behavior"
    )
    assert consumer_detail.secondary_rescue_eligible is False
    assert consumer_detail.evidence_tag_count == 2
    assert consumer_detail.evidence_section_count == 1


def test_category_mapping_service_loads_weighted_schema(tmp_path: Path) -> None:
    mapping_path = tmp_path / "category-mappings.yaml"
    mapping_path.write_text(
        "\n".join(
            [
                "schema_version: '1.1'",
                "classification:",
                "  schema_version: '1.1'",
                "  max_categories: 1",
                "  min_primary_score: 3.0",
                "  secondary_rescue_score_ratio: 0.6",
                "  secondary_rescue_min_strong_matches: 3",
                "  secondary_rescue_min_evidence_tags: 2",
                "  secondary_rescue_min_evidence_sections: 2",
                "  global_generic_tags:",
                "    - digital_economy",
                "categories:",
                "  - id: macroeconomics",
                "    label: Macroeconomics",
                "    description: Macro category",
                "    definition: Reports mainly about macroeconomic conditions and public-market outlooks.",
                "    include_when:",
                "      - Repeated evidence focuses on inflation, rates, GDP, or national outlooks.",
                "    exclude_when:",
                "      - Reject when macro context is only background for an industry report.",
                "    core_tags:",
                "      - macroeconomic_outlook",
                "    supporting_tags:",
                "      - country_analysis",
                "    secondary_supporting_tags:",
                "      - interest_rates",
                "    descriptor_tags:",
                "      - country_forecasts",
                "    generic_tags:",
                "      - digital_economy",
                "    negative_tags:",
                "      - social_media",
                "    must_have_one_of:",
                "      - macroeconomic_outlook",
                "    priority: 5",
                "inference_rules:",
                "  - name: macro_to_growth",
                "    target_category_id: business_performance",
                "    trigger_tags:",
                "      - macroeconomic_outlook",
                "    inferred_tag: business_performance",
                "    inferred_tier: secondary",
                "    context_keywords_any:",
                "      - growth",
                "    remove_tags:",
                "      - digital_economy",
                "uncategorized: []",
                "",
            ]
        ),
        encoding="utf-8",
    )

    response = load_mappings(
        CategoryMappingLoadRequest(
            schema_version="1.0",
            path=str(mapping_path),
            reload_if_changed=True,
            force_reload=True,
        ),
        _ctx(),
    )

    assert response.mappings.classification.max_categories == 1
    assert response.mappings.classification.min_primary_score == 3.0
    assert response.mappings.classification.secondary_rescue_score_ratio == 0.6
    assert response.mappings.classification.secondary_rescue_min_strong_matches == 3
    assert response.mappings.classification.secondary_rescue_min_evidence_tags == 2
    assert response.mappings.classification.secondary_rescue_min_evidence_sections == 2
    assert response.mappings.classification.global_generic_tags == ["digital_economy"]
    assert response.mappings.categories[0].core_tags == ["macroeconomic_outlook"]
    assert response.mappings.categories[0].supporting_tags == ["country_analysis"]
    assert response.mappings.categories[0].secondary_supporting_tags == ["interest_rates"]
    assert response.mappings.categories[0].descriptor_tags == ["country_forecasts"]
    assert response.mappings.categories[0].generic_tags == ["digital_economy"]
    assert response.mappings.categories[0].negative_tags == ["social_media"]
    assert response.mappings.categories[0].must_have_one_of == ["macroeconomic_outlook"]
    assert response.mappings.categories[0].priority == 5
    assert len(response.mappings.inference_rules) == 1
    assert response.mappings.inference_rules[0].name == "macro_to_growth"
    assert response.mappings.inference_rules[0].target_category_id == "business_performance"
    assert response.mappings.inference_rules[0].trigger_tags == ["macroeconomic_outlook"]
    assert response.mappings.inference_rules[0].inferred_tag == "business_performance"
    assert response.mappings.inference_rules[0].context_keywords_any == ["growth"]
    assert response.mappings.inference_rules[0].remove_tags == ["digital_economy"]


def test_repo_category_mapping_config_is_normalized() -> None:
    mapping_path = Path(__file__).resolve().parents[1] / "src" / "config" / "category-mappings.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    categories = payload.get("categories") or []
    inference_rules = payload.get("inference_rules") or []

    legacy_categories = [
        str(item.get("id"))
        for item in categories
        if isinstance(item, dict) and "tags" in item
    ]
    assert legacy_categories == []

    missing_positive_groups = [
        str(item.get("id"))
        for item in categories
        if isinstance(item, dict)
        and not (
            item.get("core_tags")
            or item.get("supporting_tags")
            or item.get("generic_tags")
        )
    ]
    assert missing_positive_groups == []

    incomplete_inference_rules = [
        str(item.get("name"))
        for item in inference_rules
        if isinstance(item, dict)
        and not (
            str(item.get("name") or "").strip()
            and str(item.get("target_category_id") or "").strip()
            and (item.get("trigger_tags") or [])
            and str(item.get("inferred_tag") or "").strip()
        )
    ]
    assert incomplete_inference_rules == []


def test_repo_category_mapping_context_profiles_are_complete() -> None:
    mapping_path = Path(__file__).resolve().parents[1] / "src" / "config" / "category-mappings.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))

    incomplete_profiles: list[str] = []
    for item in payload.get("categories") or []:
        if not isinstance(item, dict) or not item.get("portal_exposed", True):
            continue
        category_id = str(item.get("id") or "<missing-id>")
        if not str(item.get("description") or "").strip():
            incomplete_profiles.append(f"{category_id}.description")
        if not str(item.get("definition") or "").strip():
            incomplete_profiles.append(f"{category_id}.definition")
        if not (item.get("include_when") or []):
            incomplete_profiles.append(f"{category_id}.include_when")
        if not (item.get("exclude_when") or []):
            incomplete_profiles.append(f"{category_id}.exclude_when")

    assert incomplete_profiles == []


def test_load_mappings_rejects_portal_category_without_context_profile(
    tmp_path: Path,
    assert_app_error,
) -> None:
    mapping_path = tmp_path / "category-mappings.yaml"
    mapping_path.write_text(
        "\n".join(
            [
                "schema_version: '1.2'",
                "categories:",
                "  - id: technology",
                "    label: Technology",
                "    description: Technology reports.",
                "    core_tags:",
                "      - technology",
                "uncategorized: []",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(AppError) as exc_info:
        load_mappings(
            CategoryMappingLoadRequest(
                schema_version="1.0",
                path=str(mapping_path),
                reload_if_changed=True,
                force_reload=True,
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="category_mapping_context_profile_incomplete",
        retryable=False,
        severity="error",
    )
    assert exc_info.value.context["incomplete_fields"] == [
        "technology.include_when",
        "technology.exclude_when",
    ]


def test_repo_category_mapping_rule_and_coverage_tags_are_scored() -> None:
    mapping_path = Path(__file__).resolve().parents[1] / "src" / "config" / "category-mappings.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    categories = payload.get("categories") or []
    inference_rules = payload.get("inference_rules") or []
    classification = payload.get("classification") or {}

    scoring_tags_by_category: dict[str, set[str]] = {}
    all_scoring_tags: set[str] = set()
    all_supported_tags: set[str] = set(classification.get("global_generic_tags") or [])
    for item in categories:
        if not isinstance(item, dict):
            continue
        category_id = str(item.get("id") or "")
        scoring_tags = set(item.get("core_tags") or [])
        scoring_tags.update(item.get("supporting_tags") or [])
        scoring_tags.update(item.get("secondary_supporting_tags") or [])
        scoring_tags_by_category[category_id] = scoring_tags
        all_scoring_tags.update(scoring_tags)
        all_supported_tags.update(item.get("descriptor_tags") or [])
        all_supported_tags.update(item.get("generic_tags") or [])
        all_supported_tags.update(scoring_tags)

    missing_rule_trigger_coverage = [
        tag
        for rule in inference_rules
        if isinstance(rule, dict)
        for tag in (rule.get("trigger_tags") or [])
        if tag not in all_supported_tags
    ]
    assert missing_rule_trigger_coverage == []

    category_ids = {
        str(item.get("id") or "")
        for item in categories
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    rules_by_target: dict[str, list[dict]] = {}
    for rule in inference_rules:
        if not isinstance(rule, dict):
            continue
        target = str(rule.get("target_category_id") or "").strip()
        rules_by_target.setdefault(target, []).append(rule)

    assert set(rules_by_target) == category_ids
    for target_category_id, rules in rules_by_target.items():
        scoring_tags = scoring_tags_by_category[target_category_id]
        assert rules
        for rule in rules:
            assert str(rule.get("inferred_tag") or "").strip() in scoring_tags

    assert "generative_ai_and_ai_agents" in scoring_tags_by_category["ai_automation"]
    assert "ai_and_productivity" in scoring_tags_by_category["ai_automation"]
    assert "generative_engine_optimisation_geo" in scoring_tags_by_category["search_performance"]
    assert "brand_safety_and_suitability" in scoring_tags_by_category["programmatic_ad_tech"]
    assert "emerging_tech" in scoring_tags_by_category["technology"]
    assert "tech_trends" in scoring_tags_by_category["technology"]
    assert "ai_in_retail" in scoring_tags_by_category["omnichannel_commerce"]


def test_repo_category_mapping_broad_descriptors_stay_non_scoring() -> None:
    mapping_path = Path(__file__).resolve().parents[1] / "src" / "config" / "category-mappings.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    categories = payload.get("categories") or []
    classification = payload.get("classification") or {}

    all_scoring_tags: set[str] = set()
    descriptor_or_generic_tags: set[str] = set(classification.get("global_generic_tags") or [])
    for item in categories:
        if not isinstance(item, dict):
            continue
        all_scoring_tags.update(item.get("core_tags") or [])
        all_scoring_tags.update(item.get("supporting_tags") or [])
        all_scoring_tags.update(item.get("secondary_supporting_tags") or [])
        descriptor_or_generic_tags.update(item.get("descriptor_tags") or [])
        descriptor_or_generic_tags.update(item.get("generic_tags") or [])

    broad_descriptor_tags = {
        "consumer_trends",
        "social_media",
        "digital_economy",
        "forecasts",
    }

    assert broad_descriptor_tags.issubset(descriptor_or_generic_tags)
    assert broad_descriptor_tags.isdisjoint(all_scoring_tags)


def test_repo_category_mapping_uses_slug_tags_only() -> None:
    mapping_path = Path(__file__).resolve().parents[1] / "src" / "config" / "category-mappings.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))

    non_slug_entries: list[str] = []
    for category in payload.get("categories") or []:
        if not isinstance(category, dict):
            continue
        category_id = str(category.get("id") or "")
        for field in (
            "tags",
            "core_tags",
            "supporting_tags",
            "secondary_supporting_tags",
            "descriptor_tags",
            "generic_tags",
            "negative_tags",
            "must_have_one_of",
        ):
            for value in category.get(field) or []:
                if str(value) != _slug(str(value)):
                    non_slug_entries.append(f"{category_id}.{field}:{value}")

    classification = payload.get("classification") or {}
    for value in classification.get("global_generic_tags") or []:
        if str(value) != _slug(str(value)):
            non_slug_entries.append(f"classification.global_generic_tags:{value}")

    for rule in payload.get("inference_rules") or []:
        if not isinstance(rule, dict):
            continue
        rule_name = str(rule.get("name") or "")
        for field in ("trigger_tags", "context_keywords_any", "remove_tags"):
            for value in rule.get(field) or []:
                if str(value) != _slug(str(value)):
                    non_slug_entries.append(f"{rule_name}.{field}:{value}")
        inferred_tag = str(rule.get("inferred_tag") or "")
        if inferred_tag != _slug(inferred_tag):
            non_slug_entries.append(f"{rule_name}.inferred_tag:{inferred_tag}")

    assert non_slug_entries == []
