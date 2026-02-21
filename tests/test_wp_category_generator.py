from __future__ import annotations

from src.contracts.categories import (
    CategoryDefinition,
    CategoryMappingLoadResponse,
    CategoryMappings,
)
from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressCategoryEnsureResponse,
    WordPressPostUpdateResponse,
)
from src.generators import wp_category_generator as gen


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _mappings() -> CategoryMappingLoadResponse:
    return CategoryMappingLoadResponse(
        schema_version="1.0",
        mappings=CategoryMappings(
            schema_version="1.0",
            categories=[
                CategoryDefinition(
                    schema_version="1.0",
                    id="digital_payments",
                    label="Digital Payments",
                    description="Payments category",
                    tags=["payments"],
                ),
                CategoryDefinition(
                    schema_version="1.0",
                    id="consumer_behavior",
                    label="Consumer Behavior",
                    description="Behavior category",
                    tags=["behavior"],
                ),
            ],
            uncategorized=[],
        ),
    )


def test_wp_category_update_skips_when_no_categories():
    outcome = gen.update_post_categories_for_record(
        file_id="file-1",
        post_id=10,
        categories=[],
        base_url="https://example.com",
        auth_header="Bearer token",
        mappings=_mappings(),
        ctx=_ctx(),
    )
    assert outcome.status == "skipped"
    assert outcome.error == "no_categories"
    assert outcome.categories == []


def test_wp_category_update_applies_categories(monkeypatch):
    monkeypatch.setattr(
        gen,
        "ensure_categories",
        lambda req, ctx: WordPressCategoryEnsureResponse(
            schema_version="1.0",
            slug_to_id={"digital_payments": 101, "consumer_behavior": 102},
        ),
    )
    monkeypatch.setattr(
        gen,
        "update_post_categories",
        lambda req, ctx: WordPressPostUpdateResponse(
            schema_version="1.0", post_id=req.post_id
        ),
    )

    outcome = gen.update_post_categories_for_record(
        file_id="file-1",
        post_id=10,
        categories=["digital_payments", "consumer_behavior"],
        base_url="https://example.com",
        auth_header="Bearer token",
        mappings=_mappings(),
        ctx=_ctx(),
    )
    assert outcome.status == "updated"
    assert outcome.post_id == 10
    assert outcome.categories == ["digital_payments", "consumer_behavior"]


def test_wp_category_update_skips_when_no_term_ids(monkeypatch):
    monkeypatch.setattr(
        gen,
        "ensure_categories",
        lambda req, ctx: WordPressCategoryEnsureResponse(
            schema_version="1.0",
            slug_to_id={},
        ),
    )
    monkeypatch.setattr(
        gen,
        "update_post_categories",
        lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("update_post_categories should not be called")
        ),
    )

    outcome = gen.update_post_categories_for_record(
        file_id="file-1",
        post_id=10,
        categories=["digital_payments"],
        base_url="https://example.com",
        auth_header="Bearer token",
        mappings=_mappings(),
        ctx=_ctx(),
    )
    assert outcome.status == "skipped"
    assert outcome.error == "no_category_ids"
