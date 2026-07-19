from __future__ import annotations

import sqlite3
from pathlib import Path

from src.contracts.publisher_profiles import PublisherProfileRecord
from src.contracts.report_store import PublishersReplaceRequest
from src.services.report_store_service import replace_publishers
from src.utils.logging import new_run_context


def test_report_store_schema_authority_is_sqlite_migration_service(
    tmp_path: Path,
) -> None:
    legacy_schema_module = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "services"
        / "_report_store_service"
        / "schema.py"
    )
    assert not legacy_schema_module.exists()

    db_path = tmp_path / "reports.sqlite"
    replace_publishers(
        PublishersReplaceRequest(
            schema_version="1.0",
            db_path=str(db_path),
            source_page_url="https://www.notion.so/source",
            publishers=[
                PublisherProfileRecord(
                    schema_version="1.0",
                    notion_page_id="page-1",
                    notion_page_url="https://www.notion.so/page-1",
                    name="Migration Authority Publisher",
                    homepage="https://example.com/",
                    self_presentation="Publisher description",
                    insights_url="https://example.com/insights",
                    icon_source="https://cdn.example.com/icon.png",
                )
            ],
        ),
        new_run_context(task_id="test_report_store_schema_authority"),
    )

    with sqlite3.connect(db_path) as conn:
        schema_version = conn.execute(
            """
            SELECT current_version
            FROM schema_version
            WHERE database_key='reports_db'
            """
        ).fetchone()
        applied_migrations = conn.execute(
            """
            SELECT migration_id
            FROM schema_migration_ledger
            WHERE database_key='reports_db'
            ORDER BY version ASC
            """
        ).fetchall()
        publisher = conn.execute(
            """
            SELECT name, normalized_insights_url
            FROM publishers
            """
        ).fetchone()
        private_api_table = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='publisher_private_api_candidates'
            """
        ).fetchone()

    assert schema_version == (22,)
    assert applied_migrations == [
        ("reports_db_001_create_reports_core",),
        ("reports_db_002_create_report_sources_base",),
        ("reports_db_003_normalize_report_sources",),
        ("reports_db_004_create_publishers_base",),
        ("reports_db_005_normalize_publishers",),
        ("reports_db_006_create_or_upgrade_download_route_history",),
        ("reports_db_007_normalize_inventory_recovery_cache",),
        ("reports_db_008_create_inventory_route_history",),
        ("reports_db_009_add_reports_projection_columns",),
        ("reports_db_010_create_analytics_projection_tables",),
        ("reports_db_011_add_report_source_value_scores",),
        ("reports_db_012_create_private_api_candidate_ledger",),
        ("reports_db_013_create_signal_candidate_projection",),
        ("reports_db_014_create_claim_embedding_records",),
        ("reports_db_015_create_artifact_lineage_registry",),
        ("reports_db_016_add_claim_embedding_queue_controls",),
        ("reports_db_017_add_lineage_execution_planning",),
        ("reports_db_018_create_source_publication_metadata",),
        ("reports_db_019_create_source_identity_observations",),
        ("reports_db_020_expand_execution_plan_audit",),
        ("reports_db_021_create_acquisition_resource_telemetry",),
        ("reports_db_022_add_execution_plan_prompt_family_reconciliation",),
    ]
    assert private_api_table == ("publisher_private_api_candidates",)
    assert publisher == (
        "Migration Authority Publisher",
        "https://example.com/insights",
    )
