from __future__ import annotations

from src.contracts.categories import (
    CategoryDefinition,
    CategoryMappingLoadResponse,
    CategoryMappings,
)
from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressPostUpdateResponse,
    WordPressTaxonomyEnsureResponse,
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
        post_type="ml_report",
        mappings=_mappings(),
        ctx=_ctx(),
    )
    assert outcome.status == "skipped"
    assert outcome.error == "no_categories"
    assert outcome.categories == []


def test_wp_category_update_applies_categories(monkeypatch):
    monkeypatch.setattr(
        gen,
        "ensure_taxonomy_terms",
        lambda req, ctx: (
            (_ for _ in ()).throw(AssertionError("ssl_verify should be disabled"))
            if req.ssl_verify is not False
            else WordPressTaxonomyEnsureResponse(
                schema_version="1.0",
                slug_to_id={"digital_payments": 101, "consumer_behavior": 102},
            )
        ),
    )

    def _update(req, ctx):
        assert req.post_type == "ml_report"
        assert req.ssl_verify is False
        return WordPressPostUpdateResponse(schema_version="1.0", post_id=req.post_id)

    monkeypatch.setattr(gen, "update_post_categories", _update)

    outcome = gen.update_post_categories_for_record(
        file_id="file-1",
        post_id=10,
        categories=["digital_payments", "consumer_behavior"],
        base_url="https://example.com",
        auth_header="Bearer token",
        post_type="ml_report",
        ssl_verify=False,
        mappings=_mappings(),
        ctx=_ctx(),
    )
    assert outcome.status == "updated"
    assert outcome.post_id == 10
    assert outcome.categories == ["digital_payments", "consumer_behavior"]


def test_wp_category_update_skips_when_no_term_ids(monkeypatch):
    monkeypatch.setattr(
        gen,
        "ensure_taxonomy_terms",
        lambda req, ctx: WordPressTaxonomyEnsureResponse(
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
        post_type="ml_report",
        mappings=_mappings(),
        ctx=_ctx(),
    )
    assert outcome.status == "skipped"
    assert outcome.error == "no_category_ids"
