from __future__ import annotations

# ruff: noqa: E501
from pathlib import Path

import pytest

from src.contracts.wordpress_intelligence_projection import (
    WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
    WordPressIntelligenceBuildRequest,
    WordPressIntelligenceEntity,
    WordPressIntelligenceProjectionWriteResponse,
    WordPressIntelligenceSourceReadRequest,
    WordPressIntelligenceSourceReadResponse,
    WordPressIntelligenceSyncRequest,
    WordPressIntelligenceTerm,
)
from src.generators.wordpress_intelligence_projection_generator import (
    build_wordpress_intelligence_projection,
)
from src.orchestrators.wordpress_intelligence_projection_orchestrator import (
    WordPressIntelligenceProjectionDependencies,
    sync_wordpress_intelligence_projection,
)
from src.utils.errors import AppError

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "Wordpress" / "wp-content" / "plugins" / "marketlense-core"
PROJECTION = PLUGIN / "includes" / "class-marketlense-core-intelligence-projection.php"
STATS = PLUGIN / "includes" / "class-marketlense-core-intelligence-stats.php"


def _term(name: str, url: str, homepage: str = "") -> WordPressIntelligenceTerm:
    return WordPressIntelligenceTerm(
        schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
        name=name,
        url=url,
        homepage=homepage,
    )


def _entity(
    entity_id: str, entity_type: str, published_at_utc: str
) -> WordPressIntelligenceEntity:
    return WordPressIntelligenceEntity(
        schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
        entity_id=entity_id,
        entity_type=entity_type,  # type: ignore[arg-type]
        published_at_utc=published_at_utc,
        url=f"https://marketlense.local/{entity_id}",
        publishers=[
            _term(
                "Acme",
                "https://marketlense.local/publisher/acme",
                "https://acme.example",
            )
        ],
        topics=[_term("AI", "https://marketlense.local/category/ai")],
    )


def test_pipeline_projection_counts_only_approved_entities_and_preserves_freshness(
    assert_no_defaulted_required_fields,
) -> None:
    source = WordPressIntelligenceSourceReadResponse(
        schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
        entities=[
            _entity("report-1", "ml_report", "2026-07-12T10:00:00Z"),
            _entity("briefing-1", "ml_briefing", "2026-07-11T10:00:00Z"),
            _entity("signal-1", "ml_signal", "2026-06-20T10:00:00Z"),
        ],
    )
    projection = build_wordpress_intelligence_projection(
        WordPressIntelligenceBuildRequest(
            schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
            source=source,
            generated_at_utc="2026-07-13T12:00:00Z",
        )
    )

    assert projection.homepage_metrics.report_count == 1
    assert projection.homepage_metrics.briefing_count == 1
    assert projection.homepage_metrics.signal_count == 1
    assert projection.homepage_metrics.publisher_count == 1
    assert projection.homepage_metrics.topic_count == 1
    assert projection.homepage_metrics.latest_label == "Updated 2026-07-12"
    assert projection.weekly_signals.window_label == "Past 30 days"
    assert projection.publisher_authority[0].name == "Acme"
    assert_no_defaulted_required_fields(projection)


def test_projection_rejects_invalid_source_timestamps(assert_app_error) -> None:
    source = WordPressIntelligenceSourceReadResponse(
        schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
        entities=[_entity("report-1", "ml_report", "not-a-timestamp")],
    )
    with pytest.raises(AppError) as error:
        build_wordpress_intelligence_projection(
            WordPressIntelligenceBuildRequest(
                schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
                source=source,
                generated_at_utc="2026-07-13T12:00:00Z",
            )
        )
    assert_app_error(
        error.value,
        code="wordpress_intelligence_source_timestamp_invalid",
        retryable=False,
    )


def test_orchestrator_writes_the_projection_built_from_its_read_source(
    run_context,
) -> None:
    source = WordPressIntelligenceSourceReadResponse(
        schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
        entities=[_entity("report-1", "ml_report", "2026-07-12T10:00:00Z")],
    )
    writes = []

    def _read_source(_request, _ctx):
        return source

    def _write_projection(request, _ctx):
        writes.append(request)
        return WordPressIntelligenceProjectionWriteResponse(
            schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
            projection_version=request.projection.projection_version,
            generated_at_utc=request.projection.generated_at_utc,
            status="stored",
        )

    response = sync_wordpress_intelligence_projection(
        WordPressIntelligenceSyncRequest(
            schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
            source_request=WordPressIntelligenceSourceReadRequest(
                schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
                base_url="https://marketlense.local",
                auth_header="Basic redacted",
                ssl_verify=True,
                ca_bundle_path=None,
            ),
            generated_at_utc="2026-07-13T12:00:00Z",
        ),
        run_context,
        dependencies=WordPressIntelligenceProjectionDependencies(
            read_source=_read_source,
            build_projection=build_wordpress_intelligence_projection,
            write_projection=_write_projection,
        ),
    )

    assert response.entity_count == 1
    assert len(writes) == 1
    assert writes[0].projection == response.projection


def test_wordpress_renders_only_validated_pipeline_projections() -> None:
    projection = PROJECTION.read_text(encoding="utf-8")
    stats = STATS.read_text(encoding="utf-8")

    assert "'/intelligence-source'" in projection
    assert "'/intelligence-projection'" in projection
    assert "current_user_can('manage_options')" in projection
    assert "update_option(self::OPTION_NAME, $normalized, false)" in projection
    assert "return $this->neutral_homepage_metrics();" in stats
    assert "$this->intelligence_projection->current()" in stats
    assert "derived_signal_count" not in stats
