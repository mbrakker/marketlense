from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import src.contracts.categories as category_contracts
import src.services.category_mapping_service as category_mapping_service
from src.contracts.categories import CategoryMappingLoadRequest
from src.contracts.run_context import RunContext
from src.services.category_mapping_service import load_mappings
from src.utils.errors import AppError
from src.utils.tag_utils import normalize_slug_tag


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run", task_id="task", span_id="span"
    )


def _slug(value: str) -> str:
    return normalize_slug_tag(value)


def _repo_mapping_payload() -> dict:
    mapping_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "config"
        / "category-mappings.yaml"
    )
    return yaml.safe_load(mapping_path.read_text(encoding="utf-8"))


def test_category_mapping_service_loads_context_schema(tmp_path: Path) -> None:
    mapping_path = tmp_path / "category-mappings.yaml"
    mapping_path.write_text(
        "\n".join(
            [
                "schema_version: '1.2'",
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

    assert not hasattr(response.mappings, "classification")
    assert response.mappings.categories[0].core_tags == ["macroeconomic_outlook"]
    assert response.mappings.categories[0].semantic_concepts == []
    assert response.mappings.high_confidence_fit_threshold == 0.85
    assert response.mappings.categories[0].supporting_tags == ["country_analysis"]
    assert response.mappings.categories[0].secondary_supporting_tags == [
        "interest_rates"
    ]
    assert response.mappings.categories[0].descriptor_tags == ["country_forecasts"]
    assert response.mappings.categories[0].generic_tags == ["digital_economy"]
    assert response.mappings.categories[0].negative_tags == ["social_media"]
    assert response.mappings.categories[0].must_have_one_of == ["macroeconomic_outlook"]
    assert response.mappings.categories[0].priority == 5
    assert len(response.mappings.inference_rules) == 1
    assert response.mappings.inference_rules[0].name == "macro_to_growth"
    assert (
        response.mappings.inference_rules[0].target_category_id
        == "business_performance"
    )
    assert response.mappings.inference_rules[0].trigger_tags == [
        "macroeconomic_outlook"
    ]
    assert response.mappings.inference_rules[0].inferred_tag == "business_performance"
    assert response.mappings.inference_rules[0].context_keywords_any == ["growth"]
    assert response.mappings.inference_rules[0].remove_tags == ["digital_economy"]


def test_category_mapping_service_rejects_non_mapping_root(
    tmp_path: Path,
    assert_app_error,
) -> None:
    mapping_path = tmp_path / "category-mappings.yaml"
    mapping_path.write_text("- not-a-mapping\n", encoding="utf-8")

    with pytest.raises(AppError) as exc_info:
        load_mappings(
            CategoryMappingLoadRequest(
                schema_version="1.0",
                path=str(mapping_path),
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="category_mapping_invalid_yaml",
        retryable=False,
    )


def test_category_mapping_service_does_not_expose_uncategorized_yaml_writes() -> None:
    assert not hasattr(category_mapping_service, "update_uncategorized_tags")
    assert not hasattr(category_mapping_service, "flush_uncategorized_tags")
    assert not hasattr(category_contracts, "UncategorizedTagsUpdateRequest")
    assert not hasattr(category_contracts, "UncategorizedTagsFlushRequest")


def test_repo_category_mapping_config_is_normalized() -> None:
    payload = _repo_mapping_payload()
    categories = payload.get("categories") or []
    inference_rules = payload.get("inference_rules") or []

    assert payload["high_confidence_fit_threshold"] == 0.85

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


def test_category_mapping_service_rejects_invalid_high_confidence_threshold(
    tmp_path: Path,
    assert_app_error,
) -> None:
    mapping_path = tmp_path / "category-mappings.yaml"
    mapping_path.write_text(
        "\n".join(
            [
                "high_confidence_fit_threshold: 1.0",
                "categories: []",
                "uncategorized: []",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(AppError) as exc_info:
        load_mappings(
            CategoryMappingLoadRequest(schema_version="1.0", path=str(mapping_path)),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="category_mapping_invalid_fit_threshold",
        retryable=False,
        severity="error",
    )


def test_repo_category_mapping_context_profiles_are_complete() -> None:
    payload = _repo_mapping_payload()

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


def test_repo_category_mapping_rule_and_coverage_tags_support_taxonomy_metadata() -> (
    None
):
    payload = _repo_mapping_payload()
    categories = payload.get("categories") or []
    inference_rules = payload.get("inference_rules") or []

    signal_tags_by_category: dict[str, set[str]] = {}
    all_supported_tags: set[str] = set()
    for item in categories:
        if not isinstance(item, dict):
            continue
        category_id = str(item.get("id") or "")
        signal_tags = set(item.get("core_tags") or [])
        signal_tags.update(item.get("supporting_tags") or [])
        signal_tags.update(item.get("secondary_supporting_tags") or [])
        signal_tags_by_category[category_id] = signal_tags
        all_supported_tags.update(item.get("descriptor_tags") or [])
        all_supported_tags.update(item.get("generic_tags") or [])
        all_supported_tags.update(signal_tags)

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
        signal_tags = signal_tags_by_category[target_category_id]
        assert rules
        for rule in rules:
            assert str(rule.get("inferred_tag") or "").strip() in signal_tags

    assert "generative_ai_and_ai_agents" in signal_tags_by_category["ai_automation"]
    assert "ai_and_productivity" in signal_tags_by_category["ai_automation"]
    assert (
        "generative_engine_optimisation_geo"
        in signal_tags_by_category["search_performance"]
    )
    assert (
        "brand_safety_and_suitability"
        in signal_tags_by_category["programmatic_ad_tech"]
    )
    assert "emerging_tech" in signal_tags_by_category["technology"]
    assert "tech_trends" in signal_tags_by_category["technology"]
    assert "ai_in_retail" in signal_tags_by_category["omnichannel_commerce"]


def test_repo_category_mapping_broad_descriptors_stay_out_of_signal_groups() -> None:
    payload = _repo_mapping_payload()
    categories = payload.get("categories") or []

    signal_tags: set[str] = set()
    descriptor_or_generic_tags: set[str] = set()
    for item in categories:
        if not isinstance(item, dict):
            continue
        signal_tags.update(item.get("core_tags") or [])
        signal_tags.update(item.get("supporting_tags") or [])
        signal_tags.update(item.get("secondary_supporting_tags") or [])
        descriptor_or_generic_tags.update(item.get("descriptor_tags") or [])
        descriptor_or_generic_tags.update(item.get("generic_tags") or [])

    broad_descriptor_tags = {
        "consumer_trends",
        "social_media",
        "digital_economy",
        "forecasts",
    }

    assert broad_descriptor_tags.issubset(descriptor_or_generic_tags)
    assert broad_descriptor_tags.isdisjoint(signal_tags)


def test_repo_category_mapping_uses_slug_tags_only() -> None:
    payload = _repo_mapping_payload()

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
