# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath
__file__ = str(_SplitPath(__file__).resolve().parent.parent / "test_publisher_inventory_candidate_quality_generator.py")

import json

import logging

from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateQualityRequest,
    PublisherInventoryCandidateScreeningItem,
    PublisherInventoryLandingPageInspectionResponse,
    PublisherInventoryLandingPageObservation,
    PublisherInventorySettings,
)

from src.contracts.run_context import RunContext

from src.generators.publisher_inventory_candidate_quality_generator import (
    qualify_publisher_inventory_candidates,
)

def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

def _settings() -> PublisherInventorySettings:
    return PublisherInventorySettings(
        schema_version="1.0",
        openrouter_api_key="openrouter-key",
        model="google/gemini-2.5-flash-lite",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=10,
        output_dir="./out/publisher_inventory_discovery",
        reports_db="./state/reports.sqlite",
        google_sa_path="./sa.json",
        prompt_namespace="publisher_inventory/discovery",
        pagination_max_pages=10,
        http_timeout_seconds=30.0,
        openrouter_http_referer=None,
        headed=False,
        force_browser=True,
        retry_retries=1,
        retry_base_delay_seconds=0.0,
        retry_backoff_step_seconds=0.0,
        retry_jitter_seconds=0.0,
        openai_api_key="openai-key",
        openai_models={},
        openai_seed=123,
        candidate_screening_enabled=True,
        candidate_screening_model="gpt-5-nano",
        candidate_screening_temperature=1.0,
        candidate_screening_timeout_seconds=45.0,
        candidate_screening_batch_size=20,
        candidate_screening_prompt_namespace="publisher_inventory/meaningful_candidate_screen",
        candidate_quality_check_enabled=True,
        candidate_quality_check_timeout_seconds=10.0,
        candidate_quality_check_max_workers=4,
    )

def _candidate(url: str, title: str) -> PublisherInventoryCandidateScreeningItem:
    return PublisherInventoryCandidateScreeningItem(
        schema_version="1.0",
        canonical_url=url,
        title=title,
        discovered_on_page_number=1,
        source_page_url="https://example.com/insights",
    )

def _observation(
    *,
    canonical_url: str,
    source_title: str,
    final_url: str,
    final_title: str = "",
    h1_title: str = "",
    og_title: str = "",
    http_status_code: int | None = 200,
    content_type: str = "text/html",
    fetch_error: str = "",
    is_pdf: bool = False,
    has_asset_type_term: bool = False,
    has_download_language: bool = False,
    has_gated_form: bool = False,
    has_document_structure: bool = False,
    has_price_or_purchase: bool = False,
    has_print_language: bool = False,
    has_editorial_url_pattern: bool = False,
    has_editorial_markers: bool = False,
    has_related_posts: bool = False,
    has_newsletter_cta: bool = False,
    has_contact_sales_cta: bool = False,
    has_dead_page_marker: bool = False,
    verification_class: str = "verified",
    recovery_eligible: bool = False,
    source_surface_class: str = "unknown",
) -> PublisherInventoryLandingPageObservation:
    return PublisherInventoryLandingPageObservation(
        schema_version="1.0",
        canonical_url=canonical_url,
        source_title=source_title,
        final_url=final_url,
        final_title=final_title,
        h1_title=h1_title,
        og_title=og_title,
        http_status_code=http_status_code,
        content_type=content_type,
        fetch_error=fetch_error,
        is_pdf=is_pdf,
        has_asset_type_term=has_asset_type_term,
        has_download_language=has_download_language,
        has_gated_form=has_gated_form,
        has_document_structure=has_document_structure,
        has_price_or_purchase=has_price_or_purchase,
        has_print_language=has_print_language,
        has_editorial_url_pattern=has_editorial_url_pattern,
        has_editorial_markers=has_editorial_markers,
        has_related_posts=has_related_posts,
        has_newsletter_cta=has_newsletter_cta,
        has_contact_sales_cta=has_contact_sales_cta,
        has_dead_page_marker=has_dead_page_marker,
        verification_class=verification_class,
        recovery_eligible=recovery_eligible,
        source_surface_class=source_surface_class,
    )



__all__ = [
    name
    for name in globals()
    if name
    not in {
        '__name__', '__annotations__', '__doc__', '__spec__',
        '__file__', '__package__', '__loader__', '__cached__',
        '__builtins__', '_SplitPath',
    }
]
